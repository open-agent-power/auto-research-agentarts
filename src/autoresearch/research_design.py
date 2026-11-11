"""Discover reusable research designs and retain feedback-derived resource versions."""

import copy
import json

from .contracts import ResearchError
from .prediction_summary import summarize_oof_range


RESOURCE = {
    "schema_version": "research-design-resource-v1", "id": "saved-prediction-review", "version": 1,
    "title": "保存预测的公平基线核验", "question": "候选预测相对公平均值参考是否有优势？",
    "claim": "候选预测的绝对误差低于排除评价对象后的均值参考。",
    "alternatives": ["全样本均值掩盖了评价对象信息的使用", "总体优势可能集中于少量样本或分组"],
    "checks": ["baseline"],
    "sources": ["本项目计算定义：逐行或逐组排除评价对象后计算均值参考，保存配对误差。"],
    "parent_version": None, "change_reason": "首版先核对保存预测与公平均值参考。",
}
METHODS = {"data.prediction-" + name: name for name in ("baseline", "grouped", "sensitivity")}
RAW_RESOURCE = {
    "schema_version": "research-design-resource-v1", "id": "ridge-validation-design", "version": 1,
    "title": "原始数据的划分对照与负对照", "question": "固定模型的优势在随机和未见组评价中是否保持，是否依赖预测与样本的对应？",
    "claim": "固定Ridge在两种划分中优于训练集均值参考，原预测对应的误差低于绝大多数折内重排。",
    "alternatives": ["随机划分中的相似组重叠造成乐观结果", "预测值的分布本身足以产生表面优势", "缺失排除或预处理使用了评价样本的信息"],
    "checks": ["random_cv", "group_cv", "negative_control"],
    "sources": ["固定协议：KFold(5,shuffle=True,seed=11)与GroupKFold(最多5折)，训练折StandardScaler与Ridge(alpha=1)。",
                "负对照：保留评价折，折内重排预测199次，seed=11，保存误差分布与原误差的条件秩。"],
    "parent_version": None, "change_reason": "在同一数据、字段及完整样本口径上比较划分协议并检查样本对应。",
}
METHODS.update({"data.ridge-random-validation": "random_cv", "data.ridge-group-validation": "group_cv",
                "data.prediction-negative-control": "negative_control"})


def _records(project, state, binding=None):
    binding = binding or (state.get("design_revisions") or [None])[-1]
    if binding is None:
        return []
    records = []
    for action in state["actions"]:
        if action["command"] not in METHODS or action["status"] != "completed":
            continue
        saved = action.get("design_binding", {})
        if saved.get("version") != binding["version"]:
            continue
        project._recover(action)
        result = json.loads(project._artifact(action).read_bytes())["tool_result"]["result"]
        check = result.get("analysis", result.get("check_result", result))
        records.append({"action_id": action["id"], "method_id": action["command"],
                        "status": action["status"], "check": METHODS[action["command"]], **copy.deepcopy(check)})
        if METHODS[action["command"]] in ("random_cv", "group_cv"):
            records[-1]["prediction_range"] = summarize_oof_range(check["oof"])
    return records


