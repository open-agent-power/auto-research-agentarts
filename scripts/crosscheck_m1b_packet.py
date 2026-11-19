"""Independent read-only cross-check of the M1b packet (runs/m1b-packet-20261119).

Deliberately does NOT import build_packet.py or src.autoresearch. Every number
here is recomputed from the frozen XML and from the packet's own bytes with
stdlib only, so agreement means the packet is reproducible from what is on disk
rather than merely accepted by the builder that produced it.

What M1b is. M0 measured recall@20 = 1.0 on all 32 queries for both arms: 85
documents, top_k 20, one positive per query. This packet widens only the
distractor pool to the whole frozen volume, so top 20 covers ~2% instead of
23.5%. Queries, qrels, the 85 labelled documents, the scorer and every
comparison constant are supposed to be unchanged.

This script does NOT rank anything. It checks that the packet is what it claims
to be, and records what a freeze would still need.

Checks
  A  corpus / licence ledger / spec identities recomputed from bytes
  B  every physical SECTION maps to exactly one ledger entry, under the three id
     conventions in use: plain, letter-suffixed duplicate, range id
  C  the 85 labelled documents are byte-identical to the M0 packet
  D  distractor hygiene: uniqueness, non-empty text, declared size ceiling
  E  inheritance from M0, and what a freeze still needs
  F  coverage arithmetic for the primary endpoint
  G  prose-vs-ledger agreement in the extraction report

  python scripts/crosscheck_m1b_packet.py    -> runs/m1b-crosscheck-20261119/result.json
"""

import argparse
import collections
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "runs/m1b-packet-20261119"
ASSETS = PACKET / "assets"
M0 = ROOT / "runs/m0-cfr-20261118"
M0_ASSETS = M0 / "assets"
SOURCE = ROOT / "runs/source-audit-20261118/CFR-2025-title16-vol1.xml"
OUT = ROOT / "runs/m1b-crosscheck-20261119/result.json"

EXPECTED_BYTES = 4422809
EXPECTED_SHA256 = "fbaf04e9bb41f1a8598a9f8f93091f68b5f468b50e4bf481a52abfc64982b3a9"
TOP_K = 20
MAX_TEXT = 131072
M0_CORPUS_SHA = "1731636ad332e0310f48fc0ea37b065d4dfad0bd596fcba8e20437e4ac131948"
M0_QUERIES_SHA = "4b0736e58ae927ca90b0b7615379c53022525894e6d249fc9980aba0ffb8f23c"
M0_QRELS_SHA = "d736cc37e782f628a0f1db5d38a2c06591ad8094410b4d2ce4dad89caf314e4b"
PLAIN_ID = re.compile(r"d-16-(\d+\.\d+)$")
SUFFIX_ID = re.compile(r"d-16-(\d+\.\d+)([A-Za-z])$")
RANGE_ID = re.compile(r"d-16-(\d+\.\d+)-(\d+\.\d+)$")
THIRD_PARTY = ("incorporated by reference", "incorporation by reference", "copyright",
               "ansi", "astm", "nfpa", "ieee")

CHECKS = []


