"""Development-only relevance pair and saved-only audit.

This separate contract captures only explicitly named development files. It
cannot establish OS isolation or prove that supplied rows were not previously
exposed; a final evaluator needs an independent frozen protocol and assets.
"""
import copy
import csv
import math
from pathlib import Path
import statistics
import time

from . import relevance_retrieval_adapter as base, retrieval_lexical as lexical
from .contracts import ResearchError, canonical, fingerprint, identifier

TOOL_ID = "research.relevance-validation-pair"
AUDIT_TOOL_ID = "research.relevance-validation-saved-audit"
ADAPTER_VERSION = "1"
CONTRACT = "staged-relevance-development-v1"
FILES = {"corpus": "corpus.jsonl", "queries": "queries.jsonl", "qrels": "qrels.tsv", "license": "license.md"}
LIMITS = copy.deepcopy(base.LIMITS)
COMPARISON = copy.deepcopy(base.COMPARISON)
SEMANTICS = base.SEMANTICS
MAX_RESULT_BYTES = base.MAX_RESULT_BYTES
SPLITS = ("dev", "validation")
NOTES = ["Only the declared development and validation assets were captured; final assets are not part of this contract.",
         "This separation is procedural, not OS isolation, and does not establish that the submitted rows were previously unseen.",
         "Grades 1/2 are retained and metrics use positive binary relevance; missing positives remain in the denominator.",
         "Identical query/document IDs are excluded before the top-20 cutoff; corpus statistics retain all documents.",
         "Source and license provenance are host declarations; scientific validation and automatic promotion are not implied."]
_require = base._require
_object = base._object
_text = base._text
_digest = base._digest
_parse = base._parse


def _limit(role):
    return LIMITS["qrels_bytes"] if role == "qrels" else LIMITS[role + "_bytes"]


def _spec(spec):
    _object(spec, ("schema_version", "dataset_label", "source_url", "attribution", "license_notes",
                   "source_provenance", "files", "query_splits", "comparison", "limits"), "development spec")
    _require(spec["schema_version"] == "staged-relevance-development-spec-v1" and spec["files"] == FILES
             and canonical(spec["comparison"]) == canonical(COMPARISON) and spec["limits"] == LIMITS
             and all(type(v) is int for v in spec["limits"].values())
             and type(spec["comparison"]["top_k"]) is int and spec["comparison"]["ignore_identical_ids"] is True
             and all(type(spec["comparison"][key]) is float for key in ("k1", "b")),
             "INVALID_SOURCE", "Use the fixed development protocol and files.")
    _require(all(_text(spec[key], maximum) for key, maximum in
                 (("dataset_label", 300), ("source_url", 2000), ("attribution", 4000))),
             "INVALID_SOURCE", "Bounded dataset attribution is required.")
    _object(spec["license_notes"], ("corpus", "queries_and_qrels"), "licence notes")
    _require(all(_text(v, 4000) for v in spec["license_notes"].values()), "INVALID_SOURCE", "Licence notes are required.")
    provenance = spec["source_provenance"]
    _object(provenance, ("archive_sha256", "source_receipt_sha256", "selection_sha256", "qrels_semantics"), "provenance")
    _require(all(_digest(provenance[key]) for key in ("archive_sha256", "source_receipt_sha256", "selection_sha256"))
             and provenance["qrels_semantics"] == SEMANTICS, "INVALID_SOURCE", "Valid declared source identities are required.")
    splits = spec["query_splits"]
    _object(splits, SPLITS, "development query splits")
    ids = []
    for split in SPLITS:
        values = splits[split]
        _require(type(values) is list and bool(values) and len(values) <= LIMITS["max_queries"]
                 and all(_text(qid, 80) for qid in values), "INVALID_SOURCE", "Each development split needs bounded query IDs.")
        ids.extend(values)
    _require(len(ids) <= LIMITS["max_queries"] and len(ids) == len(set(ids)),
             "INVALID_SOURCE", "Development splits must be disjoint and unique.")


