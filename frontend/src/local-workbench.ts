/** Explicit local commands above the existing saved-result reader; no automatic research. */
import { $, el } from "./dom";
import { createProjectPages } from "./project-pages";
import { createLocalEvidencePanel } from "./local-evidence";
import { createLocalBatchPanel, continuationStopReason } from "./local-batch";
import { createLocalModelPanel } from "./local-model";
import { createLocalRecipePanel } from "./local-recipe";
import { progressFeedback, researcherFeedbackItems, sourceQuestionText } from "./project-view";

type Obj = Record<string, unknown>;
type Pending = { command: string; requestId: string; body: string; uncertain: boolean; recoverBatch?: boolean; recoverModel?: boolean };
const obj = (value: unknown): Obj => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const items = (value: unknown): Obj[] => Array.isArray(value) ? value.map(obj) : [];
const text = (value: unknown, fallback = "未记录"): string => typeof value === "string" && value.length ? value : fallback;
const names = (value: unknown): string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
const sameBody = (left: Obj, right: Obj): boolean => Object.keys(left).length === Object.keys(right).length
  && Object.keys(left).every(key => JSON.stringify(left[key]) === JSON.stringify(right[key]));
const methodNames: Record<string, string> = {
  "data.tabular-quality-audit": "核对表格质量、重复与声明分组",
  "data.grouped-quality-profile": "查看零值与缺失集中于哪些组",
  "data.numeric-association": "查看数值字段与目标的关联",
  "research.source-selection": "读取已登记的来源选区",
  "p02.source-mapping-check": "读取已登记的来源选区",
};
const PENDING_KEY = "autoresearch.local-workbench.pending.v1";
const MODEL_COMMANDS = new Set(["model-advance", "model-resume", "model-plan-advance", "model-plan-adopt", "model-plan-reject"]);

function header(textValue: string, delimiter: string): string[] {
  const columns: string[] = [];
  let value = "", quoted = false, closed = false;
  for (let index = 0; index < textValue.length; index++) {
    const char = textValue[index];
    if (quoted) {
      if (char === '"' && textValue[index + 1] === '"') { value += '"'; index++; }
      else if (char === '"') { quoted = false; closed = true; }
      else value += char;
    } else if (char === delimiter) { columns.push(value); value = ""; closed = false; }
    else if (char === "\r" || char === "\n") { columns.push(value); return checkHeader(columns); }
    else if (char === '"' && !value && !closed) quoted = true;
    else if (closed) throw Error("表头引号后出现其他字符，请核对CSV格式或分隔符。");
    else value += char;
  }
  if (quoted) throw Error("CSV表头的引号没有闭合。");
  columns.push(value); return checkHeader(columns);
}

function checkHeader(columns: string[]): string[] {
  if (!columns.length || columns.length > 128 || columns.some(name => !name.trim() || name !== name.trim() || name.length > 256 || name.includes("\0")))
    throw Error("表头需有1至128个非空字段，不能带首尾空格或NUL。");
  if (new Set(columns.map(name => name.normalize("NFKC").toLocaleLowerCase())).size !== columns.length)
    throw Error("表头存在重复或歧义字段名，请先核对来源。");
  return columns;
}

function base64(bytes: Uint8Array): string {
  const chunks: string[] = [];
  for (let offset = 0; offset < bytes.length; offset += 8192) chunks.push(String.fromCharCode(...bytes.subarray(offset, offset + 8192)));
  return btoa(chunks.join(""));
}

async function sha256(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new Uint8Array(bytes).buffer);
  return Array.from(new Uint8Array(digest), value => value.toString(16).padStart(2, "0")).join("");
}

function field(labelText: string, control: HTMLElement, hint?: string): HTMLElement {
  const wrap = el("label", "local-field"); wrap.append(el("span", "local-label", labelText), control);
  if (hint) wrap.append(el("small", "detail-note", hint));
  return wrap;
}

function input(value = "", maximum = 4000): HTMLInputElement {
  const control = el("input"); control.type = "text"; control.value = value; control.maxLength = maximum; return control;
}

function panel(title: string, description: string): HTMLElement {
  const section = el("section", "local-panel content-section");
  section.append(el("h2", "section-title", title), el("p", "detail-note", description)); return section;
}

function requestId(command: string): string { return "local-" + command + "-" + crypto.randomUUID(); }

const planFields = [
  { key: "question", label: "这轮要解决的问题", maximum: 4000, required: true },
  { key: "basis", label: "依据与已有材料", maximum: 6000, required: false },
  { key: "steps", label: "准备怎样推进", maximum: 12000, required: true },
  { key: "expected_feedback", label: "预期反馈与调整条件", maximum: 4000, required: true },
  { key: "reason", label: "本次制定或修订的理由", maximum: 2000, required: true },
];

function planChangeView(previous: Obj, saved: Obj, projectId: string, modelRecords: Obj[]): DocumentFragment {
  const body = document.createDocumentFragment();
  const changed = planFields.filter(definition => definition.key !== "reason" && text(previous[definition.key], "") !== text(saved[definition.key], ""));
  if (!changed.length) body.append(el("p", "detail-note", "两版计划正文一致，可结合上方修订依据查看本次记录。"));
  for (const definition of changed) {
    const change = el("section", "research-plan-change"), columns = el("div", "research-plan-change-columns");
    change.append(el("h4", "", definition.label));
    for (const [label, version] of [["调整前", previous], ["调整后", saved]] as const) {
      const column = el("div"); column.append(el("h5", "", label), el("p", "", text(version[definition.key], "未填写"))); columns.append(column);
    }
    change.append(columns); body.append(change);
  }
  const model = modelRecords.find(record => {
    const outcome = obj(record.outcome), adopted = obj(outcome.research_plan), context = obj(obj(record.context).selection_context), proposal = obj(record.proposal);
    return record.purpose === "plan" && record.status === "applied" && record.controller_request_id === saved.request_id
      && outcome.kind === "plan_revision" && context.project_id === projectId && context.state_version === saved.based_on_state_version
      && ["request_id", "version", "based_on_state_version"].every(key => adopted[key] === saved[key])
      && planFields.filter(definition => definition.key !== "reason").every(definition => obj(proposal.plan)[definition.key] === adopted[definition.key])
      && proposal.reason === adopted.reason;
  });
  if (model) {
    const references = names(obj(model.proposal).feedback_action_ids), feedback = items(obj(model.context).feedback);
    const evidence = el("section", "research-plan-evidence"); evidence.append(el("h4", "", "这次建议引用的工具反馈"));
    if (!references.length) evidence.append(el("p", "detail-note", "该模型建议没有引用工具行动。"));
    for (const id of references) {
      const action = feedback.find(record => record.action_id === id);
      if (!action) continue;
      const source = ["research.source-selection", "p02.source-mapping-check"].includes(text(action.method_id, ""));
      const raw = el("details"), link = el("a", "text-button", "查看实际" + (source ? "来源" : "方法") + "结果"); link.href = source ? "#/knowledge" : "#/experiments";
      evidence.append(el("h5", "", methodNames[text(action.method_id, "")] ?? text(action.method_id)), el("p", "", progressFeedback(action, source)), link);
      raw.append(el("summary", "", "查看这条反馈原记录"), el("pre", "project-source-text", JSON.stringify(action, null, 2))); evidence.append(raw);
    }
    body.append(evidence);
  }
  return body;
}

function planSourceFeedback(project: Obj, saved: Obj): HTMLElement {
  const feedback = el("div", "research-plan-evidence"), completed = items(project.evidence_actions).filter(action => action.status === "completed");
  const selectionCount = completed.reduce((count, action) => count + items(action.observations).filter(observation => observation.kind === "source_observed").length, 0);
  const latest = completed.at(-1), questions = names(obj(latest?.next_decision).remaining_questions);
  const basisState = typeof saved.based_on_state_version === "number" ? String(saved.based_on_state_version) : "未记录";
  const currentState = typeof project.state_version === "number" ? String(project.state_version) : "未记录";
  feedback.append(el("h3", "", "当前保存的来源反馈"),
    el("p", "detail-note", `第${String(saved.version)}版计划依据项目状态 ${basisState} 制定，当前项目状态为 ${currentState}。下方计划正文保留制定时记录。`),
    el("p", "project-progress-copy", `当前已完成 ${completed.length} 次来源读取，共提取 ${selectionCount} 个选区。提取完成不表示资料解释或提交者主张已获确认。`));
  if (latest) {
    feedback.append(el("h4", "", "最近一次来源读取仍待确认的问题"));
    if (questions.length) {
      const list = el("ul", "project-questions");
      for (const question of new Set(questions.map(sourceQuestionText))) list.append(el("li", "", question));
      feedback.append(list);
    } else feedback.append(el("p", "detail-note", "该来源行动未保存具体未决问题，可查看来源原文与实际实验记录继续核对。"));
  } else feedback.append(el("p", "detail-note", "尚无已完成的来源读取；已登记资料仍需明确读取后才会出现在这里。"));
  const links = el("div", "local-actions");
  for (const [label, href] of [["查看来源原文与定位", "#/knowledge"], ["查看已完成实验", "#/experiments"]]) {
    const link = el("a", "text-button", label); link.href = href; links.append(link);
  }
  feedback.append(links); return feedback;
}

