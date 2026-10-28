import "./styles.css";
import { $, date, el } from "./dom";
import * as api from "./api";
import { ResearchBoard } from "./board";
import { renderDetails, renderReading, type ContentContext } from "./content";
import { objectsFor, kindLabels } from "./model";
import type { Project, ResearchObject, SectionName, Viewport } from "./types";

let project: Project | null = null;
let objects: ResearchObject[] = [];
let board: ResearchBoard | null = null;
let mode: "canvas" | "list" = matchMedia("(max-width:720px)").matches ? "list" : "canvas";
let section: SectionName = "overview";
let selected = "";
let draft = "";
let downloadBusy = false;
let previousFocus: HTMLElement | null = null;
let previousViewport: Viewport | null = null;
let toastTimer = 0;
const mobile = () => matchMedia("(max-width:720px)").matches;
const sectionTitles: Record<SectionName, string> = { overview: "研究全景", sources: "依据与来源", trials: "假设与真实试验", claims: "判断与适用边界", paper: "论文与图表", questions: "后续研究问题" };

function toast(message: string, error = false): void {
  clearTimeout(toastTimer);
  const element = $("toast"); element.textContent = message; element.classList.toggle("error", error); element.hidden = false;
  toastTimer = window.setTimeout(() => { element.hidden = true; }, error ? 8000 : 5000);
}
function controls(): void {
  const ready = project !== null;
  document.querySelectorAll<HTMLButtonElement>("#sections button").forEach((button) => { button.disabled = !ready; });
  $<HTMLInputElement>("search").disabled = !ready;
  for (const id of ["view-canvas", "view-list"]) $<HTMLButtonElement>(id).disabled = !ready;
  for (const id of ["save-layout", "restore-layout", "reset-layout", "zoom-in", "zoom-out", "zoom-reset", "fit-view"]) $<HTMLButtonElement>(id).disabled = !board || mode === "list";
  $<HTMLButtonElement>("download-pdf").disabled = !ready || downloadBusy || project?.exports.pdf !== "/api/export/paper.pdf";
  $<HTMLButtonElement>("download-zip").disabled = !ready || downloadBusy || project?.exports.reproduction !== "/api/export/reproduction.zip";
}
function counts(): void {
  if (!project) return;
  $("count-all").textContent = String(objects.length);
  $("count-sources").textContent = String(project.sources.length);
  $("count-trials").textContent = String(project.trials.length);
  $("count-claims").textContent = String(project.claims.length);
  $("count-questions").textContent = String(project.next_questions.length);
}
function context(): ContentContext {
  if (!project) throw new Error("项目尚未载入");
  return {
    project, objects, find: (id) => objects.find((object) => object.rawId === id), open: openDetails,
    download: (format) => { void download(format); }, draft: () => draft, setDraft: (value) => { draft = value; },
    save: async (value) => {
      if (!project) throw new Error("项目尚未载入");
      const question = await api.saveQuestion(project.csrf_token || "", value);
      if (!project.next_questions.some((item) => item.id === question.id)) project.next_questions.push(question);
      draft = ""; objects = objectsFor(project); board?.updateObjects(objects); counts();
      toast("问题已保存为待人工执行；没有启动模型或试验。");
    },
    layout: { save: () => board?.save(), restore: () => board?.restore(), reset: () => board?.reset() },
  };
}
function modalState(open: boolean): void {
  const isModal = open && mobile();
  const inspector = $("inspector");
  inspector.setAttribute("role", isModal ? "dialog" : "complementary");
  if (isModal) inspector.setAttribute("aria-modal", "true"); else inspector.removeAttribute("aria-modal");
  for (const id of ["project-nav", "topbar", "graph", "reading-view", "canvas-dock"]) $(id).inert = isModal;
}
function openDetails(id: string): void {
  if (!project) return;
  const object = objects.find((item) => item.id === id); if (!object) return;
  if ($("inspector").hidden) {
    previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    previousViewport = mode === "canvas" ? board?.viewport() || null : null;
  }
  selected = id; board?.select(id);
  $("inspector-kind").textContent = kindLabels[object.kind] + " · 原始记录";
  $("inspector-title").textContent = object.title;
  renderDetails($("inspector-body"), object, context());
  $("inspector-body").scrollTop = 0;
  $("inspector").hidden = false; document.body.classList.add("has-inspector"); modalState(true);
  if (mode === "canvas" && !mobile()) board?.focus(id);
  $("inspector-title").focus({ preventScroll: true });
}
function closeDetails(restoreFocus = true): void {
  if ($("inspector").hidden) return;
  $("inspector").hidden = true; document.body.classList.remove("has-inspector"); modalState(false);
  if (previousViewport) board?.restoreViewport(previousViewport);
  previousViewport = null;
  board?.select(selected);
  if (mode === "list" && project) renderReading($("reading-content"), section, context());
  if (restoreFocus) {
    if (previousFocus?.isConnected && !previousFocus.closest("[hidden]")) previousFocus.focus({ preventScroll: true });
    else $("search").focus({ preventScroll: true });
  }
}
function setMode(value: "canvas" | "list"): void {
  mode = value;
  document.body.classList.toggle("view-list", mode === "list");
  document.body.classList.toggle("view-canvas", mode === "canvas");
  $("reading-view").hidden = mode !== "list";
  for (const [id, active] of [["view-canvas", mode === "canvas"], ["view-list", mode === "list"]] as const) {
    $(id).classList.toggle("active", active); $(id).setAttribute("aria-pressed", String(active));
  }
  if (project && mode === "list") renderReading($("reading-content"), section, context());
  controls();
}
function selectSection(value: SectionName): void {
  section = value;
  document.querySelectorAll<HTMLElement>("[data-section]").forEach((element) => {
    const active = element.dataset.section === value; element.classList.toggle("active", active);
    if (active) element.setAttribute("aria-current", "page"); else element.removeAttribute("aria-current");
  });
  $("reading-title").textContent = sectionTitles[value];
  if (!project) return;
  if (mode === "list") { closeDetails(false); renderReading($("reading-content"), section, context()); $("reading-view").scrollTop = 0; }
  else if (value === "overview") { closeDetails(false); board?.fit(); }
  else if (value === "paper" || value === "questions") { const object = objects.find((item) => item.kind === value); if (object) openDetails(object.id); }
  else { closeDetails(false); board?.focusGroup(({ sources: "evidence", trials: "experiments", claims: "conclusions" } as Record<string, string>)[value]); }
}
function search(): void {
  const query = $<HTMLInputElement>("search").value.trim().toLocaleLowerCase();
  const results = $("search-results"); results.replaceChildren(); results.hidden = !query;
  if (!query) return;
  const matches = objects.filter((object) => (object.title + " " + object.summary + " " + object.rawId).toLocaleLowerCase().includes(query)).slice(0, 8);
  matches.forEach((object) => {
    const button = el("button", "search-result");
    button.append(el("small", "", kindLabels[object.kind]), el("strong", "", object.title));
    button.addEventListener("click", () => { openDetails(object.id); results.hidden = true; });
    results.append(button);
  });
  if (!matches.length) results.append(el("p", "empty-state", "当前证据中没有匹配对象。"));
}
async function download(format: "pdf" | "reproduction"): Promise<void> {
  if (!project || downloadBusy) return;
  const path = format === "pdf" ? "/api/export/paper.pdf" : "/api/export/reproduction.zip";
  if (project.exports[format] !== path) { toast("当前快照没有可用的导出入口。", true); return; }
  downloadBusy = true; controls(); toast("正在获取本地成果文件，不会启动新研究。");
  try { await api.download(format); toast("文件已交给浏览器下载，请查看下载记录。"); }
  catch (error) { toast(error instanceof DOMException && error.name === "AbortError" ? "获取文件超时，请稍后重试。" : error instanceof Error ? error.message : "下载未完成。", true); }
  finally { downloadBusy = false; controls(); }
}
async function load(): Promise<void> {
  board?.dispose(); board = null; project = null; objects = [];
  closeDetails(false); $("page-state").hidden = false; $("retry").hidden = true;
  $("state-title").textContent = "正在读取本地证据"; $("state-message").textContent = "不会启动模型、训练或新的研究行动。";
  document.querySelector<HTMLElement>(".loader")!.hidden = false; controls();
  try {
    project = await api.loadProject(); objects = objectsFor(project);
    $("project-title").textContent = project.title; $("project-title").title = project.title;
    $("nav-project-title").textContent = project.title;
    $("snapshot-label").textContent = "证据 " + project.snapshot.sha256.slice(0, 8) + " · " + date(project.snapshot.created_at);
    document.title = project.title + " · 空间研究"; counts();
    try {
      board = new ResearchBoard($("graph"), project, objects, {
        select: openDetails, blank: () => { closeDetails(false); selected = ""; board?.select(""); }, message: toast,
        change: (zoom, dirty) => { $("zoom-reset").textContent = Math.round(zoom * 100) + "%"; $("layout-state").textContent = dirty ? "未保存" : "布局就绪"; },
      });
    } catch { mode = "list"; toast("画布暂不可用，已保留完整阅读与成果路径。", true); }
    $("page-state").hidden = true; setMode(mode); controls();
    if (!project.trials.length) toast("当前快照没有试验记录，不据此推断研究效果。");
  } catch (error) {
    project = null; $("state-title").textContent = "研究证据暂未载入";
    $("state-message").textContent = error instanceof Error ? error.message : "请检查本地服务后重试。";
    document.querySelector<HTMLElement>(".loader")!.hidden = true; $("retry").hidden = false; controls();
  }
}
$("retry").addEventListener("click", () => { void load(); });
document.querySelector<HTMLAnchorElement>(".skip-link")?.addEventListener("click", (event) => {
  event.preventDefault();
  if (project) { closeDetails(false); setMode("list"); $("reading-view").focus(); }
  else { $("state-title").tabIndex = -1; $("state-title").focus(); }
});
$("view-canvas").addEventListener("click", () => { setMode("canvas"); if (mobile()) board?.fit(); });
$("view-list").addEventListener("click", () => { setMode("list"); });
$("reading-to-canvas").addEventListener("click", () => setMode("canvas"));
$("download-pdf").addEventListener("click", () => { void download("pdf"); });
$("download-zip").addEventListener("click", () => { void download("reproduction"); });
$("close-inspector").addEventListener("click", () => closeDetails());
$("save-layout").addEventListener("click", () => board?.save());
$("restore-layout").addEventListener("click", () => board?.restore());
$("reset-layout").addEventListener("click", () => board?.reset());
$("zoom-in").addEventListener("click", () => board?.zoom(.1));
$("zoom-out").addEventListener("click", () => board?.zoom(-.1));
$("zoom-reset").addEventListener("click", () => board?.zoomReset());
$("fit-view").addEventListener("click", () => board?.fit());
$("search").addEventListener("input", search);
$("search").addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === "ArrowDown") { event.preventDefault(); $("search-results").querySelector<HTMLButtonElement>("button")?.focus(); } });
document.querySelectorAll<HTMLElement>("[data-section]").forEach((element) => element.addEventListener("click", () => selectSection(element.dataset.section as SectionName)));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") { if (!$("inspector").hidden) closeDetails(); else { $<HTMLInputElement>("search").value = ""; search(); } }
  const target = event.target as HTMLElement;
  if (event.key === "/" && !target.closest("input,textarea,[contenteditable]")) { event.preventDefault(); $("search").focus(); }
  if (event.key === "Tab" && mobile() && !$("inspector").hidden) {
    const focusable = [...$("inspector").querySelectorAll<HTMLElement>("button,a[href],input,textarea,[tabindex='0']")].filter((element) => !element.hasAttribute("disabled") && element.offsetParent !== null);
    const first = focusable[0], last = focusable.at(-1);
    if (event.shiftKey && (document.activeElement === first || document.activeElement === $("inspector-title"))) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }
});
matchMedia("(max-width:720px)").addEventListener("change", () => { if (mobile()) { closeDetails(false); setMode("list"); } else modalState(!$("inspector").hidden); });
setMode(mode); void load();

