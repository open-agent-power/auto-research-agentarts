"""Synthetic native retrieval holdout lifecycle, no model, API or fitting."""
import copy
import json
import random
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_staged_relevance_adapter as fixtures
from autoresearch import retrieval_holdout as holdout, staged_relevance_adapter as staged
from autoresearch import relevance_retrieval_adapter as relevance, retrieval_lexical as lexical
from autoresearch.contracts import ResearchError, canonical
from autoresearch.research_project import ResearchProject
from autoresearch.project_controller import ProjectController


class RetrievalHoldoutTests(unittest.TestCase):
    def fixture(self, sign=None):
        helper = fixtures.StagedDevelopmentTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        if sign is not None:
            rng = random.Random(108)
            words = ["amber", "blue", "cyan", "denim", "ecru"]
            docs = [{"_id": str(i), "title": "", "text": " ".join(w for w in words for _ in range(rng.randint(0, 5))), "metadata": {}} for i in range(40)]
            (helper.root / "corpus.jsonl").write_text(fixtures._rows(docs))
            queries = [{"_id": "qd", "text": "amber", "metadata": {}}, {"_id": "qv", "text": "amber blue cyan", "metadata": {}}]
            (helper.root / "queries.jsonl").write_text(fixtures._rows(queries))
            target = "3" if sign == "positive" else "36"
            (helper.root / "qrels.tsv").write_text("query-id\tcorpus-id\tscore\nqd\t1\t1\nqv\t" + target + "\t1\n")
            corpus = (helper.root / "corpus.jsonl").read_bytes()
            helper.spec["source_provenance"]["archive_sha256"] = hashlib.sha256(corpus).hexdigest()
            helper.write_spec()
        packet = helper.capture()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "input").mkdir()
        source = root / "input" / "source.json"
        source.write_text(canonical(packet))
        project = ResearchProject(root / "project")
        project.create(source=source, goal="Synthetic final evaluation", budget_ref="fixture", max_tool_calls=3, method_id=staged.TOOL_ID)
        project.save_plan(request_id="plan", expected_state_version=project.status()["state_version"],
                          plan={"question": "Fixture?", "basis": "synthetic", "steps": "validation then final",
                                "expected_feedback": "validation recall20 delta"}, reason="fixture")
        data = {"schema_version": "retrieval-holdout-v1", "corpus_sha256": packet["assets"]["corpus"]["sha256"],
                "queries_jsonl": canonical({"_id": "final-q", "text": "SECRET_FINAL_QUERY fish", "metadata": {}}) + "\n",
                "qrels_tsv": "query-id\tcorpus-id\tscore\nfinal-q\tc\t2\n"}
        return project, packet, canonical(data).encode()

    def register(self, project, raw):
        version = project.status()["state_version"]
        record = holdout.register_holdout(project, request_id="holdout", expected_state_version=version, holdout=raw)
        return record, version

    def primary(self, project):
        return project.step(request_id="primary", expected_state_version=project.status()["state_version"])

    def freeze(self, project, action):
        version = project.status()["state_version"]
        return holdout.freeze_strategy(project, request_id="freeze", expected_state_version=version, primary_action_id=action["id"]), version

    def test_original_native_flow_private_bound_and_same_id(self):
        project, packet, raw = self.fixture()
        initial_budget = copy.deepcopy(project.status()["budget"])
        registration, version = self.register(project, raw)
        self.assertEqual(holdout.register_holdout(project, request_id="holdout", expected_state_version=version, holdout=raw), registration)
        with self.assertRaises(ResearchError):
            holdout.register_holdout(project, request_id="holdout", expected_state_version=version, holdout=raw + b" ")
        self.assertEqual(project.status()["budget"], initial_budget)
        with self.assertRaises(ResearchError):
            holdout.verify_holdout(project, project.status())
        for value in (canonical(project.status()), (project.root / "source.json").read_text(), canonical(ProjectController(project.root).selection_context())):
            self.assertNotIn("SECRET_FINAL_QUERY", value)
            self.assertNotIn("final-q", value)
        with patch.object(relevance, "retrieve", wraps=relevance.retrieve) as rank, patch.object(lexical, "metrics", wraps=lexical.metrics) as metric:
            action = self.primary(project)
            before = (rank.call_count, metric.call_count)
            frozen, freeze_version = self.freeze(project, action)
            self.assertEqual((rank.call_count, metric.call_count), before)
            self.assertEqual(frozen["validation_delta_recall20"], 0)
            self.assertEqual(frozen["selected_method"], "bm25")
            self.assertEqual(holdout.freeze_strategy(project, request_id="freeze", expected_state_version=freeze_version, primary_action_id=action["id"]), frozen)
            params = {"based_on_action_id": action["id"], "based_on_result_sha256": action["result_sha256"]}
            state = project.status()
            with patch.object(holdout, "_verified_private", side_effect=AssertionError("metadata hint cannot read private")):
                self.assertTrue(holdout.eligible_metadata(state, params))
            envelope = json.loads(project._artifact(action).read_bytes())
            original = envelope["tool_result"]
            self.assertTrue(holdout.eligible_project(project, state, original, params))
            with self.assertRaises(ResearchError):
                holdout.FINAL.execute_project(project.root, original, params)
            self.assertEqual((rank.call_count, metric.call_count), before)
            final = project.step(request_id="final", method_id=holdout.FINAL_TOOL_ID, parameters=params,
                                 expected_state_version=state["state_version"])
            self.assertEqual(final["status"], "completed")
            self.assertEqual((rank.call_count - before[0], metric.call_count - before[1]), (1, 1))
            result = json.loads(project._artifact(final).read_bytes())["tool_result"]
            holdout.validate_final_result(result)
            self.assertEqual(holdout.verify_holdout(project, project.status()), registration)
            self.assertEqual(result["result"]["usage"]["scoring_calls"], 1)
            self.assertEqual(result["result"]["summary"]["delta"]["recall@20"], 0)
            self.assertNotIn("SECRET_FINAL_QUERY", canonical(result))
            self.assertNotIn("final-q", canonical(result))
            self.assertEqual(project.step(request_id="final", method_id=holdout.FINAL_TOOL_ID, parameters=params)["id"], final["id"])
            self.assertEqual((rank.call_count - before[0], metric.call_count - before[1]), (1, 1))
            self.assertEqual(project.status()["budget"]["local_tool_calls_used"], 2)
            self.assertFalse(holdout.eligible_metadata(project.status(), params))
            changed = copy.deepcopy(result)
            changed["result"]["per_query"][0]["raw_qrels"] = "leak"
            with self.assertRaises(ResearchError):
                holdout.validate_final_result(changed)

    def test_overlap_missing_labels_wrong_corpus_and_post_primary_rejected(self):
        project, packet, raw = self.fixture()
        data = json.loads(raw)
        variations = []
        value = copy.deepcopy(data)
        value["queries_jsonl"] = canonical({"_id": "qv", "text": "private", "metadata": {}}) + "\n"
        value["qrels_tsv"] = "query-id\tcorpus-id\tscore\nqv\ta\t1\n"
        variations.append(value)
        value = copy.deepcopy(data)
        value["corpus_sha256"] = "0" * 64
        variations.append(value)
        value = copy.deepcopy(data)
        value["qrels_tsv"] = "query-id\tcorpus-id\tscore\n"
        variations.append(value)
        for value in variations:
            with self.subTest(value=value), self.assertRaises(ResearchError):
                self.register(project, canonical(value).encode())
        self.primary(project)
        with self.assertRaises(ResearchError):
            self.register(project, raw)

    def test_tampered_private_stops_final_and_changed_plan_blocks_freeze(self):
        project, _, raw = self.fixture()
        self.register(project, raw)
        action = self.primary(project)
        path = project.root / holdout.PRIVATE_DIR / holdout.PRIVATE_FILE
        path.write_bytes(raw + b" ")
        # Freeze intentionally reads metadata and public validation only.
        with patch.object(holdout, "_verified_private", side_effect=AssertionError("must not read private")):
            frozen, _ = self.freeze(project, action)
        params = {"based_on_action_id": action["id"], "based_on_result_sha256": action["result_sha256"]}
        with self.assertRaises(ResearchError) as error:
            project.step(request_id="final", method_id=holdout.FINAL_TOOL_ID, parameters=params,
                         expected_state_version=project.status()["state_version"])
        self.assertEqual(error.exception.code, "EVIDENCE_CHANGED")
        self.assertEqual(project.status()["budget"]["local_tool_calls_used"], 2)
        self.assertEqual(len(list((project.root / holdout.PRIVATE_DIR).glob("execution-*.json"))), 1)
        project2, _, raw2 = self.fixture()
        self.register(project2, raw2)
        action2 = self.primary(project2)
        project2.save_plan(request_id="revised", expected_state_version=project2.status()["state_version"],
                          plan={"question": "Changed?", "basis": "synthetic", "steps": "validation then final",
                                "expected_feedback": "validation recall20 delta"}, reason="fixture")
        with self.assertRaises(ResearchError):
            self.freeze(project2, action2)

    def test_crash_after_marker_retains_original_unknown_without_second_score(self):
        project, _, raw = self.fixture()
        self.register(project, raw)
        action = self.primary(project)
        frozen, _ = self.freeze(project, action)
        params = {"based_on_action_id": action["id"], "based_on_result_sha256": action["result_sha256"]}
        with patch.object(holdout, "_verified_private", side_effect=KeyboardInterrupt), \
             patch.object(lexical, "metrics", side_effect=AssertionError("no scoring")):
            with self.assertRaises(KeyboardInterrupt):
                project.step(request_id="final", method_id=holdout.FINAL_TOOL_ID, parameters=params,
                             expected_state_version=project.status()["state_version"])
            marker, = (project.root / holdout.PRIVATE_DIR).glob("execution-*.json")
            claim = json.loads(marker.read_bytes())
            self.assertEqual(claim["freeze_sha256"], frozen["record_sha256"])
            self.assertEqual(claim["source_snapshot_sha256"], project.status()["source_snapshot_sha256"])
            self.assertEqual(claim["request_id"], "final")
            reopened = ResearchProject(project.root)
            result = reopened.step(request_id="final", method_id=holdout.FINAL_TOOL_ID, parameters=params)
            self.assertIn(result["status"], ("running", "unknown"))
            with self.assertRaises(ResearchError):
                reopened.step(request_id="different", method_id=holdout.FINAL_TOOL_ID, parameters=params)
            self.assertEqual(len(list(marker.parent.glob("execution-*.json"))), 1)

    def test_strict_positive_and_negative_validation_deltas(self):
        for sign, method, calls in (("positive", "tfidf_cosine", 2), ("negative", "bm25", 1)):
            with self.subTest(sign=sign):
                project, _, raw = self.fixture(sign)
                self.register(project, raw)
                action = self.primary(project)
                frozen, _ = self.freeze(project, action)
                self.assertEqual(frozen["selected_method"], method)
                self.assertEqual(frozen["validation_delta_recall20"], 1 if sign == "positive" else -1)
                params = {"based_on_action_id": action["id"], "based_on_result_sha256": action["result_sha256"]}
                with patch.object(relevance, "retrieve", wraps=relevance.retrieve) as rank, \
                     patch.object(lexical, "metrics", wraps=lexical.metrics) as metric:
                    final = project.step(request_id="final", method_id=holdout.FINAL_TOOL_ID, parameters=params,
                                         expected_state_version=project.status()["state_version"])
                    result = json.loads(project._artifact(final).read_bytes())["tool_result"]
                    self.assertEqual((rank.call_count, metric.call_count), (calls, calls))
                    self.assertEqual(result["result"]["usage"]["ranking_calls"], calls)
                    self.assertEqual(result["result"]["usage"]["scoring_calls"], calls)
                    self.assertEqual(result["result"]["selected_method"], method)
                    holdout.validate_final_result(result)

    def test_existing_start_marker_prevents_second_computation(self):
        project, _, raw = self.fixture()
        self.register(project, raw)
        action = self.primary(project)
        self.freeze(project, action)
        params = {"based_on_action_id": action["id"], "based_on_result_sha256": action["result_sha256"]}
        original = json.loads(project._artifact(action).read_bytes())["tool_result"]
        def reenter(*args):
            with self.assertRaises(ResearchError) as error:
                holdout.FINAL.execute_project(project.root, original, params)
            self.assertEqual(error.exception.code, "EXECUTION_UNKNOWN")
            raise KeyboardInterrupt
        with patch.object(holdout, "_verified_private", side_effect=reenter), \
             patch.object(lexical, "metrics", side_effect=AssertionError("no score allowed")):
            with self.assertRaises(KeyboardInterrupt):
                project.step(request_id="final", method_id=holdout.FINAL_TOOL_ID, parameters=params,
                             expected_state_version=project.status()["state_version"])

    def test_public_projection_exposes_only_bounded_metadata(self):
        project, _, raw = self.fixture()
        self.assertIsNone(holdout.public_evaluation_context(project.status()))
        self.register(project, raw)
        with patch.object(holdout, "_verified_private", side_effect=AssertionError("no final reads")):
            value = holdout.public_evaluation_context(project.status())
            self.assertIsNone(value["freeze"])
            self.assertIsNone(value["final"])
            self.assertNotIn("final-q", canonical(value))
            self.assertNotIn("SECRET_FINAL_QUERY", canonical(value))
            bad = copy.deepcopy(value)
            bad["qrels"] = "exfiltration"
            with self.assertRaises(ResearchError):
                holdout.validate_public_evaluation_context(bad)
        action = self.primary(project)
        self.freeze(project, action)
        value = holdout.public_evaluation_context(project.status())
        self.assertEqual(value["freeze"]["primary_action_id"], action["id"])
        self.assertEqual(value["freeze"]["validation_delta_recall20"], 0)
        params = {"based_on_action_id": action["id"], "based_on_result_sha256": action["result_sha256"]}
        result = project.step(request_id="final", method_id=holdout.FINAL_TOOL_ID, parameters=params,
                              expected_state_version=project.status()["state_version"])
        value = holdout.public_evaluation_context(project.status())
        self.assertEqual(value["final"], {"status": "completed", "action_id": result["id"], "result_sha256": result["result_sha256"]})
        self.assertNotIn("final-q", canonical(value))

    def test_interruption_before_marker_never_dispatches_a_second_time(self):
        project, _, raw = self.fixture()
        self.register(project, raw)
        action = self.primary(project)
        self.freeze(project, action)
        params = {"based_on_action_id": action["id"], "based_on_result_sha256": action["result_sha256"]}
        actual_open = holdout.os.open
        def interrupted(path, flags, *args):
            if flags & holdout.os.O_EXCL:
                raise KeyboardInterrupt
            return actual_open(path, flags, *args)
        with patch.object(holdout.os, "open", side_effect=interrupted), \
             patch.object(lexical, "metrics", side_effect=AssertionError("no final scoring")):
            with self.assertRaises(KeyboardInterrupt):
                project.step(request_id="final", method_id=holdout.FINAL_TOOL_ID, parameters=params,
                             expected_state_version=project.status()["state_version"])
            self.assertFalse(list((project.root / holdout.PRIVATE_DIR).glob("execution-*.json")))
            replay = ResearchProject(project.root).step(request_id="final", method_id=holdout.FINAL_TOOL_ID, parameters=params)
            self.assertIn(replay["status"], ("running", "unknown"))
            with self.assertRaises(ResearchError):
                project.step(request_id="replacement", method_id=holdout.FINAL_TOOL_ID, parameters=params)
            self.assertEqual(project.status()["budget"]["local_tool_calls_reserved"], 1)

    def test_metadata_rejects_rehashed_nested_fields_and_bad_bindings(self):
        from autoresearch.contracts import fingerprint
        project, _, raw = self.fixture()
        self.assertIsNone(holdout.validate_metadata(project.status()))
        self.register(project, raw)
        action = self.primary(project)
        self.freeze(project, action)
        state = project.status()
        with patch.object(holdout, "_verified_private", side_effect=AssertionError("must not read private")):
            self.assertIsNotNone(holdout.validate_metadata(state))
        changes = []
        for field in ("request_id", "project_id", "run_id", "sha256", "corpus_sha256", "source_sha256",
                      "source_snapshot_sha256", "plan_sha256", "project_code_identity", "policy"):
            altered = copy.deepcopy(state)
            altered["private_evaluation"][field] = {"nested": "SECRET_FINAL_QUERY"}
            changes.append(altered)
        for field in ("bytes", "query_count", "plan_version", "state_version_before"):
            altered = copy.deepcopy(state)
            altered["private_evaluation"][field] = True
            changes.append(altered)
        altered = copy.deepcopy(state)
        altered["private_evaluation"]["request"]["nested"] = {"qrels": "secret"}
        changes.append(altered)
        for field in ("request_id", "project_id", "run_id", "holdout_record_sha256", "source_snapshot_sha256",
                      "plan_sha256", "project_code_identity", "primary_action_id", "primary_result_sha256",
                      "policy", "selected_method", "validation_delta_recall20"):
            altered = copy.deepcopy(state)
            altered["frozen_evaluation_strategy"][field] = ["SECRET_FINAL_QUERY"]
            changes.append(altered)
        altered = copy.deepcopy(state)
        altered["frozen_evaluation_strategy"]["request"]["expected_state_version"] = True
        changes.append(altered)
        altered = copy.deepcopy(state)
        altered["frozen_evaluation_strategy"]["request"]["nested"] = ["qrels"]
        changes.append(altered)
        altered = copy.deepcopy(state)
        del altered["private_evaluation"]
        with self.assertRaises(ResearchError) as error:
            holdout.validate_metadata(altered)
        self.assertEqual(error.exception.code, "EVIDENCE_CHANGED")
        for i, altered in enumerate(changes):
            record = altered["private_evaluation"]
            record["request_sha256"] = fingerprint(record["request"])
            record["record_sha256"] = fingerprint({k: v for k, v in record.items() if k != "record_sha256"})
            frozen = altered["frozen_evaluation_strategy"]
            # Make the attacker-controlled saved hashes internally consistent.
            if frozen["holdout_record_sha256"] == state["frozen_evaluation_strategy"]["holdout_record_sha256"]:
                frozen["holdout_record_sha256"] = record["record_sha256"]
            frozen["request_sha256"] = fingerprint(frozen["request"])
            frozen["record_sha256"] = fingerprint({k: v for k, v in frozen.items() if k != "record_sha256"})
            with self.subTest(case=i), self.assertRaises(ResearchError) as error:
                holdout.validate_metadata(altered)
            self.assertEqual(error.exception.code, "EVIDENCE_CHANGED")
