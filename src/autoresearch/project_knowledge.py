"""Frozen FTS indexes of actually extracted project selections, not scientific approval."""
import hashlib
import json
from pathlib import Path
import re
import uuid

from . import knowledge
from .contracts import ResearchError, canonical

POINTS = ("clarification", "design", "preparation", "interpretation")


def _data_interpretation(scope):
    query = "missing invalid nonfinite group target_unit"
    if type(scope) is not dict:
        return query
    names = [scope.get("target_column")]
    for role in ("numeric_columns", "group_columns", "key_columns"):
        if type(scope.get(role)) is list:
            names.extend(scope[role])
    seen = set()
    for name in names:
        if type(name) is not str or not name.strip() or "\x00" in name or name in seen:
            continue
        seen.add(name)
        candidate = query + " " + name
        # Keep whole declared names; a long field must not invalidate retrieval
        # or crowd later short fields past the lexical search's 64-term limit.
        if len(candidate) <= 512 and len(set(knowledge.tokens(candidate))) <= 64:
            query = candidate
    return query


def _remaining_question_need(project):
    questions = (project.get("next_decision") or {}).get("remaining_questions", [])
    if type(questions) is not list:
        return None
    for question in questions:
        if type(question) is not str:
            continue
        query = question.strip()
        if not query or len(query) > 512 or not 1 <= len(set(knowledge.tokens(query))) <= 64:
            continue
        # Keep the literal identifier while also matching separately stored field/value tokens.
        aliases = dict.fromkeys(re.sub(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])", " ", term)
                                for term in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", query)
                                if re.search(r"[A-Za-z]\d|\d[A-Za-z]", term))
        for alias in aliases:
            candidate = query + " " + alias
            if len(candidate) <= 512 and len(set(knowledge.tokens(candidate))) <= 64:
                query = candidate
        return query
    return None


def decision_needs(project):
    method = project.get("registration", {}).get("method_id", "p02.saved-oof-residuals")
    # These are bounded lexical lookup needs, not scientific conclusions or
    # permission to execute a study. Only the registered primary is selected.
    cpu_needs = {
        "research.retrieval-fixed-pair": {
            "clarification": "citation retrieval cited document cited_doc_ids qrels annotation semantics",
            "design": "dev validation test query splits query_splits tfidf cosine baseline tfidf_cosine bm25 candidate top20",
            "preparation": "corpus queries qrels document identifiers source provenance license",
            "interpretation": "recall mrr ndcg adverse queries adverse_queries unretrieved citations",
        },
        "research.relevance-fixed-pair": {
            "clarification": "relevance qrels positive grades binary projection qrels_semantics",
            "design": "dev validation test query splits query_splits bm25 baseline tfidf cosine candidate tfidf_cosine top20",
            "preparation": "corpus queries qrels grades document_grades identical query document id exclusion ignore_identical_ids",
            "interpretation": "recall mrr ndcg adverse queries adverse_queries missing positive denominator missing_positive_document_ids",
        },
        "research.weighted-interval-fixed-pair": {
            "clarification": "synthetic weighted interval scheduling jobs objective weight",
            "design": "quadratic scan dp baseline quadratic_scan_dp binary search dp candidate binary_search_dp fixed cases repetitions",
            "preparation": "job identifiers jobs_sha256 start end weight compatibility tie rule",
            "interpretation": "saved schedule feasibility objective timing adverse slower cases adverse_cases",
        },
    }
    if isinstance(method, str) and method in cpu_needs:
        needs = cpu_needs[method]
        needs["interpretation"] = _remaining_question_need(project) or needs["interpretation"]
        return needs
    if method == "data.tabular-quality-audit":
        return {"clarification": "dataset columns target unit", "design": "group key independence duplicates",
                "preparation": "numeric_columns missing_tokens group_columns",
                "interpretation": _remaining_question_need(project) or _data_interpretation(project.get("source_scope", {}))}
    if method == "materials.saved-steel-audit":
        return {"clarification": "yield strength composition MPa", "design": "linear interaction validation holdout",
                "preparation": "composition processing heat treatment microstructure", "interpretation": "validation MSE threshold external validation"}
    if method == "software.source-integrity-check":
        return {"clarification": "file capture consistency Windows", "design": "lstat fstat ctime semantics",
                "preparation": "source bytes hash task binding", "interpretation": "mutation file identity filesystem"}
    return {"clarification": "ALP red intensity endpoint", "design": "chemistry topography comparison",
            "preparation": "ObjectName column channel Count Intensity", "interpretation": "CropRed NaN batch export mapping"}


