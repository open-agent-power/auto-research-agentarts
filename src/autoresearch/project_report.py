"""Export saved project evidence as a bounded paper, without research execution."""

import base64
from io import BytesIO
import hashlib
import json
import math
from pathlib import Path
from xml.sax.saxutils import escape

from . import paper_export, project_workbench, project_selection_view, snapshot_viewer, host_model_report, plan_readiness, prediction_summary
from .contracts import ResearchError, canonical, fingerprint
from .research_project import ResearchProject, safe_path


KINDS = {"p02.saved-oof-residuals": "p02", "materials.saved-steel-audit": "steel",
         "software.source-integrity-check": "software", "data.tabular-quality-audit": "tabular"}
TITLES = {"p02": "P02 保存预测与来源核对报告", "steel": "钢材保存模型与评价复核报告",
          "software": "软件原件捕获一致性报告", "tabular": "表格质量与分组核对报告"}


def _report_title(kind, results):
    if kind == "tabular" and any(entry["status"] == "completed"
                                 and entry["command"] in ("data.ridge-random-validation", "data.ridge-group-validation")
                                 for entry in results):
        return "原始数据划分对照与研究设计报告"
    if kind == "tabular" and any(entry["status"] == "completed"
                                 and (((entry.get("tool_result") or {}).get("result") or {}).get("analysis") or {}).get("schema_version") == "prediction-check-v1"
                                 for entry in results):
        return "保存预测验证与研究设计报告"
    if kind == "tabular" and any(entry["command"] == "data.numeric-association"
                                 and entry["status"] == "completed" and entry["tool_result"] is not None
                                 for entry in results):
        return "表格质量与数值关联报告"
    return TITLES[kind]


def _require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def _digest(raw):
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _text(value, limit=600):
    if value is None:
        return "未知"
    value = str(value).translate(paper_export._DASHES)
    value = "".join(char for char in value if ord(char) >= 32 or char in "\n\t")
    return value[:limit] + ("（节选，全文见JSON）" if len(value) > limit else "")


def _number(value):
    return f"{value:.8g}" if type(value) in (int, float) and math.isfinite(value) else "未知"


def _summary(kind, state, results):
    primary = state["registration"].get("method_id", "p02.saved-oof-residuals")
    complete = [item["tool_result"] for item in results if item["command"] == primary and item["tool_result"] is not None]
    tool = complete[-1] if complete else None
    if kind == "p02":
        method = "读取冻结四规则的已保存OOF预测，在同规则内相对化学基线诊断；残差为预测减目标，MAE单位为无量纲比值。不新增拟合，不将红通道代理认定为ALP。"
        headers = ["处理规则", "候选 MAE", "化学 MAE", "差值", "单位"]
        rows = []
        if tool:
            for policy, entry in tool["result"]["summary"]["policies"].items():
                methods = entry["methods"]
                row = methods["current_candidate"]
                rows.append([policy, _number(row["mae"]), _number(methods["chemistry"]["mae"]),
                             _number(row["delta_mae_vs_chemistry"]), "比值"])
        detail = "结果来自既存已查看数据及同section实测平坦对照；四处理规则改变目标，不能跨规则按MAE选优。材料组合及分组不是独立生物重复，数值复核不构成新发现。"
    elif kind == "steel":
        method = "对既存五个JSON模型的保存预测与原训练/验证MSE进行审计，采用原固定划分与1%采用门槛。目标为屈服强度MPa，MSE为MPa^2；不重新拟合，也不改变候选排序。"
        headers = ["方案", "degree / alpha", "训练 MSE", "验证 MSE", "原决定"]
        rows = []
        if tool:
            for index, row in enumerate(tool["result"]["trials"], 1):
                rows.append([str(index), f"{row['candidate']['degree']} / {_number(row['candidate']['alpha'])}",
                             _number(row["metrics"]["training_mse"]), _number(row["metrics"]["validation_mse"]), row["decision"]])
        detail = "表中MSE单位均为MPa^2。测试集只核对原先已选基线，不用测试集重新排名；当前固定划分不是官方Matbench成绩或跨实验室材料有效性证明。"
        if tool:
            check = tool["result"].get("baseline_only_test_check", {})
            detail += " 原基线测试MSE=" + _number(check.get("test_mse")) + " MPa^2；n=" + str(check.get("n", "未知")) + "。"
    elif kind == "tabular":
        method = "只读核对已捕获的CSV与spec原字节，按提交者声明的键、分组和数值列统计记录数、重复、缺失、非法及非有限值。不执行内容、不拟合、不改变数据或构造训练标签。"
        headers = ["核对项", "实际计数或状态"]
        rows = []
        if tool:
            profile = tool["result"]["profile"]
            rows = [["数据记录（不含表头）", profile["rows"]], ["列数", profile["columns"]],
                    ["完全重复额外记录", profile["exact_duplicate_rows"]], ["机械核对状态", profile["mechanical_status"]]]
        detail = "记录数不等于独立样本量；分组重复不自动作为错误。零值是有限数子集，不自动转为缺失，Count=0也不自动视为缺失或有效终点。字段角色、sample_unit、目标单位、来源和许可均为提交者声明；target资格仍为declared_unconfirmed，具体目标含义、单位、训练资格或领域结论仍未核验。"
    else:
        method = "把宿主选择的真实源码作为原字节数据捕获，在任务专有临时副本上做固定文件I/O检查。源码不被执行；正常读写与确定性故障注入分开记录，不调用模型或网络。"
        headers = ["检查", "类型", "结果", "实际反馈"]
        rows = []
        if tool:
            for check in tool["result"]["checks"]:
                feedback = ("跨API差异：" + ", ".join(check.get("cross_api_different_fields", []))) if check["id"] == "normal_capture" else str(check.get("actual_code") or "未拒绝")
                rows.append([check["id"], "正常I/O" if check["classification"] == "actual_normal_io" else "故障注入",
                             "符合预期" if check["passed"] else "未通过", feedback])
        detail = "五项check属于本机软件验证，单位为检查项；不使用MAE、ALP或生物终点。真实追加由读取边界hook安排时机，OS metadata未伪造；未穷尽文件系统、全部竞态或生产安全。"
    summary = {"method": method, "headers": headers, "rows": rows, "result_notice": detail,
               "has_completed_primary_result": bool(tool), "scope": state.get("source_scope", {})}
    if kind == "tabular" and tool:
        profile = tool["result"]["profile"]
        summary["numeric_headers"] = ["数值列", "有限", "零", "空串", "声明缺失", "非法", "非有限", "最小", "最大"]
        summary["numeric_rows"] = [[row["name"], *[row["counts"][key] for key in
                                   ("finite", "zero", "empty", "declared_missing", "invalid_numeric", "nonfinite")],
                                   _number(row["min"]), _number(row["max"])] for row in profile["numeric_columns"]]
        summary["group_headers"] = ["键或分组核对", "实际计数"]
        key, group = profile["key_columns"], profile["group_columns"]
        summary["group_rows"] = ([["键核对", "未声明键，未计算"]] if all(value is None for value in key.values()) else [
            ["键完整 / 不完整记录", f"{key['complete_rows']} / {key['incomplete_rows']}"],
            ["重复键额外行 / 重复组 / 冲突组", f"{key['duplicate_rows']} / {key['duplicate_groups']} / {key['conflict_groups']}"]])
        summary["group_rows"] += ([["分组核对", "未声明分组，未计算"]] if all(value is None for value in group.values()) else [
            ["分组数 / 单记录组 / 重复组", f"{group['group_count']} / {group['singletons']} / {group['repeated_groups']}"],
            ["重复组内 / 分组字段不完整记录", f"{group['rows_in_repeated_groups']} / {group['incomplete_group_rows']}"],
            ["最小 / 最大组大小", f"{_number(group['min_group_size'])} / {_number(group['max_group_size'])}"]])
        summary["quality_flags"] = profile["flags"]
        summary["duplicate_examples"] = [example for example in profile["examples"] if example["kind"] == "exact_duplicate_row"][:5]
    return summary


