"""Compile explicit method priorities into a host-bound proposal without execution."""

import copy
import json

from .contracts import ResearchError, canonical
from .project_selection import validate_proposal


MAX_RECIPE_BYTES = 64 * 1024
RECIPE_FIELDS = {"schema_version", "id", "version", "question", "scope_match", "need",
                 "ordered_methods", "on_no_match"}


def _require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def _text(value, maximum):
    return type(value) is str and 0 < len(value) <= maximum and bool(value.strip()) and "\x00" not in value


def parse_json(raw, *, maximum, code):
    """Read a bounded, unambiguous UTF-8 JSON object; never interpret its content."""
    _require(type(raw) is bytes and 0 < len(raw) <= maximum, code,
             "Input must be nonempty JSON bytes within its size limit.")

    def unique(pairs):
        value = {}
        for key, item in pairs:
            _require(key not in value, code, "Duplicate JSON member.")
            value[key] = item
        return value

    def nonfinite(_):
        raise ResearchError(code, "Nonfinite JSON number.")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=nonfinite)
    except ResearchError:
        raise
    except (ValueError, UnicodeError, TypeError, RecursionError):
        raise ResearchError(code, "Input must be strict UTF-8 JSON.") from None
    _require(type(value) is dict, code, "Input must be a JSON object.")
    return value


def validate_recipe(recipe):
    """Validate the closed v1 recipe format; no code, parameters or overrides."""
    code = "INVALID_RESEARCH_RECIPE"
    _require(type(recipe) is dict and set(recipe) == RECIPE_FIELDS, code,
             "Recipe requires exactly the research-recipe-v1 fields.")
    _require(recipe["schema_version"] == "research-recipe-v1" and recipe["on_no_match"] == "wait", code,
             "Only research-recipe-v1 and on_no_match=wait are supported.")
    _require(_text(recipe["id"], 160) and type(recipe["version"]) is int
             and 1 <= recipe["version"] <= 2**31 - 1 and _text(recipe["question"], 4000)
             and _text(recipe["need"], 512), code, "Invalid recipe identity, question, version or need.")
    scope = recipe["scope_match"]
    _require(type(scope) is dict and set(scope) == {"domain", "contract"}
             and all(_text(scope[key], 160) for key in ("domain", "contract")), code,
             "Scope must contain only nonempty domain and contract strings.")
    methods, seen = recipe["ordered_methods"], set()
    _require(type(methods) is list and 1 <= len(methods) <= 16, code,
             "Recipe must contain one to sixteen ordered method/evaluation pairs.")
    for method in methods:
        _require(type(method) is dict and set(method) == {"method_id", "evaluation_ref"}
                 and _text(method["method_id"], 160) and _text(method["evaluation_ref"], 1000), code,
                 "Each method requires only method_id and a string evaluation_ref.")
        pair = (method["method_id"], method["evaluation_ref"])
        _require(pair not in seen, code, "Duplicate method/evaluation pair.")
        seen.add(pair)
    try:
        raw = canonical(recipe).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ResearchError(code, "Recipe must contain valid UTF-8 JSON values.") from None
    _require(len(raw) <= MAX_RECIPE_BYTES, code, "Recipe exceeds 64 KiB.")
    return copy.deepcopy(recipe)


def compile_recipe(recipe, context):
    """Return a separate decision record containing a validated proposal.

    Scope matching checks engineering identity only. The host remains responsible
    for eligibility, source/parameter identity, budget, persistence and execution.
    """
    recipe = validate_recipe(recipe)
    # A wait proposal invokes the original validator before inspecting any host
    # fields, including when this recipe would otherwise decline the context.
    proposal = {"schema_version": "project-selection-proposal-v1",
                "context_sha256": context.get("context_sha256") if type(context) is dict else None,
                "provider": {"kind": "operator_assistant", "label": "deterministic recipe policy; no model"},
                "choice": {"kind": "wait"}, "rationale": "Validate the sealed host context before selecting.",
                "evidence_citation_ids": []}
    validate_proposal(context, proposal)
    scope_matches = all(context["domain_scope"].get(key) == value
                        for key, value in recipe["scope_match"].items())
    need_matches = context["need"] == recipe["need"]
    reason = ("HOST_BLOCKERS" if context["blockers"] else "SCOPE_MISMATCH" if not scope_matches
              else "NEED_MISMATCH" if not need_matches else "NO_MATCHING_HOST_CANDIDATE")
    selected = None
    method_decisions = []
    for method in recipe["ordered_methods"]:
        matches = [candidate for candidate in context["candidates"]
                   if candidate["method_id"] == method["method_id"]
                   and candidate["evaluation_ref"] == method["evaluation_ref"]]
        if context["blockers"] or not scope_matches or not need_matches:
            method_reason = reason
        elif selected is not None:
            method_reason = "LOWER_RECIPE_PRIORITY"
        elif not matches:
            method_reason = "NO_MATCHING_HOST_CANDIDATE"
        else:
            selected = matches[0]
            reason = method_reason = "FIRST_MATCHING_HOST_CANDIDATE"
        method_decisions.append({**method, "outcome": "selected" if method_reason == "FIRST_MATCHING_HOST_CANDIDATE" else "skipped",
                                 "reason": method_reason, "matching_candidate_ids": [item["id"] for item in matches]})
    if selected is not None:
        proposal["choice"] = {"kind": "execute", "candidate_id": selected["id"]}
    proposal["rationale"] = ("Deterministic recipe priority: " + reason
                             + ". Engineering selection only; scientific conditions remain unapproved.")
    validate_proposal(context, proposal)
    candidate_decisions = []
    for candidate in context["candidates"]:
        chosen = selected is not None and candidate["id"] == selected["id"]
        candidate_reason = ("FIRST_MATCHING_HOST_CANDIDATE" if chosen else reason if selected is None
                            else "NOT_FIRST_MATCHING_CANDIDATE_IN_RECIPE_AND_HOST_ORDER")
        candidate_decisions.append({"candidate_id": candidate["id"], "outcome": "selected" if chosen else "skipped",
                                    "reason": candidate_reason})
    return {"schema_version": "research-recipe-decision-v1", "recipe_id": recipe["id"],
            "recipe_version": recipe["version"], "recipe": recipe, "context_sha256": context["context_sha256"],
            "checks": {"scope_match": scope_matches, "need_match": need_matches,
                       "host_blockers": copy.deepcopy(context["blockers"])},
            "reason": reason, "selected_candidate_id": selected["id"] if selected else None,
            "method_decisions": method_decisions, "candidate_decisions": candidate_decisions,
            "proposal": proposal, "scientific_validation": False}
