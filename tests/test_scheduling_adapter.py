"""Small synthetic native-scheduling fixtures; never the twelve full workloads."""
from copy import deepcopy
import hashlib
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import scheduling_adapter as adapter, scheduling_kernel as kernel
from autoresearch.contracts import ResearchError, canonical, fingerprint


def case(case_id, jobs, split="test", seed=None):
    return {"case_id": case_id, "split": split, "seed": seed, "jobs_sha256": kernel.value_hash(jobs),
            "jobs": [{"start": a, "end": b, "weight": w, "id": i} for a, b, w, i in jobs]}


def specification():
    return {"schema_version": "weighted-interval-spec-v1", "dataset_label": "Synthetic engineering fixture only",
            "source_url": "urn:engineering:weighted-interval", "attribution": "Explicit fixture author",
            "license_notes": "Author-created engineering inputs, not external scientific observations",
            "source_provenance": {"origin_script_sha256": "a"*64, "origin_protocol_sha256": "b"*64,
                "origin_manifest_sha256": "c"*64, "generator": "explicit-engineering-fixture-v1", "workload_kind": "synthetic_engineering"},
            "files": deepcopy(adapter.FILES), "comparison": deepcopy(adapter.COMPARISON), "limits": deepcopy(adapter.LIMITS)}


def reseal(packet):
    packet["snapshot_sha256"] = fingerprint({k: v for k, v in packet.items() if k != "snapshot_sha256"})
    return packet


class SchedulingAdapterTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.spec = specification()
        self.cases = [case("tiny-test", [(0, 2, 3, 5), (2, 4, 4, 1), (0, 4, 6, 9)])]
        self.write_inputs()

    def write_inputs(self):
        (self.root/"spec.json").write_text(canonical(self.spec), encoding="utf-8")
        (self.root/"jobs.json").write_text(canonical({"schema_version": "weighted-interval-jobs-v1", "cases": self.cases}), encoding="utf-8")
        (self.root/"license.md").write_text("Synthetic engineering input notice; no scientific assertion.\n", encoding="utf-8")

    def captured(self):
        return adapter.capture_source(self.root)

    def result(self):
        return adapter.execute(self.captured())

    def denied(self, function, *args, **kwargs):
        with self.assertRaises(ResearchError):
            function(*args, **kwargs)

    def test_complete_packet_and_original_bytes_roundtrip_without_writes(self):
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir()}
        packet = self.captured()
        self.assertEqual(packet["schema_version"], "cpu-research-source-v1")
        self.assertEqual(packet["task_kind"], "weighted_interval")
        self.assertEqual(adapter.load_source(canonical(packet).encode()), packet)
        self.assertEqual(packet["scope"]["case_count"], 1)
        self.assertEqual(packet["scope"]["job_count"], 3)
        self.assertEqual(set(packet["assets"]), {"jobs", "license"})
        self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir()})

    def test_primary_retains_all_actual_runs_schedules_counts_and_zero_model_fit(self):
        result = self.result()
        self.assertEqual((result["new_fits"], result["model_calls"], result["scientific_validation"]), (0, 0, False))
        body = result["result"]
        self.assertEqual(body["usage"]["solver_calls"], 6)
        self.assertEqual(body["usage"]["naive_pair_evaluations"], 9)
        self.assertEqual(body["usage"]["bruteforce_calls"], 1)
        records = body["cases"][0]["runs"]
        self.assertEqual([r["method"] for r in records], [kernel.METHODS[0], kernel.METHODS[1], kernel.METHODS[1], kernel.METHODS[0], kernel.METHODS[0], kernel.METHODS[1]])
        self.assertEqual([r["repeat"] for r in records], [0, 0, 1, 1, 2, 2])
        self.assertTrue(all(r["objective"] == 7 and r["schedule"] == [5, 1] for r in records))
        self.assertTrue(all(r["seconds"] >= 0 for r in records))
        self.assertTrue(adapter.AUDIT.eligible(result))
        self.assertEqual(adapter.next_decision(result)["next_action"]["method_id"], adapter.AUDIT_TOOL_ID)
        self.assertEqual(adapter.next_decision(result)["project_status"], "active")

    def test_echo_spec_numeric_type_cannot_differ_from_original_spec(self):
        packet = self.captured()
        packet["spec"]["comparison"]["test_repetitions"] = 3.0
        self.denied(adapter.load_source, canonical(reseal(packet)).encode())

    def test_overflowed_json_float_is_classified_rejection_for_capture_and_load(self):
        packet_raw = canonical(self.captured()).encode()
        invalid = canonical(self.spec).replace('"test_repetitions":3', '"test_repetitions":1e309')
        (self.root/"spec.json").write_text(invalid, encoding="utf-8")
        self.denied(self.captured)
        self.denied(adapter.load_source, packet_raw.replace(b'"test_repetitions":3', b'"test_repetitions":1e309'))

    def test_empty_adjacent_overlapping_zero_and_negative_weight_semantics(self):
        examples = [([], 0, []), ([(0, 1, 1, 0), (1, 2, 2, 1)], 3, [0, 1]),
                    ([(0, 2, 2, 0), (0, 2, 3, 1)], 3, [1]),
                    ([(0, 1, 0, 0), (0, 1, 0, 1)], 0, []),
                    ([(-3, -1, -5, 0), (-1, 2, 7, 1)], 7, [1]),
                    ([(0, 1, -1, 3)], 0, [])]
        for jobs, objective, chosen in examples:
            for method in kernel.METHODS:
                result = kernel.schedule(jobs, method)
                self.assertEqual((result["objective"], result["schedule"]), (objective, chosen))
                self.assertTrue(kernel.verify_schedule(jobs, result))
                self.assertEqual(result["operations"]["reconstruction_steps"], kernel.saved_reconstruction_steps(jobs, chosen))
                self.assertEqual(kernel.brute_force(jobs), objective)

    def test_numerical_id_sort_and_skip_on_equal_objective_preserved(self):
        jobs = [(0, 2, 3, 10), (0, 2, 3, 2), (2, 4, 4, 8)]
        for source in (jobs, list(reversed(jobs))):
            for method in kernel.METHODS:
                result = kernel.schedule(source, method)
                self.assertEqual(result["schedule"], [2, 8])
                self.assertEqual(result["objective"], 7)

    def test_small_seeded_cases_against_exhaustive_optimum_and_backtracking_count(self):
        rng = random.Random(777)
        for index in range(16):
            jobs = []
            for i in range(8):
                start = rng.randrange(-5, 20)
                jobs.append((start, start+rng.randrange(1, 7), rng.randrange(-2, 11), i))
            optimum = kernel.brute_force(jobs)
            arms = [kernel.schedule(jobs, method) for method in kernel.METHODS]
            self.assertTrue(all(r["objective"] == optimum for r in arms))
            self.assertEqual(arms[0]["schedule"], arms[1]["schedule"])
            for result in arms:
                kernel.verify_schedule(jobs, result)
                self.assertEqual(result["operations"]["reconstruction_steps"], kernel.saved_reconstruction_steps(jobs, result["schedule"]))

    def test_non_test_case_single_pair_and_exhaustive_budget(self):
        self.cases = [case("empty", [], "correctness"), case("dev", [(0, 1, 4, 0)], "dev")]
        self.write_inputs()
        result = self.result()["result"]
        self.assertEqual(result["usage"]["solver_calls"], 4)
        self.assertEqual(result["usage"]["bruteforce_subsets"], 3)
        self.assertTrue(all(len(c["runs"]) == 2 for c in result["cases"]))

    def test_saved_audit_never_resolves_generates_or_times(self):
        original = self.result()
        params = {"based_on_action_id": "action-fixed", "based_on_result_sha256": "d"*64}
        with patch.object(kernel, "schedule", side_effect=AssertionError("No solving")), \
             patch.object(kernel, "brute_force", side_effect=AssertionError("No exhaustive solving")), \
             patch.object(kernel, "jobs_for", side_effect=AssertionError("No generation")), \
             patch.object(adapter.time, "perf_counter", side_effect=AssertionError("No timing")):
            self.assertTrue(adapter.AUDIT.eligible(original))
            audit = adapter.AUDIT.execute_saved(original, params)
        self.assertEqual(audit["result"]["predecessor"], params)
        self.assertEqual(audit["result"]["usage"]["solver_calls"], 0)
        self.assertEqual(audit["result"]["usage"]["new_timing_calls"], 0)
        self.assertEqual(audit["result"]["summary"], original["result"]["paired_summary"])
        self.assertEqual(adapter.AUDIT.next_decision(audit)["project_status"], "waiting")
        self.assertEqual(adapter.AUDIT.code_identity(), adapter.code_identity())

    def test_audit_rejects_changed_jobs_schedule_objective_repeats_ops_and_source(self):
        original = self.result()
        params = {"based_on_action_id": "saved-action", "based_on_result_sha256": "a"*64}
        mutations = [lambda v: v["result"]["cases"][0]["jobs"][0].update(weight=4),
                     lambda v: v["result"]["cases"][0]["runs"][0].update(schedule=[9]),
                     lambda v: v["result"]["cases"][0]["runs"][0].update(objective=8),
                     lambda v: v["result"]["cases"][0]["runs"].pop(),
                     lambda v: v["result"]["cases"][0]["runs"][0].update(repeat=1),
                     lambda v: v["result"]["cases"][0]["runs"][0]["operations"].update(reconstruction_steps=0),
                     lambda v: v["result"]["usage"].update(solver_calls=5),
                     lambda v: v["result"]["scope"]["input_identities"]["jobs"].update(sha256="f"*64),
                     lambda v: v["result"].update(source_snapshot_sha256="e"*64)]
        for mutate in mutations:
            modified = deepcopy(original)
            mutate(modified)
            self.assertFalse(adapter.AUDIT.eligible(modified))
            self.denied(adapter.AUDIT.execute_saved, modified, params)

    def test_audit_preserves_tied_and_adverse_cases(self):
        clock = iter(i/4 for i in range(100))
        with patch.object(adapter.time, "perf_counter", side_effect=lambda: next(clock)):
            original = self.result()
        self.assertEqual(original["result"]["paired_summary"]["by_split"]["test"]["tie"], 1)
        audit = adapter.AUDIT.execute_saved(original, {"based_on_action_id": "a", "based_on_result_sha256": "b"*64})
        self.assertEqual(audit["result"]["summary"]["adverse_cases"], ["tiny-test"])

    def test_predecessor_and_runtime_parameter_contracts_are_closed(self):
        result = self.result()
        self.denied(adapter.execute, self.captured(), dimension="arbitrary")
        self.denied(adapter.AUDIT.execute_saved, result, {"based_on_action_id": "a", "based_on_result_sha256": "x"})
        self.denied(adapter.AUDIT.execute_saved, result, {"based_on_action_id": "a", "based_on_result_sha256": "b"*64, "command": "anything"})

    def test_no_top_level_extra_code_fields_or_raised_limits(self):
        for mutate in [lambda s: s.update(command="python"), lambda s: s["files"].update(jobs="../jobs.json"),
                       lambda s: s["comparison"].update(test_repetitions=4), lambda s: s["limits"].update(max_cases=100),
                       lambda s: s["source_provenance"].update(generator="python:eval")]:
            self.spec = specification()
            mutate(self.spec)
            self.write_inputs()
            self.denied(self.captured)

    def test_duplicate_case_job_ids_zero_duration_boolean_and_float_rejected(self):
        invalid_jobs = [[{"id": 0, "start": 0, "end": 1, "weight": 2}]*2,
                        [{"id": 0, "start": 0, "end": 0, "weight": 1}],
                        [{"id": True, "start": 0, "end": 1, "weight": 1}],
                        [{"id": 0, "start": 0.0, "end": 1, "weight": 1}],
                        [{"id": 4096, "start": 0, "end": 1, "weight": 1}]]
        for jobs in invalid_jobs:
            self.cases = [case("invalid", [])]
            self.cases[0]["jobs"] = jobs
            self.write_inputs()
            self.denied(self.captured)
        self.cases = [case("same", []), case("same", [])]
        self.write_inputs()
        self.denied(self.captured)

    def test_token_snapshot_asset_and_derived_scope_tampering_rejected(self):
        packet = self.captured()
        for field in ("snapshot", "asset", "scope", "parsed_spec"):
            value = deepcopy(packet)
            if field == "snapshot":
                value["snapshot_sha256"] = "0"*64
            elif field == "asset":
                value["assets"]["jobs"]["sha256"] = "0"*64
                reseal(value)
            elif field == "scope":
                value["scope"]["case_count"] = True
                reseal(value)
            else:
                value["spec"]["dataset_label"] = "Changed"
                reseal(value)
            self.denied(adapter.load_source, canonical(value).encode())

    def test_hash_and_raw_json_integrity_rejects_nonfinite_duplicate_and_bad_utf8(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'\xff'):
            self.denied(adapter.load_source, raw)
        (self.root/"license.md").write_bytes(b'\xff')
        self.denied(self.captured)

    def test_capture_rejects_symlink_and_asset_byte_limit_before_decode(self):
        raw = (self.root/"jobs.json").read_bytes()
        (self.root/"jobs.json").unlink()
        (self.root/"other.json").write_bytes(raw)
        (self.root/"jobs.json").symlink_to(self.root/"other.json")
        self.denied(self.captured)
        (self.root/"jobs.json").unlink()
        (self.root/"jobs.json").write_bytes(raw)
        packet = self.captured()
        packet["assets"]["jobs"]["bytes"] = adapter.LIMITS["jobs_bytes"]+1
        reseal(packet)
        self.denied(adapter.load_source, canonical(packet).encode())

    def test_aggregate_naive_cost_and_total_jobs_rejected_before_any_solve(self):
        jobs = [(i, i+1, 1, i) for i in range(4096)]
        for count, split in ((6, "test"), (7, "correctness")):
            self.cases = [case("large-"+str(i), jobs, split) for i in range(count)]
            self.write_inputs()
            with patch.object(kernel, "schedule", side_effect=AssertionError("No solve before workload preflight")):
                self.denied(self.captured)

    def test_saved_feasibility_cannot_hide_omitted_or_reordered_selected_ids(self):
        original = self.result()
        modified = deepcopy(original)
        run = modified["result"]["cases"][0]["runs"][0]
        run["schedule"] = list(reversed(run["schedule"]))
        run["schedule_sha256"] = kernel.value_hash(run["schedule"])
        self.assertFalse(adapter.AUDIT.eligible(modified))

    def test_large_bruteforce_call_is_forbidden_and_generator_is_host_bounded(self):
        with self.assertRaises(ValueError):
            kernel.brute_force([(i, i+1, 1, i) for i in range(13)])
        with self.assertRaises(ValueError):
            kernel.jobs_for(True, 12)
        self.assertEqual(kernel.jobs_for(701, 5), kernel.jobs_for(701, 5))
        self.assertEqual([job[3] for job in kernel.jobs_for(701, 5)], list(range(5)))


if __name__ == "__main__":
    unittest.main()