def check(name, ok, detail):
    CHECKS.append({"check": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return ok


def note(name, ok, detail):
    """A finding that is recorded but is not a packet defect."""
    CHECKS.append({"check": name, "ok": bool(ok), "detail": detail, "kind": "finding"})
    print(f"[{'NOTE' if ok else 'WARN'}] {name}: {detail}")
    return ok


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def section_number(section):
    node = section.find("SECTNO")
    if node is None:
        return None
    match = re.search(r"(\d+\.\d+)", "".join(node.itertext()))
    return match.group(1) if match else None


def physical_sections(raw):
    """Section number -> list of normalised full-section text, one entry per SECTION."""
    root = ET.fromstring(raw)
    out = collections.defaultdict(list)
    for section in root.iter("SECTION"):
        number = section_number(section)
        if number is None:
            continue
        out[number].append(" ".join("".join(section.itertext()).split()))
    return out


def number_key(number):
    return tuple(int(p) for p in number.split("."))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    out = Path(args.out) if args.out else OUT

    raw_corpus = (ASSETS / "corpus.jsonl").read_bytes()
    manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
    spec = json.loads((ASSETS / "spec.json").read_text(encoding="utf-8"))
    report = (ASSETS / "extraction-report.md").read_text(encoding="utf-8")
    rows = read_jsonl(ASSETS / "corpus.jsonl")
    queries = read_jsonl(ASSETS / "queries.jsonl")
    docs = {row["_id"]: row for row in rows}
    excluded = {entry["id"]: entry for entry in manifest["excluded_sections"]}

    # --- A: identities recomputed from bytes -------------------------------
    declared = manifest["corpus"]
    got = {"documents": len(rows), "bytes": len(raw_corpus), "sha256": sha256(raw_corpus)}
    check("A1 corpus bytes and sha256 match the manifest",
          got == {"documents": declared["documents"], "bytes": declared["bytes"],
                  "sha256": declared["sha256"]},
          {"recomputed": got, "declared": {k: declared[k] for k in ("documents", "bytes", "sha256")}})

    lengths = [len(row["text"]) for row in rows]
    stats = {"chars_min": min(lengths), "chars_max": max(lengths), "chars_total": sum(lengths)}
    check("A2 char statistics match the manifest",
          stats == {k: declared[k] for k in stats},
          {"recomputed": stats, "declared": {k: declared[k] for k in stats}})

    ledger_raw = (ASSETS / "license-ledger.tsv").read_bytes()
    ledger_lines = ledger_raw.decode("utf-8").replace("\r\n", "\n").split("\n")
    ledger_header = ledger_lines[0].split("\t")
    ledger_rows = [line.split("\t") for line in ledger_lines[1:] if line.strip()]
    ledger_ids = [row[0] for row in ledger_rows]
    roles = collections.Counter(row[3] for row in ledger_rows)
    basis = collections.Counter(row[5] for row in ledger_rows)
    chars_ok = all(row[4] == str(len(docs[row[0]]["text"])) for row in ledger_rows if row[0] in docs)
    check("A3 licence ledger covers all 940 corpus rows, one row each, chars agree",
          ledger_ids == [row["_id"] for row in rows] and chars_ok and len(ledger_ids) == len(set(ledger_ids)),
          {"rows": len(ledger_rows), "header": ledger_header, "roles": dict(roles),
           "rights_basis": dict(basis), "chars_mismatches": not chars_ok,
           "ordered_like_corpus": ledger_ids == [row["_id"] for row in rows]})

    selection_sha = sha256((ASSETS / "selection.json").read_bytes())
    split_ids = [qid for split in ("dev", "validation") for qid in spec["query_splits"][split]]
    check("A4 spec binds this packet's selection.json, the frozen archive, and the same query set",
          spec["source_provenance"]["selection_sha256"] == selection_sha
          and spec["source_provenance"]["archive_sha256"] == EXPECTED_SHA256
          and spec["source_provenance"]["qrels_semantics"] == "positive_relevance_binary_projection"
          and set(split_ids) == {row["_id"] for row in queries},
          {"selection_sha256": spec["source_provenance"]["selection_sha256"],
           "selection_matches": spec["source_provenance"]["selection_sha256"] == selection_sha,
           "query_ids_declared": len(split_ids), "query_rows": len(queries),
           "dataset_label": spec["dataset_label"][:90]})

    check("A5 declared corpus limits still admit 940 rows / 2.45 MB",
          len(rows) <= spec["limits"]["max_corpus_rows"]
          and len(raw_corpus) <= spec["limits"]["corpus_bytes"],
          {"rows": len(rows), "row_limit": spec["limits"]["max_corpus_rows"],
           "bytes": len(raw_corpus), "byte_limit": spec["limits"]["corpus_bytes"]})

    # --- A6: the freeze manifest still describes the bytes on disk ---------
    freeze_path = PACKET / "freeze.json"
    if freeze_path.exists():
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
        asset_drift = {}
        for role, name in freeze["assets"].items():
            path = ASSETS / name["file"]
            digest = sha256(path.read_bytes()) if path.exists() else None
            if digest != name["sha256"] or (path.exists() and path.stat().st_size != name["bytes"]):
                asset_drift[role] = {"recorded": name["sha256"][:12], "on_disk": (digest or "absent")[:12]}
        builder_drift = {name: {"recorded": want[:12],
                                "on_disk": sha256((PACKET / name).read_bytes())[:12] if (PACKET / name).exists() else "absent"}
                         for name, want in freeze["code"]["builders"].items()}
        builder_drift = {k: v for k, v in builder_drift.items() if v["recorded"] != v["on_disk"]}
        qrels_pairs = len([line for line in (ASSETS / "qrels.tsv").read_text(encoding="utf-8").splitlines()[1:]
                           if line.strip()])
        counts_ok = (freeze["counts"]["documents"] == len(rows)
                     and freeze["counts"]["queries"] == len(queries)
                     and freeze["counts"]["qrel_pairs"] == qrels_pairs
                     and freeze["counts"]["missing_positive_document_count"] == 0)
        check("A6 freeze.json assets, builders, counts and constants still describe this packet",
              not asset_drift and not builder_drift and counts_ok
              and freeze["source"]["archive_sha256"] == EXPECTED_SHA256
              and freeze["comparison"] == spec["comparison"],
              {"asset_drift": asset_drift, "builder_drift": builder_drift,
               "counts_agree": counts_ok,
               "comparison_equals_spec": freeze["comparison"] == spec["comparison"],
               "snapshot_sha256": freeze["snapshot_sha256"][:16],
               "note": "snapshot itself needs the adapter to recompute; that is freeze.py --check, not this script"})
    else:
        check("A6 freeze.json present", False, {"absent": True})

    # --- B: physical section -> ledger reconciliation ----------------------
    src = SOURCE.read_bytes()
    check("B0 source archive is the frozen volume",
          len(src) == EXPECTED_BYTES and sha256(src) == EXPECTED_SHA256,
          {"bytes": len(src), "sha256": sha256(src)})

    physical = physical_sections(src)
    physical_count = sum(len(v) for v in physical.values())
    root = ET.fromstring(src)
    # Count identifiers as direct children of SECTION. Whole-document iteration
    # would also pick up SECTNO/SUBJECT nested inside citation blocks.
    elements = {"SECTNO": sum(1 for s in root.iter("SECTION") for c in s if c.tag == "SECTNO"),
                "SUBJECT": sum(1 for s in root.iter("SECTION") for c in s if c.tag == "SUBJECT")}
    check("B0b declared identifier counts match the archive",
          elements == manifest["corpus"]["element_counts"]["identifiers"],
          {"recomputed": elements, "declared": manifest["corpus"]["element_counts"]["identifiers"]})

    kept_ids, excluded_ids = set(docs), set(excluded)
    check("B1 no duplicate id inside the corpus or inside the exclusion list",
          len(kept_ids) == len(rows) and len(excluded_ids) == len(manifest["excluded_sections"]),
          {"corpus_rows": len(rows), "corpus_unique": len(kept_ids),
           "excluded_rows": len(manifest["excluded_sections"]), "excluded_unique": len(excluded_ids)})

    # Classify ledger ids by convention. A duplicate section number needs two
    # representations, so accounting is per number, not per id.
    plain, suffixed, ranged, unmapped = [], [], [], []
    for ledger_id in kept_ids | excluded_ids:
        if RANGE_ID.match(ledger_id):
            ranged.append(ledger_id)
        elif SUFFIX_ID.match(ledger_id):
            suffixed.append(ledger_id)
        elif PLAIN_ID.match(ledger_id):
            plain.append(ledger_id)
        else:
            unmapped.append(ledger_id)

    check("B2 every ledger id follows one of the three id conventions in use",
          not unmapped, {"plain": len(plain), "letter_suffixed": len(suffixed),
                         "range": len(ranged), "unmapped": unmapped[:10]})

    letter_base = collections.Counter(SUFFIX_ID.match(i).group(1) for i in suffixed)
    plain_numbers = {PLAIN_ID.match(i).group(1) for i in plain}
    plain_kept = {PLAIN_ID.match(i).group(1) for i in plain if i in kept_ids}
    plain_excluded = {PLAIN_ID.match(i).group(1) for i in plain if i in excluded_ids}

    # Two physical copies share a number when the volume repeats it; the ledger
    # can therefore need two rows for one number, and for 10 numbers it instead
    # reuses one id across "kept" and "excluded" (reported as B5).
    represented = collections.Counter()
    for number in plain_numbers:
        represented[number] = ((1 if number in plain_kept else 0)
                               + (1 if number in plain_excluded else 0)
                               + letter_base.get(number, 0))

    # A range id retires every physical section whose number falls inside it --
    # not every integer in between, since most of those never exist as SECTIONs.
    range_detail = {}
    for ledger_id in ranged:
        lo, hi = RANGE_ID.match(ledger_id).groups()
        inside = [n for n in physical
                  if lo.split(".")[0] == n.split(".")[0] == hi.split(".")[0]
                  and number_key(lo) <= number_key(n) <= number_key(hi)]
        range_detail[ledger_id] = {"sections_inside": len(inside),
                                   "reason": excluded.get(ledger_id, {}).get("reason")}
        for number in inside:
            represented[number] += 1

    mismatched = [{"number": n, "physical_copies": len(c), "ledger": represented.get(n, 0)}
                  for n, c in physical.items() if represented.get(n, 0) != len(c)]
    check("B3 every physical SECTION is accounted for exactly once",
          not mismatched and sum(represented.values()) == physical_count,
          {"physical_sections": physical_count, "distinct_numbers": len(physical),
           "ledger_representations": sum(represented.values()),
           "mismatches": mismatched[:10], "mismatch_count": len(mismatched)})

    duplicates = {n: len(v) for n, v in physical.items() if len(v) > 1}
    suffixed_pairs = sorted(n for n in duplicates if n in letter_base)
    reused_id = sorted(n for n in duplicates if n in plain_excluded and n in plain_kept)
    dropped_both = sorted(set(duplicates) - set(suffixed_pairs) - set(reused_id))
    check("B4 every duplicate number is handled explicitly, by one of three routes",
          sorted(set(suffixed_pairs) | set(reused_id) | set(dropped_both)) == sorted(duplicates),
          {"numbers_appearing_twice": len(duplicates),
           "kept_as_letter_suffixed_pair": suffixed_pairs,
           "one_copy_kept_other_dropped_under_same_id": reused_id,
           "both_copies_dropped": dropped_both})

    overlap = sorted(kept_ids & excluded_ids)
    check("B5 the exclusion ledger never reuses an id that is also a kept document",
          not overlap,
          {"overlap": overlap, "count": len(overlap),
           "consequence": "for these 10 numbers the corpus keeps one copy and the ledger retires the "
                          "other under the same id; a consumer that skips every id present in the "
                          "ledger would drop a kept document. A freeze must key on (id, kept_as) "
                          "or restamp the dropped copy."})

    note("B6 range exclusions retire 20-odd sections per ledger row", True,
         {"range_rows": len(ranged),
          "sections_retired": sum(v["sections_inside"] for v in range_detail.values()),
          "detail": {k: v for k, v in list(range_detail.items())[:6]},
          "note": "a 'no prose' row can cover a whole [Reserved] range, so row counts are not section counts"})

    # --- C: the 85 labelled documents are untouched ------------------------
    m0_rows = read_jsonl(M0_ASSETS / "corpus.jsonl")
    m0_docs = {row["_id"]: row for row in m0_rows}
    m0_freeze = json.loads((M0 / "freeze.json").read_text(encoding="utf-8"))
    m0_sha = sha256((M0_ASSETS / "corpus.jsonl").read_bytes())
    check("C1 M0 corpus still matches its own freeze",
          m0_sha == m0_freeze["assets"]["corpus"]["sha256"] == M0_CORPUS_SHA, {"sha256": m0_sha})

    missing_positives = sorted(set(m0_docs) - set(docs))
    drifted = sorted(i for i, row in m0_docs.items()
                     if i in docs and (docs[i]["text"] != row["text"] or docs[i]["title"] != row["title"]))
    check("C2 all 85 labelled documents are present and byte-identical to M0",
          not missing_positives and not drifted,
          {"m0_documents": len(m0_docs), "present": len(set(m0_docs) & set(docs)),
           "missing": missing_positives, "drifted": drifted})

    check("C3 no labelled document was routed into the exclusion ledger",
          not (set(m0_docs) & excluded_ids),
          {"labelled_in_exclusions": sorted(set(m0_docs) & excluded_ids)})

    design = manifest["design"]
    check("C4 declared design arithmetic: 85 positives + 855 distractors = 940",
          design["positive_pool_documents"] == len(m0_docs)
          and design["distractor_documents"] == len(rows) - len(m0_docs),
          {"declared": {"positives": design["positive_pool_documents"],
                        "distractors": design["distractor_documents"]},
           "recomputed": {"positives": len(m0_docs), "distractors": len(rows) - len(m0_docs)}})

    # --- D: distractor hygiene --------------------------------------------
    manifest_sha = {d["id"]: d["text_sha256"] for d in manifest["documents"]}
    bad_sha = [row["_id"] for row in rows
               if sha256(row["text"].encode("utf-8")) != manifest_sha.get(row["_id"])]
    check("D1 per-document text sha256 matches the manifest",
          not bad_sha, {"checked": len(rows), "mismatches": bad_sha[:10], "mismatch_count": len(bad_sha)})

    empty = [row["_id"] for row in rows if not row["text"].strip()]
    oversized = [row["_id"] for row in rows if len(row["text"]) > MAX_TEXT]
    check("D2 no kept document is empty or above the text ceiling",
          not empty and not oversized,
          {"empty": empty[:10], "oversized": oversized[:10], "ceiling": MAX_TEXT})

    blobs = [(row["title"] + " " + row["text"]).lower() for row in rows]
    markers = {marker: sum(marker in blob for blob in blobs) for marker in THIRD_PARTY}
    check("D3 no kept document contains an incorporation-by-reference clause",
          markers["incorporated by reference"] == 0 and markers["incorporation by reference"] == 0,
          {"marker_counts": markers,
           "note": "4 documents still say 'ANSI' and 1 says 'ASTM' without a formal reference clause; "
                   "reported, not failed"})

    # --- E: inheritance and what a freeze still needs ---------------------
    inherited = {}
    for name, published in (("queries.jsonl", M0_QUERIES_SHA), ("qrels.tsv", M0_QRELS_SHA)):
        digest = sha256((ASSETS / name).read_bytes())
        inherited[name] = {"sha256": digest, "matches_m0": digest == published}
    check("E1 inherited queries and qrels are byte-identical to the M0 packet",
          all(v["matches_m0"] for v in inherited.values()), inherited)

    absent = [name for name in ("freeze.json", "freeze.py", "approval-card.md") if not (PACKET / name).exists()]
    card = (PACKET / "approval-card.md").read_text(encoding="utf-8") if (PACKET / "approval-card.md").exists() else ""
    boxes_ticked = card.count("- [x]") + card.count("- [X]")
    signature = re.search(r"签字人：(\S*)", card)
    signed_name = (signature.group(1) if signature else "").strip()
    by_proxy = "代理" in signed_name or "代记" in card
    note("E2 approval card is signed by proxy, so the scope is needs_review from this round",
         False,
         {"absent": absent, "ticked_boxes": boxes_ticked, "signature": signed_name,
          "signed_by_proxy": by_proxy,
          "needs_review": True,
          "reason": "a periodic check has no user turn; it can read the card but cannot confirm that "
                    "the operator actually granted this scope. Only the operator can clear that."})

    distractor_rows = [row for row in ledger_rows if row[3] == "distractor"]
    note("E3 855 distractor rows rest on a mechanical screen, not a section-by-section review", True,
         {"distractor_rows": len(distractor_rows),
          "screened_in_m0": roles.get("positive", 0),
          "note": "declared in license.md §3 as deliberately over-broad; it is a rights argument, "
                  "not a substitute for review"})

    # --- F: coverage arithmetic for the primary endpoint ------------------
    coverage = {"m0": TOP_K / len(m0_docs), "m1b": TOP_K / len(rows)}
    check("F1 top_k coverage falls from 23.5% to about 2.1%",
          abs(coverage["m0"] - 20 / 85) < 1e-12 and abs(coverage["m1b"] - 20 / 940) < 1e-12
          and coverage["m1b"] < coverage["m0"] / 10,
          {"top_k": TOP_K, "m0_documents": len(m0_docs), "m1b_documents": len(rows),
           "coverage": {k: round(v, 6) for k, v in coverage.items()},
           "note": "a smaller share does not prove recall@20 will vary; that is a measurement, not a derivation"})

    # --- G: prose vs ledger ------------------------------------------------
    claim = re.search(r"(\d+)\s*个条款号各出现两次", report)
    claimed = int(claim.group(1)) if claim else None
    check("G1 extraction report understates how many section numbers repeat",
          claimed == len(duplicates),
          {"report_claims": claimed, "actual": len(duplicates),
           "all_repeats": sorted(duplicates)})

    mentions_436 = bool(re.search(r"§\s*436\.5", report))
    reason_436 = excluded.get("d-16-436.5", {}).get("reason")
    check("G2 extraction report files 436.5 under the size rule; the ledger files it as third-party",
          (not mentions_436) or reason_436 == "extracted text 313225 > 131072",
          {"report_mentions_436.5": mentions_436, "ledger_reason": reason_436,
           "note": "only 425.1 was dropped for size; 436.5 was dropped as a copyright marker"})

    # --- summary ----------------------------------------------------------
    failed = [c["check"] for c in CHECKS if not c["ok"]]
    findings = [c["check"] for c in CHECKS if c.get("kind") == "finding"]
    result = {
        "packet": "m1b-cfr-open-corpus-20261119",
        "verifier": "scripts/crosscheck_m1b_packet.py",
        "independent": "stdlib only; does not import build_packet.py or src.autoresearch",
        "rankings_computed": False,
        "generated_at_local": "2026-11-19 (Asia/Shanghai)",
        "corpus": {"documents": len(rows), "bytes": len(raw_corpus), "sha256": sha256(raw_corpus)},
        "physical_sections": physical_count,
        "excluded_entries": len(excluded),
        "checks_total": len(CHECKS),
        "checks_failed": failed,
        "findings": findings,
        "checks": CHECKS,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed "
          f"({len(CHECKS) - len(failed) - len(findings)} verified, {len(findings)} findings); wrote {out}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
