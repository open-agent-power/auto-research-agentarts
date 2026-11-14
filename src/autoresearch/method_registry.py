"""Explicit local method registry; domain adapters share execution, never target semantics."""
import hashlib
from importlib.metadata import version as package_version
from pathlib import Path

from . import saved_oof_adapter, steel_audit_adapter, source_integrity_adapter, tabular_quality_adapter, grouped_quality_adapter, workbook_projection_adapter, numeric_association_adapter
from . import prediction_adapter, ridge_validation_adapter, saved_oof_diagnostic_adapter
from .contracts import ResearchError, canonical
from . import retrieval_adapter, relevance_retrieval_adapter, scheduling_adapter, staged_relevance_adapter, retrieval_holdout

SOURCE = "research.source-selection"
LEGACY_SOURCE = "p02.source-mapping-check"
PRIMARY = {module.TOOL_ID: module for module in (saved_oof_adapter, steel_audit_adapter, source_integrity_adapter, tabular_quality_adapter, retrieval_adapter, relevance_retrieval_adapter, scheduling_adapter, staged_relevance_adapter)}
WORKBOOK = workbook_projection_adapter.TOOL_ID
NUMERIC = numeric_association_adapter.TOOL_ID
PREDICTIONS = {module.TOOL_ID: module for module in prediction_adapter.ADAPTERS}
RIDGE = {module.TOOL_ID: module for module in ridge_validation_adapter.ADAPTERS}
DIAGNOSTICS = {module.TOOL_ID: module for module in saved_oof_diagnostic_adapter.ADAPTERS}
DESIGN_METHODS = PREDICTIONS | RIDGE
SAVED_PAIR_AUDITS = {item.TOOL_ID: item for item in (retrieval_adapter.AUDIT, relevance_retrieval_adapter.AUDIT, scheduling_adapter.AUDIT, staged_relevance_adapter.AUDIT)}
STAGED_FINALS = {retrieval_holdout.FINAL_TOOL_ID: retrieval_holdout.FINAL}
SAVED_PAIR_PARENTS = {retrieval_adapter.AUDIT_TOOL_ID: retrieval_adapter.TOOL_ID,
                      relevance_retrieval_adapter.AUDIT_TOOL_ID: relevance_retrieval_adapter.TOOL_ID,
                      staged_relevance_adapter.AUDIT_TOOL_ID: staged_relevance_adapter.TOOL_ID,
                      retrieval_holdout.FINAL_TOOL_ID: staged_relevance_adapter.TOOL_ID,
                      scheduling_adapter.AUDIT_TOOL_ID: scheduling_adapter.TOOL_ID}
SAVED_PAIR_KINDS = {retrieval_adapter.TOOL_ID: "citation_retrieval_pair",
                   relevance_retrieval_adapter.TOOL_ID: "relevance_retrieval_pair",
                   staged_relevance_adapter.TOOL_ID: "staged_relevance_validation_pair",
                   scheduling_adapter.TOOL_ID: "weighted_interval_fixed_pair"}
FOLLOWUP = {module.TOOL_ID: module for module in (grouped_quality_adapter, workbook_projection_adapter, numeric_association_adapter)} | DESIGN_METHODS | DIAGNOSTICS | SAVED_PAIR_AUDITS | STAGED_FINALS


def primary_id(project):
    return project.get("registration", {}).get("method_id", saved_oof_adapter.TOOL_ID)


def get(method_id):
    try:
        return PRIMARY[method_id]
    except (KeyError, TypeError):
        raise ResearchError("METHOD_NOT_SUPPORTED", "Select an explicitly registered local method.") from None


def get_analysis(method_id):
    try:
        return (PRIMARY | FOLLOWUP)[method_id]
    except (KeyError, TypeError):
        raise ResearchError("METHOD_NOT_SUPPORTED", "Select an explicitly registered analysis method.") from None


def followup_ids(primary_method_id):
    get(primary_method_id)
    if primary_method_id in SAVED_PAIR_KINDS:
        return [key for key, parent in SAVED_PAIR_PARENTS.items() if parent == primary_method_id]
    return [*DESIGN_METHODS, grouped_quality_adapter.TOOL_ID, WORKBOOK, NUMERIC, *DIAGNOSTICS] if primary_method_id == tabular_quality_adapter.TOOL_ID else []


def source_id(project):
    return LEGACY_SOURCE if primary_id(project) == saved_oof_adapter.TOOL_ID else SOURCE


def is_source(method_id):
    return method_id in (SOURCE, LEGACY_SOURCE)


def evaluation_ref(method_id):
    get_analysis(method_id)
    if method_id in PREDICTIONS:
        return "prediction-check-" + PREDICTIONS[method_id].check + "-v1"
    if method_id in RIDGE:
        return "ridge-validation-" + RIDGE[method_id].check + "-v1"
    if method_id in DIAGNOSTICS:
        return "saved-oof-" + DIAGNOSTICS[method_id].check + "-diagnostics-v1"
    return {saved_oof_adapter.TOOL_ID: "P02-frozen-within-policy-OOF",
            steel_audit_adapter.TOOL_ID: "materials-composition-holdout-v1",
            source_integrity_adapter.TOOL_ID: "file-capture-consistency-v1",
            tabular_quality_adapter.TOOL_ID: "tabular-quality-v1",
            grouped_quality_adapter.TOOL_ID: "grouped-quality-profile-v1",
            NUMERIC: "numeric-association-v1",
            WORKBOOK: "workbook-projection-v1",
            retrieval_adapter.TOOL_ID: "citation-retrieval-fixed-pair-v1",
            retrieval_adapter.AUDIT_TOOL_ID: "citation-retrieval-saved-error-audit-v1",
            relevance_retrieval_adapter.TOOL_ID: "relevance-retrieval-fixed-pair-v1",
            relevance_retrieval_adapter.AUDIT_TOOL_ID: "relevance-retrieval-saved-error-audit-v1",
            staged_relevance_adapter.TOOL_ID: "staged-relevance-development-v1",
            staged_relevance_adapter.AUDIT_TOOL_ID: "staged-relevance-development-saved-audit-v1",
            retrieval_holdout.FINAL_TOOL_ID: "staged-relevance-frozen-final-v1",
            scheduling_adapter.TOOL_ID: "weighted-interval-fixed-pair-v1",
            scheduling_adapter.AUDIT_TOOL_ID: "weighted-interval-saved-audit-v1"}[method_id]


def runtime_dependencies():
    """Numerical runtime is part of execution identity, not just source bytes.

    GroupKFold 1.9 changes actual partitions relative to 1.8. A dependency
    upgrade must not silently continue an older project's evaluation.
    """
    import numpy
    import scipy
    import sklearn
    loaded = {"numpy": numpy.__version__, "scipy": scipy.__version__, "scikit-learn": sklearn.__version__}
    installed = {name: package_version(name) for name in loaded}
    if loaded != installed:
        raise ResearchError("RUNTIME_CHANGED", "Loaded numerical modules differ from installed distributions; restart with the registered environment.")
    return loaded


def code_identity():
    digest = hashlib.sha256(Path(__file__).read_bytes())
    digest.update(canonical({"runtime_dependencies": runtime_dependencies()}).encode("utf-8"))
    for key, module in sorted((PRIMARY | FOLLOWUP).items()):
        digest.update(key.encode("utf-8")); digest.update(module.code_identity().encode("ascii"))
    return digest.hexdigest()
