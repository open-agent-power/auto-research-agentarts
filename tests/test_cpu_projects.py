"""Native CPU lifecycle engineering fixtures; never full public study workloads."""
from contextlib import ExitStack
import hashlib
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import test_retrieval_adapter as retrieval_fixture
import test_scheduling_adapter as scheduling_fixture
from autoresearch import method_registry as registry
from autoresearch import retrieval_adapter, retrieval_lexical, scheduling_adapter, scheduling_kernel
from autoresearch.contracts import ResearchError, canonical
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject, code_identity


class NativeCPUProjectTests(unittest.TestCase):
    def fixture(self, module, allowance=2):
        fixture_type = (retrieval_fixture.RetrievalAdapterTests if module is retrieval_adapter
                        else scheduling_fixture.SchedulingAdapterTests)
        helper = fixture_type()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name)
        inputs = base / "inputs"
        inputs.mkdir()
        source = inputs / "source.json"
        source.write_text(canonical(helper.captured()), encoding="utf-8")
        project = ResearchProject(base / "project")
        project.create(source=source, goal="Synthetic native lifecycle verification; not a study result",
                       budget_ref="engineering-native-cpu", max_tool_calls=allowance, method_id=module.TOOL_ID)
        project.limit_evidence_budget(request_id="source-cap", expected_limit=8, new_limit=0,
            expected_state_version=project.status()["state_version"], reason="No source extraction in this engineering fixture")
        return base, project

    def advance(self, manager, project, request_id, method=None):
        context = ProjectController(project.root).selection_context()
        if method is None:
            choice = {"kind": "wait"}
        else:
            eligible = [c for c in context["candidates"] if c["method_id"] == method]
            self.assertEqual(len(eligible), 1, context["blockers"])
            choice = {"kind": "execute", "candidate_id": eligible[0]["id"]}
            self.assertEqual(eligible[0]["evaluation_ref"], registry.evaluation_ref(method))
        body = {"request_id": request_id, "project_id": project.status()["id"],
                "expected_state_version": context["state_version"], "proposal": {
                    "schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                    "provider": {"kind": "operator_assistant", "label": "Engineering fixture; no model send"},
                    "choice": choice, "rationale": "Verify the exact native bounded candidate and original request lifecycle",
                    "evidence_citation_ids": []}}
        return manager.advance(body), body

    def test_both_domains_use_native_import_plan_controller_audit_export_and_replay(self):
        for module in (retrieval_adapter, scheduling_adapter):
            with self.subTest(method=module.TOOL_ID), ExitStack() as stack:
                stack.enter_context(patch("sklearn.linear_model.Ridge.fit", side_effect=AssertionError("No fitting")))
                stack.enter_context(patch("sklearn.preprocessing.StandardScaler.fit", side_effect=AssertionError("No fitting")))
                base, project = self.fixture(module)
                project_id = project.status()["id"]
                manager = LocalWorkbench(base / "manager")
                imported = manager.import_project(request_id="import", workspace=project.root)
                self.assertEqual(imported["project_id"], project_id)
                self.assertFalse(project.root.exists())
                manager.select({"request_id": "activate", "project_id": project_id})
                project, _ = manager.binding()
                plan = {"question": "What does this fixed pair show?", "basis": "Explicit synthetic input; no scientific validity claim",
                        "steps": "Compute fixed pair, then audit saved evidence", "expected_feedback": "Keep adverse results and complete identities"}
                manager.save_plan({"request_id": "plan1", "project_id": project_id,
                    "expected_state_version": project.status()["state_version"], "plan": plan, "reason": "Before fixture execution"})
                self.advance(manager, project, "primary", module.TOOL_ID)
                state = project.status()
                parent = state["actions"][0]
                self.assertEqual(parent["command"], module.TOOL_ID)
                manager.save_plan({"request_id": "plan2", "project_id": project_id,
                    "expected_state_version": state["state_version"], "plan": {**plan, "basis": "Actual parent " + parent["id"] + " sha256:" + parent["result_sha256"]},
                    "reason": "Revise from actual saved pair"})
                with patch.object(module, "execute", side_effect=AssertionError("No primary replay")), \
                     patch.object(retrieval_lexical, "build_index", side_effect=AssertionError("No index")), \
                     patch.object(retrieval_lexical, "retrieve", side_effect=AssertionError("No reranking")), \
                     patch.object(retrieval_lexical, "metrics", side_effect=AssertionError("No gold rescoring")), \
                     patch.object(scheduling_kernel, "schedule", side_effect=AssertionError("No resolving")):
                    _, audit_body = self.advance(manager, project, "audit", module.AUDIT_TOOL_ID)
                    saved = manager.advance(audit_body)
                    self.assertTrue(saved.get("replayed"))
                state = project.status()
                self.assertEqual([a["command"] for a in state["actions"]], [module.TOOL_ID, module.AUDIT_TOOL_ID])
                self.assertEqual(state["budget"]["local_tool_calls_used"], 2)
                self.assertEqual(state["budget"]["fit_attempts_used"], 0)
                self.assertEqual(state["budget"]["evidence_reads_used"], 0)
                self.assertEqual(state["budget"]["new_model_requests"], 0)
                self.advance(manager, project, "wait")
                result = manager.export({"request_id": "report", "project_id": project_id,
                    "expected_state_version": project.status()["state_version"]})
                self.assertEqual(set(result["manifest"]["files"]), {"input.json", "report.json", "report.md", "report.pdf"})
                report = json.loads(next((manager.root / "reports").glob("*/report.json")).read_bytes())
                self.assertEqual(report["kind"], "retrieval" if module is retrieval_adapter else "scheduling")
                self.assertIn("cpu_sections", report)
                self.assertEqual(len(report["project"]["plan_revisions"]), 2)

    def test_saved_audit_rejects_a_different_projects_predecessor(self):
        for module in (retrieval_adapter, scheduling_adapter):
            with self.subTest(method=module.TOOL_ID):
                _, a = self.fixture(module)
                _, b = self.fixture(module)
                original = a.step(request_id="primary")
                b.step(request_id="primary")
                with self.assertRaises(ResearchError):
                    b.step(request_id="foreign-audit", method_id=module.AUDIT_TOOL_ID,
                           parameters={"based_on_action_id": original["id"], "based_on_result_sha256": original["result_sha256"]})
                self.assertEqual(len(b.status()["actions"]), 1)

    def test_tool_cap_blocks_new_audit_but_completed_primary_can_be_replayed(self):
        _, project = self.fixture(retrieval_adapter, allowance=1)
        parent = project.step(request_id="primary")
        with self.assertRaises(ResearchError) as error:
            project.step(request_id="audit", method_id=retrieval_adapter.AUDIT_TOOL_ID,
                         parameters={"based_on_action_id": parent["id"], "based_on_result_sha256": parent["result_sha256"]})
        self.assertEqual(error.exception.code, "BUDGET_EXHAUSTED")
        with patch.object(retrieval_adapter, "execute", side_effect=AssertionError("No new compute")):
            self.assertTrue(project.step(request_id="primary", expected_state_version=0)["replayed"])
        self.assertEqual(project.status()["budget"]["local_tool_calls_used"], 1)

    def test_complete_artifact_recovers_without_recomputing_the_primary(self):
        for module in (retrieval_adapter, scheduling_adapter):
            with self.subTest(method=module.TOOL_ID):
                _, project = self.fixture(module)
                with patch.object(project, "_commit_result", side_effect=RuntimeError("interrupt after complete artifact")):
                    with self.assertRaises(RuntimeError):
                        project.step(request_id="original")
                with patch.object(module, "execute", side_effect=AssertionError("Do not rerun")):
                    restored = project.step(request_id="original", expected_state_version=0)
                self.assertTrue(restored["recovered"])
                self.assertEqual(project.status()["budget"]["local_tool_calls_used"], 1)

    def test_unknown_without_artifact_keeps_its_original_slot(self):
        _, project = self.fixture(retrieval_adapter)
        with patch.object(retrieval_adapter, "execute", side_effect=KeyboardInterrupt("simulated lost execution")):
            with self.assertRaises(KeyboardInterrupt):
                project.step(request_id="original")
        with patch.object(retrieval_adapter, "execute", side_effect=AssertionError("Do not resend")):
            unknown = project.step(request_id="original")
            self.assertEqual(unknown["status"], "unknown")
            self.assertFalse(unknown["automatic_retry"])
            with self.assertRaises(ResearchError) as error:
                project.step(request_id="replacement")
            self.assertEqual(error.exception.code, "EXECUTION_UNKNOWN")
        budget = project.status()["budget"]
        self.assertEqual((budget["local_tool_calls_used"], budget["local_tool_calls_reserved"]), (0, 1))
        self.assertEqual(budget["local_tool_dispatches"], 1)

    def test_numerical_dependency_change_blocks_new_execution_without_mutating_budget(self):
        _, project = self.fixture(retrieval_adapter)
        state = project.status()
        runtime = registry.runtime_dependencies()
        self.assertEqual(state["runtime_dependencies"], runtime)
        with patch.object(registry, "runtime_dependencies", return_value={**runtime, "scikit-learn": "different-reviewed-runtime"}), \
             patch.object(retrieval_adapter, "execute", side_effect=AssertionError("Runtime mismatch cannot compute")):
            self.assertNotEqual(state["code_identity"], code_identity())
            self.assertIn("CODE_CHANGED", [b["code"] for b in ProjectController(project.root).selection_context()["blockers"]])
            with self.assertRaises(ResearchError) as error:
                project.step(request_id="not-compatible")
            self.assertEqual(error.exception.code, "CODE_CHANGED")
        self.assertEqual(project.status()["budget"], state["budget"])

    def test_upgrade_cannot_restamp_a_changed_or_unregistered_runtime(self):
        for unknown in (False, True):
            with self.subTest(unknown=unknown):
                _, project = self.fixture(retrieval_adapter)
                if unknown:
                    with project._connect() as con:
                        state = project._project(con)
                        state.pop("runtime_dependencies")
                        project._save(con, state)
                state = project.status()
                before = {str(p.relative_to(project.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in project.root.rglob("*") if p.is_file()}
                changed = {**registry.runtime_dependencies(), "scikit-learn": "changed"}
                with patch.object(registry, "runtime_dependencies", return_value=changed):
                    with self.assertRaises(ResearchError) as error:
                        project.upgrade(request_id="unsafe-upgrade", expected_code_identity=state["code_identity"], evidence_read_limit=0)
                    self.assertEqual(error.exception.code, "RUNTIME_CHANGED")
                after = {str(p.relative_to(project.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in project.root.rglob("*") if p.is_file()}
                self.assertEqual(before, after)
                self.assertEqual(project.status(), state)

    def test_same_runtime_upgrade_preserves_usage_and_old_receipt_replays_after_runtime_drift(self):
        _, project = self.fixture(retrieval_adapter)
        project.step(request_id="primary")
        before = project.status()
        revision = project.upgrade(request_id="compatible", expected_code_identity=before["code_identity"], evidence_read_limit=0)
        state = project.status()
        self.assertEqual(state["budget"], before["budget"])
        self.assertEqual(state["runtime_dependencies"], before["runtime_dependencies"])
        changed = {**registry.runtime_dependencies(), "scikit-learn": "changed"}
        with patch.object(registry, "runtime_dependencies", return_value=changed):
            self.assertEqual(project.upgrade(request_id="compatible", expected_code_identity=before["code_identity"], evidence_read_limit=0), revision)
        self.assertEqual(project.status(), state)

    def test_loaded_and_installed_dependency_versions_must_agree(self):
        real = registry.package_version
        with patch.object(registry, "package_version", side_effect=lambda name: "changed" if name == "scikit-learn" else real(name)):
            with self.assertRaises(ResearchError) as error:
                registry.runtime_dependencies()
            self.assertEqual(error.exception.code, "RUNTIME_CHANGED")


if __name__ == "__main__":
    unittest.main()