function createResearchPlanPanel(deps: {
  current(): Obj; modelRecords(projectId: string): Obj[]; submit(body: Obj): Promise<Obj | null>;
}): { element: HTMLElement; update(project: Obj): void; setLocked(value: boolean): void } {
  const section = panel("研究计划", "写下当前问题、准备采取的步骤，以及什么反馈会让你调整路线。"), sourceFeedback = el("div"), preview = el("div", "research-plan-copy");
  section.classList.add("research-plan");
  const editor = el("details", "research-plan-editor"), summary = el("summary", "", "编写计划"), form = el("form"), fields = el("fieldset", "local-fieldset");
  const inputs = new Map<string, HTMLTextAreaElement>();
  for (const definition of planFields) {
    const control = el("textarea"); control.maxLength = definition.maximum; control.required = definition.required; control.rows = definition.key === "steps" ? 4 : 2;
    inputs.set(definition.key, control); fields.append(field(definition.label, control));
  }
  const status = el("p", "detail-note"), save = el("button", "local-primary", "保存计划"), rebase = el("button", "text-button", "按当前版本继续编辑");
  save.type = "submit"; rebase.type = "button"; rebase.hidden = true;
  const actions = el("div", "local-actions"); actions.append(save, rebase); form.append(fields, status, actions); editor.append(summary, form);
  const history = el("details", "research-plan-history"), historyBody = el("div"); history.append(el("summary", "", "查看修订记录"), historyBody);
  const comparison = el("details", "research-plan-comparison"), comparisonTitle = el("summary"), comparisonBody = el("div");
  comparison.append(comparisonTitle, comparisonBody); comparison.hidden = true;
  section.append(sourceFeedback, preview, comparison, editor, history);
  const drafts = new Map<string, { values: Record<string, string>; stateVersion: number }>();
  let projectId = "", stateVersion = 0, locked = true;
  const values = (): Record<string, string> => Object.fromEntries([...inputs].map(([key, control]) => [key, control.value]));
  function controls(): void {
    const stale = stateVersion !== deps.current().state_version;
    fields.disabled = locked || !projectId; save.disabled = fields.disabled || stale;
    rebase.hidden = !projectId || !stale; rebase.disabled = locked;
    status.textContent = stale ? "项目已更新，草稿已保留。核对当前计划后，可按当前版本继续编辑。" : "保存后进入项目记录，下一次模型选择会读取当前计划。";
  }
  function update(project: Obj): void {
    if (projectId !== project.id) comparison.open = false;
    projectId = text(project.id, ""); section.hidden = !projectId;
    const plan = obj(project.research_plan), saved = obj(plan.current), draft = drafts.get(projectId);
    stateVersion = draft?.stateVersion ?? Number(project.state_version);
    summary.textContent = typeof saved.version === "number" ? "修订计划 · 当前第" + saved.version + "版" : "编写计划";
    preview.replaceChildren();
    sourceFeedback.replaceChildren();
    if (saved.version) {
      sourceFeedback.append(planSourceFeedback(project, saved));
      const route = el("div"), feedback = el("div");
      route.append(el("p", "project-progress-copy", "第" + String(saved.version) + "版已采用计划 · 以下为制定时原文"),
        el("h3", "", text(saved.question)), el("p", "research-plan-steps", text(saved.steps)));
      if (saved.basis) route.append(el("h4", "", "依据与材料"), el("p", "", text(saved.basis)));
      feedback.append(el("h4", "", "预期反馈与调整"), el("p", "", text(saved.expected_feedback)), el("h4", "", "本次修订依据"), el("p", "", text(saved.reason)));
      preview.append(route, feedback);
    } else preview.append(el("p", "detail-note", "当前项目尚未保存研究计划，可以从本轮问题开始编写。"));
    for (const [key, control] of inputs) control.value = draft ? draft.values[key] : key === "reason" ? "" : text(saved[key], key === "question" ? text(project.goal, "") : "");
    historyBody.replaceChildren(); const revisions = items(plan.revisions); history.hidden = revisions.length === 0;
    const previous = revisions.find(revision => typeof saved.version === "number" && revision.version === saved.version - 1);
    comparison.hidden = !previous; comparisonBody.replaceChildren();
    if (previous) {
      comparisonTitle.textContent = "查看本次调整 · 第" + previous.version + "版 → 第" + saved.version + "版";
      comparisonBody.append(planChangeView(previous, saved, projectId, deps.modelRecords(projectId)));
    }
    for (const revision of [...revisions].reverse()) {
      const record = el("details"), heading = el("summary", "", "第" + revision.version + "版 · " + text(revision.reason));
      record.append(heading, el("p", "", text(revision.question)), el("p", "research-plan-steps", text(revision.steps)), el("p", "", "预期反馈与调整 · " + text(revision.expected_feedback)));
      if (revision.basis) record.append(el("p", "", "依据与材料 · " + text(revision.basis)));
      historyBody.append(record);
    }
    controls();
  }
  form.addEventListener("input", () => { if (projectId) drafts.set(projectId, { values: values(), stateVersion }); });
  rebase.addEventListener("click", () => {
    stateVersion = Number(deps.current().state_version); drafts.set(projectId, { values: values(), stateVersion }); controls();
  });
  form.addEventListener("submit", async event => {
    event.preventDefault(); if (save.disabled || !form.reportValidity()) return;
    const submittedProject = projectId, content = values(), { reason, ...plan } = content;
    drafts.set(projectId, { values: content, stateVersion });
    const result = await deps.submit({ project_id: projectId, expected_state_version: stateVersion, plan, reason });
    if (result?.status === "completed") { drafts.delete(submittedProject); update(deps.current()); editor.open = false; summary.focus(); }
  });
  return { element: section, update, setLocked(value): void { locked = value; controls(); } };
}

