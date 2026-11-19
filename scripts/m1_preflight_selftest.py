"""Fault-injection self-test for scripts/m1_preflight.py.

A gate that cannot fail is decoration. Each case injects one fault and asserts the
matching check flips to FAIL (or BLOCKED), then restores it. Nothing here touches
the frozen packet: the approval card and the budget file are copied to a temp
directory, and the scorer faults are stubs.

  .venv/Scripts/python.exe -B scripts/m1_preflight_selftest.py
"""

import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_gate():
    spec = importlib.util.spec_from_file_location("m1_preflight", ROOT / "scripts/m1_preflight.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def last_state(gate):
    return gate.CHECKS[-1]["state"]


def run(gate, fn, *args):
    gate.CHECKS.clear()
    fn(*args)
    return last_state(gate), gate.CHECKS[-1]["detail"]


def main():
    sys.path.insert(0, str(ROOT))
    from src.autoresearch import relevance_retrieval_adapter as adapter, retrieval_lexical as lexical

    gate = load_gate()
    results = []
    tmp = Path(tempfile.mkdtemp(prefix="m1-preflight-selftest-"))
    try:
        original_card, original_budget = gate.CARD, gate.BUDGET

        # --- approval card -------------------------------------------------
        signed = tmp / "signed.md"
        text = original_card.read_text(encoding="utf-8")
        text = text.replace("- [ ]", "- [x]").replace("**待签字**", "**已签字（自检用假卡）**")
        text = text.replace("签字人：__________　日期：__________",
                            "签字人：selftest-not-a-signature　日期：2026-11-19")
        signed.write_text(text, encoding="utf-8")
        gate.CARD = signed
        state, detail = run(gate, gate.check_approval)
        results.append({"case": "all four boxes ticked + signature filled", "expected": "PASS",
                        "got": state, "detail": detail})

        partial = tmp / "partial.md"
        partial.write_text(text.replace("- [x] 允许将可发布部分", "- [ ] 允许将可发布部分"), encoding="utf-8")
        gate.CARD = partial
        state, detail = run(gate, gate.check_approval)
        results.append({"case": "three of four boxes ticked", "expected": "BLOCKED",
                        "got": state, "detail": detail})

        blank_name = tmp / "blank-name.md"
        blank_name.write_text(text.replace("签字人：selftest-not-a-signature", "签字人：__________"),
                              encoding="utf-8")
        gate.CARD = blank_name
        state, detail = run(gate, gate.check_approval)
        results.append({"case": "boxes ticked but signature blank", "expected": "BLOCKED",
                        "got": state, "detail": detail})
        gate.CARD = original_card

        # --- budget --------------------------------------------------------
        budget = json.loads(original_budget.read_text(encoding="utf-8"))
        over = tmp / "budget-over.json"
        budget_over = dict(budget, confirmed_cash_spent=budget["cumulative_additional_cash_limit"] + 1)
        over.write_text(json.dumps(budget_over, ensure_ascii=False), encoding="utf-8")
        gate.BUDGET = over
        state, detail = run(gate, gate.check_budget, 0, 0, 0)
        results.append({"case": "recorded cash above the cap", "expected": "FAIL", "got": state, "detail": detail})
        gate.BUDGET = original_budget
        state, detail = run(gate, gate.check_budget, gate.RESEARCH_ACTION_LIMIT + 1, 0, 0)
        results.append({"case": "declared research actions above the limit", "expected": "FAIL",
                        "got": state, "detail": detail})

        # --- metric contract ----------------------------------------------
        class Skewed:
            METRICS = lexical.METRICS

            @staticmethod
            def metrics(ranking, relevant):
                out = lexical.metrics(ranking, relevant)
                out["ndcg@10"] *= 0.99
                return out

        state, detail = run(gate, gate.check_metrics, Skewed)
        results.append({"case": "nDCG off by 1%", "expected": "FAIL", "got": state,
                        "detail": {"fixtures_failed": len(detail["failures"])}})

        class Dropped:
            METRICS = lexical.METRICS

            @staticmethod
            def metrics(ranking, relevant):
                out = lexical.metrics(ranking, relevant)
                out.pop("mrr@10")
                return out

        state, detail = run(gate, gate.check_metrics, Dropped)
        results.append({"case": "mrr@10 missing from the result", "expected": "FAIL", "got": state,
                        "detail": {"fixtures_failed": len(detail["failures"])}})

        class RecallOnlyAtFive:
            METRICS = lexical.METRICS

            @staticmethod
            def metrics(ranking, relevant):
                out = lexical.metrics(ranking, relevant)
                out["recall@20"] = out["recall@5"]
                return out

        state, detail = run(gate, gate.check_metrics, RecallOnlyAtFive)
        results.append({"case": "recall@20 collapsed onto recall@5", "expected": "FAIL", "got": state,
                        "detail": {"fixtures_failed": len(detail["failures"])}})

        # --- ranking contract ---------------------------------------------
        class DescendingTieBreak:
            @staticmethod
            def retrieve(query, index, method, *, exclude_doc_id):
                return list(reversed(adapter.retrieve(query, index, method, exclude_doc_id=exclude_doc_id)))

        class NoCutoff:
            @staticmethod
            def retrieve(query, index, method, *, exclude_doc_id):
                scored = adapter.retrieve(query, index, method, exclude_doc_id=exclude_doc_id)
                return scored + ["zz-extra"] * 5

        state, detail = run(gate, gate.check_ranking, lexical, DescendingTieBreak)
        results.append({"case": "tie-break reversed", "expected": "FAIL", "got": state,
                        "detail": {"problems": [p["rule"] for p in detail["problems"]]}})

        state, detail = run(gate, gate.check_ranking, lexical, NoCutoff)
        results.append({"case": "cutoff raised to 25", "expected": "FAIL", "got": state,
                        "detail": {"problems": [p["rule"] for p in detail["problems"]]}})

        # --- code pin discrimination --------------------------------------
        same = gate._tabular_identity(sys.version, "0.0.0") == gate._tabular_identity(sys.version, "0.0.1")
        results.append({"case": "pypdf version is part of the identity chain", "expected": "DIFFERS",
                        "got": "SAME" if same else "DIFFERS",
                        "detail": {"same_hash": same,
                                   "note": "if this read SAME the pin would silently ignore a dependency change"}})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    unexpected = [r for r in results if r["got"] != r["expected"]]
    for row in results:
        flag = "ok " if row["got"] == row["expected"] else "BAD"
        print(f"[{flag}] {row['case']}: expected {row['expected']}, got {row['got']}")
    print(f"\n{len(results) - len(unexpected)}/{len(results)} fault injections behaved as specified")
    return 0 if not unexpected else 1


if __name__ == "__main__":
    sys.exit(main())
