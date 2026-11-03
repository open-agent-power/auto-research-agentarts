"""One real FTS/controller check over fixture source text; no research dispatch."""

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


if __name__ == "__main__":
    unittest.main()
