/** Explicit project-local snapshots of historical method cases. */
import { el } from "./dom";

type Obj = Record<string, unknown>;
type Host = {
  read(url: string): Promise<Obj>;
  submit(command: "experience-import" | "experience-status" | "experience-resume", body: Obj, recover?: boolean): Promise<Obj | null>;
  canRecover(body: Obj): boolean;
  methodTitle(methodId: string): string;
  announce(message: string, error?: boolean): void;
};
type Draft = { name: string; encoded: string; preview: Obj; reason: string; loading: boolean; submitted: boolean; statusReasons: Map<string, string> };
const object = (value: unknown): Obj => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const objects = (value: unknown): Obj[] => Array.isArray(value) ? value.map(object) : [];
const text = (value: unknown, fallback = "未记录"): string => typeof value === "string" && value.length ? value : fallback;
const strings = (value: unknown): string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
const numeric = (value: unknown): string => typeof value === "number" && Number.isFinite(value) ? String(value) : "未记录";

function field(label: string, control: HTMLElement): HTMLElement {
  const wrap = el("label", "local-field"); wrap.append(el("span", "local-label", label), control); return wrap;
}
function encoded(bytes: Uint8Array): string {
  const parts: string[] = []; for (let index = 0; index < bytes.length; index += 8192) parts.push(String.fromCharCode(...bytes.subarray(index, index + 8192)));
  return btoa(parts.join(""));
}
function download(value: Obj, label: string): void {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json;charset=utf-8" }));
  const link = el("a"); link.href = url; link.download = label.replace(/[^A-Za-z0-9_.-]/g, "_") + ".json"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function summaryText(summary: Obj): string {
  const labels: Record<string, string> = { n: "评价行数", input_n: "原输入行数", excluded: "排除行数", candidate_mae: "MAE",
    reference_mae: "训练均值参考 MAE", negative_predictions: "负预测数" };
  return Object.entries(labels).filter(([key]) => typeof summary[key] === "number" && Number.isFinite(summary[key]))
    .map(([key, label]) => label + " " + numeric(summary[key])).join("；");
}
function parentComparison(article: HTMLElement, comparison: Obj): void {
  if (comparison.status !== "comparable") return;
  const concise = (value: unknown): string => typeof value === "number" && Number.isFinite(value) ? String(Number(value.toPrecision(7))) : "未记录";
  const metrics = object(comparison.metrics), rows = object(comparison.row_summary), groups = object(comparison.group_summary);
  const relative = typeof metrics.relative_improvement === "number" ? concise(metrics.relative_improvement * 100) + "%" : "未计算";
  article.append(el("h4", "", "原项目保存的父版对照"),
    el("p", "", `父版 MAE ${concise(metrics.baseline_mae)} → 候选 MAE ${concise(metrics.candidate_mae)}；候选−父版 ${concise(metrics.mae_change)}；相对父版误差降低 ${relative}。`),
    el("p", "", `逐行绝对误差：${numeric(rows.improved_rows)} 改善、${numeric(rows.worsened_rows)} 恶化、${numeric(rows.tied_rows)} 持平（共 ${numeric(rows.n)} 行）。`));
  if (comparison.group_summary !== null)
    article.append(el("p", "", `按声明组 MAE：${numeric(groups.improved_groups)} 改善、${numeric(groups.worsened_groups)} 恶化、${numeric(groups.tied_groups)} 持平（共 ${numeric(groups.group_count)} 组）。`));
  const ranges = object(comparison.prediction_ranges);
  for (const [key, label] of [["baseline", "父版"], ["candidate", "候选"]]) {
    const range = object(ranges[key]);
    article.append(el("p", "", `${label}预测 ${concise(range.predicted_min)} 至 ${concise(range.predicted_max)}；负预测 ${numeric(range.negative_predictions)}；低于／高于原观察范围 ${numeric(range.below_observed_min)}／${numeric(range.above_observed_max)}。`));
  }
  article.append(el("p", "detail-note", "以上只描述原项目的保存对照；误差降低不表示本项目收益或科学确认，声明组也不自动成为独立样本。"));
}

export function createLocalExperiencePanel(host: Host): {
  element: HTMLElement; setLocked(value: boolean): void; refresh(projectId: string, project: Obj, pendingRequests?: Obj[]): Promise<void>;
  resolved(command: string, requestId: string): boolean;
} {
  const section = el("section", "local-panel local-experience content-section");
  section.append(el("h2", "section-title", "其他项目的方法案例"),
    el("p", "detail-note", "阅读历史项目的方法、观察与限制，供本项目计划参考。案例中的数值属于原项目；导入后仍需核对本项目的方法条件。"));
  const status = el("p", "notice", "创建或选择项目后可导入案例快照。"); status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
  const recovery = el("div", "local-experience-recovery"), list = el("div", "local-experience-cases"), editor = el("details", "local-advanced local-experience-import");
  editor.append(el("summary", "", "导入一个案例快照"));
  const form = el("form", "local-experience-form"), fields = el("fieldset", "local-fieldset"), chooser = el("input");
  chooser.type = "file"; chooser.accept = ".json,application/json"; chooser.setAttribute("aria-label", "选择方法案例快照 JSON");
  const fileStatus = el("p", "detail-note", "选择不超过4MiB的案例JSON；选择文件只准备草稿。"), reason = el("textarea");
  reason.rows = 3; reason.maxLength = 2000; reason.required = true;
  const save = el("button", "action-button primary", "导入为本项目参考"); save.type = "submit";
  fields.append(field("案例快照文件", chooser), fileStatus, field("本次导入理由", reason)); form.append(fields, save); editor.append(form);
  section.append(status, recovery, editor, list);
  const drafts = new Map<string, Draft>(), statusButtons: { button: HTMLButtonElement; reason: HTMLTextAreaElement }[] = [];
  const recoveryButtons: { button: HTMLButtonElement; body: Obj }[] = [];
  let active = "", project: Obj = {}, view: Obj = {}, pending: Obj[] = [], locked = true, loading = false, generation = 0;

  function draftFor(projectId: string): Draft {
    const old = drafts.get(projectId); if (old) return old;
    const draft: Draft = { name: "", encoded: "", preview: {}, reason: "", loading: false, submitted: false, statusReasons: new Map() };
    drafts.set(projectId, draft); return draft;
  }
  function controls(): void {
    const draft = active ? draftFor(active) : null, disabled = locked || loading || !active || !Number.isSafeInteger(project.state_version) || !!draft?.loading;
    fields.disabled = disabled; save.disabled = disabled || !draft?.encoded || !draft.reason.trim() || draft.submitted;
    save.textContent = draft?.submitted ? "案例快照已导入" : "导入为本项目参考";
    for (const entry of statusButtons) { entry.reason.disabled = disabled; entry.button.disabled = disabled || !entry.reason.value.trim(); }
    for (const entry of recoveryButtons) entry.button.disabled = !host.canRecover(entry.body);
  }
  function draftText(): void {
    const draft = active ? draftFor(active) : null;
    reason.value = draft?.reason ?? "";
    fileStatus.textContent = draft?.name ? draft.name + " · 案例 " + text(draft.preview.id) + " · v" + numeric(draft.preview.version)
      + (draft.submitted ? " · 已从保存记录确认导入。" : " · 草稿已准备，尚未提交。") : "选择不超过4MiB的案例JSON；选择文件只准备草稿。";
  }
  function resolved(command: string, requestId: string): boolean {
    return ["experience-import", "experience-status", "experience-resume"].includes(command)
      && !pending.some(record => record.request_id === requestId)
      && objects(view.history).some(revision => revision.request_id === requestId);
  }
  function renderRecovery(): void {
    recoveryButtons.length = 0; recovery.replaceChildren();
    for (const record of pending.filter(item => item.project_id === active && ["import_experience", "set_experience_status"].includes(text(item.command, "")))) {
      const id = text(record.request_id, ""), sourceProject = active, body = { request_id: id, project_id: sourceProject };
      const row = el("div", "notice"), button = el("button", "action-button", "核对原案例请求"); button.type = "button";
      row.append(el("p", "", "原案例请求待核对 · " + id), el("p", "detail-note", "核对沿用首次保存的文件与参数，不读取当前导入草稿。"), button);
      button.addEventListener("click", () => { if (!button.disabled) void (async () => {
        const result = await host.submit("experience-resume", body, true); if (result?.status !== "completed") return;
        const draft = draftFor(sourceProject);
        if (record.command === "import_experience" && draft.encoded) draft.submitted = true;
        const revision = objects(view.history).find(item => item.request_id === id);
        if (revision?.case_id) draft.statusReasons.delete(text(revision.case_id, ""));
        if (active === sourceProject) { draftText(); renderCases(); }
      })(); });
      recoveryButtons.push({ button, body }); recovery.append(row);
    }
    controls();
  }
  function caseRecord(record: Obj): HTMLElement {
    const article = el("article", "evidence-card local-experience-case"), card = object(record.method_card), origin = object(record.origin_evidence);
    const observation = object(record.observation), scope = object(record.source_scope), id = text(record.case_id, ""), sourceProject = active;
    const retired = record.inclusion_status === "retired", draft = draftFor(sourceProject);
    article.append(el("h3", "", text(card.question, id)), el("p", "detail-note", id + " · v" + numeric(record.case_version)
      + " · " + (retired ? "已从后续建议撤回" : "当前用于参考")), el("p", "", text(card.rationale)),
      el("p", "detail-note", "源项目 · " + text(origin.project_id)),
      el("p", "detail-note", "原方法 · " + objects(card.method_refs).map(item => host.methodTitle(text(item.method_id))).join("、")
        + "；原检查 · " + text(observation.check)), el("p", "detail-note", "原目标 · " + text(scope.target_column) + "；原单位 · " + text(scope.target_unit)));
    const numbers = summaryText(object(observation.numerical_summary)); if (numbers) article.append(el("p", "", "来源观察 · " + numbers));
    const summary = object(observation.numerical_summary);
    if ([summary.observed_min, summary.observed_max, summary.predicted_min, summary.predicted_max].every(value => typeof value === "number" && Number.isFinite(value)))
      article.append(el("p", "detail-note", `原观察范围 ${numeric(summary.observed_min)}至${numeric(summary.observed_max)}；保存预测范围 ${numeric(summary.predicted_min)}至${numeric(summary.predicted_max)}。`));
    parentComparison(article, object(observation.saved_parent_comparison));
    const limits = strings(record.limitations);
    if (limits.length) { const ul = el("ul"); for (const limit of limits) ul.append(el("li", "", limit)); article.append(el("h4", "", "适用边界与反例"), ul); }
    const original = el("details", "local-advanced"); original.append(el("summary", "", "查看方法卡、原协议与出处"));
    const applicability = object(card.applicability);
    for (const [key, label] of [["requires", "需要的条件"], ["not_applicable", "不适用情形"], ["uncertain", "尚未确定"]]) {
      const values = strings(applicability[key]), ul = el("ul"); for (const value of values) ul.append(el("li", "", value));
      if (values.length) original.append(el("h4", "", label), ul);
    }
    const protocol = object(observation.protocol);
    original.append(el("h4", "", "原计算协议"), el("p", "", text(protocol.splitter) + " · " + numeric(protocol.n_splits) + " 折；Ridge alpha " + numeric(protocol.ridge_alpha)),
      el("p", "", "原输入列：" + strings(protocol.feature_columns).join("、") + "；分组列：" + strings(protocol.split_group_columns).join("、")),
      el("p", "", "模型输入项：" + strings(protocol.model_input_terms).join("、")), el("p", "", "预处理：" + text(protocol.preprocessing)),
      el("p", "", "出处行动：" + text(origin.action_id) + "；原项目版本 " + numeric(origin.state_version)));
    const comparison = object(observation.saved_parent_comparison);
    if (comparison.status === "comparable") {
      for (const [key, label] of [["baseline_ref", "父版"], ["candidate_ref", "候选"]]) {
        const reference = object(comparison[key]);
        original.append(el("p", "", `${label}：项目设计 v${numeric(reference.design_version)}；资源 ${text(reference.resource_id)} v${numeric(reference.resource_version)}；行动 ${text(reference.action_id)}。`),
          el("p", "", label + "保存的模型输入项：" + strings(reference.model_input_terms ?? reference.feature_columns).join("、")));
      }
      original.append(el("p", "detail-note", "父版生产代码：" + text(origin.parent_producer_code_identity)),
        el("p", "detail-note", "候选生产代码：" + text(origin.producer_code_identity)));
    }
    const raw = el("details", "local-advanced"); raw.append(el("summary", "", "完整案例记录 JSON"), el("pre", "project-source-text", JSON.stringify(record, null, 2)));
    original.append(raw); article.append(original);
    const actions = el("div", "local-actions"), recordDownload = el("button", "quiet-button", "下载这条案例记录 JSON"); recordDownload.type = "button";
    recordDownload.addEventListener("click", () => download(record, id + "-v" + numeric(record.case_version))); actions.append(recordDownload);
    const statusForm = el("form", "local-experience-status"), statusReason = el("textarea"), button = el("button", "action-button");
    statusReason.rows = 2; statusReason.maxLength = 2000; statusReason.required = true; statusReason.value = draft.statusReasons.get(id) ?? "";
    button.type = "submit"; button.textContent = retired ? "恢复参考" : "从后续建议撤回";
    statusReason.addEventListener("input", () => { draft.statusReasons.set(id, statusReason.value); controls(); });
    statusForm.append(field(retired ? "恢复理由" : "撤回理由", statusReason), button);
    statusForm.addEventListener("submit", event => { event.preventDefault(); void (async () => {
      if (button.disabled || !statusForm.reportValidity()) return;
      const result = await host.submit("experience-status", { project_id: sourceProject, expected_state_version: project.state_version,
        case_id: id, status: retired ? "active" : "retired", reason: statusReason.value });
      if (result?.status === "completed") { draft.statusReasons.delete(id); if (active === sourceProject) renderCases(); }
    })(); });
    statusButtons.push({ button, reason: statusReason }); article.append(actions, statusForm); return article;
  }
  function renderCases(): void {
    statusButtons.length = 0; list.replaceChildren();
    const cases = objects(view.cases);
    if (!cases.length) list.append(el("p", "empty-state", "本项目尚未导入其他项目的方法案例。"));
    for (const record of cases) list.append(caseRecord(record));
    if (objects(view.history).length) {
      const history = el("details", "local-advanced"), changes = el("ol"); history.append(el("summary", "", "查看本项目的案例状态历史"));
      for (const revision of objects(view.history)) {
        const action = revision.command === "import_experience" ? "导入" : revision.inclusion_status === "active" ? "恢复参考" : "撤回参考";
        changes.append(el("li", "", text(revision.case_id) + " v" + numeric(revision.case_version) + " · " + action + "：" + text(revision.reason)));
      }
      const raw = el("details", "local-advanced"); raw.append(el("summary", "", "完整状态历史 JSON"), el("pre", "project-source-text", JSON.stringify(view.history, null, 2)));
      history.append(changes, raw);
      const saveHistory = el("button", "quiet-button", "下载案例状态历史 JSON"); saveHistory.type = "button";
      saveHistory.addEventListener("click", () => download({ project_id: active, history: view.history }, "experience-history")); history.append(saveHistory); list.append(history);
    }
    controls();
  }
  chooser.addEventListener("change", () => { void (async () => {
    const file = chooser.files?.[0], sourceProject = active; chooser.value = ""; if (!file || !sourceProject) return;
    const draft = draftFor(sourceProject); draft.loading = true; controls();
    try {
      if (!file.size || file.size > 4 * 1024 * 1024) throw Error("案例JSON须非空且不超过4MiB，原草稿保留。");
      const bytes = new Uint8Array(await file.arrayBuffer()), preview = object(JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)));
      if (preview.schema_version !== "project-experience-bundle-v1" || typeof preview.id !== "string" || typeof preview.version !== "number")
        throw Error("请选择导出的项目案例快照，原草稿保留。");
      draft.name = file.name; draft.encoded = encoded(bytes); draft.preview = preview; draft.submitted = false;
      if (active === sourceProject) draftText();
    } catch (error) { if (active === sourceProject) host.announce(error instanceof Error ? error.message : "文件读取未完成，原草稿保留。", true); }
    finally { draft.loading = false; controls(); }
  })(); });
  reason.addEventListener("input", () => { if (active) { const draft = draftFor(active); draft.reason = reason.value; draft.submitted = false; } controls(); });
  form.addEventListener("submit", event => { event.preventDefault(); void (async () => {
    const sourceProject = active, draft = sourceProject ? draftFor(sourceProject) : null;
    if (!draft || save.disabled || !form.reportValidity()) return;
    const result = await host.submit("experience-import", { project_id: sourceProject, expected_state_version: project.state_version,
      bundle_base64: draft.encoded, reason: draft.reason });
    if (result?.status === "completed") { draft.submitted = true; if (active === sourceProject) { draftText(); controls(); } }
  })(); });
  async function refresh(projectId: string, current: Obj, pendingRequests: Obj[] = []): Promise<void> {
    const token = ++generation; active = projectId; project = current; view = {}; pending = pendingRequests; loading = true;
    list.replaceChildren(); draftText(); renderRecovery(); controls();
    if (!projectId || current.id !== projectId) { loading = false; status.textContent = "创建或选择项目后可导入案例快照。"; controls(); return; }
    status.textContent = "正在读取当前项目的案例快照…";
    try {
      const value = await host.read("/api/local-workbench/experiences");
      if (token !== generation || projectId !== active) return;
      if (value.schema_version !== "project-experience-view-v1" || value.project_id !== projectId || value.state_version !== current.state_version)
        throw Error("案例快照与当前项目版本不一致，请只读刷新后核对。");
      view = value; renderCases(); status.textContent = "这些是历史方法案例。原数值保留其来源范围，本项目的行动仍由当前条件和额度决定。";
    } catch (error) {
      if (token !== generation || projectId !== active) return;
      status.textContent = error instanceof Error ? error.message : "案例快照读取未完成，请只读刷新后核对。";
    } finally { if (token === generation) { loading = false; controls(); } }
  }
  return { element: section, setLocked(value): void { locked = value; controls(); }, refresh, resolved };
}
