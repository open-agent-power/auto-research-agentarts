"""The single M1b primary run over the frozen open-corpus packet.

Same execution shape as the M1 runner, different packet. Two research actions only:
capture once, execute once. Refuses to start if the gate is not GO, if the result
already exists, or if the captured snapshot is not the frozen one.

  .venv/Scripts/python.exe -B scripts/m1b_preflight.py    # must print GO
  .venv/Scripts/python.exe -B scripts/run_m1b_primary.py
"""

import datetime
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "runs/m1b-packet-20261119"
ASSETS = PACKET / "assets"
FREEZE = PACKET / "freeze.json"
GATE = PACKET / "preflight.json"
OUT = ROOT / "runs/m1b-cfr-20261119"

RESEARCH_ACTION_LIMIT = 2
# Copied from docs/project/workbuddy/m1b-protocol-20261119.md, written before the run.
STOP_CONDITIONS = [
    "One run only; a second attempt requires a new approval card.",
    "If freeze verification fails after capture, stop before spending action 2.",
    "If recall@20 is still 1.0 for both arms on every query, declare the expanded pool "
    "insufficient and stop; do not expand again on this card.",
    "No tuning of k1, b, tokenizer, top_k or metric definitions after any result exists.",
]


def die(message):
    print(f"ABORT: {message}")
    return 1


def main():
    if (OUT / "primary-result.json").exists():
        return die("primary-result.json already exists; this packet is single-run by contract")

    gate = json.loads(GATE.read_text(encoding="utf-8")) if GATE.exists() else {}
    if gate.get("verdict") != "GO":
        return die(f"preflight verdict is {gate.get('verdict')!r}, not 'GO'; run scripts/m1b_preflight.py first")

    sys.path.insert(0, str(ROOT))
    from src.autoresearch import staged_relevance_adapter as staged

    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    started = datetime.datetime.now().astimezone()
    ledger = {"run": "m1b-cfr-20261119",
              "packet": "m1b-cfr-open-corpus-20261119",
              "started_local": started.isoformat(timespec="seconds"),
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
        (OUT / "ledger.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
        return die("captured snapshot differs from the freeze; not spending action 2")
    if payload["scope"]["missing_positive_document_count"] != 0:
        return die("missing positive documents present; the packet is not the frozen one")
    if payload["scope"]["document_count"] != 940:
        return die(f"captured {payload['scope']['document_count']} documents, expected 940")
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
    # Write bytes, not text: text mode expands LF to CRLF on Windows, which makes the file's
    # own bytes hash differently from the string that was hashed. Record the bytes actually written.
    (OUT / "primary-result.json").write_bytes(raw.encode("utf-8"))
    ledger["primary_result_sha256"] = hashlib.sha256((OUT / "primary-result.json").read_bytes()).hexdigest()
    ledger["rankings_before_scoring_sha256"] = result["result"]["rankings_before_scoring_sha256"]
    (OUT / "ledger.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")

    body = result["result"]
    usage = body["usage"]
    print(f"status {result['status']}  model_calls {result['model_calls']}  new_fits {result['new_fits']}")
    print(f"snapshot {body['source_snapshot_sha256'][:16]}...  documents {body['scope']['document_count']}  "
          f"query_pairs {usage['query_pairs']}  index_seconds {usage['index_seconds']:.4f}")
    for split, block in body["paired_summary"]["splits"].items():
        print(f"\n[{split}] queries per arm {block['arms']['bm25']['queries']}")
        for method in ("bm25", "tfidf_cosine"):
            print("  " + method.ljust(13) + "  " +
                  "  ".join(f"{k}={v:.6f}" for k, v in block["arms"][method]["metrics"].items()))
        print("  candidate - baseline (mean / wins / ties / losses)")
        for name, cell in block["paired_candidate_minus_baseline"].items():
            print(f"    {name:<10} {cell['mean']:+.6f}  {cell['wins']}/{cell['ties']}/{cell['losses']}")
    print(f"\nadverse queries {len(body['adverse_queries'])}")
    for row in body["adverse_queries"]:
        print(f"  {row['split']:<10} {row['query_id']:<12} loss={row['loss_metrics']} gain={row['gain_metrics']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