def _scope(spec, assets, docs, queries, qrels):
    missing = sorted({doc for grades in qrels.values() for doc in grades if doc not in docs})
    return {"domain": "retrieval", "stage": "development", "contract": CONTRACT,
            "dataset_label": spec["dataset_label"], "document_count": len(docs), "query_count": len(queries),
            "query_split_counts": {split: len(spec["query_splits"][split]) for split in SPLITS},
            "qrels_semantics": SEMANTICS,
            "input_identities": {role: {k: asset[k] for k in ("sha256", "bytes")} for role, asset in assets.items()},
            "comparison_sha256": fingerprint(COMPARISON), "missing_positive_document_ids": missing,
            "missing_positive_document_count": len(missing),
            "missing_positive_qrel_pairs": sum(doc not in docs for grades in qrels.values() for doc in grades)}


def _checked(payload):
    try:
        _object(payload, ("schema_version", "task_kind", "stage", "spec_source", "assets", "spec", "scope", "snapshot_sha256"), "development source")
        _require(payload["schema_version"] == "cpu-research-source-v1"
                 and payload["task_kind"] == "staged_relevance_development" and payload["stage"] == "development"
                 and payload["snapshot_sha256"] == fingerprint({k: v for k, v in payload.items() if k != "snapshot_sha256"}),
                 "EVIDENCE_CHANGED", "Development source identity changed.")
        _require(len(canonical(payload).encode("utf-8")) <= LIMITS["packet_bytes"], "SOURCE_TOO_LARGE", "Source packet exceeds its limit.")
        spec = _parse(base._asset_raw(payload["spec_source"], "spec.json", LIMITS["spec_bytes"]))
        _spec(spec)
        _require(canonical(spec) == canonical(payload["spec"]), "EVIDENCE_CHANGED", "Spec differs from captured bytes.")
        _object(payload["assets"], FILES, "development assets")
        raw = {role: base._asset_raw(payload["assets"][role], name, _limit(role)) for role, name in FILES.items()}
        _require(sum(map(len, raw.values())) <= LIMITS["all_asset_bytes"], "SOURCE_TOO_LARGE", "Development assets exceed their limit.")
        base._decode(raw["license"])
        docs, doc_lines = base._jsonl(raw["corpus"], True)
        queries, query_lines = base._jsonl(raw["queries"], False)
        _require(all(row["metadata"] == {} for row in (*docs.values(), *queries.values())),
                 "INVALID_SOURCE", "Development corpus and query metadata must be empty objects.")
        qrels = base._qrels(raw["qrels"], docs, queries)
        declared = {qid for split in SPLITS for qid in spec["query_splits"][split]}
        _require(set(queries) == declared == set(qrels), "INVALID_SOURCE", "Queries and qrels must contain exactly the declared development IDs.")
        _require(canonical(payload["scope"]) == canonical(_scope(spec, payload["assets"], docs, queries, qrels)),
                 "EVIDENCE_CHANGED", "Development source scope changed.")
        return spec, docs, queries, qrels, doc_lines, query_lines
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError, OverflowError, RecursionError, csv.Error):
        raise ResearchError("INVALID_SOURCE", "Malformed bounded development source.") from None


def load_source(raw):
    _require(type(raw) is bytes and 0 < len(raw) <= LIMITS["packet_bytes"], "SOURCE_TOO_LARGE", "Bounded source bytes are required.")
    payload = _parse(raw)
    _checked(payload)
    return payload


def _capture_source(directory):
    root = Path(directory).absolute()
    raw_spec = base.reader._read_file(root / "spec.json", LIMITS["spec_bytes"])
    spec = _parse(raw_spec)
    _spec(spec)
    raw = {role: base.reader._read_file(root / name, _limit(role)) for role, name in FILES.items()}
    assets = {role: base._asset(FILES[role], content) for role, content in raw.items()}
    docs, _ = base._jsonl(raw["corpus"], True)
    queries, _ = base._jsonl(raw["queries"], False)
    qrels = base._qrels(raw["qrels"], docs, queries)
    payload = {"schema_version": "cpu-research-source-v1", "task_kind": "staged_relevance_development", "stage": "development",
               "spec_source": base._asset("spec.json", raw_spec), "assets": assets, "spec": spec,
               "scope": _scope(spec, assets, docs, queries, qrels)}
    payload["snapshot_sha256"] = fingerprint(payload)
    _checked(payload)
    _require(base.reader._read_file(root / "spec.json", LIMITS["spec_bytes"]) == raw_spec
             and all(base.reader._read_file(root / FILES[role], _limit(role)) == content for role, content in raw.items()),
             "EVIDENCE_CHANGED", "Development assets changed during capture.")
    return payload


