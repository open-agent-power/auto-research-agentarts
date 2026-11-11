"""Persistence/recovery contracts; arithmetic is covered by the separate real-source trial."""
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch.contracts import ResearchError
from autoresearch.research_project import ResearchProject
from autoresearch import source_evidence_adapter
from autoresearch import source_integrity_adapter, method_registry
from autoresearch.contracts import canonical


class ResearchProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = self.root / "historical" / "source.json"
        source.parent.mkdir()
        source.write_bytes(b'{"fixture":"persistence-only"}')
        self.source = source
        source_patch = patch("autoresearch.research_project.adapter.load_source", return_value={
            "snapshot_sha256": "a" * 64, "scope": {"fixture": "not_scientific_evidence"}})
        source_patch.start()
        self.addCleanup(source_patch.stop)
        self.compute = patch("autoresearch.research_project.adapter.execute", return_value={
            "status": "completed", "observations": [{"producer": "fixture", "values": {"mae": 2}}],
            "result": {"rows": [1, 2, 3]}, "new_fits": 0}).start()
        self.addCleanup(patch.stopall)
        patch("autoresearch.research_project.adapter.next_decision", return_value={
            "project_status": "waiting", "next_action": {"method_id": "p02.source-mapping-check", "kind": "evidence_task",
                                                          "execution_status": "not_executed"},
            "reason": "Fixture negative feedback"}).start()
        self.project = ResearchProject(self.root / "project")
        self.initial = self.project.create(source=source, goal="Persistence fixture", budget_ref="original:budget")

    def assert_code(self, code, call, **kwargs):
        with self.assertRaises(ResearchError) as caught:
            call(**kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_restart_replay_conflict_reuse_and_budget(self):
        self.assert_code("STALE_STATE", self.project.step, request_id="stale", expected_state_version=10)
        action = self.project.step(request_id="first", expected_state_version=0)
        reopened = ResearchProject(self.root / "project")
        self.assertEqual(reopened.resume(request_id="first")["id"], action["id"])
        self.assertTrue(reopened.step(request_id="first", expected_state_version=0)["replayed"])
        self.assertTrue(reopened.step(request_id="another-id")["reused"])
        self.assert_code("IDEMPOTENCY_CONFLICT", reopened.step, request_id="first", dimension="topography")
        self.assert_code("IDEMPOTENCY_CONFLICT", reopened.step, request_id="another-id", dimension="topography")
        self.compute.assert_called_once()
        status = reopened.status()
        self.assertEqual(len(status["actions"]), 1)
        self.assertEqual(status["budget"]["local_tool_calls_used"], 1)
        self.assertEqual(status["budget"]["lineage_ref"], "original:budget")
        self.assertEqual(status["budget"]["new_model_requests"], 0)
        self.assertEqual(status["next_decision"]["based_on_action_id"], action["id"])
        original = self.project.create(source=self.source, goal="Persistence fixture", budget_ref="original:budget")
        self.assertEqual(original["id"], self.initial["id"])
        self.assertEqual(original["budget"]["local_tool_calls_used"], 1)
        artifact = json.loads((self.project.root / action["artifact"]).read_bytes())
        self.assertEqual(artifact["tool_result"]["result"]["rows"], [1, 2, 3])

    def test_saved_result_after_interrupted_commit_recovers_without_compute(self):
        with patch.object(self.project, "_commit_result", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.project.step(request_id="interrupted")
        self.assertEqual(self.project.status()["actions"][0]["status"], "running")
        restored = ResearchProject(self.project.root).resume(request_id="interrupted")
        self.assertTrue(restored["recovered"])
        self.assertEqual(restored["status"], "completed")
        self.compute.assert_called_once()
        self.assertEqual(self.project.status()["budget"]["local_tool_calls_reserved"], 0)

    def test_unknown_retains_reservation_and_never_reexecutes(self):
        self.compute.side_effect = KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.project.step(request_id="unknown")
        restored = ResearchProject(self.project.root).resume(request_id="unknown")
        self.assertEqual(restored["status"], "unknown")
        self.assertEqual(self.project.step(request_id="unknown")["status"], "unknown")
        self.assert_code("EXECUTION_UNKNOWN", self.project.step, request_id="bypass")
        self.compute.assert_called_once()
        self.assertEqual(self.project.status()["budget"]["local_tool_calls_reserved"], 1)

    def test_integrity_failure_and_active_writer_do_not_dispatch(self):
        with self.project._writer():
            self.assert_code("PROJECT_BUSY", self.project.step, request_id="concurrent")
        (self.project.root / "source.json").write_bytes(b'changed')
        self.assert_code("EVIDENCE_CHANGED", self.project.step, request_id="tampered")
        self.assert_code("INVALID_REQUEST", self.project.step, request_id="bad", dimension="../../code")
        self.compute.assert_not_called()
        self.assertEqual(self.project.status()["actions"], [])

    def bundle(self):
        self.project.step(request_id="numerical")
        folder = self.root / "bundle"
        (folder / "sources").mkdir(parents=True)
        raw = b"Original fixture: object channel export mapping remains unknown.\nALP is not confirmed.\n"
        (folder / "sources/source.txt").write_bytes(raw)
        document = {"schema_version": "project-evidence-bundle-v1", "task_ref": self.project.evidence_task()["task_ref"],
                    "contributor": {"role": "operator_assistant", "label": "persistence fixture"},
                    "sources": [{"id": "fixture", "path": "sources/source.txt", "sha256": hashlib.sha256(raw).hexdigest(),
                                 "url": "https://example.invalid/fixture", "media_type": "text/plain", "license_note": "test fixture"}],
                    "selections": [{"id": "selection", "source_id": "fixture", "locator": {"kind": "text_lines", "value": "1-2"},
                                    "claim": "Fixture asks for original mapping, not scientific approval"}],
                    "remaining_questions": ["Need author export mapping"]}
        (folder / "manifest.json").write_text(json.dumps(document), encoding="utf-8")
        return folder, document

    def test_source_evidence_knowledge_and_request_binding(self):
        folder, document = self.bundle()
        observed = self.project.attach_evidence(request_id="source-1", bundle=folder)
        self.assertEqual(observed["observations"][0]["endpoint_eligibility"], "unknown")
        self.assertEqual(len(observed["next_decision"]["knowledge_contexts"]), 4)
        hits = self.project.knowledge(need="object channel mapping")["evidence"]
        self.assertTrue(hits)
        self.assertEqual(hits[0]["source"]["metadata"]["locator"]["value"], "1-2")
        self.assertTrue(self.project.attach_evidence(request_id="source-1", bundle=folder)["replayed"])
        self.assertTrue(self.project.attach_evidence(request_id="source-alias", bundle=folder)["reused"])
        document["selections"][0]["claim"] = "Changed content"
        (folder / "manifest.json").write_text(json.dumps(document), encoding="utf-8")
        self.assert_code("IDEMPOTENCY_CONFLICT", self.project.attach_evidence, request_id="source-1", bundle=folder)
        document["task_ref"]["project_id"] = "another-project"
        (folder / "manifest.json").write_text(json.dumps(document), encoding="utf-8")
        self.assert_code("TASK_MISMATCH", self.project.attach_evidence, request_id="wrong-task", bundle=folder)
        state = self.project.status()
        self.assertEqual(state["id"], self.initial["id"])
        self.assertEqual(state["budget"]["local_tool_calls_used"], 1)
        self.assertEqual(state["budget"]["evidence_reads_used"], 1)
        self.assertEqual(state["research_status"], "waiting")

    def test_source_saved_result_recovery_does_not_reextract(self):
        folder, _ = self.bundle()
        with patch("autoresearch.research_project.source_adapter.execute", wraps=source_evidence_adapter.execute) as extract:
            with patch.object(self.project, "_commit_result", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    self.project.attach_evidence(request_id="source-crash", bundle=folder)
            recovered = ResearchProject(self.project.root).resume(request_id="source-crash")
            self.assertTrue(recovered["recovered"])
            extract.assert_called_once()
        self.assertEqual(self.project.status()["budget"]["evidence_reads_used"], 1)

    def test_explicit_upgrade_preserves_history_and_cannot_bypass_unknown(self):
        self.project.step(request_id="original")
        before = self.project.status()
        with self.project._connect() as con:
            project = self.project._project(con)
            project.update(code_identity="a" * 64, schema_version="local-research-project-v1")
            project.pop("code_revisions", None)
            project["budget"].pop("evidence_read_limit", None)
            self.project._save(con, project)
        revision = self.project.upgrade(request_id="upgrade-1", expected_code_identity="a" * 64)
        after = self.project.status()
        self.assertEqual(after["id"], before["id"])
        self.assertEqual(after["actions"], before["actions"])
        self.assertEqual(after["budget"]["local_tool_calls_used"], 1)
        self.assertEqual(after["budget"]["historical_request_counts"], None)
        self.assertEqual(self.project.upgrade(request_id="upgrade-1", expected_code_identity="a" * 64), revision)
        self.assert_code("IDEMPOTENCY_CONFLICT", self.project.step, request_id="upgrade-1")
        with self.project._connect() as con:
            action = self.project._action(con, "original")
            action["status"] = "unknown"
            con.execute("UPDATE actions SET record=? WHERE request_id=?", (json.dumps(action), "original"))
        self.assert_code("EXECUTION_UNKNOWN", self.project.upgrade, request_id="bypass-unknown", expected_code_identity=after["code_identity"])

    def test_completed_upgrade_replays_its_historical_receipt_after_later_code_versions(self):
        original = self.project.status()
        with patch("autoresearch.research_project.code_identity", return_value="b" * 64):
            first = self.project.upgrade(request_id="first-upgrade", expected_code_identity=original["code_identity"])
        with patch("autoresearch.research_project.code_identity", return_value="c" * 64):
            self.project.upgrade(request_id="second-upgrade", expected_code_identity="b" * 64)
            before = self.project.status()
            files = {str(path.relative_to(self.project.root)): path.read_bytes() for path in self.project.root.rglob("*") if path.is_file()}
            self.assertEqual(self.project.upgrade(request_id="first-upgrade", expected_code_identity=original["code_identity"]), first)
            self.assertEqual(self.project.status(), before)
            self.assertEqual(files, {str(path.relative_to(self.project.root)): path.read_bytes() for path in self.project.root.rglob("*") if path.is_file()})
            self.assert_code("IDEMPOTENCY_CONFLICT", self.project.upgrade, request_id="first-upgrade", expected_code_identity="b" * 64)
            self.assert_code("IDEMPOTENCY_CONFLICT", self.project.upgrade, request_id="first-upgrade", expected_code_identity=original["code_identity"], evidence_read_limit=7)
        with patch("autoresearch.research_project.code_identity", return_value="d" * 64):
            self.assertEqual(self.project.upgrade(request_id="first-upgrade", expected_code_identity=original["code_identity"]), first)
            self.assert_code("CODE_CHANGED", self.project.step, request_id="cannot-skip-current-upgrade")

    def test_domain_registry_does_not_reuse_p02_parameters_or_endpoint(self):
        packet = source_integrity_adapter.capture_source(Path(source_evidence_adapter.__file__))
        folder = self.root / "software-inputs"
        folder.mkdir()
        source = folder / "source.json"
        source.write_text(canonical(packet), encoding="utf-8")
        project = ResearchProject(self.root / "software-project")
        project.create(source=source, goal="Check file capture", budget_ref="software-local",
                       method_id=source_integrity_adapter.TOOL_ID)
        option = project.method_options()["options"][0]
        self.assertEqual(option["method_id"], source_integrity_adapter.TOOL_ID)
        self.assertEqual(option["domain_scope"]["contract"], "file-capture-consistency-v1")
        self.assertNotIn("target", option["domain_scope"])
        self.assert_code("INVALID_REQUEST", project.step, request_id="wrong-dimension", dimension="chemistry")
        self.assert_code("METHOD_NOT_SUPPORTED", method_registry.get, method_id="arbitrary.python.module")
        self.assertEqual(project.status()["actions"], [])

    def test_failed_source_receipt_is_not_offered_for_automatic_retry(self):
        folder, document = self.bundle()
        document["selections"][0]["locator"]["value"] = "20-21"
        (folder / "manifest.json").write_text(json.dumps(document), encoding="utf-8")
        self.assert_code("INVALID_LOCATOR", self.project.attach_evidence, request_id="failed-selection", bundle=folder)
        option = next(o for o in self.project.method_options()["options"] if o["method_id"] == source_evidence_adapter.TOOL_ID)
        self.assertEqual(option["source_readable"], 0)
        self.assertEqual(option["condition"], "uncertain")
        self.assertEqual(self.project.status()["budget"]["evidence_reads_used"], 1)

    def test_registered_inputs_are_bounded_and_rechecked_before_any_read(self):
        folder, document = self.bundle()
        with self.project._connect() as con:
            state = self.project._project(con)
            state["budget"]["evidence_read_limit"] = 1
            self.project._save(con, state)
        registration = self.project.register_evidence(request_id="stage", bundle=folder)
        self.assertTrue(self.project.register_evidence(request_id="stage", bundle=folder)["replayed"])
        self.assertTrue(self.project.register_evidence(request_id="alias", bundle=folder)["reused"])
        self.assertEqual(len(self.project.status()["evidence_sources"]), 1)
        document["selections"][0]["claim"] = "Different registration"
        (folder / "manifest.json").write_text(json.dumps(document), encoding="utf-8")
        self.assert_code("IDEMPOTENCY_CONFLICT", self.project.register_evidence, request_id="stage", bundle=folder)
        self.assert_code("BUDGET_EXHAUSTED", self.project.register_evidence, request_id="over-cap", bundle=folder)
        receipt = json.loads((self.project.root / registration["input_receipt"]).read_bytes())
        asset = self.project.root / "evidence-inputs" / registration["receipt_snapshot_sha256"] / (receipt["sources"][0]["asset_sha256"] + ".bin")
        asset.write_bytes(b"actually changed bytes")
        self.assert_code("EVIDENCE_CHANGED", self.project.read_evidence, request_id="read-tampered",
                         receipt_snapshot_sha256=registration["receipt_snapshot_sha256"])
        self.assertEqual(self.project.status()["evidence_actions"], [])
        self.assertEqual(self.project.status()["budget"]["evidence_reads_used"], 0)


if __name__ == "__main__":
    unittest.main()
