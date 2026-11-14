"""Portable CPU saved-result experience; no study execution or scientific approval.

Capture validates the original packet. Offline validation checks the retained
specification, saved result, and identities; original asset bytes are references.
"""
import base64
import copy
import hashlib
from pathlib import Path
import re

from . import retrieval_adapter, relevance_retrieval_adapter, scheduling_adapter, research_recipe
from . import source_evidence_adapter as source_reader
from .contracts import ResearchError, canonical, fingerprint, identifier
from .research_memory import ResearchMemory, observation_id, validate_scope
from .research_project import ResearchProject, code_identity as runtime_code_identity

MAX_BUNDLE_BYTES = 4 * 1024 * 1024
PROTOCOL = "project-saved-cpu-byte-binding-v1"
SCHEMA = "cpu-project-experience-bundle-v1"
FAMILIES = {
    retrieval_adapter.TOOL_ID: (retrieval_adapter, "citation-retrieval-fixed-pair-v1", "citation-retrieval-result-v1"),
    relevance_retrieval_adapter.TOOL_ID: (relevance_retrieval_adapter, "relevance-retrieval-fixed-pair-v1", "relevance-retrieval-result-v1"),
    scheduling_adapter.TOOL_ID: (scheduling_adapter, "weighted-interval-fixed-pair-v1", "weighted-interval-result-v1"),
}
NOTICE = ("The original source packet and asset bytes are not included; their hashes and sizes are references. "
          "Native capture checked the original bytes, but offline validation cannot independently recompute the source snapshot. "
          "Self-contained hashes are not signatures or independent proof of provenance, scientific validity, or license approval; "
          "offline checks do not recalculate retrieval metrics or solve schedules.")


def _require(condition, message, code="INVALID_CPU_EXPERIENCE"):
    if not condition:
        raise ResearchError(code, message)


