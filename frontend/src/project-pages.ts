/** Five real active-project views; persistent operation DOM belongs to the host. */
import { $, el } from "./dom";
import { renderProjectPage, type ActiveProjectPage } from "./project-view";
import { createProjectFlow } from "./project-flow";

type Obj = Record<string, unknown>;
const object = (value: unknown): Obj => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const text = (value: unknown, fallback = "未记录"): string => typeof value === "string" && value.length ? value : fallback;
const labels: Record<ActiveProjectPage, string> = { overview: "项目总览", research: "研究推进", experiments: "实验中心", knowledge: "知识空间", outputs: "成果与复现" };
const subtitles: Record<ActiveProjectPage, string> = {
  overview: "当前课题、真实进展和下一步。", research: "在无限画布中追溯实际记录；操作须另行明确提交。",
  experiments: "当前项目的真实检查、指标、失败与反馈。", knowledge: "已登记原件、已读片段和可核对的出处。", outputs: "阅读与当前快照匹配的报告，下载原记录及复现输入。",
};

export function createProjectPages(host: HTMLElement, options: {
  shared: HTMLElement[]; management: HTMLElement[]; operations: HTMLElement[];
  read(path: string): Promise<Obj>; announce(message: string, error?: boolean): void;
}): { update(project: Obj): Promise<void> } {
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
  original.append(el("h2", "section-title", "原研究工作区"), el("p", "", "P02 · ChemoTopoChip：细胞与材料表面研究。该入口保留原课题五页与记录，与当前CSV项目分别阅读。"), originalLink); panes.get("overview")?.append(original);
  const flow = createProjectFlow(options.announce), operation = el("details", "project-operations content-section");
  operation.append(el("summary", "", "开展下一步 · 方法选择、资料登记与连续批次"), el("p", "detail-note", "展开只显示已有操作草稿，不会执行方法。所有操作仍需明确提交；切页保留原请求、输入与未确认状态。"), ...options.operations);
  const research = panes.get("research")!; research.insertBefore(flow.element, content.get("research")!); research.insertBefore(operation, content.get("research")!);
  host.replaceChildren(common, ...panes.values());
  const nav = $("sections"); nav.replaceChildren();
  const icons = { overview: "◈", research: "⌁", experiments: "⚗", knowledge: "▤", outputs: "▧" };
  for (const page of Object.keys(labels) as ActiveProjectPage[]) {
    const link = el("a", "nav-item"); link.href = "#/" + page; link.dataset.page = page;
    link.append(el("span", "nav-icon", icons[page]), el("span", "", labels[page])); nav.append(link);
  }
  const brand = document.querySelector<HTMLAnchorElement>(".brand"); if (brand) brand.href = "#/overview";
  let current: Obj = {}, reportToken = 0, activePage: ActiveProjectPage | null = null;
  const bookmarks = new Map<ActiveProjectPage, number>();
  function route(): void {
    const key = location.hash.split("?")[0].slice(2), page: ActiveProjectPage = Object.hasOwn(labels, key) ? key as ActiveProjectPage : "overview";
    if (location.hash.split("?")[0] !== "#/" + page) history.replaceState(null, "", "#/" + page);
    if (activePage) bookmarks.set(activePage, scrollY);
    for (const [name, pane] of panes) pane.hidden = name !== page;
    for (const link of nav.querySelectorAll<HTMLAnchorElement>("[data-page]")) {
      const selected = link.dataset.page === page; link.classList.toggle("active", selected);
      if (selected) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
    }
    activePage = page; document.title = labels[page] + " · 空间研究";
    if (page === "research") flow.activate();
    requestAnimationFrame(() => window.scrollTo({ top: bookmarks.get(page) ?? 0, behavior: "instant" }));
  }
  window.addEventListener("hashchange", route); route();
  async function report(project: Obj, token: number): Promise<void> {
    const target = content.get("outputs")!, capability = object(project.report);
    if (capability.available !== true || capability.stale === true) return;
    const reader = el("article", "project-report-reader content-section"); reader.append(el("p", "notice", "正在读取当前报告正文…")); target.prepend(reader);
    try {
      const value = await options.read("/api/project/report.json");
      if (token !== reportToken || current.id !== project.id) return;
      if (value.project_id !== project.id || value.project_snapshot_ref !== project.snapshot_ref) throw Error("报告快照与当前项目不一致，请重新生成当前报告。");
      const summary = object(value.summary); reader.replaceChildren(el("h2", "section-title", text(value.title, "当前项目报告")), el("p", "", text(summary.method)));
      if (Array.isArray(summary.headers) && Array.isArray(summary.rows)) {
        const viewport = el("div", "project-table-scroll"), table = el("table", "data-table"), head = el("tr"), body = el("tbody");
        for (const value of summary.headers) head.append(el("th", "", String(value))); const thead = el("thead"); thead.append(head); table.append(thead);
        for (const row of summary.rows.slice(0, 16)) if (Array.isArray(row)) { const tr = el("tr"); for (const value of row) tr.append(el("td", "", String(value ?? "未知"))); body.append(tr); }
        table.append(body); viewport.append(table); reader.append(viewport);
      }
      reader.append(el("p", "detail-note", text(summary.result_notice)), el("p", "detail-note", "完整指标、原文选区和输入身份保留在当前报告JSON/Markdown及完整输入中。此处只读摘要，不重新执行或生成图表。"));
    } catch (error) { if (token === reportToken) reader.replaceChildren(el("p", "notice", error instanceof Error ? error.message : "报告正文暂不可读取，原下载入口仍按当前状态核验。")); }
  }
  async function update(project: Obj): Promise<void> {
    current = project; const token = ++reportToken;
    for (const [page, target] of content) {
      if (project.id) renderProjectPage(target, project, page);
      else target.replaceChildren(el("p", "empty-state", page === "overview" ? "尚无活动课题。展开下方入口创建或选择已有项目。" : "先在项目总览创建或选择课题；此页不会填入其他课题的示例结果。"));
    }
    manage.open = !project.id;
    flow.update(project); if (activePage === "research") flow.activate();
    await report(project, token);
  }
  return { update };
}
