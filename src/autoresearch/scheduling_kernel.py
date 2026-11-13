"""Fixed weighted-interval DP definitions, extracted from the frozen CPU study.

Input tuples are (integer start, end, weight, id). Adapters validate the complete
bounded input before calling these functions. No input code, model or IO runs.
"""
import bisect
import hashlib
import json
import random

METHODS = ("quadratic_scan_dp", "binary_search_dp")
MAX_JOBS = 4096
BRUTEFORCE_MAX_JOBS = 12


def value_hash(value):
    """Preserve the standalone integer-tuple JSON identity exactly."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def jobs_for(seed, n):
    """Host-only pure generator; runtime packets contain jobs, never generator calls."""
    if type(seed) is not int or not 0 <= seed <= 1_000_000 or type(n) is not int or not 0 <= n <= MAX_JOBS:
        raise ValueError("Fixed generator seed/count outside bounds")
    rng = random.Random(seed * 100000 + n)
    jobs = []
    for i in range(n):
        start = rng.randrange(10 * n + 1)
        jobs.append((start, start + rng.randint(1, max(2, n // 4)), rng.randint(1, 100), i))
    return jobs


def schedule(jobs, method):
    """Same recurrence, tie handling and numerical-ID ordering as the source."""
    if method not in METHODS or len(jobs) > MAX_JOBS:
        raise ValueError("Unknown fixed method or oversized job array")
    binary = method == "binary_search_dp"
    ordered = sorted(jobs, key=lambda job: (job[1], job[0], job[3]))
    ends = [job[1] for job in ordered]
    dp, parents, taken, operations = [0], [0], [False], 0
    for i, (start, end, weight, job_id) in enumerate(ordered):
        if binary:
            previous = bisect.bisect_right(ends, start, 0, i)
        else:
            previous = 0
            operations += i
            for j in range(i):
                if ends[j] <= start:
                    previous = j + 1
        pick = dp[previous] + weight
        take = pick > dp[-1]
        dp.append(pick if take else dp[-1])
        parents.append(previous if take else i)
        taken.append(take)
    selected, i, reconstruction_steps = [], len(ordered), 0
    while i:
        reconstruction_steps += 1
        if taken[i]:
            selected.append(ordered[i - 1][3])
        i = parents[i]
    return {"objective": dp[-1], "schedule": list(reversed(selected)),
            "full_scan_comparisons": operations,
            "operations": {"dp_steps": len(jobs), "full_scan_comparisons": operations,
                           "bisect_calls": len(jobs) if binary else 0,
                           "bisect_internal_comparisons": None,
                           "reconstruction_steps": reconstruction_steps}}


def verify_schedule(jobs, result):
    """Feasibility and objective arithmetic only; does not compute an optimum."""
    ids = result["schedule"]
    if (type(ids) is not list or any(type(i) is not int for i in ids)
            or len(ids) != len(set(ids)) or type(result["objective"]) is not int):
        raise ValueError("Invalid saved schedule or objective type")
    lookup = {job[3]: job for job in jobs}
    if not set(ids) <= set(lookup):
        raise ValueError("Schedule contains an unknown job ID")
    chosen = sorted((lookup[i] for i in ids), key=lambda job: job[0])
    if not all(a[1] <= b[0] for a, b in zip(chosen, chosen[1:])):
        raise ValueError("Infeasible selected intervals")
    if sum(job[2] for job in chosen) != result["objective"]:
        raise ValueError("Selected-weight sum differs from saved objective")
    # Source reconstruction is in sorted (end,start,id) order.
    if ids != [job[3] for job in sorted((lookup[i] for i in ids), key=lambda j: (j[1], j[0], j[3]))]:
        raise ValueError("Saved schedule is not in the original reconstruction order")
    return True


def brute_force(jobs):
    """Independent exhaustive optimum for an explicitly bounded small case."""
    if len(jobs) > BRUTEFORCE_MAX_JOBS:
        raise ValueError("Exhaustive correctness check exceeds 12 jobs")
    optimum = 0
    for mask in range(1 << len(jobs)):
        chosen = sorted((job for i, job in enumerate(jobs) if mask & (1 << i)), key=lambda job: job[0])
        if all(a[1] <= b[0] for a, b in zip(chosen, chosen[1:])):
            optimum = max(optimum, sum(job[2] for job in chosen))
    return optimum


def saved_reconstruction_steps(jobs, selected):
    """Count the saved backtracking path, without DP or objective optimization.

    Feasible positive-duration selected intervals have increasing starts. One
    monotone pointer counts earlier compatible ends for those selected jobs.
    """
    ordered = sorted(jobs, key=lambda job: (job[1], job[0], job[3]))
    positions = {job[3]: index for index, job in enumerate(ordered)}
    pointer, skipped = 0, 0
    for job_id in selected:
        index = positions[job_id]
        start = ordered[index][0]
        while pointer < index and ordered[pointer][1] <= start:
            pointer += 1
        skipped += index - pointer
    return len(jobs) - skipped