def _hash(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _checked(action, envelope, origin, source):
    identifier(action["id"], "action_id")
    identifier(action["request_id"], "request_id")
    identifier(origin["project_id"], "project_id")
    identifier(origin["run_id"], "run_id")
    _require(action["command"] in FAMILIES, "Only three primary CPU methods are supported.")
    module, evaluation, schema = FAMILIES[action["command"]]
    _require(action["status"] == "completed" and action["project_id"] == origin["project_id"]
             and action["run_id"] == origin["run_id"] and action["dimension"] is None
             and action["artifact"] == "artifacts/" + action["id"] + ".json"
             and action["source_snapshot_sha256"] == origin["source_snapshot_sha256"]
             and action["code_identity"] == origin["producer_code_identity"]
             and all(_hash(action[k]) for k in ("request_sha256", "result_sha256", "code_identity")),
             "Completed action identity differs.", "EVIDENCE_CHANGED")
    request = {"project_id": origin["project_id"], "command": action["command"], "dimension": None,
               "source_snapshot_sha256": origin["source_snapshot_sha256"]}
    instance = {"definition_ref": {"id": action["command"], "version": module.ADAPTER_VERSION},
                "input_bindings": {"source_snapshot_sha256": origin["source_snapshot_sha256"]},
                "parameters": {}, "evaluation_ref": evaluation, "scope": origin["source_scope"]}
    _require(action["id"] == "action-" + fingerprint({"request_id": action["request_id"], **request})[:32]
             and action["request_sha256"] == fingerprint(request) and canonical(action["method_instance"]) == canonical(instance),
             "Primary request or method binding differs.", "EVIDENCE_CHANGED")
    _require(type(envelope) is dict and set(envelope) == {"action_id", "code_identity", "request_sha256", "sha256", "source_snapshot_sha256", "tool_result"}
             and envelope["sha256"] == fingerprint({k: v for k, v in envelope.items() if k != "sha256"}) == action["result_sha256"]
             and envelope["action_id"] == action["id"] and envelope["code_identity"] == action["code_identity"]
             and envelope["request_sha256"] == action["request_sha256"]
             and envelope["source_snapshot_sha256"] == origin["source_snapshot_sha256"], "Result envelope differs.", "EVIDENCE_CHANGED")
    tool = envelope["tool_result"]
    _require(type(tool) is dict and tool.get("schema_version") == schema and tool.get("tool_id") == action["command"]
             and tool.get("adapter_version") == module.ADAPTER_VERSION and tool.get("status") == "completed"
             and tool.get("scientific_validation") is False and tool.get("new_fits") == 0 and type(tool.get("new_fits")) is int
             and tool.get("model_calls") == 0 and type(tool.get("model_calls")) is int, "Invalid completed saved result.")
    # Only saved structure/arithmetic and, for scheduling, saved feasibility; no execute/retrieve/solve.
    saved = module._saved_checked(tool)
    _require(saved["source_snapshot_sha256"] == origin["source_snapshot_sha256"]
             and canonical(saved["scope"]) == canonical(origin["source_scope"])
             and canonical(saved["comparison"]) == canonical(source["spec"]["comparison"])
             and canonical(source["assets"]) == canonical(origin["source_scope"]["input_identities"]), "Saved values/source binding differ.", "EVIDENCE_CHANGED")
    if module is not scheduling_adapter:
        methods = ("tfidf_cosine", "bm25")
        expected = {(split, qid, method) for split, ids in source["spec"]["query_splits"].items()
                    for qid in ids for method in methods}
        rows = saved["per_query_metrics"]
        _require({(r["split"], r["query_id"], r["method"]) for r in rows} == expected,
                 "Saved query coverage differs from full specification.", "EVIDENCE_CHANGED")
        for row in rows:
            locator = row["qrel_locator"]
            role = "test_qrels" if row["split"] == "test" else "train_qrels"
            _require(locator["role"] == role and locator["kind"] == "tsv_query_documents"
                     and locator["query_id"] == row["query_id"]
                     and locator["source_sha256"] == source["assets"][role]["sha256"],
                     "Saved qrel locator differs from source reference.", "EVIDENCE_CHANGED")
        # Arithmetic on already saved metrics only; never score qrels or rank.
        paired, _, adverse = module._paired(rows)
        _require(canonical(paired) == canonical(saved["paired_summary"])
                 and canonical(adverse) == canonical(saved["adverse_queries"]),
                 "Saved metric summary or adverse rows differ.", "EVIDENCE_CHANGED")
    return saved


def _validate_record(record):
    _require(type(record) is dict and set(record) == {"schema_version", "id", "kind", "scope", "review_status", "numerical_recomputation", "payload", "provenance"}
             and record["schema_version"] == "conditional-research-memory-v1" and record["kind"] == "diagnostic_observation"
             and record["review_status"] == "derived_not_scientifically_reviewed" and record["numerical_recomputation"] is False,
             "Use a CPU byte-binding record.")
    scope = validate_scope(record["scope"])
    _require(set(scope) == {"source_manifest_sha256", "inputs_sha256", "analysis_code_sha256", "protocol"}
             and scope["protocol"] == PROTOCOL and observation_id(record) == record["id"], "CPU record scope differs.")
    p = record["provenance"]
    _require(type(p) is dict and set(p) == {"action_id", "source_record_sha256", "origin", "action", "artifact", "source"}
             and _hash(p["source_record_sha256"]), "CPU provenance differs.")
    origin, source, action, artifact = p["origin"], p["source"], p["action"], p["artifact"]
    _require(type(origin) is dict and set(origin) == {"project_id", "run_id", "state_version", "snapshot_ref", "source_snapshot_sha256", "source_scope", "source_file_sha256", "registered_project_code_identity", "producer_code_identity", "capture_runtime_code_identity", "capture_implementation_sha256"}
             and type(origin["state_version"]) is int and origin["state_version"] >= 0
             and all(_hash(origin[k]) for k in ("snapshot_ref", "source_snapshot_sha256", "source_file_sha256", "registered_project_code_identity", "producer_code_identity", "capture_runtime_code_identity", "capture_implementation_sha256"))
             and type(origin["source_scope"]) is dict and p["action_id"] == action["id"], "CPU origin differs.")
    _require(type(source) is dict and set(source) == {"task_kind", "spec", "spec_source", "assets", "source_inclusion"}
             and source["source_inclusion"] == "asset_bytes_excluded_hash_references_only"
             and type(source["assets"]) is dict and type(source["spec_source"]) is dict, "CPU source references differ.")
    module = FAMILIES.get(action.get("command"), (None,))[0]
    _require(module is not None, "Only primary CPU methods are supported.")
    _require(source["task_kind"] == {retrieval_adapter.TOOL_ID: "citation_retrieval",
             relevance_retrieval_adapter.TOOL_ID: "relevance_retrieval",
             scheduling_adapter.TOOL_ID: "weighted_interval"}[action["command"]], "Source task kind differs.")
    spec_asset = source["spec_source"]
    _require(set(spec_asset) == {"file_name", "sha256", "bytes", "bytes_base64"}, "Original spec bytes required.")
    try:
        spec_bytes = base64.b64decode(spec_asset["bytes_base64"], validate=True)
    except (ValueError, TypeError):
        raise ResearchError("INVALID_CPU_EXPERIENCE", "Invalid original specification encoding.") from None
    parsed_spec = module._parse(spec_bytes)
    module._spec(parsed_spec)
    _require(spec_asset["file_name"] == "spec.json" and len(spec_bytes) == spec_asset["bytes"]
             and hashlib.sha256(spec_bytes).hexdigest() == spec_asset["sha256"]
             and base64.b64encode(spec_bytes).decode("ascii") == spec_asset["bytes_base64"]
             and canonical(parsed_spec) == canonical(source["spec"]), "Original specification differs.", "EVIDENCE_CHANGED")
    _require(all(type(v) is dict and set(v) == {"sha256", "bytes"} and _hash(v["sha256"])
                 and type(v["bytes"]) is int and v["bytes"] > 0 for v in source["assets"].values()), "Invalid original asset references.")
    saved = _checked(action, artifact, origin, source)
    payload = {"method_id": action["command"], "evaluation_ref": action["method_instance"]["evaluation_ref"],
               "source_scope": origin["source_scope"], "paired_summary": saved["paired_summary"],
               "origin_limitations": saved["limitations"], "verification": "saved_only_binding_structure_and_arithmetic"}
    _require(scope["source_manifest_sha256"] == origin["source_snapshot_sha256"]
             and scope["inputs_sha256"] == fingerprint({"result_sha256": artifact["sha256"],
                                                        "retained_source_sha256": fingerprint(source)})
             and scope["analysis_code_sha256"] == fingerprint({"implementation_sha256": origin["capture_implementation_sha256"],
                                                               "runtime_code_identity": origin["capture_runtime_code_identity"]})
             and record["payload"] == payload,
             "CPU observation values differ.", "EVIDENCE_CHANGED")
    return record


def derive_cpu_observation(workspace, action_id):
    try:
        project = ResearchProject(workspace)
        before = project.status()
        identifier(action_id, "action_id")
        actions = [a for a in before["actions"] if a["id"] == action_id]
        _require(len(actions) == 1, "Select one registered action.", "ARTIFACT_NOT_FOUND")
        action = actions[0]
        _require(action["command"] in FAMILIES and action["status"] == "completed", "Only completed primary CPU actions are supported.", "ARTIFACT_NOT_AVAILABLE")
        module, evaluation, _ = FAMILIES[action["command"]]
        _require(before["registration"]["method_id"] == action["command"], "Registered method differs.", "EVIDENCE_CHANGED")
        raw = source_reader._read_file(Path(project.root).absolute() / "source.json", module.LIMITS["packet_bytes"])
        source_sha = hashlib.sha256(raw).hexdigest()
        _require(source_sha == before["registration"]["source_sha256"], "Registered source bytes differ.", "EVIDENCE_CHANGED")
        packet = module._parse(raw)
        checked_source = module._checked(packet)  # Captured original packet validation, no new research.
        spec = checked_source[0]
        _require(packet["snapshot_sha256"] == before["source_snapshot_sha256"] and packet["scope"] == before["source_scope"], "Captured source differs.", "EVIDENCE_CHANGED")
        supported = [m for m in before.get("supported_methods", []) if m.get("id") == action["command"]]
        if "supported_methods" in before:
            _require(len(supported) == 1 and supported[0]["version"] == module.ADAPTER_VERSION and supported[0]["scope"] == before["source_scope"]
                     and supported[0].get("evaluation_ref", evaluation) == evaluation, "Registered method version differs.", "EVIDENCE_CHANGED")
        artifact_raw = source_reader._read_file(Path(project.root).absolute() / "artifacts" / (action_id + ".json"), 5 * 1024 * 1024)
        envelope = module._parse(artifact_raw)
        origin = {"project_id": before["id"], "run_id": before["run_id"], "state_version": before["state_version"],
                  "snapshot_ref": before["snapshot_ref"], "source_snapshot_sha256": before["source_snapshot_sha256"],
                  "source_scope": before["source_scope"], "source_file_sha256": source_sha,
                  "registered_project_code_identity": before["code_identity"], "producer_code_identity": action["code_identity"],
                  "capture_runtime_code_identity": runtime_code_identity(),
                  "capture_implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        source = {"task_kind": packet["task_kind"], "spec": spec, "spec_source": packet["spec_source"],
                  "assets": {k: {field: v[field] for field in ("sha256", "bytes")} for k, v in packet["assets"].items()},
                  "source_inclusion": "asset_bytes_excluded_hash_references_only"}
        saved = _checked(action, envelope, origin, source)
        # Bind already saved locations/jobs to the original source parsed above;
        # these are identity/coverage checks, not retrieval, scoring or solving.
        if module is scheduling_adapter:
            original_cases = checked_source[1]["cases"]
            case_inputs = [{k: case[k] for k in ("case_id", "split", "seed", "jobs_sha256", "jobs")}
                           for case in saved["cases"]]
            _require(canonical(case_inputs) == canonical(original_cases),
                     "Saved jobs differ from captured original source.", "EVIDENCE_CHANGED")
        else:
            _, docs, queries, qrels, doc_lines, query_lines = checked_source
            for row in saved["rankings"]:
                _require(row["query_id"] in queries and row["query_line"] == query_lines[row["query_id"]]
                         and all(doc in docs and doc_lines[doc] == line
                                 for doc, line in zip(row["ranking"], row["ranked_doc_lines"])),
                         "Saved ranking locations differ from captured source.", "EVIDENCE_CHANGED")
            for row in saved["per_query_metrics"]:
                relevant = qrels["test" if row["split"] == "test" else "train"][row["query_id"]]
                locator = row["qrel_locator"]
                _require(set(locator["document_ids"]) == set(relevant)
                         and len(locator["document_ids"]) == len(set(locator["document_ids"]))
                         and (module is not relevance_retrieval_adapter or locator["document_grades"] == relevant),
                         "Saved qrel locations differ from captured source.", "EVIDENCE_CHANGED")
        scope = {"source_manifest_sha256": before["source_snapshot_sha256"],
                 "inputs_sha256": fingerprint({"result_sha256": envelope["sha256"], "retained_source_sha256": fingerprint(source)}),
                 "analysis_code_sha256": fingerprint({"implementation_sha256": origin["capture_implementation_sha256"],
                     "runtime_code_identity": origin["capture_runtime_code_identity"]}), "protocol": PROTOCOL}
        payload = {"method_id": action["command"], "evaluation_ref": evaluation, "source_scope": before["source_scope"],
                   "paired_summary": saved["paired_summary"], "origin_limitations": saved["limitations"],
                   "verification": "saved_only_binding_structure_and_arithmetic"}
        entry = {"schema_version": "conditional-research-memory-v1", "kind": "diagnostic_observation", "scope": scope,
                 "review_status": "derived_not_scientifically_reviewed", "numerical_recomputation": False, "payload": payload,
                 "provenance": {"action_id": action_id, "source_record_sha256": fingerprint(before), "origin": origin,
                                "action": copy.deepcopy(action), "artifact": envelope, "source": source}}
        entry["id"] = observation_id(entry)
        _validate_record(entry)
        _require(project.status() == before, "Project changed during capture.", "STALE_STATE")
        _require(runtime_code_identity() == origin["capture_runtime_code_identity"]
                 and hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == origin["capture_implementation_sha256"],
                 "Capture implementation changed during capture.", "STALE_STATE")
        return {"scope": scope, "entries": [entry], "validation": {"protocol": PROTOCOL, "source_packet_checked_at_capture": True,
                "offline_verification": "saved_only_binding_structure_and_arithmetic", "scientific_validation": False}}
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, UnicodeError, OverflowError, RecursionError):
        raise ResearchError("EVIDENCE_CHANGED", "CPU project or saved result is malformed.") from None


