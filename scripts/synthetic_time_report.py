"""Private mechanical checks for the fixed S134 synthetic clock fixture.

The byte helper is for synthetic tests and the sibling generator only. It is
not a real dataset reader, a rights check, a signed attestation or a dispatch gate.
"""
import csv
import datetime as dt
import io
import math
import re

STATION = 'SYNTHETIC_S1'
CLOCK = 'synthetic_naive_clock_no_timezone_no_dst'
START = dt.datetime(2024, 2, 28, 22)
END = dt.datetime(2024, 3, 1, 2)
HEADER = ('station','year','month','day','hour','x','outcome')
MAX_CSV_BYTES = 65536


def _inspect_csv(raw):
    """Recompute counts from synthetic UTF-8 bytes, rejecting any clock ambiguity."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_CSV_BYTES:
        raise ValueError('synthetic CSV size outside fixed bound')
    text = raw.decode('utf-8', errors='strict')
    if '\x00' in text or '\r' in text:
        raise ValueError('unexpected synthetic CSV encoding or newline')
    reader = csv.reader(io.StringIO(text, newline=''), strict=True)
    try:
        if tuple(next(reader)) != HEADER:
            raise ValueError('unexpected synthetic CSV header')
        counts = {name:{'finite':0,'zero':0,'empty':0,'declared_missing':0} for name in ('x','outcome')}
        cursor = START
        rows = paired = 0
        for row in reader:
            if len(row) != len(HEADER) or rows >= 28:
                raise ValueError('unexpected synthetic row count or width')
            station, year, month, day, hour, x, outcome = row
            if (station != STATION or re.fullmatch(r'[0-9]{4}', year) is None
                    or any(re.fullmatch(r'[0-9]{2}', value) is None for value in (month, day, hour))):
                raise ValueError('invalid station or clock token')
            try:
                observed = dt.datetime(int(year), int(month), int(day), int(hour))
            except ValueError as exc:
                raise ValueError('invalid synthetic calendar hour') from exc
            if observed != cursor or not START <= observed < END:
                raise ValueError('missing, repeated, unordered or out-of-window synthetic hour')
            finite = []
            for name, token in (('x',x),('outcome',outcome)):
                if token == '':
                    counts[name]['empty'] += 1; finite.append(False)
                elif token == 'NA':
                    counts[name]['declared_missing'] += 1; finite.append(False)
                elif re.fullmatch(r'(?:0|[1-9][0-9]*)', token) is not None and math.isfinite(float(token)):
                    counts[name]['finite'] += 1; counts[name]['zero'] += token == '0'; finite.append(True)
                else:
                    raise ValueError('invalid or nonfinite synthetic numeric token')
            paired += all(finite);rows += 1;cursor += dt.timedelta(hours=1)
        if rows != 28 or cursor != END:
            raise ValueError('incomplete synthetic hourly grid')
        return {'rows':rows, 'hours_expected':28, 'numeric_counts':counts,
                'paired_finite':paired, 'paired_excluded':rows-paired}
    except (csv.Error, StopIteration, OverflowError) as exc:
        raise ValueError('malformed synthetic CSV') from exc
