import "./styles.css";
import { $, el } from "./dom";
import * as api from "./api";
import { ResearchBoard } from "./board";
import { renderDetails } from "./content";
import { kindLabels, objectsFor } from "./model";
import { knowledgeHash, researchHash, pageLabels, parseRoute, renderPage, type Page, type PageContext } from "./pages";
import { relationObjects } from "./knowledge";
import { mountLocalDemo } from "./local-demo";
import { mountC01 } from "./c01-app";
import type { Layout, Project, ResearchObject } from "./types";

let project: Project | null = null;
let objects: ResearchObject[] = [];
let board: ResearchBoard | null = null;
let boardDirty=false;
let activeHash = "";
let selected = "";
let draft = "";
let downloadBusy = false;
let toastTimer = 0;
let previousFocus: HTMLElement | null = null;
const bookmarks = new Map<string, {scroll: number; focus: string}>();
const readerOrigins = new Map<string, string>();
const canvasSessions=new Map<string,{layout:Layout;dirty:boolean}>();
const content = $("page-content");

function rememberCanvas():void{if(board)canvasSessions.set(board.storageKey,{layout:board.capture(),dirty:boardDirty});}
function saveBoardLayout():void{board?.save();rememberCanvas();}
function restoreBoardLayout():void{board?.restore();rememberCanvas();}
function resetBoardLayout():void{board?.reset();rememberCanvas();}

