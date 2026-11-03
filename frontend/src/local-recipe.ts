/** Preview host-compiled method priorities; only an explicit submit advances one step. */
import { el } from "./dom";

type Obj = Record<string, unknown>;
type Entry = { recipe: Obj; decision: Obj };
type Host = { read(url: string): Promise<Obj>; submit(body: Obj): Promise<Obj | null>; announce(message: string, error?: boolean): void };
const object = (value: unknown): Obj => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const objects = (value: unknown): Obj[] => Array.isArray(value) ? value.map(object) : [];
const text = (value: unknown, fallback = "未记录"): string => typeof value === "string" && value.length ? value : fallback;
const methods: Record<string, string> = { "data.grouped-quality-profile": "分组画像", "research.source-selection": "读取来源" };
const method = (value: unknown): string => methods[text(value)] ?? text(value);

export function recipeName(recipe: Obj): string {
  return ({ "tabular-group-first": "先看分组，再读来源", "tabular-source-first": "先读来源，再看分组" } as Record<string, string>)[text(recipe.id)] ?? text(recipe.id, "科研配方");
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
  element: HTMLElement; refresh(projectId: string, project: Obj, context: Obj | null): Promise<void>;
  invalidate(): void; setLocked(value: boolean): void;
} {
  const section = el("section", "local-panel local-recipe content-section");
  section.append(el("h2", "section-title", "按配方推进"),
    el("p", "detail-note", "选择推进顺序，核对预览后执行一步。配方按规则选择，不调用模型。"));
  const status = el("p", "notice", "先创建或选择项目，再查看配方预览。"); status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
  const form = el("form", "local-recipe-form local-batch-form"); form.setAttribute("aria-label", "按配方推进");
  const fields = el("fieldset", "local-fieldset"), select = el("select"); select.required = true; select.setAttribute("aria-label", "选择科研配方");
  const label = el("label", "local-field"); label.append(el("span", "local-label", "推进顺序"), select); fields.append(label);
  const preview = el("div", "local-recipe-preview"); preview.setAttribute("aria-live", "polite");
  const start = el("button", "action-button primary", "按此配方推进一步"); start.type = "submit";
  form.append(fields, preview, start); section.append(status, form);
  let projectId = "", project: Obj = {}, context: Obj | null = null, entries: Entry[] = [], locked = true, ready = false, generation = 0;
  const drafts = new Map<string, string>();
  const selected = (): Entry | undefined => entries.find(entry => entry.recipe.id === select.value);
  const controls = (): void => {
    fields.disabled = locked || !ready || !projectId;
    start.disabled = fields.disabled || !selected();
  };
  function invalidate(): void {
    generation++; ready = false; preview.replaceChildren(); status.classList.remove("error");
    status.textContent = "正在核对当前配方预览…"; controls();
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
    if (nextId !== projectId) select.value = drafts.get(nextId) ?? "";
    projectId = nextId; project = nextProject; context = nextContext;
    if (!projectId) { entries = []; select.replaceChildren(); status.textContent = "先创建或选择项目，再查看配方预览。"; controls(); return; }
    if (!context || context.project_id !== projectId || project.id !== projectId || typeof context.state_version !== "number" || context.state_version !== project.state_version) {
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
      const draft = drafts.get(projectId) ?? select.value, placeholder = el("option", "", "选择本次推进顺序"); placeholder.value = ""; select.replaceChildren(placeholder);
      for (const entry of entries) { const option = el("option", "", recipeName(entry.recipe) + " · v" + String(entry.recipe.version)); option.value = text(entry.recipe.id, ""); select.append(option); }
      select.value = entries.some(entry => entry.recipe.id === draft) ? draft : ""; ready = true;
      status.textContent = entries.length ? "先选择顺序并核对当前预览，再明确推进一步。" : "当前没有可用配方，已有手工与模型入口保留。";
      showPreview();
    } catch (error) {
      if (currentGeneration !== generation) return;
      status.textContent = "科研配方预览读取失败，提交已停用；选择草稿保留，请只读刷新。"; status.classList.add("error");
      host.announce(error instanceof Error ? error.message : "科研配方预览读取失败。", true);
    } finally { if (currentGeneration === generation) controls(); }
  }
  select.addEventListener("change", () => { if (projectId) drafts.set(projectId, select.value); showPreview(); });
  form.addEventListener("submit", event => {
    event.preventDefault(); const entry = selected();
    if (locked || !ready || !entry || !context || !form.reportValidity()) return;
    void host.submit({ project_id: projectId, expected_state_version: context.state_version, recipe: entry.recipe });
  });
  controls();
  return { element: section, refresh, invalidate, setLocked(value: boolean): void { locked = value; controls(); } };
}