def code_identity():
    return hashlib.sha256(Path(__file__).read_bytes() + Path(knowledge.__file__).read_bytes()).hexdigest()


def build(root, action, tool_result):
    root = Path(root)
    destination = root / "knowledge" / action["id"]
    if destination.exists():
        ref = json.loads((destination / "reference.json").read_bytes())
        index = knowledge.KnowledgeIndex(destination / "index.sqlite")
        if (ref["action_id"] != action["id"] or ref["receipt_snapshot_sha256"] != action["receipt_snapshot_sha256"]
                or ref["database_sha256"] != index.manifest["database_sha256"]):
            raise ResearchError("EVIDENCE_CHANGED", "Saved project knowledge index differs from its source action.")
        return ref
    documents = []
    for selected in tool_result["result"]["selections"]:
        source = selected["source"]
        extraction = selected["extraction"]
        pdf = extraction.get("kind") == "pdf_page"
        document = {
            "id": action["id"] + ":" + selected["id"], "title": selected["id"] + " source mapping",
            "kind": "reuse_note", "source_url": source["url"],
            "path": "sources/" + source["asset_sha256"], "sha256": source["sha256"],
            "snapshot": action["receipt_snapshot_sha256"], "text": extraction["text"],
            "page": extraction["page"] if pdf else None, "review_status": "extracted_unreviewed",
            "metadata": {"source_role": "project_source_selection", "locator": selected["locator"],
                         "license_note": source["license_note"], "action_id": action["id"],
                         "selection_id": selected["id"], "source_id": source["id"],
                         "original_source_sha256": source["sha256"], "endpoint_eligibility": "unknown"},
        }
        if pdf:
            document["metadata"]["extraction"] = {key: extraction[key] for key in
                ("kind", "page", "document_pages", "start_char", "end_char", "offset_basis", "page_text_sha256", "text_sha256")}
        documents.append(document)
    # Incomplete builds remain separate; recovery can rebuild the index from a complete saved extraction.
    staging = destination.with_name(destination.name + ".pending-" + uuid.uuid4().hex)
    staging.mkdir(parents=True)
    manifest = knowledge.build_index(documents, staging / "index.sqlite", audit={
        "action_id": action["id"], "receipt_snapshot_sha256": action["receipt_snapshot_sha256"],
        "scope": "indexed_exact_extracted_selections_not_full_sources"})
    ref = {"action_id": action["id"], "receipt_snapshot_sha256": action["receipt_snapshot_sha256"],
           "directory": "knowledge/" + action["id"], "database_sha256": manifest["database_sha256"],
           "corpus_sha256": manifest["corpus_sha256"], "documents": manifest["documents"]}
    (staging / "reference.json").write_text(canonical(ref), encoding="utf-8")
    staging.rename(destination)
    return ref


def query(root, project, *, need, point="interpretation", limit=5):
    if point not in POINTS or type(limit) is not int or not 1 <= limit <= 8:
        raise ResearchError("INVALID_REQUEST", "Use one of the four decision points and limit 1..8.")
    if not isinstance(need, str) or not 1 <= len(need.strip()) <= 512:
        raise ResearchError("INVALID_REQUEST", "Knowledge need must contain 1..512 characters.")
    evidence, indexes = [], []
    # New completed extractions must reach the bounded context before older hits.
    for ref in reversed(project.get("knowledge_refs", [])):
        relative = Path(ref["directory"])
        if relative.parts != ("knowledge", ref["action_id"]):
            raise ResearchError("EVIDENCE_CHANGED", "Invalid knowledge reference path.")
        target = Path(root) / relative / "index.sqlite"
        for path in (target, *target.parents):
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise ResearchError("UNSAFE_PATH", "Project knowledge path redirects.")
        index = knowledge.KnowledgeIndex(target)
        if index.manifest["database_sha256"] != ref["database_sha256"]:
            raise ResearchError("EVIDENCE_CHANGED", "Project index content changed.")
        reply = index.search(need, limit=limit)
        evidence.extend(reply["evidence"])
        indexes.append(ref)
    return {"decision_point": point, "need": need, "evidence": evidence[:limit],
            "index_refs": indexes, "omitted_hits": max(0, len(evidence) - limit),
            "scope": "exact_extracted_selections_only", "may_execute": False,
            "scientific_validation": False, "endpoint_eligibility": "unknown",
            "notice": "Retrieval records actual returned excerpts, not model use, scientific support or author confirmation."}