function toast(message: string, error = false): void {
  clearTimeout(toastTimer); const node = $("toast"); node.textContent = message; node.classList.toggle("error", error); node.hidden = false;
  toastTimer = window.setTimeout(() => { node.hidden = true; }, error ? 8000 : 5000);
}
function remember(focus = ""): void {
  if (!activeHash) return;
  const active = document.activeElement instanceof HTMLElement ? document.activeElement.closest<HTMLElement>("[data-focus-id]")?.dataset.focusId || "" : "";
  bookmarks.set(activeHash, {scroll: window.scrollY, focus: focus || active || (bookmarks.get(activeHash)?.focus || "")});
}
function focusQuestionForm():void{
  const target=document.getElementById("research-questions");if(!target)return;
  target.scrollIntoView({block:"start",behavior:"instant"});target.querySelector<HTMLTextAreaElement>("textarea")?.focus({preventScroll:true});
}
function navigate(hash: string): void { if (location.hash !== hash) { remember(); location.hash = hash; } else if(parseRoute(hash).page==="research"&&new URLSearchParams(hash.split("?")[1]).get("section")==="questions")focusQuestionForm(); }
function readObject(id: string): void {
  closePreview(false); remember(id);
  const from = activeHash.startsWith("#/read/") ? parseRoute(activeHash).from : activeHash || "#/knowledge";
  const hash = "#/read/" + encodeURIComponent(id) + "?from=" + encodeURIComponent(from);
  readerOrigins.set(hash, from); navigate(hash);
}
function returnFromReader(): void {
  const route = parseRoute(location.hash);
  if (readerOrigins.has(location.hash)) history.back(); else navigate(route.from);
}
function context(): PageContext {
  if (!project) throw new Error("项目尚未载入");
  return {
    project, objects, find: (raw) => objects.find((object) => object.rawId === raw), open: openPreview,
    read: readObject, navigate, returnFromReader,
    download: (format) => { void download(format); }, draft: () => draft, setDraft: (value) => { draft = value; },
    save: async (value) => {
      if (!project) throw new Error("项目尚未载入");
      const question = await api.saveQuestion(project.csrf_token || "", value);
      if (!project.next_questions.some((item) => item.id === question.id)) project.next_questions.push(question);
      draft = ""; objects = objectsFor(project);
      toast("已保存为待人工执行，未启动模型或试验。");
    },
    layout: {save: saveBoardLayout, restore: restoreBoardLayout, reset: resetBoardLayout},
  };
}
function modal(open: boolean): void {
  $("project-nav").inert = open; $("app-main").inert = open;
  $("inspector-backdrop").hidden = !open; document.body.classList.toggle("has-inspector", open);
}
function openPreview(id: string): void {
  if (!project) return;
  const object = objects.find((item) => item.id === id); if (!object) return;
  if ($("inspector").hidden) previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  selected = id; board?.select(id);
  $("inspector-kind").textContent = kindLabels[object.kind] + " · 摘要预览";
  $("inspector-title").textContent = object.title;
  const body = $("inspector-body"); body.replaceChildren();
  if (object.kind === "paper") { body.append(el("p", "", project.report.title), el("p", "detail-note", "宽版报告全文、章节目录和图表请在成果与复现中阅读。")); }
  else if (object.kind === "questions") body.append(el("p", "", objects.find((item) => item.kind === "questions")?.summary || "暂无后续问题。"), el("p", "detail-note", "在研究推进页面保存问题，状态仅为待人工执行。"));
  else renderDetails(body, object, context());
  const full = $<HTMLButtonElement>("read-object"); full.textContent = object.kind === "paper" ? "阅读完整报告 ↗" : object.kind === "questions" ? "前往记录后续问题 ↗" : object.kind === "source" ? "阅读资料记录 ↗" : "完整记录 ↗";
  $("inspector").hidden = false; modal(true); $("inspector-title").focus({preventScroll:true});
  document.querySelector(".inspector-scroll")?.scrollTo(0,0);
}
function closePreview(focus = true): void {
  if ($("inspector").hidden) return;
  $("inspector").hidden = true; modal(false);
  if (focus && previousFocus?.isConnected) previousFocus.focus({preventScroll:true});
  previousFocus = null;
}
function controls(): void {
  $<HTMLInputElement>("search").disabled = !project;
  $<HTMLButtonElement>("download-pdf").disabled = !project || downloadBusy || project.exports.pdf !== "/api/export/paper.pdf";
  $<HTMLButtonElement>("download-zip").disabled = !project || downloadBusy || project.exports.reproduction !== "/api/export/reproduction.zip";
  document.querySelectorAll<HTMLButtonElement>(".export-actions button").forEach((button) => { button.disabled = downloadBusy || !project; });
}
async function download(format: "pdf" | "reproduction"): Promise<void> {
  if (!project || downloadBusy) return;
  if (project.exports[format] !== (format === "pdf" ? "/api/export/paper.pdf" : "/api/export/reproduction.zip")) { toast("当前证据的导出地址无法确认。", true); return; }
  downloadBusy = true; controls(); toast("正在准备" + (format === "pdf" ? "研究报告 PDF" : "复现附件 ZIP") + "…");
  try { await api.download(format); toast("文件已交给浏览器下载。"); }
  catch (error) { toast(error instanceof DOMException && error.name === "AbortError" ? "导出等待超时，可检查服务后重试。" : error instanceof Error ? error.message : "下载未完成，请重试。", true); }
  finally { downloadBusy = false; controls(); }
}
function owner(object: ResearchObject): Page { return object.kind === "source" || object.kind === "claim" ? "knowledge" : object.kind === "trial" ? "experiments" : object.kind === "paper" ? "outputs" : object.kind === "questions" ? "research" : "overview"; }
function navigateToObject(object: ResearchObject): void {
  const target = "#/" + owner(object);
  $("search-results").hidden = true; $<HTMLInputElement>("search").value = "";
  if (location.hash !== target) { remember(); location.hash = target; window.setTimeout(() => openPreview(object.id), 70); }
  else openPreview(object.id);
}
function search(): void {
  const query = $<HTMLInputElement>("search").value.trim().toLocaleLowerCase(); const results = $("search-results"); results.replaceChildren();
  if (!query || !project) { results.hidden = true; return; }
  const matches = objects.filter((object) => (object.title + " " + object.summary + " " + object.rawId).toLocaleLowerCase().includes(query)).slice(0,8);
  results.hidden = false;
  if (!matches.length) results.append(el("p", "search-empty", "没有匹配的现有研究对象。"));
  matches.forEach((object) => { const button = el("button", "search-result"); button.append(el("strong", "", object.title), el("small", "", pageLabels[owner(object)] + " / " + kindLabels[object.kind])); button.addEventListener("click", () => navigateToObject(object)); results.append(button); });
}
function createBoard(route: ReturnType<typeof parseRoute>, selection: NonNullable<ReturnType<typeof renderPage>>): void {
  if (!project || !selection.boardContainer) return;
  const hasFilter = route.page==="knowledge"&&(route.type !== "全部" || route.topics.length > 0);
  const subset = relationObjects(project, objects, selection.items, route.panorama, hasFilter);
  const panel = selection.boardContainer;
  if (!subset.length) { panel.replaceChildren(el("p", "knowledge-empty", "这个筛选组合暂无可显示的原始引用关系。")); return; }
  const flow=el("div","workflow-strip glass");flow.setAttribute("aria-label","研究流程定位，阶段顺序不代表引用关系");
  const stages=[["evidence","01","问题与依据"],["experiments","02","提案与实验"],["conclusions","03","判断与下一步"]] as const;
  stages.forEach(([key,num,title],index)=>{const button=el("button","workflow-step");button.dataset.flowStage=key;button.append(el("small","",num),el("span","",title));button.addEventListener("click",()=>board?.focusGroup(key));flow.append(button);if(index<2)flow.append(el("span","workflow-arrow","→"));});panel.append(flow);panel.classList.add("has-flow-header");
  const toolbar = el("div", "canvas-dock glass"); toolbar.setAttribute("aria-label", "关系画布工具");
  const zoomLabel = el("button", "zoom-value", "100%"); zoomLabel.setAttribute("aria-label", "恢复100%缩放"); zoomLabel.addEventListener("click", () => board?.zoomReset());
  const layoutState = el("span", "layout-state", "本浏览器布局");
  const add = (label:string, callback:()=>void, cls="dock-button") => { const button=el("button",cls,label); button.addEventListener("click",callback); toolbar.append(button); return button; };
  add("−",()=>board?.zoom(-.1),"dock-icon").setAttribute("aria-label","缩小"); toolbar.append(zoomLabel); add("＋",()=>board?.zoom(.1),"dock-icon").setAttribute("aria-label","放大");
  toolbar.append(el("span","dock-divider")); add("适应全图",()=>board?.fit()); toolbar.append(el("span","dock-divider"));
  add("保存布局",saveBoardLayout); add("恢复",restoreBoardLayout); add("重置",resetBoardLayout); toolbar.append(layoutState); panel.append(toolbar);
  const hint = el("p", "canvas-hint", "拖动排布 · Ctrl/⌘ + 滚轮缩放 · 布局仅存本浏览器"); panel.append(hint);
  try {
    board = new ResearchBoard($("graph"), project, subset, {
      select:openPreview, blank:()=>board?.select(""),
      change:(zoom,dirty)=>{ boardDirty=dirty;zoomLabel.textContent=Math.round(zoom*100)+"%"; layoutState.textContent=dirty ? "布局未保存" : "本浏览器布局"; },
      message:toast,
    }, route.page==="research"?researchHash(route):knowledgeHash(route));
    const session=canvasSessions.get(board.storageKey);
    if(session&&!board.restoreSession(session.layout,session.dirty))canvasSessions.delete(board.storageKey);
  } catch {
    board = null; panel.replaceChildren(el("p","knowledge-empty","关系画布暂不可用。资料卡片、记录阅读和下载仍可使用。")); toast("画布未载入，可切回资料卡片继续阅读。",true);
  }
}
function renderRoute(): void {
  if (!project) return;
  closePreview(false);rememberCanvas();board?.dispose(); board=null;boardDirty=false;
  const hash=location.hash || "#/overview"; const route=parseRoute(hash); activeHash=hash;
  document.title=pageLabels[route.page]+" · 空间研究";
  const activePage=route.page==="read" ? parseRoute(route.from).page : route.page;
  document.querySelectorAll<HTMLAnchorElement>("[data-page]").forEach((link)=>{const active=link.dataset.page===activePage;link.classList.toggle("active",active);if(active)link.setAttribute("aria-current","page");else link.removeAttribute("aria-current");});
  const result=renderPage(content,route,context());
  if(result?.boardContainer) createBoard(route,result);
  if(route.page==="research" && route.researchView==="demo") mountLocalDemo($("local-demo"),project.csrf_token || "",project.snapshot.sha256);
  controls();
  const saved=bookmarks.get(hash);
  requestAnimationFrame(()=>{
    const title=content.querySelector<HTMLElement>("h1");if(title)title.tabIndex=-1;
    if(saved){window.scrollTo({top:saved.scroll,behavior:"instant"});
      const restoreFocus=(attempt=0)=>{
        if(activeHash!==hash)return;
        if(saved.focus&&board?.focusElement(saved.focus))return;
        const node=saved.focus?Array.from(document.querySelectorAll<HTMLElement>("[data-focus-id]")).find((item)=>item.dataset.focusId===saved.focus):null;
        if(node){node.focus({preventScroll:true});return;}
        if(saved.focus&&board&&attempt<3){requestAnimationFrame(()=>restoreFocus(attempt+1));return;}
        title?.focus({preventScroll:true});
      };restoreFocus();}
    else{window.scrollTo({top:0,behavior:"instant"});title?.focus({preventScroll:true});}
    if(route.page==="research" && new URLSearchParams(hash.split("?")[1]).get("section")==="questions")focusQuestionForm();
  });
}
async function load(): Promise<void> {
  $("page-state").hidden=false; content.hidden=true; $("retry").hidden=true;
  $("state-title").textContent="正在读取本地证据"; $("state-message").textContent="不会启动模型、训练或新的研究行动。";
  $("page-state").classList.remove("error");
  try {
    project=await api.loadProject(); objects=objectsFor(project);
    $("project-title").textContent=project.title; $("nav-project-title").textContent=project.title;
    $("project-label").textContent=project.labels.scientific_status || "冻结的本地研究证据";
    $("page-state").hidden=true; content.hidden=false;
    if(!location.hash || parseRoute(location.hash).page==="overview" && !location.hash.startsWith("#/overview")) history.replaceState(null,"","#/overview");
    renderRoute();
  } catch(error) {
    project=null; $("page-state").classList.add("error"); $("state-title").textContent="研究证据暂未读到";
    $("state-message").textContent=error instanceof Error ? error.message : "请确认本地服务仍在运行。"; $("retry").hidden=false; controls();
  }
}
if (document.body.dataset.case === "c01") {
  void mountC01();
} else {
$("download-pdf").addEventListener("click",()=>{void download("pdf");}); $("download-zip").addEventListener("click",()=>{void download("reproduction");});
$("close-inspector").addEventListener("click",()=>closePreview()); $("inspector-backdrop").addEventListener("click",()=>closePreview());
$("read-object").addEventListener("click",()=>{
  const object=objects.find((item)=>item.id===selected);if(!object)return;
  if(object.kind==="paper"||object.kind==="questions"){closePreview(false);navigate(object.kind==="paper" ? "#/outputs" : "#/research?view=records&section=questions");}else readObject(object.id);
});
$("search").addEventListener("input",search); $("retry").addEventListener("click",()=>{void load();});
document.querySelector(".skip-link")?.addEventListener("click",(event)=>{event.preventDefault();$("main-content").focus({preventScroll:true});$("main-content").scrollIntoView({block:"start"});});
window.addEventListener("hashchange",()=>{remember();renderRoute();});
document.addEventListener("click",(event)=>{if(event.target instanceof Node && !document.querySelector(".search-wrap")?.contains(event.target)) $("search-results").hidden=true;});
document.addEventListener("keydown",(event)=>{
  const inspector=$("inspector");
  if(event.key==="Escape"){if(!inspector.hidden){event.preventDefault();closePreview();}else $("search-results").hidden=true;}
  if(!inspector.hidden && event.key==="Tab"){
    const list=Array.from(inspector.querySelectorAll<HTMLElement>("button:not(:disabled),a[href],input:not(:disabled),textarea:not(:disabled),[tabindex='0']")).filter((node)=>node.getClientRects().length>0);
    const first=list[0],last=list[list.length-1];if(!first)return;
    if(event.shiftKey && (document.activeElement===first || document.activeElement===$("inspector-title"))){event.preventDefault();last.focus();}
    else if(!event.shiftKey && document.activeElement===last){event.preventDefault();first.focus();}
  }
  const tag=(event.target as HTMLElement).tagName;
  if(event.key==="/" && inspector.hidden && !["INPUT","TEXTAREA","SELECT"].includes(tag)){event.preventDefault();$("search").focus();}
});
void load();
}
