"""Captured metadata fixtures; no study execution, ranking, label scoring or solve."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_retrieval_adapter as citation_fixture
import test_relevance_retrieval_adapter as relevance_fixture
import test_scheduling_adapter as scheduling_fixture
from autoresearch import cpu_protocol_reader as reader
from autoresearch import retrieval_adapter, relevance_retrieval_adapter, scheduling_adapter
from autoresearch import retrieval_lexical, scheduling_kernel, source_evidence_adapter
from autoresearch.contracts import ResearchError, canonical, fingerprint


MODULES = (retrieval_adapter, relevance_retrieval_adapter, scheduling_adapter)


class CPUProtocolReaderTests(unittest.TestCase):
    def captured(self, module):
        fixture = (citation_fixture.RetrievalAdapterTests if module is retrieval_adapter else
                   relevance_fixture.RelevanceRetrievalAdapterTests if module is relevance_retrieval_adapter else
                   scheduling_fixture.SchedulingAdapterTests)()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        if module is scheduling_adapter:
            fixture.cases.extend([
                scheduling_fixture.case("dev-one", [(0, 1, 2, 1)], split="dev"),
                scheduling_fixture.case("dev-empty", [], split="dev"),
                scheduling_fixture.case("validation-two", [(0, 1, 2, 1), (1, 2, 3, 2)], split="validation"),
                scheduling_fixture.case("correctness-empty", [], split="correctness")])
            fixture.write_inputs()
        else:
            path = fixture.root / "queries.jsonl"
            path.write_text(path.read_text() + canonical({"_id": "unselected", "text": "Private input text not displayed",
                                                         "metadata": {"opaque": "Do not expose opaque rows"}}) + "\n")
            qrels = fixture.root / "qrels-train.tsv"
            qrels.write_text(qrels.read_text() + "unselected\ta\t1\n")
        packet = fixture.captured()  # Schema capture and original byte hashing only.
        project = SimpleNamespace(root=fixture.root / "project")
        project.root.mkdir()
        raw = canonical(packet).encode()
        (project.root / "source.json").write_bytes(raw)
        state = {"id": "project-protocol-fixture", "run_id": "run-protocol-fixture", "snapshot_ref": "a"*64,
                 "state_version": 0, "code_identity": "c"*64, "source_snapshot_sha256": packet["snapshot_sha256"],
                 "source_scope": deepcopy(packet["scope"]), "registration": {"method_id": module.TOOL_ID,
                    "source_sha256": hashlib.sha256(raw).hexdigest()}, "actions": [], "report": None,
                 "budget": {"local_tool_calls_used": 0, "fit_attempts_used": 0},
                 "supported_methods": [{"id": module.TOOL_ID, "version": module.ADAPTER_VERSION,
                    "scope": deepcopy(packet["scope"]), "evaluation_ref": reader._DESCRIPTORS[MODULES.index(module)].evaluation_ref}]}
        return project, state, packet

    def rewrite_packet(self, project, state, packet):
        packet["snapshot_sha256"] = fingerprint({key: value for key, value in packet.items() if key != "snapshot_sha256"})
        raw = canonical(packet).encode()
        (project.root / "source.json").write_bytes(raw)
        state["source_snapshot_sha256"] = packet["snapshot_sha256"]
        state["source_scope"] = deepcopy(packet["scope"])
        state["supported_methods"][0]["scope"] = deepcopy(packet["scope"])
        state["registration"]["source_sha256"] = hashlib.sha256(raw).hexdigest()

    def reject(self, function, *args, code=None):
        with self.assertRaises(ResearchError) as error:
            function(*args)
        if code is not None:
            self.assertEqual(error.exception.code, code)

    def test_all_three_families_are_compact_and_independent_of_actions_report_and_current_code(self):
        for module in MODULES:
            with self.subTest(method=module.TOOL_ID):
                project, state, packet = self.captured(module)
                state["report"] = {"stale": True}
                value = reader.read_fixed_protocol(project, state)
                self.assertEqual(value["schema_version"], "fixed-cpu-protocol-view-v1")
                self.assertEqual(set(value), {"schema_version", "binding", "adapter_version", "evaluation_ref", "source_spec_identity",
                    "declared_spec", "scalar_scope", "input_identities", "splits", "projection_notice"})
                self.assertEqual(set(value["binding"]), {"project_id", "run_id", "snapshot_ref", "state_version", "method_id",
                    "project_code_identity", "source_snapshot_sha256", "source_file_sha256"})
                self.assertEqual(value["binding"]["project_code_identity"], "c"*64)
                self.assertEqual(value["binding"]["source_file_sha256"], state["registration"]["source_sha256"])
                self.assertEqual(value["source_spec_identity"], {key: packet["spec_source"][key] for key in ("sha256", "bytes")})
                self.assertEqual(value["declared_spec"]["comparison"], module.COMPARISON)
                self.assertEqual(set(value["declared_spec"]), set(reader.SPEC_FIELDS))
                self.assertEqual(set(value["input_identities"]), set(module.FILES))
                self.assertTrue(all(set(item) == {"sha256", "bytes"} for item in value["input_identities"].values()))
                encoded = canonical(value)
                for forbidden in ('"bytes_base64"', '"query_splits"', '"missing_positive_document_ids"', '"metadata"',
                                  '"jobs":[', '"corpus":[' , "Private input text not displayed", "Do not expose opaque rows"):
                    self.assertNotIn(forbidden, encoded)
                self.assertLessEqual(len(encoded.encode()), 128*1024)

    def test_ir_split_identity_counts_original_order_and_full_source_count_are_distinct(self):
        for module in MODULES[:2]:
            project, state, packet = self.captured(module)
            value = reader.read_fixed_protocol(project, state)
            self.assertEqual(value["scalar_scope"]["query_count"], 4)
            self.assertEqual(sum(item["queries"] for item in value["splits"].values()), 3)
            self.assertEqual(value["splits"], {split: {"queries": len(ids), "query_ids_sha256": fingerprint(ids)}
                              for split, ids in packet["spec"]["query_splits"].items()})
            self.assertEqual(value["scalar_scope"]["qrels_semantics"], module.SEMANTICS)
            if module is relevance_retrieval_adapter:
                self.assertEqual(value["scalar_scope"]["missing_positive_document_count"], 1)
                self.assertEqual(value["scalar_scope"]["missing_positive_qrel_pairs"], 1)

    def test_scheduling_split_counts_include_empty_cases_without_solving(self):
        project, state, _ = self.captured(scheduling_adapter)
        value = reader.read_fixed_protocol(project, state)
        self.assertEqual(value["splits"], {"test": {"cases": 1, "jobs": 3}, "dev": {"cases": 2, "jobs": 1},
            "validation": {"cases": 1, "jobs": 2}, "correctness": {"cases": 1, "jobs": 0}})
        self.assertEqual(value["scalar_scope"]["case_count"], 5)
        self.assertEqual(value["scalar_scope"]["job_count"], 6)

    def test_split_identity_hash_keeps_original_non_sorted_query_order(self):
        for module in MODULES[:2]:
            project, state, packet = self.captured(module)
            packet["spec"]["query_splits"]["dev"] = ["unselected", "qd"]
            packet["spec_source"] = module._asset("spec.json", canonical(packet["spec"]).encode())
            self.rewrite_packet(project, state, packet)
            value = reader.read_fixed_protocol(project, state)
            self.assertEqual(value["splits"]["dev"], {"queries": 2, "query_ids_sha256": fingerprint(["unselected", "qd"])})
            self.assertNotEqual(value["splits"]["dev"]["query_ids_sha256"], fingerprint(["qd", "unselected"]))

    def test_unknown_and_followup_registration_reject_before_any_file_read(self):
        project, state, _ = self.captured(retrieval_adapter)
        for method in ("research.unsupported", retrieval_adapter.AUDIT_TOOL_ID, relevance_retrieval_adapter.AUDIT_TOOL_ID,
                       scheduling_adapter.AUDIT_TOOL_ID):
            state["registration"]["method_id"] = method
            with patch.object(source_evidence_adapter, "_read_file", side_effect=AssertionError("No file I/O")):
                self.reject(reader.read_fixed_protocol, project, state, code="ARTIFACT_NOT_AVAILABLE")

    def test_supported_method_version_scope_and_evaluation_are_bound_before_read(self):
        project, state, _ = self.captured(relevance_retrieval_adapter)
        valid = deepcopy(state["supported_methods"])
        for key, wrong in (("version", 1), ("scope", {}), ("evaluation_ref", "citation-retrieval-fixed-pair-v1")):
            state["supported_methods"] = deepcopy(valid)
            state["supported_methods"][0][key] = wrong
            with patch.object(source_evidence_adapter, "_read_file", side_effect=AssertionError("No file I/O")):
                self.reject(reader.read_fixed_protocol, project, state)
        state["supported_methods"] = valid + deepcopy(valid)
        self.reject(reader.read_fixed_protocol, project, state)

    def test_source_hash_snapshot_scope_numeric_type_and_wrong_family_reject(self):
        project, state, packet = self.captured(retrieval_adapter)
        raw = (project.root / "source.json").read_bytes()
        (project.root / "source.json").write_bytes(raw + b" ")
        self.reject(reader.read_fixed_protocol, project, state)
        (project.root / "source.json").write_bytes(raw)
        state["source_snapshot_sha256"] = "0"*64
        self.reject(reader.read_fixed_protocol, project, state)
        self.rewrite_packet(project, state, packet)
        packet["scope"]["document_count"] = True
        self.rewrite_packet(project, state, packet)
        self.reject(reader.read_fixed_protocol, project, state)
        project, state, _ = self.captured(retrieval_adapter)
        state["registration"]["method_id"] = relevance_retrieval_adapter.TOOL_ID
        state["supported_methods"][0]["id"] = relevance_retrieval_adapter.TOOL_ID
        state["supported_methods"][0]["evaluation_ref"] = "relevance-retrieval-fixed-pair-v1"
        self.reject(reader.read_fixed_protocol, project, state)

    def test_duplicate_original_query_ids_rejected_after_all_outer_hashes_rebound(self):
        project, state, packet = self.captured(relevance_retrieval_adapter)
        original = relevance_retrieval_adapter._asset_raw(packet["assets"]["queries"], "queries.jsonl", 3145728)
        changed = original + original.splitlines(keepends=True)[0]
        packet["assets"]["queries"] = relevance_retrieval_adapter._asset("queries.jsonl", changed)
        self.rewrite_packet(project, state, packet)
        self.reject(reader.read_fixed_protocol, project, state)

    def test_duplicate_and_nonfinite_json_and_missing_input_are_stable_errors(self):
        project, state, _ = self.captured(retrieval_adapter)
        path = project.root / "source.json"
        for raw in (b'{"duplicate":1,"duplicate":2}', b'{"invalid":NaN}', b'\xff'):
            path.write_bytes(raw)
            state["registration"]["source_sha256"] = hashlib.sha256(raw).hexdigest()
            self.reject(reader.read_fixed_protocol, project, state)
        path.unlink()
        self.reject(reader.read_fixed_protocol, project, state, code="ARTIFACT_NOT_FOUND")

    def test_source_and_response_caps_and_symlink_are_enforced(self):
        project, state, _ = self.captured(relevance_retrieval_adapter)
        with patch.dict(relevance_retrieval_adapter.LIMITS, {"packet_bytes": 32}):
            self.reject(reader.read_fixed_protocol, project, state, code="SOURCE_TOO_LARGE")
        with patch.object(reader, "MAX_RESPONSE_BYTES", 32):
            self.reject(reader.read_fixed_protocol, project, state, code="READER_TOO_LARGE")
        path = project.root / "source.json"
        original = project.root / "original.json"
        path.rename(original)
        path.symlink_to(original)
        self.reject(reader.read_fixed_protocol, project, state, code="UNSAFE_PATH")

    def test_validation_is_one_pass_and_never_mutates_or_calls_compute_cost_or_new_project(self):
        for module in MODULES:
            project, state, _ = self.captured(module)
            before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in project.root.rglob("*") if path.is_file()}
            old_state = deepcopy(state)
            with ExitStack() as guards:
                for adapter in MODULES:
                    for name in ("execute", "capture_source", "_paired"):
                        guards.enter_context(patch.object(adapter, name, side_effect=AssertionError("No study computation")))
                    guards.enter_context(patch.object(adapter.AUDIT, "execute_saved", side_effect=AssertionError("No new action")))
                for name in ("tokens", "build_index", "retrieve", "metrics"):
                    guards.enter_context(patch.object(retrieval_lexical, name, side_effect=AssertionError("No retrieval compute")))
                guards.enter_context(patch.object(relevance_retrieval_adapter, "retrieve", side_effect=AssertionError("No retrieval compute")))
                for name in ("schedule", "jobs_for", "verify_schedule", "brute_force"):
                    guards.enter_context(patch.object(scheduling_kernel, name, side_effect=AssertionError("No job computation")))
                guards.enter_context(patch.object(source_evidence_adapter, "execute", side_effect=AssertionError("No source extraction")))
                for name in ("create", "upgrade", "step"):
                    guards.enter_context(patch("autoresearch.research_project.ResearchProject." + name, side_effect=AssertionError("No mutation")))
                guards.enter_context(patch("sklearn.linear_model.Ridge.fit", side_effect=AssertionError("No fitting")))
                guards.enter_context(patch("sklearn.preprocessing.StandardScaler.fit", side_effect=AssertionError("No fitting")))
                guards.enter_context(patch("autoresearch.model_client.ChatClient.complete", side_effect=AssertionError("No model/API send")))
                guards.enter_context(patch("autoresearch.local_ollama.LocalHTTP.request", side_effect=AssertionError("No model/API send")))
                checked = guards.enter_context(patch.object(module, "_checked", wraps=module._checked))
                reader.read_fixed_protocol(project, state)
                self.assertEqual(checked.call_count, 1)
            self.assertEqual(old_state, state)
            self.assertEqual(before, {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in project.root.rglob("*") if path.is_file()})

    def test_scalar_projection_preserves_valid_json_scalar_types_and_rejects_infinite(self):
        self.assertEqual(reader._scalar_scope({"s": "v", "i": 0, "b": False, "n": None, "f": .5, "raw": [1], "nested": {}}),
                         {"s": "v", "i": 0, "b": False, "n": None, "f": .5})
        self.reject(reader._scalar_scope, {"invalid": float("inf")})


if __name__ == "__main__":
    unittest.main()
