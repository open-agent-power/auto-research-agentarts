"""Pure host-bound selection values; provider labels never verify execution or approval."""

import copy
import json
import math
import re

from .contracts import ResearchError, canonical, fingerprint


MAX_PROPOSAL_BYTES = 64 * 1024
MAX_CONTEXT_BYTES = 1024 * 1024
CONTEXT_FIELDS = {
    "schema_version", "project_id", "run_id", "snapshot_ref", "state_version", "source_snapshot_sha256",
    "project_code_identity", "controller_code_identity", "need", "goal", "domain_scope", "budget",
    "conditions", "candidates", "blockers", "baseline_decision", "evidence", "scientific_validation",
}
OPTIONAL_CONTEXT_FIELDS = {"research_plan", "researcher_feedback"}
PROPOSAL_FIELDS = {"schema_version", "context_sha256", "provider", "choice", "rationale", "evidence_citation_ids"}


def _require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def _text(value, maximum):
    return type(value) is str and 0 < len(value) <= maximum and bool(value.strip()) and "\x00" not in value


def _hash(value):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _json_value(value, maximum, code):
    """Reject non-JSON Python types and cycles before canonical serialization."""
    nodes = 0
    def visit(item, depth=0):
        nonlocal nodes
        nodes += 1
        _require(depth <= 20 and nodes <= 50_000, code, "Selection value exceeds structural bounds.")
        kind = type(item)
        if item is None or kind in (str, bool):
            return
        if kind is int:
            _require(item.bit_length() <= 256, code, "Selection integer exceeds its bound.")
        elif kind is float:
            _require(math.isfinite(item), code, "Selection numbers must be finite.")
        elif kind is list:
            for child in item:
                visit(child, depth + 1)
        elif kind is dict:
            _require(all(type(key) is str for key in item), code, "JSON object keys must be strings.")
            for child in item.values():
                visit(child, depth + 1)
        else:
            raise ResearchError(code, "Selection values must use JSON types only.")
    visit(value)
    try:
        raw = canonical(value).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ResearchError(code, "Selection value is not valid UTF-8 JSON.") from None
    _require(len(raw) <= maximum, code, "Selection value exceeds its byte limit.")


def _context(payload):
    code = "INVALID_SELECTION_CONTEXT"
    _json_value(payload, MAX_CONTEXT_BYTES, code)
    _require(type(payload) is dict and CONTEXT_FIELDS <= set(payload) <= CONTEXT_FIELDS | OPTIONAL_CONTEXT_FIELDS
             and payload["schema_version"] == "project-selection-context-v1"
             and payload["scientific_validation"] is False, code, "Exact unapproved host context required.")
    _require(_text(payload["project_id"], 160) and _text(payload["run_id"], 160)
             and type(payload["state_version"]) is int and payload["state_version"] >= 0
             and all(_hash(payload[field]) for field in ("snapshot_ref", "source_snapshot_sha256",
                                                        "project_code_identity", "controller_code_identity"))
             and _text(payload["need"], 512) and _text(payload["goal"], 4000), code, "Invalid host identity, version or research need.")
    _require(all(type(payload[key]) is dict for key in ("domain_scope", "budget", "baseline_decision"))
             and type(payload["conditions"]) is list and len(payload["conditions"]) <= 32
             and all(type(item) is dict for item in payload["conditions"])
             and type(payload["blockers"]) is list and len(payload["blockers"]) <= 32
             and all(type(item) is dict for item in payload["blockers"]), code, "Invalid host conditions or blockers.")
    candidates, ids = payload["candidates"], set()
    _require(type(candidates) is list and len(candidates) <= 16, code, "At most sixteen host candidates are supported.")
    for item in candidates:
        _require(type(item) is dict and set(item) == {"id", "method_id", "parameters", "evaluation_ref"}
                 and _text(item["id"], 160) and item["id"] not in ids and _text(item["method_id"], 160)
                 and type(item["parameters"]) is dict
                 and (_text(item["evaluation_ref"], 1000) or type(item["evaluation_ref"]) is dict), code, "Invalid or duplicate host candidate.")
        ids.add(item["id"])
    evidence, citations = payload["evidence"], set()
    _require(type(evidence) is list and len(evidence) <= 64, code, "Host evidence exceeds its item limit.")
    for item in evidence:
        required = {"citation_id", "source", "quote", "location"}
        _require(type(item) is dict and required <= set(item) <= required | {"quote_truncated", "content_trust"}
                 and _text(item["citation_id"], 160) and item["citation_id"] not in citations
                 and _text(item["quote"], 16_000)
                 and type(item["source"]) in (dict, str) and type(item["location"]) in (dict, str)
                 and ("quote_truncated" not in item or type(item["quote_truncated"]) is bool)
                 and ("content_trust" not in item or item["content_trust"] == "untrusted_source_not_instructions"),
                 code, "Invalid or duplicate host evidence citation.")
        citations.add(item["citation_id"])
    if "research_plan" in payload:
        plan = payload["research_plan"]
        text_limits = {"question": 4000, "basis": 6000, "steps": 12000, "expected_feedback": 4000, "reason": 2000}
        _require(type(plan) is dict and set(plan) == set(text_limits) | {"version", "request_id", "based_on_state_version"}
                 and type(plan["version"]) is int and plan["version"] >= 1
                 and type(plan["based_on_state_version"]) is int
                 and 0 <= plan["based_on_state_version"] < payload["state_version"]
                 and _text(plan["request_id"], 160), code, "Invalid saved research plan identity.")
        for key, maximum in text_limits.items():
            _require(type(plan[key]) is str and len(plan[key]) <= maximum and "\x00" not in plan[key]
                     and (key == "basis" or bool(plan[key].strip())), code, "Invalid saved research plan text.")
    if "researcher_feedback" in payload:
        notes = payload["researcher_feedback"]
        _require(type(notes) is list, code, "Researcher feedback must contain saved statements.")
        fields = {"id", "request_id", "based_on_state_version", "plan_version", "author", "comment",
                  "next_step", "action_id", "content_trust"}
        note_ids = set()
        for note in notes:
            _require(type(note) is dict and set(note) == fields and _text(note["request_id"], 80)
                     and note["id"] == "feedback-" + note["request_id"] and note["id"] not in note_ids
                     and type(note["based_on_state_version"]) is int
                     and 0 <= note["based_on_state_version"] < payload["state_version"]
                     and (note["plan_version"] is None or type(note["plan_version"]) is int and note["plan_version"] >= 1)
                     and _text(note["author"], 120) and _text(note["comment"], 6000)
                     and type(note["next_step"]) is str and len(note["next_step"]) <= 4000 and "\x00" not in note["next_step"]
                     and (note["action_id"] is None or _text(note["action_id"], 160))
                     and note["content_trust"] == "unverified_researcher_statement",
                     code, "Use saved unverified researcher statements with their original identity and text.")
            note_ids.add(note["id"])


