"""One display-only check for latest completed source claims and preserved originals."""
import copy
from pathlib import Path
import tempfile
import unittest

import test_local_workbench as fixtures
from autoresearch.contracts import canonical
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_report import _association_rows, _latest_source_review_lines, _markdown, _pdf, _source_notes, collect_report


class ProjectReportCurrentSourcesTests(unittest.TestCase):
    def test_numeric_association_report_shows_sample_scope_and_null_reason(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        manager = LocalWorkbench(root / "manager")
        manager.create(fixtures.LocalWorkbenchTests.create_body(self))
        project, _ = manager.binding()
        report = collect_report(project.root)
        result = {"schema_version": "numeric-association-v1", "target_column": "progression_target",
                  "predecessor": {"based_on_action_id": "quality-action"},
                  "overall": [{"predictor": "bmi", "n": 4, "excluded": 0, "pearson_r": 1.0, "reason": None}],
                  "groups": [{"group_id": "group-a", "rows": 3,
                              "first_coordinate": {"logical_record": 1, "physical_line_end": 2},
                              "associations": [{"predictor": "bmi", "n": 3, "excluded": 0, "pearson_r": 1.0, "reason": None}]},
                             {"group_id": "group-b", "rows": 1,
                              "first_coordinate": {"logical_record": 4, "physical_line_end": 5},
                              "associations": [{"predictor": "bmi", "n": 1, "excluded": 0, "pearson_r": None,
                                                "reason": "insufficient_pairs"}]}],
                  "incomplete_group": {"rows": 0, "associations": []}}
        report["action_results"] = [{"action_id": "association-action", "command": "data.numeric-association",
                                      "status": "completed", "failure": None,
                                      "tool_result": {"result": result}}]
        before = canonical(report)
        self.assertEqual(_association_rows(result)[-1][-1], "有效对少于3")
        markdown = _markdown(report)
        for expected in ("数值关联", "progression_target", "association-action", "quality-action", "有效对少于3"):
            self.assertIn(expected, markdown)
        self.assertTrue(_pdf(report).startswith(b"%PDF-"))
        self.assertEqual(canonical(report), before)

    @staticmethod
    def selection(index, claim):
        return {"id": "selection-" + str(index), "source": {"id": "fixture-source", "sha256": "a" * 64,
                "url": "urn:test:source", "license_note": "Unverified fixture declaration"},
                "locator": {"kind": "text_lines", "value": str(index + 1)},
                "extraction": {"text": "Saved source excerpt " + str(index)},
                "submitted_claim": {"status": "submitter_claim_unreviewed", "text": claim}}

    @staticmethod
    def action(action_id, status, label, selections, questions):
        return {"action_id": action_id, "command": "research.source-selection", "status": status,
                "failure": {"code": "FIXTURE_FAILED", "message": "Original failed source retained"} if status != "completed" else None,
                "tool_result": {"result": {"contributor": {"role": "operator_assistant", "label": label},
                    "mapping_status": "unresolved", "endpoint_eligibility": "unknown",
                    "selections": selections, "remaining_questions": questions}}}

    def test_latest_completed_claims_and_questions_precede_methods_without_rewriting_source_history(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        manager = LocalWorkbench(root / "manager")
        manager.create(fixtures.LocalWorkbenchTests.create_body(self))
        project, _ = manager.binding()
        report = collect_report(project.root)
        self.assertEqual(_latest_source_review_lines(report), [])
        self.assertNotIn("## 最新来源核对与未决问题", _markdown(report))
        old = [self.selection(index, "OLD CLAIM " + str(index)) for index in range(6)]
        new = [self.selection(0, "216条保存差异：原表Chem0与metadata Chem28未确认对应。")]
        new.extend(self.selection(index, "New saved claim " + str(index)) for index in range(6, 11))
        new.append(self.selection(11, "CLAIM-SEVEN-HIDDEN-FROM-FRONT"))
        questions = ["Chem0/28编码规则是什么？", "Series到实际图像及对象导出的映射是什么？",
                     "零值原因和ALP通道仍待确认。", "独立单位与版本规则仍未知。", "Question five", "Question six", "QUESTION-SEVEN-HIDDEN-FROM-FRONT"]
        report["action_results"] = [self.action("source-old", "completed", "OLD-LABEL", old, ["OLD QUESTION"]),
            self.action("source-current", "completed", "CURRENT-LABEL", new, questions),
            self.action("source-failed-later", "failed", "FAILED-LABEL", [self.selection(20, "FAILED CLAIM")], ["FAILED QUESTION"])]
        report["source_selections"] = [*old, *new]
        report["registered_inputs"].append({"read_status": "registered_unread", "contributor": {"label": "UNREAD-LABEL"},
                                            "remaining_questions": ["UNREAD QUESTION"]})
        original = canonical(report)
        raw_selections = copy.deepcopy(report["source_selections"])
        lines = _latest_source_review_lines(report)
        self.assertEqual(sum(line.startswith("提交者主张 ") for line in lines), 6)
        self.assertEqual(sum(line.startswith("未决问题 ") for line in lines), 6)
        front = "\n".join(lines)
        for value in ("source-current", "operator_assistant", "CURRENT-LABEL", "216", "Chem0", "Chem28",
                      "submitter_claim_unreviewed", "未经作者或科学确认", "unresolved", "unknown"):
            self.assertIn(value, front)
        for value in ("OLD-LABEL", "FAILED-LABEL", "FAILED CLAIM", "UNREAD-LABEL", "UNREAD QUESTION",
                      "CLAIM-SEVEN-HIDDEN-FROM-FRONT", "QUESTION-SEVEN-HIDDEN-FROM-FRONT"):
            self.assertNotIn(value, front)
        notes = _source_notes(report)
        self.assertEqual(notes[0]["claim"], "CLAIM-SEVEN-HIDDEN-FROM-FRONT")
        same_location = [note for note in notes if note["sha256"] == "a" * 64 and note["locator"] == canonical(old[0]["locator"])]
        self.assertEqual(len(same_location), 1)
        self.assertIn("216", same_location[0]["claim"])
        self.assertEqual(same_location[0]["claim_status"], "submitter_claim_unreviewed")
        markdown = _markdown(report)
        self.assertLess(markdown.index("## 最新来源核对与未决问题"), markdown.index("## 方法与冻结评价"))
        front_md = markdown.split("## 最新来源核对与未决问题", 1)[1].split("## 方法与冻结评价", 1)[0]
        for value in ("216", "Chem0", "Chem28", "CURRENT-LABEL", "submitter_claim_unreviewed", "未经作者或科学确认"):
            self.assertIn(value, front_md)
        self.assertNotIn("FAILED-LABEL", markdown)
        self.assertNotIn("UNREAD-LABEL", markdown)
        self.assertEqual(report["source_selections"], raw_selections)
        self.assertEqual(report["source_selections"][0]["submitted_claim"]["text"], "OLD CLAIM 0")
        self.assertEqual(canonical(report), original)


if __name__ == "__main__":
    unittest.main()
