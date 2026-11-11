"""One display-only check for latest completed source claims and preserved originals."""
import copy
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pypdf import PdfReader

import test_local_workbench as fixtures
import test_numeric_association as numeric_fixtures
import test_project_prediction_design as design_fixtures
from autoresearch import numeric_association_adapter as numeric, tabular_quality_adapter as tabular
from autoresearch.contracts import ResearchError, canonical
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_report import _association_rows, _latest_source_review_lines, _markdown, _pdf, _source_notes, collect_report
from autoresearch.research_project import ResearchProject
from autoresearch.project_controller import ProjectController
from autoresearch.project_design import bind


class ProjectReportCurrentSourcesTests(unittest.TestCase):
    def test_saved_prediction_report_keeps_design_versions_metrics_and_sensitivity(self):
        project = design_fixtures.ProjectPredictionDesignTests.project(
            self, "group,observed,prediction,other\na,0,3,0\na,1,4,0\nb,2,5,0\nb,3,6,0\nc,20,20,0\nc,21,21,0\n")
        resource = design_fixtures.ProjectPredictionDesignTests.resource(self)
        project.extend_local_budget(request_id="four-checks", expected_limit=2, new_limit=4, reason="Report fixture checks")
        revision = bind(project, request_id="design", expected_state_version=project.status()["state_version"],
                        resource=resource, prediction_column="prediction", reason="Check report evidence")
        controller = ProjectController(project.root)
        for request_id in ("quality", "baseline", "grouped", "sensitivity"):
            self.assertEqual(controller.advance(request_id=request_id)["status"], "completed")
        saved = project.status()
        report = collect_report(project.root)
        self.assertEqual(report["title"], "保存预测验证与研究设计报告")
        self.assertEqual(report["input"]["design_revisions"], [revision])
        self.assertTrue(report["action_results"][-1]["tool_result"]["result"]["analysis"]["details"]["removals"])
        markdown = _markdown(report)
        for content in (resource["title"], resource["id"], "绑定v1", "预测MAE", "相对改善", "删除单位后结论反转",
                        "影响最大的删除单位", "剩余预测MAE 3", "参考MAE 2", "-50%"):
            self.assertIn(content, markdown)
        pdf = PdfReader(BytesIO(_pdf(report)))
        text = "\n".join(page.extract_text() for page in pdf.pages)
        for content in ("保存预测验证与研究设计报告", "预测MAE", "参考MAE", "删除单位后结论反转", "-50%"):
            self.assertIn(content, text)
        self.assertEqual(project.status(), saved)

    def test_saved_numeric_association_changes_markdown_and_pdf_title_only_when_completed(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        payload = numeric_fixtures.NumericAssociationTests.payload(
            self, "group,x,outcome\na,1,2\na,2,4\na,3,6\nb,4,8\nb,5,10\nb,6,12\n")
        source = root / "captured" / "source.json"
        source.parent.mkdir()
        source.write_text(canonical(payload), encoding="utf-8")
        for completed in (False, True):
            with self.subTest(completed=completed):
                project = ResearchProject(root / ("completed" if completed else "failed"))
                project.create(source=source, goal="Describe fixture numeric association", budget_ref="fixture:report-title",
                               max_tool_calls=2, method_id=tabular.TOOL_ID)
                project.step(request_id="quality")
                quality_state = project.status()
                report = collect_report(project.root)
                self.assertEqual(report["title"], "表格质量与分组核对报告")
                self.assertTrue(_markdown(report).startswith("# " + report["title"] + "\n"))
                quality = quality_state["actions"][0]
                parameters = {"based_on_action_id": quality["id"], "based_on_result_sha256": quality["result_sha256"]}
                if completed:
                    project.step(request_id="association", method_id=numeric.TOOL_ID, parameters=parameters,
                                 expected_state_version=quality_state["state_version"])
                else:
                    with patch.object(numeric, "execute", side_effect=ResearchError("FIXTURE_FAILED", "Saved fixture failure")):
                        with self.assertRaises(ResearchError) as caught:
                            project.step(request_id="association", method_id=numeric.TOOL_ID, parameters=parameters,
                                         expected_state_version=quality_state["state_version"])
                    self.assertEqual(caught.exception.code, "FIXTURE_FAILED")
                saved = project.status()
                report = collect_report(project.root)
                association = report["action_results"][-1]
                self.assertEqual(association["command"], numeric.TOOL_ID)
                self.assertEqual(association["status"], "completed" if completed else "failed")
                self.assertEqual(association["tool_result"] is not None, completed)
                title = "表格质量与数值关联报告" if completed else "表格质量与分组核对报告"
                self.assertEqual(report["title"], title)
                self.assertTrue(_markdown(report).startswith("# " + title + "\n"))
                pdf = PdfReader(BytesIO(_pdf(report)))
                self.assertEqual(pdf.metadata.title, title)
                self.assertIn(title, pdf.pages[0].extract_text())
                self.assertEqual(project.status(), saved)

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