def collect_report(workspace) -> dict:
    """Read a stable project snapshot and verify every completed saved artifact."""
    project = ResearchProject(workspace)
    before = project.status()
    method_id = before["registration"].get("method_id", "p02.saved-oof-residuals")
    _require(method_id in KINDS, "UNSUPPORTED_REPORT", "This exporter supports the registered local report methods.")
    source_raw = snapshot_viewer._read(safe_path(project.root / "source.json"), snapshot_viewer.MAX_FILE)
    _require(hashlib.sha256(source_raw).hexdigest() == before["registration"]["source_sha256"],
             "EVIDENCE_CHANGED", "Registered report input bytes differ.")
    source_packet = snapshot_viewer._json(source_raw)
    _require(source_packet.get("snapshot_sha256") == before["source_snapshot_sha256"]
             and source_packet["snapshot_sha256"] == fingerprint({key: value for key, value in source_packet.items() if key != "snapshot_sha256"}),
             "EVIDENCE_CHANGED", "Registered report input snapshot differs.")
    source_manifest = [{"name": "source.json", "role": "registered_input", **_digest(source_raw),
                        "snapshot_sha256": source_packet["snapshot_sha256"]}]
    if KINDS[method_id] == "software":
        origin = source_packet["source"]
        source_manifest.append({"name": "embedded:" + origin["file_name"], "role": "embedded_original_code_bytes",
                                "sha256": origin["sha256"], "bytes": origin["bytes"], "license_note": origin["license_note"]})
    elif KINDS[method_id] == "steel":
        origin = source_packet["source_export"]
        source_manifest.append({"name": origin["name"], "role": "archived_origin_identity", "sha256": origin["sha256"], "bytes": origin["bytes"]})
        source_manifest.extend({"name": model["source_name"], "role": "embedded_saved_model",
                                "sha256": model["sha256"], "bytes": model["bytes"]} for model in source_packet["models"])
    elif KINDS[method_id] == "tabular":
        spec, csv_source, spec_source = source_packet["spec"], source_packet["source"], source_packet["spec_source"]
        source_manifest.extend([
            {"name": "embedded:" + spec_source["file_name"], "role": "embedded_submitted_spec_bytes",
             "sha256": spec_source["sha256"], "bytes": spec_source["bytes"]},
            {"name": "embedded:" + csv_source["file_name"], "role": "embedded_audited_csv_bytes",
             "sha256": csv_source["sha256"], "bytes": csv_source["bytes"], "url": spec["source_url"],
             "license_note": spec["license_note"], "provenance_claim": spec["provenance"],
             "notice": "These are the audited CSV input bytes; upstream origin, transformation and licence are submitter declarations, not a verified original external CSV."}])
    results, receipts, assets, source_selections = [], [], {}, []
    registered = {item["receipt_snapshot_sha256"]: dict(item) for item in before.get("evidence_sources", [])}
    for action in before["actions"] + before["evidence_actions"]:
        entry = {"action_id": action["id"], "command": action["command"], "status": action["status"],
                 "failure": action.get("failure"), "tool_result": None}
        if action["status"] == "completed":
            raw = project_workbench._artifact(project, before, action["id"])
            envelope = snapshot_viewer._json(raw)
            entry.update(envelope=envelope, tool_result=envelope["tool_result"])
            source_manifest.append({"name": action["artifact"], "role": "completed_action_artifact", **_digest(raw),
                                    "action_id": action["id"], "result_sha256": action["result_sha256"]})
            tool = envelope["tool_result"]
            source_selections.extend(tool.get("result", {}).get("selections", []))
            if action.get("input_receipt"):
                registered.setdefault(action["receipt_snapshot_sha256"], {
                    "receipt_snapshot_sha256": action["receipt_snapshot_sha256"],
                    "input_receipt": action["input_receipt"]})
        results.append(entry)
    receipt_states = []
    for receipt_sha, source_ref in registered.items():
        # Capturing an unread input for reproduction is not selection extraction.
        receipt, original_assets, relative = project._load_evidence_input(
            before, receipt_sha, input_receipt=source_ref.get("input_receipt"), task_ref=source_ref.get("task_ref"))
        receipt_raw = snapshot_viewer._read(safe_path(project.root.joinpath(*relative.split("/"))), snapshot_viewer.MAX_FILE)
        _require(snapshot_viewer._json(receipt_raw) == receipt, "EVIDENCE_CHANGED", "Receipt changed during report collection.")
        attempts = [action for action in before["evidence_actions"] if action.get("receipt_snapshot_sha256") == receipt_sha]
        read_status = ("read" if any(action["status"] == "completed" for action in attempts)
                       else attempts[-1]["status"] if attempts else "registered_unread")
        receipt_states.append({"receipt_snapshot_sha256": receipt_sha, "input_receipt": relative,
                               "task_ref": receipt["task_ref"], "read_status": read_status,
                               "source_count": len(receipt["sources"]), "selection_count": len(receipt["selections"])})
        receipts.append(receipt)
        source_manifest.append({"name": relative, "role": "captured_receipt", **_digest(receipt_raw),
                                "snapshot_sha256": receipt_sha, "read_status": read_status})
        for source in receipt["sources"]:
            digest = source["asset_sha256"]
            name = "evidence-inputs/" + receipt_sha + "/" + digest + ".bin"
            if name not in assets:
                original = original_assets[source["id"]]
                assets[name] = {"name": name, **_digest(original), "bytes_base64": base64.b64encode(original).decode("ascii")}
                source_manifest.append({"name": name, "role": "captured_original", **_digest(original), "read_status": read_status,
                                        "url": source["url"], "license_note": source["license_note"]})
    selection_history = project_selection_view.selection_view(before)
    recipe_selections = [{"request_id": parent["request_id"], "context": parent["selection_context"],
                          "decision": parent["request"]["recipe_decision"]}
                         for parent in before.get("controller_requests", [])
                         if parent.get("request", {}).get("command") == "controller.advance_recipe"]
    host_models = host_model_report.capture_host_models(project.root)
    for asset in host_models["assets"]:
        assets[asset["name"]] = {key: value for key, value in asset.items() if key != "role"}
        source_manifest.append({key: value for key, value in asset.items() if key != "bytes_base64"})
    after = project.status()
    _require(after["snapshot_ref"] == before["snapshot_ref"], "PROJECT_CHANGED", "Project changed while collecting this report.")
    _require(host_model_report.host_model_snapshot_sha256(project.root) == host_models["snapshot_sha256"],
             "PROJECT_CHANGED", "Host model evidence changed while collecting this report.")
    kind = KINDS[method_id]
    report = {"schema_version": "research-project-report-v1", "kind": kind, "title": _report_title(kind, results),
              "project_id": before["id"], "project_snapshot_ref": before["snapshot_ref"], "project": before,
              "action_results": results, "summary": _summary(kind, before, results),
              "source_selections": source_selections, "source_manifest": source_manifest, "registered_inputs": receipt_states,
              "selection_history": selection_history,
              "host_models": {key: value for key, value in host_models.items() if key != "assets"},
              "plan_reviews": plan_readiness.review_plan_requests(host_models["records"]),
              "prediction_ranges": [{"action_id": entry["action_id"], "check": analysis["check"],
                                     "summary": prediction_summary.summarize_oof_range(analysis["oof"])}
                                    for entry in results if entry["status"] == "completed"
                                    for analysis in [((entry.get("tool_result") or {}).get("result") or {}).get("analysis") or {}]
                                    if analysis.get("check") in ("random_cv", "group_cv")],
              "input": {"schema_version": "research-project-report-input-v1", "source_packet": source_packet,
                        "source_file_identity": _digest(source_raw), "receipts": receipts,
                        "receipt_states": receipt_states, "assets": list(assets.values()),
                        "researcher_feedback": before.get("researcher_feedback", []),
                        "design_revisions": before.get("design_revisions", []),
                        "recipe_selections": recipe_selections,
                        "host_models": {"snapshot_sha256": host_models["snapshot_sha256"], "status": host_models["status"],
                                        "asset_names": [asset["name"] for asset in host_models["assets"]]}},
              "exporter_code_identity": hashlib.sha256(Path(__file__).read_bytes() + Path(paper_export.__file__).read_bytes()
                                                       + Path(project_selection_view.__file__).read_bytes()
                                                       + Path(host_model_report.__file__).read_bytes()
                                                       + Path(plan_readiness.__file__).read_bytes()
                                                       + Path(prediction_summary.__file__).read_bytes()).hexdigest(),
              "scientific_validation": False,
              "notice": "A read-only export of saved results. No research execution, fit, model request or recovery is performed."}
    report["snapshot_sha256"] = fingerprint(report)
    return report


def _source_notes(report):
    notes = []
    seen = set()
    for selected in reversed(report["source_selections"]):
        source, locator = selected.get("source", {}), selected.get("locator", {})
        key = (source.get("sha256"), canonical(locator))
        if key in seen:
            continue
        seen.add(key)
        claim = selected.get("submitted_claim", {})
        claim_text = claim.get("text", "") if isinstance(claim, dict) else str(claim)
        extraction = selected.get("extraction", {})
        notes.append({"id": selected.get("id", "未知"), "url": source.get("url", "未知"),
                      "sha256": source.get("sha256", "未知"), "locator": canonical(locator),
                      "license_note": source.get("license_note", "未知"),
                      "excerpt": _text(extraction.get("text", ""), 110), "claim": _text(claim_text, 150),
                      "claim_status": claim.get("status", "未记录") if isinstance(claim, dict) else "未记录"})
    return notes


