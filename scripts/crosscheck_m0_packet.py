"""Independent read-only cross-check of the frozen M0 packet (m0-cfr-20261118).

Deliberately does NOT import src.autoresearch. Every identity here is recomputed
from raw bytes with stdlib only, so a matching snapshot hash means the packet is
reproducible from the bytes on disk rather than merely accepted by the author's
own capture path.

Checks
  A  asset/spec bytes + sha256 vs freeze.json
  B  independent payload assembly -> fingerprint == published snapshot_sha256
  C  structural counts, qrels semantics, split disjointness
  D  source archive bytes/sha and receipt sha
  E  XML fidelity: every corpus text normalises into the frozen source section
  F  licence ledger coverage and the published "no incorporation" claim
  G  bounded-limit compliance

  python scripts/crosscheck_m0_packet.py     run checks, write runs/m0-crosscheck-20261119/result.json
"""

import base64
import hashlib
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "runs/m0-cfr-20261118"
ASSETS = PACKET / "assets"
SOURCE = ROOT / "runs/source-audit-20261118/CFR-2025-title16-vol1.xml"
RECEIPT = ROOT / "runs/source-audit-20261118/receipt.md"
FREEZE = PACKET / "freeze.json"
OUT = ROOT / "runs/m0-crosscheck-20261119/result.json"

# Protocol constants, restated here on purpose: if the adapter's constants moved,
# the recomputed snapshot would move too and this check would fail loudly.
CONTRACT = "staged-relevance-development-v1"
SEMANTICS = "positive_relevance_binary_projection"
COMPARISON = {
    "baseline": "bm25",
    "candidate": "tfidf_cosine",
    "top_k": 20,
    "k1": 1.2,
    "b": 0.75,
    "tokenizer": "ascii_alnum_lower_v1",
    "tie_break": "doc_id_ascending",
    "ignore_identical_ids": True,
    "missing_document_policy": "retain_in_denominator",
    "metrics": ["recall@5", "recall@10", "recall@20", "mrr@10", "ndcg@10"],
}
SPLITS = ("dev", "validation")
FILES = {"corpus": "corpus.jsonl", "queries": "queries.jsonl", "qrels": "qrels.tsv", "license": "license.md"}
LIMITS = {
    "corpus_bytes": 12582912,
    "queries_bytes": 3145728,
    "qrels_bytes": 1048576,
    "license_bytes": 65536,
    "all_asset_bytes": 11800000,
    "spec_bytes": 65536,
    "packet_bytes": 16000000,
    "max_corpus_rows": 10000,
    "max_queries": 2000,
    "max_qrel_pairs": 20000,
    "max_query_text": 32768,
}

CHECKS = []