def _assessment(resource, records, scope):
    if resource["checks"][0] == "random_cv":
        return _raw_assessment(resource, records)
    required = [name for name in resource["checks"] if name != "grouped" or scope.get("group_columns")]
    skipped = ["grouped"] if "grouped" in resource["checks"] and not scope.get("group_columns") else []
    by_check = {item["check"]: item for item in records}
    missing = [name for name in required if name not in by_check]
    if missing:
        return {"status": "incomplete" if records else "not_started", "claim_supported": None,
                "reason": "仍需完成当前设计要求的验证。", "missing_checks": missing, "skipped_checks": skipped}
    values = [by_check[name].get("summary", {}).get("improvement") for name in required]
    sensitivity = by_check.get("sensitivity", {}).get("details", {})
    grouped = by_check.get("grouped", {}).get("details", {})
    groups = grouped.get("groups", []) if isinstance(grouped, dict) else []
    failed_group = any(group.get("candidate_mae") is not None and group.get("reference_mae") is not None
                       and group["candidate_mae"] >= group["reference_mae"] for group in groups)
    failed = failed_group or sensitivity.get("conclusion_reversed", False) or any(
        isinstance(value, (int, float)) and value <= 0 for value in values)
    unknown = any(value is None for value in values) or any(group.get("reference_mae") is None for group in groups)
    if "sensitivity" in required:
        unknown = unknown or not sensitivity.get("computable_units") or any(
            item.get("improvement") is None for item in sensitivity.get("removals", []))
    if unknown and not failed:
        return {"status": "review_ready", "claim_supported": None,
                "reason": "检查记录已保存，样本、分组或参考误差不足以判断完整优势主张。", "missing_checks": [], "skipped_checks": skipped}
    supported = not failed and not unknown
    return {"status": "review_ready", "claim_supported": supported,
            "reason": "当前已完成检查支持所声明的误差比较，仍需核对预测产生协议与样本含义。" if supported
                      else "当前结果未支持完整优势主张，保留不利结果并据此修订研究判断。",
            "missing_checks": [], "skipped_checks": skipped}


def _raw_assessment(resource, records):
    by_check = {item["check"]: item for item in records}
    missing = [name for name in resource["checks"] if name not in by_check]
    if missing:
        return {"status": "incomplete" if records else "not_started", "claim_supported": None,
                "reason": "仍需完成当前设计要求的划分对照和负对照。", "missing_checks": missing,
                "skipped_checks": [], "scientific_validation": False}
    random = by_check["random_cv"].get("summary", {})
    grouped = by_check.get("group_cv", {}).get("summary", {})
    control = by_check.get("negative_control", {}).get("summary", {})
    improvements = [by_check[name].get("summary", {}).get("improvement")
                    for name in resource["checks"] if name != "negative_control"]
    alignment = control.get("alignment_supported") if "negative_control" in resource["checks"] else True
    failed = any(value is not None and value <= 0 for value in improvements) or alignment is False
    unknown = any(value is None for value in improvements) or alignment is None
    random_mae, grouped_mae = random.get("candidate_mae"), grouped.get("candidate_mae")
    ratio = grouped_mae / random_mae if random_mae and grouped_mae is not None else None
    train_sizes = {name: [len(fold["train_records"]) for fold in by_check[name].get("folds", [])]
                   for name in ("random_cv", "group_cv") if name in by_check}
    return {"status": "review_ready", "claim_supported": False if failed else None if unknown else True,
            "reason": "本次固定协议的记录支持所声明比较；条件重排仅诊断本批预测对应关系。" if not failed and not unknown
                else "已保留不利或不可判断的检查，完整主张需要调整。",
            "missing_checks": [], "skipped_checks": [], "scientific_validation": False,
            "comparison": {"random_cv_mae": random_mae, "group_cv_mae": grouped_mae,
                           "group_to_random_mae_ratio": ratio, "conditional_rank": control.get("conditional_rank"),
                           "train_sizes": train_sizes, "group_count": grouped.get("group_count"),
                           "all_groups_singleton": grouped.get("group_count") == grouped.get("n") if grouped.get("n") else None}}


def resources(manager):
    result = [copy.deepcopy(RESOURCE), copy.deepcopy(RAW_RESOURCE)]
    with manager._connect(readonly=True) as con:
        for row in con.execute("SELECT record FROM requests WHERE command IN ('design_improve','design_import') ORDER BY rowid"):
            record = json.loads(row[0])
            if record["status"] == "completed" and not record.get("intent", {}).get("existing"):
                result.append(record["result"]["resource"])
    return result


