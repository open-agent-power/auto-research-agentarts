"""Explicit local method registry; domain adapters share execution, never target semantics."""
import hashlib
from pathlib import Path

from . import saved_oof_adapter, steel_audit_adapter, source_integrity_adapter, tabular_quality_adapter, grouped_quality_adapter
from .contracts import ResearchError

SOURCE = "research.source-selection"
LEGACY_SOURCE = "p02.source-mapping-check"
PRIMARY = {module.TOOL_ID: module for module in (saved_oof_adapter, steel_audit_adapter, source_integrity_adapter, tabular_quality_adapter)}
FOLLOWUP = {grouped_quality_adapter.TOOL_ID: grouped_quality_adapter}


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
    return [grouped_quality_adapter.TOOL_ID] if primary_method_id == tabular_quality_adapter.TOOL_ID else []


def source_id(project):
    return LEGACY_SOURCE if primary_id(project) == saved_oof_adapter.TOOL_ID else SOURCE


def is_source(method_id):
    return method_id in (SOURCE, LEGACY_SOURCE)


def evaluation_ref(method_id):
    get_analysis(method_id)
    return {saved_oof_adapter.TOOL_ID: "P02-frozen-within-policy-OOF",
            steel_audit_adapter.TOOL_ID: "materials-composition-holdout-v1",
            source_integrity_adapter.TOOL_ID: "file-capture-consistency-v1",
            tabular_quality_adapter.TOOL_ID: "tabular-quality-v1",
            grouped_quality_adapter.TOOL_ID: "grouped-quality-profile-v1"}[method_id]


def code_identity():
    digest = hashlib.sha256(Path(__file__).read_bytes())
    for key, module in sorted((PRIMARY | FOLLOWUP).items()):
        digest.update(key.encode("utf-8")); digest.update(module.code_identity().encode("ascii"))
    return digest.hexdigest()
