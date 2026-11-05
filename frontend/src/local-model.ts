/** One explicit host-model decision; durable requests and execution stay on the host. */
import { el } from "./dom";

type Obj = Record<string, unknown>;
type Host = {
  read(url: string): Promise<Obj>;
  submit(command: "model-advance" | "model-resume" | "model-plan-advance" | "model-plan-adopt" | "model-plan-reject", body: Obj): Promise<Obj | null>;
  announce(message: string, error?: boolean): void;
};
const object = (value: unknown): Obj => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const objects = (value: unknown): Obj[] => Array.isArray(value) ? value.map(object) : [];
const text = (value: unknown, fallback = "未记录"): string => typeof value === "string" && value.length ? value : fallback;
const strings = (value: unknown): string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
const number = (value: unknown): string => typeof value === "number" && Number.isFinite(value) ? String(value) : "未记录";
const estimate = (value: unknown): string => typeof value === "number" && Number.isFinite(value) ? String(Number(value.toPrecision(8))) : "未记录";
const pendingStates = new Set(["prepared", "sending", "unknown", "received"]);
const resumableStates = new Set([...pendingStates, "applied"]);
const states: Record<string, string> = {
  prepared: "已准备，尚未发送", sending: "发送结果待核对", unknown: "结果未知，保留原请求", received: "已收到，尚未提交行动",
  applied: "已提交控制器", proposed: "计划建议待采用", rejected: "计划建议已拒绝", invalid: "回答无效", stale: "上下文已过期", failed: "调用失败",
};
const outcomes: Record<string, string> = { completed: "行动已完成", waiting: "已保存等待", failed: "行动失败", unknown: "行动结果未知" };

function field(label: string, control: HTMLElement): HTMLElement {
  const wrap = el("label", "local-field"); wrap.append(el("span", "local-label", label), control); return wrap;
}

