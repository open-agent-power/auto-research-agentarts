/** Explicit local commands above the existing saved-result reader; no automatic research. */
import { $, el } from "./dom";
import { posthocPlanAdviceCases } from "./plan-advice";
import { createStagedSuccessorPreviewPanel } from "./staged-successor-preview";
import { createStagedSuccessorSavePanel } from "./staged-successor-save";
import { createProjectPages, type ProjectOperation } from "./project-pages";
import { createLocalEvidencePanel } from "./local-evidence";
import { createLocalExperiencePanel } from "./local-experience";
import { createLocalBatchPanel, continuationStopReason } from "./local-batch";
import { createLocalModelPanel } from "./local-model";
import { createLocalRecipePanel } from "./local-recipe";
import { createResearchDesignPanel } from "./research-design";
import { progressFeedback, researcherFeedbackItems, sourceQuestionText } from "./project-view";

type Obj = Record<string, unknown>;
type Pending = { command: string; requestId: string; body: string; uncertain: boolean; recoverBatch?: boolean; recoverModel?: boolean; recoverExperience?: boolean; recoverPlan?: boolean; recoverQuality?: boolean; recoverManual?: boolean; recoverStagedHypothesis?: boolean; recoverStagedPrimary?: boolean; stagedPrimaryContext?: Obj; recoverStagedFeedback?: boolean; stagedFeedbackContext?: Obj };
type PlanCaseRef = { case_id: string; case_version: number; bundle_sha256: string; applicability_statement: string };
type PlanAdvice = { projectId: string; snapshot: string; caseId: string; version: number; sha: string };
const obj = (value: unknown): Obj => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const items = (value: unknown): Obj[] => Array.isArray(value) ? value.map(obj) : [];
const text = (value: unknown, fallback = "未记录"): string => typeof value === "string" && value.length ? value : fallback;
const numeric = (value: unknown): string => typeof value === "number" && Number.isFinite(value) ? String(value) : "未记录";
const names = (value: unknown): string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
const sameBody = (left: Obj, right: Obj): boolean => Object.keys(left).length === Object.keys(right).length
  && Object.keys(left).every(key => JSON.stringify(left[key]) === JSON.stringify(right[key]));
function sameValue(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (Array.isArray(left) || Array.isArray(right)) return Array.isArray(left) && Array.isArray(right)
    && left.length === right.length && left.every((item, i) => sameValue(item, right[i]));
  if (left === null || right === null || typeof left !== "object" || typeof right !== "object") return false;
  const a = obj(left), b = obj(right), keys = Object.keys(a).sort(), other = Object.keys(b).sort();
  return keys.length === other.length && keys.every((key, i) => key === other[i] && sameValue(a[key], b[key]));
}
const methodNames: Record<string, string> = {
  "data.tabular-quality-audit": "核对表格质量、重复与声明分组",
  "data.grouped-quality-profile": "查看零值与缺失集中于哪些组",
  "data.numeric-association": "查看数值字段与目标的关联",
  "data.prediction-baseline": "比较保存预测与公平基线",
  "data.prediction-grouped": "核对各组的保存预测误差",
  "data.prediction-sensitivity": "核对移除样本或组后的比较变化",
  "data.ridge-random-validation": "在训练折内拟合并进行随机五折验证",
  "data.ridge-group-validation": "按声明组拆分并训练验证",
  "data.saved-oof-random-diagnostics": "读取随机验证的保存误差明细",
  "data.saved-oof-group-diagnostics": "读取分组验证的保存误差明细",
  "data.prediction-negative-control": "核对实际折内负对照结果",
  "research.source-selection": "读取已登记的来源选区",
  "p02.source-mapping-check": "读取已登记的来源选区",
};
const PENDING_KEY = "autoresearch.local-workbench.pending.v1";
const STAGED_HYPOTHESIS_PENDING_KEY = "autoresearch.local-workbench.staged-hypothesis.v1";
const STAGED_FEEDBACK_PENDING_KEY = "autoresearch.local-workbench.staged-feedback.v1";
const STAGED_PRIMARY_PENDING_KEY = "autoresearch.local-workbench.staged-primary.v1";
const QUALITY_PENDING_KEY = "autoresearch.local-workbench.supplied-quality-adoption.v1";
const MANUAL_PREPARE_KEY = "autoresearch.local-workbench.manual-plan-prepare.v1";
const MANUAL_IMPORT_KEY = "autoresearch.local-workbench.manual-plan-import.v1";
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
  if (JSON.stringify(previous.experience_case_refs ?? null) !== JSON.stringify(saved.experience_case_refs ?? null))
    body.append(el("p", "detail-note", "本次操作者声明的案例引用有变化；原版本引用仍保留在修订记录中。"));
  const model = modelRecords.find(record => {
    const outcome = obj(record.outcome), adopted = obj(outcome.research_plan), context = obj(obj(record.context).selection_context), proposal = obj(record.proposal);
    return !("experience_case_refs" in saved) && record.purpose === "plan" && record.status === "applied" && record.controller_request_id === saved.request_id
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
    feedback.append(el("h4", "", "最近一次来源读取时记录的问题"));
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
  current(): Obj; context(): Obj | null; modelRecords(projectId: string): Obj[]; submit(body: Obj): Promise<Obj | null>;
}): { element: HTMLElement; update(project: Obj): void; setLocked(value: boolean): void; draft(): Obj | null } {
  const section = panel("研究计划", "写下当前问题、准备采取的步骤，以及什么反馈会让你调整路线。"), sourceFeedback = el("div"), preview = el("div", "research-plan-copy");
  section.classList.add("research-plan");
  const editor = el("details", "research-plan-editor"), summary = el("summary", "", "编写计划"), form = el("form"), fields = el("fieldset", "local-fieldset");
  const inputs = new Map<string, HTMLTextAreaElement>();
  for (const definition of planFields) {
    const control = el("textarea"); control.maxLength = definition.maximum; control.required = definition.required; control.rows = definition.key === "steps" ? 4 : 2;
    inputs.set(definition.key, control); fields.append(field(definition.label, control));
  }
  const references = el("section", "local-plan-experience"), referenceList = el("div"), referenceStatus = el("p", "detail-note");
  references.append(el("h4", "", "操作者声明的历史案例引用（可选）"),
    el("p", "detail-note", "最多选择4个当前有效的案例，并逐条说明适用范围与差异；这是操作者声明，未证明模型采用或科学适用。"),
    referenceList, referenceStatus);
  const advice = el("section", "local-plan-experience"), adviceSelect = el("select"), advicePreview = el("p", "detail-note"), adviceStatus = el("p", "detail-note");
  const adviceCopy = el("button", "text-button", "将建议复制到空白计划草稿"), adviceDiscard = el("button", "text-button", "清除建议绑定");
  adviceSelect.setAttribute("aria-label", "选择事后经验生成计划建议"); adviceCopy.type = "button"; adviceDiscard.type = "button";
  advice.append(el("h4", "", "从历史经验构思计划（可选）"), el("p", "detail-note", "选择一个当前有效的已发布事后案例后预览；这只是确定性提示，不调用模型、不保存或执行。仅供未来另行明确操作，不能为已完成 primary 补事前登记或追认 final。"),
    field("选择历史案例", adviceSelect), advicePreview, adviceStatus, adviceCopy, adviceDiscard);
  fields.append(advice, references);
  const status = el("p", "detail-note"), save = el("button", "local-primary", "保存计划"), rebase = el("button", "text-button", "按当前版本继续编辑");
  save.type = "submit"; rebase.type = "button"; rebase.hidden = true;
  const actions = el("div", "local-actions"); actions.append(save, rebase); form.append(fields, status, actions); editor.append(summary, form);
  const history = el("details", "research-plan-history"), historyBody = el("div"); history.append(el("summary", "", "查看修订记录"), historyBody);
  const comparison = el("details", "research-plan-comparison"), comparisonTitle = el("summary"), comparisonBody = el("div");
  comparison.append(comparisonTitle, comparisonBody); comparison.hidden = true;
  section.append(sourceFeedback, preview, comparison, editor, history);
  const drafts = new Map<string, { values: Record<string, string>; stateVersion: number; refs: PlanCaseRef[]; advice: PlanAdvice | null }>();
  let projectId = "", stateVersion = 0, locked = true;
  let selectedRefs: PlanCaseRef[] = [], appliedAdvice: PlanAdvice | null = null, adviceSnapshot = "", adviceKey = "";
  const adviceSteps = "在本项目 validation 总体同时比较 Recall@20 与 MRR@10；在 primary 前由操作者明确两项比较符、阈值及已知结果的分支。";
  const adviceExpected = "按事前登记检查两个总体指标，并在结果未知或原证据不可核验时停查；历史负向子集不等于本项目总体结果。";
  const values = (): Record<string, string> => Object.fromEntries([...inputs].map(([key, control]) => [key, control.value]));
  const keepDraft = (): void => { if (projectId) drafts.set(projectId, { values: values(), stateVersion, refs: selectedRefs.map(ref => ({ ...ref })), advice: appliedAdvice ? { ...appliedAdvice } : null }); };
  const validIdentity = (caseId: unknown, version: unknown, sha: unknown): boolean => typeof caseId === "string" && !!caseId.trim()
    && typeof version === "number" && Number.isSafeInteger(version) && version >= 1 && typeof sha === "string" && /^[0-9a-f]{64}$/.test(sha);
  const sameIdentity = (ref: PlanCaseRef, item: Obj): boolean => ref.case_id === item.case_id && ref.case_version === item.case_version && ref.bundle_sha256 === item.bundle_sha256;
  function available(): Obj[] | null {
    const context = deps.context(), project = deps.current();
    if (!context || context.project_id !== projectId || project.id !== projectId
        || context.state_version !== project.state_version || context.snapshot_ref !== project.snapshot_ref) return null;
    return items(obj(context.experience).cases).filter(item => item.inclusion_status === "active"
      && validIdentity(item.case_id, item.case_version, item.bundle_sha256));
  }
  function adviceCases(): Obj[] { return posthocPlanAdviceCases(deps.current(), deps.context()); }
  const adviceIdentity = (item: Obj): string => JSON.stringify([item.case_id, item.case_version, item.bundle_sha256]);
  function adviceStillValid(binding: PlanAdvice): boolean {
    const project = deps.current(); return binding.projectId === project.id && binding.snapshot === project.snapshot_ref
      && adviceCases().filter(item => item.case_id === binding.caseId && item.case_version === binding.version && item.bundle_sha256 === binding.sha).length === 1;
  }
  function drawAdvice(): void {
    const project = deps.current(), snapshot = text(project.snapshot_ref, ""), same = snapshot === adviceSnapshot;
    if (!same) adviceKey = ""; adviceSnapshot = snapshot; adviceSelect.replaceChildren();
    const blank = el("option", "", "请选择案例"); blank.value = ""; adviceSelect.append(blank);
    for (const item of adviceCases()) { const option = el("option", "", text(item.case_id) + " · v" + numeric(item.case_version)); option.value = adviceIdentity(item); adviceSelect.append(option); }
    adviceSelect.value = [...adviceSelect.options].some(option => option.value === adviceKey) ? adviceKey : "";
    advice.hidden = project.primary_method !== "research.relevance-validation-pair";
  }
  function adviceControls(): void {
    const matches = adviceCases().filter(item => adviceIdentity(item) === adviceSelect.value), selected = matches.length === 1 ? matches[0] : null;
    const steps = inputs.get("steps")!, expected = inputs.get("expected_feedback")!, blank = steps.value.length === 0 && expected.value.length === 0;
    const stale = stateVersion !== deps.current().state_version, valid = appliedAdvice === null || adviceStillValid(appliedAdvice);
    adviceSelect.disabled = locked || stale || !adviceCases().length || appliedAdvice !== null; adviceCopy.disabled = locked || stale || !selected || !blank || appliedAdvice !== null;
    adviceDiscard.hidden = appliedAdvice === null; adviceDiscard.disabled = locked || !appliedAdvice || !blank;
    advicePreview.textContent = selected ? "案例 " + text(selected.case_id) + " · v" + numeric(selected.case_version) + " · SHA-256 " + text(selected.bundle_sha256)
      + "。已曝 validation 的选定负向子集：召回变化近零时排序指标下降；这不是总体均值，也不能证明因果、匿名或迁移。来源仅绑定公开字节，未重新计算或验证签名。建议：" + adviceSteps + " " + adviceExpected
      : "选择同一项目快照中的有效 S109 案例，才会出现建议；未选时没有案例专属建议。";
    adviceStatus.textContent = !valid ? "原建议的项目、快照或案例已变化，不能保存；请手动清空步骤和预期反馈，再清除建议绑定。"
      : appliedAdvice ? "建议已复制到草稿，绑定案例 " + appliedAdvice.caseId + " · v" + appliedAdvice.version + " · SHA-256 " + appliedAdvice.sha + "。请在下方明确勾选同一案例并填写适用范围与差异；不会自动登记、执行或选择阈值。"
      : !blank ? "步骤或预期反馈已有内容；为保护草稿，先手动清空这两项才可复制。"
      : "复制只写空白草稿；比较符、阈值及两分支均由操作者另行填写。";
  }
  adviceSelect.addEventListener("change", () => { adviceKey = adviceSelect.value; adviceControls(); });
  adviceCopy.addEventListener("click", () => {
    const matches = adviceCases().filter(item => adviceIdentity(item) === adviceSelect.value), steps = inputs.get("steps")!, expected = inputs.get("expected_feedback")!;
    if (adviceCopy.disabled || matches.length !== 1 || steps.value.length !== 0 || expected.value.length !== 0
        || adviceSteps.length > steps.maxLength || adviceExpected.length > expected.maxLength || adviceSteps.includes("\0") || adviceExpected.includes("\0")) return;
    const item = matches[0], project = deps.current(); appliedAdvice = {projectId:text(project.id, ""), snapshot:text(project.snapshot_ref, ""),
      caseId:text(item.case_id, ""), version:Number(item.case_version), sha:text(item.bundle_sha256, "")};
    steps.value = adviceSteps; expected.value = adviceExpected; keepDraft(); controls();
  });
  adviceDiscard.addEventListener("click", () => { if (adviceDiscard.disabled) return; appliedAdvice = null; keepDraft(); controls(); });
  function showSavedRefs(parent: HTMLElement, saved: Obj): void {
    const envelope = obj(saved.experience_case_refs), refs = items(envelope.items);
    if (!refs.length) return;
    parent.append(el("h4", "", "操作者保存的案例声明（未核验适用性）"));
    for (const ref of refs) parent.append(el("p", "detail-note", text(ref.case_id) + " · v" + numeric(ref.case_version)
      + " · SHA-256 " + text(ref.bundle_sha256) + " · " + text(ref.applicability_statement)));
  }
  function drawReferences(): void {
    referenceList.replaceChildren();
    const cases = available();
    referenceStatus.textContent = cases === null ? "当前案例快照尚未就绪；已选引用不会自动更换，请先只读刷新。"
      : cases.length ? "勾选当前有效案例；若原版本已撤回或升级，须先移除原身份再明确选择。"
        : "当前没有可选的有效案例；原计划中的历史声明仍保留。";
    for (const ref of selectedRefs.filter(item => !cases?.some(candidate => sameIdentity(item, candidate)))) {
      const row = el("div", "local-plan-reference-unavailable"), remove = el("button", "text-button", "移除不可用的原引用");
      remove.type = "button"; remove.addEventListener("click", () => {
        selectedRefs = selectedRefs.filter(item => item !== ref); keepDraft(); drawReferences(); controls();
      });
      row.append(el("p", "detail-note", "原身份当前不可用 · " + ref.case_id + " · v" + ref.case_version + " · SHA-256 " + ref.bundle_sha256),
        el("p", "detail-note", "原声明 · " + ref.applicability_statement), remove); referenceList.append(row);
    }
    for (const item of cases ?? []) {
      const existing = selectedRefs.find(ref => sameIdentity(ref, item));
      const label = el("label", "local-checkbox"), check = el("input"), note = el("textarea"), block = el("div", "local-plan-reference");
      check.type = "checkbox"; check.checked = !!existing;
      const title = text(obj(item.method_card).question, text(item.case_id));
      check.setAttribute("aria-label", "引用案例 " + text(item.case_id));
      label.append(check, el("span", "", title + " · " + text(item.case_id) + " · v" + numeric(item.case_version)));
      note.maxLength = 1000; note.rows = 2; note.required = !!existing; note.value = existing?.applicability_statement ?? "";
      note.disabled = !existing; note.setAttribute("aria-label", "案例 " + text(item.case_id) + " 的适用范围与差异");
      note.addEventListener("input", () => { const target = selectedRefs.find(ref => sameIdentity(ref, item));
        if (target) target.applicability_statement = note.value; keepDraft(); controls(); });
      check.addEventListener("change", () => {
        if (check.checked) {
          if (selectedRefs.length >= 4 || selectedRefs.some(ref => ref.case_id === item.case_id)) {
            check.checked = false; referenceStatus.textContent = "最多4个不同案例；请先移除同ID的旧身份。"; return;
          }
          selectedRefs.push({ case_id: text(item.case_id, ""), case_version: Number(item.case_version),
            bundle_sha256: text(item.bundle_sha256, ""), applicability_statement: "" });
        } else selectedRefs = selectedRefs.filter(ref => !sameIdentity(ref, item));
        keepDraft(); drawReferences(); controls();
      });
      block.append(label, el("p", "detail-note", "原快照 SHA-256 · " + text(item.bundle_sha256)),
        field("适用范围与差异", note)); referenceList.append(block);
    }
  }
  function controls(): void {
    const stale = stateVersion !== deps.current().state_version;
    const cases = available(), invalidRefs = selectedRefs.some(ref => !cases?.some(item => sameIdentity(ref, item))
      || !ref.applicability_statement.trim() || ref.applicability_statement.length > 1000 || ref.applicability_statement.includes("\0"));
    const invalidAdvice = appliedAdvice !== null && (!adviceStillValid(appliedAdvice) || !selectedRefs.some(ref => ref.case_id === appliedAdvice!.caseId
      && ref.case_version === appliedAdvice!.version && ref.bundle_sha256 === appliedAdvice!.sha && !!ref.applicability_statement.trim()));
    fields.disabled = locked || !projectId; save.disabled = fields.disabled || stale || invalidRefs || invalidAdvice;
    rebase.hidden = !projectId || !stale; rebase.disabled = locked;
    status.textContent = stale ? "项目已更新，草稿已保留。核对当前计划后，可按当前版本继续编辑。"
      : invalidAdvice ? "建议须绑定当前快照的原案例，并由操作者勾选和说明适用差异；失效建议不能保存。"
      : invalidRefs ? "请核对每条所选案例的原身份与适用说明；不可用身份不会自动替换。"
        : "保存后进入项目记录；新计划不会自动更新已有登记，原反馈可能变为未知或最终评价被阻断。";
    adviceControls();
  }
  function update(project: Obj): void {
    if (projectId !== project.id) comparison.open = false;
    projectId = text(project.id, ""); section.hidden = !projectId;
    const plan = obj(project.research_plan), saved = obj(plan.current), draft = drafts.get(projectId);
    stateVersion = draft?.stateVersion ?? Number(project.state_version); appliedAdvice = draft?.advice ?? null;
    selectedRefs = draft ? draft.refs.map(ref => ({ ...ref })) : items(obj(saved.experience_case_refs).items).map(ref => ({
      case_id: text(ref.case_id, ""), case_version: Number(ref.case_version), bundle_sha256: text(ref.bundle_sha256, ""),
      applicability_statement: text(ref.applicability_statement, "") }));
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
      showSavedRefs(feedback, saved);
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
      showSavedRefs(record, revision);
      historyBody.append(record);
    }
    drawReferences(); drawAdvice();
    controls();
  }
  form.addEventListener("input", () => { keepDraft(); controls(); });
  rebase.addEventListener("click", () => {
    stateVersion = Number(deps.current().state_version); keepDraft(); drawReferences(); controls();
  });
  form.addEventListener("submit", async event => {
    event.preventDefault(); if (save.disabled || !form.reportValidity()) return;
    const submittedProject = projectId, content = values(), { reason, ...planText } = content;
    const plan: Obj = { ...planText };
    if (selectedRefs.length) plan.experience_case_refs = { schema_version: "project-plan-experience-refs-v1", items: selectedRefs.map(ref => ({ ...ref })) };
    keepDraft();
    const result = await deps.submit({ project_id: projectId, expected_state_version: stateVersion, plan, reason });
    if (result?.status === "completed") { drafts.delete(submittedProject); update(deps.current()); editor.open = false; summary.focus(); }
  });
  function draft(): Obj | null {
    editor.open = true;
    const content = values(), cases = available();
    const invalidFields = planFields.some(def => content[def.key].length > def.maximum || content[def.key].includes("\0")
      || (def.required && !content[def.key].trim()));
    const invalidRefs = selectedRefs.some(ref => !cases?.some(item => sameIdentity(ref, item))
      || !ref.applicability_statement.trim() || ref.applicability_statement.length > 1000 || ref.applicability_statement.includes("\0"));
    const invalidAdvice = appliedAdvice !== null && (!adviceStillValid(appliedAdvice) || !selectedRefs.some(ref => ref.case_id === appliedAdvice!.caseId
      && ref.case_version === appliedAdvice!.version && ref.bundle_sha256 === appliedAdvice!.sha && !!ref.applicability_statement.trim()));
    if (!projectId || stateVersion !== deps.current().state_version || invalidFields || invalidRefs || invalidAdvice) return null;
    const { reason, ...planText } = content, plan: Obj = { ...planText };
    if (selectedRefs.length) plan.experience_case_refs = { schema_version: "project-plan-experience-refs-v1", items: selectedRefs.map(ref => ({ ...ref })) };
    keepDraft(); return { project_id: projectId, expected_state_version: stateVersion, plan, reason };
  }
  return { element: section, update, draft, setLocked(value): void { locked = value; controls(); } };
}

