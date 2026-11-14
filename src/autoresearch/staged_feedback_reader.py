"""Read one saved staged development result against its original public source.

No final package, ranking, qrel scoring, fitting, recovery or dispatch occurs.
"""
from . import staged_project_experience as evidence, staged_relevance_adapter as staged
import copy
import hashlib
from pathlib import Path

from . import retrieval_lexical as lexical, saved_retrieval_reader as legacy
from .contracts import ResearchError, canonical


def _require(condition):
    if not condition:
        raise ResearchError("EVIDENCE_CHANGED", "The saved development result differs from its original source.")


def _checked_primary(project, state, action):
    """Validate and retain the complete saved public-development projection."""
    try:
        _require(state["registration"]["method_id"] == staged.TOOL_ID)
        matches = [item for item in state["actions"] if item["id"] == action["id"]]
        _require(len(matches) == 1 and matches[0] == action)
        evidence._action(action, state, staged.TOOL_ID)
        evidence._verify_action_rows(project, [action])
        source_sha, source, parsed = evidence._dev_source(project, state)
        docs, queries, qrels, doc_lines, query_lines = parsed
        envelope, artifact_sha = evidence._read(project, action)
        result = staged._saved(envelope["tool_result"])
        _require(result["source_snapshot_sha256"] == state["source_snapshot_sha256"]
                 and result["scope"] == state["source_scope"]
                 and canonical(result["comparison"]) == canonical(staged.COMPARISON))
        expected = {(split, qid, method) for split, ids in source["spec"]["query_splits"].items()
                    for qid in ids for method in lexical.METHODS}
        rankings, metrics = {}, {}
        for row in result["rankings"]:
            key = row["split"], row["query_id"], row["method"]
            ids = row["ranking"]
            _require(key in expected and key not in rankings and row["query_id"] in queries
                     and row["query_line"] == query_lines[row["query_id"]]
                     and row["query_id"] not in ids
                     and all(doc in docs for doc in ids)
                     and row["ranked_doc_lines"] == [doc_lines[doc] for doc in ids])
            rankings[key] = row
        for row in result["per_query_metrics"]:
            key = row["split"], row["query_id"], row["method"]
            qid = row["query_id"]
            locator = row["qrel_locator"]
            _require(key in expected and key not in metrics and qid in qrels
                     and row["query_line"] == query_lines[qid]
                     and locator["kind"] == "tsv_query_documents" and locator["role"] == "qrels"
                     and locator["query_id"] == qid
                     and locator["source_sha256"] == source["assets"]["qrels"]["sha256"]
                     and locator["document_ids"] == sorted(qrels[qid])
                     and locator["document_grades"] == qrels[qid])
            metrics[key] = row
        _require(set(rankings) == set(metrics) == expected)
        summary, _, adverse = staged._paired(result["per_query_metrics"])
        _require(canonical(summary) == canonical(result["paired_summary"])
                 and canonical(adverse) == canonical(result["adverse_queries"]))
        return {"source_sha": source_sha, "source": source, "parsed": parsed, "artifact_sha": artifact_sha,
                "rankings": rankings, "metrics": metrics, "summary": summary, "adverse": adverse}
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, OSError, OverflowError, RecursionError):
        raise ResearchError("EVIDENCE_CHANGED", "The saved development result is unavailable or malformed.") from None


def read_validation_delta(project, state, action, metric):
    """Validate the original primary and return one saved paired validation mean."""
    _require(type(metric) is str and metric in lexical.METRICS)
    value = _checked_primary(project, state, action)
    return value["summary"]["splits"]["validation"]["paired_candidate_minus_baseline"][metric]["mean"]


def read_validation_deltas(project, state, action, metrics):
    """Read both saved means from one validated public development snapshot."""
    _require(type(metrics) is list and len(metrics) == 2
             and all(type(metric) is str and metric in lexical.METRICS for metric in metrics)
             and metrics[0] != metrics[1])
    checked = _checked_primary(project, state, action)
    paired = checked["summary"]["splits"]["validation"]["paired_candidate_minus_baseline"]
    return [paired[metric]["mean"] for metric in metrics]


def _view(project, state, action_id):
    if type(action_id) is not str or not action_id:
        raise ResearchError("INVALID_QUERY", "Use one saved primary action identifier.")
    if project.status() != state:
        raise ResearchError("STALE_STATE", "The bound reader project changed.")
    actions = [a for a in state["actions"] if a["id"] == action_id]
    if len(actions) != 1 or actions[0].get("command") != staged.TOOL_ID or actions[0].get("status") != "completed":
        raise ResearchError("ARTIFACT_NOT_AVAILABLE", "The staged reader requires one completed primary action.")
    action = actions[0]
    value = _checked_primary(project, state, action)
    binding = {"project_id": state["id"], "snapshot_ref": state["snapshot_ref"], "action_id": action["id"],
               "result_sha256": action["result_sha256"], "source_snapshot_sha256": state["source_snapshot_sha256"],
               "primary_action_id": action["id"], "primary_result_sha256": action["result_sha256"]}
    origin = {"source_file_sha256": value["source_sha"], "producer_code_identity": action["code_identity"],
              "reader_implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    contract = {"id": staged.CONTRACT, "stage": "development", "baseline": "bm25", "candidate": "tfidf_cosine",
                "qrels_semantics": "positive_relevance_binary_projection", "missing_document_policy": "retain_in_denominator",
                "ignore_identical_ids": True}
    return action, value, binding, origin, contract