def _latest_source_review_lines(report):
    for entry in reversed(report["action_results"]):
        if entry["status"] != "completed" or entry["command"] not in ("research.source-selection", "p02.source-mapping-check"):
            continue
        result = (entry.get("tool_result") or {}).get("result") or {}
        contributor = result.get("contributor") or {}
        lines = ["原行动：" + entry["action_id"],
                 "提交者记录 / 未经作者或科学确认。role：" + _text(contributor.get("role"), 100)
                 + "；label：" + _text(contributor.get("label"), 300),
                 "保存的映射状态 mapping_status：" + _text(result.get("mapping_status"), 100)
                 + "；终点资格 endpoint_eligibility：" + _text(result.get("endpoint_eligibility"), 100)]
        claims = [selected["submitted_claim"] for selected in result.get("selections", [])
                  if isinstance(selected.get("submitted_claim"), dict) and selected["submitted_claim"].get("text")]
        for index, claim in enumerate(claims[:6], 1):
            lines.append(f"提交者主张 {index}（" + _text(claim.get("status"), 100) + "）：" + _text(claim["text"], 400))
        questions = result.get("remaining_questions") or []
        lines.extend(f"未决问题 {index}：" + _text(question, 400) for index, question in enumerate(questions[:6], 1))
        if len(claims) > 6 or len(questions) > 6:
            lines.append("本段至多展示6条已保存主张和6条未决问题；其余完整记录见JSON。")
        return lines
    return []


def _budget_rows(report):
    budget = report["project"].get("budget", {})
    labels = [("lineage_ref", "原预算谱系"), ("new_model_requests", "原生本地模型请求已用"),
              ("model_requests_allowed", "原生本地模型请求上限"),
              ("model_requests_reserved", "原生本地模型请求预留"), ("new_fits", "新增模型拟合尝试"),
              ("preprocessing_fits", "预处理拟合尝试"), ("fit_limit", "累计拟合尝试上限"),
              ("fit_attempts_used", "累计拟合尝试已用"), ("fits_reserved", "拟合尝试预留"),
              ("local_tool_call_limit", "本地工具上限"),
              ("local_tool_calls_used", "本地工具已用"), ("local_tool_calls_reserved", "本地工具预留"),
              ("evidence_reads_used", "来源读取已用"), ("evidence_reads_reserved", "来源读取预留"),
              ("source_requests_used", "公开来源GET已用"), ("source_requests_reserved", "公开来源GET预留"),
              ("source_request_limit", "公开来源GET上限"),
              ("historical_spend_cny", "历史现金支出"), ("cash_settlement", "现金结算"),
              ("historical_unknowns_resolved", "历史未知是否解决"), ("existing_cash_cap_cny", "既有现金上限/元")]
    return [[label, "未知" if budget.get(key) is None else str(budget[key])] for key, label in labels]


def _host_model_rows(report):
    status = report["host_models"]["status"]
    usage, grant = status["usage"], status.get("grant") or {}
    threshold = grant.get("cli_budget_usd")
    known_cost = usage["known_cli_reported_cost_usd"]
    exceeded = "未设置" if threshold is None else ("是" if known_cost > threshold else "否")
    return [["宿主决策名额已用 / 原上限", f"{usage['decision_slots_used']} / {grant.get('decision_limit', '未设置')}"],
            ["Claude CLI启动尝试", str(usage["cli_launch_attempts"])],
            ["CLI已知报告估值 / USD", format(known_cost, ".8g")],
            ["CLI配置预算阈值 / USD", "未设置" if threshold is None else format(threshold, ".8g")],
            ["已知CLI报告估值超出配置阈值", exceeded],
            ["另有CLI费用未知", "是" if usage["cli_cost_unknown"] else "否"],
            ["子代理回答导入", str(usage["delegated_outputs_received"])],
            ["子代理内部推理次数 / 费用", "未知"],
            ["未关联宿主日志的其他外部选择", str(usage["unlinked_external_selection_count"])],
            ["其他外部历史用量", "未知，不计为零" if usage["prior_external_usage"] == "unknown_not_zero" else "未建立完整历史用量"],
            ["现金结算", "未知" if usage["cash_settlement"] == "unknown" else str(usage["cash_settlement"])]]


def _host_request_rows(report):
    rows = []
    for record in report["host_models"]["records"]:
        route = ", ".join(record.get("reported_models") or []) or "未报告"
        outcome = (record.get("outcome") or {}).get("status", "尚未提交")
        purpose = {"plan": "计划建议", "recipe": "配方改进"}.get(record.get("purpose"), "行动选择")
        if record.get("purpose") == "plan" and record["status"] == "applied":
            revision = record["outcome"]["research_plan"]
            outcome = "采用为计划第" + str(revision["version"]) + "版"
        if record.get("purpose") == "recipe" and record["status"] == "proposed":
            outcome = "候选已保存，验证与采用见外环记录"
        cost = record.get("reported_cost_usd")
        rows.append([record["request_id"] + " / " + purpose + " / " + route, record["status"] + " / " + outcome,
                     "未知" if cost is None else format(cost, ".8g")])
    return rows


PLAN_REVIEW_NOTE = ("以下条件来自各请求准备时的冻结版本，仅核对执行条件，不判读建议正文。"
                    "当前执行仍须重新检查项目；科学解释仍需审阅。摘要最多列最近3条，完整条件见report.json的plan_reviews。")


def _plan_review_rows(report):
    rows = []
    for entry in report["plan_reviews"][-3:]:
        review = entry["assessment"]
        budget = review["remaining_budget"]
        remaining = "；".join(label + " " + ("未知" if budget[key] is None else str(budget[key]))
                             for key, label in (("local_tool_calls", "本地工具"), ("evidence_reads", "来源读取"),
                                                ("estimator_fits", "估计器拟合")))
        rows.extend([[entry["request_id"], "请求准备时版本 " + str(review["state_version"])],
                     ["剩余额度（扣除预留）", remaining],
                     ["当时可执行候选", "；".join(item["method_id"] for item in review["available_actions"]) or "无，后续行动需先补条件"]])
        if review["blockers"]:
            rows.append(["整体阻塞", "；".join(item["code"] for item in review["blockers"])])
        for method in review["blocked_methods"]:
            reasons = list(method["execution_blockers"]) + list(method.get("missing_information", []))
            rows.append([method["method_id"], "；".join(reasons) or "受整体阻塞限制"])
    return rows


def _research_plan_rows(state):
    revisions = state.get("plan_revisions", [])
    if not revisions:
        return []
    current = revisions[-1]
    return [("当前版本", "第" + str(current["version"]) + "版"), ("本轮问题", current["question"]),
            ("依据与材料", current["basis"] or "尚未填写"), ("推进步骤", current["steps"]),
            ("预期反馈与调整", current["expected_feedback"]), ("本次修订理由", current["reason"]),
            ("修订记录", "\n".join("第" + str(item["version"]) + "版 · " + item["reason"] for item in revisions))]


RESEARCHER_FEEDBACK_NOTE = "以下为研究者提交的未核验意见和下一步建议。实际工具观察、计划采用与科学结论按各自证据和评审确认。"


def _researcher_feedback_rows(state):
    rows = []
    for index, item in enumerate(state.get("researcher_feedback", []), 1):
        plan = "第" + str(item["plan_version"]) + "版计划" if item["plan_version"] is not None else "尚无研究计划"
        rows.extend([("反馈 " + str(index) + " · " + item["author"], item["comment"]),
                     ("建议下一步", item["next_step"] or "尚未填写"),
                     ("关联记录", plan + "\n行动 " + (item["action_id"] or "未指定") + "\n反馈身份 " + item["id"])])
    return rows


HOST_MODEL_NOTE = ("原生本地模型计数不包含宿主CLI或子代理。CLI次数为宿主启动尝试，路由和USD估值来自CLI自报，不是账单或总推理次数；"
                   "未知不计为零。本机已观察到单次CLI超出配置预算参数，阈值用于后续发送阻断，不能保证单次发送硬上限。"
                   "行动选择请求applied表示已提交控制器，实际行动结果另列。计划建议请求applied表示采用了计划版本。"
                   "配方请求proposed表示候选已保存，已有验证输入与结果随原件附上，采用决定由外环记录。"
                   "input.json的host_models与assets保留原日志、回答及已有传输收据，缺失或未知不补造成功，也不自动重发。")


def _selection_records(report):
    return report.get("selection_history", {}).get("records", [])


_GROUP_EVENTS = (("zero", "零值"), ("empty", "空串"), ("declared_missing", "声明缺失"),
                 ("invalid_numeric", "非法数值"), ("nonfinite", "非有限"))