def import_resource(manager, body):
    from .local_workbench import _body, _require
    from .project_design import validate_resource
    digest = _body(body, ("request_id", "resource"))
    resource = validate_resource(body["resource"])
    with manager._writer():
        with manager._connect() as con:
            old = manager._old(con, body, digest)
            if old:
                return manager._completed(old)
            existing = next((item for item in resources(manager) if (item["id"], item["version"]) == (resource["id"], resource["version"])), None)
            _require(existing is None or existing == resource, "RESOURCE_CONFLICT", "An existing resource version cannot be overwritten.")
            response = manager._response("design_import", body["request_id"], None, status="completed", resource=resource)
            manager._accept(con, body, digest, "design_import", {})
            manager._save(con, body["request_id"], {"status": "completed", "result": response, "intent": {"existing": existing is not None}})
            return response


def resolve(manager, resource_id, version):
    resource = next((item for item in resources(manager) if item["id"] == resource_id and item["version"] == version), None)
    if resource is None:
        raise ResearchError("DESIGN_NOT_FOUND", "Select an available immutable research-design version.")
    return copy.deepcopy(resource)


def view(manager):
    catalog = resources(manager)
    usage = {(item["id"], item["version"]): [] for item in catalog}
    with manager._connect(readonly=True) as con:
        active = manager._active(con)
        projects = [manager._project(con, row[0])[1] for row in con.execute("SELECT id FROM projects ORDER BY rowid")]
        completed = [row[0] for row in con.execute("SELECT id,record FROM requests WHERE command IN ('design_bind','design_improve','design_import')")
                     if json.loads(row[1])["status"] == "completed"]
    binding, checks, state = None, [], None
    snapshots = []
    for project in projects:
        saved = project.status()
        revisions = saved.get("design_revisions", [])
        by_revision = {revision["version"]: _records(project, saved, revision) for revision in revisions}
        snapshots.append((project, saved, by_revision))
        for revision in revisions:
            if revision["request_id"] not in completed:
                completed.append(revision["request_id"])
            key = (revision["resource"]["id"], revision["resource"]["version"])
            if key in usage and saved["id"] not in usage[key]:
                usage[key].append(saved["id"])
        if saved["id"] == active:
            state = saved
            binding = revisions[-1] if revisions else None
            checks = by_revision[revisions[-1]["version"]] if revisions else []
    assessment = (_assessment(binding["resource"], checks, state["source_scope"]) if binding
                  else {"status": "not_started", "claim_supported": None,
                        "reason": "先选择研究设计并声明所用字段。", "missing_checks": []})
    for resource in catalog:
        resource["usage_count"] = len(usage[(resource["id"], resource["version"])])
        resource["status"] = "candidate" if resource["parent_version"] else "available"
        resource["validation_evidence"] = []
        for project, saved, by_revision in snapshots:
            for current in saved.get("design_revisions", []):
                if (current["resource"]["id"], current["resource"]["version"]) != (resource["id"], resource["version"]):
                    continue
                actual = by_revision[current["version"]]
                assessed = _assessment(resource, actual, saved["source_scope"])
                if assessed["status"] == "review_ready":
                    resource["status"] = "validated"
                    resource["validation_evidence"].append({"project_id": saved["id"], "source_snapshot_sha256": saved["source_snapshot_sha256"],
                        "action_ids": [item["action_id"] for item in actual], "assessment": assessed})
    if any(project.status()["snapshot_ref"] != saved["snapshot_ref"] for project, saved, _ in snapshots):
        raise ResearchError("PROJECT_CHANGED", "A project changed while reading design evidence; refresh its saved view.")
    target = state["source_scope"].get("target_column") if state else None
    return {"schema_version": "research-design-catalog-v1", "project_id": active,
            "state_version": state["state_version"] if state else None, "resources": catalog,
            "binding": binding, "prediction_columns": [name for name in state["source_scope"].get("numeric_columns", []) if name != target] if state else [],
            "numeric_columns": state["source_scope"].get("numeric_columns", []) if state else [],
            "group_columns": state["source_scope"].get("group_columns", []) if state else [],
            "budget": state["budget"] if state else {},
            "target_column": target, "completed_requests": completed,
            "checks": checks, "assessment": assessment, "model_calls": 0,
            "suggested_improvement": bool(binding and checks and binding["resource"]["checks"] == ["baseline"])}


