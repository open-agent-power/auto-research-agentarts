"""The single M1 primary run over the frozen M0 packet. Consumes both allowed actions.

Approval card section 7:
  1. freeze.py --check first  (already enforced by scripts/m1_preflight.py, which
     must return GO before this script is allowed to do anything)
  2. capture_source once      <- research tool action 1
  3. one primary execution    <- research tool action 2
  4. per-arm metrics, per-query paired deltas, and every query whose loss_metrics
     is non-empty, all of them, not just the mean
  5. stop conditions are written down before the numbers exist

This script refuses to run twice. A second run needs a new approval card that
explains why the first was insufficient. There is no --force.

  .venv/Scripts/python.exe -B scripts/m1_preflight.py       # must print GO
  .venv/Scripts/python.exe -B scripts/run_m1_primary.py
"""

import datetime
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "runs/m0-cfr-20261118"
ASSETS = PACKET / "assets"
FREEZE = PACKET / "freeze.json"
GATE = ROOT / "runs/m1-preflight-20261119/result.json"
OUT = ROOT / "runs/m1-cfr-20261119"

RESEARCH_ACTION_LIMIT = 2
# Written before any score exists, copied from approval card section 7.
STOP_CONDITIONS = [
    "If validation recall@20 and mrr@10 are both flat (every per-query delta 0 within 1e-12), "
    "report 'no difference' and do not retune.",
    "If recall rises while MRR falls, every degraded query must be listed individually, not summarised.",
    "One run only. A second attempt requires a new approval card.",
]


def die(message):
    print(f"ABORT: {message}")
    return 1


def main():
    if (OUT / "primary-result.json").exists():
        return die("primary-result.json already exists; this packet is single-run by contract")

    gate = json.loads(GATE.read_text(encoding="utf-8")) if GATE.exists() else {}
    if gate.get("verdict") != "GO":
        return die(f"preflight verdict is {gate.get('verdict')!r}, not 'GO'; run scripts/m1_preflight.py first")

    sys.path.insert(0, str(ROOT))
    from src.autoresearch import staged_relevance_adapter as staged

    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    started = datetime.datetime.now().astimezone()
    ledger = {"run": "m1-cfr-20261119", "started_local": started.isoformat(timespec="seconds"),
              "preflight_verdict": gate.get("verdict"), "actions": [],
              "research_action_limit": RESEARCH_ACTION_LIMIT,
              "stop_conditions_pre_registered": STOP_CONDITIONS}

    # --- action 1: capture -------------------------------------------------
    capture_started = datetime.datetime.now().astimezone()
    payload = staged.capture_source(ASSETS)
    ledger["actions"].append({
        "n": 1, "tool": staged.TOOL_ID.replace("pair", "capture"), "action": "capture_source",
        "started_local": capture_started.isoformat(timespec="seconds"),
        "finished_local": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "snapshot_sha256": payload["snapshot_sha256"]})
    if payload["snapshot_sha256"] != freeze["snapshot_sha256"]:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "ledger.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return die("captured snapshot differs from the freeze; not spending action 2")
    if payload["scope"]["missing_positive_document_count"] != 0:
        return die("missing positive documents present; the packet is not the frozen one")
    (OUT / "source-payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                             encoding="utf-8")

    # --- action 2: the one primary execution -------------------------------
    execute_started = datetime.datetime.now().astimezone()
    result = staged.execute(payload)
    ledger["actions"].append({
        "n": 2, "tool": staged.TOOL_ID, "action": "execute",
        "started_local": execute_started.isoformat(timespec="seconds"),
        "finished_local": datetime.datetime.now().astimezone().isoformat(timespec="seconds")})
    ledger["finished_local"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    ledger["research_actions_used"] = len(ledger["actions"])
    ledger["model_calls"] = result["model_calls"]
    ledger["new_fits"] = result["new_fits"]
    ledger["status"] = result["status"]

    raw = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (OUT / "primary-result.json").write_text(raw, encoding="utf-8")
    ledger["primary_result_sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    ledger["rankings_before_scoring_sha256"] = result["result"]["rankings_before_scoring_sha256"]
    (OUT / "ledger.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # --- summary -----------------------------------------------------------
    body = result["result"]
    usage = body["usage"]
    print(f"status {result['status']}  model_calls {result['model_calls']}  new_fits {result['new_fits']}")
    print(f"snapshot {body['source_snapshot_sha256'][:16]}...  query_pairs {usage['query_pairs']}  "
          f"ranking_calls {usage['ranking_calls']}  index_seconds {usage['index_seconds']:.4f}")
    for split, block in body["paired_summary"]["splits"].items():
        print(f"\n[{split}] queries per arm {block['arms']['bm25']['queries']}")
        for method in ("bm25", "tfidf_cosine"):
            metrics = block["arms"][method]["metrics"]
            print("  " + method.ljust(13) + "  " + "  ".join(f"{k}={v:.6f}" for k, v in metrics.items()))
        print("  candidate - baseline (mean / wins / ties / losses)")
        for name, cell in block["paired_candidate_minus_baseline"].items():
            print(f"    {name:<10} {cell['mean']:+.6f}  {cell['wins']}/{cell['ties']}/{cell['losses']}")
    degraded = [row for row in body["adverse_queries"] if row["loss_metrics"]]
    print(f"\nadverse queries {len(body['adverse_queries'])}, of which with a loss metric {len(degraded)}")
    for row in body["adverse_queries"]:
        print(f"  {row['split']:<10} {row['query_id']:<12} loss={row['loss_metrics']} gain={row['gain_metrics']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
