/** Five real active-project views; persistent operation DOM belongs to the host. */
import { $, el } from "./dom";
import { renderProjectPage, type ActiveProjectPage } from "./project-view";
import { createProjectFlow } from "./project-flow";
import { createSavedStudy } from "./saved-study";

type Obj = Record<string, unknown>;
const labels: Record<ActiveProjectPage, string> = { overview: "项目总览", research: "研究推进", experiments: "实验中心", knowledge: "知识空间", outputs: "成果与复现" };
const subtitles: Record<ActiveProjectPage, string> = {
  overview: "当前课题、真实进展和下一步。", research: "在无限画布中追溯实际记录；操作须另行明确提交。",
  experiments: "当前项目的真实检查、指标、失败与反馈。", knowledge: "已登记原件、已读片段和可核对的出处。", outputs: "阅读已保存结果、核对依据与未决问题，下载当前报告。",
};
export type ProjectOperation = "action" | "evidence" | "continuation" | "model" | "recipe";

export function createProjectPages(host: HTMLElement, options: {
  shared: HTMLElement[]; management: HTMLElement[]; operations: Record<ProjectOperation, HTMLElement>; planning: HTMLElement[];
  feedback: HTMLElement; design: HTMLElement; designLibrary: HTMLElement; experience: HTMLElement; reportButton: HTMLButtonElement;
  announce(message: string, error?: boolean): void;
}): { update(project: Obj, context: Obj | null, readOnly?: boolean): Promise<void>; revealOperation(name: ProjectOperation, recoveryKey: string): void } {
  const common = el("div", "project-workspace-common"); common.append(...options.shared);
  const panes = new Map<ActiveProjectPage, HTMLElement>(), content = new Map<ActiveProjectPage, HTMLElement>();
  for (const page of Object.keys(labels) as ActiveProjectPage[]) {
    const pane = el("section", "project-workspace-page"), heading = el("header", "page-heading"); pane.dataset.projectPage = page;
    const copy = el("div"); copy.append(el("h1", "", labels[page]), el("p", "", subtitles[page])); heading.append(copy);
    const body = el("div", "project-workspace-sections"); pane.append(heading, body); panes.set(page, pane); content.set(page, body);
  }
  const manage = el("details", "project-management content-section"), managementSummary = el("summary", "", "切换项目或创建课题");
  manage.append(managementSummary, ...options.management); panes.get("overview")?.insertBefore(manage, content.get("overview")!);
  const original = el("section", "project-original-entry content-section");
  const originalLink = el("a", "text-button", "进入 P02 研究工作区 ↗"); originalLink.href = "http://127.0.0.1:18785/#/overview"; originalLink.target = "_blank"; originalLink.rel = "noopener";
  original.append(el("h2", "section-title", "原研究工作区"), el("p", "", "P02 · ChemoTopoChip：细胞与材料表面研究。该入口保留原课题五页与记录，与当前研究项目分别阅读。"), originalLink); panes.get("overview")?.append(original);
  const flow = createProjectFlow(options.announce), operation = el("details", "project-operations content-section");
  operation.append(el("summary", "", "开展下一步 · 方法选择、资料登记与连续批次"), el("p", "detail-note", "展开只显示已有操作草稿，不会执行方法。所有操作仍需明确提交；切页保留原请求、输入与未确认状态。"), options.operations.action);
  const operationGroups = new Map<ProjectOperation, HTMLDetailsElement>(), revealed = new Set<string>();
  for (const [name, title] of [["evidence", "补充资料与选区"], ["continuation", "按授权连续推进"],
    ["model", "模型建议与原请求"], ["recipe", "配方选择与采用结果"]] as const) {
    const group = el("details", "local-advanced project-operation-group");
    group.append(el("summary", "", title), options.operations[name]); operationGroups.set(name, group); operation.append(group);
  }
  function revealOperation(name: ProjectOperation, recoveryKey: string): void {
    const key = name + ":" + recoveryKey;
    if (revealed.has(key)) return;
    revealed.add(key); operation.open = true;
    const group = operationGroups.get(name); if (group) group.open = true;
  }
  const research = panes.get("research")!; research.insertBefore(flow.element, content.get("research")!); research.insertBefore(operation, content.get("research")!);
  flow.element.before(options.design, ...options.planning);
  panes.get("knowledge")?.insertBefore(options.designLibrary, content.get("knowledge")!);
  panes.get("knowledge")?.insertBefore(options.experience, content.get("knowledge")!);
  const caseLink = el("a", "text-button", "阅读或导入历史方法案例"); caseLink.href = "#/knowledge?focus=experience";
  panes.get("knowledge")!.querySelector(".page-heading > div")!.append(caseLink);
  const focusTargets = { operations: operation, plan: options.planning[0], feedback: options.feedback, design: options.design, experience: options.experience };
  for (const target of Object.values(focusTargets)) { target.classList.add("project-route-target"); target.tabIndex = -1; }
  const savedStudy = createSavedStudy();
  host.replaceChildren(common, ...panes.values(), savedStudy.element);
  const nav = $("sections"); nav.replaceChildren();
  const icons = { overview: "◈", research: "⌁", experiments: "⚗", knowledge: "▤", outputs: "▧" };
  for (const page of Object.keys(labels) as ActiveProjectPage[]) {
    const link = el("a", "nav-item"); link.href = "#/" + page; link.dataset.page = page;
    link.append(el("span", "nav-icon", icons[page]), el("span", "", labels[page])); nav.append(link);
  }
  const savedLink = el("a", "nav-item"); savedLink.href = "#/saved-study"; savedLink.dataset.page = "saved-study";
  savedLink.append(el("span", "nav-icon", "▥"), el("span", "", "保存研究")); nav.append(savedLink);
  const brand = document.querySelector<HTMLAnchorElement>(".brand"); if (brand) brand.href = "#/overview";
  let current: Obj = {}, activePage: ActiveProjectPage | "saved-study" | null = null, focusPending = true;
  const bookmarks = new Map<ActiveProjectPage, number>();
  function route(): void {
    focusPending = true;
    const key = location.hash.split("?")[0].slice(2), page: ActiveProjectPage | "saved-study" = key === "saved-study" ? key : Object.hasOwn(labels, key) ? key as ActiveProjectPage : "overview";
    if (location.hash.split("?")[0] !== "#/" + page) history.replaceState(null, "", "#/" + page);
    if (activePage && activePage !== "saved-study") bookmarks.set(activePage, scrollY);
    if (activePage === "saved-study") savedStudy.deactivate();
    for (const [name, pane] of panes) pane.hidden = name !== page;
    savedStudy.element.hidden = page !== "saved-study";
    for (const link of nav.querySelectorAll<HTMLAnchorElement>("[data-page]")) {
      const selected = link.dataset.page === page; link.classList.toggle("active", selected);
      if (selected) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
    }
    activePage = page; document.title = (page === "saved-study" ? "保存研究" : labels[page]) + " · 空间研究";
    if (page === "saved-study") savedStudy.activate();
    if (page === "research") flow.activate();
    requestAnimationFrame(() => {
      if (!focusRoute()) window.scrollTo({ top: page === "saved-study" ? 0 : bookmarks.get(page) ?? 0, behavior: "instant" });
    });
  }
  function focusRoute(): boolean {
    const key = new URLSearchParams(location.hash.split("?")[1] ?? "").get("focus");
    const researchFocus = activePage === "research" && (key === "operations" || key === "plan" || key === "feedback" || key === "design");
    if (!focusPending || !current.id || !researchFocus && !(activePage === "knowledge" && key === "experience")) return false;
    const target = focusTargets[key as keyof typeof focusTargets];
    if (target.hidden) return false;
    focusPending = false;
    if (key === "operations") operation.open = true;
    if (key === "feedback") target.querySelector<HTMLDetailsElement>(".researcher-feedback-editor")!.open = true;
    const focus = key === "operations" ? operation.querySelector<HTMLElement>("summary")! : key === "feedback" ? target.querySelector<HTMLElement>(".researcher-feedback-editor > summary")! : target;
    focus.focus({ preventScroll: true });
    target.scrollIntoView({ block: "start", behavior: "instant" }); return true;
  }
  caseLink.addEventListener("click", event => {
    if (location.hash === caseLink.hash) { event.preventDefault(); focusPending = true; focusRoute(); }
  });
  window.addEventListener("hashchange", route); route();
  async function update(project: Obj, context: Obj | null, readOnly = false): Promise<void> {
    current = project;
    for (const [page, target] of content) {
      const subtitle = panes.get(page)?.querySelector<HTMLElement>(".page-heading p");
      if (subtitle) subtitle.textContent = readOnly ? "此只读宿主未加载项目页面；可前往保存研究查看项目摘要和外部研究。" : subtitles[page];
      if (project.id) renderProjectPage(target, project, page, context);
      else if (readOnly) {
        const empty = el("div", "empty-state"), link = el("a", "text-button", "查看保存研究与项目摘要 →"); link.href = "#/saved-study";
        empty.append(el("p", "", "只读宿主未加载当前项目页面。"), link); target.replaceChildren(empty);
      } else target.replaceChildren(el("p", "empty-state", page === "overview" ? "尚无活动课题。展开下方入口创建或选择已有项目。" : "先在项目总览创建或选择课题；此页不会填入其他课题的示例结果。"));
      if (page === "outputs" && project.id) target.querySelector(".project-report-actions")!.prepend(options.reportButton);
    }
    if (readOnly) caseLink.remove();
    manage.open = !project.id;
    flow.update(project); if (activePage === "research") flow.activate();
    requestAnimationFrame(focusRoute);
  }
  return { update, revealOperation };
}
