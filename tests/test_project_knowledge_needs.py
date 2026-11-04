"""Bounded lookup checks over fixture source text; no models or external calls."""

import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import test_local_workbench as fixtures
from autoresearch import knowledge, project_knowledge, tabular_source
from autoresearch.contracts import canonical
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController


class ProjectKnowledgeNeedsTests(unittest.TestCase):
    def test_declared_schema_terms_reach_exact_fts_evidence_and_controller_context(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = LocalWorkbench(Path(temporary) / "workbench")
            body = fixtures.LocalWorkbenchTests.create_body(self)
            spec = json.loads(base64.b64decode(body["input"]["spec_base64"]))
            spec.update(numeric_columns=["Signal_Total"], target_column="Signal_Total",
                        group_columns=["Panel", "Coating"], key_columns=["Record_ID"])
            body["input"]["spec_base64"] = base64.b64encode(canonical(spec).encode("utf-8")).decode("ascii")
            body["input"]["csv_base64"] = base64.b64encode(b"Record_ID,Panel,Coating,Signal_Total\nr1,p1,c1,0\n").decode("ascii")
            manager.create(body)
            project, _ = manager.binding()
            original = b"Signal_Total uses Panel and Coating labels. Record_ID locates exported entries.\n"
            digest = hashlib.sha256(original).hexdigest()
            locator = {"kind": "text_lines", "value": "1"}
            extraction = tabular_source.extract_selection(original, locator)
            ref = project_knowledge.build(project.root, {"id": "action-fixture-excerpt", "receipt_snapshot_sha256": "d" * 64},
                {"result": {"selections": [{"id": "excerpt", "source": {"id": "fixture", "url": "urn:test:original-excerpt",
                    "asset_sha256": digest, "sha256": digest, "license_note": "Fixture original; access unverified"},
                    "locator": locator, "extraction": extraction}]}})
            # Seed a frozen extracted-text fixture index, without executing an action.
            with project._writer(), project._connect() as con:
                saved = project._project(con); saved["knowledge_refs"] = [ref]; saved["state_version"] += 1
                project._save(con, saved)
            state = project.status()
            generic = "missing invalid nonfinite group target_unit"
            self.assertEqual(project_knowledge.query(project.root, state, need=generic)["evidence"], [])
            need = project_knowledge.decision_needs(state)["interpretation"]
            self.assertTrue(need.startswith(generic))
            for name in ("Signal_Total", "Panel", "Coating", "Record_ID"):
                self.assertIn(name, need)
            hits = project_knowledge.query(project.root, state, need=need)["evidence"]
            self.assertEqual(len(hits), 1)
            context = ProjectController(project.root).selection_context()
            self.assertEqual(context["evidence"][0]["citation_id"], hits[0]["citation_id"])
            self.assertEqual(context["evidence"][0]["quote"], extraction["text"])
            self.assertEqual(context["evidence"][0]["source"]["sha256"], digest)
            self.assertEqual(project.status()["snapshot_ref"], state["snapshot_ref"])
            self.assertEqual((len(state["actions"]), len(state["evidence_actions"])), (0, 0))

            # Legal long names are skipped whole when they exceed either bound.
            for scope in ({"target_column": "A" * 256, "numeric_columns": ["B" * 256, "short_name"]},
                          {"numeric_columns": [" ".join("Term" + str(i) for i in range(30)),
                                               " ".join("Extra" + str(i) for i in range(30))], "group_columns": ["Panel"]}):
                variant = copy.deepcopy(state); variant["source_scope"] = scope
                bounded = project_knowledge.decision_needs(variant)["interpretation"]
                self.assertLessEqual(len(bounded), 512)
                self.assertLessEqual(len(set(knowledge.tokens(bounded))), 64)
                project_knowledge.query(project.root, variant, need=bounded)
            self.assertEqual(project_knowledge.decision_needs({"registration": {"method_id": "materials.saved-steel-audit"}})["interpretation"],
                             "validation MSE threshold external validation")
            self.assertEqual(project_knowledge.decision_needs({"registration": {"method_id": "software.source-integrity-check"}})["interpretation"],
                             "mutation file identity filesystem")
            self.assertEqual(project_knowledge.decision_needs({})["interpretation"], "CropRed NaN batch export mapping")

    def test_latest_source_question_reaches_saved_and_controller_context_without_reindexing(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = LocalWorkbench(Path(temporary) / "workbench")
            manager.create(fixtures.LocalWorkbenchTests.create_body(self))
            project, _ = manager.binding()
            project.step(request_id="quality")
            with project._writer(), project._connect() as con:
                saved = project._project(con)
                saved["next_decision"]["remaining_questions"] = ["Previous98?"]
                project._save(con, saved)
            question = "Does Factor47 occur?"
            original = canonical({"padding": "padding " * 350, "ref": "C19", "field": "Factor", "value": 47})
            raw, locator = original.encode("utf-8"), {"kind": "text_lines", "value": "1"}
            self.assertGreater(original.index('"ref":"C19"'), 1400)
            digest = hashlib.sha256(raw).hexdigest()
            bundle = Path(temporary) / "bundle"
            (bundle / "sources").mkdir(parents=True)
            (bundle / "sources/current.txt").write_bytes(raw)
            manifest = {"schema_version": "project-evidence-bundle-v1", "task_ref": project.evidence_task()["task_ref"],
                "contributor": {"role": "operator_assistant", "label": "Current-question fixture"},
                "sources": [{"id": "original", "path": "sources/current.txt", "sha256": digest,
                    "url": "urn:test:separate-field-value", "media_type": "text/plain", "license_note": "Fixture only"}],
                "selections": [{"id": "current-question", "source_id": "original", "locator": locator,
                    "claim": "Unreviewed saved field/value pair"}], "remaining_questions": [question]}
            (bundle / "manifest.json").write_text(canonical(manifest), encoding="utf-8")
            registered = project.register_evidence(request_id="register-current", bundle=bundle)
            action = project.read_evidence(request_id="read-current", receipt_snapshot_sha256=registered["receipt_snapshot_sha256"])
            self.assertEqual(action["status"], "completed")
            state = project.status()
            need = project_knowledge.decision_needs(state)["interpretation"]
            self.assertEqual(need, question + " Factor 47")
            self.assertEqual(project_knowledge.query(project.root, state, need=question)["evidence"], [])
            completion = next(item for item in state["next_decision"]["knowledge_contexts"]
                              if item["decision_point"] == "interpretation")
            self.assertEqual(completion["need"], need)
            hit = next(item for item in completion["evidence"] if '"ref":"C19"' in item["quote"])
            self.assertIn(hit["quote"], original)
            self.assertIn('"ref":"C19"', hit["quote"])
            self.assertIn('"value":47', hit["quote"])
            self.assertEqual(hit["source"]["sha256"], digest)
            self.assertEqual(hit["source"]["metadata"]["locator"], locator)
            self.assertEqual(hit["location"], {"line_start": 1, "line_end": 1})
            frozen_files = {str(path): path.read_bytes() for path in (project.root / "knowledge").rglob("*") if path.is_file()}
            context = ProjectController(project.root).selection_context()
            selected = next(item for item in context["evidence"] if item["citation_id"] == hit["citation_id"])
            self.assertEqual(selected["quote"], hit["quote"])
            self.assertEqual(project.status(), state)
            self.assertEqual({str(path): path.read_bytes() for path in (project.root / "knowledge").rglob("*") if path.is_file()}, frozen_files)

            # Skip an unusable question whole; preserve a bounded literal when aliases cannot fit.
            fallback_state = copy.deepcopy(state); fallback_state["next_decision"]["remaining_questions"] = []
            fallback = project_knowledge.decision_needs(fallback_state)
            for questions, expected in ((["", "?", "x" * 513, " ".join("item" + str(i) for i in range(65)), question], need),
                                        (["x" * 504 + "Factor47"], "x" * 504 + "Factor47"),
                                        (["x" * 513], fallback["interpretation"]),
                                        (["Factor47 Factor47"], "Factor47 Factor47 Factor 47")):
                variant = copy.deepcopy(state); variant["next_decision"]["remaining_questions"] = questions
                needs = project_knowledge.decision_needs(variant)
                self.assertEqual(needs["interpretation"], expected)
                self.assertLessEqual(len(expected), 512)
                self.assertLessEqual(len(set(knowledge.tokens(expected))), 64)
                for point in ("clarification", "design", "preparation"):
                    self.assertEqual(needs[point], fallback[point])


if __name__ == "__main__":
    unittest.main()
