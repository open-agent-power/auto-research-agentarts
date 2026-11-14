"""HTTP binding and selector checks on fake read-only projects, without research."""
from copy import deepcopy
import json
from pathlib import Path
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from autoresearch import project_workbench as workbench


class _Project:
    def __init__(self, identity="project-cpu", snapshot="a" * 64):
        self.root = Path("/nonexistent-protocol-http-fixture")
        self.value = {"id": identity, "run_id": "run-cpu", "snapshot_ref": snapshot,
                      "state_version": 0, "source_scope": {}, "actions": []}

    def status(self):
        return deepcopy(self.value)


class _Manager:
    def __init__(self):
        self.project = _Project()

    def binding(self):
        return self.project, None


class FixedProtocolHttpTests(unittest.TestCase):
    def setUp(self):
        self.manager = _Manager()
        self.server = workbench.create_project_server(local_workspace=self.manager, port=0)
        self.thread = Thread(target=lambda: self.server.serve_forever(poll_interval=.01), daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.selector = {"project_id": "project-cpu", "snapshot_ref": "a" * 64}

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def get(self, query=None):
        suffix = urlencode(self.selector) if query is None else query
        url = f"http://127.0.0.1:{self.server.server_port}/api/project/fixed-protocol.json?{suffix}"
        try:
            with urlopen(url, timeout=5) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            return error.code, json.loads(error.read())

    def test_readonly_route_works_without_report_or_actions(self):
        saved = {"schema_version": "fixed-cpu-protocol-view-v1", "binding": {"project_id": "project-cpu"}}
        before = deepcopy(self.manager.project.value)
        with patch.object(workbench, "read_fixed_protocol", return_value=saved) as reader:
            status, actual = self.get()
        self.assertEqual((status, actual), (200, saved))
        self.assertEqual(reader.call_count, 1)
        self.assertIs(reader.call_args.args[0], self.manager.project)
        self.assertEqual(self.manager.project.value, before)

    def test_bad_selectors_reject_before_reading_source(self):
        valid = urlencode(self.selector)
        invalid = ["", "project_id=project-cpu", "snapshot_ref=" + "a" * 64,
                   valid + "&path=/etc/passwd", valid + "&method_id=research.other",
                   valid + "&project_id=project-cpu", "project_id=&snapshot_ref=" + "a" * 64,
                   "project_id=project-cpu&snapshot_ref=bad", "project_id=%FF&snapshot_ref=" + "a" * 64,
                   "project_id=" + "x" * 1025 + "&snapshot_ref=" + "a" * 64]
        with patch.object(workbench, "read_fixed_protocol", side_effect=AssertionError("No source read")) as reader:
            for query in invalid:
                with self.subTest(query=query[:100]):
                    status, result = self.get(query)
                    self.assertEqual(status, 400)
                    self.assertFalse(result["ok"])
        reader.assert_not_called()

    def test_stale_project_or_snapshot_reject_before_reading_source(self):
        with patch.object(workbench, "read_fixed_protocol", side_effect=AssertionError("No source read")) as reader:
            for selector in ({**self.selector, "project_id": "project-other"},
                             {**self.selector, "snapshot_ref": "b" * 64}):
                self.assertEqual(self.get(urlencode(selector))[0], 409)
        reader.assert_not_called()

    def test_project_switch_during_read_never_returns_the_old_protocol(self):
        def switch(project, state):
            self.manager.project = _Project("project-other", "b" * 64)
            return {"schema_version": "fixed-cpu-protocol-view-v1", "binding": {"project_id": state["id"]}}
        with patch.object(workbench, "read_fixed_protocol", side_effect=switch):
            status, result = self.get()
        self.assertEqual(status, 409)
        self.assertEqual(result["code"], "STALE_STATE")

    def test_same_project_snapshot_change_during_read_rejects(self):
        def change(project, state):
            project.value["snapshot_ref"] = "b" * 64
            return {"schema_version": "fixed-cpu-protocol-view-v1"}
        with patch.object(workbench, "read_fixed_protocol", side_effect=change):
            self.assertEqual(self.get()[0], 409)

    def test_http_serialization_retains_the_response_byte_bound(self):
        with patch.object(workbench, "read_fixed_protocol", return_value={"oversized": "x" * 131072}):
            status, result = self.get()
        # An oversized server-produced view is an internal projection failure;
        # retain the workbench's existing error classification.
        self.assertEqual(status, 500)
        self.assertEqual(result["code"], "READER_TOO_LARGE")


if __name__ == "__main__":
    unittest.main()
