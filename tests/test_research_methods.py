"""Terminal tasks retain domain feedback after staged evidence is read."""
import copy
import unittest

from autoresearch import method_registry as registry, research_methods as methods


class DomainTaskTests(unittest.TestCase):
    def project(self, primary="materials.saved-steel-audit", task=None):
        task = task or {"method_id": registry.SOURCE, "kind": "evidence_task", "execution_status": "not_executed",
                        "required_evidence": ["original processing and heat-treatment records"]}
        return {"registration": {"method_id": primary}, "source_snapshot_sha256": "a" * 64,
                "source_scope": {"fixture": "task-preservation-only"},
                "actions": [{"id": "primary", "command": primary, "status": "completed", "observations": [],
                             "next_decision": {"next_action": task}}],
                "evidence_actions": [{"id": "read", "command": registry.SOURCE, "status": "completed",
                                      "receipt_snapshot_sha256": "b" * 64, "observations": []}],
                "evidence_sources": [{"receipt_snapshot_sha256": "b" * 64, "selection_count": 1}],
                "next_decision": {"next_action": {"method_id": registry.SOURCE, "kind": "conditional_proposal",
                                  "parameters": {"receipt_snapshot_sha256": "b" * 64}}}}

    def choose(self, project):
        return methods.choose_next(project, methods.match_methods(project))

    def test_completed_sources_restore_each_domains_original_requirements(self):
        software_task = {"method_id": registry.SOURCE, "kind": "evidence_task", "execution_status": "not_executed",
                         "parameters": {"need": "Acquire comparable evidence from another host/filesystem.", "failed_checks": []}}
        for primary, task in (("materials.saved-steel-audit", None), ("software.source-integrity-check", software_task)):
            with self.subTest(primary=primary):
                project = self.project(primary, task)
                before = copy.deepcopy(project)
                result = self.choose(project)
                self.assertEqual(result["project_status"], "waiting")
                self.assertFalse(result["scientific_validation"])
                self.assertEqual(result["next_action"], before["actions"][0]["next_decision"]["next_action"])
                result["next_action"]["caller_change"] = True
                self.assertEqual(project, before)

    def test_new_unread_source_is_still_proposed_before_the_terminal_task(self):
        project = self.project()
        project["evidence_sources"].append({"receipt_snapshot_sha256": "c" * 64, "selection_count": 1})
        result = self.choose(project)
        self.assertEqual(result["project_status"], "active")
        self.assertEqual(result["next_action"]["kind"], "conditional_proposal")
        self.assertEqual(result["next_action"]["parameters"]["receipt_snapshot_sha256"], "c" * 64)
        self.assertFalse(result["scientific_validation"])

    def test_newer_explicit_task_is_not_overwritten_with_older_feedback(self):
        project = self.project()
        newer = {"method_id": registry.SOURCE, "kind": "evidence_task", "execution_status": "not_executed",
                 "required_evidence": ["a newer independently supplied requirement"]}
        project["next_decision"]["next_action"] = copy.deepcopy(newer)
        self.assertEqual(self.choose(project)["next_action"], newer)

    def test_missing_original_task_uses_a_gap_without_a_completed_receipt(self):
        project = self.project()
        project["actions"][0].pop("next_decision")
        result = self.choose(project)
        self.assertEqual(result["project_status"], "waiting")
        self.assertEqual(result["next_action"]["kind"], "evidence_task")
        self.assertNotIn("receipt_snapshot_sha256", result["next_action"].get("parameters", {}))

    def test_source_read_restores_latest_followup_requirements(self):
        project = self.project("data.tabular-quality-audit")
        project["source_scope"]["group_columns"] = ["batch"]
        primary = project["actions"][0]
        primary["result_sha256"] = "c" * 64
        primary["observations"] = [{"kind": "tabular_quality_audit", "profile": {
            "numeric_columns": [{"counts": {"zero": 1}}]}}]
        task = copy.deepcopy(primary["next_decision"]["next_action"])
        task["required_evidence"].append("original grouping definitions and zero-event collection records")
        project["actions"].append({"id": "followup", "command": "data.grouped-quality-profile", "status": "completed",
            "method_instance": {"parameters": {"based_on_action_id": primary["id"], "based_on_result_sha256": primary["result_sha256"]}},
            "observations": [], "next_decision": {"next_action": task}})
        before = copy.deepcopy(project)
        self.assertEqual(self.choose(project)["next_action"], task)
        self.assertEqual(project, before)


if __name__ == "__main__":
    unittest.main()