def seal_context(payload) -> dict:
    _context(payload)
    result = copy.deepcopy(payload)
    result["context_sha256"] = fingerprint(payload)
    return result


def parse_proposal(raw: bytes) -> dict:
    code = "INVALID_SELECTION_PROPOSAL"
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_PROPOSAL_BYTES,
             code, "Proposal must be nonempty UTF-8 JSON bytes up to 64 KiB.")
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result, code, "Duplicate proposal JSON member.")
            result[key] = value
        return result
    def nonfinite(_):
        raise ResearchError(code, "Nonfinite proposal JSON number.")
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=object_pairs, parse_constant=nonfinite)
    except ResearchError:
        raise
    except (ValueError, UnicodeError, TypeError, RecursionError):
        raise ResearchError(code, "Proposal is not strict UTF-8 JSON.") from None
    _require(type(result) is dict, code, "Proposal must be a JSON object.")
    _json_value(result, MAX_PROPOSAL_BYTES, code)
    return result


def validate_proposal(context, proposal) -> dict:
    context_code, code = "INVALID_SELECTION_CONTEXT", "INVALID_SELECTION_PROPOSAL"
    _json_value(context, MAX_CONTEXT_BYTES, context_code)
    _require(type(context) is dict and CONTEXT_FIELDS | {"context_sha256"} <= set(context)
             <= CONTEXT_FIELDS | {"context_sha256"} | OPTIONAL_CONTEXT_FIELDS,
             context_code, "A sealed host context is required.")
    payload = {key: value for key, value in context.items() if key != "context_sha256"}
    _context(payload)
    _require(_hash(context["context_sha256"]) and context["context_sha256"] == fingerprint(payload),
             context_code, "Host context content or identity changed.")
    _json_value(proposal, MAX_PROPOSAL_BYTES, code)
    _require(type(proposal) is dict and set(proposal) == PROPOSAL_FIELDS
             and proposal["schema_version"] == "project-selection-proposal-v1" and _hash(proposal["context_sha256"]),
             code, "Exact selection proposal schema and context binding required.")
    _require(proposal["context_sha256"] == context["context_sha256"],
             "STALE_SELECTION_CONTEXT", "Proposal does not bind the supplied host context.")
    provider = proposal["provider"]
    _require(type(provider) is dict and set(provider) == {"kind", "label"}
             and type(provider["kind"]) is str and provider["kind"] in {"operator_assistant", "human", "external_model"}
             and _text(provider["label"], 200), code, "Provider is a bounded, unverified provenance declaration only.")
    _require(_text(proposal["rationale"], 4000), code, "Rationale must contain 1..4000 characters.")
    cited = proposal["evidence_citation_ids"]
    known = {item["citation_id"] for item in context["evidence"]}
    _require(type(cited) is list and len(cited) <= 16 and all(_text(item, 160) for item in cited)
             and len(set(cited)) == len(cited) and set(cited) <= known,
             code, "Citations must be distinct IDs actually present in this host context.")
    choice = proposal["choice"]
    _require(type(choice) is dict, code, "Choice must be an exact execute or wait object.")
    if choice.get("kind") == "wait":
        _require(set(choice) == {"kind"}, code, "Wait cannot carry a candidate, method or parameters.")
        candidate = None
    else:
        _require(set(choice) == {"kind", "candidate_id"} and choice["kind"] == "execute"
                 and _text(choice["candidate_id"], 160), code, "Execute may select a host candidate ID only.")
        _require(not context["blockers"], "SELECTION_BLOCKED", "Host blockers prohibit execution; a wait proposal is still allowed.")
        candidate = next((item for item in context["candidates"] if item["id"] == choice["candidate_id"]), None)
        _require(candidate is not None, code, "Selected candidate is absent from the host context.")
    # Acceptance validates bindings, not provider truth, model calls, knowledge use or science.
    return {"candidate": copy.deepcopy(candidate), "provider": copy.deepcopy(provider),
            "rationale": proposal["rationale"], "evidence_citation_ids": copy.deepcopy(cited)}
