"""Bounded positive-relevance retrieval pair and saved-only audit; no model calls."""
import base64
import binascii
import copy
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics
import time

from . import retrieval_lexical as lexical, source_evidence_adapter as reader
from .contracts import ResearchError, canonical, fingerprint, identifier

TOOL_ID = "research.relevance-fixed-pair"
AUDIT_TOOL_ID = "research.relevance-saved-error-audit"
ADAPTER_VERSION = "1"
FILES = {"corpus": "corpus.jsonl", "queries": "queries.jsonl", "train_qrels": "qrels-train.tsv", "test_qrels": "qrels-test.tsv", "license": "license.md"}
LIMITS = {"corpus_bytes": 12582912, "queries_bytes": 3145728, "qrels_bytes": 1048576, "license_bytes": 65536,
          "all_asset_bytes": 11800000, "spec_bytes": 65536, "packet_bytes": 16000000,
          "max_corpus_rows": 10000, "max_queries": 2000, "max_qrel_pairs": 20000, "max_query_text": 32768}
COMPARISON = {"baseline": "bm25", "candidate": "tfidf_cosine", "top_k": 20, "k1": 1.2, "b": .75,
              "tokenizer": "ascii_alnum_lower_v1", "tie_break": "doc_id_ascending", "ignore_identical_ids": True,
              "missing_document_policy": "retain_in_denominator", "metrics": list(lexical.METRICS)}
MAX_RESULT_BYTES = 4 * 1024 * 1024
SEMANTICS = "positive_relevance_binary_projection"
NOTES = ["Positive source grades 1/2 are retained; metrics use a grade>0 binary relevance projection.",
         "Binary nDCG is not canonical graded BEIR nDCG; unjudged documents are treated as nonrelevant operationally.",
         "Identical query/document IDs are excluded before selecting the top 20; index statistics remain unchanged.",
         "Missing positive document IDs remain in the relevance denominator and cannot be retrieved; none are silently dropped.",
         "Input provenance and licence metadata are host declarations; capture does not independently verify their truth.",
         "Original metadata is opaque and never supplied to ranking or scoring.",
         "Public labels and same-user procedural separation are not sealed evaluation or scientific validation."]



def _require(value, code, message):
    if not value:
        raise ResearchError(code, message)


def _object(value, keys, name):
    _require(type(value) is dict and set(value) == set(keys), "INVALID_SOURCE", "Unexpected fields in " + name)


def _text(value, maximum, empty=False):
    if type(value) is not str or len(value) > maximum or "\x00" in value or (not empty and not value.strip()):
        return False
    try:
        value.encode("utf-8")
        return True
    except UnicodeError:
        return False


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _decode(raw):
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise ResearchError("INVALID_SOURCE", "Strict UTF-8 input is required") from None
    _require("\x00" not in text, "INVALID_SOURCE", "NUL input is forbidden")
    return text


