"""Byte-bound S108 published aggregate as a separate historical observation.

This reader never loads the original projects or recomputes query metrics.
An original primary ID identifies the source, not an action producing this audit.
"""
import copy
import hashlib

from . import research_recipe, staged_relevance_adapter as staged
from .contracts import ResearchError, canonical, fingerprint, identifier
from .research_memory import ResearchMemory, observation_id, validate_scope

SCHEMA = "posthoc-validation-loss-experience-bundle-v1"
PROTOCOL = "s108-posthoc-validation-loss-binding-v1"
RESULT_SHA256 = "762d92f53422976fd6b0928f4a7f35d0572fc6803bfb11cb04315cc1176493f8"
PROTOCOL_SHA256 = "bef2c9e49cb2323be5d16918703beb09b09aac19271186e059554e5685da1e70"
READER_SHA256 = "910e5715a533483aca7066e92a85591e7a3c351ae265d1d1196479eab0d6f07e"
RESULT_COMMIT = "5fa9dce69fd447e9c885e15e732667caf1af5df5"
READER_COMMIT = "a4c2eb01e92526b73e2dee4e24f1ba7aa38d5867"
EVALUATION = "staged-relevance-development-v1"
SELECTOR = {"split": "validation", "direction": "tfidf_cosine_minus_bm25", "epsilon": 1e-12,
            "recall": "abs(delta_recall@20) <= epsilon", "mrr": "delta_mrr@10 < -epsilon",
            "magnitude": "mean_negative_delta_mrr@10_rounded_4_decimals"}
NOTICE = ("Published aggregate byte binding requires origin; this import did not recompute the source data or verify a signature. "
          "The original primary action is a source reference, not the producer of this later analysis. "
          "Exposed validation data, post hoc selected negative subset, not blind, causal, anonymous, or an overall result. "
          "Four-place rounding may show 0.0000 for a nonzero loss; applicability and transfer remain unverified. "
          "Scope inputs_sha256 fingerprints the published result SHA and case label, not the original input bytes; "
          "source_manifest_sha256 records the original source snapshot identity, not a newly verified manifest file.")

CASES = {
    "S065": {"project_id": "project-2376ca4a6db64027a1099bd737ca9640", "run_id": "run-a1a631efa41541e2800b43ae047c4c66",
             "primary_action_id": "action-4de378649a2bc9026793872874663343", "primary_result_sha256": "32ced585400985fc64fb30b97877ba2ccc71c1164a651766764af4b49f0a9b1a",
             "primary_artifact_sha256": "d75481f0f3b2a2f502aa299cc42224fc9af26e9fe3b43d2aa08ba736cbfa4502",
             "source_snapshot_sha256": "c7bd3a7286072af61cd53b20465bc6f5dde3ecefae759cc5b0d08fb4c9da9dfb", "source_commit": "5d431097f3b4846ac240745121e56070edd78e86", "count": 16, "mean_mrr_loss": 0.4026},
    "S067": {"project_id": "project-dc1b1b59889f49c0b744254b1a1afd68", "run_id": "run-276475c33d7542509c840bc575005271",
             "primary_action_id": "action-ad83795edf793a9dc19125edbd2ee442", "primary_result_sha256": "5d75076370f74f6b41bde4c214428957d7531defe073bdce124404a864fad15f",
             "primary_artifact_sha256": "4f9ad51aa8f88074697e66f04631083c32e5f5e4c49be6d5746216c92edc8dd3",
             "source_snapshot_sha256": "2ab8f454956a0b0b75df792cfe9ab37cf7942df769963c58fb9c238d021f8dcb", "source_commit": "5bd9883dd435a1d39b857a51bb6f4d20a53f156b", "count": 24, "mean_mrr_loss": 0.3724},
}
PRODUCER_CORE = "ca09803b71c2bfd82a3356d428f4f05b8a311da433ea1109019e556b53d7c572"


def _require(value, message, code="INVALID_POSTHOC_EXPERIENCE"):
    if not value:
        raise ResearchError(code, message)


