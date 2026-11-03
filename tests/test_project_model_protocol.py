"""One native-output boundary check; no model, transport or research execution."""
import copy
import hashlib
import unittest

import test_project_selection as fixtures
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch import project_model_protocol as protocol
from autoresearch.local_ollama import PUBLISHER_MANIFEST_SHA256


class ProjectModelProtocolTests(unittest.TestCase):
    def test_host_binding_and_native_only_output_reject_authority_injection(self):
        context = fixtures.ProjectSelectionTests.context(self)
        identity = {"schema_version": "project-local-model-identity-v1", "transport": "owned-local-ollama",
                    "model": "qwen3:4b", "publisher_manifest_sha256": PUBLISHER_MANIFEST_SHA256,
                    "executable_sha256": "f" * 64, "cloud_disabled": True}
        arguments = {"choice": {"kind": "execute", "candidate_id": "source-1"},
                     "rationale": "Read the host candidate; scientific eligibility remains unconfirmed.",
                     "evidence_citation_ids": ["quote-1"]}
        response = {"model": "qwen3:4b", "done": True, "message": {"role": "assistant", "content": "",
                    "tool_calls": [{"function": {"name": protocol.TOOL_NAME, "arguments": arguments}}]}}

        def parse(value):
            raw = canonical(value).encode("utf-8")
            receipt = {"schema_version": "project-model-transport-receipt-v1", "identity": identity,
                       "request_sha256": fingerprint(protocol.build_request(context, identity)),
                       "response_sha256": hashlib.sha256(raw).hexdigest(), "execution": "fixture", "process": {"fixture": True}}
            return protocol.parse_response(raw, context, receipt)

        proposal = parse(response)
        self.assertEqual(proposal["context_sha256"], context["context_sha256"])
        self.assertEqual(proposal["provider"], {"kind": "external_model", "label": "qwen3:4b"})
        self.assertEqual(proposal["choice"], arguments["choice"])
        variants = []
        injected = copy.deepcopy(response)
        injected["message"]["tool_calls"][0]["function"]["arguments"]["parameters"] = {"path": "arbitrary.py"}
        variants.append(injected)
        missing = copy.deepcopy(response); missing["message"]["tool_calls"] = []
        missing["message"]["content"] = canonical(arguments); variants.append(missing)
        multiple = copy.deepcopy(response); multiple["message"]["tool_calls"] *= 2; variants.append(multiple)
        duplicate = copy.deepcopy(response)
        duplicate["message"]["tool_calls"][0]["function"]["arguments"] = '{"choice":{},"choice":{},"rationale":"x","evidence_citation_ids":[]}'
        variants.append(duplicate)
        for value in variants:
            with self.subTest(value=value):
                with self.assertRaises(ResearchError):
                    parse(value)


if __name__ == "__main__":
    unittest.main()