def capture_source(directory):
    try:
        return _capture_source(directory)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError, OverflowError, RecursionError, csv.Error):
        raise ResearchError("INVALID_SOURCE", "Malformed bounded development source.") from None


def code_identity():
    return base._sha(Path(__file__).read_bytes() + base.code_identity().encode("ascii"))


def _paired(rows):
    by_pair = {}
    for row in rows:
        by_pair.setdefault((row["split"], row["query_id"]), {})[row["method"]] = row["metrics"]
    deltas, adverse = [], []
    for (split, qid), pair in by_pair.items():
        delta = {name: pair["tfidf_cosine"][name] - pair["bm25"][name] for name in lexical.METRICS}
        item = {"split": split, "query_id": qid, "delta": delta,
                "loss_metrics": [name for name, value in delta.items() if value < -1e-12],
                "gain_metrics": [name for name, value in delta.items() if value > 1e-12],
                "tie_metrics": [name for name, value in delta.items() if abs(value) <= 1e-12],
                "baseline": pair["bm25"], "candidate": pair["tfidf_cosine"]}
        deltas.append(item)
        if item["loss_metrics"] or min(pair["bm25"]["recall@20"], pair["tfidf_cosine"]["recall@20"]) < 1:
            adverse.append(copy.deepcopy(item))
    splits = {}
    for split in SPLITS:
        selected = [row for row in rows if row["split"] == split]
        arms = {method: {"queries": len(selected)//2,
                         "metrics": {name: statistics.mean(row["metrics"][name] for row in selected if row["method"] == method)
                                     for name in lexical.METRICS}} for method in lexical.METHODS}
        changes = [row for row in deltas if row["split"] == split]
        splits[split] = {"arms": arms, "paired_candidate_minus_baseline": {name: {
            "mean": statistics.mean(row["delta"][name] for row in changes),
            "wins": sum(row["delta"][name] > 1e-12 for row in changes),
            "ties": sum(abs(row["delta"][name]) <= 1e-12 for row in changes),
            "losses": sum(row["delta"][name] < -1e-12 for row in changes)} for name in lexical.METRICS}}
    return {"splits": splits}, deltas, adverse


def _references(payload):
    return [{"source_snapshot_sha256": payload["snapshot_sha256"], "source_sha256": asset["sha256"],
             "file_name": asset["file_name"], "url": payload["spec"]["source_url"],
             "license_note": payload["spec"]["license_notes"]["corpus" if role == "corpus" else "queries_and_qrels"],
             "locator": {"kind": "jsonl_records" if role in ("corpus", "queries") else "whole_original", "role": role}}
            for role, asset in payload["assets"].items()]


def _tool(tool_id, result, kind, summary, refs):
    value = {"schema_version": "staged-relevance-validation-result-v1" if tool_id == TOOL_ID else "staged-relevance-validation-audit-v1",
             "tool_id": tool_id, "adapter_version": ADAPTER_VERSION, "status": "completed",
             "observations": [{"producer": tool_id, "kind": kind, "summary": copy.deepcopy(summary),
                               "scope": copy.deepcopy(result["scope"]), "evidence_refs": copy.deepcopy(refs),
                               "interpretation_status": "computed_binary_relevance_not_scientific_review", "scientific_validation": False}],
             "evidence_refs": copy.deepcopy(refs), "metrics": [{"name": "analyzed_query_pairs", "value": summary["query_pairs"], "unit": "query"}],
             "result": result, "failure": None, "model_calls": 0, "new_fits": 0, "scientific_validation": False}
    _require(len(canonical(value).encode("utf-8")) <= MAX_RESULT_BYTES, "RESULT_TOO_LARGE", "Development result exceeds 4 MiB.")
    return value


