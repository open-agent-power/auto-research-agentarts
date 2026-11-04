"""One bounded-context regression with real frozen lexical indexes."""
from pathlib import Path
import tempfile
import unittest

from autoresearch.contracts import canonical
from autoresearch.project_knowledge import build, decision_needs, query


class ProjectKnowledgeRecencyTests(unittest.TestCase):
    def test_new_completed_index_reaches_limit_and_old_exact_query_remains_readonly(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        project = {"registration": {"method_id": "data.tabular-quality-audit"},
                   "source_scope": {"target_column": "Mean_Red_Intensity", "numeric_columns": ["Count", "Mean_Red_Intensity"]},
                   "knowledge_refs": []}
        number = 0
        for ordinal, label, count in ((1, "OLDESTUNIQUE", 5), (2, "MIDDLEUNIQUE", 5), (3, "TMPMP", 3)):
            action = {"id": "action-index-" + str(ordinal), "receipt_snapshot_sha256": str(ordinal) * 64}
            selections = []
            for index in range(count):
                number += 1
                identity = f"{number:064x}"
                selections.append({"id": "selection-" + str(index),
                    "source": {"id": "source-" + str(number), "url": "urn:test:extracted:" + str(number),
                               "asset_sha256": identity, "sha256": identity, "license_note": "Fixture only"},
                    "locator": {"kind": "text_lines", "value": "1"},
                    "extraction": {"text": "missing invalid nonfinite group target_unit Count Mean_Red_Intensity " + label}})
            project["knowledge_refs"].append(build(root, action, {"result": {"selections": selections}}))
        original_project = canonical(project)
        original_files = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}
        current = query(root, project, need=decision_needs(project)["interpretation"], limit=5)
        self.assertEqual(len(current["evidence"]), 5)
        self.assertEqual(sum("TMPMP" in hit["quote"] for hit in current["evidence"]), 3)
        self.assertTrue(all("TMPMP" in hit["quote"] for hit in current["evidence"][:3]))
        self.assertEqual([ref["action_id"] for ref in current["index_refs"]], ["action-index-3", "action-index-2", "action-index-1"])
        archived = query(root, project, need="OLDESTUNIQUE", limit=5)
        self.assertEqual(len(archived["evidence"]), 5)
        self.assertTrue(all("OLDESTUNIQUE" in hit["quote"] for hit in archived["evidence"]))
        self.assertEqual(canonical(project), original_project)
        self.assertEqual([ref["action_id"] for ref in project["knowledge_refs"]], ["action-index-1", "action-index-2", "action-index-3"])
        self.assertEqual({str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}, original_files)


if __name__ == "__main__":
    unittest.main()
