#!/usr/bin/env python3
"""Prepare the fixed ArguAna transfer input, without ranking, fitting or scoring.

The downloaded archives are data. No downloaded program is imported or executed.
All original queries and positive labels survive the procedural split.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

REPO = Path(__file__).resolve().parents[1]
BEIR_SHA = "cfdf79adce27a401b3cd3ea267903134dbfab2c6afeb95d7fe5724a00bf7557b"
SEED = "arguana-transfer-v1"
RULE = "sha256(seed+LF+query_id)_ascending_then_query_id"
COUNTS = {"dev": 80, "validation": 80, "test": 300}
MEMBERS = {"corpus": "arguana/corpus.jsonl", "queries": "arguana/queries.jsonl", "qrels": "arguana/qrels/test.tsv"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def read(path, maximum):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink input is forbidden")
    require(path.is_file() and 0 < path.stat().st_size <= maximum, "Bounded regular input required")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    require(0 < len(raw) <= maximum, "Input grew beyond limit")
    return raw


def write(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.absolute()
    scratch = Path("/workspace/work")
    require(output != scratch and output.is_relative_to(scratch) and ".." not in output.parts,
            "Preparation output must be a fresh scratch directory")
    require(not output.exists() and not any(p.is_symlink() for p in output.parents), "Never overwrite prepared evidence")
    data = args.data_dir.absolute()
    receipt_raw = read(data / "arguana-source-admission.json", 65536)
    receipt = json.loads(receipt_raw)
    require(receipt["schema_version"] == "retrieval-transfer-origin-receipt-v1"
            and receipt["status"] == "admitted_for_bounded_local_research"
            and receipt["license"] == "CC-BY-4.0" and receipt["version_doi"] == "10.5281/zenodo.3973258",
            "An explicit reviewed source admission is required")
    originals = {}
    for role in ("beir_archive", "original_archive", "webis_official_source", "zenodo_official_record"):
        item = receipt["artifacts"][role]
        require(PurePosixPath(item["file_name"]).name == item["file_name"], "Artifact name must be a basename")
        raw = read(data / item["file_name"], 120 * 1024 * 1024)
        require(len(raw) == item["bytes"] and sha(raw) == item["sha256"], "Original artifact identity changed")
        originals[role] = raw
    require(sha(originals["beir_archive"]) == BEIR_SHA, "Use the audited BEIR ArguAna archive")
    zenodo = json.loads(originals["zenodo_official_record"])
    require(type(zenodo["id"]) is int and zenodo["id"] == 3973258
            and zenodo["doi"] == "10.5281/zenodo.3973258"
            and zenodo["metadata"]["license"]["id"] == "cc-by-4.0", "Official version/license does not match")
    files = zenodo["files"]
    require(len(files) == 1 and files[0]["key"] == "arguana-counterargs-corpus.zip"
            and type(files[0]["size"]) is int and files[0]["size"] == len(originals["original_archive"])
            and files[0]["checksum"] == "md5:" + hashlib.md5(originals["original_archive"]).hexdigest(),
            "Original archive differs from the official version checksum")
    require(b"creativecommons.org/licenses/by/4.0/" in originals["webis_official_source"],
            "Official Webis source must corroborate the licence")
    from io import BytesIO
    assets = {}
    with zipfile.ZipFile(BytesIO(originals["beir_archive"])) as archive:
        infos = archive.infolist()
        require(len(infos) <= 20 and len({info.filename for info in infos}) == len(infos), "Archive member count/uniqueness changed")
        require(sum(info.file_size for info in infos) <= 16_000_000, "Expanded archive exceeds cap")
        for info in infos:
            name = PurePosixPath(info.filename)
            require(not name.is_absolute() and ".." not in name.parts and "\\" not in info.filename
                    and not info.flag_bits & 1 and (info.external_attr >> 16) & 0o170000 != 0o120000,
                    "Unsafe/encrypted archive member")
            raw = archive.read(info)  # ZIP CRC is checked, never filesystem extract.
            for role, expected in MEMBERS.items():
                if info.filename == expected:
                    assets[role] = raw
    require(set(assets) == set(MEMBERS), "All exact dataset members are required")
    queries = [json.loads(line) for line in assets["queries"].decode("utf-8").split("\n") if line.strip()]
    qids = [row["_id"] for row in queries]
    require(len(qids) == 1406 and len(set(qids)) == 1406, "Full original query population required")
    ordered = sorted(qids, key=lambda qid: (sha((SEED + "\n" + qid).encode("utf-8")), qid))
    splits, cursor = {}, 0
    for split, count in COUNTS.items():
        splits[split] = ordered[cursor:cursor + count]
        cursor += count
    selection = {"schema_version": "retrieval-transfer-selection-v1", "seed": SEED, "rule": RULE,
                 "archive_sha256": BEIR_SHA, "population_query_ids_sha256": sha(canonical(sorted(qids)).encode()),
                 "population_count": len(qids), "evaluated_count": cursor, "counts": COUNTS,
                 "query_splits": splits, "remainder_queries": len(qids) - cursor,
                 "original_split": "BEIR test only; procedural partition, not official split"}
    selection_raw = (canonical(selection) + "\n").encode()
    # Partition complete original TSV physical records. There is no grade change,
    # per-query truncation, document filtering or target-performance selection.
    lines = assets["qrels"].splitlines(keepends=True)
    require(lines[0].rstrip(b"\r\n") == b"query-id\tcorpus-id\tscore", "Exact TSV header required")
    train_ids = set(splits["dev"] + splits["validation"])
    train, test, seen = [lines[0]], [lines[0]], set()
    for line in lines[1:]:
        qid, doc, grade = line.decode("utf-8").rstrip("\r\n").split("\t")
        require(qid in qids and grade == "1" and (qid, doc) not in seen, "Original positive labels changed")
        seen.add((qid, doc))
        (train if qid in train_ids else test).append(line)
    require(len(seen) == 1406 and {q for q, _ in seen} == set(qids), "Every original query/judgment must survive")
    license_raw = ("ArguAna Counterargs. Henning Wachsmuth, Shahbaz Syed, Benno Stein.\n"
                   "Official version: https://doi.org/10.5281/zenodo.3973258\n"
                   "Official site: https://webis.de/data/arguana-counterargs.html\n"
                   "CC BY 4.0: https://creativecommons.org/licenses/by/4.0/\n"
                   "Changes: use the archived BEIR corpus/query representation; preserve full original BEIR text, "
                   "all grades and judgments, partition qrels by a fixed query-ID hash into procedural splits. "
                   "Rankings exclude same query/document IDs. Missing positive documents remain in recall denominators. "
                   "This 460-query derived comparison is not the canonical full BEIR leaderboard.\n"
                   "Receipt SHA256: " + sha(receipt_raw) + "\n").encode()
    sys.path.insert(0, str(REPO / "src"))
    from autoresearch import relevance_retrieval_adapter as adapter
    spec = {"schema_version": "relevance-retrieval-spec-v1", "dataset_label": "ArguAna best-counterargument retrieval; frozen SHA subset, procedural splits",
            "source_url": "https://doi.org/10.5281/zenodo.3973258", "attribution": "Henning Wachsmuth, Shahbaz Syed, Benno Stein; ArguAna Counterargs; CC BY 4.0; BEIR archived representation with declared procedural split.",
            "license_notes": {"corpus": "CC BY 4.0; preserve authorship, official version DOI and changes notice.",
                              "queries_and_qrels": "CC BY 4.0; best-counterargument positive relevance labels, not citation or support/refute claims."},
            "source_provenance": {"archive_sha256": BEIR_SHA, "source_receipt_sha256": sha(receipt_raw),
                                  "selection_sha256": sha(selection_raw), "qrels_semantics": adapter.SEMANTICS},
            "files": adapter.FILES, "query_splits": splits, "comparison": adapter.COMPARISON, "limits": adapter.LIMITS}
    output.mkdir(parents=True)
    for name, raw in {"corpus.jsonl": assets["corpus"], "queries.jsonl": assets["queries"],
                      "qrels-train.tsv": b"".join(train), "qrels-test.tsv": b"".join(test),
                      "license.md": license_raw, "spec.json": canonical(spec).encode(),
                      "selection.json": selection_raw, "origin-receipt.json": receipt_raw}.items():
        write(output / name, raw)
    # Capture is schema-only. Reject accidental future research calls during prep.
    from contextlib import ExitStack
    from unittest.mock import patch
    from autoresearch import retrieval_lexical
    def forbidden(*args, **kwargs):
        raise AssertionError("No research computation during source preparation")
    with ExitStack() as guards:
        for module, names in ((retrieval_lexical, ("build_index", "retrieve", "metrics", "tokens")),
                              (adapter, ("execute", "retrieve"))):
            for name in names:
                guards.enter_context(patch.object(module, name, side_effect=forbidden))
        packet = adapter.capture_source(output)
    packet_raw = canonical(packet).encode()
    require(len(packet_raw) <= 16_000_000, "Native core source cap exceeded; do not truncate or retry with changed data")
    write(output / "source.json", packet_raw)
    result = {"schema_version": "retrieval-transfer-preparation-v1", "status": "prepared_not_evaluated",
              "packet": {"bytes": len(packet_raw), "sha256": sha(packet_raw)}, "snapshot_sha256": packet["snapshot_sha256"],
              "selection_sha256": sha(selection_raw), "source_receipt_sha256": sha(receipt_raw),
              "full_original_beir_assets_preserved": True, "qrel_pairs": len(seen), "qrel_partition_counts": {"train": len(train)-1, "test": len(test)-1},
              "research_ranking_calls": 0, "research_scoring_calls": 0, "new_fits": 0, "product_model_calls": 0,
              "scope": packet["scope"]}
    write(output / "preparation.json", (canonical(result) + "\n").encode())
    print(canonical({key: value for key, value in result.items() if key != "scope"}))


if __name__ == "__main__":
    main()
