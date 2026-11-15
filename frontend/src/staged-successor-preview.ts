/** Explicit preview of a caller-declared post-observation rule; no actions. */
import { el } from "./dom";

type Obj = Record<string, unknown>;
const obj = (value: unknown): Obj => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const validHash = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const validId = (value: unknown): value is string => typeof value === "string" && value.length > 0 && value.length <= 160;
const validVersion = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
function same(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (Array.isArray(a) || Array.isArray(b)) return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((item, index) => same(item, b[index]));
  if (a === null || b === null || typeof a !== "object" || typeof b !== "object") return false;
  const left = obj(a), right = obj(b), keys = Object.keys(left).sort(), other = Object.keys(right).sort();
  return keys.length === other.length && keys.every((key, index) => key === other[index] && same(left[key], right[key]));
}

export function createStagedSuccessorPreviewPanel(deps: {
  current(): Obj; context(): Obj | null; active(): string; preview(body: Obj): Promise<Obj>;
}): { element: HTMLElement; update(project: Obj): void; setLocked(locked: boolean): void; invalidate(): void } {
  const section = el("section", "local-panel"), title = el("h3", "", "预览后续计划的事后决策"), description = el("p", "detail-note",
    "默认等待。可明确选择观察后的规则；建议不构成事前登记、执行授权、模型采用或科学结论。预览不派发工具，但可能创建或填充本地锁文件。"),
    identity = el("p", "detail-note"), ackLabel = el("label", "local-checkbox"), ack = el("input"), ackText = el("span", "", "明确填写观察后的规则（仍需另行授权）"),
    metLabel = el("label", "local-field"), notmetLabel = el("label", "local-field"), met = el("select"), notmet = el("select"), button = el("button", "local-primary", "核对并预览"), status = el("p", "detail-note"), result = el("div"), actions = el("div", "local-actions");
  section.dataset.testid = "staged-successor-preview"; ack.type = "checkbox"; button.type = "button";
  met.setAttribute("aria-label", "条件满足后的事后建议"); notmet.setAttribute("aria-label", "条件不满足后的事后建议");
  for (const select of [met, notmet]) {
    for (const [value, label] of [["wait", "等待"], ["audit", "建议另行授权的已存结果审计"]]) {
      const option = el("option", "", label); option.value = value; select.append(option);
    }
  }
  ackLabel.append(ack, ackText); metLabel.append(el("span", "local-label", "条件满足"), met); notmetLabel.append(el("span", "local-label", "条件不满足"), notmet);
  actions.append(button); section.append(title, description, identity, ackLabel, metLabel, notmetLabel, actions, status, result);
  let locked = true, inFlight = false, generation = 0, selectedKey = "";
  function projection(): Obj | null {
    const project = deps.current(), entry = obj(project.staged_successor_plan_identity), plan = obj(obj(project.research_plan).current), ref = obj(plan.staged_feedback_ref), context = deps.context();
    if (entry.schema_version !== "staged-successor-plan-identity-v1" || entry.verification !== "state_fields_only_not_claim_sql_or_artifacts"
      || !validId(project.id) || !validId(project.run_id) || project.id !== deps.active() || entry.project_id !== project.id || entry.run_id !== project.run_id
      || !validHash(project.snapshot_ref) || entry.snapshot_ref !== project.snapshot_ref || !validVersion(project.state_version) || entry.state_version !== project.state_version
      || !validId(entry.plan_request_id) || entry.plan_request_id !== plan.request_id || !validVersion(entry.plan_version) || entry.plan_version !== plan.version
      || !validVersion(entry.original_plan_version) || entry.plan_version !== entry.original_plan_version + 1
      || ![entry.plan_sha256,entry.original_plan_sha256,entry.source_snapshot_sha256,entry.registration_sha256,entry.primary_result_sha256,entry.feedback_sha256].every(validHash)
      || ![entry.registration_request_id,entry.primary_action_id,entry.feedback_request_id].every(validId)
      || !["condition_met","condition_not_met"].includes(String(entry.feedback_outcome)) || !["wait","audit"].includes(String(entry.original_feedback_decision))
      || entry.original_plan_version !== ref.original_plan_version || entry.original_plan_sha256 !== ref.original_plan_sha256
      || entry.source_snapshot_sha256 !== ref.source_snapshot_sha256 || entry.registration_request_id !== ref.registration_request_id
      || entry.registration_sha256 !== ref.registration_sha256 || entry.primary_action_id !== ref.primary_action_id
      || entry.primary_result_sha256 !== ref.primary_result_sha256 || entry.feedback_request_id !== ref.feedback_parent_request_id
      || entry.feedback_sha256 !== ref.feedback_sha256 || entry.feedback_outcome !== ref.feedback_outcome || entry.original_feedback_decision !== ref.decision
      || !context || context.project_id !== project.id || context.run_id !== project.run_id || context.snapshot_ref !== project.snapshot_ref
      || context.state_version !== project.state_version || !validHash(context.context_sha256)) return null;
    const feedbackItems = obj(context.hypothesis_feedback).items;
    if (!Array.isArray(feedbackItems)) return null;
    const matchingFeedback = feedbackItems.map(obj).filter(item => item.request_id === entry.registration_request_id);
    if (matchingFeedback.length !== 1 || matchingFeedback[0].registration_sha256 !== entry.registration_sha256
      || matchingFeedback[0].outcome !== entry.feedback_outcome || matchingFeedback[0].action_id !== entry.primary_action_id
      || matchingFeedback[0].result_sha256 !== entry.primary_result_sha256) return null;
    return entry;
  }
  function invalidate(): void { generation++; inFlight = false; result.replaceChildren(); }
  function controls(): void {
    const entry = projection(); section.hidden = !deps.current().staged_successor_plan_identity;
    ack.disabled = locked || inFlight || !entry; met.disabled = notmet.disabled = ack.disabled || !ack.checked; button.disabled = locked || inFlight || !entry;
    if (!entry) { identity.textContent = "当前后续计划或同一项目快照不可核对；刷新后再试。"; if (!inFlight) status.textContent = "当前不发送预览请求。"; return; }
    identity.textContent = `第 ${entry.plan_version} 版计划 · 原登记 ${entry.registration_request_id} · 原反馈 ${entry.feedback_request_id} · ${entry.feedback_outcome === "condition_met" ? "条件满足" : "条件不满足"} · 原选择 ${entry.original_feedback_decision === "audit" ? "已存结果审计" : "等待"}。该身份仅为状态摘要，服务端预览另核原件。`;
    if (!inFlight && locked) status.textContent = "项目未就绪或存在未决请求；预览暂停。";
    else if (!inFlight && (!status.textContent || status.textContent === "项目未就绪或存在未决请求；预览暂停。")) status.textContent = "等待明确点击；不会调用模型或执行工具。";
  }
  const changed = (): void => { invalidate(); status.textContent = "规则已更改，请重新预览。"; controls(); };
  ack.addEventListener("change", changed); met.addEventListener("change", changed); notmet.addEventListener("change", changed);
  button.addEventListener("click", () => {
    const entry = projection(), context = deps.context(); if (!entry || !context || button.disabled) return;
    const rule: Obj | null = ack.checked ? {schema_version:"staged-feedback-preview-rule-v1", condition_met:met.value, condition_not_met:notmet.value, posthoc_acknowledged:true} : null;
    const body: Obj = {project_id:entry.project_id, snapshot_ref:entry.snapshot_ref, plan_request_id:entry.plan_request_id, plan_sha256:entry.plan_sha256};
    if (rule) body.posthoc_rule = rule;
    const expected = { ...entry }, contextSha = context.context_sha256, token = ++generation; inFlight = true; status.textContent = "正在核对原反馈与当前候选…"; result.replaceChildren(); controls();
    void deps.preview(body).then(value => {
      if (token !== generation || locked || !same(projection(), expected) || deps.context()?.context_sha256 !== contextSha) return;
      const keys = ["project_id","run_id","snapshot_ref","state_version","plan_request_id","plan_version","plan_sha256","original_plan_version","original_plan_sha256","source_snapshot_sha256","registration_request_id","registration_sha256","primary_action_id","primary_result_sha256","feedback_request_id","feedback_sha256","feedback_outcome","original_feedback_decision"];
      const candidate = obj(value.candidate), remaining = value.tool_calls_remaining, outcome = String(entry.feedback_outcome), wanted = rule ? rule[outcome] : "wait";
      const budget = obj(context.budget), limit = budget.local_tool_call_limit, used = budget.local_tool_calls_used, reserved = budget.local_tool_calls_reserved;
      if (!validVersion(limit) || !validVersion(used) || !validVersion(reserved) || used + reserved > limit || remaining !== limit - used - reserved
        || !Array.isArray(context.candidates) || !Array.isArray(context.conditions)) throw Error("当前候选或预算身份不完整。 ");
      const auditCandidates = context.candidates.map(obj).filter(item => item.method_id === "research.relevance-validation-saved-audit");
      const auditConditions = context.conditions.map(obj).filter(item => item.method_id === "research.relevance-validation-saved-audit");
      if (auditCandidates.length > 1 || auditConditions.length !== 1 || auditConditions[0].condition !== "satisfied"
        || !same(auditConditions[0].budget_cost, {local_tool_calls:1,evidence_reads:0,estimator_fits:0})) throw Error("当前审计候选或费用不完整。 ");
      const candidateValid = value.decision === "suggest_audit" && wanted === "audit" && entry.original_feedback_decision === "wait" && value.reason === "posthoc_new_authorization_required"
        && typeof remaining === "number" && Number.isSafeInteger(remaining) && remaining >= 1 && typeof candidate.id === "string" && /^choice-[a-f0-9]{32}$/.test(candidate.id)
        && auditCandidates.length === 1 && same(candidate, auditCandidates[0]) && candidate.method_id === "research.relevance-validation-saved-audit" && candidate.evaluation_ref === "staged-relevance-development-saved-audit-v1"
        && same(candidate.parameters, {based_on_action_id:entry.primary_action_id, based_on_result_sha256:entry.primary_result_sha256})
        && same(value.candidate_potential_cost, {local_tool_calls:1,evidence_reads:0,estimator_fits:0});
      const waitValid = value.decision === "wait" && value.candidate === null && value.candidate_potential_cost === null
        && ((wanted === "wait" && value.reason === "default_or_requested_wait") || (wanted === "audit" && value.reason === "tool_budget_exhausted" && remaining === 0 && entry.original_feedback_decision === "wait" && auditConditions[0].completed === false)
          || (wanted === "audit" && value.reason === "audit_already_completed" && entry.original_feedback_decision === "audit" && auditConditions[0].completed === true));
      if (value.schema_version !== "staged-feedback-plan-decision-preview-v1" || keys.some(key => value[key] !== entry[key]) || value.context_sha256 !== contextSha
        || !same(value.posthoc_rule, rule) || value.rule_scope !== "caller_declared_posthoc_not_extracted_from_plan" || value.may_execute !== false || value.scientific_validation !== false
        || value.additional_dispatches !== 0 || value.model_calls !== 0 || value.new_fits !== 0 || !validVersion(remaining) || !(candidateValid || waitValid)) throw Error("预览回执与原项目、反馈或候选身份不一致。");
      result.append(el("strong", "", value.decision === "wait" ? "建议等待" : "可建议事后审计"),
        el("p", "detail-note", value.decision === "wait" ? (value.reason === "tool_budget_exhausted" ? "工具额度不足；未执行。" : value.reason === "audit_already_completed" ? "原审计已完成；不会重复。" : "当前规则选择等待。")
          : "仅为观察后的建议；如另行授权，潜在消耗 1 次本地工具、0 次资料读取和 0 次拟合。本页不会执行。"),
        el("p", "detail-note", "认证时点快照 · " + String(entry.snapshot_ref) + " · 当前剩余工具额度 " + String(remaining)));
      status.textContent = "原反馈及候选已由服务端核对；规则由操作者在观察后提供。";
    }).catch(error => { if (token === generation) { result.replaceChildren(); status.textContent = error instanceof Error ? error.message : "预览失败；请检查原记录。"; } })
      .finally(() => { if (token === generation) { inFlight = false; controls(); } });
  });
  function update(project: Obj): void {
    const entry = obj(project.staged_successor_plan_identity), key = JSON.stringify([project.id, project.run_id, project.snapshot_ref, project.state_version, entry.plan_sha256]);
    if (key !== selectedKey) { invalidate(); selectedKey = key; ack.checked = false; met.value = notmet.value = "wait"; status.textContent = ""; }
    controls();
  }
  function setLocked(value: boolean): void { if (value && !locked) invalidate(); locked = value; controls(); }
  controls(); return { element:section, update, setLocked, invalidate };
}