function createStagedHypothesisPanel(deps: {
  current(): Obj; context(): Obj | null; submit(body: Obj): Promise<Obj | null>; submitPrimary(body: Obj, identity: Obj): Promise<Obj | null>; submitFeedback(body: Obj, identity: Obj): Promise<Obj | null>;
}): { element: HTMLElement; update(project: Obj): void; setLocked(value: boolean): void } {
  const section = panel("事前双指标登记", "仅保存操作者的预期，不执行检索、审计或模型。");
  const saved = el("div"), form = el("form"), fields = el("fieldset", "local-fieldset"), status = el("p", "detail-note");
  const future = el("p", "detail-note"), controlsByMetric: { metric: string; operator: HTMLSelectElement; threshold: HTMLInputElement }[] = [];
  for (const metric of ["recall@20", "mrr@10"]) {
    const operator = el("select"), threshold = el("input");
    operator.required = true; operator.setAttribute("aria-label", metric + " 比较符");
    for (const [value, label] of [["", "请选择比较符"], ["gt", ">"], ["gte", "≥"], ["lt", "<"], ["lte", "≤"], ["eq", "="]]) {
      const option = el("option", "", label); option.value = value; operator.append(option);
    }
    threshold.type = "number"; threshold.step = "any"; threshold.min = "-1"; threshold.max = "1"; threshold.required = true;
    threshold.setAttribute("aria-label", metric + " 阈值");
    fields.append(field(metric + " 比较", operator), field(metric + " 差值阈值", threshold));
    controlsByMetric.push({ metric, operator, threshold });
  }
  const branches: { outcome: string; input: HTMLSelectElement }[] = [];
  for (const [outcome, label] of [["condition_met", "两项均满足时"], ["condition_not_met", "两项已知但至少一项不满足时"]]) {
    const input = el("select"); input.required = true; input.setAttribute("aria-label", label);
    for (const [value, title] of [["", "请选择"], ["wait", "等待"], ["audit", "建议原保存审计（以后需明确提交，可能消耗1次工具）"]]) {
      const option = el("option", "", title); option.value = value; input.append(option);
    }
    fields.append(field(label, input)); branches.push({ outcome, input });
  }
  const submitButton = el("button", "local-primary", "仅登记事前条件"); submitButton.type = "submit";
  fields.prepend(el("p", "detail-note", "差值均为 validation 的 TF-IDF 减 BM25。必须由你填写比较符和阈值；原登记策略把未知映射为等待；下方严格反馈入口遇未知会停查，不保存等待记录。0 是有效值，普通入口不自动受此约束。"),
    el("p", "detail-note", "先保存计划及所需历史案例引用。登记固定当时计划；以后改计划可能使反馈未知。此处不登记 final，也不保证以后仍可作前瞻 final；反馈分支须以后另行明确操作。"), future);
  form.append(fields, status, submitButton); section.append(saved, form);
  const run = el("div", "local-panel"), runTitle = el("h3", "", "按原登记明确执行 primary"), runFields = el("fieldset", "local-fieldset");
  const registrationSelect = el("select"), reason = input("", 4000), execute = el("button", "action-button primary", "执行这条登记的 primary"), runStatus = el("p", "detail-note");
  registrationSelect.setAttribute("aria-label", "选择原事前登记"); reason.setAttribute("aria-label", "执行理由");
  execute.type = "button"; execute.dataset.testid = "staged-primary-execute";
  runFields.append(field("选择原事前登记", registrationSelect), field("执行理由", reason));
  run.append(runTitle, el("p", "detail-note", "明确点击后最多消耗 1 次原有工具额度：读取登记的共享语料，并对 dev 与 validation 执行 BM25 和 TF-IDF 排名与评分。不执行 final、模型或拟合。已保存结果不等于科学批准。"),
    runFields, runStatus, execute); section.append(run);
  const feedbackRun = el("div", "local-panel"), feedbackFields = el("fieldset", "local-fieldset"), feedbackSelect = el("select");
  const feedbackInfo = el("p", "detail-note"), feedbackResult = el("p", "detail-note");
  const feedbackExecute = el("button", "action-button primary", "按原登记处理已保存反馈");
  feedbackSelect.setAttribute("aria-label", "选择已完成的事前登记"); feedbackExecute.type = "button"; feedbackExecute.dataset.testid = "staged-feedback-execute";
  feedbackFields.append(field("选择已完成的事前登记", feedbackSelect));
  feedbackRun.append(el("h3", "", "按事前登记处理反馈"), el("p", "detail-note", "明确点击才处理：已知审计分支最多使用 1 次本地工具，读取已保存的 dev、validation 结果及共享语料；共享语料可能包含 final 目标段落。不新增排名、评分、拟合、模型或 final 评估。等待不使用额外工具。"), feedbackFields, feedbackInfo, feedbackResult, feedbackExecute); section.append(feedbackRun);
  let feedbackSnapshot = "";
  function feedbackEligible(): {project:Obj; context:Obj; choice:Obj; item:Obj}[] {
    const project = deps.current(), context = deps.context(), projection = obj(project.staged_primary_choices), rows = items(projection.items);
    if (!context || project.id !== projectId || context.project_id !== projectId || projection.project_id !== projectId
        || projection.schema_version !== "staged-primary-choices-v1" || projection.verification !== "registration_metadata_only"
        || projection.manager_ownership_verified !== false || projection.snapshot_ref !== project.snapshot_ref || projection.state_version !== project.state_version
        || context.snapshot_ref !== project.snapshot_ref || context.state_version !== project.state_version || context.run_id !== project.run_id
        || !Array.isArray(context.blockers) || context.blockers.length !== 0
        || typeof context.context_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(context.context_sha256)
        || !sameValue(obj(context.hypothesis_feedback), obj(project.hypothesis_feedback))) return [];
    const budget = obj(context.budget), currentBudget = obj(project.budget);
    if (!Number.isSafeInteger(budget.local_tool_call_limit) || !Number.isSafeInteger(budget.local_tool_dispatches)
        || budget.local_tool_call_limit !== currentBudget.local_tool_call_limit || budget.local_tool_dispatches !== currentBudget.local_tool_dispatches) return [];
    const ids = rows.map(r => text(r.registration_request_id, "")), futures = rows.map(r => text(r.controller_request_id, ""));
    if (ids.some(id => !id) || futures.some(id => !id) || new Set(ids).size !== ids.length || new Set(futures).size !== futures.length) return [];
    const priorView = obj(project.staged_feedback_parents);
    if (project.staged_feedback_parents !== undefined && (priorView.schema_version !== "staged-feedback-parent-view-v1"
        || priorView.verification !== "state_fields_only_not_claim_sql_or_artifacts" || priorView.project_id !== projectId
        || priorView.run_id !== project.run_id || priorView.snapshot_ref !== project.snapshot_ref || priorView.state_version !== project.state_version)) return [];
    const priorFeedback = items(priorView.items);
    if (new Set(priorFeedback.map(parent => text(parent.request_id, ""))).size !== priorFeedback.length) return [];
    const feedback = items(obj(context.hypothesis_feedback).items);
    const validBranch = (value:unknown):boolean => sameValue(value, {kind:"wait"}) || sameValue(value, {kind:"method", method_id:"research.relevance-validation-saved-audit"});
    return rows.flatMap(choice => {
      const matches = feedback.filter(item => item.request_id === choice.registration_request_id && item.registration_sha256 === choice.registration_sha256 && item.controller_request_id === choice.controller_request_id);
      if (matches.length !== 1) return [];
      const item = matches[0], candidate = obj(choice.candidate), conditions = items(obj(item.condition).all), branches = obj(item.branches), values = item.value;
      const actions = items(project.actions).filter(a => a.id === item.action_id && a.result_sha256 === item.result_sha256 && a.command === "research.relevance-validation-pair" && a.status === "completed");
      if (priorFeedback.some(parent => parent.registration_request_id === choice.registration_request_id)
          || choice.plan_matches !== true || choice.source_matches !== true || choice.code_matches !== true || choice.plan_version !== obj(context.research_plan).version
          || choice.source_snapshot_sha256 !== context.source_snapshot_sha256 || ![choice.registration_sha256, choice.plan_sha256, item.result_sha256].every(v => typeof v === "string" && /^[0-9a-f]{64}$/.test(v))
          || candidate.method_id !== "research.relevance-validation-pair" || candidate.evaluation_ref !== "staged-relevance-development-v1" || Object.keys(obj(candidate.parameters)).length !== 0
          || !sameValue(item.candidate, candidate) || !["condition_met", "condition_not_met"].includes(text(item.outcome, "")) || item.unknown_reason !== null
          || !Array.isArray(values) || values.length !== 2 || values.some(v => typeof v !== "number" || !Number.isFinite(v) || v < -1 || v > 1)
          || conditions.length !== 2 || new Set(conditions.map(c => c.metric)).size !== 2 || conditions.some(c => !["recall@20", "mrr@10"].includes(text(c.metric, "")) || !["gt", "gte", "lt", "lte", "eq"].includes(text(c.operator, "")) || typeof c.threshold !== "number" || !Number.isFinite(c.threshold))
          || Object.keys(branches).sort().join(",") !== "condition_met,condition_not_met" || !validBranch(branches.condition_met) || !validBranch(branches.condition_not_met) || actions.length !== 1) return [];
      const check = (c:Obj, v:number):boolean => c.operator === "gt" ? v > Number(c.threshold) : c.operator === "gte" ? v >= Number(c.threshold) : c.operator === "lt" ? v < Number(c.threshold) : c.operator === "lte" ? v <= Number(c.threshold) : v === Number(c.threshold);
      if ((item.outcome === "condition_met") !== conditions.every((c, i) => check(c, values[i] as number))) return [];
      return [{project, context, choice, item}];
    });
  }
  function renderFeedback():void {
    const snapshot = text(deps.current().snapshot_ref, ""), prior = snapshot === feedbackSnapshot ? feedbackSelect.value : "";
    if (snapshot !== feedbackSnapshot) feedbackResult.textContent = "";
    feedbackSnapshot = snapshot; feedbackSelect.replaceChildren(); const empty = el("option", "", "请选择已完成登记"); empty.value = ""; feedbackSelect.append(empty);
    for (const entry of feedbackEligible()) { const option = el("option", "", text(entry.choice.registration_request_id) + " · " + text(entry.choice.registration_sha256).slice(0, 12)); option.value = text(entry.choice.registration_request_id, ""); feedbackSelect.append(option); }
    feedbackSelect.value = [...feedbackSelect.options].some(option => option.value === prior) ? prior : "";
    feedbackRun.hidden = deps.current().primary_method !== "research.relevance-validation-pair";
  }
  function feedbackControls():void {
    const entries = feedbackEligible(), chosen = entries.find(entry => entry.choice.registration_request_id === feedbackSelect.value);
    feedbackFields.disabled = locked || !entries.length; feedbackExecute.disabled = locked || !chosen;
    const branchLabel = (value:unknown):string => obj(value).kind === "wait" ? "等待" : "保存结果审计";
    const conditionLabel = (entry:{item:Obj}):string => items(obj(entry.item.condition).all).map((condition, index) =>
      text(condition.metric) + " " + ({gt:">", gte:"≥", lt:"<", lte:"≤", eq:"="} as Record<string,string>)[text(condition.operator, "")]
      + " " + numeric(condition.threshold) + "，实际 " + numeric((entry.item.value as unknown[])[index])).join("；");
    feedbackInfo.textContent = chosen ? "登记 " + text(chosen.choice.registration_request_id) + " · SHA " + text(chosen.choice.registration_sha256)
      + " · primary " + text(chosen.item.action_id) + " · 结果 SHA " + text(chosen.item.result_sha256)
      + " · 原计划 SHA " + text(chosen.choice.plan_sha256) + " · validation 总体条件：" + conditionLabel(chosen)
      + " · 结果 " + (chosen.item.outcome === "condition_met" ? "两项均满足" : "至少一项不满足")
      + " · 原满足分支：" + branchLabel(obj(chosen.item.branches).condition_met) + "；原不满足分支：" + branchLabel(obj(chosen.item.branches).condition_not_met)
      + " · 工具已派发/上限 " + numeric(obj(chosen.context.budget).local_tool_dispatches) + "/" + numeric(obj(chosen.context.budget).local_tool_call_limit)
      + "。登记分支与实际决策分开：候选不可用或预算不足时可实际等待。此 GET 仅为快照提示，未认证原 manager claims；提交时核原链。S108 子集经验不是本次总体值。"
      : "选择当前计划和来源匹配、primary 完成且两个总体条件均已知的登记。未知、缺失、不一致或已有原反馈时须核对原记录；不创建替代请求。旧 pin 不自动迁移。";
  }
  feedbackSelect.addEventListener("change", feedbackControls);
  feedbackExecute.addEventListener("click", () => { void (async () => {
    const entry = feedbackEligible().find(value => value.choice.registration_request_id === feedbackSelect.value);
    if (!entry || feedbackExecute.disabled) return;
    const id = requestId("staged-feedback"), body = {request_id:id, project_id:projectId, expected_state_version:entry.context.state_version,
      registration_request_id:entry.choice.registration_request_id, registration_sha256:entry.choice.registration_sha256, primary_action_id:entry.item.action_id};
    const identity = {snapshot_ref:entry.context.snapshot_ref, context_sha256:entry.context.context_sha256, source_snapshot_sha256:entry.context.source_snapshot_sha256,
      plan_sha256:entry.choice.plan_sha256, plan_version:entry.choice.plan_version, primary_result_sha256:entry.item.result_sha256,
      candidate_id:obj(entry.choice.candidate).id, feedback:entry.item, audit_candidates:items(entry.context.candidates).filter(candidate => candidate.method_id === "research.relevance-validation-saved-audit" && sameValue(candidate.parameters, {based_on_action_id:entry.item.action_id, based_on_result_sha256:entry.item.result_sha256}))};
    const result = await deps.submitFeedback(body, identity);
    if (result) { const controller = obj(result.controller), proposal = obj(controller.selection_proposal);
      feedbackResult.textContent = "原链已核对 · 实际状态 " + text(controller.status) + " · 实际选择 " + JSON.stringify(proposal.choice) + " · 原记录理由 " + text(proposal.rationale) + "."; }
  })(); });
  let projectId = "", futureId = "", locked = true;
  let choicesSnapshot = "";
  function eligible(): { project:Obj; context:Obj; choice:Obj; item:Obj }[] {
    const project = deps.current(), context = deps.context(), projection = obj(project.staged_primary_choices), rows = items(projection.items);
    if (!context || project.id !== projectId || context.project_id !== projectId || projection.project_id !== projectId
        || projection.schema_version !== "staged-primary-choices-v1" || projection.verification !== "registration_metadata_only"
        || projection.manager_ownership_verified !== false || projection.snapshot_ref !== project.snapshot_ref
        || projection.state_version !== project.state_version || context.snapshot_ref !== project.snapshot_ref
        || context.state_version !== project.state_version || context.run_id !== project.run_id || items(context.blockers).length
        || typeof context.context_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(context.context_sha256)
        || !sameValue(obj(context.hypothesis_feedback), obj(project.hypothesis_feedback))) return [];
    const budget = obj(context.budget), currentBudget = obj(project.budget);
    if (!Number.isSafeInteger(budget.local_tool_call_limit) || !Number.isSafeInteger(budget.local_tool_dispatches)
        || budget.local_tool_call_limit !== currentBudget.local_tool_call_limit || budget.local_tool_dispatches !== currentBudget.local_tool_dispatches
        || Number(budget.local_tool_dispatches) >= Number(budget.local_tool_call_limit)) return [];
    const ids = rows.map(r => text(r.registration_request_id, "")), futures = rows.map(r => text(r.controller_request_id, ""));
    if (ids.some(id => !id) || futures.some(id => !id) || new Set(ids).size !== ids.length || new Set(futures).size !== futures.length) return [];
    const feedback = items(obj(context.hypothesis_feedback).items), candidates = items(context.candidates);
    return rows.flatMap(choice => {
      const matches = feedback.filter(item => item.request_id === choice.registration_request_id && item.registration_sha256 === choice.registration_sha256
        && item.controller_request_id === choice.controller_request_id);
      const candidate = obj(choice.candidate), available = candidates.filter(c => sameValue(c, candidate));
      const conditions = items(obj(matches[0]?.condition).all), branches = obj(matches[0]?.branches);
      const validBranch = (value: unknown): boolean => sameValue(value, {kind:"wait"})
        || sameValue(value, {kind:"method", method_id:"research.relevance-validation-saved-audit"});
      if (choice.plan_matches !== true || choice.source_matches !== true || choice.code_matches !== true
          || choice.plan_version !== obj(context.research_plan).version || choice.source_snapshot_sha256 !== context.source_snapshot_sha256
          || typeof choice.registration_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(choice.registration_sha256)
          || typeof choice.plan_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(choice.plan_sha256)
          || candidate.method_id !== "research.relevance-validation-pair" || candidate.evaluation_ref !== "staged-relevance-development-v1"
          || Object.keys(obj(candidate.parameters)).length !== 0 || available.length !== 1 || matches.length !== 1
          || matches[0].outcome !== "unknown" || matches[0].unknown_reason !== "controller_not_started"
          || matches[0].value !== null || matches[0].action_id !== null || matches[0].result_sha256 !== null
          || conditions.length !== 2 || new Set(conditions.map(c => c.metric)).size !== 2
          || conditions.some(c => !["recall@20", "mrr@10"].includes(text(c.metric, ""))
            || !["gt", "gte", "lt", "lte", "eq"].includes(text(c.operator, ""))
            || typeof c.threshold !== "number" || !Number.isFinite(c.threshold))
          || Object.keys(branches).sort().join(",") !== "condition_met,condition_not_met"
          || !validBranch(branches.condition_met) || !validBranch(branches.condition_not_met)
          || !sameValue(matches[0].candidate, candidate)) return [];
      return [{project, context, choice, item:matches[0]}];
    });
  }
  function renderPrimary(): void {
    const project = deps.current(), snapshot = text(project.snapshot_ref, ""), prior = snapshot === choicesSnapshot ? registrationSelect.value : "";
    if (snapshot !== choicesSnapshot) reason.value = "";
    choicesSnapshot = snapshot; registrationSelect.replaceChildren();
    const empty = el("option", "", "请选择已登记条件"); empty.value = ""; registrationSelect.append(empty);
    for (const entry of eligible()) {
      const option = el("option", "", text(entry.choice.registration_request_id) + " · " + text(entry.choice.registration_sha256).slice(0, 12));
      option.value = text(entry.choice.registration_request_id, ""); registrationSelect.append(option);
    }
    registrationSelect.value = [...registrationSelect.options].some(option => option.value === prior) ? prior : "";
    run.hidden = project.primary_method !== "research.relevance-validation-pair";
  }
  function primaryControls(): void {
    const entries = eligible(), chosen = entries.find(entry => entry.choice.registration_request_id === registrationSelect.value);
    runFields.disabled = locked || !entries.length; execute.disabled = locked || !chosen || !reason.value.trim();
    runStatus.textContent = chosen ? "原登记 " + text(chosen.choice.registration_request_id) + " · SHA-256 " + text(chosen.choice.registration_sha256)
      + " · 原 Controller ID " + text(chosen.choice.controller_request_id) + " · 计划版本 " + numeric(chosen.choice.plan_version)
      + " · 计划 SHA " + text(chosen.choice.plan_sha256) + " · 项目快照 " + text(chosen.context.snapshot_ref)
      + " · 选择上下文 SHA " + text(chosen.context.context_sha256) + " · 来源快照 " + text(chosen.context.source_snapshot_sha256)
      + " · 候选 " + text(obj(chosen.choice.candidate).id) + " · 工具已派发/上限 " + numeric(obj(chosen.context.budget).local_tool_dispatches)
      + "/" + numeric(obj(chosen.context.budget).local_tool_call_limit) + " · 条件 " + JSON.stringify(chosen.item.condition)
      + "。此快照提示尚未认证 manager 归属；提交时由原记录核验。"
      : "选择匹配当前项目、计划、来源、候选和剩余额度的登记；条件未知不等于0。旧源码 pin 不自动升级。";
  }
  function options(): { project: Obj; context: Obj; candidate: Obj } | null {
    const project = deps.current(), context = deps.context();
    if (!context || project.id !== projectId || context.project_id !== projectId
        || context.state_version !== project.state_version || context.snapshot_ref !== project.snapshot_ref
        || project.primary_method !== "research.relevance-validation-pair" || items(context.blockers).length
        || typeof obj(obj(project.research_plan).current).version !== "number") return null;
    const candidates = items(context.candidates).filter(c => c.method_id === "research.relevance-validation-pair"
      && c.evaluation_ref === "staged-relevance-development-v1" && Object.keys(obj(c.parameters)).length === 0);
    return candidates.length === 1 ? { project, context, candidate: candidates[0] } : null;
  }
  function update(project: Obj): void {
    const id = text(project.id, "");
    if (id !== projectId) { projectId = id; futureId = id ? requestId("staged-primary") : ""; form.reset(); }
    section.hidden = project.primary_method !== "research.relevance-validation-pair";
    future.textContent = futureId ? "未来 Controller ID（仅引用、不是预留或授权）：" + futureId : "";
    saved.replaceChildren();
    for (const item of items(obj(project.hypothesis_feedback).items)) {
      if (obj(item.candidate).method_id !== "research.relevance-validation-pair") continue;
      const outcome = text(item.outcome), message = outcome === "condition_met" ? "条件满足" : outcome === "condition_not_met" ? "条件未满足" : "未知，等待核对";
      saved.append(el("p", "detail-note", "登记 " + text(item.request_id) + " · " + message + " · 原 Controller ID " + text(item.controller_request_id)),
        el("p", "detail-note", "固定条件：" + JSON.stringify(item.condition) + "；值：" + (item.value == null ? "未知" : JSON.stringify(item.value))
          + (item.unknown_reason ? "；原因：" + text(item.unknown_reason) : "")),
        el("p", "detail-note", "原登记 SHA-256：" + text(item.registration_sha256) + "；固定分支：" + JSON.stringify(item.branches ?? null)
          + "。审计分支仍需以后另行明确提交。"));
    }
    renderPrimary(); renderFeedback(); controls();
  }
  function controls(): void {
    const ready = options() !== null;
    fields.disabled = locked || !ready; submitButton.disabled = locked || !ready;
    status.textContent = ready ? "登记不使用研究工具；后续行动必须另行明确授权。" : "需在当前项目保存计划，并只读刷新到唯一可用的 staged primary。";
    primaryControls(); feedbackControls();
  }
  form.addEventListener("submit", event => { event.preventDefault(); void (async () => {
    const selected = options(); if (!selected || submitButton.disabled || !form.reportValidity()) return;
    const conditions = controlsByMetric.map(({metric, operator, threshold}) => ({metric, operator:operator.value, threshold:Number(threshold.value)}));
    if (controlsByMetric.some(({threshold}) => !threshold.value.trim() || !Number.isFinite(Number(threshold.value)) || Number(threshold.value) < -1 || Number(threshold.value) > 1)) return;
    const selectedBranches = Object.fromEntries(branches.map(({outcome, input}) => [outcome,
      input.value === "wait" ? {kind:"wait"} : {kind:"method", method_id:"research.relevance-validation-saved-audit"}]));
    const result = await deps.submit({project_id:projectId, expected_state_version:selected.context.state_version,
      hypothesis:{candidate_id:selected.candidate.id, controller_request_id:futureId, conditions, branches:selectedBranches}});
    if (result?.status === "completed") { futureId = requestId("staged-primary"); form.reset(); update(deps.current()); }
  })(); });
  registrationSelect.addEventListener("change", primaryControls); reason.addEventListener("input", primaryControls);
  execute.addEventListener("click", () => { void (async () => {
    const entry = eligible().find(value => value.choice.registration_request_id === registrationSelect.value);
    if (!entry || execute.disabled || !reason.value.trim()) return;
    const body = {request_id:entry.choice.controller_request_id, project_id:projectId, expected_state_version:entry.context.state_version,
      registration_request_id:entry.choice.registration_request_id, registration_sha256:entry.choice.registration_sha256, reason:reason.value};
    const identity = {snapshot_ref:entry.context.snapshot_ref, context_sha256:entry.context.context_sha256,
      source_snapshot_sha256:entry.context.source_snapshot_sha256, candidate_id:obj(entry.choice.candidate).id,
      plan_sha256:entry.choice.plan_sha256, plan_version:entry.choice.plan_version};
    await deps.submitPrimary(body, identity);
  })(); });
  return { element:section, update, setLocked(value):void { locked = value; controls(); } };
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
  for (const value of [1, 2, 3, 4, 5, 6, 7, 8]) { const option = el("option", "", value + "次本地工具调用"); option.value = String(value); toolLimit.append(option); }
  toolLimit.value = "2";
  const budget = input("shared-historical:existing-cap5CNY;cash-settlement-unknown;native-model0;host-usage-separate", 500); budget.required = true;
  const importFile = el("input"); importFile.type = "file"; importFile.accept = ".json,application/json";
  const importNote = el("p", "detail-note", "可导入已有spec.json填充声明；表单修改会生成本次spec，原导入文件不会被改写。");
  const clearImport = el("button", "quiet-button", "改用当前CSV直接声明"); clearImport.type = "button";
  const advanced = el("details", "local-advanced"); advanced.append(el("summary", "", "已有字段声明与预算归属（可选）"), field("导入spec.json", importFile), importNote, clearImport, field("历史预算归属", budget));
  createFields.append(field("要核对的问题", goal), field("CSV / TSV文件", csvFile), fileStatus,
    field("分隔符", delimiter), roles);
  const declarations = el("div", "local-form-grid"); declarations.append(field("数据集标签", dataset), field("每行代表什么", sample),
    field("来源URL或本地派生标识", url), field("许可与待核对范围", license), field("目标字段（可选）", target), field("目标单位（声明）", unit),
    field("本地累计调用上限", toolLimit, "本项目累计允许1至8次，默认2次。质量核对加完整三项设计验证需至少4次；模型、拟合和来源额度分别记账。"));
  createFields.append(declarations, advanced);
  const createButton = el("button", "action-button primary", "创建项目，不执行方法"); createButton.type = "submit";
  const createToggle = el("button", "quiet-button", "收起新课题输入"); createToggle.type = "button";
  form.id = "local-create-form"; createToggle.setAttribute("aria-controls", form.id); createToggle.setAttribute("aria-expanded", "true");
  form.append(createFields, createButton); createSection.append(createToggle, form);

  const runSection = panel("选择下一步行动", "候选来自当前项目的真实条件和预算。选择一个候选并填写理由，或明确保存等待。");
  const contextStatus = el("p", "detail-note", "创建或选择项目后读取候选。"); contextStatus.setAttribute("aria-live", "polite");
  const candidateList = el("div", "local-candidates"), citationList = el("div", "local-citations");
  const rationale = el("textarea"); rationale.rows = 3; rationale.maxLength = 4000; rationale.placeholder = "说明为何现在执行这个检查，或为何等待。";
  const executeButton = el("button", "action-button primary", "明确执行所选候选一次"); executeButton.type = "button";
  const waitButton = el("button", "action-button", "本次选择等待"); waitButton.type = "button";
  const reportButton = el("button", "action-button primary", "生成当前快照报告"); reportButton.type = "button";
  reportButton.title = "只汇总已保存记录，不继续研究。";
  const runActions = el("div", "local-actions"); runActions.append(executeButton, waitButton);
  runSection.append(contextStatus, candidateList, field("这次选择的理由", rationale), citationList, runActions,
    el("p", "detail-note", "等待仅保存本次选择，不表示项目暂停或方法耗尽。"));

  let description: Obj = {}, current: Obj = {}, context: Obj | null = null, successorScan: Obj | null = null, successorGlobalScan: Obj | null = null, busy = false, loadingFile = false;
  let successorGeneration = 0;
  let selectedCandidate = "", citations = new Set<string>(), lastRequest: Pending | null = null;
  let batchUncertain: Pending | null = null;
  let csv: { name: string; bytes: Uint8Array; encoded: string; sha: string; decoded: string } | null = null;
  let imported: Obj | null = null, headers: string[] = [], roleInputs = new Map<string, Record<string, HTMLInputElement>>();
  let fileGeneration = 0, lastCreateSignature = "", lastCreatedProject = "";
  const evidencePending = new Map<string, Pending>();
  const selectedRoles = (kind: string): string[] => headers.filter(name => roleInputs.get(name)?.[kind].checked);
  const activeId = (): string => text(description.active_project_id, "");
  const successorStoragePending = (): boolean => {
    try { return localStorage.getItem("autoresearch.local-workbench.staged-successor.marker.v1") !== null
      || sessionStorage.getItem("autoresearch.local-workbench.staged-successor.session.v1") !== null; }
    catch { return true; }
  };
  const validSuccessorScan = (scan: Obj | null, project: Obj): boolean => {
    if (!scan || scan.schema_version !== "staged-successor-pending-v1" || scan.verification !== "manager_rows_only_not_project_claims"
      || scan.project_id !== project.id || scan.run_id !== project.run_id || scan.snapshot_ref !== project.snapshot_ref
      || scan.state_version !== project.state_version || scan.status !== "available" || !Number.isSafeInteger(scan.total)
      || typeof scan.total !== "number" || scan.total < 0 || !Number.isSafeInteger(scan.shown) || scan.shown !== Math.min(scan.total, 8)
      || scan.truncated !== (scan.total > 8) || !Array.isArray(scan.items) || scan.items.length !== scan.shown) return false;
    const entries = scan.items.map(obj);
    return entries.every(item => typeof item.request_id === "string" && item.request_id.length > 0 && item.status === "preparing")
      && new Set(entries.map(item => item.request_id)).size === entries.length;
  };
  const validSuccessorGlobalScan = (): boolean => {
    const scan = successorGlobalScan, projects = items(description.projects);
    if (!scan || scan.schema_version !== "staged-successor-global-pending-v1" || scan.verification !== "manager_rows_only_not_project_claims"
      || scan.active_project_id !== null || scan.status !== "available" || typeof scan.total !== "number" || !Number.isSafeInteger(scan.total) || scan.total < 0
      || !Number.isSafeInteger(scan.shown) || scan.shown !== Math.min(scan.total, 8) || scan.truncated !== (scan.total > 8)
      || !Array.isArray(scan.project_ids) || scan.project_ids.length > Number(scan.shown)
      || scan.project_ids.some(id => typeof id !== "string" || !id || !projects.some(project => project.id === id))
      || new Set(scan.project_ids).size !== scan.project_ids.length || (scan.total === 0 && scan.project_ids.length !== 0)
      || (scan.total > 0 && scan.project_ids.length === 0)) return false;
    return true;
  };
  const successorBlocked = (): boolean => successorStoragePending() || (activeId()
    ? !validSuccessorScan(successorScan, current) || successorScan!.total !== 0
    : !validSuccessorGlobalScan() || successorGlobalScan!.total !== 0);
  const canSelectSuccessorProject = (projectId: string): boolean => {
    if (activeId() || !validSuccessorGlobalScan() || successorGlobalScan!.truncated !== false || !projectId) return false;
    if (successorStoragePending()) {
      try { const marker = obj(JSON.parse(localStorage.getItem("autoresearch.local-workbench.staged-successor.marker.v1") ?? "null"));
        return marker.schema_version === "staged-successor-request-marker-v1" && marker.project_id === projectId
          && typeof marker.request_id === "string" && !!marker.request_id && typeof marker.owner === "string" && !!marker.owner
          && typeof marker.body_sha256 === "string" && /^[a-f0-9]{64}$/.test(marker.body_sha256); }
      catch { return false; }
    }
    return Array.isArray(successorGlobalScan!.project_ids) && successorGlobalScan!.project_ids.includes(projectId);
  };
  async function scanSuccessor(projectId: string, snapshot: string): Promise<Obj> {
    const scan = await read("/api/local-workbench/staged-feedback-plan-pending.json?project_id=" + encodeURIComponent(projectId) + "&snapshot_ref=" + encodeURIComponent(snapshot));
    if (projectId !== activeId() || current.id !== projectId) throw Error("活动项目已变化；请保留原 ID 并停查。");
    const basis = current.snapshot_ref === snapshot ? current : await read("/api/project");
    if (projectId !== activeId() || basis.id !== projectId || basis.snapshot_ref !== snapshot || !validSuccessorScan(scan, basis))
      throw Error("后续计划未决状态不可核对；请保留原 ID 并停查。");
    if (current.snapshot_ref === snapshot) successorScan = scan;
    return scan;
  }
  const savedQualityRequest = (): Pending | null => {
    try {
      const saved = obj(JSON.parse(sessionStorage.getItem(QUALITY_PENDING_KEY) ?? "null"));
      const body = obj(JSON.parse(text(saved.body, "")));
      if (saved.command !== "model-supplied-quality-plan-adopt" || typeof saved.body !== "string"
          || Object.keys(body).sort().join(",") !== "expected_state_version,host_request_id,project_id,registration_request_id,request_id"
          || typeof body.expected_state_version !== "number" || !Number.isSafeInteger(body.expected_state_version)
          || ![body.request_id, body.project_id, body.host_request_id, body.registration_request_id].every(v => typeof v === "string" && v.length > 0)) return null;
      return {command: saved.command, requestId: text(body.request_id, ""), body: saved.body, uncertain: true};
    } catch { return null; }
  };
  const hasQualityRequest = (): boolean => { try { return sessionStorage.getItem(QUALITY_PENDING_KEY) !== null; } catch { return false; } };
  const savedStagedHypothesis = (): Pending | null => {
    try {
      const value = obj(JSON.parse(sessionStorage.getItem(STAGED_HYPOTHESIS_PENDING_KEY) ?? "null"));
      if (value.command !== "staged-hypothesis" || typeof value.body !== "string") return null;
      const body = obj(JSON.parse(value.body));
      if (Object.keys(body).sort().join(",") !== "expected_state_version,hypothesis,project_id,request_id"
          || typeof body.request_id !== "string" || !body.request_id || typeof body.project_id !== "string" || !body.project_id
          || !Number.isSafeInteger(body.expected_state_version) || !Object.keys(obj(body.hypothesis)).length) return null;
      return {command:"staged-hypothesis", requestId:body.request_id, body:value.body, uncertain:true};
    } catch { return null; }
  };
  const hasStagedHypothesis = (): boolean => { try { return sessionStorage.getItem(STAGED_HYPOTHESIS_PENDING_KEY) !== null; } catch { return true; } };
  const savedStagedPrimary = (): Pending | null => {
    try {
      const value = obj(JSON.parse(sessionStorage.getItem(STAGED_PRIMARY_PENDING_KEY) ?? "null"));
      const body = obj(JSON.parse(text(value.body, ""))), identity = obj(value.identity);
      if (value.command !== "staged-primary" || typeof value.body !== "string"
          || Object.keys(body).sort().join(",") !== "expected_state_version,project_id,reason,registration_request_id,registration_sha256,request_id"
          || ![body.request_id, body.project_id, body.registration_request_id, body.reason, identity.candidate_id].every(v => typeof v === "string" && v.length > 0)
          || !Number.isSafeInteger(body.expected_state_version) || !Number.isSafeInteger(identity.plan_version)
          || ![body.registration_sha256, identity.snapshot_ref, identity.context_sha256, identity.source_snapshot_sha256, identity.plan_sha256]
            .every(v => typeof v === "string" && /^[0-9a-f]{64}$/.test(v))) return null;
      return {command:"staged-primary", requestId:text(body.request_id, ""), body:value.body, uncertain:true, stagedPrimaryContext:identity};
    } catch { return null; }
  };
  const hasStagedPrimary = (): boolean => { try { return sessionStorage.getItem(STAGED_PRIMARY_PENDING_KEY) !== null; } catch { return true; } };
  const savedStagedFeedback = (): Pending | null => {
    try {
      const value = obj(JSON.parse(sessionStorage.getItem(STAGED_FEEDBACK_PENDING_KEY) ?? "null"));
      const body = obj(JSON.parse(text(value.body, ""))), identity = obj(value.identity), feedback = obj(identity.feedback);
      if (value.command !== "staged-feedback" || typeof value.body !== "string"
          || Object.keys(body).sort().join(",") !== "expected_state_version,primary_action_id,project_id,registration_request_id,registration_sha256,request_id"
          || ![body.request_id, body.project_id, body.registration_request_id, body.primary_action_id, identity.candidate_id].every(v => typeof v === "string" && v.length > 0)
          || !Number.isSafeInteger(body.expected_state_version) || !Number.isSafeInteger(identity.plan_version)
          || ![body.registration_sha256, identity.snapshot_ref, identity.context_sha256, identity.source_snapshot_sha256, identity.plan_sha256, identity.primary_result_sha256]
            .every(v => typeof v === "string" && /^[0-9a-f]{64}$/.test(v))
          || feedback.request_id !== body.registration_request_id || feedback.registration_sha256 !== body.registration_sha256
          || feedback.action_id !== body.primary_action_id || feedback.result_sha256 !== identity.primary_result_sha256
          || !["condition_met", "condition_not_met"].includes(text(feedback.outcome, ""))) return null;
      return {command:"staged-feedback", requestId:text(body.request_id, ""), body:value.body, uncertain:true, stagedFeedbackContext:identity};
    } catch { return null; }
  };
  const hasStagedFeedback = ():boolean => { try { return sessionStorage.getItem(STAGED_FEEDBACK_PENDING_KEY) !== null; } catch { return true; } };
  const stagedFeedbackSummaryPending = ():boolean => { const summary = obj(description.pending_staged_feedback_summary); return summary.project_id === activeId() && typeof summary.total === "number" && summary.total > 0; };
  const savedManual = (key: string): Obj | null => {
    let raw: string | null; try { raw = sessionStorage.getItem(key); } catch { return null; }
    if (raw === null) return null; try { return obj(JSON.parse(raw)); } catch { return {}; }
  };
  const hasManualRequest = (): boolean => savedManual(MANUAL_PREPARE_KEY) !== null || savedManual(MANUAL_IMPORT_KEY) !== null;
  const scopedPending = (command: string): boolean => ["evidence", "save_plan"].includes(command);
  const stagedPrimarySummaryPending = (): boolean => {
    const summary = obj(description.pending_staged_primary_summary);
    return summary.project_id === activeId() && typeof summary.total === "number" && summary.total > 0;
  };
  const serverPending = (projectId = activeId()): boolean => successorBlocked() || stagedFeedbackSummaryPending() || stagedPrimarySummaryPending()
    || items(description.pending_requests).some(record => !scopedPending(text(record.command, "")) || !record.project_id || record.project_id === projectId);
  const requestProject = (pending: Pending): string => text(obj(JSON.parse(pending.body)).project_id, "");
  const uncertain = (projectId = activeId()): boolean => hasStagedFeedback() || hasStagedPrimary() || hasStagedHypothesis() || hasQualityRequest() || hasManualRequest() || !!batchUncertain || !!evidencePending.get(projectId)?.uncertain || !!lastRequest?.uncertain
    && (!["evidence", "plan", "plan-resume"].includes(lastRequest.command) || requestProject(lastRequest) === projectId);
  const otherNavigationBlocked = (): boolean => stagedFeedbackSummaryPending() || hasStagedFeedback() || stagedPrimarySummaryPending() || hasStagedPrimary() || hasStagedHypothesis() || hasQualityRequest() || hasManualRequest() || items(description.pending_requests).some(record => !["batch", "continue", "evidence", "save_plan", "save_staged_feedback_plan"].includes(text(record.command, "")))
    || !!lastRequest?.uncertain && !["batch", "continue", "evidence", "plan", "plan-resume"].includes(lastRequest.command);
  const navigationBlocked = (): boolean => successorBlocked() || otherNavigationBlocked();
  const unknownExecution = (): boolean => items(context?.blockers).some(item => /UNKNOWN|NEEDS_REVIEW/.test(text(item.code, ""))) || current.execution_status === "unknown";
  const evidencePanel = createLocalEvidencePanel({ read, submit: body => submit(command("evidence", body)), announce });
  const experiencePanel = createLocalExperiencePanel({ read, submit: (name, body, recover) => submit(recover
    ? { command: name, requestId: text(body.request_id, ""), body: JSON.stringify(body), uncertain: false, recoverExperience: true }
    : command(name, body)), canRecover: canRecoverExperience, announce,
    methodTitle: id => methodNames[id] ?? id });
  const batchPanel = createLocalBatchPanel({ submit: (body, recover, name) => submit(recover
    ? { command: name, requestId: text(body.request_id, ""), body: JSON.stringify(body), uncertain: false, recoverBatch: true }
    : command(name, body)), canRecover: canRecoverBatch, announce });
  const modelPanel = createLocalModelPanel({ read, canCheckPlanFacts: () => description.enabled === true, canImportManual: canRecoverManual,
    checkPlanFact: body => previewLocal("plan-fact-check", body), submit: (name, body) => submit(["model-resume", "model-plan-adopt", "model-plan-reject"].includes(name)
    ? { command: name, requestId: text(body.request_id, ""), body: JSON.stringify(body), uncertain: false, recoverModel: true }
    : name === "manual-quality-plan-import" ? { command:name, requestId:text(body.request_id, ""), body:JSON.stringify(body), uncertain:false, recoverManual:true }
    : name === "manual-quality-plan-prepare" ? (() => { const id = requestId("manual-plan"); return {command:name, requestId:id, body:JSON.stringify({request_id:id, ...body}), uncertain:false}; })()
    : command(name, body)), announce, methodTitle: id => methodNames[id] ?? id });
  const recipePanel = createLocalRecipePanel({ read, preview: body => previewLocal("recipe-preview", body),
    submit: (name, body) => submit(command(name, body)), announce });
  const designPanel = createResearchDesignPanel({ read, submit: (name, body) => submit(command(name, body)), announce });
  const planPanel = createResearchPlanPanel({ current: () => current, context: () => context, modelRecords: id => modelPanel.savedRecords(id), submit: body => submit(command("plan", body)) });
  const stagedHypothesisPanel = createStagedHypothesisPanel({ current: () => current, context: () => context, submit: body => submit(command("staged-hypothesis", body)),
    submitPrimary: (body, identity) => submit({command:"staged-primary", requestId:text(body.request_id, ""), body:JSON.stringify(body), uncertain:false, stagedPrimaryContext:identity}),
    submitFeedback: (body, identity) => submit({command:"staged-feedback", requestId:text(body.request_id, ""), body:JSON.stringify(body), uncertain:false, stagedFeedbackContext:identity}) });
  const stagedSuccessorPreview = createStagedSuccessorPreviewPanel({ current: () => current, context: () => context,
    active: () => activeId(), preview: body => previewLocal("staged-feedback-plan-preview", body) });
  const stagedSuccessorSave = createStagedSuccessorSavePanel({ current: () => current, context: () => context, active: () => activeId(), generation: () => successorGeneration,
    readDraft: () => planPanel.draft(), scanNow: scanSuccessor, read,
    post: async (name, body) => {
      const response = await fetch("/api/local-workbench/" + name, { method:"POST", credentials:"same-origin", cache:"no-store",
        headers:{"Content-Type":"application/json", "X-AutoResearch-CSRF":text(description.csrf_token, "")}, body, signal:AbortSignal.timeout(60000) });
      const value = obj(await response.json());
      if (!response.ok) throw Error("后续计划原请求尚未核对：" + text(value.code, String(response.status)));
      return value;
    },
    enabled: () => description.enabled === true && !!activeId() && current.id === activeId()
      && !stagedFeedbackSummaryPending() && !stagedPrimarySummaryPending() && !hasStagedFeedback() && !hasStagedPrimary()
      && !hasStagedHypothesis() && !hasQualityRequest() && !hasManualRequest() && !batchUncertain && !lastRequest?.uncertain
      && ![...evidencePending.values()].some(item => item.uncertain)
      && !items(description.pending_requests).some(record => record.command !== "save_staged_feedback_plan"),
    setBusy: value => { busy = value; controls(); }, onState: () => { controls(); showPending(); }, refresh });
  const feedbackPanel = createResearcherFeedbackPanel({ current: () => current, context: () => context, submit: body => submit(command("feedback", body)) });
  const workspacePages = createProjectPages(host, { shared: [message, pendingNotice, toolbar], management: [switching, createSection],
    planning: [planPanel.element, stagedSuccessorSave.element, stagedSuccessorPreview.element, stagedHypothesisPanel.element, modelPanel.planElement, modelPanel.improvementElement, recipePanel.effectiveElement, feedbackPanel.element], feedback: feedbackPanel.element,
    operations: { action: runSection, evidence: evidencePanel.element, continuation: batchPanel.element, model: modelPanel.element, recipe: recipePanel.element },
    design: designPanel.element, designLibrary: designPanel.libraryElement, experience: experiencePanel.element, reportButton, announce });
  function planContinuation(requestId = ""): Obj | undefined {
    return items(description.continuations).find(record => record.project_id === activeId() && record.record_status === "incomplete"
      && ["plan", "awaiting_adoption"].includes(text(record.phase, "")) && obj(record.plan_ref).kind === "host_plan"
      && (!requestId || obj(record.plan_ref).request_id === requestId));
  }
  function otherModelBlockers(requestId = ""): boolean {
    if (successorBlocked()) return true;
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
  function canRecoverManual(body: Obj): boolean {
    if (busy || description.enabled !== true || body.project_id !== activeId() || current.id !== activeId()
        || unknownExecution() || hasQualityRequest() || batchUncertain || evidencePending.get(activeId())?.uncertain
        || !modelPanel.canImportManual(body)) return false;
    const prepare = savedManual(MANUAL_PREPARE_KEY), imported = savedManual(MANUAL_IMPORT_KEY);
    if (prepare && (prepare.request_id !== body.request_id || prepare.project_id !== body.project_id
        || !manualPrepareMatches(prepare, modelPanel.savedRecords(text(body.project_id, "")).find(item => item.request_id === body.request_id) ?? {}))) return false;
    if (imported && (imported.request_id !== body.request_id || imported.project_id !== body.project_id
        || typeof imported.response_sha256 !== "string" || !/^[a-f0-9]{64}$/.test(imported.response_sha256))) return false;
    if (items(description.pending_requests).some(item => !scopedPending(text(item.command, "")) || !item.project_id || item.project_id === body.project_id)) return false;
    return !lastRequest?.uncertain || lastRequest.requestId === body.request_id;
  }
  function manualPrepareMatches(body: Obj, record: Obj): boolean {
    const spec = obj(record.prepare_specification), marker = obj(record.manual_plan_intent), selection = obj(obj(record.context).selection_context), grant = obj(spec.grant);
    return record.request_id === body.request_id && record.provider === "delegated" && record.purpose === "plan"
      && marker.schema_version === "host-manual-quality-plan-intent-v1" && marker.project_id === body.project_id
      && marker.snapshot_ref === body.expected_snapshot_ref && selection.project_id === body.project_id && selection.snapshot_ref === body.expected_snapshot_ref
      && spec.request_id === body.request_id && spec.expected_state_version === body.expected_state_version && spec.executable === null
      && grant.decision_limit === body.decision_limit && grant.cli_budget_usd === body.cli_budget_usd && grant.reason === body.reason
      && sameValue(spec.saved_materials, body.saved_materials);
  }
  function canRecoverExperience(body: Obj): boolean {
    const pending = items(description.pending_requests), id = text(body.request_id, "");
    if (busy || description.enabled !== true || !id || body.project_id !== activeId() || current.id !== activeId()
      || !pending.some(record => record.request_id === id && record.project_id === body.project_id
        && ["import_experience", "set_experience_status"].includes(text(record.command, "")))) return false;
    if (pending.some(record => record.request_id !== id && (record.command !== "evidence" || !record.project_id || record.project_id === body.project_id))) return false;
    if (lastRequest?.uncertain && lastRequest.requestId !== id || batchUncertain || evidencePending.get(text(body.project_id, ""))?.uncertain) return false;
    return true;
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
    const canChooseOriginal = !otherNavigationBlocked() && items(description.projects).some(project => canSelectSuccessorProject(text(project.id, "")));
    const navigationLocked = busy || description.enabled !== true || (navigationBlocked() && !(canChooseOriginal && canSelectSuccessorProject(projectSelect.value)));
    const locked = globalLocked || serverPending() || uncertain() || unknownExecution() || modelPanel.pending();
    createFields.disabled = globalLocked; createButton.disabled = globalLocked || loadingFile || !csv || !headers.length;
    selectButton.disabled = navigationLocked || !projectSelect.value || projectSelect.value === activeId();
    projectSelect.disabled = busy || description.enabled !== true || (navigationBlocked() && !canChooseOriginal);
    executeButton.disabled = locked || !context || !selectedCandidate || !rationale.value.trim() || items(context.blockers).length > 0;
    waitButton.disabled = locked || !context || !rationale.value.trim();
    const reportReady = obj(current.report).available === true && obj(current.report).stale !== true;
    reportButton.hidden = reportReady;
    reportButton.disabled = locked || !activeId() || typeof current.state_version !== "number" || reportReady;
    reportButton.textContent = busy && lastRequest?.command === "report" ? "正在生成报告…" : "生成当前快照报告";
    refreshButton.disabled = busy;
    retry.hidden = !lastRequest; retry.disabled = busy || !lastRequest || lastRequest.uncertain || (lastRequest.command === "evidence" && requestProject(lastRequest) !== activeId()) || description.enabled !== true;
    evidencePanel.setLocked(locked);
    experiencePanel.setLocked(locked || current.id !== activeId());
    batchPanel.setLocked(locked || typeof current.state_version !== "number" || current.id !== activeId());
    const planId = text(obj(planContinuation()?.plan_ref).request_id, "");
    modelPanel.setLocked(busy || description.enabled !== true || otherModelBlockers(),
      !busy && description.enabled === true && !otherModelBlockers(planId) ? planId : "");
    recipePanel.setLocked(locked || current.id !== activeId());
    designPanel.setLocked(locked || current.id !== activeId(), globalLocked);
    planPanel.setLocked(locked || current.id !== activeId());
    stagedHypothesisPanel.setLocked(locked || current.id !== activeId());
    const pendingSuccessor = description.pending_staged_feedback_plan_summary;
    const successorSummary = obj(pendingSuccessor);
    const successorPending = pendingSuccessor !== undefined && (successorSummary.project_id !== activeId()
      || typeof successorSummary.total !== "number" || !Number.isSafeInteger(successorSummary.total) || successorSummary.total < 0 || successorSummary.total > 0);
    stagedSuccessorPreview.setLocked(locked || current.id !== activeId() || successorPending);
    stagedSuccessorSave.setLocked(locked || current.id !== activeId());
    feedbackPanel.setLocked(locked || current.id !== activeId());
    rationale.disabled = locked;
    candidateList.querySelectorAll<HTMLInputElement>("input").forEach(control => { control.disabled = locked || items(context?.blockers).length > 0; });
    citationList.querySelectorAll<HTMLInputElement>("input").forEach(control => { control.disabled = locked; });
  }
  function showPending(): void {
    const records = items(description.pending_requests);
    let remembered: Obj = {};
    try { remembered = obj(JSON.parse(sessionStorage.getItem(PENDING_KEY) ?? "{}")); } catch { /* Storage is optional; manager owns durable state. */ }
    pendingNotice.replaceChildren(); pendingNotice.hidden = !successorBlocked() && !records.length && !remembered.request_id && !batchUncertain && !stagedFeedbackSummaryPending() && !hasStagedFeedback() && !stagedPrimarySummaryPending() && !hasStagedPrimary() && !hasStagedHypothesis() && !hasQualityRequest() && !hasManualRequest() && ![...evidencePending.values()].some(pending => pending.uncertain);
    if (successorBlocked()) {
      pendingNotice.append(el("p", "notice error", "后续计划未决状态、原正文或跨标签标记不可确认；保留原 ID，只能核对原请求。浏览器存储可能丢失，不适用于其他设备。"));
      if (successorStoragePending()) { const button = el("button", "text-button", "只核对原后续计划请求"); button.type = "button";
        button.disabled = busy || description.enabled !== true; button.addEventListener("click", () => { if (!button.disabled) void stagedSuccessorSave.recover(); }); pendingNotice.append(button); }
    }
    if (records.length) pendingNotice.append(el("strong", "", records.some(record => ["batch", "continue"].includes(text(record.command, "")))
      ? "有原推进记录尚未收口。请在继续研究中核对原阶段；计划建议需先采用或拒绝，未知行动不会重发。"
      : "有原请求尚未确认，保留原ID核对；资料登记仅阻断对应项目的新提交，可切换查看其他项目。"));
    else if (remembered.request_id) pendingNotice.append(el("strong", "", "上次浏览器提交尚需对照保存记录核对；没有自动重发。"));
    const planSummary = obj(description.pending_plan_summary);
    const primarySummary = obj(description.pending_staged_primary_summary);
    if (stagedPrimarySummaryPending()) pendingNotice.append(el("p", "detail-note", "当前项目有 " + numeric(primarySummary.total)
      + " 条未收口 primary，仅显示 " + numeric(primarySummary.shown) + " 条；原 ID 和正文需逐条核对，不能以新 ID 绕过。"));
    if (planSummary.truncated === true && planSummary.project_id === activeId())
      pendingNotice.append(el("p", "detail-note", "当前项目有 " + numeric(planSummary.total) + " 条未收口计划，仅显示前 " + numeric(planSummary.shown) + " 条；多个原请求可能互相阻断，须人工核对，不能新建替代请求。"));
    for (const record of records) {
      const row = el("div", "local-pending-row");
      row.append(el("p", "detail-note", text(record.command) + " · " + text(record.request_id) + " · " + text(record.status) + (record.project_id ? " · 项目 " + text(record.project_id) : "")));
      if (record.command === "save_plan") {
        if (record.recovery === "original_body_available") {
          const button = el("button", "text-button", "核对并继续原计划请求"); button.type = "button";
          const body = { request_id: text(record.request_id, ""), project_id: text(record.project_id, "") };
          button.disabled = !canRecoverPlan(body);
          button.addEventListener("click", () => { if (!button.disabled) void submit({ command: "plan-resume", requestId: body.request_id,
            body: JSON.stringify(body), uncertain: false, recoverPlan: true }); });
          row.append(el("p", "detail-note", "若原计划尚未写入，将以原内容和原ID继续保存；若已写入，仅补原回执。不是新请求，也不会自动执行。"), button);
        } else row.append(el("p", "detail-note", "旧记录或损坏记录没有可核验的原正文；状态未知，不能自动重建或用新ID绕过。"));
      }
      if (record.command === "register_staged_hypothesis" && record.project_id === activeId()) {
        const id = text(record.request_id, ""), projectId = activeId(), button = el("button", "text-button", "只核对原事前登记");
        button.type = "button"; button.disabled = busy || description.enabled !== true || !id;
        button.addEventListener("click", () => { if (!button.disabled) void submit({command:"staged-hypothesis-resume", requestId:id,
          body:JSON.stringify({request_id:id, project_id:projectId}), uncertain:false, recoverStagedHypothesis:true}); });
        row.append(el("p", "detail-note", "仅核已保存原登记和归属；若原记录不存在，不会创建登记或重派。"), button);
      }
      if (record.command === "advance_staged_primary") row.append(el("p", "detail-note", "原 primary 尚未收口；只可核对原 ID，不能重新执行。"));
      pendingNotice.append(row);
    }
    if (stagedFeedbackSummaryPending()) { const summary = obj(description.pending_staged_feedback_summary);
      pendingNotice.append(el("p", "detail-note", "当前项目有 " + numeric(summary.total) + " 条未收口反馈，仅显示 " + numeric(summary.shown) + " 条；原 ID 可能未列出，须核对，不可创建替代请求。")); }
    if (hasStagedFeedback()) {
      const saved = savedStagedFeedback();
      if (!saved) pendingNotice.append(el("p", "notice error", "原反馈正文或身份不可用；停查，不创建替代 ID。"));
      else { const original = obj(JSON.parse(saved.body)), projectId = text(original.project_id, ""), button = el("button", "text-button", "只核对原反馈记录");
        button.type = "button"; button.disabled = busy || description.enabled !== true || projectId !== activeId() || current.id !== projectId;
        button.addEventListener("click", () => { if (!button.disabled) void submit({command:"staged-feedback-resume", requestId:saved.requestId,
          body:JSON.stringify({request_id:saved.requestId, project_id:projectId}), uncertain:false, recoverStagedFeedback:true}); });
        pendingNotice.append(el("p", "detail-note", "反馈原 ID " + saved.requestId + " 待核对。只核原记录和 claims，可能补原 manager 回执；不重新派发。未完成、失败、未知或缺原意图时停查。"), button);
      }
    } else if (items(description.pending_requests).some(record => record.command === "advance_staged_feedback") || stagedFeedbackSummaryPending())
      pendingNotice.append(el("p", "notice error", "浏览器缺少原反馈正文，不能自动重建；保留原 ID 人工核对。"));
    if (hasStagedPrimary()) {
      const saved = savedStagedPrimary();
      if (!saved) pendingNotice.append(el("p", "notice error", "原 primary 正文或身份不可用；停查，不创建替代 ID。"));
      else {
        const original = obj(JSON.parse(saved.body)), projectId = text(original.project_id, "");
        const button = el("button", "text-button", "只核对原 primary 记录"); button.type = "button";
        button.disabled = busy || description.enabled !== true || projectId !== activeId() || current.id !== projectId;
        button.addEventListener("click", () => { if (!button.disabled) void submit({command:"staged-primary-resume", requestId:saved.requestId,
          body:JSON.stringify({request_id:saved.requestId, project_id:projectId}), uncertain:false, recoverStagedPrimary:true}); });
        pendingNotice.append(el("p", "detail-note", "原 primary ID " + saved.requestId + " 待核对。仅核对已完成的原记录与 claim，必要时补原 manager 回执；不会重新派发。未完成、失败、未知或缺原意图时停查。"), button);
      }
    } else if (records.some(record => record.command === "advance_staged_primary"))
      pendingNotice.append(el("p", "notice error", "浏览器缺少原 primary 正文，不能自动重建；请保留原 ID 人工核对。"));
    if (hasStagedHypothesis()) {
      const saved = savedStagedHypothesis();
      if (!saved) pendingNotice.append(el("p", "notice error", "事前登记原ID或正文无法核对；停止并人工检查，不创建替代ID。"));
      else if (!records.some(record => record.command === "register_staged_hypothesis" && record.request_id === saved.requestId)) {
        const body = obj(JSON.parse(saved.body)), id = saved.requestId, projectId = text(body.project_id, "");
        const button = el("button", "text-button", "只核对原事前登记"); button.type = "button";
        button.disabled = busy || description.enabled !== true || projectId !== activeId();
        button.addEventListener("click", () => { if (!button.disabled) void submit({command:"staged-hypothesis-resume", requestId:id,
          body:JSON.stringify({request_id:id, project_id:projectId}), uncertain:false, recoverStagedHypothesis:true}); });
        pendingNotice.append(el("p", "detail-note", "事前登记原ID " + id + " 待核对；无原manager意图时停止，不会重建。"), button);
      }
    }
    if (hasQualityRequest()) {
      const saved = savedQualityRequest();
      if (!saved) pendingNotice.append(el("p", "notice error", "严格采纳的浏览器原请求不可核对；停止并核对原 manager 记录，不会重建正文或创建新ID。"));
      else {
        const button = el("button", "text-button", "核对并重试原严格采纳"); button.type = "button";
        button.disabled = !canRecoverQuality(saved);
        button.addEventListener("click", () => { if (!button.disabled) void submit({...saved, recoverQuality: true}); });
        pendingNotice.append(el("p", "detail-note", `严格采纳原ID ${saved.requestId} · 结果待核对。仅可显式重用原项目、版本和正文；恢复入口要求原 manager 记录已存在，不会创建首次请求。`), button);
      }
    }
    if (hasManualRequest()) {
      const prepare = savedManual(MANUAL_PREPARE_KEY), imported = savedManual(MANUAL_IMPORT_KEY), id = text(imported?.request_id ?? prepare?.request_id, "未知");
      pendingNotice.append(el("p", "notice", `人工计划原 ID ${id} 仍需核对；不会凭缺记录重新准备。若原 Host 可核对，请重选原回答；导入未确认时仅接受同一原文件 SHA。`));
    }
    for (const pending of evidencePending.values()) if (pending.uncertain && !records.some(record => record.request_id === pending.requestId)) pendingNotice.append(el("p", "detail-note", "evidence · 原ID " + pending.requestId + " · 结果待核对 · 项目 " + requestProject(pending)));
    if (batchUncertain && !records.some(record => record.request_id === batchUncertain?.requestId)) pendingNotice.append(el("p", "detail-note", "batch · 原ID " + batchUncertain.requestId + " · 结果待核对；可切回原项目，新提交保持锁定。"));
    if (remembered.request_id && !records.some(record => record.request_id === remembered.request_id)) pendingNotice.append(el("p", "detail-note", text(remembered.command) + " · 原ID " + text(remembered.request_id)));
  }
  function canRecoverPlan(body: Obj): boolean {
    const plan = items(description.pending_requests).find(item => item.command === "save_plan" && item.request_id === body.request_id
      && item.project_id === body.project_id && item.recovery === "original_body_available");
    if (busy || description.enabled !== true || !plan || body.project_id !== activeId() || current.id !== activeId()
        || obj(description.pending_plan_summary).truncated === true || unknownExecution() || modelPanel.pending()) return false;
    if (items(description.pending_requests).some(item => item.request_id !== body.request_id
        && (!scopedPending(text(item.command, "")) || !item.project_id || item.project_id === body.project_id))) return false;
    if (lastRequest?.uncertain && lastRequest.requestId !== body.request_id && requestProject(lastRequest) === body.project_id) return false;
    return !batchUncertain && !evidencePending.get(text(body.project_id, ""))?.uncertain;
  }
  function canRecoverQuality(pending: Pending): boolean {
    const saved = savedQualityRequest(), body = obj(JSON.parse(pending.body));
    if (busy || description.enabled !== true || !saved || saved.body !== pending.body || saved.requestId !== pending.requestId
        || body.project_id !== activeId() || current.id !== activeId() || unknownExecution() || batchUncertain
        || evidencePending.get(text(body.project_id, ""))?.uncertain) return false;
    return !items(description.pending_requests).some(item => item.request_id !== body.request_id
      && (!scopedPending(text(item.command, "")) || !item.project_id || item.project_id === body.project_id));
  }
  function revealPendingOperations(): void {
    const projectId = activeId(); if (!projectId || current.id !== projectId) return;
    const resolved = new Set(items(obj(current.selection_history).records).filter(record => ["completed", "waiting", "failed", "rejected"].includes(text(record.status, ""))).map(record => record.request_id));
    for (const record of [...items(description.batches), ...items(description.continuations)]) if (record.record_status === "completed" && record.project_id === projectId) resolved.add(record.request_id);
    for (const record of items(current.recipe_revisions)) resolved.add(record.request_id);
    const reveal = (name: string, id: string, owner = projectId, phase = ""): void => {
      if (!id || owner !== projectId || resolved.has(id)) return;
      const operation: ProjectOperation | undefined = name === "advance" ? "action" : name === "evidence" ? "evidence"
        : ["batch", "continue"].includes(name) ? "continuation" : MODEL_COMMANDS.has(name) ? "model"
          : ["advance-recipe", "recipe-adopt"].includes(name) ? "recipe" : undefined;
      if (operation) workspacePages.revealOperation(operation, projectId + ":" + id + ":" + phase);
    };
    for (const record of items(description.pending_requests)) if (record.status !== "completed") reveal(text(record.command, ""), text(record.request_id, ""), text(record.project_id, ""));
    for (const record of items(description.batches)) if (["preparing", "incomplete"].includes(text(record.record_status, ""))) reveal("batch", text(record.request_id, ""), text(record.project_id, ""));
    for (const record of items(description.continuations)) if (record.record_status === "incomplete" && record.project_id === projectId) {
      reveal("continue", text(record.request_id, ""), projectId, text(record.phase, ""));
      if (["plan", "awaiting_adoption"].includes(text(record.phase, "")) && obj(record.plan_ref).kind === "host_plan")
        reveal("model-resume", text(obj(record.plan_ref).request_id, ""));
    }
    for (const pending of [lastRequest, batchUncertain, evidencePending.get(projectId)]) if (pending?.uncertain)
      reveal(pending.command, pending.requestId, requestProject(pending));
    try {
      const remembered = obj(JSON.parse(sessionStorage.getItem(PENDING_KEY) ?? "{}"));
      reveal(text(remembered.command, ""), text(remembered.request_id, ""));
    } catch { /* Browser storage is optional; saved requests remain authoritative. */ }
    if (modelPanel.pending()) for (const record of modelPanel.savedRecords(projectId))
      if (["prepared", "sending", "unknown", "received"].includes(text(record.status, ""))) reveal("model-resume", text(record.request_id, ""));
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
  async function previewLocal(name: "recipe-preview" | "plan-fact-check" | "staged-feedback-plan-preview", body: Obj): Promise<Obj> {
    const response = await fetch("/api/local-workbench/" + name, {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json", "X-AutoResearch-CSRF": text(description.csrf_token, "") },
      body: JSON.stringify(body), signal: AbortSignal.timeout(15000),
    });
    const result = obj(await response.json());
    if (!response.ok) throw Error((name === "recipe-preview" ? "外环核对失败：" : name === "plan-fact-check" ? "断言核对失败：" : "后续决策预览失败：") + text(result.code, String(response.status)));
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
    successorGeneration++;
    const previousId = activeId(); context = null; successorScan = null; successorGlobalScan = null; candidates();
    stagedSuccessorPreview.invalidate(); stagedSuccessorPreview.setLocked(true); stagedSuccessorSave.setLocked(true);
    planPanel.setLocked(true);
    stagedHypothesisPanel.setLocked(true);
    feedbackPanel.setLocked(true);
    modelPanel.setLocked(true);
    recipePanel.invalidate(); recipePanel.setLocked(true);
    designPanel.invalidate(); designPanel.setLocked(true);
    batchPanel.setLocked(true);
    await evidencePanel.refresh("", {});
    await experiencePanel.refresh("", {});
    description = await read("/api/local-workbench");
    if (description.schema_version !== "local-research-workbench-v1") throw Error("本地工作台返回身份不完整。");
    if (description.read_only === true) {
      current = {}; context = null;
      document.body.classList.add("saved-study-only");
      $("nav-project-title").textContent = "只读宿主";
      $("project-label").textContent = "只读保存记录";
      $("project-title").textContent = "当前项目与独立研究";
      if (statusLabel) statusLabel.textContent = "保存研究 · 只读";
      if (footer) footer.textContent = "独立保存引用 · 只读";
      await workspacePages.update({}, null, true);
      host.querySelectorAll<HTMLElement>(".project-management, .project-operations, .project-original-entry").forEach(node => { node.hidden = true; });
      return;
    }
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
    if (!now) { try { successorGlobalScan = await read("/api/local-workbench/staged-feedback-plan-global-pending.json"); }
      catch { successorGlobalScan = null; } }
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
      try { await scanSuccessor(now, text(current.snapshot_ref, "")); } catch { successorScan = null; }
      const savedPlanIds = new Set(items(obj(current.research_plan).revisions).map(revision => revision.request_id));
      const savedFeedbackIds = new Set(items(current.researcher_feedback).map(record => record.request_id));
      const pendingPlans = new Set(items(description.pending_requests).filter(record => record.command === "save_plan").map(record => record.request_id));
      if (lastRequest && ((lastRequest.command === "plan" || lastRequest.command === "plan-resume")
          && savedPlanIds.has(lastRequest.requestId) && !pendingPlans.has(lastRequest.requestId)
          || lastRequest.command === "feedback" && savedFeedbackIds.has(lastRequest.requestId))) lastRequest = null;
      try {
        const remembered = obj(JSON.parse(sessionStorage.getItem(PENDING_KEY) ?? "{}"));
        if ((remembered.command === "plan" || remembered.command === "plan-resume") && savedPlanIds.has(remembered.request_id)
            && !pendingPlans.has(remembered.request_id) || remembered.command === "feedback" && savedFeedbackIds.has(remembered.request_id)) sessionStorage.removeItem(PENDING_KEY);
      } catch { /* The project record remains available when browser storage is unavailable. */ }
      showPending();
      try {
        const next = await read("/api/project/selection-context.json");
        if (next.project_id !== now || next.schema_version !== "project-selection-context-v1") throw Error("候选不属于当前项目，请刷新后核对。");
        context = next;
      } catch (error) { context = null; announce(error instanceof Error ? error.message : "当前候选读取失败。", true); }
      planPanel.update(current); stagedSuccessorSave.update(current); stagedSuccessorPreview.update(current); stagedHypothesisPanel.update(current); feedbackPanel.update(current); candidates(); batchPanel.update(description, current); await evidencePanel.refresh(now, current);
      await modelPanel.refresh(now, current, context); planPanel.update(current); await recipePanel.refresh(now, current, context); await designPanel.update(current);
      await experiencePanel.refresh(now, current, items(description.pending_requests)); await workspacePages.update(current, context);
      if (lastRequest && modelPanel.decisionResolved(lastRequest.command, lastRequest.requestId)) lastRequest = null;
      try {
        const remembered = obj(JSON.parse(sessionStorage.getItem(PENDING_KEY) ?? "{}"));
        if (modelPanel.decisionResolved(text(remembered.command, ""), text(remembered.request_id, ""))) sessionStorage.removeItem(PENDING_KEY);
      } catch { /* Saved model records remain authoritative. */ }
      showPending();
      revealPendingOperations();
    } else { planPanel.update({}); stagedSuccessorSave.update({}); stagedSuccessorPreview.update({}); stagedHypothesisPanel.update({}); feedbackPanel.update({}); batchPanel.update(description, {}); await modelPanel.refresh("", {}, null); await recipePanel.refresh("", {}, null); await designPanel.update({}); await workspacePages.update({}, null); }
    if (lastRequest && experiencePanel.resolved(lastRequest.command, lastRequest.requestId)) lastRequest = null;
    try {
      const remembered = obj(JSON.parse(sessionStorage.getItem(PENDING_KEY) ?? "{}"));
      if (experiencePanel.resolved(text(remembered.command, ""), text(remembered.request_id, ""))) sessionStorage.removeItem(PENDING_KEY);
    } catch { /* Saved experience revisions remain authoritative. */ }
    if (lastRequest && designPanel.resolved(lastRequest.command, lastRequest.requestId)) lastRequest = null;
    try {
      const remembered = obj(JSON.parse(sessionStorage.getItem(PENDING_KEY) ?? "{}"));
      if (designPanel.resolved(text(remembered.command, ""), text(remembered.request_id, ""))) sessionStorage.removeItem(PENDING_KEY);
    } catch { /* Saved design receipts remain authoritative. */ }
    showPending();
    if (description.enabled !== true) announce("当前服务没有启用写入模式，不能提交本地命令。", true);
    downloads(); controls();
  }
  async function submit(pending: Pending): Promise<Obj | null> {
    if (busy) return null;
    const targetProject = requestProject(pending), switching = pending.command === "select";
    const selectOriginal = switching && !otherNavigationBlocked() && canSelectSuccessorProject(targetProject);
    if (successorBlocked() && !selectOriginal) { announce("后续计划原请求或未决状态尚需核对；仅允许原请求恢复。", true); return null; }
    const sameEvidence = pending.command === "evidence" && evidencePending.get(targetProject)?.requestId === pending.requestId;
    const recoverBatch = (pending.command === "batch" || pending.command === "continue") && pending.recoverBatch === true
      && canRecoverBatch(obj(JSON.parse(pending.body)), pending.command);
    const recoverModel = pending.recoverModel === true && canRecoverModel(obj(JSON.parse(pending.body)));
    const recoverExperience = pending.recoverExperience === true && pending.command === "experience-resume" && canRecoverExperience(obj(JSON.parse(pending.body)));
    const recoverPlan = pending.recoverPlan === true && pending.command === "plan-resume" && canRecoverPlan(obj(JSON.parse(pending.body)));
    const recoverQuality = pending.recoverQuality === true && pending.command === "model-supplied-quality-plan-adopt" && canRecoverQuality(pending);
    const recoverManual = pending.recoverManual === true && pending.command === "manual-quality-plan-import" && canRecoverManual(obj(JSON.parse(pending.body)));
    const stagedRecoveryBody = obj(JSON.parse(pending.body));
    const recoverStagedHypothesis = pending.recoverStagedHypothesis === true && pending.command === "staged-hypothesis-resume"
      && typeof stagedRecoveryBody.request_id === "string" && !!stagedRecoveryBody.request_id
      && stagedRecoveryBody.project_id === activeId() && current.id === activeId() && description.enabled === true;
    const originalPrimary = savedStagedPrimary(), originalPrimaryBody = originalPrimary ? obj(JSON.parse(originalPrimary.body)) : {};
    const recoverStagedPrimary = pending.recoverStagedPrimary === true && pending.command === "staged-primary-resume"
      && !!originalPrimary && stagedRecoveryBody.request_id === originalPrimary.requestId
      && stagedRecoveryBody.project_id === originalPrimaryBody.project_id && stagedRecoveryBody.project_id === activeId()
      && current.id === activeId() && description.enabled === true;
    const originalFeedback = savedStagedFeedback(), originalFeedbackBody = originalFeedback ? obj(JSON.parse(originalFeedback.body)) : {};
    const recoverStagedFeedback = pending.recoverStagedFeedback === true && pending.command === "staged-feedback-resume"
      && !!originalFeedback && stagedRecoveryBody.request_id === originalFeedback.requestId && stagedRecoveryBody.project_id === originalFeedbackBody.project_id
      && stagedRecoveryBody.project_id === activeId() && current.id === activeId() && description.enabled === true;
    if (pending.recoverStagedFeedback && !recoverStagedFeedback) { announce("原反馈正文或项目不可核对；保留原 ID，不能重派。", true); return null; }
    if (pending.recoverBatch && !recoverBatch) { announce("原批次恢复条件尚未核对，请选择原项目并只读刷新；不会创建替代批次。", true); return null; }
    if (pending.recoverModel && !recoverModel) { announce("请先只读刷新，核对当前项目中保存的原模型请求。不会创建替代请求。", true); return null; }
    if (pending.recoverExperience && !recoverExperience) { announce("请先只读刷新，核对本项目的原案例请求；不会用新文件或参数重建操作。", true); return null; }
    if (pending.recoverPlan && !recoverPlan) { announce("请先只读刷新并核对原计划请求；不会用当前草稿重建或创建新ID。", true); return null; }
    if (pending.recoverQuality && !recoverQuality) { announce("原严格采纳请求尚不能核对；保留原ID和正文，不创建替代请求。", true); return null; }
    if (pending.recoverManual && !recoverManual) { announce("原人工计划请求尚不能核对；不会导入到其他 Host 或创建新ID。", true); return null; }
    if (pending.recoverStagedHypothesis && !recoverStagedHypothesis) { announce("请选择原项目并核对原登记；不会创建替代请求。", true); return null; }
    if (pending.recoverStagedPrimary && !recoverStagedPrimary) { announce("原 primary 正文或项目不可核对；保留原 ID，不能重派。", true); return null; }
    const blocked = switching ? navigationBlocked() && !selectOriginal : pending.command === "design-import" ? serverPending("") || uncertain("")
      : (serverPending(targetProject) && !sameEvidence) || uncertain(targetProject) || modelPanel.pending() || (pending.command !== "create" && unknownExecution());
    if (!recoverBatch && !recoverModel && !recoverExperience && !recoverPlan && !recoverQuality && !recoverManual && !recoverStagedHypothesis && !recoverStagedPrimary && !recoverStagedFeedback && (description.enabled !== true || blocked)) { announce("当前命令不可提交，请先只读核对原请求与保存状态。", true); return null; }
    if (pending.command === "staged-feedback") {
      try { sessionStorage.setItem(STAGED_FEEDBACK_PENDING_KEY, JSON.stringify({command:pending.command, body:pending.body, identity:pending.stagedFeedbackContext}));
        const saved = savedStagedFeedback(); if (saved?.body !== pending.body || !sameValue(saved.stagedFeedbackContext, pending.stagedFeedbackContext)) throw Error("storage");
      } catch { announce("无法保存原反馈 ID、正文和快照身份；尚未提交。", true); return null; }
    }
    if (pending.command === "staged-primary") {
      try {
        sessionStorage.setItem(STAGED_PRIMARY_PENDING_KEY, JSON.stringify({command:pending.command, body:pending.body, identity:pending.stagedPrimaryContext}));
        const saved = savedStagedPrimary();
        if (saved?.body !== pending.body || !sameValue(saved.stagedPrimaryContext, pending.stagedPrimaryContext)) throw Error("storage");
      } catch { announce("无法保存原 primary ID、正文和快照身份；尚未提交。", true); return null; }
    }
    if (pending.command === "staged-hypothesis") {
      try {
        sessionStorage.setItem(STAGED_HYPOTHESIS_PENDING_KEY, JSON.stringify({command:pending.command, body:pending.body}));
        if (savedStagedHypothesis()?.body !== pending.body) throw Error("storage");
      } catch { announce("无法保存事前登记原ID与正文；尚未提交。", true); return null; }
    }
    if (pending.command === "model-supplied-quality-plan-adopt" && !recoverQuality) {
      try { sessionStorage.setItem(QUALITY_PENDING_KEY, JSON.stringify({command: pending.command, body: pending.body}));
        if (savedQualityRequest()?.body !== pending.body) throw Error("storage");
      } catch { announce("无法保存严格采纳原ID与正文；尚未提交。", true); return null; }
    }
    if (pending.command === "manual-quality-plan-prepare") {
      try { const original = obj(JSON.parse(pending.body)); sessionStorage.setItem(MANUAL_PREPARE_KEY, JSON.stringify(original));
        if (!sameValue(savedManual(MANUAL_PREPARE_KEY), original)) throw Error("storage");
      } catch { announce("无法保存人工计划原ID与选择；尚未提交。", true); return null; }
    }
    if (recoverManual) {
      busy = true; controls();
      try {
        const original = obj(JSON.parse(pending.body)), encoded = text(original.response_base64, ""), binary = atob(encoded);
        const digest = await sha256(Uint8Array.from(binary, char => char.charCodeAt(0)));
        const prior = savedManual(MANUAL_IMPORT_KEY), marker = {request_id:original.request_id, project_id:original.project_id, response_sha256:digest};
        if (prior && !sameValue(prior, marker)) throw Error("原回答 SHA 不同；保留首次请求，不会导入替换文件。");
        if (!prior) sessionStorage.setItem(MANUAL_IMPORT_KEY, JSON.stringify(marker));
        if (!sameValue(savedManual(MANUAL_IMPORT_KEY), marker)) throw Error("无法保存原回答 SHA；尚未提交。");
      } catch (error) { busy = false; controls(); announce(error instanceof Error ? error.message : "原回答无法核对；尚未提交。", true); return null; }
    }
    const modelCommand = MODEL_COMMANDS.has(pending.command);
    const continuation = pending.command === "continue" ? obj(JSON.parse(pending.body)) : {};
    const modelContinuation = pending.command === "continue" && (continuation.plan_mode === "suggest" || continuation.execution_mode === "model");
    lastRequest = pending; busy = true; controls(); downloads(); announce(modelCommand || modelContinuation ? "正在处理原模型请求；将保留回答和实际行动结果…" : "正在提交一次明确的本地命令…");
    if (pending.command === "evidence") evidencePending.set(targetProject, pending);
    try { sessionStorage.setItem(PENDING_KEY, JSON.stringify({ request_id: pending.requestId, command: pending.command })); } catch { /* Host journal remains authoritative. */ }
    let outcomeMessage = "", failed = false, accepted: Obj | null = null;
    try {
      const route = recoverQuality ? "model-supplied-quality-plan-resume" : pending.command;
      const response = await fetch("/api/local-workbench/" + route, { method: "POST", credentials: "same-origin", cache: "no-store",
        headers: { "Content-Type": "application/json", "X-AutoResearch-CSRF": text(description.csrf_token, "") }, body: pending.body, signal: AbortSignal.timeout(modelContinuation ? 420000 : modelCommand ? 210000 : 60000) });
      let result = obj(await response.json());
      if (response.ok && ["staged-feedback", "staged-feedback-resume"].includes(pending.command)) {
        const marker = savedStagedFeedback(), original = marker ? obj(JSON.parse(marker.body)) : {}, identity = obj(marker?.stagedFeedbackContext);
        const valid = (value:Obj):boolean => {
          const controller = obj(value.controller), proposal = obj(controller.selection_proposal), choice = obj(proposal.choice), action = obj(obj(controller.decision).next_action);
          const parentResult = obj(controller.result), child = obj(parentResult.child), waiting = value.status === "waiting";
          const feedback = obj(identity.feedback), branch = obj(obj(feedback.branches)[text(feedback.outcome, "")]), auditCandidates = items(identity.audit_candidates);
          return !!marker && value.schema_version === "local-workbench-command-v1" && value.command === "advance_staged_feedback"
            && ["waiting", "completed"].includes(text(value.status, "")) && value.request_id === marker.requestId && value.project_id === original.project_id && typeof value.replayed === "boolean"
            && controller.schema_version === "project-controller-advance-v1" && controller.project_id === original.project_id && controller.request_id === marker.requestId
            && controller.status === value.status && typeof controller.replayed === "boolean" && typeof controller.request_sha256 === "string" && /^[0-9a-f]{64}$/.test(controller.request_sha256)
            && controller.selection_context_sha256 === identity.context_sha256 && proposal.context_sha256 === identity.context_sha256
            && (waiting ? choice.kind === "wait" && action.kind === "external_wait" && controller.child_request_id === null && controller.result === null
              : branch.kind === "method" && branch.method_id === "research.relevance-validation-saved-audit" && auditCandidates.length === 1 && choice.candidate_id === auditCandidates[0].id
                && choice.kind === "execute" && action.method_id === "research.relevance-validation-saved-audit" && sameValue(action.parameters, {based_on_action_id:original.primary_action_id, based_on_result_sha256:identity.primary_result_sha256})
                && child.command === action.method_id && child.status === "completed" && child.request_id === controller.child_request_id && typeof child.id === "string" && !!child.id
                && typeof child.result_sha256 === "string" && /^[0-9a-f]{64}$/.test(child.result_sha256) && parentResult.recovered === false && parentResult.reused === false);
        };
        if (!valid(result)) throw Error("staged feedback receipt mismatch");
        if (pending.command === "staged-feedback") {
          const check = await fetch("/api/local-workbench/staged-feedback-resume", {method:"POST", credentials:"same-origin", cache:"no-store",
            headers:{"Content-Type":"application/json", "X-AutoResearch-CSRF":text(description.csrf_token, "")},
            body:JSON.stringify({request_id:marker!.requestId, project_id:original.project_id}), signal:AbortSignal.timeout(60000)});
          const checked = obj(await check.json());
          if (!check.ok || !valid(checked) || !sameValue(checked.controller, result.controller)) throw Error("staged feedback verification failed"); result = checked;
        }
        if (activeId() !== original.project_id || current.id !== original.project_id) throw Error("staged feedback project changed");
        const firstView = await read("/api/local-workbench"), projected = await read("/api/project"), finalView = await read("/api/local-workbench"), latest = await read("/api/project");
        const view = obj(projected.staged_feedback_parents), controller = obj(result.controller), child = obj(obj(controller.result).child);
        const parents = items(view.items).filter(p => p.request_id === marker!.requestId);
        const parent = parents[0], matches = parents.length === 1 && view.schema_version === "staged-feedback-parent-view-v1"
          && view.verification === "state_fields_only_not_claim_sql_or_artifacts" && view.project_id === original.project_id
          && view.run_id === projected.run_id && view.snapshot_ref === projected.snapshot_ref && view.state_version === projected.state_version
          && parent.project_id === original.project_id && parent.run_id === projected.run_id && parent.state_version_before === original.expected_state_version
          && parent.snapshot_ref_before === identity.snapshot_ref && parent.context_sha256 === identity.context_sha256
          && parent.registration_request_id === original.registration_request_id && parent.registration_sha256 === original.registration_sha256
          && parent.primary_action_id === original.primary_action_id && parent.primary_result_sha256 === identity.primary_result_sha256
          && parent.status === result.status && parent.child_request_id === controller.child_request_id
          && parent.decision === (result.status === "waiting" ? "wait" : "audit");
        const actions = items(projected.actions).filter(item => item.id === child.id && item.request_id === child.request_id && item.command === child.command && item.status === "completed" && item.result_sha256 === child.result_sha256);
        if (firstView.active_project_id !== original.project_id || projected.id !== original.project_id || finalView.active_project_id !== original.project_id
            || latest.id !== projected.id || latest.snapshot_ref !== projected.snapshot_ref || latest.state_version !== projected.state_version
            || !matches || (result.status === "completed" && actions.length !== 1) || activeId() !== original.project_id || current.id !== original.project_id) throw Error("staged feedback view changed");
        sessionStorage.removeItem(STAGED_FEEDBACK_PENDING_KEY);
      }
      if (response.ok && ["staged-primary", "staged-primary-resume"].includes(pending.command)) {
        const marker = savedStagedPrimary(), original = marker ? obj(JSON.parse(marker.body)) : {}, identity = obj(marker?.stagedPrimaryContext);
        const valid = (value: Obj): boolean => {
          const controller = obj(value.controller), proposal = obj(controller.selection_proposal), decision = obj(controller.decision);
          const parentResult = obj(controller.result), child = obj(parentResult.child), action = obj(decision.next_action);
          return !!marker && value.schema_version === "local-workbench-command-v1" && value.command === "advance_staged_primary"
            && value.status === "completed" && value.request_id === marker.requestId && value.project_id === original.project_id
            && typeof value.replayed === "boolean" && controller.schema_version === "project-controller-advance-v1"
            && controller.status === "completed" && controller.project_id === original.project_id && controller.request_id === marker.requestId
            && typeof controller.replayed === "boolean" && typeof controller.request_sha256 === "string" && /^[0-9a-f]{64}$/.test(controller.request_sha256)
            && controller.selection_context_sha256 === identity.context_sha256 && proposal.context_sha256 === identity.context_sha256
            && proposal.rationale === original.reason && obj(proposal.choice).kind === "execute" && obj(proposal.choice).candidate_id === identity.candidate_id
            && action.method_id === "research.relevance-validation-pair" && child.command === action.method_id
            && child.status === "completed" && child.request_id === controller.child_request_id && typeof child.id === "string" && !!child.id
            && typeof child.result_sha256 === "string" && /^[0-9a-f]{64}$/.test(child.result_sha256)
            && parentResult.recovered === false && parentResult.reused === false;
        };
        if (!valid(result)) throw Error("staged primary receipt mismatch");
        if (pending.command === "staged-primary") {
          const check = await fetch("/api/local-workbench/staged-primary-resume", {method:"POST", credentials:"same-origin", cache:"no-store",
            headers:{"Content-Type":"application/json", "X-AutoResearch-CSRF":text(description.csrf_token, "")},
            body:JSON.stringify({request_id:marker!.requestId, project_id:original.project_id}), signal:AbortSignal.timeout(60000)});
          const checked = obj(await check.json());
          if (!check.ok || !valid(checked) || !sameValue(checked.controller, result.controller)) throw Error("staged primary verification failed");
          result = checked;
        }
        if (activeId() !== original.project_id || current.id !== original.project_id) throw Error("staged primary project changed");
        const firstView = await read("/api/local-workbench"), projected = await read("/api/project"), finalView = await read("/api/local-workbench");
        const child = obj(obj(obj(result.controller).result).child);
        const actions = items(projected.actions).filter(item => item.id === child.id && item.request_id === child.request_id
          && item.command === child.command && item.status === "completed" && item.result_sha256 === child.result_sha256);
        if (firstView.active_project_id !== original.project_id || projected.id !== original.project_id
            || finalView.active_project_id !== original.project_id || actions.length !== 1
            || activeId() !== original.project_id || current.id !== original.project_id) throw Error("staged primary view changed");
        sessionStorage.removeItem(STAGED_PRIMARY_PENDING_KEY);
      }
      if (response.ok && ["staged-hypothesis", "staged-hypothesis-resume"].includes(pending.command)) {
        const marker = savedStagedHypothesis(), original = marker ? obj(JSON.parse(marker.body)) : null;
        const valid = (value: Obj): boolean => {
          const registration = obj(value.registration), request = obj(registration.request);
          return value.schema_version === "local-workbench-command-v1" && value.command === "register_staged_hypothesis"
            && value.status === "completed" && value.request_id === pending.requestId && value.project_id === targetProject
            && typeof value.replayed === "boolean" && registration.schema_version === "hypothesis-registration-v2"
            && registration.request_id === pending.requestId && registration.project_id === targetProject
            && typeof registration.registration_sha256 === "string" && /^[0-9a-f]{64}$/.test(registration.registration_sha256)
            && (!original || (original.request_id === pending.requestId && original.project_id === targetProject
              && sameValue(request, {request_id:original.request_id, expected_state_version:original.expected_state_version, hypothesis:original.hypothesis})));
        };
        if (!valid(result)) throw Error("staged receipt mismatch");
        if (pending.command === "staged-hypothesis") {
          const check = await fetch("/api/local-workbench/staged-hypothesis-resume", {method:"POST", credentials:"same-origin", cache:"no-store",
            headers:{"Content-Type":"application/json", "X-AutoResearch-CSRF":text(description.csrf_token, "")},
            body:JSON.stringify({request_id:pending.requestId, project_id:targetProject}), signal:AbortSignal.timeout(60000)});
          const checked = obj(await check.json());
          if (!check.ok || !valid(checked) || !sameValue(checked.registration, result.registration)) throw Error("staged receipt verification failed");
          result = checked;
        }
        if (activeId() !== targetProject || current.id !== targetProject) throw Error("staged project changed");
        sessionStorage.removeItem(STAGED_HYPOTHESIS_PENDING_KEY);
      }
      if (!response.ok) {
        pending.uncertain = response.status >= 500 || /UNKNOWN|NEEDS_REVIEW|INCOMPLETE/.test(text(result.code, ""));
        const reasons: Record<string, string> = { INVALID_SPEC: "字段声明与CSV需要逐项核对", INVALID_CSV: "CSV编码、表头或行宽不满足范围", INVALID_BUNDLE: "来源文件或选区声明需要核对", INVALID_LOCATOR: "选区坐标不满足当前读取范围", TASK_MISMATCH: "资料与当前取证任务不匹配", STALE_SELECTION_CONTEXT: "项目已变化，请重新读取候选后决定", STALE_STATE: "项目版本或当前选择已变化", IDEMPOTENCY_CONFLICT: "原请求ID已经绑定其他内容", BUDGET_EXHAUSTED: "本地调用额度已用完，已有用量保留", OPERATION_INCOMPLETE: "原操作未完成，需要保留并核对" };
        Object.assign(reasons, { MODEL_DISABLED: "服务尚未启用Claude CLI，请按使用说明启动", HOST_DECISION_LIMIT: "本项目模型决策名额已用尽", HOST_GRANT_CHANGED: "原累计额度和理由已冻结，不能替换", HOST_SELECTION_PENDING: "请核对原模型请求", HOST_USAGE_UNKNOWN: "原模型费用未知，不能按零计后继续发送" });
        reasons.CODE_CHANGED = ["staged-hypothesis", "staged-hypothesis-resume"].includes(pending.command)
          ? "请用 -B 和新空 PYTHONPYCACHEPREFIX 重启原宿主，并核对原项目及源码身份"
          : "当前项目需按使用说明明确升级到本次代码版本";
        reasons.RESOURCE_CONFLICT = "目录已有同ID同版本且内容不同的资源，请核对版本；原资源保留";
        reasons.EXPERIENCE_ALREADY_IMPORTED = "本项目已导入这版案例；撤回后的案例请使用恢复参考入口";
        reasons.EXPERIENCE_LIMIT = "本项目的案例绑定数量已达上限，请核对现有案例";
        const code = text(result.code, String(response.status));
        failed = true; outcomeMessage = "提交未完成：" + (reasons[code] ?? "请核对当前条件与输入") + "（" + code + "）。输入已保留；" + (pending.uncertain ? "结果仍需核对，不自动重发。" : "可以用原ID和原内容显式重试，或核对后修正输入。");
        if (["staged-hypothesis", "staged-hypothesis-resume"].includes(pending.command)) {
          pending.uncertain = true; outcomeMessage = "事前登记尚未确认（" + code + "）；保留原ID和正文，使用只核对入口，不创建替代请求。";
          if (code === "CODE_CHANGED") outcomeMessage += " 请用 -B 和新空 PYTHONPYCACHEPREFIX 重启原宿主并核对源码。";
        }
        if (["staged-feedback", "staged-feedback-resume"].includes(pending.command)) {
          pending.uncertain = true; outcomeMessage = "原反馈尚未确认（" + code + "）；保留原 ID 和正文，只可核对原记录，不会重派。";
        }
        if (["staged-primary", "staged-primary-resume"].includes(pending.command)) {
          pending.uncertain = true; outcomeMessage = "原 primary 尚未确认（" + code + "）；保留原 ID 和正文，只可核对原记录，不会重派。";
          if (code === "CODE_CHANGED") outcomeMessage += " 请用 -B 和新空 PYTHONPYCACHEPREFIX 重启原宿主并核对源码。";
        }
      } else if (["unknown", "running", "pending", "prepared", "sending", "received"].includes(text(result.status, ""))
                 && !(pending.command === "manual-quality-plan-prepare" && result.status === "prepared"
                   && result.request_id === pending.requestId && result.project_id === targetProject
                   && manualPrepareMatches(obj(JSON.parse(pending.body)), obj(result.model_record)))) {
        pending.uncertain = true; failed = true; outcomeMessage = "原请求结果尚未确认，请只读核对保存状态。没有自动重发。";
      } else {
        pending.uncertain = pending.command === "batch" && result.status === "needs_review"; accepted = result;
        outcomeMessage = pending.command === "create" ? "项目已创建，尚未执行方法。请从实际候选中选择下一步。" : pending.command === "select" ? "已切换活动项目，旧候选已清除。"
          : pending.command === "report" ? "当前快照报告已生成，可从顶栏或保存结果区下载。" : pending.command === "evidence" ? "资料已登记，尚未读取。请从真实来源候选中选择并明确执行。" : obj(result.decision).next_action && obj(obj(result.decision).next_action).kind === "external_wait" ? "本次等待已保存，没有创建新行动。" : "本次行动和反馈已保存，请核对结果后再决定下一步。";
        if (["staged-hypothesis", "staged-hypothesis-resume"].includes(pending.command)) outcomeMessage = "原事前条件已核对保存；没有执行检索、审计或模型。";
        if (["staged-feedback", "staged-feedback-resume"].includes(pending.command)) outcomeMessage = (result.status === "waiting" ? "原反馈已核对：本次等待，无新增工具。" : "原反馈审计与 claims 已核对；使用一次保存结果审计工具，未新增排名、评分、模型、拟合或 final。") + " 原选择理由：" + text(obj(obj(result.controller).selection_proposal).rationale);
        if (["staged-primary", "staged-primary-resume"].includes(pending.command)) outcomeMessage = "原 primary 完成记录与 claim 已由原请求核对；使用一次研究工具，未执行 final、模型或拟合。请查看保存反馈。";
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
        if (pending.command === "plan-resume") outcomeMessage = "原计划请求已核对；如此前尚未写入，本次已按原正文保存，否则仅补原回执。未创建新ID。";
        if (pending.command === "manual-quality-plan-prepare") {
          try { const original = obj(JSON.parse(pending.body)), saved = obj(result.model_record);
            const model = await read("/api/local-workbench/model"), projected = await read("/api/project");
            const matches = items(model.records).filter(item => item.request_id === pending.requestId);
            if (activeId() !== targetProject || model.project_id !== targetProject || projected.id !== targetProject
                || projected.snapshot_ref !== original.expected_snapshot_ref || matches.length !== 1
                || matches[0].status !== "prepared" || !manualPrepareMatches(original, matches[0])
                || obj(matches[0].manual_plan_intent).intent_sha256 !== obj(saved.manual_plan_intent).intent_sha256
                || !sameValue(savedManual(MANUAL_PREPARE_KEY), original)) throw Error("identity");
            sessionStorage.removeItem(MANUAL_PREPARE_KEY);
            outcomeMessage = "人工回答的原 Host 计划请求已准备；占用一次 Host 决策名额，未调用模型。请查看原请求并手动导入回答。";
          } catch { pending.uncertain = true; failed = true; accepted = null; outcomeMessage = "原 Host 准备回执未能核对，保留原ID；不会重发。"; }
        }
        if (pending.command === "manual-quality-plan-import") {
          const record = obj(result.model_record), prior = savedManual(MANUAL_IMPORT_KEY);
          if (result.status !== "proposed" || result.request_id !== pending.requestId || result.project_id !== targetProject
              || record.request_id !== pending.requestId || !prior || prior.request_id !== pending.requestId
              || record.response_sha256 !== prior.response_sha256) {
            pending.uncertain = true; failed = true; accepted = null;
            outcomeMessage = "原人工回答回执未能核对；保留原ID和SHA，不会自动重派。";
          } else {
            try {
              const model = await read("/api/local-workbench/model"), matches = items(model.records).filter(item => item.request_id === pending.requestId);
              if (activeId() !== targetProject || model.project_id !== targetProject || matches.length !== 1
                  || matches[0].status !== "proposed" || matches[0].response_sha256 !== prior.response_sha256
                  || obj(matches[0].manual_plan_intent).intent_sha256 !== obj(record.manual_plan_intent).intent_sha256
                  || !sameValue(savedManual(MANUAL_IMPORT_KEY), prior)) throw Error("identity");
              sessionStorage.removeItem(MANUAL_IMPORT_KEY); sessionStorage.removeItem(MANUAL_PREPARE_KEY);
            } catch { pending.uncertain = true; failed = true; accepted = null; }
            outcomeMessage = pending.uncertain ? "原人工回答保存状态仍需核对。" : "人工回答已保存为待审计划建议；模型身份、推理次数和费用未知。没有执行研究。";
          }
        }
        if (pending.command === "model-supplied-quality-plan-adopt") {
          if (Object.keys(result).sort().join(",") !== "command,host_request_id,plan_sha256,plan_version,project_id,replayed,request_id,schema_version,status"
              || result.schema_version !== "local-workbench-command-v1" || result.command !== "model_supplied_quality_plan_adopt"
              || typeof result.replayed !== "boolean" || !Number.isSafeInteger(result.plan_version) || (result.plan_version as number) < 1
              || typeof result.plan_sha256 !== "string" || !/^[a-f0-9]{64}$/.test(result.plan_sha256)
              || result.status !== "applied" || result.request_id !== pending.requestId || result.project_id !== targetProject
              || result.host_request_id !== obj(JSON.parse(pending.body)).host_request_id) {
            pending.uncertain = true; failed = true; accepted = null;
            outcomeMessage = "严格采纳回执身份未能核对，保留原ID和正文；不会自动重派。";
          } else {
            try {
              if (!recoverQuality) {
                const verifiedResponse = await fetch("/api/local-workbench/model-supplied-quality-plan-resume", {
                  method: "POST", credentials: "same-origin", cache: "no-store", signal: AbortSignal.timeout(60000),
                  headers: {"Content-Type":"application/json", "X-AutoResearch-CSRF":text(description.csrf_token, "")}, body:pending.body });
                const verified = obj(await verifiedResponse.json());
                if (!verifiedResponse.ok || verified.replayed !== true
                    || Object.keys(verified).length !== Object.keys(result).length
                    || Object.keys(result).some(key => key !== "replayed" && verified[key] !== result[key])) throw Error("manager identity");
              }
              const projected = await read("/api/project"), model = await read("/api/local-workbench/model"), confirm = await read("/api/project");
              const identities = obj(model.quality_adoption_receipts), matches = items(identities.items).filter(item =>
                item.request_id === pending.requestId && item.host_request_id === result.host_request_id
                && item.plan_version === result.plan_version && item.plan_sha256 === result.plan_sha256);
              const revisions = items(obj(projected.research_plan).revisions).filter(item =>
                item.request_id === result.host_request_id && item.version === result.plan_version);
              if (activeId() !== targetProject || projected.id !== targetProject || confirm.id !== targetProject
                  || model.project_id !== targetProject || identities.project_id !== targetProject
                  || projected.snapshot_ref !== identities.snapshot_ref || confirm.snapshot_ref !== projected.snapshot_ref
                  || matches.length !== 1 || revisions.length !== 1 || savedQualityRequest()?.body !== pending.body) throw Error("identity");
              sessionStorage.removeItem(QUALITY_PENDING_KEY);
              outcomeMessage = "已按原供应质量材料记录计划采用；这不证明模型理解或科学结论。";
            } catch {
              pending.uncertain = true; failed = true; accepted = null;
              outcomeMessage = "严格采纳回执或原计划身份未能核对，保留原ID和正文；不会自动重派。";
            }
          }
        }
        if (pending.command === "recipe-adopt") outcomeMessage = "外环决定已写入项目，后续配方决策将读取当前有效版本。";
        if (pending.command === "design-bind") outcomeMessage = "研究设计与输入声明已保存。请核对检查计划，再明确执行下一项验证。";
        if (pending.command === "design-improve") outcomeMessage = "已根据实际反馈保存候选新版，可在知识空间查看，并明确选择采用。";
        if (pending.command === "design-import") outcomeMessage = "研究设计资源已保存到知识目录，可查看并选择用于项目。";
        if (pending.command === "experience-import") outcomeMessage = "案例快照已加入本项目参考，可在知识空间核对原观察和适用边界。";
        if (pending.command === "experience-status") outcomeMessage = "案例参考资格已更新，原快照和状态历史保留。";
        if (pending.command === "experience-resume") outcomeMessage = "原案例请求已核对收口，沿用首次保存的文件与参数。";
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
    if (pending.command === "plan" && !items(description.pending_requests).some(record => record.command === "save_plan" && record.request_id === pending.requestId)
        && items(obj(current.research_plan).revisions).some(revision => revision.request_id === pending.requestId)) {
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
    if (designPanel.resolved(pending.command, pending.requestId)) {
      pending.uncertain = false; failed = false; accepted = { status: "completed" }; lastRequest = null;
      outcomeMessage = pending.command === "design-bind" ? "已从保存记录确认研究设计与输入声明，可明确执行下一项验证。"
        : pending.command === "design-import" ? "已从保存记录确认资源导入，可在知识目录查看并选择。" : "已从保存记录确认候选新版，可在知识空间查看并选择。";
    }
    if (experiencePanel.resolved(pending.command, pending.requestId)) {
      pending.uncertain = false; failed = false; accepted = { status: "completed" }; lastRequest = null;
      outcomeMessage = "已从原项目保存记录确认案例操作，原快照和状态历史保留。";
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
  try { await refresh(); announce(description.read_only === true ? "只读宿主提供独立研究引用及当前项目保存摘要；其他项目页面未加载。" : description.enabled !== true ? "本地动作未启用，当前只读取保存记录；需宿主显式启动写模式。" : serverPending() ? "原请求尚待核对，只读状态已载入。" : activeId() ? "已恢复活动项目；所有新行动仍需你明确提交。" : "工作台已就绪，先提出问题并选择数据。", description.enabled !== true); }
  catch (error) { announce(error instanceof Error ? error.message : "工作台读取失败，可只读刷新。", true); }
  controls(); downloads();
}