def validate_bundle(bundle):
    try:
        _require(type(bundle) is dict and set(bundle) == {"schema_version", "id", "version", "record", "method_card", "limitations", "source_inclusion_status", "scientific_validation"}
                 and bundle["schema_version"] == SCHEMA and bundle["source_inclusion_status"] == "active_at_export"
                 and bundle["scientific_validation"] is False and type(bundle["version"]) is int and 1 <= bundle["version"] <= 2**31-1,
                 "Invalid CPU experience bundle.")
        identifier(bundle["id"], "case_id")
        _require(len(canonical(bundle).encode("utf-8")) <= MAX_BUNDLE_BYTES, "CPU experience bundle exceeds 4 MiB.", "BUNDLE_TOO_LARGE")
        record = _validate_record(bundle["record"])
        card = research_recipe.validate_method_card(bundle["method_card"])
        payload = record["payload"]
        _require(card["scope_match"] == {k: payload["source_scope"][k] for k in ("domain", "contract")}
                 and card["method_refs"] == [{"method_id": payload["method_id"], "evaluation_ref": payload["evaluation_ref"]}], "Method card must match the saved method and scope.")
        limits = bundle["limitations"]
        _require(type(limits) is list and 1 <= len(limits) <= 8 and all(type(v) is str and 0 < len(v.strip()) <= 4000 and "\x00" not in v for v in limits), "One to eight limitations required.")
        return copy.deepcopy(bundle)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, UnicodeError, OverflowError, RecursionError):
        raise ResearchError("INVALID_CPU_EXPERIENCE", "Malformed CPU experience bundle.") from None


