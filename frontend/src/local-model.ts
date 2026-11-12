/** One explicit host-model decision; durable requests and execution stay on the host. */
import { el } from "./dom";

type Obj = Record<string, unknown>;
type MaterialField = "groups" | "folds" | "rows";
type MaterialRequest = { action_id: string; result_sha256: string; fields: MaterialField[] };
type Host = {
  read(url: string): Promise<Obj>;
  canCheckPlanFacts(): boolean;
  checkPlanFact(body: Obj): Promise<Obj>;
  methodTitle(methodId: string): string;
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
const readinessReasons: Record<string, string> = {
  NO_UNREAD_SOURCE: "没有已登记且带选区的未读来源", BUDGET_EXHAUSTED: "相应执行额度已用尽",
  FIT_BUDGET_EXHAUSTED: "剩余拟合额度不足以执行该设计", CONDITION_NOT_SATISFIED: "方法前提尚未满足",
  ALREADY_COMPLETED: "该方法已完成", EXECUTION_UNKNOWN: "原执行结果待核对，需沿原请求处理",
  PROJECT_BUSY: "已有未完成请求，需先接续", CODE_CHANGED: "代码版本已变化，需显式登记兼容版本",
  PROJECT_WAITING: "项目仍有待核对条件", MISSING_SOURCE: "尚未登记匹配来源",
  METHOD_NOT_SUPPORTED: "该方法尚未接入执行器", EVIDENCE_CHANGED: "来源原件已变化，需先核对",
};
const factFields: Record<string, string> = { "plan.question": "本轮问题", "plan.basis": "依据与材料", "plan.steps": "建议的步骤",
  "plan.expected_feedback": "预期反馈与调整", reason: "修改理由", expected_improvement: "预计改善" };
const factMetrics: Record<string, string> = { baseline_mae: "父版本 MAE", candidate_mae: "候选 MAE", mae_change: "候选减父版本 MAE",
  relative_improvement: "相对改善比例（非百分数）", baseline_negative_predictions: "父版本负预测数量", candidate_negative_predictions: "候选负预测数量" };
const factOrders: Record<string, string> = { candidate_lower: "候选 MAE 更低", baseline_lower: "父版本 MAE 更低", equal: "两版 MAE 相同" };
const materialFields: Record<MaterialField, string> = { groups: "完整组明细", folds: "完整折明细", rows: "完整逐行明细" };
type FactDraft = { field: string; start: number; end: number; quote: string; comparison: string; kind: string; order: string; metric: string; value: string; open: boolean };

function suppliedMaterials(context: Obj): Obj[] {
  return objects(("supplied_materials" in context ? context : object(context.research_context)).supplied_materials);
}
function materialSummary(context: Obj): HTMLElement {
  const wrap = el("div", "local-supplied-materials");
  for (const material of suppliedMaterials(context)) {
    const producer = object(material.producer), source = object(material.source_ref);
    const fields = Object.entries(object(material.fields)).map(([name, value]) => `${name} ${number(object(value).count)} 条`);
    wrap.append(el("p", "", `${text(material.action_id)} · ${fields.join("；")}`),
      el("p", "detail-note", `${text(producer.method_id)} · 原设计 v${number(producer.design_version)} · 来源验证 ${text(source.action_id)}`));
    const provenance = el("details", "local-advanced");
    provenance.append(el("summary", "", "核对供应字段与原生产身份"), el("pre", "project-source-text", JSON.stringify({
      action_id: material.action_id, result_sha256: material.result_sha256, artifact_ref: material.artifact_ref,
      producer: material.producer, source_ref: material.source_ref,
      fields: Object.fromEntries(Object.entries(object(material.fields)).map(([name, value]) => [name, { path: object(value).path, count: object(value).count }])),
      coverage: material.coverage, scientific_validation: material.scientific_validation,
    }, null, 2))); wrap.append(provenance);
  }
  return wrap;
}
function recordReading(record: Obj): Obj {
  const context = object(record.context), nested = object(context.research_context);
  if (!suppliedMaterials(context).length) return record;
  const original = "supplied_materials" in context ? context : nested;
  const summary = { ...original, supplied_materials: suppliedMaterials(context).map(material => ({ ...material,
    fields: Object.fromEntries(Object.entries(object(material.fields)).map(([name, value]) => [name, { path: object(value).path, count: object(value).count }])),
  })) };
  return { ...record, context: "supplied_materials" in context ? summary : { ...context, research_context: summary },
    prompt: { ...object(record.prompt), prompt: "完整提示原文见下载的原请求 JSON。" } };
}

function factSelect(options: Record<string, string>, selected: string): HTMLSelectElement {
  const control = el("select");
  for (const [value, label] of Object.entries(options)) { const option = el("option", "", label); option.value = value; control.append(option); }
  control.value = selected; return control;
}
function factText(record: Obj, name: string): string {
  const proposal = object(record.proposal);
  return text(name.startsWith("plan.") ? object(proposal.plan)[name.slice(5)] : proposal[name], "");
}
function factRawOffset(raw: string, textareaOffset: number): number {
  // Textareas normalize CRLF and CR to LF; quote coordinates must retain the saved text.
  let source = 0, displayed = 0;
  while (source < raw.length && displayed < textareaOffset) {
    source += raw[source] === "\r" && raw[source + 1] === "\n" ? 2 : 1;
    displayed++;
  }
  return source;
}
function factComparisonLabel(comparison: Obj): string {
  const baseline = object(comparison.baseline_ref), candidate = object(comparison.candidate_ref);
  return `${text(comparison.check)} · 父v${number(baseline.resource_version)} ${text(baseline.action_id).slice(0, 15)} → 候选v${number(candidate.resource_version)} ${text(candidate.action_id).slice(0, 15)}`;
}
function factComparisonDetails(comparison: Obj, target: HTMLElement): void {
  const metrics = object(comparison.metrics);
  target.replaceChildren(el("p", "detail-note", `父版本 MAE ${number(metrics.baseline_mae)}；候选 MAE ${number(metrics.candidate_mae)}；候选减父版本 ${number(metrics.mae_change)}。`));
  const original = el("details", "local-advanced"); original.append(el("summary", "", "查看这条冻结比较的指标与行动身份"),
    el("pre", "project-source-text", JSON.stringify(comparison, null, 2))); target.append(original);
}
function factResult(result: Obj, target: HTMLElement): void {
  const labels: Record<string, string> = { supported: "所声明的判断与保存数值一致", contradicted: "所声明的判断与保存数值矛盾", undetermined: "当前证据不可核对" };
  const reasons: Record<string, string> = { matches_saved_fact: "与所选冻结比较相符。", contradicts_saved_fact: "与所选冻结比较不符，请回看原句含义和比较对象。",
    comparison_not_supplied: "这份请求没有提供所选比较。", comparison_not_comparable: "保存记录未建立两版可比性。", metric_unavailable: "保存记录没有这项可用数值。" };
  const actual = typeof result.actual === "number" && Number.isFinite(result.actual) ? String(result.actual)
    : typeof result.actual === "string" ? factOrders[result.actual] ?? result.actual : "未提供";
  target.replaceChildren(el("p", result.status === "contradicted" ? "notice error" : "notice", labels[text(result.status)] ?? "核对记录需重新读取"),
    el("p", "", "保存事实 · " + actual), el("p", "detail-note", reasons[text(result.reason_code)] ?? text(result.reason_code)),
    el("p", "detail-note", `依据原请求 ${text(result.host_request_id)} · 冻结项目版本 ${number(result.source_state_version)}。`));
  const original = el("details", "local-advanced"); original.append(el("summary", "", "查看原句位置与完整核对记录"),
    el("pre", "project-source-text", JSON.stringify(result, null, 2))); target.append(original);
}
function factFormControls(record: Obj, draft: FactDraft, comparisons: Obj[]) {
  const details = el("details", "local-advanced local-plan-fact-check"); details.open = draft.open;
  details.append(el("summary", "", "核对一条数值断言"), el("p", "detail-note", "原句对应何种判断由你指定；这里只核对所声明的判断与冻结数值，其他正文与科学解释仍需审阅。"));
  const form = el("form", "local-fact-check-form"), fields = el("fieldset", "local-fieldset");
  const fieldControl = factSelect(factFields, draft.field), source = el("textarea"); source.readOnly = true; source.rows = 6; source.value = factText(record, draft.field);
  const pick = el("button", "quiet-button", "使用所选原句"); pick.type = "button";
  const quoted = el("p", "detail-note"); quoted.setAttribute("aria-live", "polite");
  const comparison = factSelect(Object.fromEntries(comparisons.map((item, index) => [String(index), factComparisonLabel(item)])), draft.comparison);
  const comparisonDetails = el("div"), kind = factSelect({ mae_order: "MAE 高低判断", metric: "具体指标数值" }, draft.kind);
  const order = factSelect({ "": "请选择原句声明的关系", ...factOrders }, draft.order), metric = factSelect(factMetrics, draft.metric), value = el("input");
  value.type = "text"; value.inputMode = "decimal"; value.maxLength = 80; value.value = draft.value;
  const ordering = field("所声明的 MAE 高低", order), numeric = el("div", "local-form-grid");
  numeric.append(field("要核对的指标", metric), field("原句中声明的数值", value));
  const numericHint = el("p", "detail-note", "按原文的小数位核对。相对改善填比例，如0.1表示10%；负预测数量只填整数。");
  const run = el("button", "action-button primary", "核对所声明的判断"); run.type = "submit";
  const save = el("button", "quiet-button", "下载这次核对 JSON"); save.type = "button"; save.disabled = true;
  const actions = el("div", "local-actions"); actions.append(run, save);
  const result = el("div"); result.setAttribute("aria-live", "polite");
  fields.append(field("原建议字段", fieldControl), field("原建议正文（请选中一句）", source), pick, quoted,
    field("要核对的父子比较", comparison), comparisonDetails, field("断言类型", kind), ordering, numeric, numericHint);
  form.append(fields, actions, result); details.append(form);
  if (!comparisons.length) { form.hidden = true; details.append(el("p", "notice", "这份请求封存时没有提供严格父子比较，当前无法作这项核对。请继续阅读原建议与保存反馈。")); }
  return { details, form, fields, fieldControl, source, pick, quoted, comparison, comparisonDetails, kind, order, metric, value, ordering, numeric, numericHint, run, save, result };
}

function field(label: string, control: HTMLElement): HTMLElement {
  const wrap = el("label", "local-field"); wrap.append(el("span", "local-label", label), control); return wrap;
}

function platformRunRecord(run: Obj): HTMLElement {
  const tokens = (value: unknown): string => typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value.toLocaleString("zh-CN") : "未取得";
  const time = (value: unknown): string => {
    if (typeof value !== "string" || !value) return "未取得";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
  };
  const saved = el("div");
  saved.append(el("p", "", "平台调用 · " + text(run.provider, "未取得") + " · " + text(run.model, "未取得")),
    el("p", "", "开始 · " + time(run.started_at) + "；结束 · " + time(run.ended_at)),
    el("p", "", `Token · 输入${tokens(run.input_tokens)}，输出${tokens(run.output_tokens)}，合计${tokens(run.total_tokens)}`),
    el("p", "", "关联Host请求 · " + text(run.host_request_id, "未取得")),
    el("p", "", "控制台摘录 · 操作者提供，未自动核验；现金结算未核对。"));
  return saved;
}

export function createLocalModelPanel(host: Host): {
  element: HTMLElement; planElement: HTMLElement; improvementElement: HTMLElement;
  refresh(projectId: string, project: Obj, context: Obj | null): Promise<void>;
  setLocked(value: boolean, allowedRequestId?: string): void; pending(): boolean; canResume(body: Obj): boolean;
  decisionResolved(command: string, requestId: string): boolean;
  savedRecords(projectId: string): Obj[];
} {
  const section = el("section", "local-panel local-model content-section");
  section.append(el("h2", "section-title", "模型建议与行动"),
    el("p", "detail-note", "查看已保存的计划与行动建议。这里的新模型请求使用本机已有 Claude CLI 和当前请求额度。"));
  const status = el("p", "notice", "正在读取模型请求记录…"); status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
  const usage = el("div", "local-model-usage");
  const currentCosts = el("details", "local-advanced"), costContent = el("div"); currentCosts.hidden = true;
  currentCosts.append(el("summary", "", "当前方法的额度消耗"), costContent);
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
  const materials = el("details", "local-advanced local-model-materials"), materialChoices = el("div"), materialPreview = el("div");
  const materialStatus = el("p", "detail-note"); materialStatus.setAttribute("role", "status"); materialStatus.setAttribute("aria-live", "polite");
  const previewMaterials = el("button", "action-button", "预览实际供应输入"), saveInput = el("button", "quiet-button", "下载供应后的输入 JSON");
  const saveRequests = el("button", "quiet-button", "下载字段选择 JSON");
  for (const button of [previewMaterials, saveInput, saveRequests]) button.type = "button";
  const materialActions = el("div", "local-actions"); materialActions.append(previewMaterials, saveInput, saveRequests);
  materials.append(el("summary", "", "为这次计划提供保存明细（可选）"),
    el("p", "detail-note", "逐项勾选原诊断的完整字段。预览只读取保存结果，不创建模型请求，也不占决策名额。"),
    materialChoices, materialActions, materialStatus, materialPreview,
    el("p", "detail-note", "逐行字段仅含当时保存的 input_values，可能为空，不会补入原始 CSV。字段选择 JSON 可供 CLI 的 --saved-materials 使用。"));
  form.append(field("这次请模型做什么", purpose), materials, fields, start, el("p", "detail-note", "计划建议会保存为候选版本，由你查看依据并决定采用或拒绝。"));
  const history = el("div", "local-model-history local-batch-history"); section.append(status, usage, currentCosts, form, history);
  const planHistory = el("section", "local-panel local-plan-proposals content-section"); planHistory.hidden = true;
  const improvement = el("section", "local-panel local-improvement content-section"); improvement.hidden = true;
  let projectId = "", project: Obj = {}, context: Obj | null = null, view: Obj = {}, records: Obj[] = [];
  let locked = true, loading = true, loaded = false, refreshId = 0;
  let allowedRequestId = "";
  const resumeButtons: { button: HTMLButtonElement; body: Obj }[] = [];
  const decisionButtons: { button: HTMLButtonElement; record: Obj; rejectReason?: HTMLTextAreaElement }[] = [];
  const rejectDrafts = new Map<string, string>();
  const factDrafts = new Map<string, FactDraft>();
  const materialDrafts = new Map<string, MaterialRequest[]>();
  let suppliedPreview: Obj | null = null, materialRevision = 0, materialBusy = false;
  const materialRequests = (): MaterialRequest[] => materialDrafts.get(projectId) ?? [];
  const actionMethod = (action: Obj): string => text(object(object(action.method_instance).definition_ref).id, "");
  const diagnosticActions = (): Obj[] => objects(project.actions).filter(action => action.status === "completed"
    && ["data.saved-oof-random-diagnostics", "data.saved-oof-group-diagnostics"].includes(actionMethod(action))
    && typeof action.result_sha256 === "string" && objects(action.observations).some(item => item.kind === "saved_oof_diagnostic"));
  function invalidateMaterials(message = "字段选择已保留；预览时将重新核对完整输入。"): void {
    materialRevision++; materialBusy = false; suppliedPreview = null; materialPreview.replaceChildren();
    materialStatus.className = "detail-note"; materialStatus.textContent = message;
  }
  function renderMaterialChoices(): void {
    materialChoices.replaceChildren();
    const actions = diagnosticActions(), selected = materialRequests();
    if (!actions.length) materialChoices.append(el("p", "empty-state", "当前项目还没有已完成的原生保存误差诊断。"));
    for (const action of actions) {
      const observation = objects(action.observations).find(item => item.kind === "saved_oof_diagnostic") ?? {};
      const source = object(observation.source_ref), row = el("fieldset", "local-fieldset local-material-choice");
      const legend = el("legend", "local-label", host.methodTitle(actionMethod(action)) + " · " + text(action.id));
      row.append(legend, el("p", "detail-note", `原设计 v${number(source.design_version)} · 来源验证 ${text(source.action_id)} · ${number(object(observation.row_weighted).n)} 行 / ${number(object(observation.group_weighted).group_count)} 组`));
      const identity = el("details", "local-advanced"); identity.append(el("summary", "", "核对这条诊断的结果身份"),
        el("pre", "project-source-text", JSON.stringify({ action_id: action.id, result_sha256: action.result_sha256, source_ref: source }, null, 2))); row.append(identity);
      const counts = { groups: object(observation.group_weighted).group_count, folds: objects(observation.fold_errors).length, rows: object(observation.row_weighted).n };
      const options = el("div", "local-material-fields");
      for (const name of Object.keys(materialFields) as MaterialField[]) {
        const check = el("input"); check.type = "checkbox";
        check.checked = selected.some(item => item.action_id === action.id && item.result_sha256 === action.result_sha256 && item.fields.includes(name));
        const label = el("label", "local-checkbox"); label.append(check, el("span", "", `${materialFields[name]} · ${number(counts[name])} 条`));
        check.addEventListener("change", () => {
          const current = materialRequests().filter(item => item.action_id !== action.id || item.result_sha256 !== action.result_sha256);
          const previous = materialRequests().find(item => item.action_id === action.id && item.result_sha256 === action.result_sha256)?.fields ?? [];
          const chosen = (Object.keys(materialFields) as MaterialField[]).filter(field => field === name ? check.checked : previous.includes(field));
          if (chosen.length) current.push({ action_id: text(action.id), result_sha256: text(action.result_sha256), fields: chosen });
          materialDrafts.set(projectId, current); invalidateMaterials(); controls();
        }); options.append(label);
      }
      row.append(options); materialChoices.append(row);
    }
    for (const request of selected.filter(item => !actions.some(action => action.id === item.action_id && action.result_sha256 === item.result_sha256))) {
      const stale = el("div", "local-material-choice"), remove = el("button", "quiet-button", "移除此选择"); remove.type = "button";
      stale.append(el("p", "notice error", `原选择 ${request.action_id} 的结果身份已不可用，请核对后移除；不会替换成其他诊断。`),
        el("p", "detail-note", `${request.result_sha256} · ${request.fields.join("、")}`), remove);
      remove.addEventListener("click", () => { materialDrafts.set(projectId, materialRequests().filter(item => item !== request)); invalidateMaterials(); renderMaterialChoices(); controls(); });
      materialChoices.append(stale);
    }
  }
  function materialControls(): void {
    materials.hidden = purpose.value !== "plan";
    const ready = !!projectId && typeof project.snapshot_ref === "string" && !loading && materialRequests().length > 0;
    previewMaterials.disabled = !ready || materialBusy;
    previewMaterials.textContent = materialBusy ? "正在组装完整输入…" : "预览实际供应输入";
    saveInput.disabled = !suppliedPreview || materialBusy; saveRequests.disabled = !materialRequests().length;
  }
  const grant = (): Obj => object(object(view.journal).grant);
  const pending = (): boolean => records.some(record => pendingStates.has(text(record.status, "")));
  const enabled = (): boolean => loaded && view.enabled === true && view.project_id === projectId;
  const canResume = (body: Obj): boolean => loaded && !!projectId && body.project_id === projectId
    && records.some(record => record.request_id === body.request_id && (record.purpose === "plan" && ["proposed", "applied", "rejected"].includes(text(record.status, ""))
      || record.request_id === allowedRequestId && record.purpose === "plan" && record.provider === "delegated" && pendingStates.has(text(record.status, ""))
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
    purpose.disabled = loading || !projectId;
    start.textContent = purpose.value === "plan" ? "让模型建议研究计划" : "用模型选择并执行一步";
    const validCap = Number(cap.value) > 0 && Number(cap.value) <= 0.10;
    const staleMaterials = purpose.value === "plan" && materialRequests().some(request => !diagnosticActions().some(action => action.id === request.action_id && action.result_sha256 === request.result_sha256));
    start.disabled = !available() || !validCap || !reason.value.trim() || staleMaterials;
    for (const { button, body } of resumeButtons) button.disabled = locked && body.request_id !== allowedRequestId || loading || !canResume(body);
    for (const { button, record, rejectReason } of decisionButtons) {
      const selected = object(object(record.context).selection_context);
      button.disabled = locked && record.request_id !== allowedRequestId || loading || record.status !== "proposed" || (rejectReason ? !rejectReason.value.trim() : selected.context_sha256 !== context?.context_sha256);
    }
    materialControls();
  }

  function methodBudgetCosts(methods: Obj[]): HTMLElement {
    const content = el("div"), scroll = el("div", "project-table-scroll"), table = el("table", "research-design-table method-budget-table");
    const columns = el("colgroup"); for (let index = 0; index < 4; index++) columns.append(el("col")); table.append(columns);
    const head = el("thead"), titles = el("tr");
    for (const title of ["方法", "本地工具", "来源读取", "估计器拟合"]) { const cell = el("th", "", title); cell.scope = "col"; titles.append(cell); }
    head.append(titles); table.append(head);
    const category = (method: Obj): string => {
      const cost = object(method.budget_cost);
      return typeof cost.evidence_reads === "number" && cost.evidence_reads > 0 ? "来源读取"
        : cost.estimator_fits === null || typeof cost.estimator_fits === "number" && cost.estimator_fits > 0 ? "训练" : "普通检查";
    };
    for (const group of ["来源读取", "普通检查", "训练"]) {
      const members = methods.filter(method => category(method) === group); if (!members.length) continue;
      const body = el("tbody"), heading = el("tr"), label = el("th"); label.scope = "rowgroup"; label.colSpan = 4;
      label.append(el("span", "method-budget-group", group)); heading.append(label); body.append(heading);
      for (const method of members) {
        const cost = object(method.budget_cost), row = el("tr"), name = el("th", "", host.methodTitle(text(method.method_id))); name.scope = "row"; row.append(name);
        for (const key of ["local_tool_calls", "evidence_reads", "estimator_fits"]) {
          const value = cost[key], label = value === 0 ? "0 次（不消耗）"
            : key === "estimator_fits" && value === null ? "未确定，需先绑定可用设计" : number(value) + (typeof value === "number" ? " 次" : "");
          row.append(el("td", "", label));
        }
        body.append(row);
      }
      table.append(body);
    }
    scroll.append(table); content.append(el("p", "research-design-table-hint", "左右滑动查看完整额度列"), scroll); return content;
  }
  function currentMethodCosts(): void {
    costContent.replaceChildren(); currentCosts.hidden = true;
    if (!projectId || project.id !== projectId || context?.schema_version !== "project-selection-context-v1"
      || context.project_id !== projectId || typeof project.state_version !== "number" || context.state_version !== project.state_version
      || typeof project.snapshot_ref !== "string" || context.snapshot_ref !== project.snapshot_ref) return;
    const methods = objects(context.conditions).filter(method => Object.keys(object(method.budget_cost)).length);
    if (!methods.length) return;
    currentCosts.hidden = false;
    costContent.append(el("p", "detail-note", `当前项目版本${number(context.state_version)} · 每种方法单次新派发的额度需求。`), methodBudgetCosts(methods),
      el("p", "detail-note", "估计器拟合按实际 fit 次数计，Scaler 与 Ridge 的 fit 都计入。拟合次数未确定时需先绑定可用设计，不能按 0 次处理。"),
      el("p", "detail-note", "额度需求不授予执行许可，也不代表当前可执行候选；是否能行动仍由完整当前条件决定。"));
  }

  function planExecutionConditions(record: Obj, card: HTMLElement): void {
    const frozen = object(object(record.context).selection_context);
    const review = objects(view.plan_reviews).find(item => item.request_id === record.request_id);
    const assessment = object(review?.assessment);
    if (!["plan-readiness-v1", "plan-readiness-v2"].includes(text(assessment.schema_version, "")) || typeof frozen.context_sha256 !== "string"
      || assessment.context_sha256 !== frozen.context_sha256 || assessment.project_id !== frozen.project_id
      || assessment.snapshot_ref !== frozen.snapshot_ref || !["available", "blocked"].includes(text(assessment.execution_status, ""))) return;
    const budget = object(assessment.remaining_budget), candidates = objects(assessment.available_actions);
    card.append(el("h3", "", "计划执行条件"),
      el("p", "", `请求准备时 · 项目版本${number(frozen.state_version)}。以下为该请求的冻结条件。`),
      el("p", "", `剩余可用额度（已扣除预留） · 本地工具${number(budget.local_tool_calls)}次；来源读取${number(budget.evidence_reads)}次；估计器拟合${number(budget.estimator_fits)}次。`),
      el("p", "", assessment.execution_status === "available"
        ? "当时可执行的候选 · " + [...new Set(candidates.map(item => host.methodTitle(text(item.method_id))))].join("、")
        : "当时没有可执行候选；后续行动需先补条件。"));
    const methods = objects(assessment.blocked_methods), blockers = objects(assessment.blockers);
    const costs = assessment.schema_version === "plan-readiness-v2" ? objects(assessment.method_budget_costs) : [];
    const gaps = el("details", "local-advanced"); gaps.append(el("summary", "", "查看方法成本、条件与缺口"));
    if (costs.length) gaps.append(el("p", "detail-note", "请求准备时捕获的单次新派发额度需求。估计器拟合包含 Scaler 与 Ridge 的 fit；这份冻结成本不授予执行许可。"), methodBudgetCosts(costs));
    else gaps.append(el("p", "detail-note", "当时未捕获方法成本。"));
    for (const blocker of blockers) {
      const code = text(blocker.code);
      gaps.append(el("p", "", readinessReasons[code] ?? code));
    }
    if (methods.length) {
      const list = el("ul");
      for (const method of methods) {
        const reasons = strings(method.execution_blockers).map(code => readinessReasons[code] ?? code);
        const missing = strings(method.missing_information), item = el("li"), description = el("p");
        description.append(el("strong", "", host.methodTitle(text(method.method_id))), document.createTextNode(" · "
          + (reasons.join("；") || "受上述项目条件限制") + (missing.length ? "。待补信息：" + missing.join("；") : "")));
        item.append(description); list.append(item);
      }
      gaps.append(list);
    }
    card.append(gaps);
    card.append(el("p", "", "科学解释仍需审阅；此处核对执行条件。"));
  }
  function planSuggestion(record: Obj, card: HTMLElement, actions: HTMLElement): void {
    const proposal = object(record.proposal), plan = object(proposal.plan), id = text(record.request_id, "");
    planExecutionConditions(record, card);
    if (Object.keys(plan).length) {
      card.append(el("h3", "", text(plan.question)), el("h4", "", "建议的步骤"), el("p", "", text(plan.steps)),
        el("h4", "", "预期反馈与调整"), el("p", "", text(plan.expected_feedback)),
        el("h4", "", "预计改善"), el("p", "", text(proposal.expected_improvement)),
        el("p", "detail-note", "修改理由 · " + text(proposal.reason)));
      if (plan.basis) card.append(el("p", "detail-note", "依据与材料 · " + text(plan.basis)));
      const cited = strings(proposal.feedback_action_ids);
      card.append(el("p", "detail-note", cited.length ? `引用${cited.length}条已保存执行反馈，可在实验中心和原请求中核对。` : "根据当前课题与条件制定初始计划。"));
      planFactCheck(record, card);
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
  function planFactCheck(record: Obj, card: HTMLElement): void {
    const sourceProject = projectId, id = text(record.request_id, ""), key = sourceProject + ":" + id;
    const comparisons = objects(object(record.context).saved_comparisons);
    const draft = factDrafts.get(key) ?? { field: factText(record, "plan.basis") ? "plan.basis" : "plan.question", start: 0, end: 0, quote: "",
      comparison: "0", kind: "mae_order", order: "", metric: "candidate_mae", value: "", open: false };
    factDrafts.set(key, draft);
    const ui = factFormControls(record, draft, comparisons); card.append(ui.details);
    let busy = false, revision = 0, result: Obj | null = null;
    function controls(): void {
      ui.fields.disabled = busy; ui.run.textContent = busy ? "正在核对…" : "核对所声明的判断";
      ui.run.disabled = busy || !host.canCheckPlanFacts() || !draft.quote || !comparisons[Number(draft.comparison)]
        || draft.kind === "mae_order" && !draft.order || draft.kind === "metric" && !draft.value.trim();
      ui.save.disabled = !result || busy; ui.ordering.hidden = draft.kind !== "mae_order"; ui.numeric.hidden = ui.numericHint.hidden = draft.kind !== "metric";
      ui.quoted.textContent = draft.quote ? "已选原句 · " + draft.quote : "先在原建议正文中选中要核对的一句，再使用所选原句。";
    }
    function invalidate(): void { revision++; result = null; ui.result.replaceChildren(); controls(); }
    function edited(): void {
      if (draft.field !== ui.fieldControl.value) { draft.field = ui.fieldControl.value; draft.start = draft.end = 0; draft.quote = ""; ui.source.value = factText(record, draft.field); }
      draft.comparison = ui.comparison.value; draft.kind = ui.kind.value; draft.order = ui.order.value; draft.metric = ui.metric.value; draft.value = ui.value.value;
      factComparisonDetails(comparisons[Number(draft.comparison)] ?? {}, ui.comparisonDetails); invalidate();
    }
    ui.pick.addEventListener("click", () => {
      if (ui.source.selectionStart === ui.source.selectionEnd) { host.announce("请先在原建议正文中选中要核对的原句。", true); return; }
      const raw = factText(record, draft.field), start = factRawOffset(raw, ui.source.selectionStart), end = factRawOffset(raw, ui.source.selectionEnd);
      draft.start = Array.from(raw.slice(0, start)).length; draft.end = Array.from(raw.slice(0, end)).length;
      draft.quote = raw.slice(start, end); invalidate();
    });
    for (const control of [ui.fieldControl, ui.comparison, ui.kind, ui.order, ui.metric, ui.value]) {
      control.addEventListener("input", edited); control.addEventListener("change", edited);
    }
    ui.details.addEventListener("toggle", () => { draft.open = ui.details.open; });
    ui.save.addEventListener("click", () => { if (result) download(result, "-fact-check"); });
    ui.form.addEventListener("submit", event => { event.preventDefault(); void (async () => {
      if (ui.run.disabled) return;
      const comparison = comparisons[Number(draft.comparison)], baseline = object(comparison.baseline_ref), candidate = object(comparison.candidate_ref);
      const claim = { field: draft.field, start: draft.start, end: draft.end, quote: draft.quote,
        comparison: { check: comparison.check, baseline_action_id: baseline.action_id, candidate_action_id: candidate.action_id },
        assertion: draft.kind === "mae_order" ? { kind: "mae_order", value: draft.order } : { kind: "metric", metric: draft.metric, value: draft.value } };
      const generation = ++revision; busy = true; result = null; ui.result.replaceChildren(); controls();
      try {
        const checked = await host.checkPlanFact({ project_id: sourceProject, host_request_id: id, claim });
        if (generation !== revision || projectId !== sourceProject || !ui.form.isConnected) return;
        const frozen = object(object(record.context).selection_context);
        if (checked.schema_version !== "plan-fact-check-v1" || checked.project_id !== sourceProject || checked.host_request_id !== id || checked.context_sha256 !== frozen.context_sha256)
          throw Error("返回的核对记录不属于这份建议，请重新读取后核对。");
        result = checked; factResult(checked, ui.result);
      } catch (error) {
        if (generation !== revision || projectId !== sourceProject || !ui.form.isConnected) return;
        ui.result.replaceChildren(el("p", "notice error", error instanceof Error ? error.message : "核对未完成，请重新选择原句后再试。"));
      } finally { busy = false; if (ui.form.isConnected) controls(); }
    })(); });
    factComparisonDetails(comparisons[Number(draft.comparison)] ?? {}, ui.comparisonDetails); controls();
    if (!host.canCheckPlanFacts() && comparisons.length) ui.details.append(el("p", "detail-note", "此服务未开启本地操作。请在已开启本地操作的工作台核对，原建议仍可阅读。"));
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
    usage.append(el("p", "detail-note", "原生计数不包含外部CLI或原回答导入；CLI路由和金额以原回执自报为准，报告估值不等于现金结算。"));
    if (counts.prior_external_usage === "unknown_not_zero") usage.append(el("p", "detail-note", "还有未关联到本日志的历史外部选择，用量未知，不计为零。"));
    if (typeof counts.delegated_outputs_received === "number" && counts.delegated_outputs_received > 0)
      usage.append(el("p", "detail-note", `另有${counts.delegated_outputs_received}份外部原回答导入；模型与用量的核验状态见对应记录，现金结算未知。`));
  }
  function download(record: Obj | MaterialRequest[], suffix = ""): void {
    const url = URL.createObjectURL(new Blob([JSON.stringify(record, null, 2)], { type: "application/json;charset=utf-8" }));
    const link = el("a"); link.href = url; link.download = text(object(record).request_id, text(object(record).host_request_id, "model-request")).replace(/[^A-Za-z0-9_.-]/g, "_") + suffix + ".json";
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function improvementSummary(record: Obj, originalCard: HTMLDetailsElement): void {
    const validation = objects(view.recipe_validations).find(item => item.request_id === record.request_id && item.project_id === projectId) ?? {};
    const input = object(validation.input), proposal = object(record.proposal);
    const original = object(object(record.context).current_recipe), candidate = object(proposal.candidate);
    const labels: Record<string, string> = {
      not_started: "等待工具验证", pending: "验证记录待核对", recovery_required: "原验证回执待恢复",
      unknown: "原执行结果待核对", completed: "工具验证已完成", waiting: "本次验证选择等待",
      failed: "工具验证失败", invalid: "验证记录需核对", unavailable: "验证记录暂不可用",
    };
    const validationStatus = text(validation.status, "unavailable");
    improvement.hidden = false;
    improvement.append(el("h2", "section-title", "配方改进"),
      el("h3", "", "原版第" + number(original.version) + "版 · 候选第" + number(candidate.version) + "版"),
      el("p", ["failed", "invalid"].includes(validationStatus) ? "notice error" : "notice", labels[validationStatus] ?? validationStatus));
    if (Object.keys(input).length && validationStatus !== "invalid") {
      const comparison = el("div", "local-form-grid");
      const selection = object(object(object(record.context).research_context).selection_context);
      for (const [label, decision] of [["原版当时的选择", object(input.baseline_decision)], ["候选当时的选择", object(input.candidate_decision)]] as const) {
        const choice = object(object(decision.proposal).choice);
        const selected = objects(selection.candidates).find(item => item.id === choice.candidate_id);
        const choiceText = choice.kind === "wait" ? "等待" : selected ? host.methodTitle(text(selected.method_id)) : "选择身份待核对";
        const column = el("div", "local-improvement-choice"); column.append(el("span", "local-label", label), el("strong", "", choiceText)); comparison.append(column);
      }
      improvement.append(comparison);
    }
    const error = object(validation.error);
    if (error.code) improvement.append(el("p", "detail-note", "核对记录 · " + text(error.code) + " · " + text(error.message)));
    const details = el("details", "local-advanced"); details.append(el("summary", "", "查看模型修改理由"), el("p", "detail-note", text(proposal.reason)));
    improvement.append(details, el("p", "detail-note", "采用决定与后续轮次由配方模块记录。"));
    const actions = el("div", "local-actions"), source = el("button", "quiet-button", "查看原模型记录"); source.type = "button";
    source.addEventListener("click", () => {
      for (let parent = section.parentElement; parent; parent = parent.parentElement) if (parent instanceof HTMLDetailsElement) parent.open = true;
      originalCard.open = true; originalCard.querySelector("summary")?.focus({ preventScroll: true }); originalCard.scrollIntoView({ block: "center" });
    });
    actions.append(source);
    if (Object.keys(input).length || Object.keys(object(validation.result)).length) {
      const save = el("button", "quiet-button", "下载验证记录 JSON"); save.type = "button";
      save.addEventListener("click", () => download(validation, "-validation")); actions.append(save);
    }
    improvement.append(actions);
  }
  function savedRequests(): void {
    resumeButtons.length = 0; decisionButtons.length = 0; history.replaceChildren(el("h3", "", "已保存的模型请求"));
    planHistory.replaceChildren(el("h2", "section-title", "模型计划建议")); planHistory.hidden = !records.some(record => record.purpose === "plan");
    improvement.replaceChildren(); improvement.hidden = true;
    if (!records.length) { history.append(el("p", "detail-note", "尚无请求。打开页面不会创建请求。")); return; }
    for (const [index, record] of [...records].reverse().entries()) {
      const isPlan = record.purpose === "plan", isRecipe = record.purpose === "recipe";
      const id = text(record.request_id, ""), card = el("details", isPlan ? "local-plan-record" : "local-model-record local-batch-record");
      card.open = isPlan ? record.status === "proposed" : index === 0;
      let label = states[text(record.status)] ?? text(record.status);
      if (isPlan && record.status === "applied") label = "计划建议已采用";
      if (isRecipe && record.status === "proposed") label = "配方建议已保存 · 验证与采用由外环处理";
      const platformRuns = objects(view.platform_runs).filter(run => run.host_request_id === id);
      card.append(el("summary", "", label + (platformRuns.length ? " · AgentArts控制台摘录" : "") + " · " + id));
      const arguments_ = object(record.arguments), outcome = object(record.outcome), error = object(record.error);
      const route = strings(record.reported_models).join("、");
      card.append(el("p", "", "回答接入 · " + (record.provider === "claude_cli" ? "Claude CLI；自报路由 " + (route || "未知") : "外部原回答导入（delegated）")));
      for (const run of platformRuns) card.append(platformRunRecord(run));
      if (!isPlan) card.append(el("p", "detail-note", "模型解释 · " + text(isRecipe ? arguments_.reason : arguments_.rationale, "尚无通过解析的模型解释。")));
      if (isRecipe && record.status === "proposed") {
        card.append(el("p", "detail-note", "候选配方 · " + text(object(arguments_.candidate).id) + " · 第" + number(object(arguments_.candidate).version) + "版"),
          el("p", "detail-note", "预期改善 · " + text(arguments_.expected_improvement)),
          el("p", "detail-note", "验证安排 · " + text(arguments_.validation_plan)));
      }
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
      if (suppliedMaterials(object(record.context)).length) card.append(el("h4", "", "这份冻结输入供应的保存字段"), materialSummary(object(record.context)),
        el("p", "detail-note", "以上来自该请求冻结输入，不表示模型已理解或科学评审通过。完整字段值和提示原文保留在原请求 JSON。"));
      const actions = el("div", "local-actions");
      if (isPlan) planSuggestion(record, card, actions);
      if ((record.provider === "claude_cli" || isPlan && record.provider === "delegated") && resumableStates.has(text(record.status, "")) && (!isPlan || pendingStates.has(text(record.status, "")))) {
        const body = { request_id: id, project_id: projectId }, resume = el("button", "action-button", "核对原请求"); resume.type = "button";
        resume.setAttribute("aria-label", "核对原模型请求 " + id);
        resume.addEventListener("click", () => { if ((!locked || id === allowedRequestId) && !loading && canResume(body)) void host.submit("model-resume", body); });
        actions.append(resume); resumeButtons.push({ button: resume, body });
      }
      const save = el("button", "quiet-button", "下载原请求 JSON"); save.type = "button"; save.addEventListener("click", () => download(record)); actions.append(save);
      card.append(actions);
      const raw = el("details", "local-advanced"); raw.append(el("summary", "", suppliedMaterials(object(record.context)).length ? "上下文摘要、回答与记录" : "上下文、回答与完整记录"),
        el("pre", "project-source-text", JSON.stringify(recordReading(record), null, 2)));
      if (platformRuns.length) raw.append(el("h4", "", "保存的平台控制台摘录"), el("pre", "project-source-text", JSON.stringify(platformRuns, null, 2)));
      card.append(raw); (isPlan ? planHistory : history).append(card);
      if (isRecipe && improvement.hidden && Object.keys(object(record.proposal)).length) improvementSummary(record, card);
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
    if (projectId !== nextId || project.snapshot_ref !== nextProject.snapshot_ref)
      invalidateMaterials(projectId ? "项目或快照已变化，旧预览已作废；原字段选择仍保留，未改选其他诊断。"
        : "选择需要供应的完整字段，再预览本次输入。");
    if (projectId !== nextId) {
      records = []; view = {}; reason.value = ""; limit.value = "1"; cap.value = "0.10"; usage.replaceChildren(); savedRequests();
    }
    projectId = nextId; project = nextProject; context = nextContext; loading = true; loaded = false;
    renderMaterialChoices();
    currentMethodCosts();
    improvement.hidden = true;
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
    event.preventDefault(); if (start.disabled || !available() || !form.reportValidity() || !context) return;
    const fixed = grant(), decisionLimit = Number(fixed.decision_limit ?? limit.value), cliBudget = Number(fixed.cli_budget_usd ?? cap.value), actualReason = text(fixed.reason, reason.value.trim());
    if (!Number.isInteger(decisionLimit) || decisionLimit < 1 || decisionLimit > 8 || !(cliBudget > 0 && cliBudget <= 0.10) || !actualReason.trim()) {
      host.announce("请填写1至8次累计决策、至多0.10USD的正数CLI配置阈值及范围理由。", true); return;
    }
    void host.submit(purpose.value === "plan" ? "model-plan-advance" : "model-advance", { project_id: projectId, expected_state_version: context.state_version,
      decision_limit: decisionLimit, cli_budget_usd: cliBudget, reason: actualReason,
      ...(purpose.value === "plan" && materialRequests().length ? { saved_materials: materialRequests() } : {}) });
  });
  previewMaterials.addEventListener("click", () => { void (async () => {
    if (previewMaterials.disabled) return;
    const revision = ++materialRevision, id = projectId, snapshot = text(project.snapshot_ref, ""), requests = JSON.stringify(materialRequests());
    materialBusy = true; suppliedPreview = null; materialPreview.replaceChildren(); materialStatus.textContent = "正在读取并核对所选完整字段…"; materialControls();
    try {
      const preview = await host.read("/api/project/plan-context.json?saved_materials=" + encodeURIComponent(requests) + "&snapshot_ref=" + encodeURIComponent(snapshot));
      if (revision !== materialRevision || id !== projectId || snapshot !== project.snapshot_ref) return;
      const selection = object(preview.selection_context), supplied = suppliedMaterials(preview);
      if (preview.schema_version !== "research-plan-context-v3" || selection.project_id !== id || selection.snapshot_ref !== snapshot
        || supplied.length !== materialRequests().length || !materialRequests().every(request => supplied.some(material => material.action_id === request.action_id
          && material.result_sha256 === request.result_sha256 && Object.keys(object(material.fields)).length === request.fields.length
          && request.fields.every(name => { const field = object(object(material.fields)[name]); return Array.isArray(field.value) && field.count === field.value.length; }))))
        throw Error("返回输入的项目、快照或完整字段身份不符，请只读刷新后重新核对。");
      suppliedPreview = preview;
      materialStatus.className = "notice"; materialStatus.textContent = "完整输入已组装，可下载核对；尚未创建或发送模型请求。";
      materialPreview.append(materialSummary(preview));
    } catch (error) {
      if (revision !== materialRevision) return;
      const message = error instanceof Error ? error.message : "读取失败";
      materialStatus.className = "notice error";
      materialStatus.textContent = (message.includes("INVALID_PLAN_CONTEXT") ? "无法组装完整输入，请核对是否超过 64 KiB 上限。" : "完整输入预览失败：" + message + "。")
        + "选择已保留；没有截断字段或换成简表。可减少勾选字段后重新预览。";
    } finally { if (revision === materialRevision) { materialBusy = false; materialControls(); } }
  })(); });
  saveInput.addEventListener("click", () => { if (suppliedPreview) download(suppliedPreview, "-supplied-input"); });
  saveRequests.addEventListener("click", () => { if (materialRequests().length) download(materialRequests(), "-saved-materials"); });
  for (const control of [limit, cap, reason]) control.addEventListener("input", controls);
  purpose.addEventListener("change", () => { controls(); statusText(); });
  controls();
  const decisionResolved = (command: string, id: string): boolean => records.some(record => record.request_id === id && record.purpose === "plan"
    && (command === "model-plan-adopt" && record.status === "applied" || command === "model-plan-reject" && record.status === "rejected"));
  return { element: section, planElement: planHistory, improvementElement: improvement, refresh, pending, canResume, decisionResolved,
    savedRecords(id): Obj[] { return loaded && projectId === id ? records : []; }, setLocked(value: boolean, allowedId = ""): void { locked = value; allowedRequestId = allowedId; controls(); } };
}