def _projection(label):
    _require(type(label) is str and label in CASES, "Unsupported published case.")
    item = CASES[label]
    return {"case": label, "project_id": item["project_id"], "run_id": item["run_id"],
            "primary_action_id": item["primary_action_id"], "primary_result_sha256": item["primary_result_sha256"],
            "primary_artifact_sha256": item["primary_artifact_sha256"], "source_snapshot_sha256": item["source_snapshot_sha256"],
            "source_commit": item["source_commit"], "producer_core": PRODUCER_CORE,
            "cell": {"status": "available", "count": item["count"], "mean_mrr_loss": item["mean_mrr_loss"]}}


def _record(label):
    source = _projection(label)
    scope = {"source_manifest_sha256": source["source_snapshot_sha256"],
             "inputs_sha256": fingerprint({"published_result_sha256": RESULT_SHA256, "case": label}),
             "analysis_code_sha256": READER_SHA256, "protocol": PROTOCOL}
    record = {"schema_version": "conditional-research-memory-v1", "kind": "diagnostic_observation", "scope": scope,
              "review_status": "derived_not_scientifically_reviewed", "numerical_recomputation": False,
              "payload": {"method_id": staged.TOOL_ID, "evaluation_ref": EVALUATION,
                          "selector": copy.deepcopy(SELECTOR), "cell": source["cell"], "limitations": [NOTICE]},
              "provenance": {"action_id": source["primary_action_id"],
                             "action_role": "upstream_primary_reference_not_audit_producer", "source_record_sha256": RESULT_SHA256,
                             "published_case": source, "protocol_sha256": PROTOCOL_SHA256,
                             "reader_sha256": READER_SHA256, "result_commit": RESULT_COMMIT, "reader_commit": READER_COMMIT}}
    record["id"] = observation_id(record)
    return record


def derive_published(result_bytes, protocol_bytes, case):
    """Bind exact published bytes; do not read or recompute the underlying studies."""
    _require(type(result_bytes) is bytes and hashlib.sha256(result_bytes).hexdigest() == RESULT_SHA256
             and type(protocol_bytes) is bytes and hashlib.sha256(protocol_bytes).hexdigest() == PROTOCOL_SHA256,
             "Published result or protocol bytes differ.", "EVIDENCE_CHANGED")
    result = research_recipe.parse_json(result_bytes, maximum=64 * 1024, code="INVALID_POSTHOC_EXPERIENCE")
    protocol = research_recipe.parse_json(protocol_bytes, maximum=64 * 1024, code="INVALID_POSTHOC_EXPERIENCE")
    expected = _projection(case)
    rows = result.get("cases")
    matches = [row for row in rows if type(row) is dict and row.get("case") == case] if type(rows) is list else []
    _require(len(matches) == 1 and canonical(matches[0]) == canonical(expected)
             and result.get("schema_version") == "saved-unchanged-recall-mrr-loss-v1"
             and result.get("protocol_sha256") == PROTOCOL_SHA256 and result.get("script_sha256") == READER_SHA256
             and result.get("reader_commit") == READER_COMMIT
             and protocol.get("schema_version") == "saved-validation-unchanged-recall-mrr-loss-protocol-v1"
             and protocol.get("split") == SELECTOR["split"] and protocol.get("direction") == SELECTOR["direction"]
             and type(protocol.get("epsilon")) is float and protocol["epsilon"] == SELECTOR["epsilon"],
             "Published projection or protocol differs.", "EVIDENCE_CHANGED")
    protocol_rows = protocol.get("cases")
    matches = [row for row in protocol_rows if type(row) is dict and row.get("label") == case] if type(protocol_rows) is list else []
    _require(len(matches) == 1 and all(matches[0].get(k) == expected[k] for k in
             ("project_id", "run_id", "primary_action_id", "primary_result_sha256", "source_snapshot_sha256", "source_commit", "producer_core")),
             "Published case identity differs.", "EVIDENCE_CHANGED")
    record = _record(case)
    return {"scope": record["scope"], "entries": [record], "validation": {
        "published_bytes_matched_at_import": True, "offline_binding_requires_origin": True,
        "underlying_data_recomputed": False, "signature_verified": False, "scientific_validation": False}}