def _parse(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            _require(key not in result, "INVALID_SOURCE", "Duplicate JSON member")
            result[key] = value
        return result
    def nonfinite(_):
        raise ResearchError("INVALID_SOURCE", "Nonfinite JSON is forbidden")
    try:
        return json.loads(_decode(raw), object_pairs_hook=pairs, parse_constant=nonfinite)
    except (ValueError, RecursionError):
        raise ResearchError("INVALID_SOURCE", "Malformed strict JSON") from None


def _spec(spec):
    _object(spec, ("schema_version", "dataset_label", "source_url", "attribution", "license_notes", "source_provenance", "files", "query_splits", "comparison", "limits"), "spec")
    _require(spec["schema_version"] == "relevance-retrieval-spec-v1" and spec["files"] == FILES
             and canonical(spec["comparison"]) == canonical(COMPARISON) and spec["limits"] == LIMITS, "INVALID_SOURCE", "Use the fixed retrieval protocol, files and limits")
    _require(all(type(value) is int for value in spec["limits"].values()) and type(spec["comparison"]["top_k"]) is int
             and spec["comparison"]["ignore_identical_ids"] is True
             and all(type(spec["comparison"][key]) is float for key in ("k1", "b")), "INVALID_SOURCE", "Protocol numeric types must be exact")
    for name, limit in (("dataset_label", 300), ("source_url", 2000), ("attribution", 4000)):
        _require(_text(spec[name], limit), "INVALID_SOURCE", "Invalid " + name)
    _object(spec["license_notes"], ("corpus", "queries_and_qrels"), "licence notes")
    _require(all(_text(value, 4000) for value in spec["license_notes"].values()), "INVALID_SOURCE", "Licence notes required")
    provenance = spec["source_provenance"]
    _object(provenance, ("archive_sha256", "source_receipt_sha256", "selection_sha256", "qrels_semantics"), "provenance")
    _require(all(_digest(provenance[name]) for name in ("archive_sha256", "source_receipt_sha256", "selection_sha256"))
             and provenance["qrels_semantics"] == SEMANTICS, "INVALID_SOURCE", "Invalid provenance identities/semantics")
    _object(spec["query_splits"], ("dev", "validation", "test"), "query splits")
    all_ids = []
    for values in spec["query_splits"].values():
        _require(type(values) is list and 1 <= len(values) <= LIMITS["max_queries"] and all(_text(x, 80) for x in values), "INVALID_SOURCE", "Invalid nonempty query split")
        all_ids.extend(values)
    _require(len(all_ids) <= LIMITS["max_queries"] and len(set(all_ids)) == len(all_ids), "INVALID_SOURCE", "Splits must be disjoint and duplicate-free")


def _asset(name, raw):
    return {"file_name": name, "sha256": _sha(raw), "bytes": len(raw), "bytes_base64": base64.b64encode(raw).decode("ascii")}


def _asset_limit(role):
    return LIMITS["qrels_bytes"] if role.endswith("qrels") else LIMITS[role + "_bytes"]


def _asset_raw(asset, name, maximum):
    _object(asset, ("file_name", "sha256", "bytes", "bytes_base64"), "asset")
    _require(asset["file_name"] == name and type(asset["bytes"]) is int and 0 < asset["bytes"] <= maximum
             and _digest(asset["sha256"]) and type(asset["bytes_base64"]) is str
             and len(asset["bytes_base64"]) <= 4 * ((maximum + 2)//3), "INVALID_SOURCE", "Invalid asset metadata/size/name")
    try:
        raw = base64.b64decode(asset["bytes_base64"], validate=True)
    except (ValueError, binascii.Error):
        raise ResearchError("INVALID_SOURCE", "Strict Base64 is required") from None
    _require(len(raw) == asset["bytes"] and _sha(raw) == asset["sha256"]
             and base64.b64encode(raw).decode("ascii") == asset["bytes_base64"], "EVIDENCE_CHANGED", "Asset bytes/identity differ")
    return raw


def _metadata(value):
    _require(type(value) is dict, "INVALID_SOURCE", "Metadata must be an opaque JSON object")
    pending, nodes = [(value, 1)], 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        _require(nodes <= 512 and depth <= 8, "INVALID_SOURCE", "Opaque metadata exceeds node/depth bounds")
        if type(item) is dict:
            for key, child in item.items():
                nodes += 1
                _require(nodes <= 512 and _text(key,128,empty=True), "INVALID_SOURCE", "Invalid metadata key")
                pending.append((child,depth+1))
        elif type(item) is list:
            _require(len(item) <= 512, "INVALID_SOURCE", "Oversized metadata list")
            pending.extend((child,depth+1) for child in item)
        elif type(item) is str:
            _require(_text(item,4096,empty=True), "INVALID_SOURCE", "Invalid metadata string")
        else:
            _require(item is None or type(item) in (bool,int) or (type(item) is float and math.isfinite(item)),
                     "INVALID_SOURCE", "Metadata contains a non-JSON/nonfinite primitive")
    _require(len(canonical(value).encode("utf-8")) <= 16384, "INVALID_SOURCE", "Opaque metadata exceeds 16 KiB")


def _jsonl(raw, corpus):
    rows, lines = {}, {}
    # JSONL physical records use LF (with an optional preceding CR), not every
    # Unicode character Python's str.splitlines classifies as a line separator.
    for line_number, line in enumerate(_decode(raw).split("\n"), 1):
        if not line.strip():
            continue
        row = _parse(line.encode("utf-8"))
        _object(row, ("_id", "title", "text", "metadata") if corpus else ("_id", "text", "metadata"), "JSONL row")
        _metadata(row["metadata"])
        _require(_text(row["_id"], 80) and row["_id"] not in rows
                 and _text(row["text"], 131072 if corpus else LIMITS["max_query_text"], empty=corpus)
                 and (not corpus or _text(row["title"], 4096, empty=True)), "INVALID_SOURCE", "Invalid or duplicate corpus/query record")
        rows[row["_id"]], lines[row["_id"]] = row, line_number
        _require(len(rows) <= LIMITS["max_corpus_rows" if corpus else "max_queries"], "SOURCE_TOO_LARGE", "Too many JSONL rows")
    _require(bool(rows), "INVALID_SOURCE", "Empty corpus/queries")
    return rows, lines


def _qrels(raw, docs, queries):
    parser = csv.reader(io.StringIO(_decode(raw), newline=""), delimiter="\t", strict=True)
    _require(next(parser, None) == ["query-id", "corpus-id", "score"], "INVALID_SOURCE", "Exact qrels TSV header required")
    rows, count = {}, 0
    for row in parser:
        _require(len(row) == 3, "INVALID_SOURCE", "Exact qrels width required")
        query, doc, score = row
        _require(query in queries and _text(doc, 80) and score in ("1", "2") and doc not in rows.setdefault(query, {}),
                 "INVALID_SOURCE", "Invalid qrels foreign key, score or duplicate")
        rows[query][doc] = int(score)
        count += 1
        _require(count <= LIMITS["max_qrel_pairs"], "SOURCE_TOO_LARGE", "Too many qrels")
    _require(bool(rows), "INVALID_SOURCE", "Empty qrels")
    return rows


def _scope(spec, assets, docs, queries, qrels):
    missing = sorted({doc for split in qrels.values() for values in split.values() for doc in values if doc not in docs})
    return {"domain": "retrieval", "contract": "relevance-retrieval-fixed-pair-v1", "dataset_label": spec["dataset_label"],
        "document_count": len(docs), "query_count": len(queries), "qrels_semantics": SEMANTICS,
        "input_identities": {role: {key: asset[key] for key in ("sha256", "bytes")} for role, asset in assets.items()},
        "comparison_sha256": fingerprint(spec["comparison"]),
        "missing_positive_document_ids": missing, "missing_positive_document_count": len(missing),
        "missing_positive_qrel_pairs": sum(doc not in docs for split in qrels.values() for values in split.values() for doc in values)}


def _checked(payload):
    try:
        _object(payload, ("schema_version", "task_kind", "spec_source", "assets", "spec", "scope", "snapshot_sha256"), "source packet")
        _require(payload["schema_version"] == "cpu-research-source-v1" and payload["task_kind"] == "relevance_retrieval"
                 and payload["snapshot_sha256"] == fingerprint({k: v for k,v in payload.items() if k != "snapshot_sha256"}), "EVIDENCE_CHANGED", "Source snapshot identity changed")
        _require(len(canonical(payload).encode("utf-8")) <= LIMITS["packet_bytes"], "SOURCE_TOO_LARGE", "Encoded source packet exceeds limit")
        spec = _parse(_asset_raw(payload["spec_source"], "spec.json", LIMITS["spec_bytes"]))
        _spec(spec)
        _require(canonical(spec) == canonical(payload["spec"]), "EVIDENCE_CHANGED", "Parsed spec differs from original bytes/types")
        _object(payload["assets"], FILES, "assets")
        raw = {role: _asset_raw(payload["assets"][role], name, _asset_limit(role)) for role, name in FILES.items()}
        _require(sum(map(len, raw.values())) <= LIMITS["all_asset_bytes"], "SOURCE_TOO_LARGE", "Aggregate original bytes exceed limit")
        _decode(raw["license"])
        docs, doc_lines = _jsonl(raw["corpus"], True)
        queries, query_lines = _jsonl(raw["queries"], False)
        qrels = {name: _qrels(raw[role], docs, queries) for name,role in (("train", "train_qrels"), ("test", "test_qrels"))}
        _require(not set(qrels["train"]) & set(qrels["test"]), "INVALID_SOURCE", "Train/test qrels query overlap")
        _require(sum(sum(map(len, value.values())) for value in qrels.values()) <= LIMITS["max_qrel_pairs"], "SOURCE_TOO_LARGE", "Aggregate qrels count exceeds limit")
        for split, ids in spec["query_splits"].items():
            _require(set(ids) <= set(qrels["test" if split == "test" else "train"]), "INVALID_SOURCE", "Split has unlabeled/unknown queries")
        _require(canonical(payload["scope"]) == canonical(_scope(spec, payload["assets"], docs, queries, qrels)),
                 "EVIDENCE_CHANGED", "Derived source scope values/types changed")
        return spec, docs, queries, qrels, doc_lines, query_lines
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError, OverflowError, RecursionError, csv.Error):
        raise ResearchError("INVALID_SOURCE", "Malformed bounded retrieval source") from None


def load_source(raw):
    _require(type(raw) is bytes and 0 < len(raw) <= LIMITS["packet_bytes"], "SOURCE_TOO_LARGE", "Bounded source bytes required")
    payload = _parse(raw)
    _checked(payload)
    return payload


def capture_source(directory):
    root = Path(directory).absolute()
    raw = {"spec": reader._read_file(root / "spec.json", LIMITS["spec_bytes"])}
    spec = _parse(raw["spec"])
    _spec(spec)
    for role, name in FILES.items():
        raw[role] = reader._read_file(root / name, _asset_limit(role))
    assets = {role: _asset(name, raw[role]) for role, name in FILES.items()}
    docs, _ = _jsonl(raw["corpus"], True)
    queries, _ = _jsonl(raw["queries"], False)
    qrels = {name: _qrels(raw[role], docs, queries) for name, role in (("train", "train_qrels"), ("test", "test_qrels"))}
    payload = {"schema_version": "cpu-research-source-v1", "task_kind": "relevance_retrieval",
        "spec_source": _asset("spec.json", raw["spec"]), "assets": assets, "spec": spec, "scope": _scope(spec, assets, docs, queries, qrels)}
    payload["snapshot_sha256"] = fingerprint(payload)
    _checked(payload)
    for role, content in raw.items():
        name, maximum = ("spec.json", LIMITS["spec_bytes"]) if role == "spec" else (FILES[role], _asset_limit(role))
        _require(reader._read_file(root / name, maximum) == content, "EVIDENCE_CHANGED", "Source changed during capture")
    return payload


def code_identity():
    return _sha(Path(__file__).read_bytes() + Path(lexical.__file__).read_bytes() + reader.code_identity().encode("ascii"))


def retrieve(query, index, method, *, exclude_doc_id):
    """Fixed lexical scores with the declared identical-ID exclusion.

    Exclude before the top-k cutoff, retaining the next eligible hit. Corpus
    statistics include the entire frozen corpus, as in BEIR's ID filtering.
    """
    from collections import Counter, defaultdict

    postings, lengths, idfs, norms, n, avgdl = index
    counts = Counter(lexical.tokens(query))
    scores = defaultdict(float)
    if method == "tfidf_cosine":
        weights = {term: (1 + math.log(count)) * idfs[term]
                   for term, count in counts.items() if term in idfs}
        qnorm = math.sqrt(sum(value * value for value in weights.values()))
        for term, weight in weights.items():
            for doc, tf in postings[term]:
                scores[doc] += weight * ((1 + math.log(tf)) * idfs[term]) / (qnorm * norms[doc])
    elif method == "bm25":
        k1, b = COMPARISON["k1"], COMPARISON["b"]
        for term in counts:
            rows = postings.get(term, ())
            idf = math.log(1 + (n - len(rows) + .5) / (len(rows) + .5))
            for doc, tf in rows:
                scores[doc] += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * lengths[doc] / avgdl))
    else:
        raise ResearchError("INVALID_REQUEST", "Unknown fixed relevance method")
    return sorted((doc for doc in scores if doc != exclude_doc_id),
                  key=lambda doc: (-scores[doc], doc))[:COMPARISON["top_k"]]


