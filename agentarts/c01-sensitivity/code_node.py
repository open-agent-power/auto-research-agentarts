"""Pure Python body for an AgentArts Code node; no model or network calls."""

import hashlib
import json
import math


def _correlation(samples):
    xs = [sample["water_contact_angle_deg"] for sample in samples]
    ys = [sample["cell_seeding_efficiency_24h_pct"] for sample in samples]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    numerator = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denominator = math.sqrt(sum((x - mx) ** 2 for x in xs) *
                            sum((y - my) ** 2 for y in ys))
    return None if denominator == 0 else numerator / denominator


def main(args: dict) -> dict:
    raw = args.get("query")
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > 32768:
        raise ValueError("query must be a JSON string no larger than 32 KiB")
    data = json.loads(raw)
    if not isinstance(data, dict) or set(data) != {"source_doi", "samples"}:
        raise ValueError("input must contain source_doi and samples only")
    if not isinstance(data["source_doi"], str) or not 1 <= len(data["source_doi"]) <= 160:
        raise ValueError("source_doi must identify the supplied source")
    samples = data["samples"]
    if not isinstance(samples, list) or not 4 <= len(samples) <= 128:
        raise ValueError("require 4 to 128 distinct aggregate samples")
    ids = set()
    for sample in samples:
        if not isinstance(sample, dict) or set(sample) != {
            "sample_id", "water_contact_angle_deg", "cell_seeding_efficiency_24h_pct"
        }:
            raise ValueError("unexpected or missing sample fields")
        sample_id = sample["sample_id"]
        if not isinstance(sample_id, str) or not 1 <= len(sample_id) <= 80 or sample_id in ids:
            raise ValueError("sample_id must be a unique non-empty string")
        ids.add(sample_id)
        for field, upper in (("water_contact_angle_deg", 180),
                             ("cell_seeding_efficiency_24h_pct", 100)):
            value = sample[field]
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= upper:
                raise ValueError(field + " is outside its stated measurement domain")
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    full = _correlation(samples)
    sensitivity = []
    for index, sample in enumerate(samples):
        without = _correlation(samples[:index] + samples[index + 1:])
        sensitivity.append({"removed_sample_id": sample["sample_id"], "pearson_r": without,
                            "sign_changed": full is not None and without is not None and full * without < 0})
    sign_changes = sum(item["sign_changed"] for item in sensitivity)
    undefined = full is None or any(item["pearson_r"] is None for item in sensitivity)
    result = {
        "schema_version": "c01-sensitivity-v1", "source_doi": data["source_doi"],
        "input_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "sample_count": len(samples), "pearson_r": full,
        "leave_one_out": sensitivity, "sign_changes": sign_changes,
        "status": "needs_review" if sign_changes or undefined else "exploratory_only",
        "limitations": ["Supplied aggregate samples only; source and independence are not automatically verified.",
                        "Post-hoc sensitivity analysis; not independent validation, causal or clinical evidence.",
                        "No significance test or new model training was performed."],
    }
    return {"result": json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False)}
