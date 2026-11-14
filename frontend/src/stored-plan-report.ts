/** Render stored project plans, receipts and saved report identity without actions. */
import { el, text } from "./dom";
type Obj = Record<string, unknown>;
const obj = (value: unknown): Obj => value && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const array = (value: unknown): Obj[] => Array.isArray(value) ? value.map(obj) : [];
const display = (value: unknown): string => value === null || value === undefined ? "未记录" : typeof value === "string" || typeof value === "number" ? String(value) : JSON.stringify(value);
function field(parent: HTMLElement, label: string, value: unknown): void {
  const row = el("div", "saved-study-reference"); row.append(el("strong", "", label), el("p", "", display(value))); parent.append(row);
}
function receipt(parent: HTMLElement, value: unknown, label: string): void {
  const data = obj(value), state = text(data.view_status, "not_recorded");
  if (state !== "available" && state !== "partial" && data.record_status === undefined) { parent.append(el("p", "detail-note", label + "：" + (state === "not_recorded" ? "未记录" : state))); return; }
  if (state === "partial") parent.append(el("p", "detail-note", label + "字段不完整。"));
  if (state === "integrity_error") parent.append(el("p", "detail-note", label + "与计划原值不一致；原状态如下。"));
  parent.append(el("p", "detail-note", label + " · 请求 " + display(data.request_id) + " · 原记录状态 " + display(data.record_status)
    + " · 原结果状态 " + (data.result_recorded === false ? "未记录" : data.result_present === false ? "null（原值）" : display(data.result_status))));
}
function handoff(parent: HTMLElement, value: unknown): void {
  const data = obj(value), detail = el("details"); detail.append(el("summary", "", "核对原请求与身份"),
    el("p", "detail-note", "仅供核对原 ID 与原源码 pin；这不是执行授权，也不表示当前源码可以执行旧研究。"));
  if (data.status !== "available" || data.schema_version !== "stored-original-request-handoff-v1"
      || data.scope !== "canonical_semantic_body_only_not_execution_authorization" || typeof data.canonical_semantic_json !== "string") {
    detail.append(el("p", "", "原请求无法完整核对：" + text(data.status, "未记录") + " · " + text(data.reason, "未记录")));
    parent.append(detail); return;
  }
  detail.append(el("p", "detail-note", "以下为按原保存字段重建并核对摘要的规范 JSON 语义，不代表原网络字节或字段顺序。"));
  const original = el("pre"); original.style.whiteSpace = "pre-wrap"; original.style.overflowWrap = "anywhere";
  original.textContent = data.canonical_semantic_json; detail.append(original);
  for (const [label, item] of [["工作台请求摘要", data.manager_body_sha256], ["工作台 intent 摘要", data.manager_intent_sha256],
    ["控制器请求摘要", data.controller_request_sha256], ["原项目生产代码身份", data.project_producer_code_identity],
    ["原控制器代码身份", data.controller_producer_code_identity], ["原来源快照", data.source_snapshot_sha256]] as const) field(detail, label, item);
  parent.append(detail);
}
function controller(parent: HTMLElement, value: Obj): void {
  const block = el("div", "saved-study-reference"), decision = obj(value.decision_next_action), matched = obj(value.matched_action);
  block.append(el("strong", "", "控制器原请求 " + display(value.request_id)), el("p", "", "控制器保存状态：" + display(value.status)),
    el("p", "", "选择时的提议：" + display(decision.kind) + " · 状态 " + display(decision.execution_status) + "；这是决策快照，不代表后来行动状态。"),
    el("p", "", "子请求原值：" + (value.child_binding_status === "explicit_null" ? "null（原值）" : display(value.child_request_id)) + " · 绑定状态：" + display(value.child_binding_status)));
  if (decision.method_id !== undefined) field(block, "选择时方法", decision.method_id);
  if (decision.parameters !== undefined) field(block, "选择时参数原值", decision.parameters);
  if (value.child_binding_status === "explicit_null") block.append(el("p", "detail-note", "子请求在原记录中为 null；不据此推断其他执行。"));
  if (value.child_binding_status === "not_recorded") block.append(el("p", "detail-note", "子请求字段未记录。"));
  if (value.child_binding_status === "matched") block.append(el("p", "", "按子请求匹配的项目行动：" + display(matched.id) + " · 保存状态 " + display(matched.status)));
  receipt(block, value.manager_receipt, "工作台 " + display(obj(value.manager_receipt).command) + " 收据");
  handoff(block, value.request_handoff); parent.append(block);
}
export function createStoredPlanReport(historyValue: unknown, reportValue: unknown): HTMLElement {
  const container = el("div"), history = obj(historyValue), report = obj(reportValue), plans = el("details");
  plans.append(el("summary", "", "保存的计划与控制器记录"), el("p", "detail-note", "计划、选择时提议、项目行动和工作台收据是各自保存的记录；读取不会恢复或执行。"));
  if (history.status === "partial" && Array.isArray(history.plans)) plans.append(el("p", "detail-note", "部分记录或绑定未核到：" + text(history.reason, "未提供原因")));
  if (!Array.isArray(history.plans)) plans.append(el("p", "", "计划记录未读取或未记录：" + text(history.reason, text(history.status, "未知"))));
  else if (!history.plans.length) plans.append(el("p", "", "原计划列表为空。"));
  else for (const item of array(history.plans)) {
    const revision = obj(item.revision), detail = el("details"); detail.append(el("summary", "", "保存计划版本 " + display(revision.version)),
      el("p", "detail-note", "原计划请求 " + display(revision.request_id) + " · 制定时状态版本 " + display(revision.based_on_state_version)));
    for (const [label, key] of [["问题", "question"], ["依据", "basis"], ["步骤", "steps"], ["预期反馈", "expected_feedback"], ["保存理由", "reason"]] as const) field(detail, label, revision[key]);
    receipt(detail, item.manager_receipt, "计划保存收据");
    if (!Array.isArray(item.controllers)) detail.append(el("p", "detail-note", "控制器记录未读取。"));
    else if (!item.controllers.length) detail.append(el("p", "detail-note", "没有找到完整计划上下文相同的控制器记录。"));
    else for (const parent of array(item.controllers)) controller(detail, parent);
    plans.append(detail);
  }
  if (Array.isArray(history.unmatched_controllers) && history.unmatched_controllers.length) {
    const unmatched = el("details"); unmatched.append(el("summary", "", "未匹配计划的保存控制器记录"));
    for (const parent of array(history.unmatched_controllers)) controller(unmatched, parent); plans.append(unmatched);
  }
  const savedReport = el("details"); savedReport.append(el("summary", "", "保存的报告记录"),
    el("p", "detail-note", "报告当前性未核对；仅阅读保存的 manifest 与报告元数据，不生成、刷新或下载报告。"));
  const status = text(report.status, "not_recorded");
  if (status !== "available" && !(status === "partial" && report.metadata)) savedReport.append(el("p", "", "报告元数据：" + status + " · " + text(report.reason, "未记录")));
  else {
    const metadata = obj(report.metadata); if (status === "partial") savedReport.append(el("p", "detail-note", "报告绑定不完整；原收据及字段按记录显示。"));
    savedReport.append(el("p", "", "保存标题：" + display(metadata.title)), el("p", "", "报告保存时项目状态版本：" + display(metadata.saved_project_state_version)));
    receipt(savedReport, report.export_receipt, "工作台导出收据");
    const refs = el("details"); refs.append(el("summary", "", "保存的报告身份与文件声明"));
    for (const [label, value] of [["报告槽位", report.slot], ["原项目快照", metadata.project_snapshot_ref], ["保存的报告快照 SHA-256", metadata.snapshot_sha256], ["原导出器代码身份", metadata.exporter_code_identity], ["原报告 scientific_validation", metadata.scientific_validation]] as const) field(refs, label, value);
    refs.append(el("p", "detail-note", "以下大小和 SHA 是 manifest 原声明；除 report.json 外未读取或校验这些文件。"));
    for (const [name, value] of Object.entries(obj(report.declared_files))) { const file = obj(value); field(refs, name, "大小 " + display(file.bytes) + " · SHA-256 " + display(file.sha256)); }
    savedReport.append(refs);
  }
  container.append(plans, savedReport); return container;
}