def execute(payload, dimension=None):
    _require(dimension is None, "INVALID_REQUEST", "The fixed pair has no free execution parameters.")
    spec, docs, queries, qrels, doc_lines, query_lines = _checked(payload)
    start = time.perf_counter()
    index = lexical.build_index(docs)
    index_seconds = time.perf_counter() - start
    rankings = []
    for split in SPLITS:
        for qid in spec["query_splits"][split]:
            for method in lexical.METHODS:
                started = time.perf_counter()
                rank = base.retrieve(queries[qid]["text"], index, method, exclude_doc_id=qid)
                rankings.append({"split": split, "query_id": qid, "method": method, "ranking": rank,
                                 "ranking_seconds": time.perf_counter() - started, "query_line": query_lines[qid],
                                 "ranked_doc_lines": [doc_lines[doc] for doc in rank]})
    ranks_sha = fingerprint(rankings)
    scored = [{"split": row["split"], "query_id": row["query_id"], "query_line": row["query_line"], "method": row["method"],
               "metrics": lexical.metrics(row["ranking"], qrels[row["query_id"]]),
               "qrel_locator": {"kind": "tsv_query_documents", "role": "qrels", "source_sha256": payload["assets"]["qrels"]["sha256"],
                                "query_id": row["query_id"], "document_ids": sorted(qrels[row["query_id"]]),
                                "document_grades": copy.deepcopy(qrels[row["query_id"]])}} for row in rankings]
    summary, _, adverse = _paired(scored)
    result = {"stage": "development", "scope": copy.deepcopy(payload["scope"]), "source_snapshot_sha256": payload["snapshot_sha256"],
              "comparison": copy.deepcopy(COMPARISON), "rankings": rankings, "rankings_before_scoring_sha256": ranks_sha,
              "per_query_metrics": scored, "paired_summary": summary, "adverse_queries": adverse,
              "usage": {"index_builds": 1, "ranking_calls": len(rankings), "scoring_calls": len(scored),
                        "query_pairs": len(scored)//2, "corpus_records": len(docs), "index_seconds": index_seconds,
                        "native_fits": 0, "model_calls": 0}, "limitations": copy.deepcopy(NOTES)}
    return _tool(TOOL_ID, result, "staged_relevance_validation_pair", {"query_pairs": len(scored)//2,
                 "paired_summary": summary, "adverse_queries": len(adverse)}, _references(payload))