def _references(payload):
    return [{"source_snapshot_sha256": payload["snapshot_sha256"], "source_sha256": asset["sha256"], "file_name": asset["file_name"],
             "url": payload["spec"]["source_url"], "license_note": payload["spec"]["license_notes"]["corpus" if role == "corpus" else "queries_and_qrels"],
             "locator": {"kind": "jsonl_records" if role in ("corpus", "queries") else "whole_original", "role": role}}
            for role, asset in payload["assets"].items()]


def _paired(rows):
    by_pair = {}
    for row in rows:
        by_pair.setdefault((row["split"], row["query_id"]), {})[row["method"]] = row["metrics"]
    deltas, adverse = [], []
    for (split, qid), pair in by_pair.items():
        delta = {name: pair["tfidf_cosine"][name]-pair["bm25"][name] for name in lexical.METRICS}
        item = {"split": split, "query_id": qid, "delta": delta, "loss_metrics": [name for name,value in delta.items() if value < -1e-12],
                "gain_metrics": [name for name,value in delta.items() if value > 1e-12], "tie_metrics": [name for name,value in delta.items() if abs(value) <= 1e-12],
                "baseline": pair["bm25"], "candidate": pair["tfidf_cosine"]}
        deltas.append(item)
        if item["loss_metrics"] or min(pair["bm25"]["recall@20"], pair["tfidf_cosine"]["recall@20"]) < 1:
            adverse.append(copy.deepcopy(item))
    splits = {}
    for split in ("dev", "validation", "test"):
        selected = [row for row in rows if row["split"] == split]
        arms = {method: {"queries": len(selected)//2,
            "metrics": {name: statistics.mean(row["metrics"][name] for row in selected if row["method"] == method) for name in lexical.METRICS}}
            for method in lexical.METHODS}
        changes = [row for row in deltas if row["split"] == split]
        splits[split] = {"arms": arms, "paired_candidate_minus_baseline": {name: {
            "mean": statistics.mean(row["delta"][name] for row in changes),
            "wins": sum(row["delta"][name] > 1e-12 for row in changes), "ties": sum(abs(row["delta"][name]) <= 1e-12 for row in changes),
            "losses": sum(row["delta"][name] < -1e-12 for row in changes)} for name in lexical.METRICS}}
    return {"splits": splits}, deltas, adverse


