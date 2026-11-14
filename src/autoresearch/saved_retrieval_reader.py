"""Bounded projections of completed retrieval records, never a new evaluation.

The only input paths come from a host-bound project root. Source parsing validates
captured bytes; it does not build an index, rank documents, or calculate metrics.
"""
import copy
import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

from . import retrieval_adapter as citation_adapter, relevance_retrieval_adapter as relevance_adapter
from . import source_evidence_adapter as source_reader
from .contracts import ResearchError, canonical, fingerprint, identifier

MAX_ARTIFACT_BYTES = 5 * 1024 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_PAGE_SIZE = 25
MAX_DOCUMENT_TEXT = 4096
MAX_DOCUMENT_TITLE = 512
METRICS = ("recall@5", "recall@10", "recall@20", "mrr@10", "ndcg@10")
SPLITS = ("dev", "validation", "test")
CATEGORIES = ("metric_loss", "no_metric_loss_both_incomplete",
              "no_metric_loss_baseline_only_incomplete", "no_metric_loss_other")


@dataclass(frozen=True)
class _Family:
    module: object
    methods: tuple
    primary_schema: str
    audit_schema: str
    page_schema: str
    query_schema: str
    relevance: bool = False

    def contract(self):
        return {"id": "relevance-retrieval-fixed-pair-v1", "qrels_semantics": "positive_relevance_binary_projection",
                "baseline": "bm25", "candidate": "tfidf_cosine", "ignore_identical_ids": True,
                "missing_document_policy": "retain_in_denominator"}


_FAMILIES = (
    _Family(citation_adapter, ("tfidf_cosine", "bm25"), "citation-retrieval-result-v1", "retrieval-saved-error-result-v1",
            "saved-retrieval-adverse-page-v1", "saved-retrieval-query-v1"),
    _Family(relevance_adapter, ("bm25", "tfidf_cosine"), "relevance-retrieval-result-v1", "relevance-saved-error-result-v1",
            "saved-relevance-adverse-page-v1", "saved-relevance-query-v1", True),
)


def _family(command):
    for family in _FAMILIES:
        if command in (family.module.TOOL_ID, family.module.AUDIT_TOOL_ID):
            return family
    raise ResearchError("ARTIFACT_NOT_AVAILABLE", "The action has no saved retrieval reader.")


def _require(condition, code="EVIDENCE_CHANGED", message="Saved retrieval records differ from their binding."):
    if not condition:
        raise ResearchError(code, message)


def _read(path, maximum):
    try:
        return source_reader._read_file(Path(path).absolute(), maximum)
    except FileNotFoundError:
        raise ResearchError("ARTIFACT_NOT_FOUND", "A registered saved retrieval file is unavailable.") from None
    except OSError:
        raise ResearchError("EVIDENCE_CHANGED", "A saved retrieval file cannot be read safely.") from None


def _metrics(value, *, difference=False):
    _require(type(value) is dict and set(value) == set(METRICS))
    _require(all(type(x) in (int, float) and math.isfinite(x)
                 and (-1 if difference else 0) <= x <= 1 for x in value.values()))
    return value


def _action(state, action_id, family=None):
    identifier(action_id, "action_id")
    actions = [a for a in state["actions"] if a["id"] == action_id]
    _require(len(actions) == 1, "ARTIFACT_NOT_FOUND", "No unique registered retrieval action matches.")
    action = actions[0]
    selected = _family(action["command"])
    _require(family is None or selected is family,
             "ARTIFACT_NOT_AVAILABLE", "The action has no saved retrieval reader.")
    _require(action["status"] == "completed", "ARTIFACT_NOT_AVAILABLE", "The retrieval action is not completed.")
    _require(action["project_id"] == state["id"] and action["run_id"] == state["run_id"])
    _require(action["artifact"] == "artifacts/" + action_id + ".json")
    if selected.relevance:
        _require(state["registration"]["method_id"] == selected.module.TOOL_ID)
        instance = action["method_instance"]
        _require(canonical(instance["definition_ref"]) == canonical({"id": action["command"], "version": selected.module.ADAPTER_VERSION})
                 and canonical(instance["scope"]) == canonical(state["source_scope"]) and action["dimension"] is None)
        request = {"project_id": state["id"], "command": action["command"], "dimension": None,
                   "source_snapshot_sha256": state["source_snapshot_sha256"]}
        bindings = {"source_snapshot_sha256": state["source_snapshot_sha256"]}
        if action["command"] == selected.module.AUDIT_TOOL_ID:
            parameters = action["parameters"]
            _require(type(parameters) is dict and set(parameters) == {"based_on_action_id", "based_on_result_sha256"})
            evaluation = "relevance-retrieval-saved-error-audit-v1"
            _require(action["evaluation_ref"] == evaluation)
            request.update(parameters=parameters, evaluation_ref=evaluation)
            bindings.update(parameters)
        else:
            parameters = {}
            evaluation = "relevance-retrieval-fixed-pair-v1"
        _require(canonical(instance["parameters"]) == canonical(parameters)
                 and canonical(instance["input_bindings"]) == canonical(bindings)
                 and instance["evaluation_ref"] == evaluation and action["request_sha256"] == fingerprint(request))
    return action


