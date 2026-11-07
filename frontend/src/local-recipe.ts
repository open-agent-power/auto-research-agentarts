/** Preview host-compiled method priorities; only an explicit submit advances one step. */
import { el } from "./dom";

type Obj = Record<string, unknown>;
type Entry = { recipe: Obj; decision: Obj };
type Draft = { selection: string; input: Obj | null; fileName: string; reason: string };
type RoundPreview = { input: Obj; result: Obj; stateVersion: number };
type Host = {
  read(url: string): Promise<Obj>;
  preview(body: Obj): Promise<Obj>;
  submit(name: string, body: Obj): Promise<Obj | null>;
  announce(message: string, error?: boolean): void;
};
const object = (value: unknown): Obj => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const objects = (value: unknown): Obj[] => Array.isArray(value) ? value.map(object) : [];
const text = (value: unknown, fallback = "未记录"): string => typeof value === "string" && value.length ? value : fallback;
const methods: Record<string, string> = { "data.tabular-quality-audit": "表格质量核对", "data.grouped-quality-profile": "分组画像", "data.numeric-association": "数值关联分析", "research.source-selection": "读取来源" };
const method = (value: unknown): string => methods[text(value)] ?? text(value);
const recipeKey = (recipe: Obj): string => JSON.stringify([recipe.id, recipe.version]);

export function recipeName(recipe: Obj): string {
  return objects(recipe.ordered_methods).length ? recipeOrder(recipe) : text(recipe.id, "科研配方");
}

export function recipeReason(value: unknown): string {
  const reasons: Record<string, string> = {
    FIRST_MATCHING_HOST_CANDIDATE: "按配方顺序选中首个匹配的合法候选", LOWER_RECIPE_PRIORITY: "排在本次已选方法之后",
    NO_MATCHING_HOST_CANDIDATE: "当前没有匹配的合法候选", HOST_BLOCKERS: "当前项目存在宿主条件阻断",
    SCOPE_MISMATCH: "当前领域或输入契约与配方不匹配", NEED_MISMATCH: "当前推进需求与配方不匹配",
    NOT_FIRST_MATCHING_CANDIDATE_IN_RECIPE_AND_HOST_ORDER: "不是配方与宿主顺序中的首个匹配候选",
  };
  return reasons[text(value)] ?? text(value, "请核对完整决定");
}

export function recipeOrder(recipe: Obj): string {
  return objects(recipe.ordered_methods).map(item => method(item.method_id)).join(" → ") || "未记录顺序";
}

