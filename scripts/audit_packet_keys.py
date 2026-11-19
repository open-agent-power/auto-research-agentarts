"""Audit the document-key contract of the M1b packet, independently.

Why this exists
---------------
The M1b errata (E1) found that 10 document ids appear both in `corpus.jsonl` and in
`manifest.json.excluded_sections`, and proposed to fix the next freeze by moving the key
to `(id, kept_as)`. That remedy has never been tested. This script tests it.

Everything here is recomputed from bytes with the standard library only. It does not
import `src.autoresearch`, so an error in the packet builder cannot hide itself.

  .venv/Scripts/python.exe -B scripts/audit_packet_keys.py
  .venv/Scripts/python.exe -B scripts/audit_packet_keys.py --json runs/m1b-key-audit-20261119/audit.json
"""

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "runs/m1b-packet-20261119"
ASSETS = PACKET / "assets"
SOURCE = ROOT / "runs/source-audit-20261118/CFR-2025-title16-vol1.xml"

SOURCE_SHA = "fbaf04e9bb41f1a8598a9f8f93091f68b5f468b50e4bf481a52abfc64982b3a9"

# The ten ids that exist in both partitions of this frozen packet. Pinned deliberately:
# a rebuild that removes the defect should make K5 report PASS, so this list going stale is
# a signal, not a silent permission. Must stay identical to the allowlist in m1b_preflight.py.
KNOWN_SHARED = {
    "d-16-310.2", "d-16-310.6", "d-16-425.1", "d-16-801.1", "d-16-803.2",
    "d-16-803.5", "d-16-803.8", "d-16-803.9", "d-16-803.10", "d-16-803.12",
}

RESULTS = []


def record(case, state, detail):
    RESULTS.append({"case": case, "state": state, "detail": detail})
    print(f"[{state:<7}] {case}")
    for key, value in detail.items():
        print(f"          {key}: {value}")
    return state


def tag(element):
    return element.tag.split("}")[-1]


def section_number(section):
    for child in section:
        if tag(child) == "SECTNO":
            text = (child.text or "").replace("\u2009", "").replace("\u00a0", " ").strip()
            return re.sub(r"^§\s*", "", text)
    return None


def numeric_stem(number):
    """`3.31A` -> `3.31`; `300.20a` -> `300.20`. The stem is what the letter suffix hangs off."""
    match = re.match(r"^(\d+(?:\.\d+)*)", number or "")
    return match.group(1) if match else (number or "")