def _envelope(project, state, action, family):
    raw = _read(Path(project.root) / "artifacts" / (action["id"] + ".json"), MAX_ARTIFACT_BYTES)
    envelope = family.module._parse(raw)
    _require(type(envelope) is dict and set(envelope) == {
        "action_id", "code_identity", "request_sha256", "sha256", "source_snapshot_sha256", "tool_result"})
    _require(envelope["sha256"] == action["result_sha256"]
             and envelope["sha256"] == fingerprint({k: v for k, v in envelope.items() if k != "sha256"})
             and envelope["action_id"] == action["id"]
             and envelope["request_sha256"] == action["request_sha256"]
             and envelope["code_identity"] == action["code_identity"]
             and envelope["source_snapshot_sha256"] == action["source_snapshot_sha256"] == state["source_snapshot_sha256"])
    tool = envelope["tool_result"]
    _require(type(tool) is dict and tool["status"] == "completed"
             and tool["tool_id"] == action["command"] and type(tool["result"]) is dict
             and tool["schema_version"] == (family.primary_schema if action["command"] == family.module.TOOL_ID else family.audit_schema)
             and tool["adapter_version"] == family.module.ADAPTER_VERSION
             and tool["scientific_validation"] is False
             and type(tool["model_calls"]) is int and tool["model_calls"] == 0
             and type(tool["new_fits"]) is int and tool["new_fits"] == 0)
    _require(tool["result"]["source_snapshot_sha256"] == state["source_snapshot_sha256"])
    if family.relevance:
        if action["command"] == family.module.TOOL_ID:
            family.module._saved(tool)
        else:
            family.module.AUDIT.next_decision(tool)
    return tool["result"]


def _key(row):
    _require(type(row) is dict and row["split"] in SPLITS
             and type(row["query_id"]) is str and 0 < len(row["query_id"]) <= 80)
    return row["split"], row["query_id"]


def _category(row):
    if row["loss_metrics"]:
        return "metric_loss"
    if row["baseline"]["recall@20"] < 1 and row["candidate"]["recall@20"] < 1:
        return "no_metric_loss_both_incomplete"
    if row["baseline"]["recall@20"] < 1 and row["candidate"]["recall@20"] == 1:
        return "no_metric_loss_baseline_only_incomplete"
    return "no_metric_loss_other"