_ASSOCIATION_HEADERS = ["范围", "字段", "有效对", "排除", "Pearson r", "说明"]
_ASSOCIATION_NOTICE = ("仅描述本次捕获记录中字段的线性关联。每个字段与目标分别取成对有限值，"
                       "分组不完整记录仍进入全样本计算并另列。因果、预测能力和组间差异保留为待验证问题。"
                       "原件、完整组、前序检查和排除计数保留在行动JSON。")


def _association_notes(report):
    return [{"action_id": entry["action_id"], "result": entry["tool_result"]["result"]}
            for entry in report["action_results"] if entry["status"] == "completed"
            and ((entry.get("tool_result") or {}).get("result") or {}).get("schema_version") == "numeric-association-v1"][-3:]


_PREDICTION_LABELS = {"baseline": "基线比较", "grouped": "分组误差", "sensitivity": "删除敏感性",
                      "random_cv": "随机划分验证", "group_cv": "未见组验证", "negative_control": "折内重排负对照"}
_PREDICTION_HEADERS = ["检查", "有效/排除", "预测MAE", "参考MAE", "相对改善", "结论"]
_PREDICTION_NOTICE = ("比较使用显式声明的已保存预测列。参考均值排除当前样本或整个组；"
                      "预测训练、留出身份、组定义与目标量尺需依据原记录核实。完整删除单位、分组及计算明细保存在JSON。")


def _prediction_notes(report):
    notes = []
    for entry in report["action_results"]:
        analysis = ((entry.get("tool_result") or {}).get("result") or {}).get("analysis") or {}
        if entry["status"] == "completed" and analysis.get("schema_version") == "prediction-check-v1":
            notes.append({"action_id": entry["action_id"], "analysis": analysis})
    return notes[-6:]


def _design_rows(state):
    revisions = state.get("design_revisions", [])
    if not revisions:
        return []
    binding = revisions[-1]
    resource = binding["resource"]
    fields = ([["观察目标", binding["target_column"]],
               ["模型输入列", "、".join(binding["training"]["feature_columns"])],
               ["划分分组列", "、".join(binding["training"]["split_group_columns"])]] if binding.get("training") else
              [["实际值 / 保存预测列", binding["target_column"] + " / " + binding["prediction_column"]]])
    return [["研究设计", resource["title"]], ["资源与项目绑定版本", f"{resource['id']} v{resource['version']} / 绑定v{binding['version']}"],
            ["研究问题", resource["question"]], ["待检验判断", resource["claim"]],
            ["可替代解释或方法", "；".join(resource["alternatives"])],
            ["允许检查", "、".join(_PREDICTION_LABELS[check] for check in resource["checks"])],
            *fields, ["采用理由", binding["reason"]], ["版本变更依据", resource["change_reason"]]]


def _raw_validation_lines(report):
    lines = []
    values = {}
    for entry in report["action_results"]:
        analysis = ((entry.get("tool_result") or {}).get("result") or {}).get("analysis") or {}
        if entry["status"] != "completed" or analysis.get("check") not in ("random_cv", "group_cv", "negative_control"):
            continue
        check, summary = analysis["check"], analysis["summary"]
        binding = analysis["design_binding"]
        revision = binding["version"]
        label = _PREDICTION_LABELS[check]
        lines.append(label + "，项目绑定v" + str(revision) + "，资源 " + binding["resource"]["id"]
                     + " v" + str(binding["resource"]["version"]) + "，行动 " + entry["action_id"] + "，有效/排除 "
                     + str(summary["n"]) + "/" + str(summary["excluded"]) + "。")
        if check == "negative_control":
            protocol = analysis["protocol"]
            lines.append("原预测MAE " + _number(summary["original_mae"]) + "，折内重排MAE中位数 "
                + _number(summary["permutation_median"]) + "，5%—95%范围 " + _number(summary["permutation_p05"])
                + "—" + _number(summary["permutation_p95"]) + "，条件秩 " + _number(summary["conditional_rank"])
                + "，重排次数 " + str(protocol["repeats"]) + "，随机种子 " + str(protocol["seed"]) + "。")
            lines.append("重排保持已保存评价折，仅诊断本批预测与样本对应；此条件秩不证明总体显著性或未见数据泛化。")
        else:
            values.setdefault(revision, {})[check] = summary
            improvement = summary.get("improvement")
            lines.append("预测MAE " + _number(summary["candidate_mae"]) + "，训练折均值参考MAE "
                + _number(summary["reference_mae"]) + "，相对改善 "
                + (_number(improvement * 100) + "%" if improvement is not None else "未知") + "。")
            lines.append("每个训练折分别拟合StandardScaler与Ridge(alpha=1)，评价折不参与拟合；完整行号、折分配、模型系数保存在JSON。")
            prediction_range = prediction_summary.summarize_oof_range(analysis["oof"])
            if prediction_range is not None:
                lines.append("保存预测范围 " + _number(prediction_range["predicted_min"]) + "—" + _number(prediction_range["predicted_max"])
                    + "，原目标范围 " + _number(prediction_range["observed_min"]) + "—" + _number(prediction_range["observed_max"])
                    + "；负预测 " + str(prediction_range["negative_predictions"]) + "/" + str(prediction_range["n"])
                    + "，低于/高于本次观察范围 " + str(prediction_range["below_observed_min"]) + "/" + str(prediction_range["above_observed_max"]) + "。")
                lines.append("范围描述用于复核保存预测，适用约束按课题判断。")
            sizes = [len(fold["train_records"]) for fold in analysis.get("folds", [])]
            if sizes:
                lines.append("各折训练样本数 " + "、".join(map(str, sizes)) + "。两种划分的样本量与组分布可能同时变化，误差差异不能单独归因于分组。")
            if check == "group_cv" and summary.get("group_count") == summary.get("n"):
                lines.append("当前声明组均为单条记录，未检验组内重复跨折导致的偏差。")
    for revision, checks in values.items():
        random, grouped = checks.get("random_cv", {}), checks.get("group_cv", {})
        if random.get("candidate_mae") and grouped.get("candidate_mae") is not None:
            lines.append("项目绑定v" + str(revision) + "未见组/随机划分MAE比 " + _number(grouped["candidate_mae"] / random["candidate_mae"])
                         + "；该比值依赖该绑定的声明字段和组含义，解释须结合研究问题。")
    return lines


def _prediction_rows(notes):
    rows = []
    for note in notes:
        analysis = note["analysis"]
        summary = analysis["summary"]
        decision = summary["outperforms_reference"]
        conclusion = "较参考降低MAE" if decision is True else "未低于参考MAE" if decision is False else "暂不可计算"
        if analysis["check"] == "sensitivity" and analysis["details"].get("conclusion_reversed") is True:
            conclusion = "删除单位后结论反转"
        if analysis["check"] == "grouped" and any(group.get("outperforms_reference") is False
                                                  for group in analysis["details"].get("groups", [])):
            conclusion = "部分组未降低MAE"
        improvement = summary["improvement"]
        label = _PREDICTION_LABELS[analysis["check"]] + " · 绑定v" + str(analysis["design_binding"]["version"])
        rows.append([label, f"{summary['n']} / {summary['excluded']}", _number(summary["candidate_mae"]),
                     _number(summary["reference_mae"]), _number(improvement * 100) + "%" if improvement is not None else "未知", conclusion])
    return rows


def _prediction_detail_lines(note):
    analysis = note["analysis"]
    binding = analysis["design_binding"]
    lines = ["行动 " + note["action_id"] + "，资源 " + binding["resource"]["id"] + " v" + str(binding["resource"]["version"])
             + "，项目绑定v" + str(binding["version"]) + "，预测列 " + binding["prediction_column"] + "。"]
    if analysis["check"] == "sensitivity":
        reversal = analysis["details"].get("conclusion_reversed")
        lines.append("删除后改善结论反转情况为" + ("已观察到反转" if reversal is True else "未观察到反转" if reversal is False else "尚不能计算") + "。")
        most = analysis["details"].get("most_influential")
        if most is not None:
            change = most.get("improvement")
            lines.append("影响最大的删除单位为 " + canonical(most["unit"]) + "，删除记录数 " + str(most["removed_n"])
                         + "，剩余预测MAE " + _number(most["candidate_mae"]) + "，参考MAE " + _number(most["reference_mae"])
                         + "，相对改善 " + (_number(change * 100) + "%" if change is not None else "未知") + "。")
    if analysis["check"] == "grouped" and analysis["details"].get("worst_group"):
        worst = analysis["details"]["worst_group"]
        change = worst.get("improvement")
        lines.append("保存预测误差最大的组为 " + canonical(worst["group"]) + "，预测MAE " + _number(worst["candidate_mae"])
                     + "，参考MAE " + _number(worst["reference_mae"])
                     + "，相对改善 " + (_number(change * 100) + "%" if change is not None else "未知") + "。")
    return lines