def bind(manager, body):
    from .local_workbench import _body
    from .project_design import bind as bind_project
    fields = ("request_id", "project_id", "expected_state_version", "resource_id", "resource_version", "prediction_column", "reason")
    digest = _body(body, (*fields, "training") if "training" in body else fields)
    with manager._writer():
        with manager._connect() as con:
            _, project = manager._project(con, body["project_id"], active=True)
            manager._no_pending_batch(con, body["project_id"], evidence=True)
            old = manager._old(con, body, digest)
            if old and old["status"] == "completed":
                return manager._completed(old)
            if old and old["status"] == "rejected":
                raise ResearchError(old["failure"]["code"], old["failure"]["message"])
            resource = resolve(manager, body["resource_id"], body["resource_version"])
            if old is None:
                manager._accept(con, body, digest, "design_bind", {"project_id": body["project_id"], "resource": resource})
        try:
            revision = bind_project(project, request_id=body["request_id"], expected_state_version=body["expected_state_version"],
                                    resource=resource, prediction_column=body["prediction_column"], reason=body["reason"],
                                    training=body.get("training"))
        except ResearchError as error:
            with manager._connect() as con:
                manager._save(con, body["request_id"], {"status": "rejected", "result": None,
                    "intent": {"project_id": body["project_id"]}, "failure": {"code": error.code, "message": str(error)}})
            raise
        response = manager._response("design_bind", body["request_id"], body["project_id"], status="completed", design=revision)
        with manager._connect() as con:
            manager._save(con, body["request_id"], {"status": "completed", "result": response, "intent": {"project_id": body["project_id"]}})
        return response


def improve(manager, body):
    from .local_workbench import _body, _require, _text
    digest = _body(body, ("request_id", "project_id", "expected_state_version", "reason"))
    _require(_text(body["reason"], 2000), "INVALID_REQUEST", "Record why the research design should change.")
    with manager._writer():
        with manager._connect() as con:
            old = manager._old(con, body, digest)
            if old:
                return manager._completed(old)
            _, project = manager._project(con, body["project_id"], active=True)
            manager._no_pending_batch(con, body["project_id"], evidence=True)
        with project._writer():
            state = project.status()
            project._require_fresh(state, state, body["expected_state_version"])
            binding = (state.get("design_revisions") or [None])[-1]
            records = _records(project, state)
            _require(binding is not None and records, "MISSING_FEEDBACK", "A bound design and actual saved verification feedback are required.")
            _require(binding["resource"]["checks"] == ["baseline"], "DESIGN_COMPLETE", "Only the initial saved-prediction design has a supported feedback-derived extension.")
            candidate = copy.deepcopy(binding["resource"])
            versions = [item["version"] for item in resources(manager) if item["id"] == candidate["id"]]
            candidate.update(version=max(versions) + 1, parent_version=candidate["version"], title="保存预测的分组与敏感性复核",
                             checks=["baseline", "grouped", "sensitivity"], change_reason=body["reason"],
                             claim="候选预测相对公平均值参考的误差优势在各声明分组及可计算的逐单位排除检查中保持。")
            candidate["sources"] = [*candidate["sources"], "反馈项目 " + state["id"] + "，行动 " + ", ".join(item["action_id"] for item in records)]
            response = manager._response("design_improve", body["request_id"], body["project_id"], status="completed", resource=candidate,
                                         feedback_action_ids=[item["action_id"] for item in records])
            with manager._connect() as con:
                manager._accept(con, body, digest, "design_improve", {"project_id": body["project_id"]})
                manager._save(con, body["request_id"], {"status": "completed", "result": response, "intent": {"project_id": body["project_id"]}})
            return response
