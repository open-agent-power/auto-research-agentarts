"""CPU advice follows existing inclusion and context paths, without research execution."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_cpu_project_experience as fixtures
from autoresearch import cpu_project_experience as cpu, project_experience as ridge
from autoresearch import project_experience_dispatch as dispatch
from autoresearch.contracts import ResearchError, canonical
from autoresearch.project_controller import ProjectController
from autoresearch.project_experience_binding import import_case, set_status, view_cases, case_assets
from autoresearch.project_report import _experience_rows
from autoresearch.research_project import ResearchProject


class CPUExperienceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = fixtures.CPUExperienceTests()
        cls.fixture.setUp()
        cls.addClassCleanup(cls.fixture.doCleanups)
        derived = cls.fixture.derive()
        cls.fixture.memory.import_project(cls.fixture.fake.root, cls.fixture.action["id"])
        cls.bundle = cls.fixture.export(derived)
        cls.raw = canonical(cls.bundle).encode()

    def target(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        source = root / "fixture-input" / "packet.json"
        source.parent.mkdir()
        source.write_bytes(canonical(self.fixture.f.packet).encode())
        project = ResearchProject(root / "engineering-target")
        # Fresh synthetic fixture only. No original research project is copied,
        # upgraded or advanced; the minimum local allowance remains entirely unused.
        project.create(source=source, goal="Engineering check of saved case inclusion only",
                       budget_ref="engineering:cpu-case-inclusion-no-execution", max_tool_calls=1,
                       method_id=self.fixture.action["command"])
        return project

    def include(self, project, request_id="include-cpu"):
        return import_case(project, request_id=request_id, expected_state_version=0, bundle=self.raw,
                           reason="Read this historical example without executing research.")

    def test_dispatch_keeps_CPU_and_Ridge_validators_separate(self):
        self.assertEqual(dispatch.parse_bundle(self.raw), self.bundle)
        with self.assertRaises(ResearchError):
            ridge.parse_bundle(self.raw)
        marker = {"legacy": "same validator result"}
        with patch.object(ridge, "validate_bundle", return_value=marker) as legacy:
            value = {"schema_version": "project-experience-bundle-v1"}
            self.assertEqual(dispatch.validate_bundle(value), marker)
            legacy.assert_called_once_with(value)
        for value in ({"schema_version": "unsupported"}, [], None):
            with self.subTest(value=value), self.assertRaises(ResearchError):
                dispatch.validate_bundle(value)

    def test_project_inclusion_replay_retirement_and_original_bundle_assets(self):
        project = self.target()
        budget = copy.deepcopy(project.status()["budget"])
        first = self.include(project)
        self.assertEqual(self.include(project), first)
        cases = view_cases(project.root, project.status())
        self.assertEqual(cases[0]["observation"]["kind"], "saved_cpu_fixed_pair")
        self.assertEqual(cases[0]["transfer_scope"], "analogy_not_current_evidence")
        self.assertEqual(case_assets(project.root, project.status())[0]["data"], self.raw)
        state = project.status()
        retired = set_status(project, request_id="retire-cpu", expected_state_version=state["state_version"],
                             case_id=self.bundle["id"], status="retired", reason="Withdraw local reference.")
        self.assertEqual(view_cases(project.root, project.status())[0]["inclusion_status"], "retired")
        self.assertEqual(self.include(project), first)
        self.assertEqual(view_cases(project.root, project.status())[0]["inclusion_status"], "retired")
        self.assertEqual(project.status()["budget"], budget)
        self.assertEqual(project.status()["actions"], [])
        self.assertEqual(set_status(project, request_id="retire-cpu", expected_state_version=state["state_version"],
                                    case_id=self.bundle["id"], status="retired", reason="Withdraw local reference."), retired)

    def test_context_association_keeps_original_candidates_and_budget(self):
        project = self.target()
        controller = ProjectController(project.root)
        before = controller.selection_context()
        self.include(project)
        after = controller.selection_context()
        self.assertEqual(before["candidates"], after["candidates"])
        self.assertEqual(before["budget"], after["budget"])
        case = after["experience"]["cases"][0]
        self.assertEqual(case["transfer_scope"], "analogy_not_current_evidence")
        self.assertFalse(case["scientific_validation"])
        self.assertTrue(case["association"]["matching_candidate_ids"])
        self.assertEqual(project.status()["actions"], [])

    def test_report_CPU_branch_does_not_require_Ridge_or_target_fields(self):
        case = {**cpu.summary(self.bundle), "inclusion_status": "active"}
        self.assertNotIn("numerical_summary", case["observation"])
        rows = _experience_rows({"experience_cases": [case]})
        rendered = canonical(rows)
        self.assertIn("tfidf_cosine", rendered)
        self.assertIn("bm25", rendered)
        self.assertIn("非本项目结果", rendered)
        for irrelevant in ("MAE", "训练均值", "原目标 None"):
            self.assertNotIn(irrelevant, rendered)


if __name__ == "__main__":
    unittest.main()