def parse_bundle(raw):
    return validate_bundle(research_recipe.parse_json(raw, maximum=MAX_BUNDLE_BYTES, code="INVALID_CPU_EXPERIENCE"))


def summary(bundle):
    bundle = validate_bundle(bundle)
    record = bundle["record"]
    p = record["provenance"]
    origin = p["origin"]
    # The full scope (including any missing-positive ID arrays) stays in the
    # bundle. The advisory projection keeps scalar conditions and asset hashes.
    compact_scope = {k: copy.deepcopy(v) for k, v in record["payload"]["source_scope"].items()
                     if v is None or type(v) in (str, int, float, bool) or k == "input_identities"}
    origin_keys = ("project_id", "run_id", "state_version", "snapshot_ref", "source_snapshot_sha256",
                   "source_file_sha256", "registered_project_code_identity", "producer_code_identity",
                   "capture_runtime_code_identity", "capture_implementation_sha256")
    saved = p["artifact"]["tool_result"]["result"]
    saved_counts = ({"rankings": len(saved["rankings"]), "metric_rows": len(saved["per_query_metrics"]),
                     "adverse_queries": len(saved["adverse_queries"]),
                     "queries_by_split": {k: len(v) for k, v in p["source"]["spec"]["query_splits"].items()}}
                    if record["payload"]["method_id"] != scheduling_adapter.TOOL_ID
                    else {"cases": len(saved["cases"]), "jobs": sum(len(case["jobs"]) for case in saved["cases"]),
                          "runs": sum(len(case["runs"]) for case in saved["cases"]),
                          "adverse_cases": len(saved["paired_summary"]["adverse_cases"])})
    value = {"case_id": bundle["id"], "case_version": bundle["version"], "entry_id": record["id"],
            "method_card": bundle["method_card"], "origin_evidence": {**{k: origin[k] for k in origin_keys},
                "action_id": p["action_id"], "result_sha256": p["artifact"]["sha256"], "binding_scope": record["scope"]},
            "source_scope": compact_scope, "observation": {"kind": "saved_cpu_fixed_pair",
                "method_id": record["payload"]["method_id"], "evaluation_ref": record["payload"]["evaluation_ref"],
                "comparison": copy.deepcopy(p["source"]["spec"]["comparison"]),
                "paired_summary": record["payload"]["paired_summary"], "saved_counts": saved_counts,
                "verification": record["payload"]["verification"]},
            "limitations": [*record["payload"]["origin_limitations"], *bundle["limitations"], NOTICE,
                "The advisory scope omits arrays; the complete scope remains in the bundle."],
            "transfer_scope": "analogy_not_current_evidence", "scientific_validation": False}
    _require(len(canonical(value).encode("utf-8")) <= 64 * 1024,
             "CPU advisory summary exceeds 64 KiB.", "SUMMARY_TOO_LARGE")
    return value


class CPUExperienceMemory(ResearchMemory):
    def import_project(self, workspace, action_id):
        return self._import_derived(derive_cpu_observation(workspace, action_id),
            verification="binding")

    def export_case(self, scope, entry_id, *, case_id, version, method_card, limitations):
        validate_scope(scope)
        with self._connect() as con:
            row = con.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone() if con is not None else None
            _require(row is not None, "No source memory entry matches this identity.", "NOT_FOUND")
            record = self._verify(con, row)
            _require(record["scope"] == scope, "Export requires the exact source scope.", "INVALID_SCOPE")
            _require(row["status"] == "active", "Retired evidence cannot be exported.", "EXPERIENCE_RETIRED")
            return validate_bundle({"schema_version": SCHEMA, "id": case_id, "version": version, "record": record,
                "method_card": method_card, "limitations": limitations, "source_inclusion_status": "active_at_export", "scientific_validation": False})