def _tool(tool_id, result, kind, summary, refs):
    tool = {"schema_version": "relevance-retrieval-result-v1" if tool_id == TOOL_ID else "relevance-saved-error-result-v1",
        "tool_id": tool_id, "adapter_version": ADAPTER_VERSION, "status": "completed",
        "observations": [{"producer": tool_id, "kind": kind, "summary": copy.deepcopy(summary), "scope": copy.deepcopy(result["scope"]),
            "evidence_refs": copy.deepcopy(refs), "interpretation_status": "computed_binary_relevance_not_scientific_review", "scientific_validation": False}],
        "evidence_refs": copy.deepcopy(refs), "metrics": [{"name": "analyzed_query_pairs", "value": summary["query_pairs"], "unit": "query"}],
        "result": result, "failure": None, "model_calls": 0, "new_fits": 0, "scientific_validation": False}
    _require(len(canonical(tool).encode("utf-8")) <= MAX_RESULT_BYTES, "RESULT_TOO_LARGE", "Complete retrieval result exceeds 4 MiB")
    return tool


def execute(payload, dimension=None):
    _require(dimension is None, "INVALID_REQUEST", "Retrieval primary has no free execution parameters")
    spec, docs, queries, qrels, doc_lines, query_lines = _checked(payload)
    started = time.perf_counter()
    index = lexical.build_index(docs)
    index_seconds = time.perf_counter()-started
    rankings = []
    for split in ("dev", "validation", "test"):
        for qid in spec["query_splits"][split]:
            for method in lexical.METHODS:
                start = time.perf_counter()
                rank = retrieve(queries[qid]["text"], index, method, exclude_doc_id=qid)
                rankings.append({"split": split, "query_id": qid, "method": method, "ranking": rank,
                    "ranking_seconds": time.perf_counter()-start, "query_line": query_lines[qid], "ranked_doc_lines": [doc_lines[d] for d in rank]})
    # Complete ranking data is hashed before the first metric/scoring call. The
    # native core persists it in the final immutable action, not a hidden disk checkpoint.
    ranks_sha = fingerprint(rankings)
    scored = [{"split": row["split"], "query_id": row["query_id"], "method": row["method"],
        "metrics": lexical.metrics(row["ranking"], qrels["test" if row["split"] == "test" else "train"][row["query_id"]]),
        "qrel_locator": {"kind": "tsv_query_documents", "role": "test_qrels" if row["split"] == "test" else "train_qrels",
            "source_sha256": payload["assets"]["test_qrels" if row["split"] == "test" else "train_qrels"]["sha256"],
            "query_id": row["query_id"], "document_ids": sorted(qrels["test" if row["split"] == "test" else "train"][row["query_id"]]),
            "document_grades": copy.deepcopy(qrels["test" if row["split"] == "test" else "train"][row["query_id"]])}}
        for row in rankings]
    summary, _, adverse = _paired(scored)
    result = {"scope": copy.deepcopy(payload["scope"]), "source_snapshot_sha256": payload["snapshot_sha256"], "comparison": copy.deepcopy(COMPARISON),
        "rankings": rankings, "rankings_before_scoring_sha256": ranks_sha, "per_query_metrics": scored,
        "paired_summary": summary, "adverse_queries": adverse,
        "usage": {"index_builds": 1, "ranking_calls": len(rankings), "scoring_calls": len(scored), "query_pairs": len(scored)//2,
                  "corpus_records": len(docs), "index_seconds": index_seconds, "native_fits": 0, "model_calls": 0}, "limitations": copy.deepcopy(NOTES)}
    return _tool(TOOL_ID, result, "relevance_retrieval_pair", {"query_pairs": len(scored)//2, "paired_summary": summary, "adverse_queries": len(adverse)}, _references(payload))


def _saved_checked(original):
    _require(type(original) is dict and original.get("tool_id") == TOOL_ID and original.get("status") == "completed"
             and original.get("schema_version") == "relevance-retrieval-result-v1" and original.get("scientific_validation") is False
             and original.get("adapter_version") == ADAPTER_VERSION
             and all(type(original.get(key)) is int and original[key] == 0 for key in ("new_fits","model_calls")),
             "INVALID_RESULT", "A completed fixed-pair ToolResult is required")
    result = original["result"]
    _require(type(result) is dict and len(canonical(original).encode("utf-8")) <= MAX_RESULT_BYTES,
             "INVALID_RESULT", "Malformed/oversized saved retrieval result")
    _require(canonical(result["comparison"]) == canonical(COMPARISON) and _digest(result["source_snapshot_sha256"])
             and result["rankings_before_scoring_sha256"] == fingerprint(result["rankings"]), "EVIDENCE_CHANGED", "Saved retrieval result identity changed")
    scope = result["scope"]
    _object(scope, ("domain", "contract", "dataset_label", "document_count", "query_count", "qrels_semantics",
                    "input_identities", "comparison_sha256", "missing_positive_document_ids",
                    "missing_positive_document_count", "missing_positive_qrel_pairs"), "saved relevance scope")
    _require(scope["domain"] == "retrieval" and scope["contract"] == "relevance-retrieval-fixed-pair-v1"
             and scope["qrels_semantics"] == SEMANTICS and _text(scope["dataset_label"], 300)
             and scope["comparison_sha256"] == fingerprint(COMPARISON)
             and all(type(scope[key]) is int and 1 <= scope[key] <= LIMITS[maximum]
                     for key, maximum in (("document_count", "max_corpus_rows"), ("query_count", "max_queries"))),
             "INVALID_RESULT", "Saved relevance scope differs from the declared contract")
    _object(scope["input_identities"], FILES, "saved input identities")
    for role, asset in scope["input_identities"].items():
        _object(asset, ("sha256", "bytes"), "saved asset identity")
        _require(_digest(asset["sha256"]) and type(asset["bytes"]) is int and 0 < asset["bytes"] <= _asset_limit(role),
                 "INVALID_RESULT", "Invalid saved input identity")
    missing = scope["missing_positive_document_ids"]
    _require(type(missing) is list and all(_text(doc, 80) for doc in missing)
             and missing == sorted(set(missing))
             and type(scope["missing_positive_document_count"]) is int and scope["missing_positive_document_count"] == len(missing)
             and type(scope["missing_positive_qrel_pairs"]) is int
             and len(missing) <= scope["missing_positive_qrel_pairs"] <= LIMITS["max_qrel_pairs"],
             "INVALID_RESULT", "Invalid saved missing-document accounting")
    rows, seen = result["per_query_metrics"], set()
    _require(type(rows) is list and 6 <= len(rows) <= 2 * LIMITS["max_queries"], "INVALID_RESULT", "Invalid saved query coverage")
    for row in rows:
        key = (row["split"], row["query_id"], row["method"])
        _require(row["split"] in ("dev", "validation", "test") and _text(row["query_id"], 80) and row["method"] in lexical.METHODS
                 and key not in seen and type(row["metrics"]) is dict and set(row["metrics"]) == set(lexical.METRICS)
                 and all(type(x) in (int,float) and math.isfinite(x) and 0 <= x <= 1 for x in row["metrics"].values()), "INVALID_RESULT", "Invalid saved metrics")
        locator = row["qrel_locator"]
        role = "test_qrels" if row["split"] == "test" else "train_qrels"
        _object(locator, ("kind", "role", "source_sha256", "query_id", "document_ids", "document_grades"), "saved qrel locator")
        grades = locator["document_grades"]
        _require(locator["kind"] == "tsv_query_documents" and locator["role"] == role
                 and locator["source_sha256"] == scope["input_identities"][role]["sha256"]
                 and locator["query_id"] == row["query_id"] and type(grades) is dict and bool(grades)
                 and len(grades) <= LIMITS["max_qrel_pairs"]
                 and all(_text(doc, 80) and type(grade) is int and grade in (1, 2) for doc, grade in grades.items())
                 and locator["document_ids"] == sorted(grades), "INVALID_RESULT", "Invalid saved original grades/locators")
        seen.add(key)
    expected = {(split,qid,method) for split,qid,_ in seen for method in lexical.METHODS}
    _require(seen == expected and {row["split"] for row in rows} == {"dev","validation","test"}, "INVALID_RESULT", "Unpaired/incomplete saved metrics")
    _require({(row["split"],row["query_id"],row["method"]) for row in result["rankings"]} == seen
             and len(result["rankings"]) == len(rows), "INVALID_RESULT", "Saved ranking/metric coverage mismatch")
    for row in result["rankings"]:
        rank = row["ranking"]
        _require(type(rank) is list and len(rank) <= 20 and len(set(rank)) == len(rank) and all(_text(doc,80) for doc in rank)
                 and row["query_id"] not in rank and not set(rank) & set(missing)
                 and type(row["query_line"]) is int and row["query_line"] > 0
                 and type(row["ranked_doc_lines"]) is list and len(row["ranked_doc_lines"]) == len(rank)
                 and all(type(line) is int and line > 0 for line in row["ranked_doc_lines"])
                 and type(row["ranking_seconds"]) in (int,float) and math.isfinite(row["ranking_seconds"]) and row["ranking_seconds"] >= 0,
                 "INVALID_RESULT", "Malformed saved ranking or source coordinates")
    usage = result["usage"]
    _object(usage, ("index_builds", "ranking_calls", "scoring_calls", "query_pairs", "corpus_records", "index_seconds", "native_fits", "model_calls"), "saved primary usage")
    _require(all(type(usage[key]) is int for key in usage if key != "index_seconds")
             and type(usage["index_seconds"]) in (int, float) and math.isfinite(usage["index_seconds"]) and usage["index_seconds"] >= 0
             and usage["corpus_records"] == scope["document_count"]
             and usage["index_builds"] == 1 and usage["ranking_calls"] == usage["scoring_calls"] == len(rows)
             and usage["query_pairs"] == len(rows)//2 and usage["native_fits"] == usage["model_calls"] == 0,
             "INVALID_RESULT", "Saved operation counts differ from complete coverage")
    return result


def _saved(original):
    try:
        return _saved_checked(original)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError, OverflowError, RecursionError):
        raise ResearchError("INVALID_RESULT", "Malformed saved retrieval ToolResult") from None


def _decision(tool_id, original, waiting):
    return {"policy_ref": {"id": tool_id, "version": ADAPTER_VERSION}, "project_status": "waiting" if waiting else "active",
        "next_action": {"kind": "review_saved_evidence" if waiting else "conditional_proposal", "execution_status": "not_executed",
            **({} if waiting else {"method_id": AUDIT_TOOL_ID}),
            "required_evidence": ["Preserve coverage losses and early-rank gains; binary relevance does not establish scientific validity or automatic promotion."]},
        "reason": "Review saved paired query failures without reranking or additional model/fit allowance.",
        "source_snapshot_sha256": original["result"]["source_snapshot_sha256"], "evidence_refs": copy.deepcopy(original["evidence_refs"]),
        "scientific_validation": False, "new_fits": 0, "model_calls": 0}


def next_decision(result):
    _saved(result)
    return _decision(TOOL_ID, result, False)


class SavedRelevanceAudit:
    TOOL_ID = AUDIT_TOOL_ID
    ADAPTER_VERSION = ADAPTER_VERSION
    code_identity = staticmethod(code_identity)

    @staticmethod
    def eligible(original):
        try:
            _saved(original)
            return True
        except (ResearchError, KeyError, TypeError, ValueError, OverflowError, RecursionError):
            return False

    def execute_saved(self, original, parameters):
        _object(parameters, ("based_on_action_id", "based_on_result_sha256"), "predecessor")
        identifier(parameters["based_on_action_id"], "based_on_action_id")
        _require(_digest(parameters["based_on_result_sha256"]), "INVALID_REQUEST", "Exact predecessor result SHA required")
        prior = _saved(original)
        summary, deltas, adverse = _paired(prior["per_query_metrics"])
        _require(summary == prior["paired_summary"] and adverse == prior["adverse_queries"], "EVIDENCE_CHANGED", "Saved paired arithmetic differs")
        result = {"scope": copy.deepcopy(prior["scope"]), "source_snapshot_sha256": prior["source_snapshot_sha256"],
            "predecessor": copy.deepcopy(parameters), "rankings_sha256": prior["rankings_before_scoring_sha256"],
            "summary": summary, "adverse_queries": adverse, "per_query_deltas": deltas,
            "usage": {"query_pairs": len(deltas), "index_builds": 0, "ranking_calls": 0, "scoring_calls": 0, "native_fits": 0, "model_calls": 0},
            "limitations": copy.deepcopy(NOTES) + ["Diagnostic arithmetic reuses saved metric values; it does not rescore against qrels or rerank documents."]}
        refs = copy.deepcopy(original["evidence_refs"])
        refs.append({"source_snapshot_sha256": prior["source_snapshot_sha256"], "producer": copy.deepcopy(parameters),
                     "locator": {"kind": "saved_relevance_action", **parameters}})
        return _tool(self.TOOL_ID, result, "saved_relevance_error_audit", {"query_pairs": len(deltas), "adverse_queries": len(adverse)}, refs)

    def next_decision(self, result):
        _require(type(result) is dict and result.get("tool_id") == self.TOOL_ID and result.get("status") == "completed"
                 and result.get("schema_version") == "relevance-saved-error-result-v1"
                 and result.get("adapter_version") == ADAPTER_VERSION
                 and result.get("scientific_validation") is False
                 and all(type(result.get(key)) is int and result[key] == 0 for key in ("new_fits", "model_calls")),
                 "INVALID_RESULT", "A completed saved retrieval audit is required")
        _require(type(result.get("result")) is dict, "INVALID_RESULT", "A saved audit result object is required")
        scope = result["result"].get("scope", {})
        _require(type(scope) is dict and scope.get("contract") == "relevance-retrieval-fixed-pair-v1"
                 and scope.get("qrels_semantics") == SEMANTICS, "INVALID_RESULT", "A relevance audit scope is required")
        _require(_digest(result["result"].get("source_snapshot_sha256"))
                 and type(result.get("evidence_refs")) is list and 1 <= len(result["evidence_refs"]) <= 16
                 and all(type(ref) is dict for ref in result["evidence_refs"]),
                 "INVALID_RESULT", "A saved audit requires bounded source/evidence identities")
        try:
            bounded = len(canonical(result).encode("utf-8")) <= MAX_RESULT_BYTES
        except (ValueError, TypeError, UnicodeError, RecursionError):
            bounded = False
        _require(bounded, "INVALID_RESULT", "A bounded JSON audit result is required")
        return _decision(self.TOOL_ID, result, True)


AUDIT = SavedRelevanceAudit()
