"""Fixed three-arm wrapper for a separately approved local scheduling study.

This module does not generate jobs, approve a run, or change the old two-arm
adapter. All three arms traverse the same dispatch function and timing boundary.
"""
import math
import time

from . import scheduling_kernel as kernel

ARMS = ('fixed_binary', 'fixed_scan', 'threshold32')


def method_for(arm, job_count):
    if arm not in ARMS or type(job_count) is not int or not 0 <= job_count <= kernel.MAX_JOBS:
        raise ValueError('A fixed arm and bounded nonnegative job count are required')
    if arm == 'fixed_scan' or (arm == 'threshold32' and job_count <= 32):
        return 'quadratic_scan_dp'
    return 'binary_search_dp'


def dispatch(jobs, arm):
    """One shared dispatch path, including the candidate's fixed size check."""
    return kernel.schedule(jobs, method_for(arm, len(jobs)))


def measured(jobs, arm, *, clock=None):
    """Measure only dispatch+kernel; checking and persistence happen afterward.

    The production timer is perf_counter_ns. Invalid/zero durations are retained
    and marked uninterpretable, with no retry or invented positive value.
    """
    if clock is None:
        clock = time.perf_counter_ns
    start = clock()
    returned = dispatch(jobs, arm)
    end = clock()
    if type(start) not in (int, float) or type(end) not in (int, float):
        raise ValueError('Timer values must be numeric')
    difference = end - start
    try:
        finite = math.isfinite(difference)
    except OverflowError:
        finite = False
    if not finite:
        raw = 'NaN' if math.isnan(difference) else ('Infinity' if difference > 0 else '-Infinity')
        status, elapsed = 'nonfinite', None
    elif difference == 0:
        raw, status, elapsed = difference, 'zero', None
    elif difference < 0:
        raw, status, elapsed = difference, 'negative', None
    elif type(difference) is not int:
        raise ValueError('A positive timer duration must use integer nanoseconds')
    else:
        raw, status, elapsed = difference, 'ok', difference
    return {'returned': returned, 'elapsed_ns': elapsed, 'timing_status': status, 'elapsed_raw': raw}