def _finish(project, state, action, value, response):
    # Re-read the original public bytes and SQL row to reject a changed source or
    # action during projection; no final or private files are involved.
    source_sha, _, _ = evidence._dev_source(project, state)
    _, artifact_sha = evidence._read(project, action)
    evidence._verify_action_rows(project, [action])
    if (source_sha != value["source_sha"] or artifact_sha != value["artifact_sha"]
            or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != response["origin"]["reader_implementation_sha256"]
            or project.status() != state):
        raise ResearchError("STALE_STATE", "The saved reader source or project changed while loading.")
    return legacy._response(response)


def read_adverse_page(project, state, *, action_id, offset=0, limit=legacy.MAX_PAGE_SIZE):
    """Read a bounded page from saved staged development outcomes."""
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= legacy.MAX_PAGE_SIZE:
        raise ResearchError("INVALID_QUERY", "Use a nonnegative offset and a page limit from 1 to 25.")
    action, value, binding, origin, contract = _view(project, state, action_id)
    rows = value["adverse"]
    if offset > len(rows):
        raise ResearchError("INVALID_QUERY", "The offset exceeds the saved adverse row count.")
    counts = {category: 0 for category in legacy.CATEGORIES}
    for row in rows:
        counts[legacy._category(row)] += 1
    counts.update(total=len(rows), no_metric_loss_total=len(rows) - counts["metric_loss"])
    items = [{"query_id": row["query_id"], "split": row["split"], "category": legacy._category(row),
              "metric_losses": copy.deepcopy(row["loss_metrics"]),
              "metrics": {"bm25": copy.deepcopy(row["baseline"]), "tfidf_cosine": copy.deepcopy(row["candidate"])},
              "delta": copy.deepcopy(row["delta"])} for row in rows[offset:offset + limit]]
    response = {"schema_version": "saved-staged-relevance-adverse-page-v1", "binding": binding, "origin": origin,
                "contract": contract, "pagination": {"offset": offset, "limit": limit, "total": len(rows),
                "next_offset": offset + limit if offset + limit < len(rows) else None}, "counts": counts, "items": items}
    return _finish(project, state, action, value, response)


def read_adverse_query(project, state, *, action_id, query_id, split):
    """Read one adverse development query and the original saved two-arm rankings."""
    if type(query_id) is not str or not 0 < len(query_id) <= 80 or split not in staged.SPLITS:
        raise ResearchError("INVALID_QUERY", "Use one development or validation query identifier.")
    action, value, binding, origin, contract = _view(project, state, action_id)
    row = next((r for r in value["adverse"] if r["query_id"] == query_id and r["split"] == split), None)
    if row is None:
        raise ResearchError("ARTIFACT_NOT_FOUND", "The query is not in this saved adverse set.")
    docs, queries, qrels, doc_lines, query_lines = value["parsed"]
    source = value["source"]
    query_text = queries[query_id]["text"]
    arms = []
    for method in ("bm25", "tfidf_cosine"):
        key = split, query_id, method
        metric = value["metrics"][key]
        grades = qrels[query_id]
        positive = sorted(grades)
        documents = []
        for rank, doc_id in enumerate(value["rankings"][key]["ranking"], 1):
            doc = docs[doc_id]
            documents.append({"rank": rank, "id": doc_id, "title": doc["title"][:legacy.MAX_DOCUMENT_TITLE],
                "text": doc["text"][:legacy.MAX_DOCUMENT_TEXT], "title_truncated": len(doc["title"]) > legacy.MAX_DOCUMENT_TITLE,
                "text_truncated": len(doc["text"]) > legacy.MAX_DOCUMENT_TEXT, "line": doc_lines[doc_id],
                "source_sha256": source["assets"]["corpus"]["sha256"], "relevant": doc_id in grades,
                "original_grade": grades.get(doc_id)})
        arms.append({"method": method, "metrics": copy.deepcopy(metric["metrics"]),
                     "qrel": {"doc_ids": positive, "source_sha256": source["assets"]["qrels"]["sha256"],
                              "role": "qrels", "grades": copy.deepcopy(grades),
                              "missing_doc_ids": [doc for doc in positive if doc not in docs]}, "documents": documents})
    response = {"schema_version": "saved-staged-relevance-query-v1", "binding": binding, "origin": origin,
                "contract": contract, "query": {"id": query_id, "split": split, "text": query_text[:4096],
                "text_truncated": len(query_text) > 4096, "line": query_lines[query_id],
                "source_sha256": source["assets"]["queries"]["sha256"]}, "category": legacy._category(row), "arms": arms}
    return _finish(project, state, action, value, response)
