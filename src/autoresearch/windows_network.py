"""Read a momentary exact IPv4 listener owner using Windows IP Helper only.

This neither adopts/manages a process nor grants a durable ownership lease.
Microsoft: GetExtendedTcpTable (AF_INET, TCP_TABLE_OWNER_PID_LISTENER),
MIB_TCPROW_OWNER_PID and MIB_TCPTABLE_OWNER_PID:
https://learn.microsoft.com/en-us/windows/win32/api/iphlpapi/nf-iphlpapi-getextendedtcptable
https://learn.microsoft.com/en-us/windows/win32/api/tcpmib/ns-tcpmib-mib_tcprow_owner_pid
"""
import ctypes
import os
import socket
import struct

from .contracts import ResearchError

MAX_TABLE_BYTES = 2 * 1024 * 1024
MAX_READ_ATTEMPTS = 3
AF_INET, OWNER_PID_LISTENER, INSUFFICIENT_BUFFER = 2, 3, 122


class _Row(ctypes.LittleEndianStructure):
    _fields_ = [(name, ctypes.c_uint32) for name in
                ('state', 'local_address', 'local_port', 'remote_address', 'remote_port', 'pid')]


class _Table(ctypes.LittleEndianStructure):
    _fields_ = [('count', ctypes.c_uint32), ('rows', _Row * 1)]


def _require(condition, message='IPv4 listener ownership could not be verified'):
    if not condition: raise ResearchError('OWNERSHIP_UNVERIFIED', message)


def _port(port):
    _require(type(port) is int and 1024 <= port <= 65535, 'dedicated port must be an integer in1024..65535')


def parse_listener_pid(payload, port):
    """Parse bounded table bytes; ignore unused capacity beyond the row count."""
    _port(port)
    stride, offset = ctypes.sizeof(_Row), _Table.rows.offset
    _require(stride == 24 and offset >= 4 and type(payload) is bytes and offset <= len(payload) <= MAX_TABLE_BYTES)
    count = struct.unpack_from('<I', payload)[0]
    _require(count <= (len(payload)-offset)//stride, 'truncated TCP owner table')
    loopback = struct.unpack('<I', socket.inet_aton('127.0.0.1'))[0]
    owners = set()
    for index in range(count):
        row = _Row.from_buffer_copy(payload, offset+index*stride)
        # Only the low16 bits of the DWORD port encode the network-order port.
        if row.state == 2 and row.local_address == loopback and socket.ntohs(row.local_port & 0xffff) == port:
            owners.add(row.pid)
    _require(len(owners) == 1 and next(iter(owners)) > 0, 'no unique exact127.0.0.1 LISTEN owner')
    return next(iter(owners))


def _read_table(function):
    size = ctypes.c_uint32(0)
    result = function(None, ctypes.byref(size), False, AF_INET, OWNER_PID_LISTENER, 0)
    _require(result == INSUFFICIENT_BUFFER, 'TCP owner table size probe failed')
    for _ in range(MAX_READ_ATTEMPTS):
        capacity = size.value
        _require(4 <= capacity <= MAX_TABLE_BYTES, 'TCP owner table exceeds its byte bound')
        buffer = ctypes.create_string_buffer(capacity)
        result = function(buffer, ctypes.byref(size), False, AF_INET, OWNER_PID_LISTENER, 0)
        if result == 0:
            _require(4 <= size.value <= capacity, 'invalid TCP owner table result size')
            return buffer.raw[:size.value]
        _require(result == INSUFFICIENT_BUFFER and size.value > capacity, 'TCP owner table read failed')
    raise ResearchError('OWNERSHIP_UNVERIFIED', 'TCP owner table kept growing; bounded lookup stopped')


def _function():
    _require(os.name == 'nt', 'Windows IP Helper is required for listener ownership')
    function = ctypes.WinDLL('iphlpapi.dll', use_last_error=True).GetExtendedTcpTable
    function.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.c_int,
                         ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    function.restype = ctypes.c_uint32
    return function


def listener_pid(port):
    """Return the sole exact loopback LISTEN PID, or fail closed without fallback."""
    _port(port)
    try:
        return parse_listener_pid(_read_table(_function()), port)
    except ResearchError: raise
    except (OSError, ValueError, TypeError, OverflowError, ctypes.ArgumentError):
        raise ResearchError('OWNERSHIP_UNVERIFIED', 'Windows TCP owner lookup failed') from None
