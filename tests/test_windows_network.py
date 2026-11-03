"""Synthetic IP Helper tables plus a listener owned by this test process only."""
import ctypes
import os
import socket
import struct
import unittest
from unittest.mock import patch

from autoresearch import windows_network as module
from autoresearch.contracts import ResearchError


PORT = 11436  # Synthetic only; actual test listeners use an ephemeral port.


def row(*, ip='127.0.0.1', port=PORT, pid=1234, state=2, high_port_bits=0):
    address = struct.unpack('<I', socket.inet_aton(ip))[0]
    return struct.pack('<6I', state, address, socket.htons(port) | high_port_bits, 0, 0, pid)


def table(*rows):
    return struct.pack('<I', len(rows))+b''.join(rows)


class FakeTableAPI:
    """Events are (Windows result code, reported size, optional table bytes)."""
    def __init__(self, events): self.events, self.calls = list(events), []
    def __call__(self, buffer, size_pointer, ordered, family, table_class, reserved):
        size = ctypes.cast(size_pointer, ctypes.POINTER(ctypes.c_uint32))
        capacity = size.contents.value
        self.calls.append((buffer is None, capacity, ordered, family, table_class, reserved))
        result, reported, payload = self.events.pop(0)
        size.contents.value = reported
        if buffer is not None and payload is not None:
            ctypes.memmove(buffer, payload, min(capacity, len(payload)))
        return result


class WindowsNetworkTests(unittest.TestCase):
    def error(self, operation):
        with self.assertRaises(ResearchError) as error: operation()
        self.assertEqual(error.exception.code, 'OWNERSHIP_UNVERIFIED')

    def test_exact_ipv4_listener_with_network_order_port_returns_its_pid(self):
        self.assertEqual(ctypes.sizeof(module._Row), 24)
        self.assertEqual(module._Table.rows.offset, 4)
        for port in (1024, PORT, 65535):
            self.assertEqual(module.parse_listener_pid(table(row(port=port)), port), 1234)
        self.assertEqual(module.parse_listener_pid(table(row(high_port_bits=0xabcd0000)), PORT), 1234)

    def test_wildcard_other_loopback_nonlistener_and_wrong_port_are_never_adopted(self):
        for values in ({'ip': '0.0.0.0'}, {'ip': '127.0.0.2'}, {'ip': '192.0.2.1'}, {'state': 5}, {'port': PORT+1}):
            with self.subTest(values=values):
                self.error(lambda: module.parse_listener_pid(table(row(**values)), PORT))
        mixed = table(row(ip='0.0.0.0', pid=9999), row(state=5, pid=8888), row(pid=1234))
        self.assertEqual(module.parse_listener_pid(mixed, PORT), 1234)

    def test_unique_pid_semantics_allow_same_pid_rows_but_reject_ambiguous_or_zero_owner(self):
        self.assertEqual(module.parse_listener_pid(table(row(), row()), PORT), 1234)
        for payload in (table(), table(row(pid=0)), table(row(pid=1234), row(pid=4321)), table(row(pid=0), row())):
            self.error(lambda: module.parse_listener_pid(payload, PORT))

    def test_header_count_cannot_read_truncated_rows_or_an_oversized_buffer(self):
        for payload in (None, [], bytearray(table(row())), b'', b'\0'*3,
                        struct.pack('<I', 1)+row()[:-1], struct.pack('<I', 2)+row(),
                        struct.pack('<I', 0xffffffff), b'\0'*(module.MAX_TABLE_BYTES+1)):
            self.error(lambda: module.parse_listener_pid(payload, PORT))

    def test_unused_capacity_is_not_mistaken_for_more_active_rows(self):
        payload = table(row())+row(pid=4321)+b'\xff'*7
        self.assertEqual(module.parse_listener_pid(payload, PORT), 1234)

    def test_port_validation_is_strict_and_does_not_call_the_operating_system(self):
        with patch.object(module, '_function', side_effect=AssertionError('invalid port must not query OS')):
            for port in (True, False, None, '11436', 11436.0, 0, 1023, 65536):
                self.error(lambda: module.listener_pid(port))
                self.error(lambda: module.parse_listener_pid(table(row()), port))

    def test_read_table_uses_listener_class_ipv4_reserved_zero_and_exact_success_size(self):
        payload = table(row())
        api = FakeTableAPI([(122, len(payload), None), (0, len(payload), payload)])
        self.assertEqual(module._read_table(api), payload)
        self.assertEqual(api.calls, [(True, 0, False, 2, 3, 0), (False, len(payload), False, 2, 3, 0)])

    def test_finite_resize_handles_growth_without_returning_an_old_or_partial_table(self):
        payload = table(row())
        api = FakeTableAPI([(122, 4, None), (122, len(payload), None), (0, len(payload), payload)])
        self.assertEqual(module.parse_listener_pid(module._read_table(api), PORT), 1234)
        self.assertEqual(len(api.calls), 3)
        growth = FakeTableAPI([(122, 4, None)]+[(122, 4+24*(n+1), None) for n in range(module.MAX_READ_ATTEMPTS)])
        self.error(lambda: module._read_table(growth))
        self.assertEqual(len(growth.calls), 1+module.MAX_READ_ATTEMPTS)

    def test_api_errors_bad_growth_and_out_of_bound_sizes_fail_without_fallback(self):
        cases = [
            [(5, 0, None)], [(0, 4, None)], [(122, 0, None)], [(122, 3, None)],
            [(122, module.MAX_TABLE_BYTES+1, None)],
            [(122, 4, None), (5, 4, None)], [(122, 4, None), (122, 4, None)],
            [(122, 4, None), (0, 0, None)], [(122, 4, None), (0, 5, None)],
            [(122, 4, None), (122, module.MAX_TABLE_BYTES+1, None)],
        ]
        for events in cases:
            with self.subTest(events=events): self.error(lambda: module._read_table(FakeTableAPI(events)))

    def test_native_binding_failure_is_structured_and_unsupported_platform_is_fail_closed(self):
        with patch.object(module, '_function', side_effect=OSError('synthetic native error')):
            self.error(lambda: module.listener_pid(PORT))
        with patch.object(module.os, 'name', 'posix'):
            self.error(lambda: module.listener_pid(PORT))

    @unittest.skipUnless(os.name == 'nt', 'actual IP Helper lookup is Windows-only')
    def test_own_loopback_listener_is_current_process_and_closed_socket_is_not_a_listener(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            self.assertEqual(module.listener_pid(port), os.getpid())
        try: owner = module.listener_pid(port)
        except ResearchError as error: self.assertEqual(error.code, 'OWNERSHIP_UNVERIFIED')
        else: self.assertNotEqual(owner, os.getpid())


if __name__ == '__main__': unittest.main()