def load():
    manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
    corpus = [json.loads(line) for line in
              (ASSETS / "corpus.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    qrels = [line.split("\t") for line in
             (ASSETS / "qrels.tsv").read_text(encoding="utf-8").splitlines() if line.strip()]
    qrels_rows = qrels[1:] if qrels and qrels[0][0].lower().startswith("query") else qrels
    return manifest, corpus, qrels_rows


# --- checks ---------------------------------------------------------------

def check_source():
    data = SOURCE.read_bytes()
    got = hashlib.sha256(data).hexdigest()
    root = ET.fromstring(data)
    sections = [element for element in root.iter() if tag(element) == "SECTION"]
    numbers = [section_number(section) for section in sections]
    missing = sum(1 for number in numbers if not number)
    exact = Counter(numbers)
    exact_dups = {number: count for number, count in exact.items() if count > 1}
    stems = Counter(numeric_stem(number) for number in numbers)
    stem_dups = {stem: count for stem, count in stems.items() if count > 1}
    suffix_pairs = {stem: sorted({n for n in numbers if numeric_stem(n) == stem})
                    for stem in stem_dups if stem not in exact_dups}
    state = "PASS" if got == SOURCE_SHA and not missing else "FAIL"
    return record("K1 source bytes and SECTION census", state,
                  {"sha256": got, "matches_recorded": got == SOURCE_SHA,
                   "section_elements": len(sections), "unparsed_sectno": missing,
                   "exact_duplicate_numbers": len(exact_dups),
                   "numeric_stem_collisions": len(stem_dups),
                   "suffix_only_pairs": {k: v for k, v in sorted(suffix_pairs.items())}}), exact_dups, stem_dups


def check_parts(manifest, section_count, exact_dups):
    documents = manifest["documents"]
    excluded = manifest["excluded_sections"]
    total = len(documents) + len(excluded)
    problems = []
    if total != section_count:
        problems.append(f"{len(documents)} kept + {len(excluded)} excluded != {section_count} sections")
    reasons = Counter()
    for row in excluded:
        reason = row["reason"]
        if reason.startswith("[Reserved]"):
            reasons["no_prose"] += 1
        elif "duplicate section number" in reason:
            reasons["duplicate"] += 1
        elif reason.startswith("extracted text"):
            reasons["oversized"] += 1
        else:
            reasons["third_party"] += 1
    declared = manifest["exclusion_reasons"]
    if dict(reasons) != dict(declared):
        problems.append(f"derived reason counts {dict(reasons)} != declared {declared}")
    duplicate_ids = {f"d-16-{number}" for number in exact_dups}
    recorded_dupes = {r["id"] for r in excluded if "duplicate section number" in r["reason"]}
    if not recorded_dupes <= duplicate_ids:
        problems.append(f"excluded-as-duplicate ids not explained by a real duplicate: "
                        f"{sorted(recorded_dupes - duplicate_ids)}")
    detail = {"kept": len(documents), "excluded": len(excluded), "sections": section_count,
              "reason_counts_derived": dict(reasons), "reason_counts_declared": declared,
              "duplicate_excluded": len(recorded_dupes), "problems": problems}
    return record("K2 kept + excluded reconciles to the SECTION census", "PASS" if not problems else "FAIL",
                  detail)


def check_id_derivation(manifest, corpus):
    bad_kept = [r["id"] for r in manifest["documents"] if r["id"] != "d-16-" + r["sectno"]]
    bad_excluded = [r["id"] for r in manifest["excluded_sections"] if r["id"] != "d-16-" + r["sectno"]]
    bad_corpus = [r["_id"] for r in corpus if not r["_id"].startswith("d-16-")]
    detail = {"id_is_sectno_projection": True,
              "kept_rows_not_following_rule": len(bad_kept),
              "excluded_rows_not_following_rule": len(bad_excluded),
              "corpus_rows_with_foreign_prefix": len(bad_corpus),
              "rule": 'id == "d-16-" + sectno, with no copy index',
              "consequence": "any two sections sharing a SECTNO string collapse onto one id"}
    state = "PASS" if not bad_kept and not bad_excluded and not bad_corpus else "FAIL"
    return record("K3 document id is a lossy projection of the section number", state, detail)


def check_key_candidates(manifest, corpus):
    docs = manifest["documents"]
    excluded = manifest["excluded_sections"]
    corpus_ids = {r["_id"] for r in corpus}
    problem = []

    def collisions(keyfunc):
        pairs = Counter(keyfunc(r, "kept") for r in docs) + Counter(keyfunc(r, "excluded") for r in excluded)
        return sorted({k for k, v in pairs.items() if v > 1})

    by_id = collisions(lambda r, p: r["id"])
    by_id_kept_as = collisions(lambda r, p: (r["id"], r["kept_as"]))
    by_id_partition = collisions(lambda r, p: (r["id"], p))

    if len(corpus_ids) != len(corpus):
        problem.append("corpus ids are not internally unique")
    if len({r["id"] for r in excluded}) != len(excluded):
        problem.append("excluded ids are not internally unique")

    detail = {
        "key_id_collisions": len(by_id),
        "key_id_kept_as_collisions": len(by_id_kept_as),
        "key_id_partition_collisions": len(by_id_partition),
        "id_only_examples": by_id[:3],
        "id_kept_as_examples": [list(k) for k in by_id_kept_as[:3]],
        "remedy_recorded_in_errata": "(id, kept_as)",
        "verdict_on_that_remedy": "INSUFFICIENT" if by_id_kept_as else "SUFFICIENT",
        "problems": problem,
    }
    state = "PASS" if not problem and not by_id_partition else "FAIL"
    return record("K4 which candidate key actually separates the two partitions", state, detail), by_id


def check_discriminator(manifest, shared):
    """Does any *structural* field separate the kept copy from the dropped copy?

    The errata proposes the key `(id, kept_as)`. Structural fields are the ones a key can
    legitimately be built from: id, part, sectno, kept_as. Content fields (chars,
    text_sha256) and one-sided fields (reason) do not count — a join key may not depend on
    the text it is supposed to identify.
    """
    structural = ("id", "part", "sectno", "kept_as")
    rows = []
    for doc_id in shared:
        kept = next(r for r in manifest["documents"] if r["id"] == doc_id)
        dropped = next(r for r in manifest["excluded_sections"] if r["id"] == doc_id)
        differing = [f for f in structural if kept.get(f) != dropped.get(f)]
        rows.append({"id": doc_id, "structural_differing": differing,
                     "kept_as_kept": kept["kept_as"], "kept_as_dropped": dropped["kept_as"],
                     "subject_equal": kept.get("subject") == dropped.get("subject"),
                     "reason": dropped["reason"]})
    no_discriminator = [row["id"] for row in rows if not row["structural_differing"]]
    subject_only = [row["id"] for row in rows if row["subject_equal"] is False]
    detail = {"shared_ids": len(rows),
              "shared_ids_with_no_structural_discriminator": len(no_discriminator),
              "kept_as_identical_on_every_shared_id": len(no_discriminator) == len(rows),
              "subject_differs_on": subject_only,
              "note": "a key cannot be built from the common schema while kept_as is constant; "
                      "subject differs on 1 of 10 and is content, not a key"}
    if not no_discriminator:
        state = "PASS"
    elif set(no_discriminator) == set(shared) == KNOWN_SHARED:
        state = "KNOWN"
    else:
        state = "FAIL"
    return record("K5 no structural field separates the two partitions (documented for this packet)",
                  state, detail), rows


def check_blast_radius(manifest, corpus, qrels_rows, shared):
    qrels_docs = {row[1] for row in qrels_rows}
    positive = {r["id"] for r in manifest["documents"] if r["kept_as"] == "positive_pool"}
    lost = sorted(set(shared) & {r["_id"] for r in corpus})
    lost_in_labels = sorted(set(lost) & qrels_docs)
    lost_in_positive = sorted(set(lost) & positive)
    naive = len([r for r in corpus if r["_id"] in set(shared)])
    detail = {"qrels_rows": len(qrels_rows), "qrels_unique_docs": len(qrels_docs),
              "positive_pool": len(positive),
              "documents_a_skip_the_exclusion_list_consumer_would_drop": naive,
              "dropped_ids_overlapping_labels": len(lost_in_labels),
              "dropped_ids_overlapping_positive_pool": len(lost_in_positive),
              "sample_lost": lost[:4],
              "note": "labels are unaffected today only because all 10 ids sit outside the 11 positive "
                      "Parts; the defect is latent, not harmless by construction"}
    state = "PASS" if not lost_in_labels and not lost_in_positive else "FAIL"
    return record("K6 blast radius of the naive consumer", state, detail)


def check_reid_proposal(manifest, corpus, shared):
    """If the dropped copy had carried a copy index, would the key be clean?"""
    proposed = {}
    for doc_id in shared:
        proposed[doc_id] = ["d-16-" + next(r["sectno"] for r in manifest["documents"] if r["id"] == doc_id) + "#1",
                            "d-16-" + next(r["sectno"] for r in manifest["excluded_sections"] if r["id"] == doc_id) + "#2"]
    keys = list(proposed.values())
    flat = [item for pair in keys for item in pair]
    detail = {"renamed_pairs": len(proposed), "unique_after_rename": len(flat) == len(set(flat)),
              "sample": dict(list(proposed.items())[:2]),
              "note": "re-id requires touching manifest and ledger, i.e. a new packet, not an edit"}
    return record("K7 the re-id remedy does separate them", "PASS" if len(flat) == len(set(flat)) else "FAIL",
                  detail)


def summary():
    failed = [r for r in RESULTS if r["state"] == "FAIL"]
    known = [r for r in RESULTS if r["state"] == "KNOWN"]
    print(f"\n{len(RESULTS) - len(failed) - len(known)}/{len(RESULTS)} invariants hold, "
          f"{len(known)} documented defect, {len(failed)} unexpected failure")
    return 0 if not failed else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    manifest, corpus, qrels_rows = load()
    source = check_source()
    state, exact_dups, stem_dups = source
    check_parts(manifest, 992, exact_dups)
    check_id_derivation(manifest, corpus)
    key_state, shared = check_key_candidates(manifest, corpus)
    disc_state, rows = check_discriminator(manifest, shared)
    check_blast_radius(manifest, corpus, qrels_rows, shared)
    check_reid_proposal(manifest, corpus, shared)

    code = summary()
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload = {"generated_by": "scripts/audit_packet_keys.py",
                   "packet": str(PACKET.relative_to(ROOT)).replace("\\", "/"),
                   "counts": {"exact_duplicate_numbers": len(exact_dups),
                              "numeric_stem_collisions": len(stem_dups),
                              "shared_ids": len(shared)},
                   "checks": RESULTS}
        args.json.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        print(f"wrote {args.json}")
    return code


if __name__ == "__main__":
    sys.exit(main())
