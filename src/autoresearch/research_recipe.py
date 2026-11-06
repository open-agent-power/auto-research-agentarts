"""Read method knowledge and compile host-bound recipe proposals without execution."""

import copy
import json

from .contracts import ResearchError, canonical
from .project_selection import validate_proposal


MAX_RECIPE_BYTES = 64 * 1024
RECIPE_FIELDS = {"schema_version", "id", "version", "question", "scope_match", "need",
                 "ordered_methods", "on_no_match"}
METHOD_CARD_FIELDS = {"schema_version", "id", "version", "question", "rationale", "scope_match",
                      "method_refs", "applicability", "evaluation", "feedback_branches", "sources"}
MAX_METHOD_CARD_BYTES = 64 * 1024


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


def _method_pairs(methods, code):
    seen = set()
    _require(type(methods) is list and 1 <= len(methods) <= 16, code,
             "Provide one to sixteen method/evaluation pairs.")
    for method in methods:
        _require(type(method) is dict and set(method) == {"method_id", "evaluation_ref"}
                 and _text(method["method_id"], 160) and _text(method["evaluation_ref"], 1000), code,
                 "Each method requires only method_id and a string evaluation_ref.")
        pair = (method["method_id"], method["evaluation_ref"])
        _require(pair not in seen, code, "Duplicate method/evaluation pair.")
        seen.add(pair)


def _text_list(value, code, *, minimum=0):
    _require(type(value) is list and minimum <= len(value) <= 16
             and all(_text(item, 4000) for item in value), code,
             "Knowledge lists require bounded, nonempty text entries.")


def validate_method_card(card):
    """Validate knowledge, not executable predicates, commands or approval."""
    code = "INVALID_RESEARCH_METHOD_CARD"
    _require(type(card) is dict and set(card) == METHOD_CARD_FIELDS, code,
             "Method card requires exactly the research-method-card-v1 fields.")
    _require(card["schema_version"] == "research-method-card-v1" and _text(card["id"], 160)
             and type(card["version"]) is int and 1 <= card["version"] <= 2**31 - 1, code,
             "Invalid method card schema, identity or version.")
    for key in ("question", "rationale", "evaluation"):
        _require(_text(card[key], 4000), code, "Method explanations must be bounded nonempty text.")
    scope = card["scope_match"]
    _require(type(scope) is dict and set(scope) == {"domain", "contract"}
             and all(_text(scope[key], 160) for key in scope), code,
             "Scope must contain only nonempty domain and contract strings.")
    _method_pairs(card["method_refs"], code)
    applicability = card["applicability"]
    _require(type(applicability) is dict
             and set(applicability) == {"requires", "not_applicable", "uncertain"}, code,
             "Applicability requires requires/not_applicable/uncertain text lists.")
    for key, statements in applicability.items():
        _text_list(statements, code, minimum=1 if key == "requires" else 0)
    branches, branch_ids = card["feedback_branches"], set()
    _require(type(branches) is list and 1 <= len(branches) <= 16, code,
             "Provide one to sixteen explanatory feedback branches.")
    for branch in branches:
        _require(type(branch) is dict and set(branch) == {"id", "observed", "suggested_next", "evidence_required"}
                 and _text(branch["id"], 160) and branch["id"] not in branch_ids
                 and all(_text(branch[key], 4000) for key in ("observed", "suggested_next")), code,
                 "Feedback branches require distinct identities and text, not executable conditions.")
        _text_list(branch["evidence_required"], code, minimum=1)
        branch_ids.add(branch["id"])
    sources, source_ids = card["sources"], set()
    _require(type(sources) is list and 1 <= len(sources) <= 16, code,
             "Provide one to sixteen source references; references are not fetched.")
    for source in sources:
        _require(type(source) is dict and set(source) == {"id", "url", "locator", "note"}
                 and _text(source["id"], 160) and source["id"] not in source_ids
                 and all(_text(source[key], 4000) for key in ("url", "locator", "note")), code,
                 "Source references require distinct identities, URL, locator and note text.")
        source_ids.add(source["id"])
    try:
        raw = canonical(card).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ResearchError(code, "Method card must contain valid UTF-8 JSON values.") from None
    _require(len(raw) <= MAX_METHOD_CARD_BYTES, code, "Method card exceeds 64 KiB.")
    return copy.deepcopy(card)


