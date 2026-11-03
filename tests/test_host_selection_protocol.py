"""Two pure protocol checks; no CLI, model, project execution or external files."""
import copy
import unittest

import test_project_selection as fixtures
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_selection_protocol import build_prompt, build_proposal, parse_host_response
from autoresearch.project_selection import validate_proposal


class HostSelectionProtocolTests(unittest.TestCase):
    def test_a25_style_cli_envelope_and_delegated_selection_bind_original_context(self):
        context = fixtures.ProjectSelectionTests.context(self)
        original = copy.deepcopy(context)
        arguments = {"choice": {"kind": "execute", "candidate_id": "source-1"},
                     "rationale": "Read the declared source before revising the interpretation.",
                     "evidence_citation_ids": ["quote-1"]}
        wrapper = {"type": "result", "subtype": "success", "is_error": False,
                   "result": canonical(arguments), "duration_ms": 5516, "num_turns": 1,
                   "modelUsage": {"deepseek-flash": {"costUSD": 0.034155}},
                   "usage": {"input_tokens": 2081, "output_tokens": 474}, "total_cost_usd": 0.034155}
        prompt = build_prompt(context)
        self.assertEqual(prompt["prompt"].split("\n", 1)[1], canonical(context))
        self.assertIn("untrusted data", prompt["system"])
        for provider, value in (("claude_cli", wrapper), ("delegated", arguments)):
            with self.subTest(provider=provider):
                parsed = parse_host_response(canonical(value).encode("utf-8"), provider)
                self.assertEqual(parsed["arguments"], arguments)
                self.assertEqual(parsed["reported_models"], ["deepseek-flash"] if provider == "claude_cli" else [])
                self.assertEqual(parsed["reported_usage"], wrapper["usage"] if provider == "claude_cli" else None)
                self.assertEqual(parsed["reported_cost_usd"], 0.034155 if provider == "claude_cli" else None)
                proposal = build_proposal(context, parsed["arguments"], provider)
                self.assertEqual(validate_proposal(context, proposal)["candidate"], context["candidates"][0])
                self.assertEqual(proposal["provider"], {"kind": "external_model", "label": provider})
        waiting = {**arguments, "choice": {"kind": "wait"}}
        self.assertIsNone(validate_proposal(context, build_proposal(context, waiting, "delegated"))["candidate"])
        self.assertEqual(context, original)

    def test_invalid_authority_json_cli_result_and_context_are_rejected(self):
        context = fixtures.ProjectSelectionTests.context(self)
        arguments = {"choice": {"kind": "execute", "candidate_id": "source-1"},
                     "rationale": "Keep unresolved source needs.", "evidence_citation_ids": []}
        bad_choice = copy.deepcopy(arguments); bad_choice["choice"]["parameters"] = {"command": "arbitrary"}
        for value in (bad_choice, {**arguments, "scientific_validation": True}):
            with self.subTest(value=value), self.assertRaises(ResearchError):
                parse_host_response(canonical(value).encode(), "delegated")
        for raw in (b'{"choice":{},"choice":{}}', b'{"value":NaN}', b'{"value":1e999}',
                    b'```json\n{}\n```', b'*** Begin Patch', b' ' * (2 * 1024 * 1024 + 1)):
            with self.subTest(raw=raw[:40]), self.assertRaises(ResearchError):
                parse_host_response(raw, "delegated")
        wrapper = {"type": "result", "subtype": "success", "is_error": False, "result": canonical(arguments)}
        for changes in ({"subtype": "error_max_turns"}, {"is_error": True}, {"result": arguments},
                        {"result": '{"choice":{},"choice":{}}'}):
            with self.subTest(changes=changes), self.assertRaises(ResearchError):
                parse_host_response(canonical({**wrapper, **changes}).encode(), "claude_cli")
        with self.assertRaises(ResearchError):
            build_proposal(context, {**arguments, "evidence_citation_ids": ["invented"]}, "delegated")
        broken = copy.deepcopy(context); broken["goal"] = "Changed after sealing"
        for call in (lambda: build_prompt(broken), lambda: build_proposal(broken, arguments, "delegated")):
            with self.assertRaises(ResearchError):
                call()


if __name__ == "__main__":
    unittest.main()
