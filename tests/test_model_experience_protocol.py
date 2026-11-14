"""Synthetic protocol fixtures; no model, CLI, API, tool dispatch or research."""
import copy
import hashlib
import unittest
from unittest.mock import patch

import test_experience_case_refs as case_fixture
import test_project_selection_view as view_fixture
from autoresearch import host_model_report, host_model_selection
from autoresearch import host_selection_protocol as host, project_model_protocol as native
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.project_selection import seal_context


class ModelExperienceProtocolTests(unittest.TestCase):
    def setUp(self):
        fixture = case_fixture.ExperienceCaseReferenceTests()
        fixture.setUp()
        self.legacy_case = fixture.context
        self.ref = fixture.ref
        self.empty = view_fixture.ProjectSelectionViewTests().context()
        payload = {k: copy.deepcopy(v) for k, v in self.legacy_case.items() if k != "context_sha256"}
        payload["selection_capabilities"] = {"experience_case_refs": "v1"}
        self.context = seal_context(payload)
        self.identity = {"schema_version": "project-local-model-identity-v1", "transport": "owned-local-ollama",
            "model": "qwen3:4b", "publisher_manifest_sha256": native.PUBLISHER_MANIFEST_SHA256,
            "executable_sha256": "f" * 64, "cloud_disabled": True}
        self.arguments = {"choice": {"kind": "wait"}, "rationale": "An adverse historical example remains scoped.",
                          "evidence_citation_ids": [], "experience_case_refs": [self.ref]}

    @staticmethod
    def sha(value):
        return hashlib.sha256(canonical(value).encode()).hexdigest()

    def native_parse(self, context, arguments):
        raw = canonical({"model": "qwen3:4b", "done": True, "message": {"role": "assistant",
            "tool_calls": [{"function": {"name": native.TOOL_NAME, "arguments": arguments}}]}}).encode()
        receipt = {"schema_version": "project-model-transport-receipt-v1", "identity": self.identity,
            "request_sha256": fingerprint(native.build_request(context, self.identity)),
            "response_sha256": hashlib.sha256(raw).hexdigest(), "execution": "fixture", "process": {}}
        return native.parse_response(raw, context, receipt)

    def test_prechange_golden_wire_bytes_for_old_context_with_and_without_case(self):
        for context, host_sha, native_sha in (
            (self.legacy_case, "82295aa762cf1f8105f942b4edefd7962ddd883a42b569ac930e43af0b83af97", "de8f6abe969a29cd475c5096689e0ee79783c1020483bbd1bc121df07bffe294"),
            (self.empty, "0112a9c58901ff6f3c42ec25ab0d86c03f367ce0d3d9ecec5c8cd3184e06e6c7", "24e48402ba5fbd775b475da219bfbced4c3db2bbc6d06e47a9c7aa248e11d2a5")):
            self.assertEqual(self.sha(host.build_prompt(context)), host_sha)
            self.assertEqual(self.sha(native.build_request(context, self.identity)), native_sha)
            old = {k: v for k, v in self.arguments.items() if k != "experience_case_refs"}
            parsed = host.parse_host_response(canonical(old).encode(), "delegated", context=context)
            self.assertEqual(parsed["arguments"], old)
            self.assertNotIn("experience_case_refs", self.native_parse(context, old))
            with self.assertRaises(ResearchError):
                host.parse_host_response(canonical(self.arguments).encode(), "delegated", context=context)
            with self.assertRaises(ResearchError):
                self.native_parse(context, self.arguments)

    def test_new_wire_allows_exact_active_case_or_optional_absence(self):
        prompt = host.build_prompt(self.context)
        self.assertIn("experience_case_refs", prompt["system"])
        self.assertNotIn("exactly choice, rationale", prompt["system"])
        schema = native.build_request(self.context, self.identity)["tools"][0]["function"]["parameters"]
        self.assertNotIn("experience_case_refs", schema["required"])
        self.assertEqual(schema["properties"]["experience_case_refs"]["items"]["enum"], [self.ref])
        for arguments in (self.arguments, {k: v for k, v in self.arguments.items() if k != "experience_case_refs"}):
            parsed = host.parse_host_response(canonical(arguments).encode(), "delegated", context=self.context)
            proposal = host.build_proposal(self.context, parsed["arguments"], "fixture")
            result = self.native_parse(self.context, arguments)
            self.assertEqual(proposal.get("experience_case_refs"), arguments.get("experience_case_refs"))
            self.assertEqual(result.get("experience_case_refs"), arguments.get("experience_case_refs"))
        wrapper = {"type": "result", "subtype": "success", "is_error": False, "result": canonical(self.arguments)}
        self.assertEqual(host.parse_host_response(canonical(wrapper).encode(), "claude_cli",
                                                 context=self.context)["arguments"], self.arguments)

    def test_bad_or_duplicate_refs_and_bad_capability_rejected(self):
        for refs in ([{**self.ref, "case_id": "unknown"}], [{**self.ref, "case_version": 3}],
                     [{**self.ref, "bundle_sha256": "c" * 64}], [self.ref, self.ref], [self.ref] * 5,
                     [{**self.ref, "extra": 1}], [{**self.ref, "case_version": True}]):
            args = {**self.arguments, "experience_case_refs": refs}
            with self.subTest(refs=refs), self.assertRaises(ResearchError):
                host.parse_host_response(canonical(args).encode(), "delegated", context=self.context)
            with self.subTest(native_refs=refs), self.assertRaises(ResearchError):
                self.native_parse(self.context, args)
        for context, capability in ((self.empty, {"experience_case_refs": "v1"}),
                                    (self.legacy_case, {"experience_case_refs": "v2"})):
            payload = {k: copy.deepcopy(v) for k, v in context.items() if k != "context_sha256"}
            payload["selection_capabilities"] = capability
            with self.assertRaises(ResearchError):
                seal_context(payload)

    def test_host_receive_and_report_verify_against_saved_context(self):
        raw = canonical(self.arguments).encode()
        record = {"directory": "requests/0001", "status": "prepared", "provider": "delegated",
                  "context": self.context, "prompt": host.build_prompt(self.context)}
        fake = host_model_selection.HostModelSelection.__new__(host_model_selection.HostModelSelection)
        with patch.object(fake, "_save"):
            saved = fake._receive({}, record, raw, "requests/0001/delegated.bin")
        self.assertEqual(saved["status"], "received")
        prefix = "requests/0001/"
        files = {prefix + "context.json": canonical(self.context).encode(),
                 prefix + "prompt.json": canonical(saved["prompt"]).encode(),
                 prefix + "delegated.bin": raw}
        host_model_report._verify(saved, files)
        saved["context"] = self.legacy_case
        files[prefix + "context.json"] = canonical(self.legacy_case).encode()
        with self.assertRaises(ResearchError):
            host_model_report._verify(saved, files)

    def test_default_parser_and_context_tampering_fail_closed(self):
        with self.assertRaises(ResearchError):
            host.parse_host_response(canonical(self.arguments).encode(), "delegated")
        bad = copy.deepcopy(self.context)
        bad["experience"]["cases"][0]["inclusion_status"] = "retired"
        with self.assertRaises(ResearchError):
            host.build_prompt(bad)
        with self.assertRaises(ResearchError):
            native.build_request(bad, self.identity)
        payload = {k: copy.deepcopy(v) for k, v in self.context.items() if k != "context_sha256"}
        payload["experience"]["cases"][0]["inclusion_status"] = "retired"
        with self.assertRaises(ResearchError):
            seal_context(payload)
        for raw in (b'{"choice":{},"choice":{}}', b'{"x":NaN}'):
            with self.assertRaises(ResearchError):
                host.parse_host_response(raw, "delegated", context=self.context)

    def test_native_receipt_and_context_are_bound_to_original_bytes(self):
        raw = canonical({"model": "qwen3:4b", "done": True, "message": {"role": "assistant",
            "tool_calls": [{"function": {"name": native.TOOL_NAME, "arguments": self.arguments}}]}}).encode()
        receipt = {"schema_version": "project-model-transport-receipt-v1", "identity": self.identity,
            "request_sha256": fingerprint(native.build_request(self.context, self.identity)),
            "response_sha256": hashlib.sha256(raw).hexdigest(), "execution": "fixture", "process": {}}
        self.assertEqual(native.parse_response(raw, self.context, receipt)["experience_case_refs"], [self.ref])
        with self.assertRaises(ResearchError):
            native.parse_response(raw + b" ", self.context, receipt)
        with self.assertRaises(ResearchError):
            native.parse_response(raw, self.legacy_case, receipt)


if __name__ == "__main__":
    unittest.main()