function createResearcherFeedbackPanel(deps: {
  current(): Obj; context(): Obj | null; submit(body: Obj): Promise<Obj | null>;
}): { element: HTMLElement; update(project: Obj): void; setLocked(value: boolean): void } {
  const section = panel("研究者反馈", "补充你发现的卡点、判断或后续建议。保存的意见会提供给下一次模型计划。"), saved = el("details", "researcher-feedback-saved");
  section.classList.add("researcher-feedback");
  const savedTitle = el("summary"), savedBody = el("div"); saved.append(savedTitle, savedBody);
  const editor = el("details", "researcher-feedback-editor"), summary = el("summary", "", "记录一条反馈"), form = el("form"), fields = el("fieldset", "local-fieldset");
  const author = el("input"), comment = el("textarea"), nextStep = el("textarea"), action = el("select");
  author.required = true; author.maxLength = 120; comment.required = true; comment.maxLength = 6000; comment.rows = 4; nextStep.maxLength = 4000; nextStep.rows = 3;
  fields.append(field("反馈人（自填称呼）", author), field("你发现的问题或判断", comment), field("希望接下来怎样调整（可选）", nextStep), field("关联的已保存工作", action));
  const status = el("p", "detail-note"), save = el("button", "action-button primary", "保存反馈"), rebase = el("button", "text-button", "核对后按当前版本记录");
  save.type = "submit"; rebase.type = "button"; rebase.hidden = true;
  const actions = el("div", "local-actions"); actions.append(save, rebase); form.append(fields, status, actions); editor.append(summary, form); section.append(saved, editor);
  const drafts = new Map<string, { author: string; comment: string; nextStep: string; actionId: string; stateVersion: number }>();
  let projectId = "", stateVersion = 0, locked = true;
  const remember = (): void => { if (projectId) drafts.set(projectId, { author: author.value, comment: comment.value, nextStep: nextStep.value, actionId: action.value, stateVersion }); };
  function controls(): void {
    const stale = stateVersion !== deps.current().state_version;
    const codeChanged = items(deps.context()?.blockers).some(item => item.code === "CODE_CHANGED");
    fields.disabled = locked || !projectId; save.disabled = fields.disabled || stale || codeChanged;
    rebase.hidden = !projectId || !stale; rebase.disabled = locked;
    status.textContent = codeChanged ? "项目源码版本需先明确升级，草稿会保留。" : stale ? "项目已更新，请先核对保存工作，再按当前版本记录这条意见。"
      : "意见按自填身份保存，属于研究者陈述。采用计划和执行方法仍需分别提交。";
  }
  function update(project: Obj): void {
    projectId = text(project.id, ""); section.hidden = !projectId;
    const draft = drafts.get(projectId), records = items(project.researcher_feedback);
    stateVersion = draft?.stateVersion ?? Number(project.state_version);
    savedTitle.textContent = "已保存反馈 " + records.length + " 条"; saved.hidden = records.length === 0;
    savedBody.replaceChildren(researcherFeedbackItems(project, records.length));
    action.replaceChildren(); const whole = el("option", "", "整个项目与当前计划"); whole.value = ""; action.append(whole);
    for (const record of [...items(project.actions), ...items(project.evidence_actions)]) {
      const method = text(record.command, ""); const option = el("option", "", (methodNames[method] ?? method) + " · " + text(record.id)); option.value = text(record.id, ""); action.append(option);
    }
    author.value = draft?.author ?? ""; comment.value = draft?.comment ?? ""; nextStep.value = draft?.nextStep ?? ""; action.value = draft?.actionId ?? "";
    controls();
  }
  form.addEventListener("input", remember); form.addEventListener("change", remember);
  rebase.addEventListener("click", () => { stateVersion = Number(deps.current().state_version); remember(); controls(); });
  form.addEventListener("submit", async event => {
    event.preventDefault(); if (save.disabled || !form.reportValidity()) return;
    const submittedProject = projectId; remember();
    const result = await deps.submit({ project_id: projectId, expected_state_version: stateVersion, author: author.value, comment: comment.value, next_step: nextStep.value, action_id: action.value || null });
    if (result?.status === "completed") { drafts.delete(submittedProject); update(deps.current()); editor.open = false; saved.open = true; savedTitle.focus(); }
  });
  return { element: section, update, setLocked(value): void { locked = value; controls(); } };
}