def _bundle(project, state, action_id):
    requested = _action(state, action_id)
    family = _family(requested["command"])
    adapter, methods = family.module, family.methods
    requested_result = _envelope(project, state, requested, family)
    if requested["command"] == adapter.AUDIT_TOOL_ID:
        predecessor = requested_result["predecessor"]
        if family.relevance:
            _require(canonical(predecessor) == canonical(requested["parameters"]))
        primary = _action(state, predecessor["based_on_action_id"], family)
        _require(primary["command"] == adapter.TOOL_ID
                 and predecessor["based_on_result_sha256"] == primary["result_sha256"])
        result = _envelope(project, state, primary, family)
        _require(requested_result["adverse_queries"] == result["adverse_queries"])
    else:
        primary, result = requested, requested_result
    raw = _read(Path(project.root) / "source.json", adapter.LIMITS["packet_bytes"])
    _require(hashlib.sha256(raw).hexdigest() == state["registration"]["source_sha256"])
    source = adapter._parse(raw)
    spec, docs, queries, qrels, doc_lines, query_lines = adapter._checked(source)
    _require(source["snapshot_sha256"] == state["source_snapshot_sha256"]
             and canonical(source["scope"]) == canonical(state["source_scope"]) == canonical(result["scope"]) == canonical(requested_result["scope"])
             and canonical(result["comparison"]) == canonical(adapter.COMPARISON))
    if family.relevance:
        _require(state["registration"]["method_id"] == adapter.TOOL_ID)
    records, metrics = result["rankings"], result["per_query_metrics"]
    _require(type(records) is list and type(metrics) is list and len(records) == len(metrics)
             and 0 < len(records) <= 2 * adapter.LIMITS["max_queries"])
    rank_index, metric_index = {}, {}
    for row in records:
        split, query_id = _key(row)
        method = row["method"]
        key = split, query_id, method
        _require(method in methods and key not in rank_index and query_id in spec["query_splits"][split]
                 and type(row["query_line"]) is int and row["query_line"] == query_lines[query_id])
        ids, lines = row["ranking"], row["ranked_doc_lines"]
        _require(type(ids) is list and type(lines) is list and len(ids) == len(lines) <= 20
                 and all(type(item) is str for item in ids) and len(set(ids)) == len(ids)
                 and all(doc in docs and type(line) is int and doc_lines[doc] == line for doc, line in zip(ids, lines)))
        if family.relevance:
            _require(query_id not in ids)
        rank_index[key] = row
    _require(result["rankings_before_scoring_sha256"] == fingerprint(records))
    for row in metrics:
        split, query_id = _key(row)
        method = row["method"]
        key = split, query_id, method
        _require(method in methods and key not in metric_index and key in rank_index)
        _metrics(row["metrics"])
        locator = row["qrel_locator"]
        role = "test_qrels" if split == "test" else "train_qrels"
        relevant = qrels["test" if split == "test" else "train"][query_id]
        _require(type(locator) is dict and locator["kind"] == "tsv_query_documents"
                 and locator["query_id"] == query_id and locator["role"] == role
                 and locator["source_sha256"] == source["assets"][role]["sha256"]
                 and type(locator["document_ids"]) is list and all(type(item) is str for item in locator["document_ids"])
                 and len(locator["document_ids"]) == len(set(locator["document_ids"]))
                 and set(locator["document_ids"]) == set(relevant))
        if family.relevance:
            _require(type(locator["document_grades"]) is dict
                     and canonical(locator["document_grades"]) == canonical(relevant))
        metric_index[key] = row
    expected = {(split, query_id, method) for split, query_ids in spec["query_splits"].items()
                for query_id in query_ids for method in methods}
    _require(set(rank_index) == set(metric_index) == expected)
    adverse = result["adverse_queries"]
    _require(type(adverse) is list and len(adverse) <= adapter.LIMITS["max_queries"])
    seen = set()
    for row in adverse:
        key = _key(row)
        _require(key not in seen and (*key, methods[0]) in metric_index and (*key, methods[1]) in metric_index)
        seen.add(key)
        _metrics(row["baseline"])
        _metrics(row["candidate"])
        _metrics(row["delta"], difference=True)
        losses = row["loss_metrics"]
        _require(type(losses) is list and all(type(name) is str and name in METRICS for name in losses)
                 and len(losses) == len(set(losses))
                 and set(losses) == {name for name, value in row["delta"].items() if value < -1e-12}
                 and row["baseline"] == metric_index[(*key, methods[0])]["metrics"]
                 and row["candidate"] == metric_index[(*key, methods[1])]["metrics"]
                 and (losses or min(row["baseline"]["recall@20"], row["candidate"]["recall@20"]) < 1))
    if family.relevance:
        summary, deltas, complete_adverse = adapter._paired(metrics)
        _require(canonical(result["paired_summary"]) == canonical(summary)
                 and canonical(adverse) == canonical(complete_adverse))
        if requested["command"] == adapter.AUDIT_TOOL_ID:
            _require(requested_result["rankings_sha256"] == result["rankings_before_scoring_sha256"]
                     and canonical(requested_result["summary"]) == canonical(summary)
                     and canonical(requested_result["per_query_deltas"]) == canonical(deltas))
    binding = {"project_id": state["id"], "snapshot_ref": state["snapshot_ref"], "action_id": requested["id"],
               "result_sha256": requested["result_sha256"], "source_snapshot_sha256": requested["source_snapshot_sha256"],
               "primary_action_id": primary["id"], "primary_result_sha256": primary["result_sha256"]}
    return family, binding, adverse, rank_index, metric_index, source, docs, queries, doc_lines, query_lines