def _association_rows(result):
    reasons = {"insufficient_pairs": "有效对少于3", "constant_target": "目标为常量",
               "constant_predictor": "字段为常量", "constant_both": "目标与字段均为常量"}
    scopes = [("全样本", result["overall"])]
    for index, group in enumerate(result["groups"][:8], 1):
        coordinate = group["first_coordinate"]
        scopes.append(("组" + str(index) + " · 起始记录" + str(coordinate["logical_record"]), group["associations"]))
    if result["incomplete_group"]["rows"]:
        scopes.append(("分组不完整", result["incomplete_group"]["associations"]))
    rows = []
    for label, pairs in scopes:
        for pair in pairs[:8]:
            value = pair["pearson_r"]
            if value is None:
                explanation = reasons.get(pair["reason"], "未计算")
            elif value == 0:
                explanation = "线性相关为0"
            else:
                explanation = "正向关联" if value > 0 else "负向关联"
            rows.append([label, pair["predictor"], pair["n"], pair["excluded"], _number(value),
                         explanation])
    return rows


def _grouped_quality_notes(report):
    notes = []
    for entry in report["action_results"]:
        tool = entry.get("tool_result") or {}
        result = tool.get("result") or {}
        if result.get("schema_version") == "grouped-quality-profile-v1":
            notes.append({"action_id": entry["action_id"], "summary": result["summary"], "scope": result["scope"],
                          "predecessor": result["predecessor"], "examples": result["examples"]})
    return notes[-3:]


def _grouped_quality_rows(summary, limit):
    rows = []
    for column in summary["numeric_columns"][:limit]:
        rows.append([column["name"], *[f"{column['concentration'][kind]['total']} / {column['concentration'][kind]['affected_groups']}"
                                      for kind, _ in _GROUP_EVENTS]])
    return rows


def _grouped_quality_locations(note):
    return "；".join(str(item["column"]) + " / " + dict(_GROUP_EVENTS).get(item["kind"], str(item["kind"]))
                     + "，逻辑记录 " + str(item["logical_record"]) + " / 结束物理行 " + str(item["physical_line_end"])
                     + "，组 " + (str(item["group_id"])[:12] if item["group_id"] is not None else "分组不完整")
                     for item in note["examples"][:5]) or "无所选事件代表；不据此批准字段或目标资格。"


_WORKBOOK_HEADERS = ["候选工作表", "精确/比较格", "非精确（文本异/不符）", "公式格", "工作簿缺/多行", "完全一致候选"]
_WORKBOOK_NOTICE = ("摘要最多6张工作表。精确匹配、数值相等但文本不同、不符三类互斥；非精确为后两类之和。"
                    "公式只读取保存缓存，不求值。多个完全一致候选保留歧义；唯一候选也不证明作者实际转换、运行或ALP身份。"
                    "完整候选、前序身份与例子保留在行动JSON，未改写原值或批准科学资格。")


def _workbook_projection_notes(report):
    notes = []
    for entry in report["action_results"]:
        result = (entry.get("tool_result") or {}).get("result") or {}
        if result.get("schema_version") == "workbook-projection-check-v1":
            notes.append({"action_id": entry["action_id"], "result": result})
    return notes[-3:]


def _workbook_projection_summary(result):
    summary = result["summary"]
    names = "、".join(_text(name, 60) for name in summary["exact_candidate_sheets"][:6]) or "无"
    return (f"CSV {summary['csv_rows']}行、{summary['csv_columns']}列；候选工作表{summary['candidate_sheet_count']}张，"
            f"完全一致候选{summary['exact_candidate_sheet_count']}张。候选名称（最多6张）：" + names + "。")


def _workbook_projection_rows(result):
    return [[candidate["sheet"], f"{candidate['exact_matches']} / {candidate['compared_cells']}",
             f"{candidate['non_exact_cells']}（{candidate['numeric_equal_text_diff']} / {candidate['mismatch_cells']}）",
             candidate["formula_cells"], f"{len(candidate['missing_workbook_rows'])} / {len(candidate['extra_workbook_rows'])}",
             "是" if candidate["projection_candidate_exact"] else "否"] for candidate in result["candidates"][:6]]


def _workbook_projection_locations(result):
    locations = []
    for candidate in result["candidates"][:6]:
        for item in candidate["examples"]:
            comparison = "数值同、文本异" if item["comparison"] == "numeric_equal_text_diff" else "不符"
            locations.append(_text(candidate["sheet"], 60) + "!" + item["cell"] + "，逻辑记录 "
                             + str(item["logical_record"]) + " / 结束物理行 " + str(item["physical_line_end"]) + "，" + comparison)
            if len(locations) == 5:
                return "；".join(locations)
    return "；".join(locations) or "无非精确格代表；不据此确认作者实际转换或运行。"


def _duplicate_locations(summary):
    examples = summary.get("duplicate_examples", [])
    if not examples:
        return None
    locations = "；".join(f"逻辑记录 {item['logical_record']}/{item['first_logical_record']}，结束物理行 {item['physical_line_end']}/{item['first_physical_line_end']}"
                         for item in examples[:5])
    return ("重复代表定位（至多5例，后记录/首次记录）：" + locations
            + "。逻辑记录从1起且不含表头；物理行是该CSV记录的结束行号，包含表头及带引号换行。原记录未删除或改写。")


def _selection_provider(record):
    recipe = record.get("recipe_decision")
    if recipe is not None:
        return "确定性科研配方（无模型）：" + _text(recipe["recipe_id"], 100) + " v" + str(recipe["recipe_version"])
    claim = record["provider_claim"]
    names = {"operator_assistant": "操作者助手", "human": "人", "external_model": "外部模型"}
    return names.get(claim.get("kind"), "未知来源") + "（仅声明，未核验）：" + _text(claim.get("label"), 100)


def _selection_recipe_notes(record):
    decision = record.get("recipe_decision")
    if decision is None:
        return []
    reasons = {"FIRST_MATCHING_HOST_CANDIDATE": "首个匹配宿主候选", "LOWER_RECIPE_PRIORITY": "位于已选方法之后",
               "NO_MATCHING_HOST_CANDIDATE": "当前无匹配候选", "HOST_BLOCKERS": "宿主条件阻断",
               "SCOPE_MISMATCH": "领域或契约不匹配", "NEED_MISMATCH": "当前需求不匹配"}
    order = " → ".join(_selection_action(method["method_id"], {}) for method in decision["recipe"]["ordered_methods"])
    choices = "；".join(_selection_action(item["method_id"], {}) + "："
                        + ("选用，" if item["outcome"] == "selected" else "跳过，") + reasons.get(item["reason"], item["reason"])
                        for item in decision["method_decisions"])
    return ["配方顺序：" + order, "配方取舍：" + choices,
            "确定性编译，不调用模型；完整配方、当时context及全部候选取舍见input.json.recipe_selections。"]


def _selection_status(value):
    return {"prepared": "已保存选择", "running": "执行中", "waiting": "等待", "completed": "已完成",
            "failed": "失败", "unknown": "未知", "needs_review": "待核对", "active": "可继续"}.get(value, value)


def _selection_action(method, parameters):
    names = {"p02.saved-oof-residuals": "保存OOF诊断", "materials.saved-steel-audit": "钢材保存模型审计",
             "software.source-integrity-check": "原件捕获检查", "research.source-selection": "来源读取",
             "p02.source-mapping-check": "来源读取", "data.tabular-quality-audit": "表格质量审计"}
    names["data.grouped-quality-profile"] = "分组质量画像"
    names["data.workbook-projection-check"] = "工作簿候选投影核对"
    label = names.get(method, method or "未指定方法")
    if parameters.get("receipt_snapshot_sha256"):
        label += "，收据 " + parameters["receipt_snapshot_sha256"][:12]
    elif parameters.get("dimension"):
        label += "，分组 " + parameters["dimension"]
    return label


def _selection_baseline(record):
    baseline = record.get("baseline_decision") or {}
    action = baseline.get("next_action") or {}
    return _selection_action(action["method_id"], action.get("parameters", {})) if action.get("method_id") else _text(baseline.get("reason", "未指定可执行候选"), 120)


def _selection_child(record):
    child = record.get("child")
    if record["decision_kind"] == "external_wait":
        return "本父请求等待，无子行动"
    if not child:
        return "尚无保存的子行动"
    status = _selection_status(child["status"])
    return "子行动" + status + "：" + child["id"]


def _selection_citation(hit):
    source = hit.get("source")
    source = source if isinstance(source, dict) else {"label": source}
    metadata = source.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    locator = source.get("locator") or metadata.get("locator") or hit.get("location")
    return ("引用 " + hit["citation_id"] + "；来源 " + str(source.get("url") or source.get("label") or source.get("id") or "未知")
            + "；定位 " + canonical(locator) + "；SHA " + str(source.get("sha256", "未知")))


