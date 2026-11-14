"""Selection case declarations bind to the saved context; no research executes."""
import copy
import unittest

from autoresearch.contracts import ResearchError, fingerprint
from autoresearch.project_controller import ProjectController
from autoresearch.project_selection import seal_context, validate_proposal
from autoresearch.project_selection_view import selection_view
import test_project_selection_view as view_fixtures


class ExperienceCaseReferenceTests(unittest.TestCase):
    def setUp(self):
        self.state = view_fixtures.ProjectSelectionViewTests().state()
        self.parent = self.state["controller_requests"][0]
        payload = {k: copy.deepcopy(v) for k, v in self.parent["selection_context"].items() if k != "context_sha256"}
        card = {"schema_version": "research-method-card-v1", "id": "card", "version": 1,
            "question": "What was observed?", "rationale": "Retain an adverse example.",
            "scope_match": {"domain": "other", "contract": "other"},
            "method_refs": [{"method_id": "example", "evaluation_ref": "example-v1"}],
            "applicability": {"requires": ["Check local evidence."], "not_applicable": [], "uncertain": []},
            "evaluation": "Use local evidence.",
            "feedback_branches": [{"id": "b", "observed": "Example.", "suggested_next": "Inspect.", "evidence_required": ["Evidence."]}],
            "sources": [{"id": "s", "url": "urn:test:case", "locator": "original", "note": "Fixture."}]}
        case = {"case_id": "historic", "case_version": 2, "bundle_sha256": "a" * 64,
            "inclusion_status": "active", "entry_id": "b" * 64, "origin_evidence": {}, "source_scope": {},
            "observation": {}, "transfer_scope": "analogy_not_current_evidence", "scientific_validation": False,
            "method_card": card, "association": {"status": "scope_mismatch", "matching_candidate_ids": [], "missing_information": []}}
        payload["experience"] = {"schema_version": "project-experience-context-v1", "cases": [case], "scientific_validation": False}
        self.context = seal_context(payload)
        self.ref = {"case_id": "historic", "case_version": 2, "bundle_sha256": "a" * 64}
        self.proposal = copy.deepcopy(self.parent["request"]["proposal"])
        self.proposal["context_sha256"] = self.context["context_sha256"]
        self.proposal["experience_case_refs"] = [copy.deepcopy(self.ref)]

    def save_fixture(self):
        controller = ProjectController.__new__(ProjectController)
        plan = controller._selected_plan({}, "next_check", self.proposal, context=self.context)
        self.parent["selection_context"] = copy.deepcopy(self.context)
        self.parent["request"]["proposal"] = copy.deepcopy(self.proposal)
        self.parent["request_sha256"] = fingerprint(self.parent["request"])
        self.parent["decision"] = copy.deepcopy(plan["decision"])
        self.parent["decision_sha256"] = fingerprint(self.parent["decision"])
        return plan

    def test_reference_is_separate_declaration_with_frozen_scope_mismatch(self):
        result = validate_proposal(self.context, self.proposal)
        self.assertEqual(result["experience_case_refs"], [self.ref])
        self.assertEqual(result["evidence_citation_ids"], ["cited"])
        plan = self.save_fixture()
        self.assertFalse(plan["executable"])
        view = selection_view(self.state)["records"][0]
        self.assertEqual(view["experience_case_refs"], [self.ref])
        self.assertEqual(view["experience_case_associations"][0]["association"]["status"], "scope_mismatch")
        self.assertEqual(view["experience_case_associations"][0]["transfer_scope"], "analogy_not_current_evidence")
        self.assertEqual(self.state["actions"], [])

    def test_old_shape_remains_unchanged_and_optional_empty_is_explicit(self):
        old = copy.deepcopy(self.proposal)
        del old["experience_case_refs"]
        self.assertNotIn("experience_case_refs", validate_proposal(self.context, old))
        old["experience_case_refs"] = []
        self.assertEqual(validate_proposal(self.context, old)["experience_case_refs"], [])
        self.assertNotIn("experience_case_refs", selection_view(self.state)["records"][0])

    def test_unknown_duplicate_bad_versions_and_extra_fields_rejected(self):
        for refs in ([{**self.ref, "case_id": "wrong"}], [{**self.ref, "case_version": 3}],
                     [{**self.ref, "case_version": True}], [{**self.ref, "bundle_sha256": "f" * 64}],
                     [{**self.ref, "extra": 1}], [self.ref, self.ref], [self.ref] * 5, None):
            with self.subTest(refs=refs), self.assertRaises(ResearchError):
                validate_proposal(self.context, {**self.proposal, "experience_case_refs": refs})

    def test_inactive_context_and_stale_context_rejected(self):
        payload = {k: copy.deepcopy(v) for k, v in self.context.items() if k != "context_sha256"}
        payload["experience"]["cases"][0]["inclusion_status"] = "retired"
        retired = seal_context(payload)
        with self.assertRaises(ResearchError):
            validate_proposal(retired, self.proposal)
        updated = {**self.proposal, "context_sha256": retired["context_sha256"]}
        with self.assertRaises(ResearchError):
            validate_proposal(retired, updated)

    def test_saved_decision_reference_tampering_rejected_even_if_rehashed(self):
        self.save_fixture()
        ref = self.parent["decision"]["selection_ref"]
        ref["experience_case_refs"][0]["bundle_sha256"] = "f" * 64
        self.parent["decision_sha256"] = fingerprint(self.parent["decision"])
        with self.assertRaises(ResearchError) as error:
            selection_view(self.state)
        self.assertEqual(error.exception.code, "EVIDENCE_CHANGED")

    def test_unreferenced_legacy_case_without_bundle_hash_does_not_break_projection(self):
        payload = {k: copy.deepcopy(v) for k, v in self.context.items() if k != "context_sha256"}
        legacy = copy.deepcopy(payload["experience"]["cases"][0])
        legacy["case_id"] = "legacy"
        del legacy["bundle_sha256"]
        payload["experience"]["cases"].append(legacy)
        for value in (None, ["not-a-hash"]):
            if value is not None:
                legacy["bundle_sha256"] = value
            self.context = seal_context(payload)
            self.proposal["context_sha256"] = self.context["context_sha256"]
            self.save_fixture()
            associations = selection_view(self.state)["records"][0]["experience_case_associations"]
            self.assertEqual([item["case_id"] for item in associations], ["historic"])


if __name__ == "__main__":
    unittest.main()