def _item(row, family):
    return {"query_id": row["query_id"], "split": row["split"], "category": _category(row),
            "metric_losses": copy.deepcopy(row["loss_metrics"]),
            "metrics": {family.methods[0]: copy.deepcopy(row["baseline"]), family.methods[1]: copy.deepcopy(row["candidate"])},
            "delta": copy.deepcopy(row["delta"])}


def _response(value):
    _require(len(canonical(value).encode("utf-8")) <= MAX_RESPONSE_BYTES,
             "READER_RESPONSE_TOO_LARGE", "The saved reading exceeds its response limit.")
    return value


def _malformed(call):
    try:
        return call()
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        raise ResearchError("EVIDENCE_CHANGED", "Saved retrieval records are malformed or incomplete.") from None


def read_adverse_page(project, state, *, action_id, offset=0, limit=MAX_PAGE_SIZE):
    """Copy an ordered page of saved adverse rows, preserving zero and absent values."""
    _require(type(offset) is int and offset >= 0 and type(limit) is int and 1 <= limit <= MAX_PAGE_SIZE,
             "INVALID_QUERY", "Use a nonnegative offset and a page limit from 1 to 25.")
    def read():
        family, binding, rows, *_ = _bundle(project, state, action_id)
        _require(offset <= len(rows), "INVALID_QUERY", "The offset exceeds the saved adverse row count.")
        counts = {name: 0 for name in CATEGORIES}
        for row in rows:
            counts[_category(row)] += 1
        counts.update(total=len(rows), no_metric_loss_total=len(rows) - counts["metric_loss"])
        value = {"schema_version": family.page_schema, "binding": binding,
            "pagination": {"offset": offset, "limit": limit, "total": len(rows),
                           "next_offset": offset + limit if offset + limit < len(rows) else None},
            "counts": counts, "items": [_item(row, family) for row in rows[offset:offset + limit]]}
        if family.relevance:
            value["contract"] = family.contract()
        return _response(value)
    return _malformed(read)


def read_adverse_query(project, state, *, action_id, query_id, split):
    """Read one saved adverse query and its original captured top-20 documents per arm."""
    _require(type(query_id) is str and 0 < len(query_id) <= 80 and split in SPLITS,
             "INVALID_QUERY", "Use one saved query identifier and split.")
    def read():
        family, binding, adverse, ranks, metrics, source, docs, queries, doc_lines, query_lines = _bundle(project, state, action_id)
        row = next((r for r in adverse if r["query_id"] == query_id and r["split"] == split), None)
        _require(row is not None, "ARTIFACT_NOT_FOUND", "The query is not in this saved adverse set.")
        query_text = queries[query_id]["text"]
        arms = []
        for method in family.methods:
            key = split, query_id, method
            metric = metrics[key]
            relevant = metric["qrel_locator"]["document_ids"]
            grades = metric["qrel_locator"]["document_grades"] if family.relevance else None
            documents = []
            for rank, document_id in enumerate(ranks[key]["ranking"], 1):
                document = docs[document_id]
                documents.append({"rank": rank, "id": document_id, "title": document["title"][:MAX_DOCUMENT_TITLE],
                    "text": document["text"][:MAX_DOCUMENT_TEXT], "title_truncated": len(document["title"]) > MAX_DOCUMENT_TITLE,
                    "text_truncated": len(document["text"]) > MAX_DOCUMENT_TEXT, "line": doc_lines[document_id],
                    "source_sha256": source["assets"]["corpus"]["sha256"], "relevant": document_id in relevant})
                if family.relevance:
                    documents[-1]["original_grade"] = grades.get(document_id)
            arm = {"method": method, "metrics": copy.deepcopy(metric["metrics"]),
                "qrel": {"doc_ids": copy.deepcopy(relevant), "source_sha256": metric["qrel_locator"]["source_sha256"],
                         "role": metric["qrel_locator"]["role"]}, "documents": documents}
            if family.relevance:
                arm["qrel"].update(grades=copy.deepcopy(grades), missing_doc_ids=[doc for doc in relevant if doc not in docs])
            arms.append(arm)
        value = {"schema_version": family.query_schema, "binding": binding,
            "query": {"id": query_id, "split": split, "text": query_text[:4096], "text_truncated": len(query_text) > 4096,
                      "line": query_lines[query_id], "source_sha256": source["assets"]["queries"]["sha256"]},
            "category": _category(row), "arms": arms}
        if family.relevance:
            value["contract"] = family.contract()
        return _response(value)
    return _malformed(read)