export function createLocalRecipePanel(host: Host): {
  element: HTMLElement; effectiveElement: HTMLElement; refresh(projectId: string, project: Obj, context: Obj | null): Promise<void>;
  invalidate(): void; setLocked(value: boolean): void;
} {
  const section = el("section", "local-panel local-recipe content-section");
  section.append(el("h2", "section-title", "按配方推进"),
    el("p", "detail-note", "选择推进顺序，核对预览后执行一步。配方按规则选择，不调用模型。"));
  const effectiveElement = el("section", "local-panel content-section local-recipe-current"), effective = el("div", "local-recipe-effective");
  effectiveElement.append(el("h2", "section-title", "当前有效配方"), effective);
  const status = el("p", "notice", "先创建或选择项目，再查看配方预览。"); status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
  const form = el("form", "local-recipe-form local-batch-form"); form.setAttribute("aria-label", "按配方推进");
  const fields = el("fieldset", "local-fieldset"), select = el("select"); select.required = true; select.setAttribute("aria-label", "选择科研配方");
  const label = el("label", "local-field"); label.append(el("span", "local-label", "推进顺序"), select); fields.append(label);
  const preview = el("div", "local-recipe-preview"); preview.setAttribute("aria-live", "polite");
  const start = el("button", "action-button primary", "按此配方推进一步"); start.type = "submit";
  form.append(fields, preview, start); section.append(status, form);
  const roundForm = el("form", "local-recipe-round local-batch-form"); roundForm.setAttribute("aria-label", "保存外环决定");
  const roundFields = el("fieldset", "local-fieldset");
  const file = el("input"); file.type = "file"; file.accept = ".json,application/json";
  const fileLabel = el("label", "local-field");
  fileLabel.append(el("span", "local-label", "选择已保存的外环 input.json"), file,
    el("small", "detail-note", "文件上限 4 MiB。核对使用已有记录。"));
  const fileStatus = el("p", "detail-note", "尚未选择文件。");
  const check = el("button", "action-button", "核对已保存外环"); check.type = "button";
  const roundStatus = el("p", "notice", "选择文件后，明确核对本轮决定。");
  roundStatus.setAttribute("role", "status"); roundStatus.setAttribute("aria-live", "polite");
  const roundResult = el("div", "local-recipe-round-result");
  const reason = el("textarea"); reason.rows = 3; reason.required = true; reason.maxLength = 2000;
  const reasonLabel = el("label", "local-field");
  reasonLabel.append(el("span", "local-label", "保存决定的理由"), reason);
  const adopt = el("button", "action-button primary", "先核对外环决定"); adopt.type = "submit";
  roundFields.append(fileLabel, fileStatus, check, roundStatus, roundResult, reasonLabel, adopt);
  roundForm.append(el("h3", "", "保存外环决定"), roundFields); section.append(roundForm);
  let projectId = "", project: Obj = {}, context: Obj | null = null, entries: Entry[] = [], locked = true, ready = false, generation = 0;
  let roundPreview: RoundPreview | null = null, previewBusy = false, readingFile = false, fileGeneration = 0;
  const drafts = new Map<string, Draft>();
  const draft = (): Draft => {
    let value = drafts.get(projectId);
    if (!value) { value = { selection: "", input: null, fileName: "", reason: "" }; drafts.set(projectId, value); }
    return value;
  };
  const selected = (): Entry | undefined => entries.find(entry => recipeKey(entry.recipe) === select.value);
  const appliedRound = (result: Obj): boolean => objects(project.recipe_revisions).some(record => record.model_request_id === result.request_id);
  const validRound = (): boolean => !!roundPreview && roundPreview.input === draft().input
    && roundPreview.stateVersion === context?.state_version && roundPreview.stateVersion === project.state_version
    && roundPreview.result.project_id === projectId && roundPreview.result.status === "completed"
    && ["keep", "revert"].includes(text(roundPreview.result.decision, "")) && !appliedRound(roundPreview.result);
  const controls = (): void => {
    fields.disabled = locked || !ready || !projectId || previewBusy || readingFile;
    start.disabled = fields.disabled || !selected();
    roundFields.disabled = fields.disabled;
    check.disabled = roundFields.disabled || !draft().input;
    adopt.disabled = roundFields.disabled || !validRound() || !reason.value.trim();
    check.textContent = previewBusy ? "正在核对保存记录…" : "核对已保存外环";
  };
  function clearRound(message: string): void {
    roundPreview = null; roundResult.replaceChildren(); roundStatus.classList.remove("error");
    roundStatus.textContent = message; adopt.textContent = "先核对外环决定";
  }
  function invalidate(): void {
    generation++; fileGeneration++; previewBusy = false; readingFile = false; ready = false;
    preview.replaceChildren(); effective.replaceChildren(el("p", "detail-note", "正在读取当前有效配方…")); status.classList.remove("error");
    clearRound("刷新后请重新核对保存记录，再保存决定。");
    status.textContent = "正在核对当前配方预览…"; controls();
  }
  function showEffective(value: unknown): void {
    effective.replaceChildren();
    const record = object(value), recipe = object(record.recipe);
    if (!text(recipe.id, "")) { effective.append(el("p", "detail-note", "尚未保存项目有效配方。")); return; }
    const decision = record.decision === "keep" ? "已采用候选配方。"
      : record.decision === "revert" ? "已记录回退，保留此版本。" : text(record.decision, "决定尚未记录。");
    effective.append(el("p", "local-recipe-order", recipeName(recipe) + " · v" + String(recipe.version)),
      el("p", "notice", decision), el("p", "", text(record.reason)));
    const raw = el("details", "local-advanced");
    raw.append(el("summary", "", "查看有效配方与原决定"), el("p", "", text(record.explanation)),
      el("pre", "project-source-text", JSON.stringify(record, null, 2)));
    effective.append(raw);
  }
  function showPreview(): void {
    preview.replaceChildren(); const entry = selected();
    start.textContent = "按此配方推进一步";
    if (!ready || !entry) { controls(); return; }
    const choice = object(object(entry.decision.proposal).choice), waiting = choice.kind === "wait";
    const candidate = objects(context?.candidates).find(item => item.id === entry.decision.selected_candidate_id);
    preview.append(el("p", "local-recipe-order", "方法顺序：" + recipeOrder(entry.recipe)),
      el("p", "notice local-recipe-next", waiting ? "当前预览：等待，尚无行动执行。" : "当前预览：" + method(candidate?.method_id) + "，尚未执行。"),
      el("p", "detail-note", "判断理由：" + recipeReason(entry.decision.reason)));
    for (const item of objects(entry.decision.method_decisions)) preview.append(el("p", "detail-note",
      (item.outcome === "selected" ? "选用" : "跳过") + method(item.method_id) + "：" + recipeReason(item.reason) + "。"));
    const raw = el("details", "local-advanced"); raw.append(el("summary", "", "查看配方与本次预览的完整记录"),
      el("pre", "project-source-text", JSON.stringify(entry, null, 2))); preview.append(raw);
    start.textContent = waiting ? "保存本次等待" : "按此配方推进一步"; controls();
  }
  function checkedEntries(result: Obj, seal: string): Entry[] {
    if (!Array.isArray(result.recipes)) throw Error("科研配方列表不完整，请只读刷新后核对。");
    return objects(result.recipes).map(item => {
      const recipe = object(item.recipe), decision = object(item.decision), proposal = object(decision.proposal), choice = object(proposal.choice);
      const matching = objects(context?.candidates).some(candidate => candidate.id === decision.selected_candidate_id && candidate.id === choice.candidate_id);
      if (!text(recipe.id, "") || recipe.version !== decision.recipe_version || recipe.id !== decision.recipe_id
        || decision.schema_version !== "research-recipe-decision-v1" || decision.context_sha256 !== seal || proposal.context_sha256 !== seal
        || !((choice.kind === "wait" && decision.selected_candidate_id === null) || (choice.kind === "execute" && matching)))
        throw Error("配方预览与当前候选或上下文不一致，请只读刷新后核对。");
      return { recipe, decision };
    });
  }
  async function refresh(nextId: string, nextProject: Obj, nextContext: Obj | null): Promise<void> {
    invalidate(); const currentGeneration = generation;
    if (nextId !== projectId) { select.value = drafts.get(nextId)?.selection ?? ""; file.value = ""; }
    projectId = nextId; project = nextProject; context = nextContext;
    reason.value = drafts.get(projectId)?.reason ?? "";
    fileStatus.textContent = draft().fileName ? "已选文件 " + draft().fileName : "尚未选择文件。";
    if (!projectId) {
      entries = []; select.replaceChildren(); effective.replaceChildren(el("p", "detail-note", "先创建或选择项目。"));
      status.textContent = "先创建或选择项目，再查看配方预览。"; controls(); return;
    }
    if (!context || context.project_id !== projectId || project.id !== projectId || typeof context.state_version !== "number" || context.state_version !== project.state_version) {
      effective.replaceChildren(el("p", "detail-note", "当前有效配方尚未完整读取，请只读刷新。"));
      status.textContent = "当前项目条件尚未完整读取，请只读刷新；配方预览和提交已停用。"; controls(); return;
    }
    try {
      const result = await host.read("/api/local-workbench/recipes");
      if (currentGeneration !== generation) return;
      const seal = text(context.context_sha256, "");
      if (result.schema_version !== "local-research-recipes-v1" || result.project_id !== projectId
        || result.state_version !== context.state_version || !/^[a-f0-9]{64}$/.test(seal) || result.context_sha256 !== seal)
        throw Error("科研配方预览已过期，请只读刷新后核对当前项目。");
      entries = checkedEntries(result, seal);
      showEffective(result.effective_recipe);
      const selection = draft().selection, placeholder = el("option", "", "选择本次推进顺序"); placeholder.value = ""; select.replaceChildren(placeholder);
      for (const entry of entries) { const option = el("option", "", recipeName(entry.recipe) + " · v" + String(entry.recipe.version)); option.value = recipeKey(entry.recipe); select.append(option); }
      select.value = entries.some(entry => recipeKey(entry.recipe) === selection) ? selection : ""; ready = true;
      status.textContent = entries.length ? "先选择顺序并核对当前预览，再明确推进一步。" : "当前没有可用配方，已有手工与模型入口保留。";
      clearRound(draft().input ? "已保留文件草稿，请重新核对当前项目。" : "选择文件后，明确核对本轮决定。");
      showPreview();
    } catch (error) {
      if (currentGeneration !== generation) return;
      effective.replaceChildren(el("p", "detail-note", "当前有效配方读取失败，请只读刷新。"));
      status.textContent = "科研配方预览读取失败，提交已停用；选择草稿保留，请只读刷新。"; status.classList.add("error");
      host.announce(error instanceof Error ? error.message : "科研配方预览读取失败。", true);
    } finally { if (currentGeneration === generation) controls(); }
  }
  select.addEventListener("change", () => { if (projectId) draft().selection = select.value; showPreview(); });
  reason.addEventListener("input", () => { if (projectId) draft().reason = reason.value; controls(); });
  file.addEventListener("change", () => {
    const selectedFile = file.files?.[0], currentId = projectId, currentGeneration = ++fileGeneration;
    draft().input = null; draft().fileName = ""; clearRound("请核对新选择的保存记录。");
    fileStatus.textContent = selectedFile ? "正在读取 " + selectedFile.name : "尚未选择文件。";
    if (!selectedFile) { controls(); return; }
    readingFile = true; controls();
    void (async () => {
      try {
        if (selectedFile.size > 4 * 1024 * 1024) throw Error("文件超过 4 MiB，请选择完整且未超限的 input.json。");
        const input = JSON.parse(await selectedFile.text()) as unknown;
        if (!input || typeof input !== "object" || Array.isArray(input)) throw Error("请选择包含完整外环输入对象的 JSON 文件。");
        const value = input as Obj, selection = object(object(value.trace).selection_context);
        if (value.schema_version !== "recipe-improvement-input-v1" || selection.project_id !== currentId)
          throw Error("外环文件不属于当前项目，请选择对应的 input.json。");
        if (currentGeneration !== fileGeneration || currentId !== projectId) return;
        draft().input = value; draft().fileName = selectedFile.name; fileStatus.textContent = "已选文件 " + selectedFile.name;
      } catch (error) {
        if (currentGeneration !== fileGeneration || currentId !== projectId) return;
        fileStatus.textContent = "文件未载入，请重新选择。"; roundStatus.textContent = error instanceof Error ? error.message : "文件读取失败。";
        roundStatus.classList.add("error");
      } finally {
        if (currentGeneration === fileGeneration && currentId === projectId) { readingFile = false; controls(); }
      }
    })();
  });
  check.addEventListener("click", () => {
    const input = draft().input;
    if (locked || !ready || previewBusy || readingFile || !input || !context) return;
    const currentGeneration = generation, currentId = projectId, stateVersion = context.state_version;
    clearRound("正在核对原轮次、请求和实际判据…"); previewBusy = true; controls();
    void (async () => {
      try {
        const response = await host.preview({ project_id: currentId, input });
        if (currentGeneration !== generation || currentId !== projectId) return;
        const result = object(response.result), effectiveRecipe = object(result.effective_recipe);
        if (response.schema_version !== "local-recipe-preview-v1" || response.project_id !== currentId
          || response.state_version !== stateVersion || typeof stateVersion !== "number"
          || result.schema_version !== "recipe-improvement-result-v1" || result.project_id !== currentId
          || result.round_id !== input.round_id || result.request_id !== input.request_id
          || !(result.status === "completed" && ["keep", "revert"].includes(text(result.decision, ""))
            || result.status === "pending" && result.decision === "pending")
          || !text(effectiveRecipe.id, "") || !Number.isInteger(effectiveRecipe.version)
          || !/^[a-f0-9]{64}$/.test(text(result.input_sha256, "")))
          throw Error("核对结果与当前项目、版本或文件不一致，请只读刷新后重新核对。");
        roundPreview = { input, result, stateVersion };
        roundStatus.textContent = appliedRound(result) ? "本轮决定已保存在项目，可在上方查看当前有效配方。" : result.status === "completed"
          ? (result.decision === "keep" ? "本轮决定采用候选，尚未写入项目。" : "本轮决定回退，尚未写入项目。")
          : "本轮尚未收口，保存决定已停用。";
        roundResult.append(el("p", "local-recipe-order", "原版 v" + String(result.base_version)
          + " · 候选 " + (result.candidate_version === null ? "未生成" : "v" + String(result.candidate_version))
          + " · 有效 v" + String(effectiveRecipe.version)),
        el("p", "detail-note", text(result.explanation)),
        el("p", "detail-note", "原轮次 " + text(result.round_id)),
        el("p", "detail-note", "原模型请求 " + text(result.request_id)));
        const labels: Record<string, string> = { baseline_misses_target: "原版未满足本轮目标", candidate_selects_target: "候选选择目标方法与评价",
          controller_completed: "原控制器完成验证", completed_artifact_recorded: "已记录完成行动与工件" };
        const checks = el("ul", "local-recipe-checks");
        for (const [name, passed] of Object.entries(object(result.checks))) checks.append(el("li", "detail-note",
          (labels[name] ?? name) + " · " + (passed === true ? "通过" : passed === false ? "未通过" : "未记录")));
        if (checks.childElementCount) roundResult.append(checks);
        const raw = el("details", "local-advanced"); raw.append(el("summary", "", "查看本轮完整核对结果"),
          el("pre", "project-source-text", JSON.stringify(result, null, 2))); roundResult.append(raw);
        adopt.textContent = appliedRound(result) ? "本轮决定已保存" : result.decision === "pending" ? "等待本轮收口"
          : result.decision === "keep" ? "采用 v" + String(effectiveRecipe.version) : "记录回退，保留 v" + String(effectiveRecipe.version);
      } catch (error) {
        if (currentGeneration !== generation || currentId !== projectId) return;
        clearRound(error instanceof Error ? error.message : "外环核对失败，请只读刷新后重新核对。"); roundStatus.classList.add("error");
      } finally {
        if (currentGeneration === generation && currentId === projectId) { previewBusy = false; controls(); }
      }
    })();
  });
  form.addEventListener("submit", event => {
    event.preventDefault(); const entry = selected();
    if (fields.disabled || !entry || !context || !form.reportValidity()) return;
    void host.submit("advance-recipe", { project_id: projectId, expected_state_version: context.state_version, recipe: entry.recipe });
  });
  roundForm.addEventListener("submit", event => {
    event.preventDefault();
    if (roundFields.disabled || !validRound() || !roundPreview || !reason.value.trim() || !roundForm.reportValidity()) return;
    void host.submit("recipe-adopt", { project_id: projectId, expected_state_version: roundPreview.stateVersion,
      input: roundPreview.input, reason: reason.value.trim() });
  });
  controls();
  return { element: section, effectiveElement, refresh, invalidate, setLocked(value: boolean): void { locked = value; controls(); } };
}