export function createLocalModelPanel(host: Host): {
  element: HTMLElement; planElement: HTMLElement; refresh(projectId: string, project: Obj, context: Obj | null): Promise<void>;
  setLocked(value: boolean): void; pending(): boolean; canResume(body: Obj): boolean;
  decisionResolved(command: string, requestId: string): boolean;
} {
  const section = el("section", "local-panel local-model content-section");
  section.append(el("h2", "section-title", "模型建议与行动"),
    el("p", "detail-note", "模型可根据当前计划与实际反馈提出研究计划，或选择下一步行动。使用本机已有 Claude CLI 和当前请求额度。"));
  const status = el("p", "notice", "正在读取模型请求记录…"); status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
  const usage = el("div", "local-model-usage");
  const form = el("form", "local-model-form local-batch-form"), fields = el("fieldset", "local-fieldset");
  const purpose = el("select");
  for (const [value, label] of [["selection", "选择并执行下一步"], ["plan", "建议研究计划"]]) {
    const option = el("option", "", label); option.value = value; purpose.append(option);
  }
  const limit = el("select"); limit.required = true;
  for (let value = 1; value <= 8; value++) { const option = el("option", "", `累计最多${value}次决策`); option.value = String(value); limit.append(option); }
  const cap = el("input"); cap.type = "number"; cap.min = "0"; cap.max = "0.10"; cap.step = "any"; cap.value = "0.10"; cap.required = true;
  const reason = el("textarea"); reason.rows = 3; reason.maxLength = 1000; reason.required = true; reason.placeholder = "说明本次允许模型推进的范围与理由。";
  const thresholdNote = "单次CLI调用可能超出阈值，不能保证硬支出上限；达到阈值将阻止后续发送，现金结算仍未知。";
  const grantNote = el("p", "detail-note", "计划建议与行动选择共用决策名额和CLI配置阈值，首次提交固定范围，准备即占一次名额。" + thresholdNote);
  const grid = el("div", "local-form-grid"); grid.append(field("累计决策限额", limit), field("CLI配置阈值（USD，至多0.10）", cap));
  fields.append(grid, field("本次范围与理由", reason), grantNote);
  const start = el("button", "action-button primary", "用模型选择并执行一步"); start.type = "submit";
  form.append(field("这次请模型做什么", purpose), fields, start, el("p", "detail-note", "计划建议会保存为候选版本，由你查看依据并决定采用或拒绝。"));
  const history = el("div", "local-model-history local-batch-history"); section.append(status, usage, form, history);
  const planHistory = el("section", "local-panel local-plan-proposals content-section"); planHistory.hidden = true;
  let projectId = "", project: Obj = {}, context: Obj | null = null, view: Obj = {}, records: Obj[] = [];
  let locked = true, loading = true, loaded = false, refreshId = 0;
  const resumeButtons: { button: HTMLButtonElement; body: Obj }[] = [];
  const decisionButtons: { button: HTMLButtonElement; record: Obj; rejectReason?: HTMLTextAreaElement }[] = [];
  const rejectDrafts = new Map<string, string>();
  const grant = (): Obj => object(object(view.journal).grant);
  const pending = (): boolean => records.some(record => pendingStates.has(text(record.status, "")));
  const enabled = (): boolean => loaded && view.enabled === true && view.project_id === projectId;
  const canResume = (body: Obj): boolean => loaded && !!projectId && body.project_id === projectId
    && records.some(record => record.request_id === body.request_id && (record.purpose === "plan" && ["proposed", "applied", "rejected"].includes(text(record.status, ""))
      || enabled() && record.provider === "claude_cli" && resumableStates.has(text(record.status, ""))));
  function available(): boolean {
    if (locked || loading || !enabled() || !projectId || !context || context.project_id !== projectId
      || typeof context.state_version !== "number" || objects(context.blockers).length || purpose.value === "selection" && !objects(context.candidates).length || pending()) return false;
    const journal = object(view.journal), actualGrant = grant(), counts = object(journal.usage);
    if (counts.cli_cost_unknown === true) return false;
    if (typeof actualGrant.decision_limit === "number" && typeof counts.decision_slots_used === "number"
      && counts.decision_slots_used >= actualGrant.decision_limit) return false;
    return !(typeof actualGrant.cli_budget_usd === "number" && typeof counts.known_cli_reported_cost_usd === "number"
      && counts.known_cli_reported_cost_usd >= actualGrant.cli_budget_usd);
  }
  function controls(): void {
    const fixed = Object.keys(grant()).length > 0;
    fields.disabled = locked || loading || !enabled() || !projectId || fixed;
    purpose.disabled = locked || loading || !enabled() || !projectId || pending();
    start.textContent = purpose.value === "plan" ? "让模型建议研究计划" : "用模型选择并执行一步";
    const validCap = Number(cap.value) > 0 && Number(cap.value) <= 0.10;
    start.disabled = !available() || !validCap || !reason.value.trim();
    for (const { button, body } of resumeButtons) button.disabled = locked || loading || !canResume(body);
    for (const { button, record, rejectReason } of decisionButtons) {
      const selected = object(object(record.context).selection_context);
      button.disabled = locked || loading || record.status !== "proposed" || (rejectReason ? !rejectReason.value.trim() : selected.context_sha256 !== context?.context_sha256);
    }
  }

  function planSuggestion(record: Obj, card: HTMLElement, actions: HTMLElement): void {
    const proposal = object(record.proposal), plan = object(proposal.plan), id = text(record.request_id, "");
    if (Object.keys(plan).length) {
      card.append(el("h3", "", text(plan.question)), el("h4", "", "建议的步骤"), el("p", "", text(plan.steps)),
        el("h4", "", "预期反馈与调整"), el("p", "", text(plan.expected_feedback)),
        el("h4", "", "预计改善"), el("p", "", text(proposal.expected_improvement)),
        el("p", "detail-note", "修改理由 · " + text(proposal.reason)));
      if (plan.basis) card.append(el("p", "detail-note", "依据与材料 · " + text(plan.basis)));
      const cited = strings(proposal.feedback_action_ids);
      card.append(el("p", "detail-note", cited.length ? `引用${cited.length}条已保存执行反馈，可在实验中心和原请求中核对。` : "根据当前课题与条件制定初始计划。"));
    }
    const outcome = object(record.outcome);
    if (record.status === "applied") card.append(el("p", "notice", "已采用为研究计划第" + object(outcome.research_plan).version + "版。"));
    if (record.status === "rejected") card.append(el("p", "detail-note", "拒绝理由 · " + text(record.rejection_reason)));
    if (record.status !== "proposed") return;
    const adopt = el("button", "action-button primary", "采用此计划建议"), reject = el("button", "action-button", "拒绝此建议"), rejectReason = el("textarea");
    adopt.type = reject.type = "button"; rejectReason.rows = 2; rejectReason.maxLength = 2000; rejectReason.value = rejectDrafts.get(id) ?? "";
    adopt.addEventListener("click", () => { if (!adopt.disabled) void host.submit("model-plan-adopt", { request_id: id, project_id: projectId }); });
    reject.addEventListener("click", () => { if (!reject.disabled) void host.submit("model-plan-reject", { request_id: id, project_id: projectId, reason: rejectReason.value }); });
    rejectReason.addEventListener("input", () => { rejectDrafts.set(id, rejectReason.value); controls(); });
    const frozen = object(object(record.context).selection_context);
    if (frozen.context_sha256 !== context?.context_sha256) card.append(el("p", "notice", "项目已变化，核对当前计划后再准备新的建议。"));
    card.append(field("拒绝理由", rejectReason)); actions.append(adopt, reject);
    decisionButtons.push({ button: adopt, record }, { button: reject, record, rejectReason });
  }
  function usageText(): void {
    const journal = object(view.journal), counts = object(journal.usage);
    const threshold = grant().cli_budget_usd, known = counts.known_cli_reported_cost_usd;
    const savedNative = object(journal.native_local_model_budget), native = Object.keys(savedNative).length ? savedNative : object(project.budget);
    usage.replaceChildren(
      el("p", "detail-note", `原生本地模型：已用${number(native.new_model_requests)} / 允许${number(native.model_requests_allowed)}，预留${number(native.model_requests_reserved)}。`),
      el("p", "detail-note", Object.keys(journal).length
        ? `本项目宿主记录：决策${number(counts.decision_slots_used)}次，CLI启动尝试${number(counts.cli_launch_attempts)}次；已知报告估值${estimate(known)} USD。`
        : "本项目尚无宿主模型请求记录。"));
    if (typeof threshold === "number" && typeof known === "number" && known >= threshold) usage.append(el("p", "notice error",
      `已停止新发送：CLI报告估值${estimate(known)} USD，${known > threshold ? "已超出" : "已达到"}配置阈值${estimate(threshold)} USD。原记录仍可查看和下载。`));
    if (counts.cli_cost_unknown === true) {
      const reasons = new Set(records.filter(record => record.provider === "claude_cli" && record.cli_launch_attempted === true
        && !(typeof record.reported_cost_usd === "number" && Number.isFinite(record.reported_cost_usd)))
        .map(record => ["sending", "unknown"].includes(text(record.status, "")) ? "原CLI调用结果与费用待核对"
          : record.status === "failed" ? "调用失败，费用尚未核对"
            : record.status === "invalid" ? "回答无效，费用尚未核对" : "费用尚未核对"));
      usage.append(el("p", "notice error", "已停止新发送：" + ([...reasons].join("；") || "有CLI费用未取得可核对报告") + "。未知费用不能按0计算，保留原ID核对。"));
    }
    usage.append(el("p", "detail-note", "原生计数不包含外部CLI或子代理；CLI路由和金额以原回执自报为准，报告估值不等于现金结算。"));
    if (counts.prior_external_usage === "unknown_not_zero") usage.append(el("p", "detail-note", "还有未关联到本日志的历史外部选择，用量未知，不计为零。"));
    if (typeof counts.delegated_outputs_received === "number" && counts.delegated_outputs_received > 0)
      usage.append(el("p", "detail-note", `另有${counts.delegated_outputs_received}份子代理回答导入；内部推理次数、模型和费用未知。`));
  }
  function download(record: Obj): void {
    const url = URL.createObjectURL(new Blob([JSON.stringify(record, null, 2)], { type: "application/json;charset=utf-8" }));
    const link = el("a"); link.href = url; link.download = text(record.request_id, "model-request").replace(/[^A-Za-z0-9_.-]/g, "_") + ".json";
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function savedRequests(): void {
    resumeButtons.length = 0; decisionButtons.length = 0; history.replaceChildren(el("h3", "", "已保存的模型请求"));
    planHistory.replaceChildren(el("h2", "section-title", "模型计划建议")); planHistory.hidden = !records.some(record => record.purpose === "plan");
    if (!records.length) { history.append(el("p", "detail-note", "尚无请求。打开页面不会创建请求。")); return; }
    for (const [index, record] of [...records].reverse().entries()) {
      const isPlan = record.purpose === "plan", id = text(record.request_id, ""), card = el("details", isPlan ? "local-plan-record" : "local-model-record local-batch-record");
      card.open = isPlan ? record.status === "proposed" : index === 0;
      const label = isPlan && record.status === "applied" ? "计划建议已采用" : states[text(record.status)] ?? text(record.status);
      card.append(el("summary", "", label + " · " + id));
      const arguments_ = object(record.arguments), outcome = object(record.outcome), error = object(record.error);
      const route = strings(record.reported_models).join("、");
      card.append(el("p", "detail-note", "提供方记录 · " + (record.provider === "claude_cli" ? "Claude CLI；自报路由 " + (route || "未知") : "子代理原回答导入")));
      if (!isPlan) card.append(el("p", "detail-note", "模型解释 · " + text(arguments_.rationale, "尚无通过解析的模型解释。")));
      if (record.provider === "claude_cli") {
        const cost = record.reported_cost_usd, reported = typeof cost === "number" && Number.isFinite(cost);
        const costNote = record.cli_launch_attempted === false ? "尚未启动CLI，无费用报告。"
          : reported ? `本次CLI报告估值：${estimate(cost)} USD；${["failed", "invalid"].includes(text(record.status, "")) ? states[text(record.status)] + "也计入累计" : "已计入累计"}。`
            : "本次CLI费用尚未核对，不能按0计算。";
        card.append(el("p", "detail-note", costNote));
      }
      const choice = object(arguments_.choice);
      if (choice.kind) card.append(el("p", "detail-note", "模型选择：" + (choice.kind === "wait" ? "等待" : "执行候选 " + text(choice.candidate_id))));
      if (outcome.status && !isPlan) card.append(el("p", "notice", "控制器结果：" + (outcomes[text(outcome.status)] ?? text(outcome.status))));
      if (error.code) card.append(el("p", "notice error", "原错误：" + text(error.code) + " · " + text(error.message)));
      if (pendingStates.has(text(record.status, ""))) card.append(el("p", "detail-note", "保留原ID核对。未知请求不会重新发送模型，刷新只读已保存状态。"));
      const actions = el("div", "local-actions");
      if (isPlan) planSuggestion(record, card, actions);
      if (record.provider === "claude_cli" && resumableStates.has(text(record.status, "")) && (!isPlan || pendingStates.has(text(record.status, "")))) {
        const body = { request_id: id, project_id: projectId }, resume = el("button", "action-button", "核对原请求"); resume.type = "button";
        resume.setAttribute("aria-label", "核对原模型请求 " + id);
        resume.addEventListener("click", () => { if (!locked && !loading && canResume(body)) void host.submit("model-resume", body); });
        actions.append(resume); resumeButtons.push({ button: resume, body });
      }
      const save = el("button", "quiet-button", "下载原请求 JSON"); save.type = "button"; save.addEventListener("click", () => download(record)); actions.append(save);
      card.append(actions);
      const raw = el("details", "local-advanced"); raw.append(el("summary", "", "上下文、回答与完整记录"),
        el("pre", "project-source-text", JSON.stringify(record, null, 2))); card.append(raw); (isPlan ? planHistory : history).append(card);
    }
  }
  function statusText(): void {
    status.classList.remove("error");
    if (!projectId) status.textContent = "先创建或选择项目，再使用模型选择下一步。";
    else if (!enabled()) status.textContent = "当前可阅读模型记录、处理已保存的计划建议。新模型调用按服务启动配置启用。";
    else if (pending()) status.textContent = "有原模型请求尚未收口。请核对原请求，不能另开请求绕过。";
    else if (objects(context?.blockers).some(item => item.code === "CODE_CHANGED")) status.textContent = "原项目使用旧版执行内核，须先显式登记兼容版本后再执行；已有结果仍可阅读，额度不会自动增加。";
    else if (!context || objects(context.blockers).length) status.textContent = "当前条件阻断模型选择，请核对项目状态与所缺条件。";
    else if (!objects(context.candidates).length && purpose.value === "selection") status.textContent = "当前没有可执行候选，可核对所缺资料，或切换到研究计划建议。";
    else {
      const counts = object(object(view.journal).usage), fixed = grant();
      status.textContent = counts.cli_cost_unknown === true ? "先核对原CLI的未知用量；不会按零计费继续发送。"
        : typeof fixed.decision_limit === "number" && typeof counts.decision_slots_used === "number" && counts.decision_slots_used >= fixed.decision_limit
          ? "累计决策名额已用完，已有结果和原请求保留。"
          : typeof fixed.cli_budget_usd === "number" && typeof counts.known_cli_reported_cost_usd === "number" && counts.known_cli_reported_cost_usd >= fixed.cli_budget_usd
            ? "已达到CLI配置阈值，新发送已停止；原请求仍可核对。" : "当前有合法候选。填写范围并明确提交后，才会调用模型。";
    }
  }
  async function refresh(nextId: string, nextProject: Obj, nextContext: Obj | null): Promise<void> {
    const generation = ++refreshId;
    if (projectId !== nextId) {
      records = []; view = {}; reason.value = ""; limit.value = "1"; cap.value = "0.10"; usage.replaceChildren(); savedRequests();
    }
    projectId = nextId; project = nextProject; context = nextContext; loading = true; loaded = false;
    status.textContent = "正在读取模型请求记录…"; controls();
    try {
      const result = await host.read("/api/local-workbench/model");
      if (generation !== refreshId) return;
      if (result.schema_version !== "local-host-model-view-v1" || (result.project_id ?? "") !== projectId)
        throw Error("模型记录不属于当前项目，请只读刷新后核对。");
      view = result; records = objects(result.records); loaded = true;
      const fixed = grant();
      if (Object.keys(fixed).length) { limit.value = number(fixed.decision_limit); cap.value = number(fixed.cli_budget_usd); reason.value = text(fixed.reason, ""); }
      grantNote.textContent = "计划建议与行动选择共用原决策额度。" + (Object.keys(fixed).length ? "本项目名额、CLI阈值和范围理由已固定。" : "首次提交固定名额、CLI阈值和范围理由，准备即占一次。") + thresholdNote;
      usageText(); savedRequests(); statusText();
    } catch (error) {
      if (generation !== refreshId) return;
      status.textContent = "模型状态读取失败，请只读刷新后核对；不会重新发送请求。"; status.classList.add("error");
      host.announce(error instanceof Error ? error.message : "模型状态读取失败。", true);
    } finally { if (generation === refreshId) { loading = false; controls(); } }
  }
  form.addEventListener("submit", event => {
    event.preventDefault(); if (!available() || !form.reportValidity() || !context) return;
    const fixed = grant(), decisionLimit = Number(fixed.decision_limit ?? limit.value), cliBudget = Number(fixed.cli_budget_usd ?? cap.value), actualReason = text(fixed.reason, reason.value.trim());
    if (!Number.isInteger(decisionLimit) || decisionLimit < 1 || decisionLimit > 8 || !(cliBudget > 0 && cliBudget <= 0.10) || !actualReason.trim()) {
      host.announce("请填写1至8次累计决策、至多0.10USD的正数CLI配置阈值及范围理由。", true); return;
    }
    void host.submit(purpose.value === "plan" ? "model-plan-advance" : "model-advance", { project_id: projectId, expected_state_version: context.state_version,
      decision_limit: decisionLimit, cli_budget_usd: cliBudget, reason: actualReason });
  });
  for (const control of [limit, cap, reason]) control.addEventListener("input", controls);
  purpose.addEventListener("change", () => { controls(); statusText(); });
  controls();
  const decisionResolved = (command: string, id: string): boolean => records.some(record => record.request_id === id && record.purpose === "plan"
    && (command === "model-plan-adopt" && record.status === "applied" || command === "model-plan-reject" && record.status === "rejected"));
  return { element: section, planElement: planHistory, refresh, pending, canResume, decisionResolved, setLocked(value: boolean): void { locked = value; controls(); } };
}
