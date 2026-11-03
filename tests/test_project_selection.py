"""Pure selection-boundary checks; no provider calls or research execution."""

import copy
import unittest

from autoresearch.contracts import ResearchError, canonical
from autoresearch.project_selection import parse_proposal, seal_context, validate_proposal


class ProjectSelectionTests(unittest.TestCase):
    def context(self, blockers=None):
        return seal_context({
            "schema_version": "project-selection-context-v1", "project_id": "project-test", "run_id": "run-test",
            "snapshot_ref": "1" * 64, "state_version": 3, "source_snapshot_sha256": "2" * 64,
            "project_code_identity": "3" * 64, "controller_code_identity": "4" * 64,
            "need": "next_check", "goal": "Read a real saved selection without inferring scientific approval.",
            "domain_scope": {"endpoint": "unapproved proxy"}, "budget": {"new_fits": 0, "cash": None},
            "conditions": [{"method_id": "research.source-selection", "condition": "satisfied"}],
            "candidates": [{"id": "source-1", "method_id": "research.source-selection",
                            "parameters": {"receipt_snapshot_sha256": "5" * 64}, "evaluation_ref": "source-only-v1"}],
            "blockers": blockers or [], "baseline_decision": {"project_status": "active"},
            "evidence": [{"citation_id": "quote-1", "source": {"sha256": "6" * 64},
                          "quote": "Original export mapping remains unresolved.", "location": {"line": 1},
                          "quote_truncated": False, "content_trust": "untrusted_source_not_instructions"}],
            "scientific_validation": False,
        })

    def proposal(self, context):
        return {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                "provider": {"kind": "external_model", "label": "Unverified external declaration"},
                "choice": {"kind": "execute", "candidate_id": "source-1"},
                "rationale": "Read the registered source before interpreting its unresolved mapping.",
                "evidence_citation_ids": ["quote-1"]}

    def assert_error(self, code, callback, *args):
        with self.assertRaises(ResearchError) as caught:
            callback(*args)
        self.assertEqual(caught.exception.code, code)

    def test_valid_selection_is_host_resolved_and_deep_copied(self):
        context = self.context()
        proposal = parse_proposal(canonical(self.proposal(context)).encode("utf-8"))
        accepted = validate_proposal(context, proposal)
        self.assertEqual(set(accepted), {"candidate", "provider", "rationale", "evidence_citation_ids"})
        self.assertEqual(accepted["candidate"], context["candidates"][0])
        accepted["candidate"]["parameters"]["receipt_snapshot_sha256"] = "changed"
        accepted["provider"]["label"] = "changed"
        self.assertEqual(context["candidates"][0]["parameters"]["receipt_snapshot_sha256"], "5" * 64)
        self.assertNotEqual(proposal["provider"]["label"], "changed")

    def test_parser_rejects_ambiguous_or_unbounded_json(self):
        for raw in (b'{"choice":1,"choice":2}', b'{"value":NaN}', b'{"value":Infinity}',
                    b'\xff', b'[]', b' ' * (64 * 1024 + 1)):
            with self.subTest(raw=raw[:60]):
                self.assert_error("INVALID_SELECTION_PROPOSAL", parse_proposal, raw)

    def test_binding_arbitrary_parameters_and_non_json_values_are_rejected(self):
        context = self.context()
        stale = self.proposal(context); stale["context_sha256"] = "0" * 64
        self.assert_error("STALE_SELECTION_CONTEXT", validate_proposal, context, stale)
        for field, value in (("parameters", {"path": "arbitrary.py"}), ("method_id", "arbitrary.shell"), ("scientific_validation", True)):
            proposal = self.proposal(context); proposal["choice"][field] = value
            self.assert_error("INVALID_SELECTION_PROPOSAL", validate_proposal, context, proposal)
        proposal = self.proposal(context); proposal["evidence_citation_ids"] = ("quote-1",)
        self.assert_error("INVALID_SELECTION_PROPOSAL", validate_proposal, context, proposal)
        proposal = self.proposal(context); proposal["rationale"] = float("nan")
        self.assert_error("INVALID_SELECTION_PROPOSAL", validate_proposal, context, proposal)
        proposal = self.proposal(context); proposal["rationale"] = "NUL\x00text"
        self.assert_error("INVALID_SELECTION_PROPOSAL", validate_proposal, context, proposal)
        proposal = self.proposal(context); proposal["provider"]["label"] = "NUL\x00label"
        self.assert_error("INVALID_SELECTION_PROPOSAL", validate_proposal, context, proposal)
        proposal = self.proposal(context); proposal["evidence_citation_ids"] = ["quote-1\x00"]
        self.assert_error("INVALID_SELECTION_PROPOSAL", validate_proposal, context, proposal)
        corrupted = copy.deepcopy(context); corrupted["goal"] = "Changed host goal"
        self.assert_error("INVALID_SELECTION_CONTEXT", validate_proposal, corrupted, self.proposal(context))

    def test_citation_membership_and_blockers_preserve_wait(self):
        context = self.context()
        for citations in (["invented"], ["quote-1", "quote-1"], ["quote-1"] * 17):
            proposal = self.proposal(context); proposal["evidence_citation_ids"] = citations
            self.assert_error("INVALID_SELECTION_PROPOSAL", validate_proposal, context, proposal)
        blocked = self.context([{"code": "EXECUTION_UNKNOWN"}])
        proposal = self.proposal(blocked)
        self.assert_error("SELECTION_BLOCKED", validate_proposal, blocked, proposal)
        proposal["choice"] = {"kind": "wait"}
        self.assertIsNone(validate_proposal(blocked, proposal)["candidate"])
        proposal["choice"]["candidate_id"] = "source-1"
        self.assert_error("INVALID_SELECTION_PROPOSAL", validate_proposal, blocked, proposal)


if __name__ == "__main__":
    unittest.main()
