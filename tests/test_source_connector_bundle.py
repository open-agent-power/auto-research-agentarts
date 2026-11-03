"""Original response and derived source projections remain separate and bound."""
import json
import unittest

import test_europe_pmc as fixtures
from autoresearch import source_connector_bundle as bridge, source_evidence_adapter
from autoresearch.project_controller import ProjectController


class SourceBundleTests(unittest.TestCase):
    setUp = fixtures.PublicSourceTests.setUp
    transport = fixtures.PublicSourceTests.transport
    assert_code = fixtures.PublicSourceTests.assert_code

    def test_raw_bytes_projection_and_provenance_enter_existing_read_path(self):
        with self.transport():
            self.connector.fetch("get", fixtures.DOI, self.root / "http")
        prepared = bridge.build_bundle(workspace=self.project.root, request_id="get", output=self.root / "prepared")
        self.assertEqual(prepared["lookup"]["exact_doi_matches_in_page"], 1)
        self.assertEqual((self.root / "prepared/sources/provider-response.json").read_bytes(), fixtures.RAW)
        projection = (self.root / "prepared/sources/host-projection.txt").read_text(encoding="utf-8")
        self.assertIn('"provider_json_pointer":"/resultList/result/0/title"', projection)
        self.assertIn('host_derived_projection', projection)
        receipt, assets = source_evidence_adapter.capture_bundle(self.root / "prepared", self.project.evidence_task()["task_ref"])
        self.assertEqual(len(receipt["sources"]), 3)
        self.assertEqual(len(receipt["selections"]), 2)
        self.assertEqual(assets["provider-response"], fixtures.RAW)
        self.project.register_evidence(request_id="register", bundle=self.root / "prepared")
        self.assertEqual(self.project.status()["budget"]["evidence_reads_used"], 0)
        self.assertEqual(ProjectController(self.project.root).advance(request_id="read")["status"], "completed")
        self.assertEqual(self.project.status()["research_status"], "waiting")
        self.assertTrue(all(o["endpoint_eligibility"] == "unknown" for o in self.project.status()["evidence_actions"][0]["observations"]))

    def test_zero_is_scoped_and_malformed_provider_data_are_not_projected(self):
        projected, result = bridge._projection(b'{"hitCount":0,"resultList":{"result":[]}}', fixtures.DOI, "a"*64)
        self.assertTrue(result["provider_zero_results"])
        self.assertIn(b"does not prove", projected)
        for raw in (b'{"hitCount":0,"hitCount":1,"resultList":{"result":[]}}',
                    b'{"hitCount":1,"resultList":{"result":[]}}', b'{"hitCount":NaN,"resultList":{"result":[]}}'):
            with self.subTest(raw=raw):
                self.assert_code("PROVIDER_JSON_INVALID", bridge._projection, raw=raw, doi=fixtures.DOI, raw_sha="a"*64)


if __name__ == "__main__":
    unittest.main()
