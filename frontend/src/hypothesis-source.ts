/** Show a frozen protocol's source declaration without asserting a causal link. */
import { el, text } from "./dom";
type Obj = Record<string, unknown>;
const obj = (value: unknown): Obj => value && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const labels: Record<string, string> = { old_source_commit: "原来源源码提交", old_source_project_id: "原来源项目 ID", old_source_primary_action: "原来源行动 ID", old_source_producer: "原来源生产代码身份", old_result_sha256: "原来源结果 SHA-256", source_counterevidence: "来源观察及反证原文", source_informed_rule_choices: "来源启发的规则选择次数", id: "冻结策略 ID", threshold: "冻结阈值", if_n_le_threshold: "不超过阈值时", otherwise: "高于阈值时", allowed_arm_ids: "原方法臂", controls: "原对照", candidate_changes_after_target_input_or_scores: "目标输入或评分后更改候选" };
function savedValue(value: unknown): string {
  if (value === null || value === undefined) return "未记录";
  if (typeof value === "string") return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return JSON.stringify(value);
}
function fields(value: Obj): HTMLElement {
  const list = el("dl", "saved-study-pairs");
  for (const [key, item] of Object.entries(value)) { const row = el("div"); row.append(el("dt", "", labels[key] || key), el("dd", "", savedValue(item))); list.append(row); }
  return list;
}
export function createHypothesisSource(data: unknown, project: unknown): HTMLElement {
  const source = obj(data), basis = obj(source.source_basis), policy = obj(source.policy), current = obj(project);
  const details = el("details", "saved-study-hypothesis"); details.append(el("summary", "", "假设来源与反证"),
    el("p", "detail-note", "以下是冻结协议中的假设来源声明，只作只读引用；不能据此确认因果关系或科学结论。"));
  if (source.scope !== "frozen_protocol_hypothesis_source_declaration" || !Object.keys(basis).length) {
    details.append(el("p", "", "来源声明未记录或无法确认。")); return details;
  }
  const counter = typeof basis.source_counterevidence === "string" && basis.source_counterevidence ? basis.source_counterevidence : "未记录";
  details.append(el("p", "", "来源观察及反证原文：" + counter),
    el("p", "", "来源启发的规则选择次数：" + savedValue(basis.source_informed_rule_choices) + "；冻结阈值：" + savedValue(policy.threshold) + "。"),
    el("p", "detail-note", "独立目标研究的保存结果与来源声明分开，参见上方结果；不重新计算计时。"));
  const sourceId = basis.old_source_project_id;
  if (typeof sourceId === "string" && sourceId && sourceId === current.project_id && ["available", "partial"].includes(text(current.status, "")))
    details.append(el("p", "detail-note", "当前项目 ID 与来源项目 ID 相同；这仅是记录 ID 匹配，不自动导入或关联行动，也不共享预算。"));
  const original = el("details"); original.append(el("summary", "", "查看协议原值与身份"),
    el("p", "detail-note", "协议 SHA-256：" + text(source.protocol_sha256, "未记录")), el("h3", "", "来源声明"), fields(basis),
    el("h3", "", "冻结策略"));
  if (Object.keys(policy).length) original.append(fields(policy)); else original.append(el("p", "", "冻结策略未记录。"));
  details.append(original); return details;
}