export async function mountLocalWorkbench(): Promise<void> {
  document.body.classList.add("project-standalone", "local-workbench-mode");
  $("page-state").hidden = true; $("page-content").hidden = false;
  for (const id of ["inspector", "inspector-backdrop", "search-results"]) $(id).hidden = true;
  const searchWrap = document.querySelector<HTMLElement>(".search-wrap"); if (searchWrap) searchWrap.hidden = true;
  $<HTMLInputElement>("search").disabled = true;
  const statusLabel = document.querySelector<HTMLElement>(".topbar-status"); if (statusLabel) statusLabel.textContent = "本地项目 · 明确提交";
  const footer = document.querySelector<HTMLElement>(".nav-footer>span:nth-child(2)"); if (footer) footer.textContent = "本地工作台 · 显式操作";
  $("project-label").textContent = "当前研究项目"; $("project-title").textContent = "从问题和数据开始";
  $("nav-project-title").textContent = "尚未选择项目";

  const host = el("div", "local-workbench project-workspace"); $("page-content").replaceChildren(host);
  const message = el("p", "notice local-message", "正在读取本地工作台…"); message.setAttribute("role", "status"); message.setAttribute("aria-live", "polite");
  const pendingNotice = el("div", "notice local-pending"); pendingNotice.hidden = true;
  const retry = el("button", "quiet-button", "用原请求ID核对／重试"); retry.type = "button"; retry.hidden = true;
  const refreshButton = el("button", "quiet-button", "只读刷新保存状态"); refreshButton.type = "button";
  const toolbar = el("div", "local-actions"); toolbar.append(refreshButton, retry);
  const switching = panel("已保存的项目", "重开页面会读取持久保存的当前项目；切换会清除旧候选上下文。");
  const projectSelect = el("select"); projectSelect.setAttribute("aria-label", "选择已保存项目");
  const selectButton = el("button", "action-button", "切换当前项目"); selectButton.type = "button";
  const switchControls = el("div", "local-project-switch"); switchControls.append(projectSelect, selectButton); switching.append(switchControls);

  const createSection = panel("1 · 问题与输入", "创建只登记本次输入，随后才可选择执行检查。CSV原字节和本次字段声明会一起保存。");
  const form = el("form", "local-create-form"), createFields = el("fieldset", "local-fieldset");
  const goal = el("textarea"); goal.rows = 3; goal.required = true; goal.maxLength = 4000; goal.placeholder = "例如：这份表格的零值是否集中在少数组，哪些记录需要回到来源核对？";
  const csvFile = el("input"); csvFile.type = "file"; csvFile.accept = ".csv,.tsv,text/csv,text/tab-separated-values"; csvFile.required = true;
  const fileStatus = el("p", "detail-note", "选择CSV或TSV后，先读取表头供你声明字段；完整格式仍由宿主校验。"); fileStatus.setAttribute("aria-live", "polite");
  const delimiter = el("select"); for (const [value, label] of [[",", "逗号 CSV"], ["\t", "Tab TSV"]]) { const option = el("option", "", label); option.value = value; delimiter.append(option); }
  const dataset = input("", 300), sample = input("本CSV每行的一条记录；独立性尚未核验", 300);
  const url = input("", 2000), license = input("许可与访问范围尚待核验", 4000);
  dataset.required = true; sample.required = true; url.required = true; license.required = true;
  const unit = input("", 300); unit.placeholder = "选择目标后，填写实际单位；未知需明确写未知";
  const target = el("select"), noTarget = el("option", "", "不声明目标字段"); noTarget.value = ""; target.append(noTarget);
  const roles = el("div", "local-roles");
  const toolLimit = el("select"); toolLimit.required = true;
  const emptyLimit = el("option", "", "明确选择本地调用上限"); emptyLimit.value = ""; toolLimit.append(emptyLimit);
  for (const value of [1, 2]) { const option = el("option", "", value + "次本地工具调用"); option.value = String(value); toolLimit.append(option); }
  const budget = input("shared-historical:existing-cap5CNY;cash-settlement-unknown;native-model0;host-usage-separate", 500); budget.required = true;
  const importFile = el("input"); importFile.type = "file"; importFile.accept = ".json,application/json";
  const importNote = el("p", "detail-note", "可导入已有spec.json填充声明；表单修改会生成本次spec，原导入文件不会被改写。");
  const clearImport = el("button", "quiet-button", "改用当前CSV直接声明"); clearImport.type = "button";
  const advanced = el("details", "local-advanced"); advanced.append(el("summary", "", "已有字段声明与预算归属（可选）"), field("导入spec.json", importFile), importNote, clearImport, field("历史预算归属", budget));
  createFields.append(field("要核对的问题", goal), field("CSV / TSV文件", csvFile), fileStatus,
    field("分隔符", delimiter), roles);
  const declarations = el("div", "local-form-grid"); declarations.append(field("数据集标签", dataset), field("每行代表什么", sample),
    field("来源URL或本地派生标识", url), field("许可与待核对范围", license), field("目标字段（可选）", target), field("目标单位（声明）", unit),
    field("本地调用上限", toolLimit, "只允许本次明确选定的1或2次；模型、拟合和来源额度不会因此增加。"));
  createFields.append(declarations, advanced);
  const createButton = el("button", "action-button primary", "创建项目，不执行方法"); createButton.type = "submit";
  const createToggle = el("button", "quiet-button", "收起新课题输入"); createToggle.type = "button";
  form.id = "local-create-form"; createToggle.setAttribute("aria-controls", form.id); createToggle.setAttribute("aria-expanded", "true");
  form.append(createFields, createButton); createSection.append(createToggle, form);

  const runSection = panel("2 · 选择一次行动", "候选来自当前项目的真实条件和预算。选择一个候选并填写理由，或明确保存等待。");
  const contextStatus = el("p", "detail-note", "创建或选择项目后读取候选。"); contextStatus.setAttribute("aria-live", "polite");
  const candidateList = el("div", "local-candidates"), citationList = el("div", "local-citations");
  const rationale = el("textarea"); rationale.rows = 3; rationale.maxLength = 4000; rationale.placeholder = "说明为何现在执行这个检查，或为何等待。";
  const executeButton = el("button", "action-button primary", "明确执行所选候选一次"); executeButton.type = "button";
  const waitButton = el("button", "action-button", "本次选择等待"); waitButton.type = "button";
  const reportButton = el("button", "action-button", "生成当前快照报告"); reportButton.type = "button";
  const runActions = el("div", "local-actions"); runActions.append(executeButton, waitButton, reportButton);
  runSection.append(contextStatus, candidateList, field("这次选择的理由", rationale), citationList, runActions,
    el("p", "detail-note", "等待仅保存本次选择，不表示项目暂停或方法耗尽。生成报告不继续研究。"));

  let description: Obj = {}, current: Obj = {}, context: Obj | null = null, busy = false, loadingFile = false;
  let selectedCandidate = "", citations = new Set<string>(), lastRequest: Pending | null = null;
  let batchUncertain: Pending | null = null;
  let csv: { name: string; bytes: Uint8Array; encoded: string; sha: string; decoded: string } | null = null;
  let imported: Obj | null = null, headers: string[] = [], roleInputs = new Map<string, Record<string, HTMLInputElement>>();
  let fileGeneration = 0, lastCreateSignature = "", lastCreatedProject = "";
  const evidencePending = new Map<string, Pending>();
  const selectedRoles = (kind: string): string[] => headers.filter(name => roleInputs.get(name)?.[kind].checked);
  const activeId = (): string => text(description.active_project_id, "");
  const serverPending = (projectId = activeId()): boolean => items(description.pending_requests).some(record => record.command !== "evidence" || !record.project_id || record.project_id === projectId);
  const requestProject = (pending: Pending): string => text(obj(JSON.parse(pending.body)).project_id, "");
  const uncertain = (projectId = activeId()): boolean => !!batchUncertain || !!evidencePending.get(projectId)?.uncertain || !!lastRequest?.uncertain && (lastRequest.command !== "evidence" || requestProject(lastRequest) === projectId);
  const navigationBlocked = (): boolean => items(description.pending_requests).some(record => !["batch", "continue", "evidence"].includes(text(record.command, "")))
    || !!lastRequest?.uncertain && !["batch", "continue", "evidence"].includes(lastRequest.command);
  const unknownExecution = (): boolean => items(context?.blockers).some(item => /UNKNOWN|NEEDS_REVIEW/.test(text(item.code, ""))) || current.execution_status === "unknown";
  const evidencePanel = createLocalEvidencePanel({ read, submit: body => submit(command("evidence", body)), announce });
  const batchPanel = createLocalBatchPanel({ submit: (body, recover, name) => submit(recover
    ? { command: name, requestId: text(body.request_id, ""), body: JSON.stringify(body), uncertain: false, recoverBatch: true }
    : command(name, body)), canRecover: canRecoverBatch, announce });
  const modelPanel = createLocalModelPanel({ read, submit: (name, body) => submit(["model-resume", "model-plan-adopt", "model-plan-reject"].includes(name)
    ? { command: name, requestId: text(body.request_id, ""), body: JSON.stringify(body), uncertain: false, recoverModel: true }
    : command(name, body)), announce, methodTitle: id => methodNames[id] ?? id });
  const recipePanel = createLocalRecipePanel({ read, preview: previewRecipe,
    submit: (name, body) => submit(command(name, body)), announce });
  const planPanel = createResearchPlanPanel({ current: () => current, modelRecords: id => modelPanel.savedRecords(id), submit: body => submit(command("plan", body)) });
  const feedbackPanel = createResearcherFeedbackPanel({ current: () => current, context: () => context, submit: body => submit(command("feedback", body)) });
  const workspacePages = createProjectPages(host, { shared: [message, pendingNotice, toolbar], management: [switching, createSection],
    planning: [planPanel.element, modelPanel.planElement, modelPanel.improvementElement, recipePanel.effectiveElement, feedbackPanel.element], feedback: feedbackPanel.element,
    operations: [batchPanel.element, modelPanel.element, recipePanel.element, runSection, evidencePanel.element], read, announce });
  function planContinuation(requestId = ""): Obj | undefined {
    return items(description.continuations).find(record => record.project_id === activeId() && record.record_status === "incomplete"
      && ["plan", "awaiting_adoption"].includes(text(record.phase, "")) && obj(record.plan_ref).kind === "host_plan"
      && (!requestId || obj(record.plan_ref).request_id === requestId));
  }
  function otherModelBlockers(requestId = ""): boolean {
    const owner = requestId ? planContinuation(requestId) : undefined;
    return items(description.pending_requests).some(record => record.request_id !== owner?.request_id
      && (record.command !== "evidence" || !record.project_id || record.project_id === activeId()))
      || !!batchUncertain && batchUncertain.requestId !== owner?.request_id || !!evidencePending.get(activeId())?.uncertain
      || !!lastRequest?.uncertain && !MODEL_COMMANDS.has(lastRequest.command) && lastRequest.requestId !== owner?.request_id;
  }
  function canRecoverModel(body: Obj): boolean {
    return !busy && description.enabled === true && !otherModelBlockers(text(body.request_id, ""))
      && body.project_id === activeId() && modelPanel.canResume(body);
  }
  function canRecoverBatch(body: Obj, name: "batch" | "continue" = "batch"): boolean {
    const record = items(description[name === "continue" ? "continuations" : "batches"]).find(item => item.request_id === body.request_id && item.project_id === body.project_id);
    if (busy || description.enabled !== true || !record || record.record_status === "completed"
      || !["preparing", "incomplete"].includes(text(record.record_status, "")) || body.project_id !== activeId()
      || !sameBody(obj(record.body), body)) return false;
    if (items(description.pending_requests).some(item => item.request_id !== body.request_id && item.request_id !== obj(record.batch_ref).request_id
      && (item.command !== "evidence" || !item.project_id || item.project_id === body.project_id))) return false;
    if (lastRequest?.uncertain && lastRequest.requestId !== body.request_id
      && (lastRequest.command !== "evidence" || requestProject(lastRequest) === body.project_id)) return false;
    if (batchUncertain && batchUncertain.requestId !== body.request_id) return false;
    return !evidencePending.get(text(body.project_id, ""))?.uncertain;
  }
  function announce(value: string, error = false): void { message.textContent = value; message.classList.toggle("error", error); message.setAttribute("role", error ? "alert" : "status"); }
  function controls(): void {
    const globalLocked = busy || description.enabled !== true || serverPending("") || uncertain("");
    const navigationLocked = busy || description.enabled !== true || navigationBlocked();
    const locked = globalLocked || serverPending() || uncertain() || unknownExecution() || modelPanel.pending();
    createFields.disabled = globalLocked; createButton.disabled = globalLocked || loadingFile || !csv || !headers.length;
    selectButton.disabled = navigationLocked || !projectSelect.value || projectSelect.value === activeId(); projectSelect.disabled = navigationLocked;
    executeButton.disabled = locked || !context || !selectedCandidate || !rationale.value.trim() || items(context.blockers).length > 0;
    waitButton.disabled = locked || !context || !rationale.value.trim();
    reportButton.disabled = locked || !activeId() || typeof current.state_version !== "number" || (obj(current.report).available === true && obj(current.report).stale !== true);
    refreshButton.disabled = busy;
    retry.hidden = !lastRequest; retry.disabled = busy || !lastRequest || lastRequest.uncertain || (lastRequest.command === "evidence" && requestProject(lastRequest) !== activeId()) || description.enabled !== true;
    evidencePanel.setLocked(locked);
    batchPanel.setLocked(locked || typeof current.state_version !== "number" || current.id !== activeId());
    const planId = text(obj(planContinuation()?.plan_ref).request_id, "");
    modelPanel.setLocked(busy || description.enabled !== true || otherModelBlockers(),
      !busy && description.enabled === true && !otherModelBlockers(planId) ? planId : "");
    recipePanel.setLocked(locked || current.id !== activeId());
    planPanel.setLocked(locked || current.id !== activeId());
    feedbackPanel.setLocked(locked || current.id !== activeId());
    rationale.disabled = locked;
    candidateList.querySelectorAll<HTMLInputElement>("input").forEach(control => { control.disabled = locked || items(context?.blockers).length > 0; });
    citationList.querySelectorAll<HTMLInputElement>("input").forEach(control => { control.disabled = locked; });
  }
  function showPending(): void {
    const records = items(description.pending_requests);
    let remembered: Obj = {};
    try { remembered = obj(JSON.parse(sessionStorage.getItem(PENDING_KEY) ?? "{}")); } catch { /* Storage is optional; manager owns durable state. */ }
    pendingNotice.replaceChildren(); pendingNotice.hidden = !records.length && !remembered.request_id && !batchUncertain && ![...evidencePending.values()].some(pending => pending.uncertain);
    if (records.length) pendingNotice.append(el("strong", "", records.some(record => ["batch", "continue"].includes(text(record.command, "")))
      ? "有原推进记录尚未收口。请在继续研究中核对原阶段；计划建议需先采用或拒绝，未知行动不会重发。"
      : "有原请求尚未确认，保留原ID核对；资料登记仅阻断对应项目的新提交，可切换查看其他项目。"));
    else if (remembered.request_id) pendingNotice.append(el("strong", "", "上次浏览器提交尚需对照保存记录核对；没有自动重发。"));
    for (const record of records) pendingNotice.append(el("p", "detail-note", text(record.command) + " · " + text(record.request_id) + " · " + text(record.status) + (record.project_id ? " · 项目 " + text(record.project_id) : "")));
    for (const pending of evidencePending.values()) if (pending.uncertain && !records.some(record => record.request_id === pending.requestId)) pendingNotice.append(el("p", "detail-note", "evidence · 原ID " + pending.requestId + " · 结果待核对 · 项目 " + requestProject(pending)));
    if (batchUncertain && !records.some(record => record.request_id === batchUncertain?.requestId)) pendingNotice.append(el("p", "detail-note", "batch · 原ID " + batchUncertain.requestId + " · 结果待核对；可切回原项目，新提交保持锁定。"));
    if (remembered.request_id && !records.some(record => record.request_id === remembered.request_id)) pendingNotice.append(el("p", "detail-note", text(remembered.command) + " · 原ID " + text(remembered.request_id)));
  }
  function renderRoles(useImported = false): void {
    if (!csv) return;
    headers = header(csv.decoded, delimiter.value); roleInputs = new Map(); roles.replaceChildren();
    const table = el("table", "data-table local-role-table"), head = el("thead"), row = el("tr");
    for (const label of ["实际字段", "数值", "分组", "键"]) { const th = el("th", "", label); th.scope = "col"; row.append(th); }
    head.append(row); table.append(head); const body = el("tbody");
    for (const name of headers) {
      const tr = el("tr"), heading = el("th", "", name); heading.scope = "row"; tr.append(heading);
      const choices: Record<string, HTMLInputElement> = {};
      for (const kind of ["numeric", "group", "key"] as const) {
        const td = el("td"), label = el("label", "local-checkbox"), check = el("input"); check.type = "checkbox";
        check.setAttribute("aria-label", name + "作为" + ({ numeric: "数值列", group: "分组列", key: "键列" }[kind]));
        check.checked = useImported && names(imported?.[kind + "_columns"]).includes(name);
        label.append(check); td.append(label); tr.append(td); choices[kind] = check;
      }
      roleInputs.set(name, choices); body.append(tr);
    }
    table.append(body); roles.append(el("p", "detail-note", "至少勾选1个数值字段；分组和键可不声明。声明角色不证明样本独立性。"), table);
    const chosen = useImported ? text(imported?.target_column, "") : target.value;
    const emptyTarget = el("option", "", "不声明目标字段"); emptyTarget.value = ""; target.replaceChildren(emptyTarget);
    for (const name of headers) { const option = el("option", "", name); option.value = name; target.append(option); }
    target.value = headers.includes(chosen) ? chosen : ""; controls();
  }
  function applyImported(): void {
    if (!imported) return;
    if (csv && imported.file !== csv.name) throw Error("spec的file与当前CSV文件名不一致，请选择对应文件或改用直接声明。");
    delimiter.value = text(imported.delimiter, ","); dataset.value = text(imported.dataset_label, ""); sample.value = text(imported.sample_unit, "");
    url.value = text(imported.source_url, ""); license.value = text(imported.license_note, ""); unit.value = text(imported.target_unit, "");
    if (csv) {
      const actual = header(csv.decoded, delimiter.value);
      if ([...names(imported.numeric_columns), ...names(imported.group_columns), ...names(imported.key_columns)].some(name => !actual.includes(name))) throw Error("导入spec声明了CSV表头中不存在的字段。");
      renderRoles(true);
    }
    importNote.textContent = "已导入声明。来源、许可、单位和provenance原声明保留；表单修改后提交本次新spec。";
  }
  csvFile.addEventListener("change", () => { void (async () => {
    const generation = ++fileGeneration, file = csvFile.files?.[0]; csv = null; headers = []; roles.replaceChildren(); loadingFile = true; controls();
    try {
      if (!file) { fileStatus.textContent = "尚未选择CSV。"; return; }
      const max = typeof obj(description.constraints).max_csv_bytes === "number" ? Number(obj(description.constraints).max_csv_bytes) : 8 * 1024 * 1024;
      if (!file.size || file.size > max || file.name.length > 160 || /[<>:"/\\|?*\u0000-\u001f]/.test(file.name) || !/\.(csv|tsv)$/i.test(file.name)) throw Error("请选择安全文件名的CSV/TSV，大小需在8MiB以内且非空。");
      const bytes = new Uint8Array(await file.arrayBuffer()), decoded = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      if (decoded.includes("\0")) throw Error("CSV含NUL，不能作为本次输入。");
      const digest = await sha256(bytes); if (generation !== fileGeneration) return;
      csv = { name: file.name, bytes, encoded: base64(bytes), sha: digest, decoded };
      if (imported) applyImported();
      else {
        const comma = (() => { try { return header(decoded, ",").length; } catch { return 0; } })();
        const tab = (() => { try { return header(decoded, "\t").length; } catch { return 0; } })();
        delimiter.value = tab > comma ? "\t" : ","; dataset.value = file.name; url.value = "urn:autoresearch:local-upload:sha256:" + digest;
        renderRoles();
      }
      fileStatus.textContent = `${file.name} · ${file.size.toLocaleString("zh-CN")}字节 · ${headers.length}个表头字段；完整CSV仍待宿主核验。`;
    } catch (error) { fileStatus.textContent = error instanceof Error ? error.message : "文件读取失败，请核对UTF-8编码。"; headers = []; announce(fileStatus.textContent, true); }
    finally { if (generation === fileGeneration) { loadingFile = false; controls(); } }
  })(); });
  delimiter.addEventListener("change", () => { try { renderRoles(); fileStatus.textContent = "已按所选分隔符重读表头，请重新声明字段。"; } catch (error) { headers = []; roles.replaceChildren(); announce(error instanceof Error ? error.message : "表头无法读取。", true); controls(); } });
  target.addEventListener("change", () => { if (target.value) { const choices = roleInputs.get(target.value); if (choices) choices.numeric.checked = true; } unit.required = !!target.value; });
  importFile.addEventListener("change", () => { void (async () => {
    try {
      const file = importFile.files?.[0]; if (!file) return;
      if (!file.size || file.size > 64 * 1024) throw Error("spec.json须为非空且不超过64KiB的UTF-8 JSON。");
      const parsed: unknown = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer()));
      const value = obj(parsed), expected = ["schema_version", "file", "dataset_label", "source_url", "license_note", "sample_unit", "group_columns", "key_columns", "numeric_columns", "target_column", "target_unit", "missing_tokens", "delimiter", "provenance"];
      if (Object.keys(value).length !== expected.length || expected.some(key => !(key in value)) || value.schema_version !== "tabular-quality-spec-v1" || ![",", "\t"].includes(text(value.delimiter))) throw Error("导入文件不是支持的tabular-quality-spec-v1完整声明。");
      imported = value; applyImported();
    } catch (error) { imported = null; importNote.textContent = error instanceof Error ? error.message : "声明导入失败。"; announce(importNote.textContent, true); }
  })(); });
  clearImport.addEventListener("click", () => { imported = null; importFile.value = ""; unit.value = "";
    importNote.textContent = "当前使用CSV直接声明；上游待核验。";
    if (csv) { dataset.value = csv.name; url.value = "urn:autoresearch:local-upload:sha256:" + csv.sha; renderRoles(); }
  });
  function spec(): Obj {
    if (!csv) throw Error("请先选择CSV文件。");
    const numeric = selectedRoles("numeric"), group = selectedRoles("group"), key = selectedRoles("key");
    if (!numeric.length || numeric.length > 32 || group.length > 8 || key.length > 8) throw Error("请声明1至32个数值列，分组与键各最多8列。");
    if (target.value && (!numeric.includes(target.value) || !unit.value.trim())) throw Error("声明目标时，须勾选为数值列并填写实际单位或明确未知。");
    return { ...(imported ?? {}), schema_version: "tabular-quality-spec-v1", file: csv.name, dataset_label: dataset.value.trim(),
      source_url: url.value.trim(), license_note: license.value.trim(), sample_unit: sample.value.trim(), group_columns: group, key_columns: key,
      numeric_columns: numeric, target_column: target.value || null, target_unit: target.value ? unit.value.trim() : null,
      missing_tokens: imported?.missing_tokens ?? [""], delimiter: delimiter.value,
      provenance: imported?.provenance ?? { origin_sha256: csv.sha, description: "Direct capture of the selected CSV bytes; upstream origin, transformation, license and target meaning remain unverified." } };
  }

  async function read(urlValue: string): Promise<Obj> {
    const response = await fetch(urlValue, { cache: "no-store", signal: AbortSignal.timeout(15000) });
    const value: unknown = await response.json(); if (!response.ok) throw Error("读取失败：" + text(obj(value).code, String(response.status)));
    return obj(value);
  }
  async function previewRecipe(body: Obj): Promise<Obj> {
    const response = await fetch("/api/local-workbench/recipe-preview", {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json", "X-AutoResearch-CSRF": text(description.csrf_token, "") },
      body: JSON.stringify(body), signal: AbortSignal.timeout(15000),
    });
    const result = obj(await response.json());
    if (!response.ok) throw Error("外环核对失败：" + text(result.code, String(response.status)));
    return result;
  }
  function candidates(): void {
    candidateList.replaceChildren(); citationList.replaceChildren();
    if (!context) { contextStatus.textContent = activeId() ? "当前候选未载入；只读刷新可重新核对。" : "创建或选择项目后读取候选。"; controls(); return; }
    const choices = items(context.candidates);
    if (!choices.some(choice => choice.id === selectedCandidate)) selectedCandidate = "";
    contextStatus.textContent = items(context.blockers).length ? "当前有宿主阻断条件，不能执行新方法；可查看保存结果或明确等待。" : choices.length ? `当前有${choices.length}个真实可执行候选；不会自动选择或执行。` : "当前没有合资格候选；可以填写理由并保存本次等待。";
    for (const choice of choices) {
      const label = el("label", "local-candidate evidence-card"), radio = el("input"); radio.type = "radio"; radio.name = "local-candidate"; radio.value = text(choice.id, ""); radio.checked = choice.id === selectedCandidate;
      radio.addEventListener("change", () => { selectedCandidate = radio.value; controls(); });
      const content = el("span"); content.append(el("strong", "", methodNames[text(choice.method_id)] ?? text(choice.method_id)), el("small", "detail-note", "只使用宿主绑定的参数和评价范围"));
      label.append(radio, content); candidateList.append(label);
    }
    const evidence = items(context.evidence), available = new Set(evidence.map(hit => text(hit.citation_id, "")));
    citations = new Set([...citations].filter(id => available.has(id)));
    if (evidence.length) {
      citationList.append(el("h3", "", "引用实际来源（可选，最多16处）"));
      for (const hit of evidence) {
        const box = el("details", "local-citation"), summary = el("summary");
        summary.textContent = text(obj(hit.source).title, "已提取来源") + " · " + text(hit.citation_id).slice(0, 12);
        const label = el("label", "local-checkbox"), check = el("input"); check.type = "checkbox"; check.checked = citations.has(text(hit.citation_id));
        check.addEventListener("change", () => { const id = text(hit.citation_id); if (check.checked && citations.size >= 16) { check.checked = false; announce("最多引用16处实际来源。", true); return; } if (check.checked) citations.add(id); else citations.delete(id); });
        label.append(check, el("span", "", "引用这一真实片段"));
        box.append(summary, label, el("pre", "project-source-text", text(hit.quote)), el("p", "detail-note", "原定位：" + JSON.stringify(hit.location)));
        citationList.append(box);
      }
    }
    const raw = el("details", "local-advanced"); raw.append(el("summary", "", "条件、阻断与候选参数"), el("pre", "project-source-text", JSON.stringify({ state_version: context.state_version, context_sha256: context.context_sha256, blockers: context.blockers, conditions: context.conditions, candidates: context.candidates }, null, 2))); candidateList.append(raw);
    controls();
  }
  function downloads(): void {
    const ready = obj(current.report).available === true && obj(current.report).stale !== true;
    for (const [id, format, label] of [["download-pdf", "pdf", "当前报告 PDF ↓"], ["download-zip", "json", "当前报告 JSON ↓"]]) {
      const button = $<HTMLButtonElement>(id); button.textContent = label; button.disabled = busy || !ready;
      button.title = ready ? "当前快照报告" : "先生成与当前项目匹配的报告";
      button.onclick = () => { if (ready && !busy) location.assign("/api/project/report." + format); };
    }
  }
  async function refresh(): Promise<void> {
    const previousId = activeId(); context = null; candidates();
    planPanel.setLocked(true);
    feedbackPanel.setLocked(true);
    modelPanel.setLocked(true);
    recipePanel.invalidate(); recipePanel.setLocked(true);
    batchPanel.setLocked(true);
    await evidencePanel.refresh("", {});
    description = await read("/api/local-workbench");
    if (description.schema_version !== "local-research-workbench-v1") throw Error("本地工作台返回身份不完整。");
    const savedContinuation = (id: string, body?: string): Obj | undefined => items(description.continuations).find(record =>
      record.schema_version === "local-research-continuation-v1" && record.request_id === id
      && (!body || sameBody(obj(record.body), obj(JSON.parse(body)))));
    if (lastRequest?.command === "continue" && savedContinuation(lastRequest.requestId, lastRequest.body)) lastRequest = null;
    if (batchUncertain?.command === "continue" && savedContinuation(batchUncertain.requestId, batchUncertain.body)) batchUncertain = null;
    try {
      const remembered = obj(JSON.parse(sessionStorage.getItem(PENDING_KEY) ?? "{}"));
      if (remembered.command === "continue" && savedContinuation(text(remembered.request_id, ""))) sessionStorage.removeItem(PENDING_KEY);
    } catch { /* The saved continuation, including its pending phase, remains authoritative. */ }
    const now = activeId();
    if (now !== previousId) { selectedCandidate = ""; citations.clear(); rationale.value = ""; if (now) form.hidden = true; }
    if (evidencePending.has(now)) lastRequest = evidencePending.get(now) ?? null;
    createToggle.textContent = form.hidden ? "展开新课题与CSV输入" : "收起新课题输入";
    createToggle.setAttribute("aria-expanded", String(!form.hidden));
    projectSelect.replaceChildren();
    const projects = items(description.projects);
    if (!projects.length) { const option = el("option", "", "暂无已保存项目"); option.value = ""; projectSelect.append(option); }
    for (const project of projects) { const option = el("option", "", text(project.goal).slice(0, 90)); option.value = text(project.id, ""); projectSelect.append(option); }
    projectSelect.value = now; current = {};
    $("nav-project-title").textContent = now ? text(projects.find(project => project.id === now)?.goal, "当前本地项目") : "尚未选择项目";
    $("project-title").textContent = $("nav-project-title").textContent;
    const navNote = document.querySelector<HTMLElement>(".nav-note p"); if (navNote) navNote.textContent = "操作需明确提交。查看不会执行，结果保留，未知不自动重发。";
    showPending();
    if (now) {
      try { current = await read("/api/project"); }
      catch (error) { planPanel.update({}); feedbackPanel.update({}); await workspacePages.update({}, null); throw error; }
      const savedPlanIds = new Set(items(obj(current.research_plan).revisions).map(revision => revision.request_id));
      const savedFeedbackIds = new Set(items(current.researcher_feedback).map(record => record.request_id));
      if (lastRequest && (lastRequest.command === "plan" && savedPlanIds.has(lastRequest.requestId) || lastRequest.command === "feedback" && savedFeedbackIds.has(lastRequest.requestId))) lastRequest = null;
      try {
        const remembered = obj(JSON.parse(sessionStorage.getItem(PENDING_KEY) ?? "{}"));
        if (remembered.command === "plan" && savedPlanIds.has(remembered.request_id) || remembered.command === "feedback" && savedFeedbackIds.has(remembered.request_id)) sessionStorage.removeItem(PENDING_KEY);
      } catch { /* The project record remains available when browser storage is unavailable. */ }
      showPending();
      try {
        const next = await read("/api/project/selection-context.json");
        if (next.project_id !== now || next.schema_version !== "project-selection-context-v1") throw Error("候选不属于当前项目，请刷新后核对。");
        context = next;
      } catch (error) { context = null; announce(error instanceof Error ? error.message : "当前候选读取失败。", true); }
      planPanel.update(current); feedbackPanel.update(current); candidates(); batchPanel.update(description, current); await evidencePanel.refresh(now, current);
      await modelPanel.refresh(now, current, context); planPanel.update(current); await recipePanel.refresh(now, current, context); await workspacePages.update(current, context);
      if (lastRequest && modelPanel.decisionResolved(lastRequest.command, lastRequest.requestId)) lastRequest = null;
      try {
        const remembered = obj(JSON.parse(sessionStorage.getItem(PENDING_KEY) ?? "{}"));
        if (modelPanel.decisionResolved(text(remembered.command, ""), text(remembered.request_id, ""))) sessionStorage.removeItem(PENDING_KEY);
      } catch { /* Saved model records remain authoritative. */ }
      showPending();
    } else { planPanel.update({}); feedbackPanel.update({}); batchPanel.update(description, {}); await modelPanel.refresh("", {}, null); await recipePanel.refresh("", {}, null); await workspacePages.update({}, null); }
    if (description.enabled !== true) announce("当前服务没有启用写入模式，不能提交本地命令。", true);
    downloads(); controls();
  }
  async function submit(pending: Pending): Promise<Obj | null> {
    if (busy) return null;
    const targetProject = requestProject(pending), switching = pending.command === "select";
    const sameEvidence = pending.command === "evidence" && evidencePending.get(targetProject)?.requestId === pending.requestId;
    const recoverBatch = (pending.command === "batch" || pending.command === "continue") && pending.recoverBatch === true
      && canRecoverBatch(obj(JSON.parse(pending.body)), pending.command);
    const recoverModel = pending.recoverModel === true && canRecoverModel(obj(JSON.parse(pending.body)));
    if (pending.recoverBatch && !recoverBatch) { announce("原批次恢复条件尚未核对，请选择原项目并只读刷新；不会创建替代批次。", true); return null; }
    if (pending.recoverModel && !recoverModel) { announce("请先只读刷新，核对当前项目中保存的原模型请求。不会创建替代请求。", true); return null; }
    const blocked = switching ? navigationBlocked() : (serverPending(targetProject) && !sameEvidence) || uncertain(targetProject) || modelPanel.pending() || (pending.command !== "create" && unknownExecution());
    if (!recoverBatch && !recoverModel && (description.enabled !== true || blocked)) { announce("当前命令不可提交，请先只读核对原请求与保存状态。", true); return null; }
    const modelCommand = MODEL_COMMANDS.has(pending.command);
    lastRequest = pending; busy = true; controls(); downloads(); announce(modelCommand ? "正在处理原模型请求；将保留回答和实际行动结果…" : "正在提交一次明确的本地命令…");
    if (pending.command === "evidence") evidencePending.set(targetProject, pending);
    try { sessionStorage.setItem(PENDING_KEY, JSON.stringify({ request_id: pending.requestId, command: pending.command })); } catch { /* Host journal remains authoritative. */ }
    let outcomeMessage = "", failed = false, accepted: Obj | null = null;
    try {
      const response = await fetch("/api/local-workbench/" + pending.command, { method: "POST", credentials: "same-origin", cache: "no-store",
        headers: { "Content-Type": "application/json", "X-AutoResearch-CSRF": text(description.csrf_token, "") }, body: pending.body, signal: AbortSignal.timeout(modelCommand ? 210000 : 60000) });
      const result = obj(await response.json());
      if (!response.ok) {
        pending.uncertain = response.status >= 500 || /UNKNOWN|NEEDS_REVIEW|INCOMPLETE/.test(text(result.code, ""));
        const reasons: Record<string, string> = { INVALID_SPEC: "字段声明与CSV需要逐项核对", INVALID_CSV: "CSV编码、表头或行宽不满足范围", INVALID_BUNDLE: "来源文件或选区声明需要核对", INVALID_LOCATOR: "选区坐标不满足当前读取范围", TASK_MISMATCH: "资料与当前取证任务不匹配", STALE_SELECTION_CONTEXT: "项目已变化，请重新读取候选后决定", STALE_STATE: "项目版本或当前选择已变化", IDEMPOTENCY_CONFLICT: "原请求ID已经绑定其他内容", BUDGET_EXHAUSTED: "本地调用额度已用完，已有用量保留", OPERATION_INCOMPLETE: "原操作未完成，需要保留并核对" };
        Object.assign(reasons, { MODEL_DISABLED: "服务尚未启用Claude CLI，请按使用说明启动", HOST_DECISION_LIMIT: "本项目模型决策名额已用尽", HOST_GRANT_CHANGED: "原累计额度和理由已冻结，不能替换", HOST_SELECTION_PENDING: "请核对原模型请求", HOST_USAGE_UNKNOWN: "原模型费用未知，不能按零计后继续发送" });
        reasons.CODE_CHANGED = "当前项目需按使用说明明确升级到本次代码版本";
        const code = text(result.code, String(response.status));
        failed = true; outcomeMessage = "提交未完成：" + (reasons[code] ?? "请核对当前条件与输入") + "（" + code + "）。输入已保留；" + (pending.uncertain ? "结果仍需核对，不自动重发。" : "可以用原ID和原内容显式重试，或核对后修正输入。");
      } else if (["unknown", "running", "pending", "prepared", "sending", "received"].includes(text(result.status, ""))) {
        pending.uncertain = true; failed = true; outcomeMessage = "原请求结果尚未确认，请只读核对保存状态。没有自动重发。";
      } else {
        pending.uncertain = pending.command === "batch" && result.status === "needs_review"; accepted = result;
        outcomeMessage = pending.command === "create" ? "项目已创建，尚未执行方法。请从实际候选中选择下一步。" : pending.command === "select" ? "已切换活动项目，旧候选已清除。"
          : pending.command === "report" ? "当前快照报告已生成，可从顶栏或保存结果区下载。" : pending.command === "evidence" ? "资料已登记，尚未读取。请从真实来源候选中选择并明确执行。" : obj(result.decision).next_action && obj(obj(result.decision).next_action).kind === "external_wait" ? "本次等待已保存，没有创建新行动。" : "本次行动和反馈已保存，请核对结果后再决定下一步。";
        if (pending.command === "evidence") { evidencePanel.acceptRegistered(result); evidencePending.delete(targetProject); }
        if (pending.command === "batch") {
          const batch = obj(result.batch), stop = obj(batch.stop), count = items(batch.steps).length;
          const labels: Record<string, string> = { waiting: "等待后续条件", limit_reached: "达到本次授权上限", not_authorized: "下一步未获本次授权", blocked: "当前条件或原额度阻断", failed: "行动失败，原记录保留", needs_review: "待核对，未知行动不重发" };
          outcomeMessage = `批次已保存${count}步记录：${labels[text(result.status)] ?? "请核对原批次状态"}。` + text(stop.reason, "") + " 没有自动扩大授权或生成下一批次。";
          failed = pending.uncertain || result.status === "failed";
        }
        if (pending.command === "continue") {
          const stop = obj(result.stop);
          outcomeMessage = result.phase === "awaiting_adoption" ? "计划建议已保存，请先在本页查看并明确采用或拒绝，再接回原任务。"
            : result.phase === "plan" ? "原计划请求已保存，等待同一请求的回答；核对原请求不会另开模型调用。"
              : "本次继续记录已保存。";
          outcomeMessage += continuationStopReason(stop);
          failed = result.status === "failed" || result.status === "needs_review" && stop.resume_allowed !== true;
        }
        if (pending.command === "advance-recipe") {
          pending.uncertain = result.status === "needs_review"; failed = pending.uncertain || result.status === "failed";
          outcomeMessage = result.status === "waiting" ? "本次配方等待已保存，没有新行动；选择规则未调用模型。"
            : result.status === "completed" ? "配方已推进一步并保存实际反馈；选择规则未调用模型。"
              : "配方请求已保存，请核对实际行动和原请求状态；没有自动继续。";
        }
        if (pending.command === "plan") outcomeMessage = "研究计划已保存。后续模型选择将读取当前版本，可展开修订记录查看变更依据。";
        if (pending.command === "recipe-adopt") outcomeMessage = "外环决定已写入项目，后续配方决策将读取当前有效版本。";
        if (modelCommand) {
          const record = obj(result.model_record), outcome = obj(record.outcome), state = text(record.status, ""), actual = text(outcome.status, "尚未提交行动");
          const labels: Record<string, string> = { completed: "已完成", waiting: "已保存等待", failed: "失败，原记录保留", unknown: "未知，保留原请求核对" };
          pending.uncertain = ["sending", "unknown", "received", "prepared"].includes(state) || actual === "unknown";
          failed = pending.uncertain || ["invalid", "stale", "failed"].includes(state) || actual === "failed";
          if (record.purpose === "plan") {
            const messages: Record<string, string> = {
              proposed: "模型计划建议已保存，可查看反馈依据和预计改善，再决定采用或拒绝。",
              applied: "模型建议已采用为研究计划第" + obj(outcome.research_plan).version + "版。",
              rejected: "计划建议及拒绝理由已保存。",
            };
            outcomeMessage = messages[state] ?? "计划建议需要核对，当前状态为" + state + "，请查看原请求记录。";
          } else if (record.purpose === "recipe") {
            outcomeMessage = state === "proposed" ? "配方候选已保存，可交给改进外环验证并记录采用决定。"
              : "配方模型请求状态为" + state + "，请查看原请求与改进外环记录。";
          } else outcomeMessage = state === "applied" ? `模型选择已保存，原控制器结果：${labels[actual] ?? actual}。请查看本次理由、实际行动与用量。`
            : `模型请求${state === "stale" ? "已过期" : state === "invalid" ? "回答未通过校验" : "未完成"}，原始记录已保留。请核对原请求；没有自动重发。`;
        }
        if (pending.command === "create") {
          lastCreatedProject = text(result.project_id, "");
          const created = obj(JSON.parse(pending.body)); delete created.request_id; lastCreateSignature = JSON.stringify(created);
        }
        selectedCandidate = ""; citations.clear(); if (pending.command === "advance") rationale.value = "";
        if (!pending.uncertain) lastRequest = null;
      }
      if (!pending.uncertain) { if (pending.command === "evidence") evidencePending.delete(targetProject); try { sessionStorage.removeItem(PENDING_KEY); } catch { /* Optional browser note. */ } }
    } catch {
      pending.uncertain = true; failed = true; outcomeMessage = "未取得完整命令回执，不能当作未执行。输入与原请求ID已保留；只读核对后再处理，不自动重发。";
    }
    if (["batch", "continue"].includes(pending.command)) {
      if (pending.uncertain) batchUncertain = pending;
      else if (batchUncertain?.requestId === pending.requestId) batchUncertain = null;
    }
    try { await refresh(); } catch (error) { outcomeMessage += " 保存状态刷新未完成，可稍后只读刷新。"; context = null; announce(error instanceof Error ? error.message : "状态读取失败。", true); }
    if (pending.command === "continue" && pending.uncertain) {
      const saved = items(description.continuations).find(record => record.request_id === pending.requestId
        && record.schema_version === "local-research-continuation-v1" && sameBody(obj(record.body), obj(JSON.parse(pending.body))));
      if (saved) {
        pending.uncertain = false; failed = saved.status === "failed" || saved.status === "needs_review"; accepted = saved;
        outcomeMessage = "已从保存记录确认原任务阶段，没有重新发送。" + continuationStopReason(obj(saved.stop));
      }
    }
    if (pending.command === "plan" && items(obj(current.research_plan).revisions).some(revision => revision.request_id === pending.requestId)) {
      pending.uncertain = false; failed = false; accepted = { status: "completed" }; lastRequest = null;
      outcomeMessage = "研究计划已从保存记录中确认。后续模型选择将读取当前版本，可展开修订记录查看变更依据。";
    }
    if (pending.command === "feedback" && items(current.researcher_feedback).some(record => record.request_id === pending.requestId)) {
      pending.uncertain = false; failed = false; accepted = { status: "completed" }; lastRequest = null;
      outcomeMessage = "研究反馈已从保存记录中确认，将作为后续模型计划的参考。";
    }
    if (pending.command === "recipe-adopt" && items(current.recipe_revisions).some(record => record.request_id === pending.requestId)) {
      pending.uncertain = false; failed = false; accepted = { status: "completed" }; lastRequest = null;
      outcomeMessage = "已从项目保存记录确认外环决定，当前有效配方可供后续决策使用。";
    }
    if (modelPanel.decisionResolved(pending.command, pending.requestId)) {
      pending.uncertain = false; failed = false; accepted = { status: "completed" }; lastRequest = null;
      outcomeMessage = pending.command === "model-plan-adopt" ? "已从原模型请求确认计划采用，当前版本可继续使用。" : "已从原模型请求确认拒绝结果与理由。";
    }
    busy = false; candidates(); downloads(); controls(); showPending(); announce(outcomeMessage, failed);
    return accepted;
  }
  function command(name: string, body: Obj): Pending {
    const id = requestId(name); return { command: name, requestId: id, body: JSON.stringify({ request_id: id, ...body }), uncertain: false };
  }
  form.addEventListener("submit", event => { event.preventDefault(); void (async () => {
    if (!form.reportValidity() || !csv) return;
    try {
      const declaration = spec(), specBytes = new TextEncoder().encode(JSON.stringify(declaration));
      if (specBytes.length > 64 * 1024) throw Error("本次字段声明超过64KiB，请核对输入。");
      const body = { goal: goal.value.trim(), budget_ref: budget.value.trim(), max_tool_calls: Number(toolLimit.value),
        input: { file_name: csv.name, csv_base64: csv.encoded, spec_base64: base64(specBytes) } };
      const signature = JSON.stringify(body);
      if (signature === lastCreateSignature && lastCreatedProject) { announce("这份问题和输入已经创建为保存项目，请从项目列表选择；未再次创建。"); return; }
      const pending = command("create", body); await submit(pending);
    } catch (error) { announce(error instanceof Error ? error.message : "输入尚不完整。", true); }
  })(); });
  projectSelect.addEventListener("change", controls);
  createToggle.addEventListener("click", () => { form.hidden = !form.hidden; createToggle.textContent = form.hidden ? "展开新课题与CSV输入" : "收起新课题输入"; createToggle.setAttribute("aria-expanded", String(!form.hidden)); });
  selectButton.addEventListener("click", () => { context = null; selectedCandidate = ""; citations.clear(); candidates(); void submit(command("select", { project_id: projectSelect.value })); });
  const advance = (wait: boolean): void => {
    if (!context || !activeId() || !rationale.value.trim()) { announce("请先读取当前候选并填写选择理由。", true); return; }
    if (!wait && !items(context.candidates).some(candidate => candidate.id === selectedCandidate)) { announce("请选择当前上下文中的实际候选。", true); return; }
    const proposal = { schema_version: "project-selection-proposal-v1", context_sha256: context.context_sha256,
      provider: { kind: "operator_assistant", label: "本地工作台提交（操作者身份未核验）" }, choice: wait ? { kind: "wait" } : { kind: "execute", candidate_id: selectedCandidate },
      rationale: rationale.value.trim(), evidence_citation_ids: [...citations] };
    void submit(command("advance", { project_id: activeId(), expected_state_version: context.state_version, proposal }));
  };
  executeButton.addEventListener("click", () => advance(false)); waitButton.addEventListener("click", () => advance(true));
  rationale.addEventListener("input", controls);
  reportButton.addEventListener("click", () => { if (activeId() && typeof current.state_version === "number") void submit(command("report", { project_id: activeId(), expected_state_version: current.state_version })); });
  retry.addEventListener("click", () => { if (lastRequest && !lastRequest.uncertain) void submit(lastRequest); });
  refreshButton.addEventListener("click", () => { void (async () => { busy = true; controls(); try { await refresh(); announce(description.enabled !== true ? "本地动作未启用，当前只读取保存记录。" : serverPending() || lastRequest?.uncertain ? "原请求仍待核对，仅刷新了保存状态。" : "已只读刷新保存状态，没有执行新行动。", description.enabled !== true); } catch (error) { announce(error instanceof Error ? error.message : "读取失败。", true); } finally { busy = false; controls(); downloads(); } })(); });
  document.querySelector(".skip-link")?.addEventListener("click", event => { event.preventDefault(); $("main-content").focus({ preventScroll: true }); });
  controls(); downloads();
  try { await refresh(); announce(description.enabled !== true ? "本地动作未启用，当前只读取保存记录；需宿主显式启动写模式。" : serverPending() ? "原请求尚待核对，只读状态已载入。" : activeId() ? "已恢复活动项目；所有新行动仍需你明确提交。" : "工作台已就绪，先提出问题并选择数据。", description.enabled !== true); }
  catch (error) { announce(error instanceof Error ? error.message : "工作台读取失败，可只读刷新。", true); }
  controls(); downloads();
}
