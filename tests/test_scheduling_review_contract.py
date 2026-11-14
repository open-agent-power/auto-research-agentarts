"""A fake review cannot authorize different inputs, runtime, code or a later phase."""
import copy
from contextlib import ExitStack
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from autoresearch import scheduling_kernel
from autoresearch.contracts import ResearchError


class SchedulingReviewContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).parents[1] / "scripts/run_scheduling_policy_transfer.py"
        spec = importlib.util.spec_from_file_location("scheduling_review_contract_runner", path)
        cls.runner = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.runner
        cls.addClassCleanup(sys.modules.pop, spec.name, None)
        with ExitStack() as guards:
            for name in ("jobs_for", "schedule", "brute_force"):
                guards.enter_context(patch.object(scheduling_kernel, name, side_effect=AssertionError("review import must not compute")))
            spec.loader.exec_module(cls.runner)

    def setUp(self):
        self.expected = {
            "protocol_sha256": "1" * 64, "code_commit": "2" * 40,
            "output_root": "/workspace/auto-research-agentarts/runs/g5-scheduling-threshold-transfer-20261114-01",
            "budget_sha256": "3" * 64,
            "source_fingerprints": {name: "4" * 64 for name in (
                "src/autoresearch/contracts.py", "src/autoresearch/bounded_study_ledger.py",
                "src/autoresearch/scheduling_threshold_policy.py", "src/autoresearch/scheduling_kernel.py",
                "scripts/run_scheduling_policy_transfer.py", "scripts/verify_scheduling_policy_transfer.py",
                "docs/execution/g5-local/scheduling-threshold-transfer-protocol.json")},
            "runtime": {"python_version": "fake interpreter", "boot_id": "fake boot",
                        "dependencies": {"numpy": "fake version"}},
        }
        self.setup = {**copy.deepcopy(self.expected),
            "schema_version": "scheduling-policy-setup-review-v1", "status": "approved",
            "reviewer": "independent-fixture-reviewer", "study_id": "g5-scheduling-threshold-transfer-v1",
            "request_id": "prepare-g5-scheduling-threshold-transfer-v1", "allowed_phase": "generate_only",
            "limitations": ["Synthetic contract fixture; authorizes no production call."]}
        self.inputs_sha, self.claim_sha = "5" * 64, "6" * 64
        self.input_review = {**copy.deepcopy(self.setup), "schema_version": "scheduling-policy-input-review-v1",
            "request_id": "primary-g5-scheduling-threshold-transfer-v1",
            "allowed_phase": "primary_and_saved_audit", "inputs_sha256": self.inputs_sha,
            "shared_claim_sha256": self.claim_sha}

    def validate(self, review, stage="setup", **fields):
        return self.runner.validate_review(review, self.expected, stage, **fields)

    def assert_rejected(self, callback):
        with self.assertRaises((ResearchError, ValueError)):
            callback()

    def test_matching_setup_and_input_contracts_are_accepted_without_execution(self):
        self.validate(self.setup)
        self.validate(self.input_review, "input", inputs_sha256=self.inputs_sha,
                      shared_claim_sha256=self.claim_sha)

    def test_approval_is_bound_to_every_expected_field_including_nested_runtime(self):
        for field, changed in (("protocol_sha256", "9" * 64), ("code_commit", "9" * 40),
                               ("output_root", "/tmp/copied-study"), ("budget_sha256", "9" * 64),
                               ("source_fingerprints", {"other.py": "4" * 64}),
                               ("runtime", {"boot_id": "another boot"})):
            review = copy.deepcopy(self.setup)
            review[field] = changed
            with self.subTest(field=field):
                self.assert_rejected(lambda: self.validate(review))

    def test_setup_approval_cannot_authorize_primary_or_change_identity(self):
        self.assert_rejected(lambda: self.validate(self.setup, "input", inputs_sha256=self.inputs_sha,
                                                   shared_claim_sha256=self.claim_sha))
        for field, value in (("request_id", "another-request"), ("study_id", "another-study"),
                             ("allowed_phase", "primary_and_saved_audit"), ("status", "pending")):
            review = copy.deepcopy(self.setup)
            review[field] = value
            with self.subTest(field=field):
                self.assert_rejected(lambda: self.validate(review))

    def test_input_approval_requires_exact_completed_manifest_and_shared_claim(self):
        for input_sha, claim_sha in ((None, self.claim_sha), (self.inputs_sha, None),
                                    ("7" * 64, self.claim_sha), (self.inputs_sha, "7" * 64)):
            with self.subTest(input_sha=input_sha, claim_sha=claim_sha):
                self.assert_rejected(lambda: self.validate(self.input_review, "input",
                    inputs_sha256=input_sha, shared_claim_sha256=claim_sha))

    def test_missing_or_additional_fields_do_not_become_review_authority(self):
        for field in self.setup:
            review = copy.deepcopy(self.setup)
            del review[field]
            with self.subTest(missing=field):
                self.assert_rejected(lambda: self.validate(review))
        review = {**self.setup, "allow_budget_reset": True}
        self.assert_rejected(lambda: self.validate(review))

    def test_reviewer_and_limitations_must_be_explicit_and_well_typed(self):
        for field, value in (("reviewer", ""), ("reviewer", True), ("limitations", []),
                             ("limitations", "none"), ("limitations", [False])):
            review = copy.deepcopy(self.setup)
            review[field] = value
            with self.subTest(field=field, value=value):
                self.assert_rejected(lambda: self.validate(review))
        self.assert_rejected(lambda: self.validate(self.setup, "run"))


if __name__ == "__main__":
    unittest.main()