def validate_bundle(bundle):
    try:
        _require(type(bundle) is dict and set(bundle) == {"schema_version", "id", "version", "record", "method_card", "limitations", "source_inclusion_status", "scientific_validation"}
                 and bundle["schema_version"] == SCHEMA and bundle["source_inclusion_status"] == "active_at_export"
                 and bundle["scientific_validation"] is False and type(bundle["version"]) is int and 1 <= bundle["version"] <= 2**31 - 1,
                 "Invalid post-hoc bundle.")
        identifier(bundle["id"], "case_id")
        _require(len(canonical(bundle).encode("utf-8")) <= 4 * 1024 * 1024, "Bundle too large.", "BUNDLE_TOO_LARGE")
        record = bundle["record"]
        label = record["provenance"]["published_case"]["case"]
        _require(canonical(record) == canonical(_record(label)), "Published case projection changed.", "EVIDENCE_CHANGED")
        card = research_recipe.validate_method_card(bundle["method_card"])
        _require(card["scope_match"] == {"domain": "retrieval", "contract": staged.CONTRACT}
                 and card["method_refs"] == [{"method_id": staged.TOOL_ID, "evaluation_ref": EVALUATION}], "Invalid method card scope.")
        _require(type(bundle["limitations"]) is list and 1 <= len(bundle["limitations"]) <= 8
                 and all(type(x) is str and 0 < len(x.strip()) <= 4000 and "\x00" not in x for x in bundle["limitations"]), "Invalid limitations.")
        return copy.deepcopy(bundle)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError, OverflowError):
        raise ResearchError("INVALID_POSTHOC_EXPERIENCE", "Malformed post-hoc experience.") from None


def summary(bundle):
    bundle = validate_bundle(bundle)
    record = bundle["record"]
    source = record["provenance"]["published_case"]
    value = {"case_id": bundle["id"], "case_version": bundle["version"], "entry_id": record["id"],
             "method_card": bundle["method_card"], "origin_evidence": {"project_id": source["project_id"],
                "run_id": source["run_id"], "action_id": source["primary_action_id"],
                "action_role": "upstream_primary_reference_not_audit_producer",
                "result_sha256": source["primary_result_sha256"], "source_snapshot_sha256": source["source_snapshot_sha256"],
                "primary_artifact_sha256": source["primary_artifact_sha256"], "source_commit": source["source_commit"],
                "producer_core": source["producer_core"],
                "published_result_sha256": RESULT_SHA256, "protocol_sha256": PROTOCOL_SHA256,
                "reader_sha256": READER_SHA256, "result_commit": RESULT_COMMIT, "reader_commit": READER_COMMIT},
             "source_scope": {"domain": "retrieval", "contract": staged.CONTRACT, "source_case": source["case"]},
             "observation": {"kind": "posthoc_validation_loss", "selector": copy.deepcopy(SELECTOR),
                             "cell": copy.deepcopy(source["cell"]), "verification": "published_binding_requires_origin; no_recomputation_or_signature"},
             "limitations": [*bundle["limitations"], NOTICE], "transfer_scope": "analogy_not_current_evidence", "scientific_validation": False}
    _require(len(canonical(value).encode("utf-8")) <= 64 * 1024, "Summary too large.", "SUMMARY_TOO_LARGE")
    return value


class PosthocLossExperienceMemory(ResearchMemory):
    def import_published(self, result_bytes, protocol_bytes, case):
        return self._import_derived(derive_published(result_bytes, protocol_bytes, case), verification="binding")

    def export_case(self, scope, entry_id, *, case_id, version, method_card, limitations):
        validate_scope(scope)
        with self._connect() as con:
            row = con.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone() if con is not None else None
            _require(row is not None, "Post-hoc memory entry not found.", "NOT_FOUND")
            record = self._verify(con, row)
            _require(record["scope"] == scope and row["status"] == "active", "Post-hoc entry is not active under this scope.")
            return validate_bundle({"schema_version": SCHEMA, "id": case_id, "version": version, "record": record,
                                    "method_card": method_card, "limitations": limitations,
                                    "source_inclusion_status": "active_at_export", "scientific_validation": False})
