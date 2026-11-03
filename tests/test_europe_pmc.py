"""Public-source transport fixtures: no actual sockets, models or research fits."""
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import test_research_project as fixtures
from autoresearch import europe_pmc as epmc
from autoresearch.project_controller import ProjectController

DOI = "10.1016/j.biomaterials.2021.120740"
RAW = json.dumps({"hitCount": 1, "resultList": {"result": [{"id": "fixture-id", "source": "MED", "doi": DOI,
                  "title": "Fixture metadata, not author mapping", "isOpenAccess": "Y"}]}}, separators=(",", ":")).encode()


class Response(io.BytesIO):
    def __init__(self, raw, url, status=200):
        super().__init__(raw)
        self.url, self.status = url, status
        self.headers = {"content-type": "application/json", "content-length": str(len(raw))}

    def getcode(self): return self.status
    def geturl(self): return self.url


class PublicSourceTests(unittest.TestCase):
    assert_code = fixtures.ResearchProjectTests.assert_code

    def setUp(self):
        fixtures.ResearchProjectTests.setUp(self)
        self.bundle = fixtures.ResearchProjectTests.bundle(self)[0]
        self.connector = epmc.EuropePmcSource(self.project.root)

    def transport(self, raw=RAW, status=200):
        def spawn(argv, **kwargs):
            folder = Path(argv[-1])
            metadata = json.loads((folder / "request.json").read_bytes())
            opener = unittest.mock.Mock()
            opener.open.side_effect = lambda request, timeout: Response(raw, request.full_url, status)
            with patch.object(epmc, "build_opener", return_value=opener):
                epmc._transport_worker(folder, metadata)
            child = unittest.mock.Mock()
            child.wait.return_value = 0
            child.poll.return_value = 0
            return child
        return patch.object(epmc.subprocess, "Popen", side_effect=spawn)

    def test_fixed_endpoint_replay_namespace_and_frozen_allowance(self):
        query = urlsplit(epmc._url(DI := epmc._doi(DOI)))
        self.assertEqual((query.scheme, query.netloc, query.path), ("https", "www.ebi.ac.uk", "/europepmc/webservices/rest/search"))
        self.assertEqual(parse_qs(query.query)["query"], ['DOI:"' + DI + '"'])
        with self.transport() as network:
            value = self.connector.fetch("get-one", DOI, self.root / "response")
            self.assertEqual(value["status"], "received")
            self.assertEqual((self.root / "response/response.bin").read_bytes(), RAW)
            self.assertTrue(self.connector.fetch("get-one", DOI, self.root / "response")["replayed"])
            self.assert_code("IDEMPOTENCY_CONFLICT", self.connector.fetch, request_id="get-one", doi=DOI, output=self.root / "changed-output")
            self.assert_code("SOURCE_ALREADY_REQUESTED", self.connector.fetch, request_id="new-id", doi=DOI, output=self.root / "new-output")
            self.assert_code("INVALID_DOI", self.connector.fetch, request_id="injection", doi=DOI+'" OR *', output=self.root / "bad")
            network.assert_called_once()
        self.assert_code("IDEMPOTENCY_CONFLICT", self.project.step, request_id="get-one")
        self.assert_code("IDEMPOTENCY_CONFLICT", ProjectController(self.project.root).advance, request_id="get-one")
        with patch.object(epmc, "SOURCE_REQUEST_LIMIT", 99):
            self.assertEqual(self.connector.status("get-one")["source_request_limit"], 8)
        state = self.project.status()
        self.assertEqual(state["budget"]["source_requests_used"], 1)
        self.assertEqual(state["budget"]["source_request_limit"], 8)
        self.assertEqual(state["budget"]["evidence_reads_used"], 0)

    def test_missing_response_retains_unknown_and_blocks_new_work(self):
        with patch.object(epmc.subprocess, "Popen", side_effect=OSError("controlled no process")) as network:
            self.assertEqual(self.connector.fetch("unknown", DOI, self.root / "unknown")["status"], "unknown")
            self.assertEqual(self.connector.status("unknown")["status"], "unknown")
            self.assertEqual(self.connector.fetch("unknown", DOI, self.root / "unknown")["status"], "unknown")
            self.assert_code("SOURCE_REQUEST_UNKNOWN", self.connector.fetch, request_id="bypass", doi="10.1000/other", output=self.root / "bypass")
            network.assert_called_once()
        self.assertFalse(ProjectController(self.project.root).next()["executable"])
        self.assert_code("EXECUTION_UNKNOWN", self.project.register_evidence, request_id="read-bypass", bundle=self.bundle)
        self.assert_code("EXECUTION_UNKNOWN", self.project.upgrade, request_id="upgrade-bypass",
                         expected_code_identity=self.project.status()["code_identity"])
        self.assertEqual(self.project.status()["budget"]["source_requests_reserved"], 1)

    def test_completed_receipt_recovers_after_commit_interruption_without_resend(self):
        with self.transport() as network:
            with patch.object(self.connector, "_recover_locked", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    self.connector.fetch("interrupted", DOI, self.root / "interrupted")
            recovered = epmc.EuropePmcSource(self.project.root).status("interrupted")
            self.assertEqual(recovered["status"], "received")
            network.assert_called_once()
        self.assertEqual(self.project.status()["budget"]["source_requests_reserved"], 0)

    def test_bad_json_is_retained_as_failed_and_output_changes_cannot_reset_budget(self):
        with self.transport(raw=b'{"error":"fixture, not zero results"}') as network:
            for index in range(8):
                result = self.connector.fetch("failure-"+str(index), "10.1000/fixture"+str(max(0, index-1)), self.root / ("failure-"+str(index)))
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["failure"]["code"], "INVALID_SOURCE_RESPONSE")
            self.assert_code("SOURCE_BUDGET_EXHAUSTED", self.connector.fetch,
                             request_id="over-budget", doi="10.1000/ninth", output=self.root / "ninth")
            self.assertEqual(network.call_count, 8)
        self.assertEqual(self.project.status()["budget"]["source_requests_used"], 8)


if __name__ == "__main__":
    unittest.main()