def parse_method_card(raw):
    """Read a strict, bounded UTF-8 method card; never interpret its prose."""
    return validate_method_card(parse_json(raw, maximum=MAX_METHOD_CARD_BYTES,
                                           code="INVALID_RESEARCH_METHOD_CARD"))


def _wait_proposal(context):
    proposal = {"schema_version": "project-selection-proposal-v1",
                "context_sha256": context.get("context_sha256") if type(context) is dict else None,
                "provider": {"kind": "operator_assistant", "label": "deterministic recipe policy; no model"},
                "choice": {"kind": "wait"}, "rationale": "Validate the sealed host context before selecting.",
                "evidence_citation_ids": []}
    validate_proposal(context, proposal)
    return proposal


def match_method_card(card, context):
    """Associate knowledge with exact host candidates and report unresolved conditions.

    Free-text requirements/branches are unverified knowledge, not predicates.
    Candidate eligibility comes exclusively from the sealed host context.
    """
    card = validate_method_card(card)
    _wait_proposal(context)
    scope_matches = all(context["domain_scope"].get(key) == value
                        for key, value in card["scope_match"].items())
    pairs = {(item["method_id"], item["evaluation_ref"]) for item in card["method_refs"]}
    matches = [item for item in context["candidates"]
               if type(item["evaluation_ref"]) is str
               and (item["method_id"], item["evaluation_ref"]) in pairs]
    status = ("blocked" if context["blockers"] else "scope_mismatch" if not scope_matches
              else "applicable" if matches else "no_matching_candidate")
    reason = {"blocked": "宿主存在阻断，方法卡不能绕过；请先核对原执行或资源状态。",
              "scope_mismatch": "当前领域或输入契约与方法卡不符，不能关联执行候选。",
              "applicable": "范围匹配，宿主提供了方法和评价引用均相同的候选；仅表示工程资格。",
              "no_matching_candidate": "宿主未提供方法与评价引用均匹配的候选，不能从方法卡创建候选。"}[status]
    method_matches, missing, unreported, host_reasons = [], [], [], []
    for method in card["method_refs"]:
        candidates = [item for item in matches if item["method_id"] == method["method_id"]
                      and item["evaluation_ref"] == method["evaluation_ref"]]
        conditions = [item for item in context["conditions"]
                      if item.get("method_id") == method["method_id"]
                      and item.get("evaluation_ref") == method["evaluation_ref"]]
        gaps = []
        for condition in conditions:
            reported = condition.get("missing_information", [])
            if type(reported) is list:
                gaps.extend(item for item in reported if _text(item, 4000))
            reported_reasons = condition.get("reasons", [])
            if type(reported_reasons) is list:
                host_reasons.extend("宿主 " + method["method_id"] + " 条件记录：" + item
                                    for item in reported_reasons if _text(item, 4000))
        if not candidates:
            gaps.append("需要宿主提供对应的合法候选：" + method["method_id"] + " / " + method["evaluation_ref"])
        if not conditions:
            unreported.append(copy.deepcopy(method))
        missing.extend(gaps)
        method_matches.append({**method,
                               "matching_candidate_ids": [item["id"] for item in candidates] if status == "applicable" else [],
                               "reason": reason if status != "applicable" else
                                         "精确匹配宿主候选。" if candidates else "没有对应宿主候选；保留条件缺口。",
                               "host_conditions": copy.deepcopy(conditions),
                               "missing_information": list(dict.fromkeys(gaps))})
    eligible = matches if status == "applicable" else []
    return {"schema_version": "research-method-card-match-v1", "card_id": card["id"],
            "card_version": card["version"], "card": card, "context_sha256": context["context_sha256"],
            "question": context.get("research_plan", {}).get("question", context["goal"]), "need": context["need"],
            "status": status, "reasons": [reason, card["rationale"], *dict.fromkeys(host_reasons)],
            "matching_candidate_ids": [item["id"] for item in eligible],
            "applicable_methods": [{"candidate_id": item["id"], "method_id": item["method_id"],
                                    "evaluation_ref": item["evaluation_ref"]} for item in eligible],
            "method_matches": method_matches, "missing_information": list(dict.fromkeys(missing)),
            "host_blockers": copy.deepcopy(context["blockers"]),
            "unreported_condition_refs": unreported, "unverified_applicability": copy.deepcopy(card["applicability"]),
            "eligibility_basis": "sealed_host_candidates_only_not_scientific_approval",
            "execution_status": "not_executed", "scientific_validation": False}


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
    _method_pairs(recipe["ordered_methods"], code)
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
    proposal = _wait_proposal(context)
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
