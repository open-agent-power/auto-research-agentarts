"""Hand-authored stored receipts only; no generated workloads or solver calls."""
import ast
import base64
from collections import Counter
import copy
import hashlib
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "verify_scheduling_policy_transfer.py"
ORIGINAL = ROOT / "work" / "native-cpu-source-8e8a206" / "scripts" / "verify_native_cpu_cases.py"
spec = importlib.util.spec_from_file_location("saved_policy_verifier", MODULE)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class SavedPolicyVerifierTests(unittest.TestCase):
    def setUp(self):
        # Hand-authored 3-row record; no producer or oracle was invoked.
        self.jobs = [[0, 2, 5, 0], [1, 3, 4, 1], [3, 4, 2, 2]]
        self.returned = {"objective": 7, "schedule": [0, 2], "full_scan_comparisons": 3,
                         "operations": {"dp_steps": 3, "full_scan_comparisons": 3,
                                        "bisect_calls": 0, "bisect_internal_comparisons": None,
                                        "reconstruction_steps": 3}}

    def test_oracle_source_is_exact_original_without_executing_it(self):
        current = MODULE.read_text()
        def segment(text):
            fn = next(node for node in ast.parse(text).body
                      if isinstance(node, ast.FunctionDef) and node.name == "fenwick_optimum")
            return ast.get_source_segment(text, fn)
        self.assertEqual(verifier.ORACLE_SOURCE_SHA256,
                         "ed8da57ef6eca1061e513fc328e2c5c95084ef599099ca401808fc841bd504a9")
        self.assertEqual(hashlib.sha256(segment(current).encode()).hexdigest(), verifier.ORACLE_SOURCE_SHA256)
        if ORIGINAL.is_file():
            self.assertEqual(hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(), verifier.ORIGINAL_VERIFIER_SHA256)
            self.assertEqual(segment(current), segment(ORIGINAL.read_text()))

    def test_saved_schedule_validation_does_not_call_oracle(self):
        with patch.object(verifier, "fenwick_optimum", side_effect=AssertionError("no oracle")):
            verifier._verify_jobs(self.jobs, 3, verifier._fingerprint(self.jobs))
            self.assertEqual(verifier._verify_saved_run(self.jobs, self.returned, "quadratic_scan_dp"), (7, [0, 2]))

    def test_rejects_corrupt_schedule_identity_feasibility_and_counts(self):
        variants = []
        for field, value in (("schedule", [0, 0]), ("schedule", [0, 1]), ("schedule", [2, 0]),
                             ("schedule", [99]), ("objective", 8), ("full_scan_comparisons", 0)):
            record = copy.deepcopy(self.returned)
            record[field] = value
            variants.append(record)
        record = copy.deepcopy(self.returned)
        record["operations"]["reconstruction_steps"] = 2
        variants.append(record)
        with patch.object(verifier, "fenwick_optimum", side_effect=AssertionError("no oracle")):
            for record in variants:
                with self.subTest(record=record), self.assertRaises(verifier.SavedVerificationError):
                    verifier._verify_saved_run(self.jobs, record, "quadratic_scan_dp")
            with self.assertRaises(verifier.SavedVerificationError):
                verifier._verify_jobs(self.jobs, 3, "0" * 64)

    def test_timing_status_preserves_invalid_without_guessing(self):
        def receipt(status, raw, elapsed):
            return {"returned": self.returned, "timing_status": status, "elapsed_raw": raw, "elapsed_ns": elapsed}
        self.assertEqual(verifier._saved_elapsed(receipt("ok", 23, 23)), 23)
        for status, raw in (("zero", 0), ("negative", -1), ("nonfinite", "NaN"), ("nonfinite", "Infinity")):
            self.assertIsNone(verifier._saved_elapsed(receipt(status, raw, None)))
        for item in (receipt("ok", 0, 0), receipt("zero", 0, 1), receipt("nonfinite", "-0", None)):
            with self.subTest(item=item), self.assertRaises(verifier.SavedVerificationError):
                verifier._saved_elapsed(item)

    def test_invalid_warmup_or_control_timing_makes_case_uninterpretable(self):
        times = {"fixed_binary": [10, 12], "fixed_scan": [9, 11], "threshold32": [8, 10]}
        _, ratio = verifier._case_timing_medians(times, [])
        self.assertEqual(ratio, 9 / 11)
        _, ratio = verifier._case_timing_medians(times, ["bad-warmup"])
        self.assertIsNone(ratio)
        times["fixed_scan"][1] = None
        _, ratio = verifier._case_timing_medians(times, [])
        self.assertIsNone(ratio)

    def test_summary_retains_every_fake_case_and_does_not_drop_bad_clock(self):
        # Descriptors and made-up saved durations only: no job arrays are made.
        cases = {case_id: {"kind": kind} for case_id, kind, _, _ in verifier._expected_cases()}
        observations = {case_id: {"timed": {"fixed_binary": [10] * 12, "fixed_scan": [11] * 12,
                                                   "threshold32": [8] * 12}, "invalid_warmups": []}
                        for case_id, kind, _, _ in verifier._expected_cases() if kind == "performance"}
        with patch.object(verifier, "fenwick_optimum", side_effect=AssertionError("no oracle")):
            summary = verifier._summarize_saved(cases, observations)
            self.assertEqual(len(summary["performance_cases"]), 27)
            self.assertEqual(summary["primary_case_count"], 12)
            self.assertEqual(summary["primary_policy_over_binary"], 0.8)
            observations["perf-n16-seed601"]["timed"]["fixed_scan"][0] = None
            summary = verifier._summarize_saved(cases, observations)
            self.assertFalse(summary["primary_timing_interpretable"])
            self.assertIsNone(summary["primary_policy_over_binary"])
            self.assertEqual(len(summary["performance_cases"]), 27)
            self.assertEqual(summary["performance_cases"][0]["outcome"], "uninterpretable")

    def test_saved_event_chain_requires_a_unique_reservation_and_exact_receipt(self):
        claim = {"study_id": "hand-authored-test"}
        claim_sha = verifier._fingerprint(claim)
        reserved = {"ordinal": 1, "previous_sha256": claim_sha, "event": "reserved",
                    "op_id": "one", "operation": "oracle", "spec": {"case_id": "fake"},
                    "reservation_sha256": None, "result": None, "result_sha256": None,
                    "boot_id": "fake-boot", "monotonic_ns": 101}
        reserved_sha = verifier._fingerprint(reserved)
        value = {"objective": 7}
        done = {"ordinal": 2, "previous_sha256": reserved_sha, "event": "completed",
                "op_id": "one", "operation": "oracle", "spec": {"case_id": "fake"},
                "reservation_sha256": reserved_sha, "result": value,
                "result_sha256": verifier._fingerprint(value), "boot_id": "fake-boot", "monotonic_ns": 102}
        events = [{"event": reserved, "sha256": reserved_sha},
                  {"event": done, "sha256": verifier._fingerprint(done)}]
        with patch.object(verifier, "fenwick_optimum", side_effect=AssertionError("no oracle")):
            self.assertEqual(len(verifier._verify_event_chain(claim, claim_sha, events)), 1)
            with self.assertRaises(verifier.SavedVerificationError):
                verifier._verify_event_chain(claim, claim_sha, events[:1])
            bad = copy.deepcopy(events)
            bad[1]["event"]["reservation_sha256"] = "0" * 64
            bad[1]["sha256"] = verifier._fingerprint(bad[1]["event"])
            with self.assertRaises(verifier.SavedVerificationError):
                verifier._verify_event_chain(claim, claim_sha, bad)
            for key, replacement in (("monotonic_ns", 100), ("monotonic_ns", True), ("boot_id", "other")):
                bad = copy.deepcopy(events)
                bad[1]["event"][key] = replacement
                bad[1]["sha256"] = verifier._fingerprint(bad[1]["event"])
                with self.assertRaises(verifier.SavedVerificationError):
                    verifier._verify_event_chain(claim, claim_sha, bad)

    def test_fixed_call_plan_has_balanced_order_and_exact_budget_without_jobs(self):
        cases = {case_id: {"jobs_sha256": "a" * 64}
                 for case_id, _, _, _ in verifier._expected_cases()}
        with patch.object(verifier, "fenwick_optimum", side_effect=AssertionError("no oracle")):
            operations = list(verifier._expected_operations(cases))
        counts = Counter(kind for _, kind, _ in operations)
        self.assertEqual(counts, {"generate": 29, "oracle": 29, "correctness": 6,
                                  "bruteforce": 2, "warmup": 162, "timed": 972})
        self.assertEqual(len(operations), 1200)
        self.assertTrue(all(kind == "generate" for _, kind, _ in operations[:29]))
        scan_cost = sum(spec["n"] * (spec["n"] - 1) // 2
                        for _, kind, spec in operations
                        if kind in ("warmup", "timed", "correctness")
                        and verifier._fixed_method(spec["arm"], spec["n"]) == "quadratic_scan_dp")
        self.assertEqual(scan_cost, 6080234)
        exhaustive_specs = [spec for _, kind, spec in operations if kind == "bruteforce"]
        self.assertEqual([spec["n"] for spec in exhaustive_specs], [8, 12])
        self.assertEqual(sum(verifier._saved_exhaustive_charge(spec) for spec in exhaustive_specs), 4352)
        self.assertEqual(verifier.EXPECTED_LIMITS["exhaustive_subsets"], 4352)
        for bad_n in (-1, 13, True, None):
            with self.assertRaises(verifier.SavedVerificationError):
                verifier._saved_exhaustive_charge({"n": bad_n})
        for left in verifier.ARMS:
            for right in verifier.ARMS:
                if left != right:
                    self.assertEqual(sum(p.index(left) < p.index(right) for p in verifier.PERMUTATIONS), 3)

    def test_review_bytes_reject_duplicate_keys_even_with_correct_raw_hash(self):
        raw = b'{"status":"approved","status":"forged"}'
        wrapper = {"raw_base64": base64.b64encode(raw).decode("ascii"),
                   "raw_sha256": hashlib.sha256(raw).hexdigest()}
        with patch.object(verifier, "fenwick_optimum", side_effect=AssertionError("no oracle")):
            with self.assertRaises(verifier.SavedVerificationError):
                verifier._review_document(wrapper)
            with self.assertRaises(verifier.SavedVerificationError):
                verifier._strict_json(b'{"duration":1e999}')

    def test_threshold_boundary_preserves_both_fixed_controls(self):
        self.assertEqual(verifier._fixed_method("threshold32", 32), "quadratic_scan_dp")
        self.assertEqual(verifier._fixed_method("threshold32", 33), "binary_search_dp")
        self.assertEqual(verifier._fixed_method("fixed_binary", 2), "binary_search_dp")
        self.assertEqual(verifier._fixed_method("fixed_scan", 512), "quadratic_scan_dp")

    def test_recorded_phase_clocks_are_checked_without_reading_a_clock(self):
        claim_sha, anchor, manifest_sha, review_sha = ("a" * 64, "b" * 64, "c" * 64, "d" * 64)
        generation = {"schema_version": "bounded-study-generation-v1", "study_id": verifier.STUDY_ID,
                      "boot_id": "fake-boot", "started_monotonic_ns": 1000,
                      "deadline_monotonic_ns": 120_000_001_000, "after_ordinal": 0,
                      "previous_event_sha256": claim_sha}
        generated = {"schema_version": "bounded-study-generation-result-v1", "manifest_sha256": manifest_sha,
                     "boot_id": "fake-boot", "finished_monotonic_ns": 1100, "elapsed_ns": 100,
                     "after_ordinal": 58, "previous_event_sha256": anchor}
        review = {"schema_version": "bounded-study-input-review-v1", "manifest_sha256": manifest_sha,
                  "review_sha256": review_sha, "after_ordinal": 58, "previous_event_sha256": anchor}
        primary = {"schema_version": "bounded-study-primary-v1", "study_id": verifier.STUDY_ID,
                   "input_review_sha256": verifier._fingerprint(review), "boot_id": "fake-boot",
                   "started_monotonic_ns": 2000, "deadline_monotonic_ns": 120_000_001_900,
                   "after_ordinal": 58, "previous_event_sha256": anchor}
        phases = {"generation": generation, "generation_result": generated,
                  "input_review": review, "primary": primary, "primary_result": None}
        done = {"boot_id": "fake-boot", "operations_finished_monotonic_ns": 3000}
        with patch.object(verifier, "fenwick_optimum", side_effect=AssertionError("no oracle")):
            verifier._verify_saved_phases(phases, claim_sha, anchor, manifest_sha, review_sha, done)
            events = ([{"event": {"boot_id": "fake-boot", "monotonic_ns": 1050}} for _ in range(58)]
                      + [{"event": {"boot_id": "fake-boot", "monotonic_ns": 2500}}])
            verifier._verify_event_clock_bounds(events, phases, done)
            for position, clock in ((0, 999), (57, 1101), (58, 1999), (58, 3001)):
                altered_events = copy.deepcopy(events)
                altered_events[position]["event"]["monotonic_ns"] = clock
                with self.assertRaises(verifier.SavedVerificationError):
                    verifier._verify_event_clock_bounds(altered_events, phases, done)
            altered_events = copy.deepcopy(events)
            altered_events[58]["event"]["boot_id"] = "other"
            with self.assertRaises(verifier.SavedVerificationError):
                verifier._verify_event_clock_bounds(altered_events, phases, done)
            altered = copy.deepcopy(phases)
            altered["generation_result"]["elapsed_ns"] = 99
            with self.assertRaises(verifier.SavedVerificationError):
                verifier._verify_saved_phases(altered, claim_sha, anchor, manifest_sha, review_sha, done)
            with self.assertRaises(verifier.SavedVerificationError):
                verifier._verify_saved_phases(phases, claim_sha, anchor, manifest_sha, review_sha,
                                              {"boot_id": "other", "operations_finished_monotonic_ns": 3000})
            with self.assertRaises(verifier.SavedVerificationError):
                verifier._verify_saved_phases(phases, claim_sha, anchor, manifest_sha, review_sha,
                    {"boot_id": "fake-boot", "operations_finished_monotonic_ns": primary["deadline_monotonic_ns"]})

    def test_primary_receipt_binds_bundle_and_requires_recorded_finish_before_deadline(self):
        completion = {"boot_id": "fake-boot", "operations_finished_monotonic_ns": 100}
        receipt = {"schema_version": "bounded-study-primary-result-v1", "bundle_sha256": "a" * 64,
                   "boot_id": "fake-boot", "finished_monotonic_ns": 101,
                   "after_ordinal": 2400, "previous_event_sha256": "b" * 64}
        with patch.object(verifier, "fenwick_optimum", side_effect=AssertionError("no oracle")):
            verifier._verify_primary_receipt(receipt, "a" * 64, completion, 102, "b" * 64)
            with self.assertRaises(verifier.SavedVerificationError):
                verifier._verify_primary_receipt(receipt, "c" * 64, completion, 102, "b" * 64)
            with self.assertRaises(verifier.SavedVerificationError):
                verifier._verify_primary_receipt(receipt, "a" * 64, completion, 101, "b" * 64)

    def test_runtime_receipt_requires_single_threads_and_monotonic_timer(self):
        runtime = {"python_version": "fake", "python_executable": "/fake/python", "python_implementation": "fake",
                   "dependencies": {"numpy": "x", "scipy": "x", "scikit-learn": "x"},
                   "native_code_identity": "a" * 64, "boot_id": "12345678-1234-1234-1234-123456789abc",
                   "perf_counter": {"implementation": "fake", "monotonic": True, "adjustable": False,
                                    "resolution": 1e-9}, "gc_enabled": True, "cpu_affinity": [0, 1],
                   "thread_environment": {key: "1" for key in
                       ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")}}
        verifier._verify_runtime(runtime)
        runtime["thread_environment"]["OMP_NUM_THREADS"] = "2"
        with self.assertRaises(verifier.SavedVerificationError):
            verifier._verify_runtime(runtime)

    def test_malformed_top_level_never_dispatches_an_oracle(self):
        with patch.object(verifier, "fenwick_optimum", side_effect=AssertionError("no oracle")):
            with self.assertRaises(verifier.SavedVerificationError):
                verifier.validate_saved({})


if __name__ == "__main__":
    unittest.main()
