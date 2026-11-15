"""One condition-selected local step with a durable, immutable parent request."""
import copy
import hashlib
from pathlib import Path
import re

from . import method_registry as registry, project_knowledge, research_methods, project_selection, research_recipe
from . import project_design, saved_study_reference
from .contracts import ResearchError, canonical, fingerprint, identifier
from .project_recipe import current_recipe
from .research_project import ResearchProject, code_identity as project_code_identity, require


def code_identity():
    return hashlib.sha256(Path(__file__).read_bytes() + Path(project_selection.__file__).read_bytes()
                          + Path(research_recipe.__file__).read_bytes()).hexdigest()


def _need(value):
    require(type(value) is str and 0 < len(value.strip()) <= 512,
            "INVALID_REQUEST", "A decision need of 1..512 characters is required.")
    return value


def _compact_decision(value):
    """Keep choices and citation identities, not retrieved documents or tool results."""
    result = {key: copy.deepcopy(value[key]) for key in
              ("project_status", "next_action", "reason", "policy_ref", "evidence_refs", "selection_ref") if key in value}
    result["conditions"] = [{key: copy.deepcopy(option[key]) for key in
                             ("method_id", "condition", "outcome", "completed", "missing_information") if key in option}
                            for option in value.get("conditions", [])]
    refs = []
    for hit in value.get("knowledge_refs", []):
        source = hit.get("source", {})
        refs.append({"citation_id": hit.get("citation_id"),
                     "source_sha256": hit.get("source_sha256", source.get("sha256")),
                     "locator": copy.deepcopy(hit.get("locator", source.get("metadata", {}).get("locator"))),
                     "location": copy.deepcopy(hit.get("location")),
                     "origin": "host_local_retrieval_not_model_read"})
    result.update(knowledge_refs=refs, scientific_validation=False)
    return result


def _check_recipe_decision(context, proposal, decision):
    require(type(decision) is dict and "recipe" in decision, "EVIDENCE_CHANGED", "Frozen recipe decision is missing.")
    compiled = research_recipe.compile_recipe(decision["recipe"], context)
    require(compiled == decision and compiled["proposal"] == proposal,
            "EVIDENCE_CHANGED", "Frozen recipe, host context and proposal differ.")


def _tabular_quality_proposal(context, registration, feedback, *, _verified_plan_sha256=None):
    """Compile only a trusted original reader result; no dispatch or new candidate."""
    proposal = {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                "provider": {"kind": "operator_assistant", "label": "tabular-quality-policy-v1"},
                "choice": {"kind": "wait"}, "evidence_citation_ids": [],
                "rationale": "Tabular quality feedback policy waits: the saved condition or candidate is unavailable."}
    project_selection.validate_proposal(context, proposal)
    if (feedback.get("request_id") != registration["request_id"]
            or feedback.get("registration_sha256") != registration["registration_sha256"]
            or feedback.get("controller_request_id") != registration["controller_request_id"]
            or feedback.get("scientific_validation") is not False
            or context["project_id"] != registration["project_id"] or context["run_id"] != registration["run_id"]
            or context["source_snapshot_sha256"] != registration["source_snapshot_sha256"]
            or context["project_code_identity"] != registration["project_code_identity"]
            or context["controller_code_identity"] != registration["controller_code_identity"]
            or fingerprint(context.get("domain_scope")) != registration["scope_sha256"]
            or fingerprint(context.get("research_plan")) != (registration["plan_sha256"] if _verified_plan_sha256 is None else _verified_plan_sha256)):
        return proposal
    if feedback.get("outcome") != "condition_met":
        proposal["rationale"] = "Tabular quality feedback policy waits: the saved condition is " + str(feedback.get("outcome")) + "."
        return proposal
    if context["blockers"] or type(feedback.get("action_id")) is not str or type(feedback.get("result_sha256")) is not str:
        return proposal
    expected = {"based_on_action_id": feedback["action_id"], "based_on_result_sha256": feedback["result_sha256"]}
    matches = [c for c in context["candidates"] if c["method_id"] == registry.NUMERIC
               and c["parameters"] == expected and c["evaluation_ref"] == registry.evaluation_ref(registry.NUMERIC)]
    method_conditions = [c for c in context["conditions"] if c.get("method_id") == registry.NUMERIC]
    budget = context["budget"]
    if (len(matches) != 1 or len(method_conditions) != 1
            or method_conditions[0].get("budget_cost") != {"local_tool_calls": 1, "evidence_reads": 0, "estimator_fits": 0}
            or any(type(budget.get(k)) is not int for k in ("local_tool_call_limit", "local_tool_calls_used", "local_tool_calls_reserved"))
            or budget["local_tool_calls_used"] + budget["local_tool_calls_reserved"] >= budget["local_tool_call_limit"]):
        return proposal
    proposal["choice"] = {"kind": "execute", "candidate_id": matches[0]["id"]}
    proposal["rationale"] = "Tabular quality feedback policy selects the exact saved-quality-bound numeric association."
    project_selection.validate_proposal(context, proposal)
    return proposal