def check(name, ok, detail):
    CHECKS.append({"check": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return ok


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value):
    return sha256(canonical(value).encode("utf-8"))


def norm(value):
    return " ".join(value.split())


def asset(name, raw):
    return {
        "file_name": name,
        "sha256": sha256(raw),
        "bytes": len(raw),
        "bytes_base64": base64.b64encode(raw).decode("ascii"),
    }


def jsonl_rows(raw, corpus):
    rows = {}
    for line in raw.decode("utf-8").split("\n"):
        if not line.strip():
            continue
        row = json.loads(line)
        if row["_id"] in rows:
            raise ValueError(f"duplicate row id {row['_id']}")
        rows[row["_id"]] = row
    return rows


def read_qrels(raw):
    lines = raw.decode("utf-8").replace("\r\n", "\n").split("\n")
    header = lines[0].split("\t")
    pairs = []
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            raise ValueError(f"bad qrels width: {line!r}")
        pairs.append((parts[0], parts[1], int(parts[2])))
    return header, pairs


def xml_sections(raw):
    """Section number -> list of normalised section texts, from the frozen archive."""
    text = raw.decode("utf-8")
    out = {}
    for block in re.findall(r"<SECTION>(.*?)</SECTION>", text, flags=re.S):
        sectno = re.search(r"<SECTNO>(.*?)</SECTNO>", block, flags=re.S)
        if not sectno:
            continue
        number = re.search(r"(\d+\.\d+)", sectno.group(1))
        if not number:
            continue
        cleaned = re.sub(r"<SU>.*?</SU>", " ", block, flags=re.S)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        out.setdefault(number.group(1), []).append(norm(html.unescape(cleaned)))
    return out


def main():
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))

    # --- A: bytes and hashes ------------------------------------------------
    raw_assets = {role: (ASSETS / name).read_bytes() for role, name in FILES.items()}
    raw_spec = (ASSETS / "spec.json").read_bytes()
    spec = json.loads(raw_spec)

    asset_ok, asset_detail = True, {}
    for role, name in FILES.items():
        want = freeze["assets"][role]
        got = {"file": name, "bytes": len(raw_assets[role]), "sha256": sha256(raw_assets[role])}
        same = got["bytes"] == want["bytes"] and got["sha256"] == want["sha256"]
        asset_ok = asset_ok and same
        asset_detail[role] = {"bytes": got["bytes"], "sha256": got["sha256"], "matches_freeze": same}
    check("A1 assets match freeze.json bytes+sha256", asset_ok, asset_detail)

    spec_ok = all(spec[key] == COMPARISON for key in ("comparison",)) and spec["files"] == FILES
    check("A2 spec.json constants equal the protocol restatement", spec_ok,
          {"schema": spec["schema_version"], "files": spec["files"],
           "comparison_equal": spec["comparison"] == COMPARISON, "limits_equal": spec["limits"] == LIMITS})
    check("A3 spec.json size within limit", len(raw_spec) <= LIMITS["spec_bytes"], f"{len(raw_spec)} B")

    # --- B: independent snapshot recompute ---------------------------------
    docs = jsonl_rows(raw_assets["corpus"], True)
    queries = jsonl_rows(raw_assets["queries"], False)
    qrels_header, qrel_pairs = read_qrels(raw_assets["qrels"])

    assets_block = {role: asset(FILES[role], raw) for role, raw in raw_assets.items()}
    qrels_map = {}
    for qid, doc, grade in qrel_pairs:
        qrels_map.setdefault(qid, {})[doc] = grade
    missing = sorted({doc for grades in qrels_map.values() for doc in grades if doc not in docs})
    scope = {
        "domain": "retrieval",
        "stage": "development",
        "contract": CONTRACT,
        "dataset_label": spec["dataset_label"],
        "document_count": len(docs),
        "query_count": len(queries),
        "query_split_counts": {split: len(spec["query_splits"][split]) for split in SPLITS},
        "qrels_semantics": SEMANTICS,
        "input_identities": {role: {"sha256": a["sha256"], "bytes": a["bytes"]} for role, a in assets_block.items()},
        "comparison_sha256": fingerprint(COMPARISON),
        "missing_positive_document_ids": missing,
        "missing_positive_document_count": len(missing),
        "missing_positive_qrel_pairs": sum(doc not in docs for grades in qrels_map.values() for doc in grades),
    }
    payload = {
        "schema_version": "cpu-research-source-v1",
        "task_kind": "staged_relevance_development",
        "stage": "development",
        "spec_source": asset("spec.json", raw_spec),
        "assets": assets_block,
        "spec": spec,
        "scope": scope,
    }
    payload["snapshot_sha256"] = snapshot = fingerprint(payload)
    pub = freeze["snapshot_sha256"]
    check("B1 recomputed snapshot == published snapshot", snapshot == pub,
          {"recomputed": snapshot, "published": pub, "match": snapshot == pub})
    check("B2 freeze.json counts equal the recomputed scope",
          freeze["counts"] == {"documents": len(docs), "queries": len(queries),
                               "query_splits": {s: len(spec["query_splits"][s]) for s in SPLITS},
                               "qrel_pairs": len(qrel_pairs), "missing_positive_document_count": len(missing)},
          {"freeze": freeze["counts"], "recomputed_documents": len(docs), "recomputed_queries": len(queries),
           "recomputed_pairs": len(qrel_pairs), "recomputed_missing": len(missing)})

    # --- C: structure and qrels semantics ---------------------------------
    declared = [qid for split in SPLITS for qid in spec["query_splits"][split]]
    split_sets = [set(spec["query_splits"][s]) for s in SPLITS]
    check("C1 document count 85, query count 32", len(docs) == 85 and len(queries) == 32,
          {"documents": len(docs), "queries": len(queries)})
    check("C2 splits disjoint, declared == query ids == qrels keys",
          not (split_sets[0] & split_sets[1]) and set(declared) == set(queries) == set(qrels_map),
          {"dev": len(split_sets[0]), "validation": len(split_sets[1]),
           "intersection": len(split_sets[0] & split_sets[1]),
           "declared_eq_queries": set(declared) == set(queries),
           "declared_eq_qrels": set(declared) == set(qrels_map)})
    grades = sorted({g for _, _, g in qrel_pairs})
    per_query = {qid: len(g) for qid, g in qrels_map.items()}
    check("C3 qrels header exact and every pair score=2", qrels_header == ["query-id", "corpus-id", "score"]
          and grades == [2], {"header": qrels_header, "distinct_grades": grades, "pairs": len(qrel_pairs)})
    check("C4 exactly one positive per query, all resolvable in corpus",
          set(per_query.values()) == {1} and not missing,
          {"positives_per_query": sorted(set(per_query.values())), "missing_positive_ids": missing})
    dup = len(qrel_pairs) - len(set(qrel_pairs))
    check("C5 no duplicate qrel rows", dup == 0, {"duplicates": dup, "unique": len(set(qrel_pairs))})

    empty_text = [did for did, row in docs.items() if not str(row.get("text", "")).strip()]
    nonempty_meta = [did for did, row in docs.items() if row.get("metadata") != {}]
    check("C6 corpus rows: non-empty text, empty metadata, unique ids",
          not empty_text and not nonempty_meta and len(docs) == len(set(docs)),
          {"empty_text": len(empty_text), "non_empty_metadata": len(nonempty_meta), "rows": len(docs)})

    selection = json.loads((ASSETS / "selection.json").read_text(encoding="utf-8"))
    check("C7 selection.json doc_ids equal corpus ids",
          sorted(selection["doc_ids"]) == sorted(docs),
          {"selection": len(selection["doc_ids"]), "corpus": len(docs)})

    parts = sorted({row["_id"].split("-")[2].split(".")[0] for row in docs.values()})
    check("C8 corpus spans the 11 declared Parts", len(parts) == 11, {"parts": parts})

    # --- D: source provenance ---------------------------------------------
    src = SOURCE.read_bytes()
    rec = RECEIPT.read_bytes()
    check("D1 source archive bytes + sha256 match freeze",
          len(src) == freeze["source"]["archive_bytes"] and sha256(src) == freeze["source"]["archive_sha256"],
          {"bytes": len(src), "sha256": sha256(src)})
    check("D2 source receipt sha256 matches freeze", sha256(rec) == freeze["source"]["receipt_sha256"],
          {"sha256": sha256(rec)})
    check("D3 spec provenance restates the same source identities",
          spec["source_provenance"]["archive_sha256"] == freeze["source"]["archive_sha256"]
          and spec["source_provenance"]["source_receipt_sha256"] == freeze["source"]["receipt_sha256"]
          and spec["source_provenance"]["qrels_semantics"] == SEMANTICS,
          spec["source_provenance"])

    # --- E: XML fidelity (the check the tamper test explicitly does not do) -
    sections = xml_sections(src)
    fidelity_fail = []
    for did, row in docs.items():
        number = did.split("-", 2)[2]
        body = norm(row["text"])
        candidates = sections.get(number, [])
        if not any(body in candidate for candidate in candidates):
            fidelity_fail.append({"doc_id": did, "xml_sections_found": len(candidates),
                                  "text_head": body[:80]})
    check("E1 every corpus text lies inside its frozen source section", not fidelity_fail,
          {"documents": len(docs), "xml_sections_indexed": len(sections),
           "failures": fidelity_fail[:10], "failure_count": len(fidelity_fail)})

    # --- F: licence ledger and the published "no incorporation" claim ------
    ledger_lines = (ASSETS / "license-ledger.tsv").read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    ledger_header = ledger_lines[0].split("\t")
    ledger_rows = [line.split("\t") for line in ledger_lines[1:] if line.strip()]
    ledger_ids = [r[0] for r in ledger_rows]
    decisions = {}
    for r in ledger_rows:
        decisions[r[6]] = decisions.get(r[6], 0) + 1
    kept_ids = {r[0] for r in ledger_rows if r[6] == "kept"}
    excluded_ids = [r[0] for r in ledger_rows if r[6] == "excluded"]
    check("F1 ledger = 85 kept + the one documented exclusion, kept == corpus",
          kept_ids == set(docs) and len(ledger_rows) == 86 and excluded_ids == ["d-16-465.3"],
          {"ledger_rows": len(ledger_rows), "decisions": decisions,
           "kept_equals_corpus": kept_ids == set(docs), "excluded_ids": excluded_ids,
           "duplicate_ledger_ids": len(ledger_ids) - len(set(ledger_ids))})
    check("F2 ledger chars column equals raw text length",
          all(int(r[5]) == len(docs[r[0]]["text"]) for r in ledger_rows if r[6] == "kept"),
          {"mismatches": [r[0] for r in ledger_rows if r[6] == "kept" and int(r[5]) != len(docs[r[0]]["text"])]})
    corpus_blob = "\n".join(row["text"] for row in docs.values()).lower()
    ib = corpus_blob.count("incorporated by reference")
    check("F3 no 'incorporated by reference' clause in the frozen corpus", ib == 0,
          {"occurrences": ib})
    reserved = [did for did, row in docs.items() if "reserved" in row["title"].lower()]
    check("F4 no [Reserved] section was kept as a document", not reserved, {"reserved_titles": reserved})

    # --- G: limits --------------------------------------------------------
    total_assets = sum(len(v) for v in raw_assets.values())
    under = (len(raw_assets["corpus"]) <= LIMITS["corpus_bytes"]
             and len(raw_assets["queries"]) <= LIMITS["queries_bytes"]
             and len(raw_assets["qrels"]) <= LIMITS["qrels_bytes"]
             and len(raw_assets["license"]) <= LIMITS["license_bytes"]
             and total_assets <= LIMITS["all_asset_bytes"]
             and len(docs) <= LIMITS["max_corpus_rows"] and len(queries) <= LIMITS["max_queries"]
             and len(qrel_pairs) <= LIMITS["max_qrel_pairs"])
    check("G1 all assets and row counts inside protocol limits", under,
          {"all_asset_bytes": total_assets, "limit": LIMITS["all_asset_bytes"], "packet_fingerprint_bytes":
           len(canonical(payload).encode("utf-8"))})

    # --- H: byte-level portability of the freeze ---------------------------
    endings = {}
    for name in ("corpus.jsonl", "queries.jsonl", "qrels.tsv", "license.md", "spec.json"):
        blob = (ASSETS / name).read_bytes()
        crlf, lf = blob.count(b"\r\n"), blob.count(b"\n")
        endings[name] = {"crlf": crlf, "lf": lf,
                         "profile": "CRLF" if crlf and crlf == lf else ("LF" if lf and crlf == 0 else "none")}
    consistent = all(v["profile"] in ("CRLF", "LF", "none") for v in endings.values())
    mixed_files = sorted({v["profile"] for v in endings.values()})
    check("H1 each asset uses one line ending, no mixed file", consistent,
          {"per_file": endings, "profiles_present": mixed_files,
           "note": "profiles differ across files: regenerating on a platform with a different "
                   "newline default changes these hashes"})

    # --- summary ----------------------------------------------------------
    failed = [c["check"] for c in CHECKS if not c["ok"]]
    result = {
        "packet": "m0-cfr-20261118",
        "verifier": "scripts/crosscheck_m0_packet.py",
        "independent": "stdlib only; does not import src.autoresearch",
        "generated_at_local": "2026-11-19 (Asia/Shanghai)",
        "snapshot_recomputed": snapshot,
        "snapshot_published": pub,
        "checks_total": len(CHECKS),
        "checks_failed": failed,
        "checks": CHECKS,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed; wrote {OUT.name}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
