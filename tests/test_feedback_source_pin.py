"""Reader-only source drift must stop a new action in a fresh interpreter."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import autoresearch
import test_hypothesis_feedback as fixtures


class FeedbackSourcePinTests(unittest.TestCase):
    fixture = fixtures.HypothesisFeedbackTests.fixture
    register = fixtures.HypothesisFeedbackTests.register

    def test_changed_reader_bytes_block_original_target_without_reset_or_dispatch(self):
        project, candidate = self.fixture()
        self.register(project, candidate)
        before = project.status()
        temporary = self.enterContext(tempfile.TemporaryDirectory())
        copied = Path(temporary) / "src" / "autoresearch"
        shutil.copytree(Path(autoresearch.__file__).parent, copied,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        script = '''
import json,sys
from autoresearch.research_project import ResearchProject,code_identity
from autoresearch.project_controller import ProjectController
from autoresearch.contracts import ResearchError
p=ResearchProject(sys.argv[1]); state=p.status()
c=ProjectController(p.root).selection_context()
proposal={"schema_version":"project-selection-proposal-v1","context_sha256":c["context_sha256"],
          "provider":{"kind":"operator_assistant","label":"source drift engineering probe"},
          "choice":{"kind":"wait"},"rationale":"Do not dispatch changed source","evidence_citation_ids":[]}
code=None
try:
    ProjectController(p.root).advance_selection(request_id="future",proposal=proposal,expected_state_version=state["state_version"])
except ResearchError as error:
    code=error.code
print(json.dumps({"identity":code_identity(),"registered":state["code_identity"],"blockers":c["blockers"],
                  "code":code,"unchanged":p.status()==state,"actions":len(p.status()["actions"])}))
'''
        env = dict(os.environ, PYTHONPATH=str(copied.parent), PYTHONDONTWRITEBYTECODE="1")
        baseline = subprocess.run([sys.executable, "-B", "-c",
            "from autoresearch.research_project import code_identity; print(code_identity())"],
            env=env, capture_output=True, text=True, check=True)
        self.assertEqual(baseline.stdout.strip(), before["code_identity"])
        # Only the isolated copy changes; no real source pin or ledger is edited.
        reader = copied / "saved_retrieval_reader.py"
        reader.write_bytes(reader.read_bytes() + b"\n# Isolated reader-only drift probe.\n")
        result = subprocess.run([sys.executable, "-B", "-c", script, str(project.root)],
                                env=env, capture_output=True, text=True, check=True)
        observed = json.loads(result.stdout)
        self.assertNotEqual(observed["identity"], observed["registered"])
        self.assertEqual(observed["code"], "CODE_CHANGED")
        self.assertIn("CODE_CHANGED", [row["code"] for row in observed["blockers"]])
        self.assertTrue(observed["unchanged"])
        self.assertEqual(observed["actions"], 0)
        self.assertEqual(project.status(), before)


if __name__ == "__main__":
    unittest.main()
