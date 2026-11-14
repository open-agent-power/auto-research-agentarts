"""Read one saved staged development result against its original public source.

No final package, ranking, qrel scoring, fitting, recovery or dispatch occurs.
"""
from . import staged_project_experience as evidence, staged_relevance_adapter as staged
from . import retrieval_lexical as lexical
from .contracts import ResearchError, canonical


def _require(condition):
    if not condition:
        raise ResearchError("EVIDENCE_CHANGED", "The saved development result differs from its original source.")


def read_validation_delta(project, state, action, metric):
    """Validate the original primary and return one saved paired validation mean."""
    try:
        _require(type(metric) is str and metric in lexical.METRICS)
        _require(state["registration"]["method_id"] == staged.TOOL_ID)
        matches = [item for item in state["actions"] if item["id"] == action["id"]]
        _require(len(matches) == 1 and matches[0] == action)
        evidence._action(action, state, staged.TOOL_ID)
        evidence._verify_action_rows(project, [action])
        _, source, parsed = evidence._dev_source(project, state)
        docs, queries, qrels, doc_lines, query_lines = parsed
        envelope, _ = evidence._read(project, action)
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
        return summary["splits"]["validation"]["paired_candidate_minus_baseline"][metric]["mean"]
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, OSError, OverflowError, RecursionError):
        raise ResearchError("EVIDENCE_CHANGED", "The saved development result is unavailable or malformed.") from None