def _saved_checked(original):
    _require(type(original) is dict and set(original) == {"schema_version", "tool_id", "adapter_version", "status", "observations",
             "evidence_refs", "metrics", "result", "failure", "model_calls", "new_fits", "scientific_validation"}
             and original["tool_id"] == TOOL_ID and original["status"] == "completed"
             and original["schema_version"] == "staged-relevance-validation-result-v1"
             and original["adapter_version"] == ADAPTER_VERSION and original["scientific_validation"] is False
             and original["failure"] is None and all(type(original[key]) is int and original[key] == 0 for key in ("new_fits", "model_calls"))
             and len(canonical(original).encode("utf-8")) <= MAX_RESULT_BYTES,
             "INVALID_RESULT", "A bounded completed development result is required.")
    result = original["result"]
    _object(result, ("stage", "scope", "source_snapshot_sha256", "comparison", "rankings", "rankings_before_scoring_sha256",
                     "per_query_metrics", "paired_summary", "adverse_queries", "usage", "limitations"), "development result")
    _require(result["stage"] == "development" and canonical(result["comparison"]) == canonical(COMPARISON)
             and _digest(result["source_snapshot_sha256"]) and type(result["rankings"]) is list
             and result["rankings_before_scoring_sha256"] == fingerprint(result["rankings"])
             and result["limitations"] == NOTES, "EVIDENCE_CHANGED", "Saved development protocol or rankings changed.")
    scope = result["scope"]
    _object(scope, ("domain", "stage", "contract", "dataset_label", "document_count", "query_count", "query_split_counts",
                    "qrels_semantics", "input_identities", "comparison_sha256", "missing_positive_document_ids",
                    "missing_positive_document_count", "missing_positive_qrel_pairs"), "development scope")
    _require(scope["domain"] == "retrieval" and scope["stage"] == "development" and scope["contract"] == CONTRACT
             and scope["qrels_semantics"] == SEMANTICS and _text(scope["dataset_label"], 300)
             and scope["comparison_sha256"] == fingerprint(COMPARISON)
             and type(scope["document_count"]) is int and 1 <= scope["document_count"] <= LIMITS["max_corpus_rows"]
             and type(scope["query_count"]) is int and 2 <= scope["query_count"] <= LIMITS["max_queries"],
             "INVALID_RESULT", "Development scope differs from its contract.")
    _object(scope["query_split_counts"], SPLITS, "split counts")
    _require(all(type(v) is int and v > 0 for v in scope["query_split_counts"].values())
             and sum(scope["query_split_counts"].values()) == scope["query_count"], "INVALID_RESULT", "Invalid development split counts.")
    _object(scope["input_identities"], FILES, "development input identities")
    for role, asset in scope["input_identities"].items():
        _object(asset, ("sha256", "bytes"), "development input identity")
        _require(_digest(asset["sha256"]) and type(asset["bytes"]) is int and 0 < asset["bytes"] <= _limit(role),
                 "INVALID_RESULT", "Invalid development input identity.")
    missing = scope["missing_positive_document_ids"]
    _require(type(missing) is list and all(_text(doc, 80) for doc in missing) and missing == sorted(set(missing))
             and type(scope["missing_positive_document_count"]) is int and scope["missing_positive_document_count"] == len(missing)
             and type(scope["missing_positive_qrel_pairs"]) is int
             and len(missing) <= scope["missing_positive_qrel_pairs"] <= LIMITS["max_qrel_pairs"],
             "INVALID_RESULT", "Invalid missing-positive accounting.")
    rows, seen, locators, lines = result["per_query_metrics"], set(), {}, {}
    _require(type(rows) is list and len(rows) == 2 * scope["query_count"], "INVALID_RESULT", "Incomplete saved metric coverage.")
    for row in rows:
        _object(row, ("split", "query_id", "query_line", "method", "metrics", "qrel_locator"), "saved metric row")
        _require(type(row["split"]) is str and row["split"] in SPLITS and _text(row["query_id"], 80)
                 and type(row["query_line"]) is int and row["query_line"] > 0
                 and type(row["method"]) is str and row["method"] in lexical.METHODS,
                 "INVALID_RESULT", "Invalid development query/arm identity.")
        key = row["split"], row["query_id"], row["method"]
        _require(key not in seen and type(row["metrics"]) is dict and set(row["metrics"]) == set(lexical.METRICS)
                 and all(type(x) in (int, float) and 0 <= x <= 1 and math.isfinite(x) for x in row["metrics"].values()),
                 "INVALID_RESULT", "Invalid saved metrics.")
        locator = row["qrel_locator"]
        _object(locator, ("kind", "role", "source_sha256", "query_id", "document_ids", "document_grades"), "development qrel locator")
        grades = locator["document_grades"]
        _require(locator["kind"] == "tsv_query_documents" and locator["role"] == "qrels"
                 and locator["source_sha256"] == scope["input_identities"]["qrels"]["sha256"] and locator["query_id"] == row["query_id"]
                 and type(grades) is dict and bool(grades) and len(grades) <= LIMITS["max_qrel_pairs"]
                 and all(_text(doc, 80) and type(grade) is int and grade in (1, 2) for doc, grade in grades.items())
                 and locator["document_ids"] == sorted(grades), "INVALID_RESULT", "Invalid saved qrel grades/locator.")
        pair = row["split"], row["query_id"]
        _require(pair not in locators or (locators[pair] == locator and lines[pair] == row["query_line"]),
                 "INVALID_RESULT", "The same query must have identical saved source bindings in both arms.")
        locators[pair], lines[pair] = locator, row["query_line"]
        seen.add(key)
    missing_set = set(missing)
    missing_seen = {doc for locator in locators.values() for doc in locator["document_ids"] if doc in missing_set}
    missing_pairs = sum(doc in missing_set for locator in locators.values() for doc in locator["document_ids"])
    _require(sum(len(locator["document_ids"]) for locator in locators.values()) <= LIMITS["max_qrel_pairs"]
             and missing_seen == missing_set and missing_pairs == scope["missing_positive_qrel_pairs"]
             and seen == {(split, qid, method) for split, qid in locators for method in lexical.METHODS}
             and len({qid for _, qid in locators}) == scope["query_count"]
             and {split: sum(key[0] == split for key in locators) for split in SPLITS} == scope["query_split_counts"],
             "INVALID_RESULT", "Unpaired or overlapping development queries.")
    rankings = result["rankings"]
    _require(len(rankings) == len(rows), "INVALID_RESULT", "Ranking coverage differs from metrics.")
    rank_keys = set()
    for row in rankings:
        _object(row, ("split", "query_id", "method", "ranking", "ranking_seconds", "query_line", "ranked_doc_lines"), "saved ranking")
        key = row["split"], row["query_id"], row["method"]
        rank = row["ranking"]
        _require(key in seen and key not in rank_keys and type(rank) is list and len(rank) <= 20
                 and all(_text(doc, 80) for doc in rank) and len(set(rank)) == len(rank)
                 and row["query_id"] not in rank and not set(rank) & set(missing)
                 and type(row["query_line"]) is int and row["query_line"] == lines[(row["split"], row["query_id"])]
                 and type(row["ranked_doc_lines"]) is list and len(row["ranked_doc_lines"]) == len(rank)
                 and all(type(line) is int and line > 0 for line in row["ranked_doc_lines"])
                 and type(row["ranking_seconds"]) in (int, float) and 0 <= row["ranking_seconds"] < float("inf"),
                 "INVALID_RESULT", "Malformed saved ranking or source coordinates.")
        rank_keys.add(key)
    usage = result["usage"]
    _object(usage, ("index_builds", "ranking_calls", "scoring_calls", "query_pairs", "corpus_records", "index_seconds", "native_fits", "model_calls"), "development usage")
    _require(all(type(usage[k]) is int for k in usage if k != "index_seconds")
             and type(usage["index_seconds"]) in (int, float) and 0 <= usage["index_seconds"] < float("inf")
             and usage["corpus_records"] == scope["document_count"] and usage["index_builds"] == 1
             and usage["ranking_calls"] == usage["scoring_calls"] == len(rows) and usage["query_pairs"] == len(rows)//2
             and usage["native_fits"] == usage["model_calls"] == 0, "INVALID_RESULT", "Operation counts differ from saved coverage.")
    summary, _, adverse = _paired(rows)
    _require(canonical(result["paired_summary"]) == canonical(summary)
             and canonical(result["adverse_queries"]) == canonical(adverse),
             "EVIDENCE_CHANGED", "Saved development summary or adverse results changed.")
    refs = original["evidence_refs"]
    _require(type(refs) is list and len(refs) == len(FILES), "INVALID_RESULT", "Development evidence references are incomplete.")
    seen_roles = set()
    for ref in refs:
        _object(ref, ("source_snapshot_sha256", "source_sha256", "file_name", "url", "license_note", "locator"), "development evidence reference")
        locator = ref["locator"]
        _object(locator, ("kind", "role"), "development evidence locator")
        role = locator["role"]
        _require(type(role) is str and role in FILES and role not in seen_roles
                 and locator["kind"] == ("jsonl_records" if role in ("corpus", "queries") else "whole_original")
                 and ref["file_name"] == FILES[role] and ref["source_sha256"] == scope["input_identities"][role]["sha256"]
                 and ref["source_snapshot_sha256"] == result["source_snapshot_sha256"]
                 and _text(ref["url"], 2000) and _text(ref["license_note"], 4000), "INVALID_RESULT", "Development evidence reference changed.")
        seen_roles.add(role)
    expected_summary = {"query_pairs": len(rows)//2, "paired_summary": summary, "adverse_queries": len(adverse)}
    expected_observation = {"producer": TOOL_ID, "kind": "staged_relevance_validation_pair", "summary": expected_summary,
                            "scope": scope, "evidence_refs": refs,
                            "interpretation_status": "computed_binary_relevance_not_scientific_review", "scientific_validation": False}
    _require(canonical(original["observations"]) == canonical([expected_observation])
             and canonical(original["metrics"]) == canonical([{"name": "analyzed_query_pairs", "value": len(rows)//2, "unit": "query"}]),
             "EVIDENCE_CHANGED", "Saved observation differs from the development result.")
    return result


def _saved(original):
    try:
        return _saved_checked(original)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError, OverflowError, RecursionError):
        raise ResearchError("INVALID_RESULT", "Malformed saved development ToolResult.") from None


def _decision(tool_id, original, waiting):
    return {"policy_ref": {"id": tool_id, "version": ADAPTER_VERSION}, "project_status": "waiting" if waiting else "active",
            "next_action": {"kind": "review_saved_evidence" if waiting else "conditional_proposal", "execution_status": "not_executed",
                            **({} if waiting else {"method_id": AUDIT_TOOL_ID}),
                            "required_evidence": ["Preserve development losses and unknowns; an independent final protocol remains separate."]},
            "reason": "Review the saved development pair without automatic scientific adoption.",
            "source_snapshot_sha256": original["result"]["source_snapshot_sha256"], "evidence_refs": copy.deepcopy(original["evidence_refs"]),
            "scientific_validation": False, "new_fits": 0, "model_calls": 0}


def next_decision(result):
    _saved(result)
    return _decision(TOOL_ID, result, False)


class SavedDevelopmentAudit:
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
        _require(_digest(parameters["based_on_result_sha256"]), "INVALID_REQUEST", "Exact predecessor result SHA is required.")
        prior = _saved(original)
        summary, deltas, adverse = _paired(prior["per_query_metrics"])
        result = {"stage": "development", "scope": copy.deepcopy(prior["scope"]),
                  "source_snapshot_sha256": prior["source_snapshot_sha256"], "predecessor": copy.deepcopy(parameters),
                  "rankings_sha256": prior["rankings_before_scoring_sha256"], "summary": summary,
                  "adverse_queries": adverse, "per_query_deltas": deltas,
                  "usage": {"query_pairs": len(deltas), "index_builds": 0, "ranking_calls": 0, "scoring_calls": 0,
                            "native_fits": 0, "model_calls": 0},
                  "limitations": copy.deepcopy(NOTES) + ["Saved metrics are inspected without reranking or rescoring labels."]}
        refs = copy.deepcopy(original["evidence_refs"])
        refs.append({"source_snapshot_sha256": prior["source_snapshot_sha256"], "producer": copy.deepcopy(parameters),
                     "locator": {"kind": "saved_development_action", **parameters}})
        return _tool(self.TOOL_ID, result, "saved_staged_relevance_audit", {"query_pairs": len(deltas), "adverse_queries": len(adverse)}, refs)

    def next_decision(self, result):
        try:
            _require(type(result) is dict and result.get("tool_id") == self.TOOL_ID and result.get("status") == "completed"
                     and result.get("schema_version") == "staged-relevance-validation-audit-v1"
                     and result.get("adapter_version") == ADAPTER_VERSION and result.get("scientific_validation") is False
                     and all(type(result.get(key)) is int and result[key] == 0 for key in ("new_fits", "model_calls"))
                     and type(result.get("result")) is dict and result["result"].get("stage") == "development"
                     and type(result["result"].get("scope")) is dict and result["result"]["scope"].get("contract") == CONTRACT
                     and _digest(result["result"].get("source_snapshot_sha256"))
                     and type(result.get("evidence_refs")) is list and 1 <= len(result["evidence_refs"]) <= 16
                     and len(canonical(result).encode("utf-8")) <= MAX_RESULT_BYTES,
                     "INVALID_RESULT", "A bounded completed development audit is required.")
            return _decision(self.TOOL_ID, result, True)
        except ResearchError:
            raise
        except (KeyError, TypeError, ValueError, UnicodeError, OverflowError, RecursionError):
            raise ResearchError("INVALID_RESULT", "Malformed saved development audit.") from None


AUDIT = SavedDevelopmentAudit()
