"""Project OOF cases retain checked arithmetic, origin scope and revocable source inclusion."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

import test_group_only_design as fixtures
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.project_experience import ProjectExperienceMemory, derive_project_observation, parse_bundle, summary, validate_bundle
from autoresearch.research_memory import observation_id


class ProjectExperienceTests(unittest.TestCase):
    resource = fixtures.GroupOnlyDesignTests.resource
    make_project = fixtures.GroupOnlyDesignTests.project

    def setUp(self):
        self.project, self.controller = self.make_project(groups=3, fit_limit=6)
        self.controller.advance(request_id="source-group")
        self.action = self.project.status()["actions"][-1]
        self.memory = ProjectExperienceMemory(self.project.root.parent / "memory")
        self.derived = derive_project_observation(self.project.root, self.action["id"])
        self.scope, self.entry = self.derived["scope"], self.derived["entries"][0]

    def card(self):
        return {"schema_version": "research-method-card-v1", "id": "checked-group-case", "version": 1,
            "question": "What does this saved group validation show within its original fixture?",
            "rationale": "A retained numerical example, not a transferable performance claim.",
            "scope_match": {"domain": "data", "contract": "tabular-quality-v1"},
            "method_refs": [{"method_id": self.action["command"], "evaluation_ref": self.action["evaluation_ref"]}],
            "applicability": {"requires": ["Check this project's own groups and target unit."],
                              "not_applicable": ["Do not transfer the original MAE to another dataset."],
                              "uncertain": ["Independent target-population validity remains unreviewed."]},
            "evaluation": "Read the original complete-case OOF metrics and scope.",
            "feedback_branches": [{"id": "adverse", "observed": "An aggregate advantage may coexist with local failures.",
                "suggested_next": "Inspect saved prediction ranges without retuning.",
                "evidence_required": ["Current project's actual saved results and source meaning."]}],
            "sources": [{"id": "origin", "url": "urn:test:project-experience", "locator": self.action["id"],
                         "note": "Constructed 12-row fixture; not human or scientific validation."}]}

    def bundle(self):
        self.memory.import_project(self.project.root, self.action["id"])
        return self.memory.export_case(self.scope, self.entry["id"], case_id="fixture-case", version=1,
            method_card=self.card(), limitations=["A constructed source case, not current-project evidence."])

    @staticmethod
    def files(root):
        return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def expect_code(self, code, callback, *args, **kwargs):
        with self.assertRaises(ResearchError) as caught:
            callback(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_import_recomputes_without_refitting_or_source_mutation_and_exact_scope_remains_exact(self):
        before, files = self.project.status(), self.files(self.project.root)
        with patch.object(Ridge, "fit", side_effect=AssertionError("No experience refit")), \
                patch.object(StandardScaler, "fit", side_effect=AssertionError("No experience refit")):
            result = self.memory.import_project(self.project.root, self.action["id"])
            same = self.memory.import_project(self.project.root, self.action["id"])
        self.assertEqual((result["inserted"], same["inserted"]), (1, 0))
        self.assertEqual(self.project.status(), before)
        self.assertEqual(self.files(self.project.root), files)
        self.assertEqual(self.scope["inputs_sha256"], self.action["result_sha256"])
        self.assertEqual(self.scope["analysis_code_sha256"], hashlib.sha256(
            (Path(__file__).parents[1] / "src/autoresearch/project_experience.py").read_bytes()).hexdigest())
        retained, = self.memory.recall(self.scope)["entries"]
        self.assertEqual(retained["record"], self.entry)
        altered = {**self.scope, "inputs_sha256": "f" * 64}
        self.assertEqual(self.memory.recall(altered)["entries"], [])
        numerical = self.entry["payload"]["numerical_summary"]
        self.assertEqual((numerical["n"], numerical["input_n"], numerical["excluded"]), (12, 12, 0))
        self.assertTrue(self.entry["numerical_recomputation"])

    def test_later_project_revision_adds_source_version_without_rewriting_observation(self):
        self.memory.import_project(self.project.root, self.action["id"])
        self.project.save_plan(request_id="later-plan", expected_state_version=self.project.status()["state_version"],
            plan={"question": "Review the saved result", "basis": "The prior OOF fixture", "steps": "Stop fitting and review.",
                  "expected_feedback": "No new fits."}, reason="New project text must not rewrite the old numerical case.")
        result = self.memory.import_project(self.project.root, self.action["id"])
        self.assertEqual(result["inserted"], 0)
        retained, = self.memory.recall(self.scope)["entries"]
        self.assertEqual(retained["record"], self.entry)
        self.assertEqual(len(retained["source_versions"]), 2)
        self.assertEqual({source["origin"]["producer_code_identity"] for source in retained["source_versions"]}, {self.action["code_identity"]})

    def test_retired_source_cannot_export_and_reimport_never_reactivates(self):
        snapshot = self.bundle()
        self.memory.set_status(self.entry["id"], "retired", "Review source suitability", "retire-case")
        self.memory.import_project(self.project.root, self.action["id"])
        self.assertEqual(self.memory.recall(self.scope)["entries"], [])
        self.expect_code("EXPERIENCE_RETIRED", self.memory.export_case, self.scope, self.entry["id"],
            case_id="later-case", version=1, method_card=self.card(), limitations=["No new active export."])
        # An earlier export is deliberately a frozen snapshot, not a revocation lease.
        self.assertEqual(validate_bundle(snapshot), snapshot)
        self.memory.set_status(self.entry["id"], "active", "Restore source inclusion only", "restore-case")
        replay = self.memory.set_status(self.entry["id"], "retired", "Review source suitability", "retire-case")
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["current_status"], "active")

    def test_offline_bundle_rechecks_arithmetic_and_compact_projection_omits_raw_rows(self):
        bundle = self.bundle()
        self.assertEqual(parse_bundle(canonical(bundle).encode("utf-8")), bundle)
        compact = summary(bundle)
        self.assertEqual(compact["transfer_scope"], "analogy_not_current_evidence")
        self.assertEqual(compact["origin_evidence"]["producer_code_identity"], self.action["code_identity"])
        self.assertEqual(compact["observation"]["numerical_summary"], self.entry["payload"]["numerical_summary"])
        def keys(value):
            if isinstance(value, dict):
                return set(value).union(*(keys(item) for item in value.values()))
            return set().union(*(keys(item) for item in value)) if isinstance(value, list) else set()
        self.assertTrue({"artifact", "oof", "folds"}.isdisjoint(keys(compact)))
        self.assertFalse(compact["scientific_validation"])

    def test_changed_payload_and_rehashed_false_summary_are_rejected(self):
        bundle = self.bundle()
        wrong = copy.deepcopy(bundle)
        wrong["record"]["payload"]["numerical_summary"]["candidate_mae"] += 1
        self.expect_code("EVIDENCE_CHANGED", validate_bundle, wrong)
        wrong = copy.deepcopy(bundle)
        record = wrong["record"]
        envelope = record["provenance"]["artifact"]
        envelope["tool_result"]["result"]["analysis"]["summary"]["candidate_mae"] += 1
        envelope["sha256"] = fingerprint({key: value for key, value in envelope.items() if key != "sha256"})
        record["provenance"]["action"]["result_sha256"] = envelope["sha256"]
        record["scope"]["inputs_sha256"] = envelope["sha256"]
        record["provenance"]["recomputation_scope"] = copy.deepcopy(record["scope"])
        record["id"] = observation_id(record)
        self.expect_code("EVIDENCE_CHANGED", validate_bundle, wrong)

    def test_source_artifact_mutation_is_rejected_without_changing_memory(self):
        self.memory.import_project(self.project.root, self.action["id"])
        before = self.files(self.memory.root)
        path = self.project._artifact(self.action)
        original = path.read_bytes()
        value = json.loads(original)
        value["tool_result"]["result"]["analysis"]["oof"][0]["predicted"] += 1
        path.write_text(canonical(value), encoding="utf-8")
        self.expect_code("EVIDENCE_CHANGED", self.memory.import_project, self.project.root, self.action["id"])
        self.assertEqual(self.files(self.memory.root), before)
        path.write_bytes(original)

    def test_scope_method_evaluation_and_limitations_must_match_the_source_case(self):
        bundle = self.bundle()
        for field in ("scope", "method", "evaluation", "limitations"):
            wrong = copy.deepcopy(bundle)
            if field == "scope":
                wrong["method_card"]["scope_match"]["domain"] = "software"
            elif field == "method":
                wrong["method_card"]["method_refs"][0]["method_id"] = "data.ridge-random-validation"
            elif field == "evaluation":
                wrong["method_card"]["method_refs"][0]["evaluation_ref"] = "another-version"
            else:
                wrong["limitations"] = []
            with self.subTest(field=field):
                self.expect_code("INVALID_PROJECT_EXPERIENCE", validate_bundle, wrong)
        self.expect_code("INVALID_SCOPE", self.memory.export_case, {**self.scope, "inputs_sha256": "e" * 64}, self.entry["id"],
            case_id="same-case", version=1, method_card=self.card(), limitations=["Origin scope only."])

    def test_saved_old_evaluation_reference_is_retained_without_equating_it_to_current_method(self):
        bundle = self.bundle()
        record = bundle["record"]
        record["provenance"]["action"]["evaluation_ref"] = "ridge-validation-group_cv-historical"
        record["payload"]["evaluation_ref"] = "ridge-validation-group_cv-historical"
        bundle["method_card"]["method_refs"][0]["evaluation_ref"] = "ridge-validation-group_cv-historical"
        self.assertEqual(validate_bundle(bundle), bundle)

    def test_bad_nested_source_structures_are_rejected_as_experience_errors(self):
        bundle = self.bundle()
        for field in ("artifact", "tool_result", "source_scope", "fold", "command"):
            wrong = copy.deepcopy(bundle)
            provenance = wrong["record"]["provenance"]
            if field == "artifact":
                provenance["artifact"] = []
            elif field == "source_scope":
                provenance["origin"]["source_scope"] = {}
            elif field == "command":
                provenance["action"]["command"] = []
            else:
                artifact = provenance["artifact"]
                if field == "tool_result":
                    artifact["tool_result"] = []
                else:
                    artifact["tool_result"]["result"]["analysis"]["folds"][0] = []
                artifact["sha256"] = fingerprint({key: value for key, value in artifact.items() if key != "sha256"})
                provenance["action"]["result_sha256"] = artifact["sha256"]
                wrong["record"]["scope"]["inputs_sha256"] = artifact["sha256"]
                provenance["recomputation_scope"] = copy.deepcopy(wrong["record"]["scope"])
                wrong["record"]["id"] = observation_id(wrong["record"])
            with self.subTest(field=field), self.assertRaises(ResearchError):
                validate_bundle(wrong)

    def test_cli_exports_an_identical_frozen_case(self):
        bundle = self.bundle()
        folder = self.project.root.parent
        for name, value in (("scope", self.scope), ("card", self.card()), ("limitations", {"limitations": bundle["limitations"]})):
            (folder / (name + ".json")).write_text(canonical(value), encoding="utf-8")
        product = Path(__file__).parents[1]
        argv = [str(product / ".venv/Scripts/python.exe"), "scripts/project_experience.py", "export", "--memory", str(self.memory.root),
                "--scope", str(folder / "scope.json"), "--entry-id", self.entry["id"], "--case-id", "fixture-case", "--version", "1",
                "--method-card", str(folder / "card.json"), "--limitations", str(folder / "limitations.json"), "--output", str(folder / "case.json")]
        result = subprocess.run(argv, cwd=product, capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout)["case_id"], "fixture-case")
        self.assertEqual(parse_bundle((folder / "case.json").read_bytes()), bundle)


if __name__ == "__main__":
    unittest.main()
