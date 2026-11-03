"""Focused parent-request and staged-input contracts; fixtures are not research evidence."""
import hashlib
import json
import unittest
from unittest.mock import patch

import test_research_project as fixtures
from autoresearch import source_evidence_adapter
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class ProjectControllerTests(unittest.TestCase):
    setUp = fixtures.ResearchProjectTests.setUp
    bundle = fixtures.ResearchProjectTests.bundle
    assert_code = fixtures.ResearchProjectTests.assert_code

    def test_unread_registration_dispatches_once_from_internal_bytes(self):
        folder, _ = self.bundle()
        before = self.project.status()
        with patch.object(source_evidence_adapter, "execute", wraps=source_evidence_adapter.execute) as extract:
            registration = self.project.register_evidence(request_id="register", bundle=folder)
            extract.assert_not_called()
            staged = self.project.status()
            self.assertEqual(staged["state_version"], before["state_version"] + 1)
            self.assertEqual(staged["budget"]["evidence_reads_used"], 0)
            self.assertEqual(staged["evidence_actions"], [])
            controller = ProjectController(self.project.root)
            digest = hashlib.sha256(self.project.db.read_bytes()).hexdigest()
            plan = controller.next()
            self.assertTrue(plan["executable"])
            self.assertEqual(plan["decision"]["next_action"]["parameters"]["receipt_snapshot_sha256"],
                             registration["receipt_snapshot_sha256"])
            self.assertEqual(hashlib.sha256(self.project.db.read_bytes()).hexdigest(), digest)
            folder.rename(folder.with_name("external-bundle-moved"))
            result = controller.advance(request_id="advance-source")
            self.assertEqual(result["status"], "completed")
            replay = ProjectController(self.project.root).advance(request_id="advance-source")
            self.assertTrue(replay["replayed"])
            self.assertEqual(replay["child_request_id"], result["child_request_id"])
            extract.assert_called_once()
        self.assertEqual(self.project.status()["budget"]["evidence_reads_used"], 1)

    def test_waiting_parent_stays_frozen_and_command_ids_cannot_collide(self):
        folder, _ = self.bundle()
        controller = ProjectController(self.project.root)
        waiting = controller.advance(request_id="frozen-wait")
        self.assertEqual(waiting["status"], "waiting")
        self.project.register_evidence(request_id="register", bundle=folder)
        self.assertTrue(controller.next()["executable"])
        replay = controller.advance(request_id="frozen-wait")
        self.assertIsNone(replay["child_request_id"])
        self.assertEqual(replay["decision"], waiting["decision"])
        self.assert_code("IDEMPOTENCY_CONFLICT", controller.advance, request_id="frozen-wait", need="changed")
        self.assert_code("IDEMPOTENCY_CONFLICT", self.project.step, request_id="frozen-wait")
        self.assert_code("IDEMPOTENCY_CONFLICT", self.project.register_evidence,
                         request_id="frozen-wait", bundle=folder)
        self.assert_code("IDEMPOTENCY_CONFLICT", controller.advance, request_id="register")
        self.assertEqual(self.project.status()["budget"]["evidence_reads_used"], 0)
        self.assertEqual(controller.advance(request_id="new-source-step")["status"], "completed")

    def test_saved_child_result_recovers_without_a_second_extraction(self):
        folder, _ = self.bundle()
        self.project.register_evidence(request_id="register", bundle=folder)
        controller = ProjectController(self.project.root)
        with patch.object(source_evidence_adapter, "execute", wraps=source_evidence_adapter.execute) as extract:
            with patch.object(ResearchProject, "_commit_result", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    controller.advance(request_id="crashed-parent")
            recovered = ProjectController(self.project.root).advance(request_id="crashed-parent")
            self.assertEqual(recovered["status"], "completed")
            extract.assert_called_once()
        self.assertEqual(self.project.status()["budget"]["evidence_reads_used"], 1)

    def test_unknown_child_and_busy_writer_never_redispatch(self):
        folder, _ = self.bundle()
        registration = self.project.register_evidence(request_id="register", bundle=folder)
        controller = ProjectController(self.project.root)
        with self.project._writer():
            self.assert_code("PROJECT_BUSY", controller.advance, request_id="busy-parent")
        with patch.object(source_evidence_adapter, "execute", side_effect=KeyboardInterrupt) as extract:
            with self.assertRaises(KeyboardInterrupt):
                controller.advance(request_id="unknown-parent")
            recovered = ProjectController(self.project.root).advance(request_id="unknown-parent")
            self.assertEqual(recovered["status"], "unknown")
            self.assertEqual(controller.advance(request_id="unknown-parent")["status"], "unknown")
            self.assertFalse(controller.next()["executable"])
            self.assertIsNone(controller.advance(request_id="do-not-bypass")["child_request_id"])
            self.assert_code("EXECUTION_UNKNOWN", self.project.read_evidence, request_id="direct-bypass",
                             receipt_snapshot_sha256=registration["receipt_snapshot_sha256"])
            extract.assert_called_once()
        self.assertEqual(self.project.status()["budget"]["evidence_reads_reserved"], 1)

    def test_state_change_after_parent_acceptance_rejects_the_frozen_dispatch(self):
        folder, _ = self.bundle()
        self.project.register_evidence(request_id="register", bundle=folder)
        controller = ProjectController(self.project.root)
        with patch.object(controller, "_dispatch", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                controller.advance(request_id="prepared-parent")
        self.project.register_evidence(request_id="interleaving-registration", bundle=folder)
        self.assert_code("STALE_STATE", ProjectController(self.project.root).advance,
                         request_id="prepared-parent")
        self.assert_code("STALE_STATE", controller.advance, request_id="prepared-parent")
        self.assertEqual(self.project.status()["evidence_actions"], [])
        self.assertEqual(controller.advance(request_id="fresh-parent")["status"], "completed")


if __name__ == "__main__":
    unittest.main()
