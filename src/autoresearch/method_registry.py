"""Explicit local method registry; domain adapters share execution, never target semantics."""
import hashlib
from pathlib import Path

from . import saved_oof_adapter, steel_audit_adapter, source_integrity_adapter, tabular_quality_adapter, grouped_quality_adapter, workbook_projection_adapter, numeric_association_adapter
from . import prediction_adapter, ridge_validation_adapter, saved_oof_diagnostic_adapter
from .contracts import ResearchError

SOURCE = "research.source-selection"
LEGACY_SOURCE = "p02.source-mapping-check"
PRIMARY = {module.TOOL_ID: module for module in (saved_oof_adapter, steel_audit_adapter, source_integrity_adapter, tabular_quality_adapter)}
WORKBOOK = workbook_projection_adapter.TOOL_ID
NUMERIC = numeric_association_adapter.TOOL_ID
PREDICTIONS = {module.TOOL_ID: module for module in prediction_adapter.ADAPTERS}
RIDGE = {module.TOOL_ID: module for module in ridge_validation_adapter.ADAPTERS}
DIAGNOSTICS = {module.TOOL_ID: module for module in saved_oof_diagnostic_adapter.ADAPTERS}
DESIGN_METHODS = PREDICTIONS | RIDGE
FOLLOWUP = {module.TOOL_ID: module for module in (grouped_quality_adapter, workbook_projection_adapter, numeric_association_adapter)} | DESIGN_METHODS | DIAGNOSTICS


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
            WORKBOOK: "workbook-projection-v1"}[method_id]


def code_identity():
    digest = hashlib.sha256(Path(__file__).read_bytes())
    for key, module in sorted((PRIMARY | FOLLOWUP).items()):
        digest.update(key.encode("utf-8")); digest.update(module.code_identity().encode("ascii"))
    return digest.hexdigest()
