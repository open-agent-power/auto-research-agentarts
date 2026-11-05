"""One condition-selected local step with a durable, immutable parent request."""
import copy
import hashlib
from pathlib import Path

from . import method_registry as registry, project_knowledge, research_methods, project_selection, research_recipe
from .contracts import ResearchError, canonical, fingerprint, identifier
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


class ProjectController:
    def __init__(self, workspace):
        self.project = ResearchProject(workspace)

    def _plan(self, project, need, *, include_knowledge=False):
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
        if outstanding:
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
        elif executable and method_id == registry.source_id(project):
            receipt = parameters.get("receipt_snapshot_sha256")
            if not any(item["receipt_snapshot_sha256"] == receipt for item in project.get("evidence_sources", [])):
                blockers.append({"code": "MISSING_SOURCE", "reason": "Register the actual task-bound source before reading it."})
            if len(project["evidence_actions"]) >= project["budget"].get("evidence_read_limit", 0):
                blockers.append({"code": "BUDGET_EXHAUSTED", "reason": "The cumulative source-read allowance is exhausted."})
        elif executable:
            blockers.append({"code": "METHOD_NOT_SUPPORTED", "reason": "Only the registered primary method or a source read may execute."})
        executable = bool(executable and not blockers)
        status = "needs_review" if outstanding else "waiting" if blockers else decision["project_status"]
        result = {"schema_version": "project-controller-next-v1", "project_id": project["id"],
                "snapshot_ref": project["snapshot_ref"], "state_version": project["state_version"],
                "source_snapshot_sha256": project["source_snapshot_sha256"], "options": options,
                "decision": decision, "status": status, "executable": executable,
                "blockers": blockers, "scientific_validation": False}
        if include_knowledge:
            result["selection_evidence"] = knowledge.get("evidence", [])
        return result

    def next(self, *, need="next_check"):
        need = _need(need)
        before = self.project.status()
        result = self._plan(before, need)
        require(self.project.status()["snapshot_ref"] == before["snapshot_ref"],
                "STALE_STATE", "Project changed while preparing the next decision.")
        return result

    def _selection_context(self, project, need):
        plan = self._plan(project, need, include_knowledge=True)
        # Budget/wait blockers above apply to the default choice. Recheck each
        # candidate independently so an unread source can remain eligible.
        blockers = [copy.deepcopy(item) for item in plan["blockers"]
                    if item["code"] not in ("BUDGET_EXHAUSTED", "PROJECT_WAITING")]
        candidates, conditions = [], []
        primary = registry.primary_id(project)
        finished = {item.get("receipt_snapshot_sha256") for item in project["evidence_actions"]
                    if item["status"] in ("completed", "failed")}
        unread = [item for item in project.get("evidence_sources", [])
                  if item.get("selection_count", 0) > 0 and item["receipt_snapshot_sha256"] not in finished]
        for option in plan["options"]:
            method_id, reasons = option["method_id"], []
            if option["condition"] != "satisfied":
                reasons.append("CONDITION_NOT_SATISFIED")
            if option["completed"]:
                reasons.append("ALREADY_COMPLETED")
            parameters = []
            if method_id == primary or method_id in registry.followup_ids(primary):
                if method_id == primary and project["research_status"] != "active":
                    reasons.append("PROJECT_WAITING")
                if len(project["actions"]) >= project["budget"]["local_tool_call_limit"]:
                    reasons.append("BUDGET_EXHAUSTED")
                parameters = ([{"dimension": value} for value in option.get("remaining_dimensions", [])]
                              if method_id == research_methods.OOF else [copy.deepcopy(option.get("parameters", {}))])
            elif method_id == registry.source_id(project):
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
        return project_selection.seal_context(context)

    def selection_context(self, *, need="next_check"):
        before = self.project.status()
        context = self._selection_context(before, _need(need))
        require(self.project.status()["snapshot_ref"] == before["snapshot_ref"],
                "STALE_STATE", "Project changed while preparing selection context.")
        return context

    def _selected_plan(self, project, need, proposal):
        context = self._selection_context(project, need)
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
                elif current["code_identity"] != parent["code_identity"] or current["code_identity"] != project_code_identity() or parent["controller_code_identity"] != code_identity():
                    failure = {"code": "CODE_CHANGED", "message": "The frozen controller choice requires its registered implementation."}
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
        return self._advance(request_id=request_id, need=need, expected_state_version=expected_state_version)

    def advance_selection(self, *, request_id, proposal, need="next_check", expected_state_version=None):
        try:
            proposal = project_selection.parse_proposal(canonical(proposal).encode("utf-8"))
        except (TypeError, ValueError, RecursionError):
            raise ResearchError("INVALID_SELECTION_PROPOSAL", "A bounded JSON proposal is required.") from None
        return self._advance(request_id=request_id, need=need, expected_state_version=expected_state_version, proposal=proposal)

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

    def _advance(self, *, request_id, need, expected_state_version, proposal=None, recipe_decision=None):
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
                digest = fingerprint(request)
                old = self._parent(project, request_id)
                if old is not None:
                    require(old["request_sha256"] == digest, "IDEMPOTENCY_CONFLICT", "Controller request content changed.")
                    if recipe_decision is not None:
                        require(fingerprint(old["request"]) == old["request_sha256"],
                                "EVIDENCE_CHANGED", "Frozen recipe request identity changed.")
                        _check_recipe_decision(old["selection_context"], old["request"]["proposal"], old["request"]["recipe_decision"])
                    parent, replayed = copy.deepcopy(old), True
                else:
                    require(self.project._action(con, request_id) is None
                            and not any(item["request_id"] == request_id for key in ("code_revisions", "evidence_registrations", "source_requests", "model_budget_revisions", "local_model_requests")
                                        for item in project.get(key, [])),
                            "IDEMPOTENCY_CONFLICT", "Request ID is already bound to a project command.")
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
                    require(self.project._action(con, child_id) is None
                            and not any(item["request_id"] == child_id for key in ("code_revisions", "evidence_registrations", "controller_requests", "source_requests", "model_budget_revisions", "local_model_requests")
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
                    parent["decision_sha256"] = fingerprint(parent["decision"])
                    project.setdefault("controller_requests", []).append(parent)
                    self.project._save(con, project)
                    parent = copy.deepcopy(parent)
        return self._dispatch(parent, replayed=replayed)
