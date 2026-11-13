"""Tiny native relevance lifecycle fixtures, distinct from real target research."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_relevance_retrieval_adapter as fixture
from autoresearch import method_registry as registry, relevance_retrieval_adapter as adapter
from autoresearch import retrieval_adapter as citation, retrieval_lexical as lexical
from autoresearch.contracts import ResearchError, canonical
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class RelevanceProjectTests(unittest.TestCase):
    def fixture(self):
        helper = fixture.RelevanceRetrievalAdapterTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        inputs = base / "inputs"
        inputs.mkdir()
        source = inputs / "source.json"
        source.write_text(canonical(helper.captured()))
        project = ResearchProject(base / "project")
        project.create(source=source, goal="Tiny engineering relevance lifecycle; no scientific result",
                       budget_ref="engineering-relevance-fixture", max_tool_calls=2, method_id=adapter.TOOL_ID)
        project.limit_evidence_budget(request_id="source-cap", expected_limit=8, new_limit=0,
                                     expected_state_version=project.status()["state_version"],
                                     reason="Engineering fixture forbids source extraction")
        return base, project

    def advance(self, manager, project, request_id, method=None):
        context = ProjectController(project.root).selection_context()
        self.assertFalse(any(row["method_id"] in (citation.TOOL_ID, citation.AUDIT_TOOL_ID)
                             for row in context["candidates"]))
        if method is None:
            choice = {"kind": "wait"}
        else:
            matches = [row for row in context["candidates"] if row["method_id"] == method]
            self.assertEqual(len(matches), 1, context["blockers"])
            self.assertEqual(matches[0]["evaluation_ref"], registry.evaluation_ref(method))
            choice = {"kind": "execute", "candidate_id": matches[0]["id"]}
        body = {"request_id": request_id, "project_id": project.status()["id"],
                "expected_state_version": context["state_version"], "proposal": {
                    "schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                    "provider": {"kind": "operator_assistant", "label": "Synthetic fixture; no model"},
                    "choice": choice, "rationale": "Exercise the exact registered relevance lifecycle",
                    "evidence_citation_ids": []}}
        return manager.advance(body), body

    def save_plan(self, manager, project, request_id, basis):
        return manager.save_plan({"request_id": request_id, "project_id": project.status()["id"],
            "expected_state_version": project.status()["state_version"], "reason": "Engineering lifecycle evidence",
            "plan": {"question": "What does the fixed relevance pair show?", "basis": basis,
                     "steps": "Fixed pair, saved audit, final wait; no parameter search",
                     "expected_feedback": "Original grades, missing positives, all adverse cases and exact identities"}})

    def test_native_import_three_plans_pair_audit_wait_report_and_exact_replays(self):
        with ExitStack() as guards:
            guards.enter_context(patch("sklearn.linear_model.Ridge.fit", side_effect=AssertionError("No fits")))
            guards.enter_context(patch("sklearn.preprocessing.StandardScaler.fit", side_effect=AssertionError("No fits")))
            base, project = self.fixture()
            project_id = project.status()["id"]
            manager = LocalWorkbench(base / "manager")
            imported = manager.import_project(request_id="import", workspace=project.root)
            self.assertEqual(imported["project_id"], project_id)
            self.assertFalse(project.root.exists())
            manager.select({"request_id": "activate", "project_id": project_id})
            project, _ = manager.binding()
            self.save_plan(manager, project, "plan1", "Synthetic fixture source, declared binary projection; no real target data")
            _, primary_body = self.advance(manager, project, "primary", adapter.TOOL_ID)
            primary = project.status()["actions"][0]
            primary_tool = json.loads(project._artifact(primary).read_bytes())["tool_result"]
            self.assertEqual(primary_tool["result"]["usage"]["ranking_calls"], 6)
            self.assertEqual(primary_tool["result"]["usage"]["scoring_calls"], 6)
            self.save_plan(manager, project, "plan2", "Actual primary " + primary["id"] + " sha256:" + primary["result_sha256"]
                           + "; adverse=" + str(len(primary_tool["result"]["adverse_queries"]))
                           + "; test BM25 Recall20=" + str(primary_tool["result"]["paired_summary"]["splits"]["test"]["arms"]["bm25"]["metrics"]["recall@20"]))
            with patch.object(adapter, "execute", side_effect=AssertionError("No primary replay")), \
                 patch.object(adapter, "retrieve", side_effect=AssertionError("No new relevance ranking")), \
                 patch.object(lexical, "build_index", side_effect=AssertionError("No new index")), \
                 patch.object(lexical, "retrieve", side_effect=AssertionError("No legacy ranking")), \
                 patch.object(lexical, "metrics", side_effect=AssertionError("No qrel rescoring")):
                self.assertTrue(manager.advance(primary_body).get("replayed"))
                _, audit_body = self.advance(manager, project, "audit", adapter.AUDIT_TOOL_ID)
                self.assertTrue(manager.advance(audit_body).get("replayed"))
                audit = project.status()["actions"][1]
                self.save_plan(manager, project, "plan3", "Actual saved audit " + audit["id"] + " sha256:" + audit["result_sha256"]
                               + "; preserve the missing-positive and no-hit failures, then wait")
                _, wait_body = self.advance(manager, project, "wait")
                self.assertTrue(manager.advance(wait_body).get("replayed"))
                exported = manager.export({"request_id": "report", "project_id": project_id,
                                           "expected_state_version": project.status()["state_version"]})
            state = project.status()
            self.assertEqual(state["research_status"], "waiting")
            self.assertEqual([row["command"] for row in state["actions"]], [adapter.TOOL_ID, adapter.AUDIT_TOOL_ID])
            self.assertEqual(len(state["plan_revisions"]), 3)
            budget = state["budget"]
            for key, value in {"local_tool_call_limit": 2, "local_tool_calls_used": 2, "local_tool_calls_reserved": 0,
                               "fit_limit": 0, "fit_attempts_used": 0, "new_fits": 0, "new_model_requests": 0,
                               "evidence_read_limit": 0, "evidence_reads_used": 0}.items():
                self.assertEqual(budget[key], value, key)
            self.assertEqual(set(exported["manifest"]["files"]), {"input.json", "report.json", "report.md", "report.pdf"})
            report = json.loads(next((manager.root / "reports").glob("*/report.json")).read_bytes())
            self.assertEqual(report["kind"], "relevance")
            self.assertIn("cpu_sections", report)
            self.assertEqual(len(report["project"]["plan_revisions"]), 3)

    def test_citation_primary_and_audit_cannot_enter_relevance_lineage(self):
        _, project = self.fixture()
        for method in (citation.TOOL_ID, citation.AUDIT_TOOL_ID):
            with self.assertRaises(ResearchError) as rejected:
                project.step(request_id="wrong-" + method.rsplit(".", 1)[-1], method_id=method,
                             parameters={"based_on_action_id": "foreign", "based_on_result_sha256": "f"*64})
            self.assertEqual(rejected.exception.code, "METHOD_NOT_SUPPORTED")
        state = project.status()
        self.assertEqual(state["actions"], [])
        self.assertEqual(state["budget"]["local_tool_calls_used"], 0)
        self.assertEqual(state["budget"]["local_tool_calls_reserved"], 0)


if __name__ == "__main__":
    unittest.main()
