"""Explicit method-case snapshots preserve project authority and local retirement."""

import base64
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_group_only_design as group_fixtures
import test_local_workbench as manager_fixtures
import test_local_workbench_http as http_fixtures
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_experience import ProjectExperienceMemory
from autoresearch.project_experience_binding import active_cases, case_assets, view_cases


class ProjectExperienceBindingTests(unittest.TestCase):
    serve = http_fixtures.LocalWorkbenchHTTPTests.serve
    request = http_fixtures.LocalWorkbenchHTTPTests.request
    session = http_fixtures.LocalWorkbenchHTTPTests.session

    @classmethod
    def setUpClass(cls):
        cls.source_fixture = group_fixtures.GroupOnlyDesignTests()
        cls.addClassCleanup(cls.source_fixture.doCleanups)
        source, controller = cls.source_fixture.project(fit_limit=4, groups=2)
        controller.advance(request_id="source-group-for-case")
        state = source.status()
        action = state["actions"][-1]
        memory = ProjectExperienceMemory(source.root.parent / "memory")
        imported = memory.import_project(source.root, action["id"])
        entry = memory.recall(imported["scope"])["entries"][0]["record"]
        card = {"schema_version": "research-method-card-v1", "id": "source-case-card", "version": 1,
                "question": "What did a fixed grouped Ridge check observe?", "rationale": "Constructed source study, not a transferable numeric result.",
                "scope_match": {key: state["source_scope"][key] for key in ("domain", "contract")},
                "method_refs": [{"method_id": action["command"], "evaluation_ref": action["evaluation_ref"]}],
                "applicability": {"requires": ["Verify the target task's own groups"], "not_applicable": ["Do not transfer source MAE"], "uncertain": ["Independent samples unknown"]},
                "evaluation": "Use target evidence, not these source values.",
                "feedback_branches": [{"id": "observe", "observed": "A saved check exists", "suggested_next": "Inspect local evidence", "evidence_required": ["Target group identities"]}],
                "sources": [{"id": "source", "url": "urn:test:source-case", "locator": action["id"], "note": "Constructed protocol fixture"}]}
        cls.bundle = memory.export_case(imported["scope"], entry["id"], case_id="source-case", version=1,
                                        method_card=card, limitations=["Not scientific validation or new target evidence."])

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())) / "manager"
        self.manager = LocalWorkbench(self.root)
        self.manager.create(manager_fixtures.LocalWorkbenchTests.create_body(self, "create-case-target"))
        self.project, _ = self.manager.binding()

    @staticmethod
    def tree_bytes(root):
        return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def raw(self, *, case_id="source-case", version=1):
        bundle = copy.deepcopy(self.bundle)
        bundle.update(id=case_id, version=version)
        return canonical(bundle).encode("utf-8")

    def body(self, request_id="import-case", *, case_id="source-case", version=1):
        return {"request_id": request_id, "project_id": self.project.status()["id"],
                "expected_state_version": self.project.status()["state_version"],
                "bundle_base64": base64.b64encode(self.raw(case_id=case_id, version=version)).decode("ascii"),
                "reason": "Explicitly include a historical method example, not target evidence."}

    def status_body(self, case_id="source-case", status="retired", request_id="retire-case"):
        return {"request_id": request_id, "project_id": self.project.status()["id"],
                "expected_state_version": self.project.status()["state_version"], "case_id": case_id,
                "status": status, "reason": "Explicit local inclusion decision."}

    def assert_code(self, code, callback, *args, **kwargs):
        with self.assertRaises(ResearchError) as caught:
            callback(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def request_count(self):
        with self.manager._connect(readonly=True) as con:
            return con.execute("SELECT count(*) FROM requests").fetchone()[0]

    def test_empty_views_do_not_create_a_host_or_mutate_the_project(self):
        before = self.tree_bytes(self.root)
        self.assertEqual(self.manager.experiences()["cases"], [])
        self.assertEqual(active_cases(self.project.root, self.project.status()), [])
        self.assertEqual(case_assets(self.project.root, self.project.status()), [])
        self.assertEqual(self.tree_bytes(self.root), before)
        self.assertFalse((self.project.root / "host-model-selections").exists())
        empty = LocalWorkbench(self.root.parent / "empty")
        self.assertEqual(empty.experiences()["project_id"], None)

    def test_import_preserves_budget_actions_plan_host_and_exact_original_bytes(self):
        before, host_before = self.project.status(), HostModelSelection(self.project.root).status()
        body = self.body()
        result = self.manager.import_experience(body)
        after = self.project.status()
        self.assertEqual(after["state_version"], before["state_version"] + 1)
        self.assertEqual(after["budget"], before["budget"])
        self.assertEqual(after["actions"], before["actions"])
        self.assertEqual(after["evidence_actions"], before["evidence_actions"])
        self.assertEqual(after.get("plan_revisions"), before.get("plan_revisions"))
        self.assertEqual(HostModelSelection(self.project.root).status(), host_before)
        revision = result["experience_revision"]
        self.assertEqual((self.project.root / revision["bundle_ref"]).read_bytes(), self.raw())
        view = self.manager.experiences()
        self.assertEqual(view["cases"][0]["inclusion_status"], "active")
        self.assertEqual(view["cases"][0]["transfer_scope"], "analogy_not_current_evidence")
        self.assertEqual(case_assets(self.project.root, after), [{"name": revision["bundle_ref"], "data": self.raw()}])
        self.assertFalse((self.project.root / "knowledge").exists())
        files = self.tree_bytes(self.root)
        self.assertTrue(self.manager.import_experience(body)["replayed"])
        self.assertEqual(self.tree_bytes(self.root), files)

    def test_retire_replay_reimport_and_restore_keep_one_explicit_current_status(self):
        imported = self.body()
        first = self.manager.import_experience(imported)
        retired = self.status_body()
        self.manager.set_experience_status(retired)
        after_retire = self.project.status()
        self.assertEqual(active_cases(self.project.root, after_retire), [])
        self.assertTrue(self.manager.import_experience(imported)["replayed"])
        self.assertEqual(self.project.status(), after_retire)
        self.assertEqual(first["experience_revision"], self.project.import_experience(
            request_id=imported["request_id"], expected_state_version=imported["expected_state_version"], bundle=self.raw(), reason=imported["reason"]))
        count = self.request_count()
        self.assert_code("EXPERIENCE_ALREADY_IMPORTED", self.manager.import_experience, self.body("duplicate-case"))
        self.assertEqual(self.request_count(), count)
        restore = self.status_body(status="active", request_id="restore-case")
        self.manager.set_experience_status(restore)
        after_restore = self.project.status()
        self.assertEqual(len(active_cases(self.project.root, after_restore)), 1)
        self.assertTrue(self.manager.set_experience_status(retired)["replayed"])
        self.assertEqual(self.project.status(), after_restore)
        self.assertEqual(len(case_assets(self.project.root, after_restore)), 1)

    def test_new_case_version_replaces_without_retired_fallback_or_old_replay_reactivation(self):
        first = self.body()
        self.manager.import_experience(first)
        retired = self.status_body()
        self.manager.set_experience_status(retired)
        self.manager.import_experience(self.body("import-case-v2", version=2))
        view = self.manager.experiences()
        self.assertEqual(len(view["cases"]), 1)
        self.assertEqual(view["cases"][0]["case_version"], 2)
        self.manager.set_experience_status(self.status_body(request_id="retire-case-v2"))
        after = self.project.status()
        self.assertEqual(active_cases(self.project.root, after), [])
        self.assertTrue(self.manager.import_experience(first)["replayed"])
        self.assertTrue(self.manager.set_experience_status(retired)["replayed"])
        self.assertEqual(self.project.status(), after)
        self.assertEqual(len(case_assets(self.project.root, after)), 2)
        self.assert_code("EXPERIENCE_ALREADY_IMPORTED", self.manager.import_experience, self.body("old-v1-again"))

    def test_four_active_limit_releases_on_retirement_and_blocks_restore_until_space(self):
        for name in ("a", "b", "c", "d"):
            self.manager.import_experience(self.body("import-" + name, case_id=name))
        count = self.request_count()
        self.assert_code("EXPERIENCE_LIMIT", self.manager.import_experience, self.body("import-e", case_id="e"))
        self.assertEqual(self.request_count(), count)
        self.manager.set_experience_status(self.status_body("a", request_id="retire-a"))
        self.manager.import_experience(self.body("import-e", case_id="e"))
        count = self.request_count()
        self.assert_code("EXPERIENCE_LIMIT", self.manager.set_experience_status, self.status_body("a", "active", "restore-a"))
        self.assertEqual(self.request_count(), count)
        self.manager.set_experience_status(self.status_body("b", request_id="retire-b"))
        self.manager.set_experience_status(self.status_body("a", "active", "restore-a"))
        self.assertEqual(len(active_cases(self.project.root, self.project.status())), 4)

    def test_known_rejections_leave_no_accepted_request_or_blocking_pending_state(self):
        count = self.request_count()
        self.assert_code("EXPERIENCE_NOT_FOUND", self.manager.set_experience_status, self.status_body("missing"))
        stale = self.body("stale-import"); stale["expected_state_version"] += 1
        self.assert_code("STALE_STATE", self.manager.import_experience, stale)
        self.assertEqual(self.request_count(), count)
        self.manager.import_experience(self.body())
        count = self.request_count()
        self.assert_code("EXPERIENCE_STATUS_UNCHANGED", self.manager.set_experience_status, self.status_body(status="active"))
        self.assertEqual(self.request_count(), count)
        self.assertEqual(self.manager.describe()["pending_requests"], [])
        self.manager.set_experience_status(self.status_body())

    def test_request_content_conflict_and_claimed_ids_are_rejected(self):
        body = self.body()
        self.manager.import_experience(body)
        changed = copy.deepcopy(body); changed["reason"] = "Different reason"
        self.assert_code("IDEMPOTENCY_CONFLICT", self.manager.import_experience, changed)
        self.project.save_plan(request_id="saved-plan", expected_state_version=self.project.status()["state_version"],
                               plan={"question": "Fixture", "basis": "", "steps": "Read", "expected_feedback": "Uncertainty"}, reason="Plan fixture")
        count = self.request_count()
        self.assert_code("IDEMPOTENCY_CONFLICT", self.manager.import_experience, self.body("saved-plan", case_id="other"))
        self.assertEqual(self.request_count(), count)

    def test_code_and_pending_host_conditions_reject_before_manager_acceptance(self):
        body = self.body()
        count = self.request_count()
        with patch("autoresearch.research_project.code_identity", return_value="f" * 64):
            self.assert_code("CODE_CHANGED", self.manager.import_experience, body)
        self.assertEqual(self.request_count(), count)
        host = HostModelSelection(self.project.root)
        host.prepare(request_id="pending-plan", provider="delegated", purpose="plan", expected_state_version=0,
                     decision_limit=1, cli_budget_usd=0.1, reason="Constructed no-launch pending fixture")
        self.assert_code("HOST_SELECTION_PENDING", self.manager.import_experience, body)
        self.assertEqual(self.request_count(), count)

    def test_changed_bundle_snapshot_is_rejected_by_view_asset_and_core_replay(self):
        body = self.body()
        revision = self.manager.import_experience(body)["experience_revision"]
        (self.project.root / revision["bundle_ref"]).write_bytes(b"changed original")
        for callback in (lambda: self.manager.experiences(), lambda: active_cases(self.project.root, self.project.status()),
                         lambda: case_assets(self.project.root, self.project.status()),
                         lambda: self.manager.import_experience(body),
                         lambda: self.manager.resume_experience({key: body[key] for key in ("request_id", "project_id")}),
                         lambda: self.project.import_experience(request_id=body["request_id"], expected_state_version=body["expected_state_version"], bundle=self.raw(), reason=body["reason"])):
            self.assert_code("EVIDENCE_CHANGED", callback)

    def test_core_committed_manager_receipt_loss_recovers_original_without_new_revision(self):
        body = self.body()
        with patch.object(self.manager, "_save", side_effect=RuntimeError("Lost receipt")):
            with self.assertRaisesRegex(RuntimeError, "Lost receipt"):
                self.manager.import_experience(body)
        after = self.project.status()
        self.assertEqual(len(after["experience_revisions"]), 1)
        self.assertEqual(self.manager.describe()["pending_requests"][0]["command"], "import_experience")
        self.assert_code("OPERATION_INCOMPLETE", self.manager.import_experience, self.body("do-not-bypass", case_id="another"))
        resume = {key: body[key] for key in ("request_id", "project_id")}
        recovered = LocalWorkbench(self.root).resume_experience(resume)
        self.assertTrue(recovered["replayed"])
        self.assertEqual(self.project.status(), after)
        self.assertEqual(self.manager.describe()["pending_requests"], [])
        self.assertTrue(self.manager.resume_experience(resume)["replayed"])

    def test_accepted_body_before_core_commit_resumes_without_reupload_or_new_id(self):
        from autoresearch.research_project import ResearchProject
        body, before = self.body(), self.project.status()
        with patch.object(ResearchProject, "import_experience", side_effect=RuntimeError("Stopped before core")):
            with self.assertRaisesRegex(RuntimeError, "Stopped before core"):
                self.manager.import_experience(body)
        self.assertEqual(self.project.status(), before)
        resume = {key: body[key] for key in ("request_id", "project_id")}
        result = LocalWorkbench(self.root).resume_experience(resume)
        self.assertEqual(result["status"], "completed")
        after = self.project.status()
        self.assertEqual(len(after["experience_revisions"]), 1)
        self.assertEqual(after["budget"], before["budget"])
        self.assertTrue(self.manager.resume_experience(resume)["replayed"])
        self.assertEqual(self.project.status(), after)
        self.assert_code("INVALID_REQUEST", self.manager.resume_experience, {**resume, "reason": "Cannot replace original"})

    def test_written_bundle_before_core_commit_reuses_exact_orphan_on_resume(self):
        from autoresearch.research_project import ResearchProject
        body, before = self.body(), self.project.status()
        with patch.object(ResearchProject, "_save", side_effect=RuntimeError("Stopped after snapshot write")):
            with self.assertRaisesRegex(RuntimeError, "Stopped after snapshot write"):
                self.manager.import_experience(body)
        self.assertEqual(self.project.status(), before)
        files = list((self.project.root / "experience").glob("*.json"))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].read_bytes(), self.raw())
        result = self.manager.resume_experience({key: body[key] for key in ("request_id", "project_id")})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(self.project.status()["experience_revisions"]), 1)
        self.assertEqual(list((self.project.root / "experience").glob("*.json")), files)
        self.assertEqual(self.project.status()["budget"], before["budget"])

    def test_http_original_import_and_status_replay_and_readonly_gates(self):
        server = self.serve(local_workspace=self.manager, allow_local_actions=True)
        headers = self.session(server)
        body = self.body()
        self.assertEqual(self.request(server, "/api/local-workbench/experience-import", "POST", body)[0], 403)
        status, imported = self.request(server, "/api/local-workbench/experience-import", "POST", body, headers)
        self.assertEqual(status, 200)
        self.assertEqual(imported["status"], "completed")
        self.assertTrue(self.request(server, "/api/local-workbench/experience-import", "POST", body, headers)[1]["replayed"])
        self.assertTrue(self.request(server, "/api/local-workbench/experience-resume", "POST",
                                     {key: body[key] for key in ("request_id", "project_id")}, headers)[1]["replayed"])
        status, view = self.request(server, "/api/local-workbench/experiences")
        self.assertEqual(status, 200)
        self.assertEqual(len(view["cases"]), 1)
        retired = self.status_body()
        self.assertEqual(self.request(server, "/api/local-workbench/experience-status", "POST", retired, headers)[0], 200)
        readonly = self.serve(local_workspace=self.manager)
        self.assertEqual(self.request(readonly, "/api/local-workbench/experiences")[0], 200)
        self.assertEqual(self.request(readonly, "/api/local-workbench/experience-status", "POST", retired, {"Content-Type": "application/json"})[0], 405)


if __name__ == "__main__":
    unittest.main()