def _markdown_table(headers, rows):
    def cell(value):
        return _text(value, 300).replace("|", "\\|").replace("\n", " ")
    return "\n".join(["| " + " | ".join(map(cell, headers)) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
                     + ["| " + " | ".join(map(cell, row)) + " |" for row in rows])


def _markdown(report):
    state, summary = report["project"], report["summary"]
    saved_decision = state.get("next_decision") or state.get("initial_decision") or {}
    next_action = {key: saved_decision[key] for key in (
        "project_status", "reason", "next_action", "method_id", "execution_status",
        "based_on_action_id", "based_on_observation_ids") if key in saved_decision}
    lines = ["# " + report["title"], "", "## 问题与摘要", "", _text(state["registration"]["goal"], 800), "",
             "本报告绑定项目快照 `" + report["project_snapshot_ref"] + "`；只读汇总保存事实，不新增研究。",
             ""]
    latest_source = _latest_source_review_lines(report)
    if latest_source:
        lines.extend(["## 最新来源核对与未决问题", ""])
        for line in latest_source:
            lines.extend([line, ""])
    plan_rows = _research_plan_rows(state)
    if plan_rows:
        lines.extend(["## 当前研究计划与修订", ""])
        for label, content in plan_rows:
            lines.extend(["### " + label, "", _text(content, 1800), ""])
    feedback_rows = _researcher_feedback_rows(state)
    if feedback_rows:
        lines.extend(["## 研究者反馈", "", RESEARCHER_FEEDBACK_NOTE, ""])
        for label, content in feedback_rows:
            lines.extend(["### " + label, "", _text(content, 6000), ""])
    design_rows = _design_rows(state)
    if design_rows:
        lines.extend(["## 当前采用的研究设计", "", _markdown_table(["设计项", "保存内容"], design_rows), ""])
    lines.extend(["## 方法与冻结评价", "", summary["method"], "", "范围：" + _text(canonical(summary["scope"]), 1200),
             "", "## 实际结果", "", _markdown_table(summary["headers"], summary["rows"]) if summary["rows"] else "没有已完成的主方法结果。", "", summary["result_notice"],
             ""])
    prediction_notes = _prediction_notes(report)
    if prediction_notes:
        lines.extend(["## 保存预测验证", "", _markdown_table(_PREDICTION_HEADERS, _prediction_rows(prediction_notes)), ""])
        for note in prediction_notes:
            lines.extend(_prediction_detail_lines(note))
            lines.append("")
        lines.extend([_PREDICTION_NOTICE, ""])
    raw_lines = _raw_validation_lines(report)
    if raw_lines:
        lines.extend(["## 原始数据划分对照", "", *[line + "\n" for line in raw_lines]])
    if summary.get("numeric_headers"):
        lines.extend(["## 数值字段计数", "", _markdown_table(summary["numeric_headers"], summary["numeric_rows"]),
                      "", "零包含在有限计数中；空串与声明缺失分别计数，最小/最大仅针对有限值。", "",
                      "## 键与分组", "", _markdown_table(summary["group_headers"], summary["group_rows"]),
                      "", "机械标记（原值，解释及资格仍待核对）：" + canonical(summary["quality_flags"]), ""])
        duplicate_locations = _duplicate_locations(summary)
        if duplicate_locations:
            lines.extend([duplicate_locations, ""])
    for note in _grouped_quality_notes(report):
        grouped = note["summary"]
        lines.extend(["## 后续方法：分组质量画像", "", "行动：" + note["action_id"] + "；前序绑定：" + canonical(note["predecessor"]),
                      "", f"原记录{grouped['rows']}；分组字段完整{grouped['complete_group_rows']}，不完整{grouped['incomplete_group_rows']}；完整组{grouped['group_count']}。",
                      "", _markdown_table(["字段", *[label + "事件 / 组" for _, label in _GROUP_EVENTS]], _grouped_quality_rows(grouped, 8)),
                      "", "表中为完整组内事件数 / 受影响组数，摘要最多8个数值列；零是有限值子集。分组不完整记录的事件另列于incomplete_group_totals，不参与完整组集中份额。",
                      "", "代表定位（最多5例）：" + _grouped_quality_locations(note),
                      "", "逻辑记录从1起且不含表头；物理行为CSV记录结束行，含表头及带引号换行。组ID为原声明分组字符串的哈希，不能当作生物或材料类别。",
                      "", "完整groups、各列集中份额/top_groups、全量计数及前序身份见本行动的JSON；未改写主方法原profile或来源记录，不推断组间独立性、目标含义或训练资格。", ""])
    for note in _association_notes(report):
        result = note["result"]
        lines.extend(["## 后续分析：数值关联", "", "目标字段 " + _text(result["target_column"], 120),
                      "", "行动 " + note["action_id"] + "，前序质量检查 " + result["predecessor"]["based_on_action_id"],
                      "", _markdown_table(_ASSOCIATION_HEADERS, _association_rows(result)),
                      "", "摘要最多8个完整组及每组8个字段，完整结果见JSON。", "", _ASSOCIATION_NOTICE, ""])
    for note in _workbook_projection_notes(report):
        result = note["result"]
        lines.extend(["## 后续方法：工作簿候选投影核对", "", "行动：" + note["action_id"] + "；前序绑定：" + canonical(result["predecessor"]),
                      "", "原件ID：" + result["origin"]["id"] + "；已捕获字节SHA：" + result["origin"]["sha256"],
                      "", _workbook_projection_summary(result), "", _markdown_table(_WORKBOOK_HEADERS, _workbook_projection_rows(result)),
                      "", "代表定位（总计最多5例）：" + _workbook_projection_locations(result), "", _WORKBOOK_NOTICE, ""])
    lines.extend(["## 来源与未决问题", ""])
    for index, source in enumerate(_source_notes(report), 1):
        lines.extend([f"{index}. 来源：{source['url']}；定位：`{source['locator']}`；SHA：`{source['sha256']}`。",
                      "   许可/访问说明：" + source["license_note"],
                      "   原文抽取节选：" + source["excerpt"], "   提交者主张（未审定；" + source["claim_status"] + "）：" + source["claim"], ""])
    if not report["source_selections"]:
        lines.append("尚无实际提取的来源选区；已登记原件保存在input.json，未读不计为研究观察或知识命中。")
    unread = sum(item["read_status"] == "registered_unread" for item in report.get("registered_inputs", []))
    if unread:
        lines.append(f"已登记未读收据：{unread}份。仅保存原件、坐标及任务身份；没有执行选区提取或FTS建索引。")
    records = _selection_records(report)
    if records:
        has_recipe = any(record.get("recipe_decision") is not None for record in records)
        provider_note = ("配方为确定性编译，不调用模型；其他提案提供方为声明，" if has_recipe else "提案提供方为声明，")
        lines.extend(["", "## 已保存的选择提案" if has_recipe else "## 已保存的外部选择", "", "以下为最近3条以内的父请求记录。" + provider_note + "宿主派发证据见下方模型记录；等待只约束该父请求，项目状态仍为 "
                      + _selection_status(state["research_status"]) + "，不表示全局暂停、方法耗尽或科学完成。", ""])
        for record in records[:3]:
            choice = "本父等待" if record["decision_kind"] == "external_wait" else _selection_action(record["method_id"], record["parameters"])
            lines.extend(["### " + record["request_id"], "", "提案来源：" + _selection_provider(record),
                          "", ("配方选择：" if record.get("recipe_decision") is not None else "外部选择：") + choice + "；父状态：" + _selection_status(record["status"]) + "；" + _selection_child(record),
                          "", "理由：" + _text(record["rationale"], 500), "", "固定建议（同一历史上下文）：" + _selection_baseline(record)])
            for note in _selection_recipe_notes(record):
                lines.extend(["", note])
            for hit in record["evidence"][:2]:
                lines.extend(["", _selection_citation(hit), "", "宿主摘录节选：" + _text(hit["quote"], 160)])
            if not record["evidence"]:
                lines.append("该提案未引用context片段。")
            lines.append("")
        lines.append("完整父请求、context、proposal及其余记录见report.json；上述固定建议没有被外部理由覆盖。")
    next_label = "固定建议（工具反馈，仍是待办，不代表执行）：" if records else "下一决定（仍是待办，不代表执行）："
    lines.extend(["", next_label, "", "```json", json.dumps(next_action, ensure_ascii=False, indent=2), "```",
                  "", "## 预算、恢复与复现边界", "", _markdown_table(["项目", "保存状态"], _budget_rows(report)), ""])
    lines.extend(["## 宿主模型用量与原请求", "", _markdown_table(["记录项", "保存值"], _host_model_rows(report)), "",
                  _markdown_table(["请求 / CLI自报路由", "请求状态 / 实际控制器结果", "报告估值USD"], _host_request_rows(report))
                  if report["host_models"]["records"] else "尚无宿主模型请求；其他外部选择的未知用量按上表单列。", "", HOST_MODEL_NOTE,
                  "", "宿主模型证据快照：`" + report["host_models"]["snapshot_sha256"] + "`。", ""])
    if report["plan_reviews"]:
        lines.extend(["## 计划执行条件", "", PLAN_REVIEW_NOTE, "",
                      _markdown_table(["记录项", "请求准备时的条件"], _plan_review_rows(report)), ""])
    incomplete = [entry for entry in report["action_results"] if entry["status"] != "completed"]
    lines.append(_markdown_table(["行动", "状态", "真实失败/未知"], [[entry["action_id"], entry["status"], canonical(entry["failure"])] for entry in incomplete]) if incomplete else "保存的行动均完成；这不等于研究问题解决或科学批准。")
    lines.extend(["", "恢复只使用原request_id和完整保存工件；unknown不自动重发，预算不通过新目录重置。数值复算、来源抽取和故障注入均按原范围解释。",
                  "", "复现入口：在匹配源码版本下，先用 `scripts/run_research_project.py status --workspace <原项目目录>` 读取。完整输入在input.json，保存工具结果在report.json；本包不是自动续算或平台运行入口。",
                  "", "核心代码身份：`" + state["code_identity"] + "`。导出器身份：`" + report["exporter_code_identity"] + "`。",
                  "", "报告不证明跨域普适性、独立科学收益、用户价值或生产安全；具体局限及原始失败保留在完整JSON。"])
    return "\n".join(lines) + "\n"


def _pdf(report):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, PageBreak, Spacer
    except ImportError:
        raise ResearchError("PDF_DEPENDENCY_REQUIRED", "Existing ReportLab reports dependencies are required.") from None
    font = paper_export._font_name()
    green, grey = colors.HexColor("#244A3B"), colors.HexColor("#5A625E")
    margin, width = 44, A4[0] - 88
    body = ParagraphStyle("PRBody", fontName=font, fontSize=9.5, leading=14.2, spaceAfter=6, wordWrap="CJK", splitLongWords=1)
    small = ParagraphStyle("PRSmall", parent=body, fontSize=8.2, leading=11.8, spaceAfter=4)
    heading = ParagraphStyle("PRHeading", parent=body, fontSize=12, leading=17, textColor=green, spaceBefore=8, spaceAfter=7, keepWithNext=True)
    title = ParagraphStyle("PRTitle", parent=body, fontSize=18, leading=25, spaceAfter=12)
    table_style = ParagraphStyle("PRCell", parent=small, spaceAfter=0)
    story = []

    def p(value, style=body, limit=700):
        return Paragraph(escape(_text(value, limit)).replace("\n", "<br/>"), style)

    def h(value):
        story.append(p(value, heading))

    def table(headers, rows, fractions):
        data = [[p(value, table_style, 240) for value in headers]]
        data += [[p(value, table_style, 240) for value in row] for row in rows]
        value = Table(data, colWidths=[width * part for part in fractions], repeatRows=1, hAlign="LEFT")
        value.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF3EF")),
                                  ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                  ("LINEBELOW", (0, 0), (-1, 0), .6, green),
                                  ("LINEBELOW", (0, 1), (-1, -1), .25, colors.HexColor("#DDE4DF")),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                                  ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        story.append(value)
        story.append(Spacer(1, 6))

    state, summary = report["project"], report["summary"]
    story.extend([p(report["title"], title), p("只读研究项目报告 | 保存事实、原始失败与未决问题", small)])
    h("一、问题与摘要")
    story.append(p(state["registration"]["goal"], limit=430))
    story.append(p("执行状态：" + str(state["execution_status"]) + "；研究状态：" + str(state["research_status"]) + "。只读导出未调用工具、模型或拟合。", small))
    latest_source = _latest_source_review_lines(report)
    if latest_source:
        h("最新来源核对与未决问题")
        for line in latest_source:
            story.append(p(line, small, 650))
    plan_rows = _research_plan_rows(state)
    if plan_rows:
        h("当前研究计划与修订")
        for label, content in plan_rows:
            story.append(p(label, small))
            story.append(p(content, limit=1800))
    feedback_rows = _researcher_feedback_rows(state)
    if feedback_rows:
        h("研究者反馈")
        story.append(p(RESEARCHER_FEEDBACK_NOTE, small))
        for label, content in feedback_rows:
            story.append(p(label, small))
            story.append(p(content, limit=6000))
    design_rows = _design_rows(state)
    if design_rows:
        h("当前采用的研究设计")
        table(["设计项", "保存内容"], design_rows, [.25, .75])
    h("二、方法与冻结评价")
    story.append(p(summary["method"], limit=500))
    h("三、实际结果")
    if summary["rows"]:
        fractions = ([.35, .15, .15, .18, .17] if report["kind"] == "p02" else [.10, .20, .23, .23, .24]
                     if report["kind"] == "steel" else [.62, .38] if report["kind"] == "tabular" else [.30, .15, .15, .40])
        table(summary["headers"], summary["rows"], fractions)
    else:
        story.append(p("没有已完成的主方法结果；失败与未知仍保留，不填造数值。"))
    story.append(p(summary["result_notice"], small, 600))
    prediction_notes = _prediction_notes(report)
    if prediction_notes:
        h("保存预测验证")
        table(_PREDICTION_HEADERS, _prediction_rows(prediction_notes), [.21, .13, .15, .15, .14, .22])
        for note in prediction_notes:
            for line in _prediction_detail_lines(note):
                story.append(p(line, small, 450))
        story.append(p(_PREDICTION_NOTICE, small, 600))
    raw_lines = _raw_validation_lines(report)
    if raw_lines:
        h("原始数据划分对照")
        for line in raw_lines:
            story.append(p(line, small, 600))
    if summary.get("numeric_headers"):
        h("数值字段计数")
        numeric_rows = [[*row[:-2], *[format(float(value), ".4g") if value != "未知" else value for value in row[-2:]]]
                        for row in summary["numeric_rows"]]
        table(summary["numeric_headers"], numeric_rows, [.22, .10, .08, .08, .12, .08, .10, .11, .11])
        story.append(p("零包含在有限计数中；空串与声明缺失分别计数；最小/最大仅针对有限值，PDF显示4位有效数字，完整值见JSON。单位与字段角色仍为声明。", small))
        h("键与分组")
        table(summary["group_headers"], summary["group_rows"], [.62, .38])
        if summary["quality_flags"]:
            story.append(p("机械标记（原值）：" + canonical(summary["quality_flags"]), small, 300))
        duplicate_locations = _duplicate_locations(summary)
        if duplicate_locations:
            story.append(p(duplicate_locations, small, 700))
    grouped_notes = _grouped_quality_notes(report)
    if grouped_notes:
        story.append(PageBreak())
        h("后续方法：分组质量画像")
        for note in grouped_notes:
            grouped = note["summary"]
            story.append(p("行动：" + note["action_id"] + "；绑定前序行动：" + note["predecessor"]["based_on_action_id"], small, 180))
            story.append(p(f"原记录{grouped['rows']}；分组字段完整{grouped['complete_group_rows']}，不完整{grouped['incomplete_group_rows']}；完整组{grouped['group_count']}。", small))
            table(["字段", *[label + "事件/组" for _, label in _GROUP_EVENTS]], _grouped_quality_rows(grouped, 6), [.25, .15, .15, .15, .15, .15])
            story.append(p("摘要最多6个数值列。表中为完整组内事件数/受影响组数；零是有限值子集，不完整组事件另存且不参与集中份额。原值保留。", small, 220))
            story.append(p("代表定位（最多5例）：" + _grouped_quality_locations(note), small, 700))
            story.append(p("逻辑记录从1起、不含表头；物理行为记录结束行，包含表头及带引号换行。组ID为声明分组的哈希，不赋予独立样本身份。", small, 220))
        story.append(p("完整groups、集中份额、前序结果SHA与原观察见JSON。此后续方法不覆盖原profile，不批准目标、单位、领域结论或训练资格。", small, 250))
    for note in _association_notes(report):
        result = note["result"]
        h("后续分析 · 数值关联")
        story.append(p("目标字段 " + _text(result["target_column"], 120)))
        story.append(p("行动 " + note["action_id"] + "，前序质量检查 "
                       + result["predecessor"]["based_on_action_id"], small, 240))
        table(_ASSOCIATION_HEADERS, _association_rows(result), [.24, .15, .10, .10, .14, .27])
        story.append(p("摘要最多8个完整组及每组8个字段，完整结果见JSON。", small))
        story.append(p(_ASSOCIATION_NOTICE, small, 650))
    projection_notes = _workbook_projection_notes(report)
    if projection_notes:
        story.append(PageBreak())
        h("后续方法：工作簿候选投影核对")
        for note in projection_notes:
            result = note["result"]
            story.append(p("行动：" + note["action_id"] + "；绑定前序行动：" + result["predecessor"]["based_on_action_id"], small, 220))
            story.append(p("原件ID：" + result["origin"]["id"] + "；已捕获字节SHA：" + result["origin"]["sha256"], small, 300))
            story.append(p(_workbook_projection_summary(result), small, 550))
            table(_WORKBOOK_HEADERS, _workbook_projection_rows(result), [.22, .15, .23, .12, .13, .15])
            story.append(p("代表定位（总计最多5例）：" + _workbook_projection_locations(result), small, 750))
            story.append(p(_WORKBOOK_NOTICE, small, 450))
    story.append(PageBreak())
    records = _selection_records(report)
    if records:
        has_recipe = any(record.get("recipe_decision") is not None for record in records)
        h("最近选择提案（已保存父请求）" if has_recipe else "最近外部选择（已保存父请求）")
        provider_note = ("配方为确定性编译，不调用模型，其他提案提供方为声明，" if has_recipe else "提案提供方为声明，")
        story.append(p("仅展示最近2条；" + provider_note + "宿主派发证据另见模型记录。等待只使本父请求无子行动，项目状态仍为 "
                       + _selection_status(state["research_status"]) + "；其余记录和完整上下文见JSON。", small, 220))
        for record in records[:2]:
            choice = "本父等待" if record["decision_kind"] == "external_wait" else _selection_action(record["method_id"], record["parameters"])
            story.append(p(record["request_id"] + " | " + _selection_provider(record), small, 180))
            story.append(p(("配方选择：" if record.get("recipe_decision") is not None else "外部选择：") + choice + "；父状态：" + _selection_status(record["status"]) + "；" + _selection_child(record), small, 180))
            story.append(p("理由：" + record["rationale"], small, 140))
            for note in _selection_recipe_notes(record):
                story.append(p(note, small, 280))
            story.append(p("固定建议（历史上下文）：" + _selection_baseline(record), small, 160))
            for hit in record["evidence"][:1]:
                story.append(p(_selection_citation(hit), small, 290))
                story.append(p("宿主摘录节选：" + hit["quote"], small, 90))
            if not record["evidence"]:
                story.append(p("该提案未引用context片段。", small))
    h("四、来源、解释与未决问题")
    sources = _source_notes(report)
    if not sources:
        story.append(p("尚无已提取来源选区。已登记的主输入和完整原字节见input.json，全部SHA在report.json/source_manifest。"))
    unread = sum(item["read_status"] == "registered_unread" for item in report.get("registered_inputs", []))
    if unread:
        story.append(p(f"另有{unread}份收据仅完成原件登记，未执行提取、未形成观察或FTS命中；其原件与任务身份仅在输入附件保留。", small))
    for index, source in enumerate(sources[:8], 1):
        story.append(p(f"来源 {index}：{source['id']} | {source['url']}", small, 230))
        story.append(p("坐标：" + source["locator"] + "；SHA：" + source["sha256"], small, 260))
        story.append(p("许可/访问：" + source["license_note"], small, 180))
        story.append(p("原文抽取节选：" + source["excerpt"], small, 150))
        story.append(p("提交者主张（未审定；" + source["claim_status"] + "）：" + source["claim"], small, 260))
    if len(sources) > 8:
        story.append(p(f"另有{len(sources) - 8}个去重展示选区未列出，全部原始选区（含重复历史主张）、坐标和原文仍保留在JSON。", small))
    h("真实失败与未知")
    incomplete = [entry for entry in report["action_results"] if entry["status"] != "completed"]
    if incomplete:
        table(["行动", "状态", "原始失败/未知"], [[entry["action_id"], entry["status"], canonical(entry["failure"])] for entry in incomplete[:5]], [.35, .16, .49])
        if len(incomplete) > 5:
            story.append(p("其余未完成行动完整保留在JSON。", small))
    else:
        story.append(p("保存行动均已完成；完成是执行状态，不代表研究目标解决、来源映射成立或候选被科学批准。", small))
    decision = state.get("next_decision") or state.get("initial_decision") or {}
    h("固定建议（工具反馈）" if records else "下一项决定")
    story.append(p(decision.get("reason", "未保存决定"), small, 350))
    story.append(p("待办：" + canonical(decision.get("next_action", decision)), small, 500))
    story.append(PageBreak())
    h("五、预算、恢复与复现边界")
    table(["预算或状态", "保存值"], _budget_rows(report), [.44, .56])
    story.append(p("unknown不会自动重发；已保存完整结果只按原请求身份恢复，不重跑工具。历史现金/请求未知保持未知，研究等待不等于预算清零。", small))
    h("宿主模型用量与原请求")
    table(["记录项", "保存值"], _host_model_rows(report), [.44, .56])
    host_rows = _host_request_rows(report)
    if host_rows:
        table(["请求 / CLI自报路由", "请求 / 控制器结果", "报告估值USD"], host_rows, [.51, .29, .20])
    else:
        story.append(p("尚无宿主模型请求；其他外部选择的未知用量按上表单列。", small))
    story.append(p(HOST_MODEL_NOTE, small))
    if report["plan_reviews"]:
        h("计划执行条件")
        story.append(p(PLAN_REVIEW_NOTE, small))
        table(["记录项", "请求准备时的条件"], _plan_review_rows(report), [.40, .60])
    h("代码与输入身份")
    for label, value in [("项目", report["project_id"]), ("项目快照", report["project_snapshot_ref"]),
                         ("核心代码", state["code_identity"]), ("导出器代码", report["exporter_code_identity"]),
                         ("宿主模型证据快照", report["host_models"]["snapshot_sha256"]),
                         ("主输入字节SHA", report["input"]["source_file_identity"]["sha256"])]:
        story.append(p(label + "：" + value, small, 160))
    h("复现与继续")
    story.append(p("匹配源码后，用 scripts/run_research_project.py status --workspace <原项目目录> 只读核对；完整输入在input.json，完整工具结果在report.json。输入不能当任意Python执行，报告包也不自动继续研究。", small, 450))
    final_boundary = ("本报告只说明所选声明列的机械核对；记录/分组不自动成为独立样本，来源和许可仍待核对。具体目标含义、单位、训练资格或领域结论仍未核验，未验证独立科研收益或真实用户价值。平台接入及新增费用授权继续沿原边界。"
                      if report["kind"] == "tabular" else
                      "本报告只说明这些保存结果及限定复核。未证明跨域普适、独立科研收益或真实用户价值；软件结果不等于全面安全或生产可靠性。平台接入及新增费用授权继续沿原边界。")
    story.append(p(final_boundary, small, 350))

    def frame(canvas, document):
        canvas.setFont(font, 8)
        canvas.setFillColor(grey)
        canvas.drawString(margin, 24, "Auto Research | 保存证据报告")
        canvas.drawRightString(A4[0] - margin, 24, str(document.page))

    buffer = BytesIO()
    SimpleDocTemplate(buffer, pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=37, bottomMargin=40,
                      title=report["title"], author="Auto Research").build(story, onFirstPage=frame, onLaterPages=frame)
    return buffer.getvalue()


def export_report(*, workspace, output) -> dict:
    project_root = safe_path(Path(workspace).absolute()).resolve()
    target = safe_path(Path(output).absolute())
    resolved = target.resolve()
    _require(not target.exists() and not resolved.is_relative_to(project_root) and not project_root.is_relative_to(resolved),
             "OUTPUT_OVERLAP", "Use a fresh report directory separate from registered sources and project assets.")
    report = collect_report(workspace)
    payloads = {"report.json": canonical(report).encode("utf-8"), "report.md": _markdown(report).encode("utf-8"),
                "report.pdf": _pdf(report), "input.json": canonical(report["input"]).encode("utf-8")}
    _require(ResearchProject(project_root).status()["snapshot_ref"] == report["project_snapshot_ref"]
             and host_model_report.host_model_snapshot_sha256(project_root) == report["host_models"]["snapshot_sha256"],
             "PROJECT_CHANGED", "Project or host model evidence changed before report publication.")
    manifest = {"schema_version": "project-report-export-v1", "project_id": report["project_id"],
                "host_model_snapshot_sha256": report["host_models"]["snapshot_sha256"],
                "project_snapshot_ref": report["project_snapshot_ref"], "files": {name: _digest(raw) for name, raw in payloads.items()},
                "source_manifest": report["source_manifest"], "scientific_validation": False}
    target.mkdir(parents=True, exist_ok=False)
    for name, raw in {**payloads, "manifest.json": canonical(manifest).encode("utf-8")}.items():
        with (target / name).open("xb") as stream:
            stream.write(raw)
    return manifest