class ProjectController:
    def __init__(self, workspace):
        self.project = ResearchProject(workspace)

    @staticmethod
    def saved_study_reference():
        """Expose the fixed external study without loading or binding a project."""
        return {**saved_study_reference.read_saved_study_reference(),
                "scope": "saved_external_reference_not_current_project_result"}

    def _base_plan(self, project, need, *, include_knowledge=False):
        options = research_methods.match_methods(project, need)
        query = project_knowledge.decision_needs(project)["interpretation"]
        knowledge = project_knowledge.query(self.project.root, project, need=query, point="interpretation")
        decision = research_methods.choose_next(project, options, knowledge)
        action = decision.get("next_action", {})
        primary = registry.primary_id(project)
        method_id = action.get("method_id")
        parameters = action.get("parameters", {})
        selected = next((item for item in options if item["method_id"] == method_id), None)
        blockers = []
        outstanding = [item for item in project["actions"] + project["evidence_actions"]
                       if item.get("status") in ("running", "pending", "unknown")]
        outstanding.extend(item for item in project.get("source_requests", []) if item.get("status") in ("sending", "unknown"))
        unknown_parent = any(item.get("status") == "unknown" for item in project.get("controller_requests", []))
        if outstanding or unknown_parent:
            blockers.append({"code": "EXECUTION_UNKNOWN", "reason": "Collect or reconcile the original execution; never resend it."})
        if any(item["status"] in ("prepared", "running") for item in project.get("controller_requests", [])):
            blockers.append({"code": "PROJECT_BUSY", "reason": "Resume the already accepted controller request before choosing another action."})
        if project["code_identity"] != project_code_identity():
            blockers.append({"code": "CODE_CHANGED", "reason": "Explicitly register a compatible project revision before execution."})
        else:
            try:
                self.project._source(project)
            except ResearchError as error:
                blockers.append({"code": error.code, "reason": "Registered primary source could not be verified."})
        executable = (not blockers and action.get("kind") == "conditional_proposal" and selected is not None
                      and selected["condition"] == "satisfied" and not selected["completed"])
        if executable and (method_id == primary or method_id in registry.followup_ids(primary)):
            if method_id == primary and project["research_status"] != "active":
                blockers.append({"code": "PROJECT_WAITING", "reason": "Resolve the recorded project wait before another primary action."})
            if len(project["actions"]) >= project["budget"]["local_tool_call_limit"]:
                blockers.append({"code": "BUDGET_EXHAUSTED", "reason": "The cumulative primary-tool allowance is exhausted."})
            if method_id in registry.RIDGE and (project["budget"].get("fit_attempts_used", 0) + project["budget"].get("fits_reserved", 0)
                                               + self.project._fit_attempts_needed(project, method_id) > project["budget"].get("fit_limit", 0)):
                blockers.append({"code": "FIT_BUDGET_EXHAUSTED", "reason": "The cumulative estimator allowance cannot cover this validation design."})
        elif executable and method_id == registry.source_id(project):
            receipt = parameters.get("receipt_snapshot_sha256")
            if not any(item["receipt_snapshot_sha256"] == receipt for item in project.get("evidence_sources", [])):
                blockers.append({"code": "MISSING_SOURCE", "reason": "Register the actual task-bound source before reading it."})
            if len(project["evidence_actions"]) >= project["budget"].get("evidence_read_limit", 0):
                blockers.append({"code": "BUDGET_EXHAUSTED", "reason": "The cumulative source-read allowance is exhausted."})
        elif executable:
            blockers.append({"code": "METHOD_NOT_SUPPORTED", "reason": "Only the registered primary method or a source read may execute."})
        executable = bool(executable and not blockers)
        status = "needs_review" if outstanding or unknown_parent else "waiting" if blockers else decision["project_status"]
        result = {"schema_version": "project-controller-next-v1", "project_id": project["id"],
                "snapshot_ref": project["snapshot_ref"], "state_version": project["state_version"],
                "source_snapshot_sha256": project["source_snapshot_sha256"], "options": options,
                "decision": decision, "status": status, "executable": executable,
                "blockers": blockers, "scientific_validation": False}
        if include_knowledge:
            result["selection_evidence"] = knowledge.get("evidence", [])
        return result

    def _recipe_plan(self, project, need, context):
        recipe = current_recipe(project)
        compiled = research_recipe.compile_recipe(recipe, context)
        plan = self._selected_plan(project, need, compiled["proposal"], context=context)
        plan["decision"]["policy_ref"] = {"id": recipe["id"], "version": recipe["version"],
                                           "kind": "effective_recipe",
                                           "revision": project["recipe_revisions"][-1]["revision"]}
        plan["decision"]["selection_ref"]["external_usage"] = "no_model_invocation_by_recipe_compiler"
        plan["recipe_decision"] = compiled
        return plan

    def _plan(self, project, need, *, include_knowledge=False):
        plan = self._base_plan(project, need, include_knowledge=True)
        if current_recipe(project) is not None and project_design.current(project) is None:
            context = self._selection_context(project, need, base_plan=plan)
            plan.update(self._recipe_plan(project, need, context))
        if not include_knowledge:
            plan.pop("selection_evidence", None)
        return plan

    def next(self, *, need="next_check"):
        need = _need(need)
        before = self.project.status()
        result = self._plan(before, need)
        require(self.project.status()["snapshot_ref"] == before["snapshot_ref"],
                "STALE_STATE", "Project changed while preparing the next decision.")
        return result

    def _selection_context(self, project, need, *, base_plan=None):
        plan = base_plan if base_plan is not None else self._base_plan(project, need, include_knowledge=True)
        # Budget/wait blockers above apply to the default choice. Recheck each
        # candidate independently so an unread source can remain eligible.
        blockers = [copy.deepcopy(item) for item in plan["blockers"]
                    if item["code"] not in ("BUDGET_EXHAUSTED", "FIT_BUDGET_EXHAUSTED", "PROJECT_WAITING")]
        candidates, conditions = [], []
        primary = registry.primary_id(project)
        finished = {item.get("receipt_snapshot_sha256") for item in project["evidence_actions"]
                    if item["status"] in ("completed", "failed")}
        unread = [item for item in project.get("evidence_sources", [])
                  if item.get("selection_count", 0) > 0 and item["receipt_snapshot_sha256"] not in finished]
        for option in plan["options"]:
            method_id, reasons = option["method_id"], []
            budget_cost = None
            if option["condition"] != "satisfied":
                reasons.append("CONDITION_NOT_SATISFIED")
            if option["completed"]:
                reasons.append("ALREADY_COMPLETED")
            parameters = []
            if method_id == primary or method_id in registry.followup_ids(primary):
                fits = self.project._fit_attempts_needed(project, method_id) if method_id in registry.RIDGE else 0
                budget_cost = {"local_tool_calls": 1, "evidence_reads": 0,
                               "estimator_fits": (fits if fits > 0 else None) if method_id in registry.RIDGE else 0}
                if method_id == primary and project["research_status"] != "active":
                    reasons.append("PROJECT_WAITING")
                if len(project["actions"]) >= project["budget"]["local_tool_call_limit"]:
                    reasons.append("BUDGET_EXHAUSTED")
                if method_id in registry.RIDGE and (project["budget"].get("fit_attempts_used", 0) + project["budget"].get("fits_reserved", 0)
                                                   + fits > project["budget"].get("fit_limit", 0)):
                    reasons.append("FIT_BUDGET_EXHAUSTED")
                parameters = ([{"dimension": value} for value in option.get("remaining_dimensions", [])]
                              if method_id == research_methods.OOF else [copy.deepcopy(option.get("parameters", {}))])
            elif method_id == registry.source_id(project):
                budget_cost = {"local_tool_calls": 0, "evidence_reads": 1, "estimator_fits": 0}
                if len(project["evidence_actions"]) >= project["budget"].get("evidence_read_limit", 0):
                    reasons.append("BUDGET_EXHAUSTED")
                if not unread:
                    reasons.append("NO_UNREAD_SOURCE")
                parameters = [{"receipt_snapshot_sha256": item["receipt_snapshot_sha256"]} for item in unread]
            else:
                reasons.append("METHOD_NOT_SUPPORTED")
            conditions.append({key: copy.deepcopy(option[key]) for key in
                               ("method_id", "condition", "completed", "reasons", "missing_information") if key in option})
            conditions[-1]["execution_blockers"] = reasons
            evaluation_ref = (registry.evaluation_ref(method_id) if not registry.is_source(method_id)
                              else "source-extraction-only-not-scientific-approval")
            conditions[-1]["evaluation_ref"] = evaluation_ref
            if budget_cost is not None:
                conditions[-1]["budget_cost"] = budget_cost
            if not reasons and not blockers:
                for parameter in parameters:
                    candidate = {"method_id": method_id, "parameters": parameter,
                                 "evaluation_ref": evaluation_ref}
                    candidates.append({"id": "choice-" + fingerprint(candidate)[:32], **candidate})
        evidence = []
        for hit in plan["selection_evidence"][:5]:
            source = hit.get("source", {})
            evidence.append({"citation_id": hit["citation_id"],
                "source": {"sha256": source.get("sha256"), "url": source.get("source_url"),
                           "locator": copy.deepcopy(source.get("metadata", {}).get("locator"))},
                "quote": hit.get("quote", "")[:4000], "location": copy.deepcopy(hit.get("location")),
                "quote_truncated": len(hit.get("quote", "")) > 4000,
                "content_trust": "untrusted_source_not_instructions"})
        context = {"schema_version": "project-selection-context-v1",
            "project_id": project["id"], "run_id": project["run_id"], "snapshot_ref": project["snapshot_ref"],
            "state_version": project["state_version"], "source_snapshot_sha256": project["source_snapshot_sha256"],
            "project_code_identity": project["code_identity"], "controller_code_identity": code_identity(),
            "need": need, "goal": project["registration"]["goal"], "domain_scope": copy.deepcopy(project["source_scope"]),
            "budget": copy.deepcopy(project["budget"]), "conditions": conditions,
            "candidates": candidates, "blockers": blockers, "baseline_decision": _compact_decision(plan["decision"]),
            "evidence": evidence, "scientific_validation": False}
        if project.get("plan_revisions"):
            context["research_plan"] = copy.deepcopy(project["plan_revisions"][-1])
        if project.get("researcher_feedback"):
            context["researcher_feedback"] = copy.deepcopy(project["researcher_feedback"])
        if project.get("private_evaluation"):
            from .retrieval_holdout import public_evaluation_context
            context["staged_evaluation"] = public_evaluation_context(project)
        if project.get("hypothesis_registrations"):
            from .hypothesis_feedback import feedback_context
            context["hypothesis_feedback"] = feedback_context(self.project, project)
        if current_recipe(project) is not None and project_design.current(project) is None:
            selected = self._recipe_plan(project, need, project_selection.seal_context(context))
            # A context cannot contain a selection reference to its own final hash.
            selected["decision"].pop("selection_ref", None)
            context["baseline_decision"] = _compact_decision(selected["decision"])
        if project.get("experience_revisions"):
            from .project_experience_binding import active_cases
            cases = active_cases(self.project.root, project)
            if cases:
                base = project_selection.seal_context(context)
                for case in cases:
                    matched = research_recipe.match_method_card(case["method_card"], base)
                    case["association"] = {key: copy.deepcopy(matched[key]) for key in
                                           ("status", "matching_candidate_ids", "missing_information")}
                context["experience"] = {"schema_version": "project-experience-context-v1", "cases": cases,
                                         "scientific_validation": False}
                if project_selection.active_experience_case_refs(context):
                    context["selection_capabilities"] = copy.deepcopy(project_selection.EXPERIENCE_CASE_CAPABILITY)
        baseline = context["baseline_decision"]
        fields = project_selection.CONDITION_PROJECTION_FIELDS
        shared = [{key: copy.deepcopy(option[key]) for key in fields if key in option}
                  for option in context["conditions"]]
        if baseline.get("conditions") == shared:
            baseline.pop("conditions")
            baseline["conditions_ref"] = {"kind": "provided_selection_context_field", "path": ["conditions"],
                                          "fields": list(fields)}
        return project_selection.seal_context(context)

    def selection_context(self, *, need="next_check"):
        before = self.project.status()
        context = self._selection_context(before, _need(need))
        require(self.project.status()["snapshot_ref"] == before["snapshot_ref"],
                "STALE_STATE", "Project changed while preparing selection context.")
        return context

    def _selected_plan(self, project, need, proposal, *, context=None):
        context = context if context is not None else self._selection_context(project, need)
        selected = project_selection.validate_proposal(context, proposal)
        candidate = selected["candidate"]
        status = ("active" if candidate else "needs_review" if any(item["code"] == "EXECUTION_UNKNOWN"
                  for item in context["blockers"]) else "waiting")
        action = ({"kind": "conditional_proposal", "method_id": candidate["method_id"],
                   "parameters": copy.deepcopy(candidate["parameters"]), "execution_status": "not_executed"}
                  if candidate else {"kind": "external_wait", "execution_status": "not_executed"})
        decision = {"project_status": status, "next_action": action, "reason": selected["rationale"],
                    "conditions": context["conditions"], "policy_ref": {"id": "external-proposal", "version": "1"},
                    "knowledge_refs": [], "evidence_refs": [], "scientific_validation": False,
                    "selection_ref": {"context_sha256": context["context_sha256"],
                                      "candidate_id": candidate["id"] if candidate else None,
                                      "provider_claim": selected["provider"], "provider_verified": False,
                                      "evidence_citation_ids": selected["evidence_citation_ids"],
                                      "model_execution_verified": False,
                                      "external_usage": "unknown_not_counted_as_zero"}}
        if "experience_case_refs" in selected:
            decision["selection_ref"]["experience_case_refs"] = copy.deepcopy(selected["experience_case_refs"])
        return {"decision": decision, "executable": candidate is not None, "status": status,
                "blockers": context["blockers"], "selection_context": context}

    @staticmethod
    def _parent(project, request_id):
        return next((item for item in project.get("controller_requests", []) if item["request_id"] == request_id), None)

    @staticmethod
    def _response(parent, replayed=False):
        response = {"schema_version": "project-controller-advance-v1", "project_id": parent["project_id"],
                "request_id": parent["request_id"], "request_sha256": parent["request_sha256"],
                "status": parent["status"], "replayed": replayed,
                "decision": copy.deepcopy(parent["decision"]), "blockers": copy.deepcopy(parent.get("blockers", [])),
                "child_request_id": parent["child_request_id"], "result": copy.deepcopy(parent.get("result")),
                "scientific_validation": False}
        if "selection_context" in parent:
            response["selection_context_sha256"] = parent["selection_context"]["context_sha256"]
            response["selection_proposal"] = copy.deepcopy(parent["request"]["proposal"])
        if "recipe_decision" in parent["request"]:
            response["recipe_decision"] = copy.deepcopy(parent["request"]["recipe_decision"])
        return response

    @staticmethod
    def _check_rejected(parent):
        if parent["status"] == "rejected":
            error = parent["result"]["failure"]
            raise ResearchError(error["code"], error["message"])

    def _finish(self, original, *, child=None, failure=None):
        """Update only this request, never turn a competing live writer into failure."""
        with self.project._writer():
            with self.project._connect() as con:
                project = self.project._project(con)
                parent = self._parent(project, original["request_id"])
                require(parent is not None and parent["request_sha256"] == original["request_sha256"],
                        "IDEMPOTENCY_CONFLICT", "Controller request binding changed.")
                if parent["status"] in ("completed", "failed", "rejected", "waiting", "needs_review"):
                    return copy.deepcopy(parent)
                if child is not None:
                    parent["status"] = child["status"]
                    parent["result"] = {"child": {key: copy.deepcopy(child[key]) for key in
                        ("id", "request_id", "command", "status", "artifact", "result_sha256", "failure") if key in child},
                        "recovered": child.get("recovered", False), "reused": child.get("reused", False)}
                else:
                    parent.update(status="rejected", result={"failure": failure, "child": None})
                project["state_version"] += 1
                parent["state_version_after"] = project["state_version"]
                self.project._save(con, project)
                return copy.deepcopy(parent)

    def _dispatch(self, parent, *, replayed):
        self._check_rejected(parent)
        if parent["status"] not in ("prepared", "unknown", "running"):
            return self._response(parent, replayed)
        with self.project._writer():
            with self.project._connect() as con:
                current = self.project._project(con)
                stored = self._parent(current, parent["request_id"])
                require(stored is not None and stored["request_sha256"] == parent["request_sha256"],
                        "IDEMPOTENCY_CONFLICT", "Controller request binding changed.")
                parent = copy.deepcopy(stored)
                self._check_rejected(parent)
                if parent["status"] not in ("prepared", "unknown", "running"):
                    return self._response(parent, True)
                require(parent["decision_sha256"] == fingerprint(parent["decision"]),
                        "EVIDENCE_CHANGED", "Frozen controller decision identity changed.")
                # Block before touching either an accepted child or a parent-only
                # intent. Do not turn a source mismatch into a permanent rejection.
                require(current["code_identity"] == parent["code_identity"] == project_code_identity()
                        and parent["controller_code_identity"] == code_identity(),
                        "CODE_CHANGED", "Resume the original nonterminal request with its source pin.")
                child = self.project._action(con, parent["child_request_id"])
            failure = None
            if child is None:
                if "selection_context" in parent:
                    selected = project_selection.validate_proposal(parent["selection_context"], parent["request"]["proposal"])
                    candidate = selected["candidate"]
                    frozen = parent["decision"]["next_action"]
                    require(candidate is not None and candidate["method_id"] == frozen["method_id"]
                            and candidate["parameters"] == frozen.get("parameters", {})
                            and parent["selection_context"]["controller_code_identity"] == parent["controller_code_identity"],
                            "EVIDENCE_CHANGED", "Frozen selection context and dispatched action differ.")
                if current["state_version"] != parent["dispatch_state_version"]:
                    failure = {"code": "STALE_STATE", "message": "Frozen controller choice is stale; it will not be replaced with another action."}
                elif current["source_snapshot_sha256"] != parent["source_snapshot_sha256"]:
                    failure = {"code": "EVIDENCE_CHANGED", "message": "The frozen controller input identity changed."}
        if failure is not None:
            rejected = self._finish(parent, failure=failure)
            self._check_rejected(rejected)
            return self._response(rejected, replayed)
        action = parent["decision"]["next_action"]
        parameters = action.get("parameters", {})
        try:
            if registry.is_source(action["method_id"]):
                result = self.project.read_evidence(request_id=parent["child_request_id"],
                    receipt_snapshot_sha256=parameters["receipt_snapshot_sha256"],
                    expected_state_version=parent["dispatch_state_version"])
            else:
                if action["method_id"] in registry.followup_ids(registry.primary_id(current)):
                    result = self.project.step(request_id=parent["child_request_id"], method_id=action["method_id"],
                                               parameters=parameters, expected_state_version=parent["dispatch_state_version"])
                else:
                    result = self.project.step(request_id=parent["child_request_id"], dimension=parameters.get("dimension"),
                                               expected_state_version=parent["dispatch_state_version"])
        except ResearchError as error:
            # A concurrent writer may still own the child. Do not persist a spurious failure.
            if error.code == "PROJECT_BUSY":
                raise
            with self.project._connect(readonly=True) as con:
                recorded = self.project._action(con, parent["child_request_id"])
            if recorded is not None and recorded["status"] in ("completed", "failed", "unknown"):
                self._finish(parent, child=recorded)
            elif recorded is None:
                self._finish(parent, failure={"code": error.code, "message": str(error)})
            raise
        finished = self._finish(parent, child=result)
        return self._response(finished, replayed)

    def advance(self, *, request_id, need="next_check", expected_state_version=None):
        identifier(request_id)
        need = _need(need)
        state = self.project.status()
        old = self._parent(state, request_id)
        if old is not None and "effective_recipe_revision" in old:
            recipe = old["request"]["recipe_decision"]["recipe"]
            revision = old["effective_recipe_revision"]
        elif old is None and current_recipe(state) is not None and project_design.current(state) is None:
            recipe = current_recipe(state)
            revision = state["recipe_revisions"][-1]["revision"]
        else:
            return self._advance(request_id=request_id, need=need, expected_state_version=expected_state_version)
        context = old["selection_context"] if old is not None else self.selection_context(need=need)
        decision = research_recipe.compile_recipe(recipe, context)
        return self._advance(request_id=request_id, need=need, expected_state_version=expected_state_version,
                             proposal=decision["proposal"], recipe_decision=decision, effective_revision=revision)

    def advance_selection(self, *, request_id, proposal, need="next_check", expected_state_version=None):
        try:
            proposal = project_selection.parse_proposal(canonical(proposal).encode("utf-8"))
        except (TypeError, ValueError, RecursionError):
            raise ResearchError("INVALID_SELECTION_PROPOSAL", "A bounded JSON proposal is required.") from None
        return self._advance(request_id=request_id, need=need, expected_state_version=expected_state_version, proposal=proposal)

    def advance_feedback(self, *, request_id, registration_request_id, expected_state_version=None):
        """Execute a preregistered branch through the original selection gates.

        A replay rebuilds the decision from its original context, never from
        newer feedback. Unknown chooses wait and cannot dispatch an action.
        """
        identifier(request_id)
        identifier(registration_request_id, "registration_request_id")
        from .feedback_policy import select_from_feedback
        state = self.project.status()
        registrations = [item for item in state.get("hypothesis_registrations", [])
                         if item["request_id"] == registration_request_id]
        require(len(registrations) == 1, "INVALID_REQUEST", "Use one original prediction registration.")
        old = self._parent(state, request_id)
        if old is not None:
            require(old["request"]["command"] == "controller.advance_selection"
                    and type(old.get("selection_context")) is dict,
                    "IDEMPOTENCY_CONFLICT", "The original request is not a feedback selection.")
        context = old["selection_context"] if old is not None else self.selection_context()
        proposal = select_from_feedback(context, registration=registrations[0],
            provider={"kind": "operator_assistant", "label": "preregistered-feedback-policy-v1"})
        proposal["rationale"] = ("Preregistration " + registration_request_id + " sha256:"
                                 + registrations[0]["registration_sha256"] + ". " + proposal["rationale"])
        return self.advance_selection(request_id=request_id, proposal=proposal,
                                      expected_state_version=expected_state_version)

    def _replay_tabular_quality(self, state, parent, body, registration, *, v2=False):
        """Validate an original terminal policy receipt while the writer is held."""
        from .tabular_quality_feedback import _artifact, _outcome
        meta = parent.get("tabular_quality_policy")
        fields = {"schema_version", "request", "request_sha256", "registration_sha256",
                  "feedback", "context_sha256", "proposal_sha256", "record_sha256"}
        require(type(meta) is dict and set(meta) == fields | ({"plan_sha256"} if v2 else set())
                and meta["schema_version"] == ("tabular-quality-policy-v2" if v2 else "tabular-quality-policy-v1")
                and meta["record_sha256"] == fingerprint({k:v for k,v in meta.items() if k != "record_sha256"})
                and meta["request"] == body and meta["request_sha256"] == fingerprint(body)
                and meta["registration_sha256"] == registration["registration_sha256"],
                "IDEMPOTENCY_CONFLICT", "The original tabular policy request or registration differs.")
        require(parent["status"] not in ("prepared", "running", "unknown"),
                "EXECUTION_UNKNOWN", "The original policy request is nonterminal; inspect it without dispatch.")
        require(parent["status"] in ("completed", "failed", "rejected", "waiting", "needs_review"),
                "EVIDENCE_CHANGED", "The original policy status is not recognized.")
        context, request, decision = parent["selection_context"], parent["request"], parent["decision"]
        require(state["id"] == registration["project_id"] and state["run_id"] == registration["run_id"]
                and state["source_snapshot_sha256"] == registration["source_snapshot_sha256"]
                and state["registration"]["source_sha256"] == registration["source_sha256"]
                and fingerprint(state["source_scope"]) == registration["scope_sha256"]
                and state["code_identity"] == registration["project_code_identity"] == project_code_identity()
                and code_identity() == registration["controller_code_identity"] == parent["controller_code_identity"]
                and parent["code_identity"] == state["code_identity"]
                and parent["project_id"] == state["id"] and parent["source_snapshot_sha256"] == state["source_snapshot_sha256"]
                and parent["request_sha256"] == fingerprint(request) and parent["decision_sha256"] == fingerprint(decision)
                and request["command"] == "controller.advance_selection" and request["need"] == "next_check"
                and request["project_id"] == state["id"] and request["expected_state_version"] == body["expected_state_version"]
                and meta["context_sha256"] == context["context_sha256"]
                and meta["proposal_sha256"] == fingerprint(request["proposal"])
                and context["snapshot_ref"] == parent["snapshot_ref_before"]
                and context["state_version"] == parent["state_version_before"]
                and any(fingerprint(p) == fingerprint(context.get("research_plan"))
                        for p in state.get("plan_revisions", []))
                and any(p["version"] == registration["plan_version"] and fingerprint(p) == registration["plan_sha256"]
                        for p in state.get("plan_revisions", [])),
                "EVIDENCE_CHANGED", "The original policy context, source, plan or code differs.")
        self.project._source(state)
        selected = project_selection.validate_proposal(context, request["proposal"])
        candidate = selected["candidate"]
        reconstructed = self._selected_plan(state, "next_check", request["proposal"], context=context)
        require(_compact_decision(reconstructed["decision"]) == decision,
                "EVIDENCE_CHANGED", "The original frozen policy decision differs.")
        fb = meta["feedback"]
        require(type(fb) is dict and fb.get("registration_sha256") == registration["registration_sha256"]
                and fb.get("request_id") == registration["request_id"]
                and fb.get("controller_request_id") == registration["controller_request_id"]
                and fb.get("scientific_validation") is False,
                "EVIDENCE_CHANGED", "The original feedback binding differs.")
        if v2:
            from .tabular_quality_plan import check_reference
            frozen_plan = context.get("research_plan")
            require(type(frozen_plan) is dict and frozen_plan.get("request_id") == body["plan_request_id"]
                    and fingerprint(frozen_plan) == body["plan_sha256"] == meta["plan_sha256"]
                    and type(frozen_plan.get("quality_feedback_ref")) is dict
                    and frozen_plan["quality_feedback_ref"].get("registration_request_id") == registration["request_id"],
                    "EVIDENCE_CHANGED", "Original quality-linked plan differs.")
            verified = check_reference(self.project, state, frozen_plan["quality_feedback_ref"],
                                       based_on_state_version=frozen_plan["based_on_state_version"], revision=frozen_plan)
            require(canonical(verified) == canonical(fb), "EVIDENCE_CHANGED", "Original plan feedback differs.")
        require(canonical(_tabular_quality_proposal(context, registration, fb,
                          _verified_plan_sha256=meta["plan_sha256"] if v2 else None)) == canonical(request["proposal"]),
                "EVIDENCE_CHANGED", "The original feedback does not reproduce its frozen proposal.")
        require(fb.get("outcome") in ("condition_met", "condition_not_met", "unknown")
                and (type(fb.get("evaluation")) is dict if fb.get("outcome") != "unknown" else
                     fb.get("action_id") is None and fb.get("result_sha256") is None),
                "EVIDENCE_CHANGED", "The original feedback outcome is malformed.")
        # Reauthenticate original quality evidence under its registered historical
        # plan, even if a later unrelated plan exists. Never redispatch either action.
        if fb.get("evaluation") is not None:
            old_plans = [p for p in state["plan_revisions"] if p["version"] == registration["plan_version"]
                         and fingerprint(p) == registration["plan_sha256"]]
            require(len(old_plans) == 1, "EVIDENCE_CHANGED", "Original registered plan is unavailable.")
            historical = copy.deepcopy(state)
            historical["plan_revisions"] = old_plans
            original_feedback = _outcome(self.project, historical, registration)
            expected_feedback = {k:v for k,v in fb.items() if k not in
                                 ("request_id", "registration_sha256", "controller_request_id")}
            require(canonical(original_feedback) == canonical(expected_feedback),
                    "EVIDENCE_CHANGED", "The original quality feedback or evidence differs.")
        if candidate is None:
            require(parent["status"] in ("waiting", "needs_review") and parent["child_request_id"] is None
                    and parent["result"] is None, "EVIDENCE_CHANGED", "Original wait receipt differs.")
        else:
            require(fb.get("outcome") == "condition_met" and candidate["method_id"] == registry.NUMERIC
                    and candidate["evaluation_ref"] == registry.evaluation_ref(registry.NUMERIC)
                    and candidate["parameters"] == {"based_on_action_id": fb.get("action_id"),
                                                      "based_on_result_sha256": fb.get("result_sha256")},
                    "EVIDENCE_CHANGED", "Original quality-bound candidate differs.")
            quality = [a for a in state["actions"] if a["id"] == fb.get("action_id")]
            require(len(quality) == 1 and quality[0]["result_sha256"] == fb.get("result_sha256")
                    and quality[0]["status"] == "completed", "EVIDENCE_CHANGED", "Original quality action differs.")
            _artifact(self.project, quality[0])
            child_id = "controller-child-" + fingerprint({"project_id":state["id"],"request_id":body["request_id"]})[:32]
            require(parent["child_request_id"] == child_id, "EVIDENCE_CHANGED", "Original child ID differs.")
            if parent["status"] == "rejected":
                # Rejection can be terminal before a child was ever accepted.
                # Return the original error only after all original policy and
                # quality evidence above has been reauthenticated.
                rejected = parent.get("result")
                failure = rejected.get("failure") if type(rejected) is dict else None
                require(type(rejected) is dict and set(rejected) == {"failure", "child"}
                        and rejected["child"] is None and type(failure) is dict
                        and set(failure) == {"code", "message"}
                        and all(type(failure[k]) is str and failure[k] for k in ("code", "message")),
                        "EVIDENCE_CHANGED", "Original rejected receipt is malformed.")
                with self.project._connect(readonly=True) as con:
                    action_row = con.execute("SELECT 1 FROM actions WHERE request_id=?", (child_id,)).fetchone()
                    replay_row = con.execute("SELECT 1 FROM replays WHERE request_id=? OR action_request_id=?",
                                             (child_id, child_id)).fetchone()
                require(action_row is None and replay_row is None and not any(a.get("request_id") == child_id
                        for a in state["actions"] + state["evidence_actions"]),
                        "EVIDENCE_CHANGED", "A rejected parent unexpectedly has a child or replay reference.")
                if v2:
                    final_feedback = check_reference(self.project, state, frozen_plan["quality_feedback_ref"],
                        based_on_state_version=frozen_plan["based_on_state_version"], revision=frozen_plan)
                    require(canonical(final_feedback) == canonical(fb), "EVIDENCE_CHANGED", "Original quality evidence changed during replay.")
                self._check_rejected(parent)
            with self.project._connect(readonly=True) as con:
                row = con.execute("SELECT fingerprint, record FROM actions WHERE request_id=?", (child_id,)).fetchone()
            require(row is not None, "EVIDENCE_CHANGED", "Original terminal child is missing.")
            import json
            child = json.loads(row["record"])
            fields = ("id", "request_id", "command", "status", "artifact", "result_sha256", "failure")
            child_request = {"project_id":state["id"], "command":registry.NUMERIC, "dimension":None,
                             "source_snapshot_sha256":state["source_snapshot_sha256"],
                             "parameters":candidate["parameters"], "evaluation_ref":candidate["evaluation_ref"]}
            binding = child["method_instance"]["input_bindings"]
            require(row["fingerprint"] == child["request_sha256"] == fingerprint(child_request)
                    and child["id"] == "action-" + fingerprint({"request_id":child_id, **child_request})[:32]
                    and child["request_id"] == child_id and child in state["actions"]
                    and child["project_id"] == state["id"] and child["run_id"] == state["run_id"]
                    and child["code_identity"] == state["code_identity"]
                    and child["command"] == registry.NUMERIC and child["dimension"] is None
                    and child["parameters"] == candidate["parameters"]
                    and child["method_instance"]["parameters"] == candidate["parameters"]
                    and child["method_instance"]["evaluation_ref"] == candidate["evaluation_ref"]
                    and all(binding.get(k) == v for k,v in {"source_snapshot_sha256":state["source_snapshot_sha256"],
                                                            **candidate["parameters"]}.items())
                    and child["source_snapshot_sha256"] == state["source_snapshot_sha256"]
                    and type(parent["result"]) is dict and set(parent["result"]) == {"child", "recovered", "reused"}
                    and parent["result"]["recovered"] is False and parent["result"]["reused"] is False
                    and parent["result"]["child"] == {k:child[k] for k in fields if k in child} and parent["status"] == child["status"],
                    "EVIDENCE_CHANGED", "Original terminal child binding differs.")
            if child["status"] == "completed":
                _artifact(self.project, child)
        if v2:
            final_feedback = check_reference(self.project, state, frozen_plan["quality_feedback_ref"],
                based_on_state_version=frozen_plan["based_on_state_version"], revision=frozen_plan)
            require(canonical(final_feedback) == canonical(fb), "EVIDENCE_CHANGED", "Original quality evidence changed during replay.")
        self._check_rejected(parent)
        return self._response(parent, True)

    def advance_tabular_quality_feedback(self, *, request_id, registration_request_id, expected_state_version,
                                         _manager_intent_sha256=None):
        """Opt in to a saved-quality branch; unknown/nonterminal requests never dispatch."""
        identifier(request_id)
        identifier(registration_request_id, "registration_request_id")
        require(type(expected_state_version) is int and expected_state_version >= 0,
                "INVALID_REQUEST", "Use an exact nonnegative state version.")
        from .tabular_quality_feedback import _checked_collection
        body = {"request_id":request_id, "registration_request_id":registration_request_id,
                "expected_state_version":expected_state_version}
        with self.project._writer():
            with self.project._connect() as con:
                stored = self.project._project(con)
                registrations = stored.get("tabular_quality_registrations", [])
                _checked_collection(registrations)
                matches = [r for r in registrations if r["request_id"] == registration_request_id]
                require(len(matches) == 1, "INVALID_REQUEST", "Use one original quality registration.")
                registration = matches[0]
                old = self._parent(stored, request_id)
                if old is not None:
                    state = self.project.status()
                    return self._replay_tabular_quality(state, old, body, registration)
                require(not any(p.get("status") in ("prepared", "running", "unknown") for p in stored.get("controller_requests", [])),
                        "EXECUTION_UNKNOWN", "Inspect the original nonterminal controller request.")
                self.project._require_unclaimed(stored, request_id)
                require(self.project._action(con, request_id) is None, "IDEMPOTENCY_CONFLICT", "Request ID belongs to an action.")
                require(stored["state_version"] == expected_state_version, "STALE_STATE", "Read the current project state before advancing.")
                require(stored["code_identity"] == registration["project_code_identity"] == project_code_identity()
                        and code_identity() == registration["controller_code_identity"],
                        "CODE_CHANGED", "Use the original registered project and controller code.")
                current = self.project.status()
                require(not any(a.get("status") in ("pending", "running", "unknown") for a in current["actions"] + current["evidence_actions"]),
                        "EXECUTION_UNKNOWN", "Inspect the original nonterminal action.")
                feedback = self.project.read_tabular_quality_feedback(request_id=registration_request_id)
                require(self.project.status()["snapshot_ref"] == current["snapshot_ref"], "STALE_STATE", "Project changed while reading quality feedback.")
                context = self._selection_context(current, "next_check")
                proposal = _tabular_quality_proposal(context, registration, feedback)
                plan = self._selected_plan(current, "next_check", proposal, context=context)
                request = {"project_id":stored["id"], "command":"controller.advance_selection", "need":"next_check",
                           "expected_state_version":expected_state_version, "proposal":copy.deepcopy(proposal)}
                child_id = "controller-child-" + fingerprint({"project_id":stored["id"], "request_id":request_id})[:32]
                self.project._require_unclaimed(stored, child_id)
                require(self.project._action(con, child_id) is None, "IDEMPOTENCY_CONFLICT", "Derived child ID is already claimed.")
                meta = {"schema_version":"tabular-quality-policy-v1", "request":body, "request_sha256":fingerprint(body),
                        "registration_sha256":registration["registration_sha256"], "feedback":copy.deepcopy(feedback),
                        "context_sha256":context["context_sha256"], "proposal_sha256":fingerprint(proposal)}
                meta["record_sha256"] = fingerprint(meta)
                stored["state_version"] += 1
                parent = {"schema_version":"project-controller-request-v1", "project_id":stored["id"],
                          "request_id":request_id, "request_sha256":fingerprint(request), "request":request,
                          "source_snapshot_sha256":stored["source_snapshot_sha256"], "snapshot_ref_before":current["snapshot_ref"],
                          "state_version_before":current["state_version"], "dispatch_state_version":stored["state_version"],
                          "code_identity":stored["code_identity"], "controller_code_identity":code_identity(),
                          "decision":_compact_decision(plan["decision"]), "blockers":copy.deepcopy(plan["blockers"]),
                          "child_request_id":child_id if plan["executable"] else None,
                          "status":"prepared" if plan["executable"] else plan["status"], "result":None,
                          "selection_context":context, "tabular_quality_policy":meta}
                parent["decision_sha256"] = fingerprint(parent["decision"])
                stored.setdefault("controller_requests", []).append(parent)
                self.project._save(con, stored)
                if _manager_intent_sha256 is not None:
                    from .tabular_quality_feedback import _manager_claim
                    core_sha = fingerprint({"request_sha256":parent["request_sha256"], "policy_sha256":meta["record_sha256"]})
                    _manager_claim(con, "policy", request_id, _manager_intent_sha256, core_sha, create=True)
                parent = copy.deepcopy(parent)
        return self._dispatch(parent, replayed=False)

    def advance_tabular_quality_feedback_v2(self, *, request_id, registration_request_id, plan_request_id,
                                            plan_sha256, expected_state_version, _manager_intent_sha256=None):
        """Opt in to a verified direct-successor plan, using the real current context."""
        identifier(request_id)
        identifier(registration_request_id, "registration_request_id")
        identifier(plan_request_id, "plan_request_id")
        require(type(plan_sha256) is str and re.fullmatch(r"[a-f0-9]{64}", plan_sha256) is not None
                and type(expected_state_version) is int and expected_state_version >= 0,
                "INVALID_REQUEST", "Use the exact current plan identity and state version.")
        from .tabular_quality_feedback import _checked_collection
        from .tabular_quality_plan import check_reference
        body = {"request_id":request_id, "registration_request_id":registration_request_id,
                "plan_request_id":plan_request_id, "plan_sha256":plan_sha256,
                "expected_state_version":expected_state_version}
        with self.project._writer():
            with self.project._connect() as con:
                stored = self.project._project(con)
                registrations = stored.get("tabular_quality_registrations", [])
                _checked_collection(registrations)
                matches = [r for r in registrations if r["request_id"] == registration_request_id]
                require(len(matches) == 1, "INVALID_REQUEST", "Use one original quality registration.")
                registration = matches[0]
                old = self._parent(stored, request_id)
                if old is not None:
                    return self._replay_tabular_quality(self.project.status(), old, body, registration, v2=True)
                require(not any(p.get("status") in ("prepared", "running", "unknown") for p in stored.get("controller_requests", [])),
                        "EXECUTION_UNKNOWN", "Inspect the original nonterminal controller request.")
                self.project._require_unclaimed(stored, request_id)
                require(con.execute("SELECT 1 FROM actions WHERE request_id=?", (request_id,)).fetchone() is None
                        and con.execute("SELECT 1 FROM replays WHERE request_id=? OR action_request_id=?", (request_id, request_id)).fetchone() is None,
                        "IDEMPOTENCY_CONFLICT", "Request ID belongs to an action or replay.")
                require(stored["state_version"] == expected_state_version, "STALE_STATE", "Read the current project state before advancing.")
                require(stored["code_identity"] == registration["project_code_identity"] == project_code_identity()
                        and code_identity() == registration["controller_code_identity"],
                        "CODE_CHANGED", "Use the original registered project and controller code.")
                current = self.project.status()
                require(not any(a.get("status") in ("pending", "running", "unknown") for a in current["actions"] + current["evidence_actions"]),
                        "EXECUTION_UNKNOWN", "Inspect the original nonterminal action.")
                revisions = current.get("plan_revisions", [])
                require(bool(revisions) and revisions[-1].get("request_id") == plan_request_id
                        and fingerprint(revisions[-1]) == plan_sha256
                        and type(revisions[-1].get("quality_feedback_ref")) is dict
                        and revisions[-1]["quality_feedback_ref"].get("registration_request_id") == registration_request_id,
                        "CONDITION_NOT_SATISFIED", "Use the current exact quality-linked successor plan.")
                revision = revisions[-1]
                verified = check_reference(self.project, current, revision["quality_feedback_ref"],
                                           based_on_state_version=revision["based_on_state_version"], revision=revision)
                require(self.project.status()["snapshot_ref"] == current["snapshot_ref"], "STALE_STATE", "Project changed while authenticating quality feedback.")
                context = self._selection_context(current, "next_check")
                require(fingerprint(context.get("research_plan")) == plan_sha256, "EVIDENCE_CHANGED", "Current selection context has a different plan.")
                proposal = _tabular_quality_proposal(context, registration, verified, _verified_plan_sha256=plan_sha256)
                plan = self._selected_plan(current, "next_check", proposal, context=context)
                final_feedback = check_reference(self.project, current, revision["quality_feedback_ref"],
                    based_on_state_version=revision["based_on_state_version"], revision=revision)
                require(canonical(final_feedback) == canonical(verified), "EVIDENCE_CHANGED", "Quality evidence changed before accepting the decision.")
                request = {"project_id":stored["id"], "command":"controller.advance_selection", "need":"next_check",
                           "expected_state_version":expected_state_version, "proposal":copy.deepcopy(proposal)}
                child_id = "controller-child-" + fingerprint({"project_id":stored["id"], "request_id":request_id})[:32]
                self.project._require_unclaimed(stored, child_id)
                require(con.execute("SELECT 1 FROM actions WHERE request_id=?", (child_id,)).fetchone() is None
                        and con.execute("SELECT 1 FROM replays WHERE request_id=? OR action_request_id=?", (child_id, child_id)).fetchone() is None,
                        "IDEMPOTENCY_CONFLICT", "Derived child ID is already claimed.")
                meta = {"schema_version":"tabular-quality-policy-v2", "request":body, "request_sha256":fingerprint(body),
                        "registration_sha256":registration["registration_sha256"], "feedback":copy.deepcopy(verified),
                        "context_sha256":context["context_sha256"], "proposal_sha256":fingerprint(proposal), "plan_sha256":plan_sha256}
                meta["record_sha256"] = fingerprint(meta)
                stored["state_version"] += 1
                parent = {"schema_version":"project-controller-request-v1", "project_id":stored["id"],
                          "request_id":request_id, "request_sha256":fingerprint(request), "request":request,
                          "source_snapshot_sha256":stored["source_snapshot_sha256"], "snapshot_ref_before":current["snapshot_ref"],
                          "state_version_before":current["state_version"], "dispatch_state_version":stored["state_version"],
                          "code_identity":stored["code_identity"], "controller_code_identity":code_identity(),
                          "decision":_compact_decision(plan["decision"]), "blockers":copy.deepcopy(plan["blockers"]),
                          "child_request_id":child_id if plan["executable"] else None,
                          "status":"prepared" if plan["executable"] else plan["status"], "result":None,
                          "selection_context":context, "tabular_quality_policy":meta}
                parent["decision_sha256"] = fingerprint(parent["decision"])
                stored.setdefault("controller_requests", []).append(parent)
                self.project._save(con, stored)
                if _manager_intent_sha256 is not None:
                    from .tabular_quality_feedback import _manager_claim
                    core_sha = fingerprint({"request_sha256":parent["request_sha256"], "policy_sha256":meta["record_sha256"]})
                    _manager_claim(con, "policy", request_id, _manager_intent_sha256, core_sha, create=True)
                parent = copy.deepcopy(parent)
        return self._dispatch(parent, replayed=False)

    def advance_recipe(self, *, request_id, recipe, need="next_check", expected_state_version=None):
        identifier(request_id)
        need = _need(need)
        old = self._parent(self.project.status(), request_id)
        if old is not None:
            require(old["request"]["command"] == "controller.advance_recipe", "IDEMPOTENCY_CONFLICT",
                    "Controller request ID is already bound to a different command.")
        context = old["selection_context"] if old is not None else self.selection_context(need=need)
        decision = research_recipe.compile_recipe(recipe, context)
        return self._advance(request_id=request_id, need=need, expected_state_version=expected_state_version,
                             proposal=decision["proposal"], recipe_decision=decision)

    def _advance(self, *, request_id, need, expected_state_version, proposal=None, recipe_decision=None, effective_revision=None):
        identifier(request_id)
        need = _need(need)
        require(expected_state_version is None or (type(expected_state_version) is int and expected_state_version >= 0),
                "INVALID_REQUEST", "Expected state version must be a nonnegative integer.")
        replayed = False
        with self.project._writer():
            with self.project._connect() as con:
                project = self.project._project(con)
                request = {"project_id": project["id"], "command": "controller.advance", "need": need,
                           "expected_state_version": expected_state_version}
                if proposal is not None:
                    request.update(command="controller.advance_selection", proposal=copy.deepcopy(proposal))
                if recipe_decision is not None:
                    require(proposal is not None, "EVIDENCE_CHANGED", "A recipe decision requires its exact proposal.")
                    request.update(command="controller.advance_recipe", recipe_decision=copy.deepcopy(recipe_decision))
                old = self._parent(project, request_id)
                digest = fingerprint(request)
                if old is not None:
                    require("tabular_quality_policy" not in old, "IDEMPOTENCY_CONFLICT",
                            "Use the original tabular quality policy request; direct replay is forbidden.")
                    require(old["request_sha256"] == digest, "IDEMPOTENCY_CONFLICT", "Controller request content changed.")
                    if recipe_decision is not None:
                        require(fingerprint(old["request"]) == old["request_sha256"],
                                "EVIDENCE_CHANGED", "Frozen recipe request identity changed.")
                        _check_recipe_decision(old["selection_context"], old["request"]["proposal"], old["request"]["recipe_decision"])
                    parent, replayed = copy.deepcopy(old), True
                else:
                    self.project._require_unclaimed(project, request_id)
                    if effective_revision is not None:
                        revisions = project.get("recipe_revisions", [])
                        require(bool(revisions) and revisions[-1]["revision"] == effective_revision,
                                "STALE_RECIPE", "Effective recipe changed before this request was accepted.")
                    require(self.project._action(con, request_id) is None
                            and not any(item["request_id"] == request_id for key in ("code_revisions", "evidence_registrations", "source_requests", "model_budget_revisions", "local_model_requests", "researcher_feedback", "plan_revisions", "recipe_revisions", "hypothesis_registrations")
                                        for item in project.get(key, [])),
                            "IDEMPOTENCY_CONFLICT", "Request ID is already bound to a project command.")
                    require(not any(item.get("status") == "unknown" for item in project.get("controller_requests", [])),
                            "EXECUTION_UNKNOWN", "Inspect the original unknown controller request before accepting new work.")
                    require(not any(item["status"] in ("prepared", "running") for item in project.get("controller_requests", [])),
                            "PROJECT_BUSY", "Resume the already accepted controller request first.")
                    require(expected_state_version is None or project["state_version"] == expected_state_version,
                            "STALE_STATE", "Read the current project state before advancing.")
                    require(project["code_identity"] == project_code_identity(), "CODE_CHANGED", "Explicitly upgrade this project first.")
                    current = self.project.status()
                    plan = self._plan(current, need) if proposal is None else self._selected_plan(current, need, proposal)
                    if recipe_decision is not None:
                        _check_recipe_decision(plan["selection_context"], proposal, recipe_decision)
                        plan["decision"]["policy_ref"] = {"id": recipe_decision["recipe_id"],
                            "version": recipe_decision["recipe_version"], "kind": "deterministic_recipe"}
                        plan["decision"]["selection_ref"]["external_usage"] = "no_model_invocation_by_recipe_compiler"
                    child_id = "controller-child-" + fingerprint({"project_id": project["id"], "request_id": request_id})[:32]
                    self.project._require_unclaimed(project, child_id)
                    require(self.project._action(con, child_id) is None
                            and not any(item["request_id"] == child_id for key in ("code_revisions", "evidence_registrations", "controller_requests", "source_requests", "model_budget_revisions", "local_model_requests", "researcher_feedback", "plan_revisions", "recipe_revisions", "hypothesis_registrations")
                                        for item in project.get(key, [])),
                            "IDEMPOTENCY_CONFLICT", "Derived child ID is already bound to another command.")
                    project["state_version"] += 1
                    parent = {"schema_version": "project-controller-request-v1", "project_id": project["id"],
                              "request_id": request_id, "request_sha256": digest, "request": request,
                              "source_snapshot_sha256": project["source_snapshot_sha256"],
                              "snapshot_ref_before": current["snapshot_ref"], "state_version_before": current["state_version"],
                              "dispatch_state_version": project["state_version"], "code_identity": project["code_identity"],
                              "controller_code_identity": code_identity(), "decision": _compact_decision(plan["decision"]),
                              "blockers": copy.deepcopy(plan["blockers"]), "child_request_id": child_id if plan["executable"] else None,
                              "status": "prepared" if plan["executable"] else plan["status"], "result": None}
                    if "selection_context" in plan:
                        parent["selection_context"] = copy.deepcopy(plan["selection_context"])
                    if effective_revision is not None:
                        parent["effective_recipe_revision"] = effective_revision
                    parent["decision_sha256"] = fingerprint(parent["decision"])
                    project.setdefault("controller_requests", []).append(parent)
                    self.project._save(con, project)
                    parent = copy.deepcopy(parent)
        return self._dispatch(parent, replayed=replayed)
