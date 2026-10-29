import { Graph, Shape } from "@antv/x6";
import { $, el, numeric } from "./dom";

type Metric = {target: string; target_label: string; target_unit: string; alpha: number; feature_names: string[]; mae: number; baseline_mae: number; r2: number; better_than_baseline: boolean};
type Round = {id: string; title: string; method: string; feedback: string; metrics: Metric[]; limitations: string; next_action: string};
type Case = {case_id: string; source: {archive_sha256: string; doi: string}; data: {sample_count: number}; rounds: Round[]; audit: {field: string; issue: string; handling: string; origin?:string}[]; artifacts?: {figures?: {title:string; path:string; caption:string}[]}};

const labels: Record<string,string> = {overview:"项目总览",research:"研究推进",experiments:"实验中心",knowledge:"知识空间",outputs:"成果与复现"};
const section = (title:string):HTMLElement => {const n=el("section","content-section");n.append(el("h2","section-title",title));return n;};
const p = (container:HTMLElement, value:string, cls=""):void => {container.append(el("p",cls,value));};
const button = (name:string, click:()=>void, cls="action-button"):HTMLButtonElement => {const b=el("button",cls,name); b.addEventListener("click",click); return b;};
const link = (name:string, url:string, cls="text-button"):HTMLAnchorElement => {const a=el("a",cls,name);a.href=url;return a;};
const describe = (v:unknown):string => Array.isArray(v) ? v.map(String).join(" ") : typeof v === "string" ? v : JSON.stringify(v);

export async function mountC01():Promise<void> {
  let data:Case; let graph:Graph | null=null; let lastFocus:HTMLElement|null=null;
  const content=$("page-content"), state=$("page-state");
  $("project-title").textContent="C01 · 钛合金与成骨细胞"; $("nav-project-title").textContent="C01 · 钛合金与成骨细胞";
  $("project-label").textContent="医疗 × 材料 · 本地研究";
  const note=document.querySelector(".nav-note p"); if(note) note.textContent="8 个合金 · 体外数据；真实模型与平台暂未接入。";
  const search=document.querySelector<HTMLElement>(".search-wrap"); if(search) search.hidden=true;
  const status=document.querySelector<HTMLElement>(".topbar-status"); if(status) status.textContent="独立案例 · 本地分析";
  $("download-pdf").addEventListener("click",()=>{location.href="/api/c01/report.pdf";});
  $("download-zip").addEventListener("click",()=>{location.href="/api/c01/reproduction.zip";});
  const close=():void=>{$("inspector").hidden=true;$("inspector-backdrop").hidden=true;$("project-nav").inert=false;$("app-main").inert=false;lastFocus?.focus();};
  $("close-inspector").addEventListener("click",close); $("inspector-backdrop").addEventListener("click",close);
  $("read-object").hidden=true;
  document.addEventListener("keydown",(event)=>{const dialog=$("inspector");if(dialog.hidden)return;if(event.key==="Escape"){event.preventDefault();close();}else if(event.key==="Tab"){const controls=Array.from(dialog.querySelectorAll<HTMLElement>("button:not([hidden]):not(:disabled),a[href],input:not(:disabled),[tabindex='0']")).filter(n=>n.getClientRects().length>0);const first=controls[0],last=controls[controls.length-1];if(!first)return;if(event.shiftKey&&(document.activeElement===first||document.activeElement===$("inspector-title"))){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}});
  document.querySelector(".skip-link")?.addEventListener("click",event=>{event.preventDefault();$("main-content").focus();});
  const show=(title:string, paragraphs:string[]):void=>{lastFocus=document.activeElement instanceof HTMLElement?document.activeElement:null;$("inspector-title").textContent=title;$("inspector-kind").textContent="C01 · 研究记录"; const body=$("inspector-body");body.replaceChildren();paragraphs.forEach(t=>p(body,t));$("inspector").hidden=false;$("inspector-backdrop").hidden=false;$("project-nav").inert=true;$("app-main").inert=true;$("inspector-title").focus();};
  const head=(page:string, subtitle:string):void=>{const h=el("header","page-heading"),d=el("div");d.append(el("h1","",labels[page]),el("p","",subtitle));h.append(d);content.append(h);};
  const overview=():void=>{
    head("overview","材料性质与体外细胞反应：证据、分析和下一步。");
    const hero=el("section","project-hero"),copy=el("div","hero-copy"),vis=el("div","hero-archive");
    copy.append(el("span","pill sage","医疗 × 材料 · 探索性分析"),el("h2","","钛合金的材料特征与成骨细胞反应有什么联系？"),el("p","hero-description","以公开实验数据核对问题，保留模型失败和数据疑点。"));
    const actions=el("div","hero-actions");actions.append(link("查看研究推进 →","#/research","action-button primary"),link("阅读数据与来源 ↗","#/knowledge"));copy.append(actions);
    vis.append(el("span","archive-top","C01 研究档案"),el("div","archive-orbit","材料 → 细胞"),el("span","archive-foot","公开体外实验数据"));hero.append(copy,vis);content.append(hero);
    const grid=el("div","overview-grid"),a=section("当前研究"),b=section("还需要确认");
    p(a,`${data.data.sample_count} 个合金 · 两轮本地分析 · 每折留一合金`);p(a,"第二轮沿用同一数据进行敏感性比较，不是独立验证。");a.append(link("查看分析结果 →","#/experiments"));
    p(b,"合金与生物标签的权威映射、星号含义、重复结构与部分字段单位仍待原论文或作者资料确认。");b.append(link("查看核验记录 →","#/knowledge"));grid.append(a,b);content.append(grid);
    p(content,"公开数据的历史测量并非新做的细胞实验。关联、模型结果都不能推断临床疗效或因果机制。","page-boundary");
  };
  const research=():void=>{
    head("research","沿着证据、分析与判断查看本次研究。画布可拖动、缩放，点击节点查看记录。");
    const box=el("div","c01-canvas-wrap"),surface=el("div","c01-graph"),hint=el("p","c01-canvas-hint","拖动画布移动 · Ctrl + 滚轮缩放 · 点击节点查看详情");box.append(surface,hint);content.append(box);
    type Card={id:string; title:string; kind:string; body:string; details:string[]; x:number; y:number; color:string};
    const cards:Card[]=[
      {id:"question",kind:"研究问题",title:"材料与细胞反应",body:"8 种钛合金的表征与体外成骨细胞指标。",details:["研究对象是同一公开数据集中的 8 个合金。","数据来自既有体外实验，不能据此推断临床效果或因果机制。"],x:25,y:60,color:"sage"},
      {id:"audit",kind:"数据核验",title:"先确认能否比较",body:"映射、增殖率定义、单位和重复结构待核。",details:data.audit.map(a=>`${a.field}：${a.issue}；处理：${a.handling}`),x:25,y:255,color:"sage"},
      ...data.rounds.map((r,i)=>({id:r.id,kind:`分析 0${i+1}`,title:r.title,body:describe(r.feedback).split(" 数值域警告")[0],details:[`方法：${describe(r.method)}`,`反馈：${describe(r.feedback)}`,`局限：${describe(r.limitations)}`,`下一步：${describe(r.next_action)}`],x:345+i*320,y:110,color:"sand"})),
      {id:"decision",kind:"当前判断",title:"保留失败与限制",body:"两轮沿用相同 8 个样本，结果仅供探索。",details:["同一组数据上调整方案不能证明泛化提升。","若标签、单位或重复结构无法核实，应保留为描述性分析。","后续需领域专家复核和独立实验反馈。"],x:985,y:205,color:"lavender"}
    ];
    Shape.HTML.register({shape:"c01-record",effect:["data"],html:(node)=>{const c=node.getData<Card>(),card=el("div","c01-node c01-node-"+c.color);card.tabIndex=0;card.setAttribute("role","button");card.setAttribute("aria-label",c.kind+"："+c.title);card.append(el("span","overline",c.kind),el("h3","",c.title),el("p","",c.body),el("span","c01-node-link","查看记录 ↗"));card.addEventListener("click",()=>show(c.title,c.details));card.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();show(c.title,c.details);}});return card;}});
    graph=new Graph({container:surface,autoResize:true,grid:{size:24,visible:true,type:"dot",args:{color:"#cfd7d6",thickness:1.1}},background:{color:"#f4f5f7"},panning:{enabled:true,eventTypes:["leftMouseDown","mouseWheel","mouseWheelDown"]},mousewheel:{enabled:true,modifiers:["ctrl","meta"],zoomAtMousePosition:true,minScale:.3,maxScale:1.5},interacting:{nodeMovable:true}});
    cards.forEach(c=>graph!.addNode({id:c.id,shape:"c01-record",x:c.x,y:c.y,width:270,height:160,data:c}));
    [["question","audit"],["audit",data.rounds[0]?.id],[data.rounds[0]?.id,data.rounds[1]?.id],[data.rounds[1]?.id,"decision"]].forEach(([from,to])=>{if(from&&to)graph!.addEdge({source:from,target:to,connector:{name:"rounded"},attrs:{line:{stroke:"#96aa96",strokeWidth:1.5,targetMarker:{name:"classic",size:5}}}});});
    if (window.matchMedia("(max-width: 720px)").matches) { graph.zoomTo(.9); graph.translate(10,45); }
    else graph.zoomToFit({padding:30,maxScale:1});
    const toolbar=el("div","c01-tools glass"); toolbar.append(button("＋",()=>graph?.zoom(.15),"quiet-button"),button("−",()=>graph?.zoom(-.15),"quiet-button"),button("适应画布",()=>graph?.zoomToFit({padding:30,maxScale:1}),"quiet-button"));box.append(toolbar);
    const list=section("研究记录");cards.forEach(c=>list.append(button(c.kind+" · "+c.title,()=>show(c.title,c.details),"c01-record-button")));content.append(list);
  };
  const experiments=():void=>{
    head("experiments","真实计算结果；留一基线每折只使用另外 7 个合金。");
    data.rounds.forEach((r,i)=>{const s=section(`${String(i+1).padStart(2,"0")} · ${r.title}`);p(s,`逐折标准化 + Ridge · α = ${numeric(r.metrics[0]?.alpha)} · 特征：弹性模量、屈服强度、水接触角、OWRK 总表面自由能`,"muted");p(s,describe(r.feedback),"c01-feedback");const wrap=el("div","table-scroll"),table=el("table","trial-table"),thead=el("thead"),tr=el("tr");["体外终点","模型 MAE","留一均值 MAE","R²","比较"].forEach(v=>{const th=el("th","",v);th.scope="col";tr.append(th);});thead.append(tr);const body=el("tbody");r.metrics.forEach(m=>{const row=el("tr");[m.target_label,numeric(m.mae),numeric(m.baseline_mae),numeric(m.r2),m.better_than_baseline?"误差较低":"未优于基线"].forEach(v=>row.append(el("td","",v)));body.append(row);});table.append(thead,body);wrap.append(table);s.append(wrap);p(s,describe(r.limitations),"detail-note");content.append(s);});
    const charts=section("分析图表");const figures=el("div","figure-grid");(data.artifacts?.figures||[]).forEach(f=>{if(!["figures/loo_mae.svg","figures/loo_predictions.svg"].includes(f.path))return;const figure=el("figure","figure-block"),img=el("img");img.src="/api/c01/"+f.path;img.alt=f.title;img.loading="lazy";img.addEventListener("error",()=>img.replaceWith(el("p","figure-error","图表暂未载入，可查看复现附件。")));figure.append(el("h3","",f.title),img,el("figcaption","",f.caption));figures.append(figure);});if(!figures.childElementCount)p(charts,"当前运行未生成图表，可查看逐折结果表。","muted");charts.append(figures);content.append(charts);
    p(content,"两轮在同一组样本上进行，不能把第二轮结果当作独立验证；具体数值和每折预测见复现附件。","page-boundary");
  };
  const knowledge=():void=>{head("knowledge","原始资料、字段核对与仍待确认的问题。");const src=section("公开数据与论文");p(src,"数据集：Torres-Sanchez 等，Mendeley Data，Version 1，CC BY 4.0。");src.append(link("查看数据集 ↗","https://data.mendeley.com/datasets/tt7gwkpck8/1"),document.createTextNode("　"),link("查看原论文 ↗","https://doi.org/10.1016/j.bioadv.2023.213572"));p(src,"队员原始包 SHA-256："+data.source.archive_sha256,"mono");content.append(src);const audit=section("数据核验记录");p(audit,"包括人工预审问题和程序核对结果；具体来源及单元格见复现附件的 audit.csv。","detail-note");data.audit.forEach(a=>{const row=el("div","insight-line");row.append(el("strong","",(a.origin==="manual_pre_review"?"人工预审 · ":"程序核对 · ")+a.field),el("p","",a.issue+"；"+a.handling));audit.append(row);});content.append(audit);};
  const outputs=():void=>{head("outputs","本案例的分析报告与可复算材料。");const s=section("C01 研究记录");p(s,"报告和附件对应本案例的本地运行，不包含钢材项目结果。结果仅用于探索，不是临床或因果结论。");const actions=el("div","hero-actions");actions.append(link("下载 C01 报告 PDF ↓","/api/c01/report.pdf","action-button primary"),link("下载复现附件 ZIP ↓","/api/c01/reproduction.zip","action-button"));s.append(actions);content.append(s);};
  const render=():void=>{graph?.dispose();graph=null;content.replaceChildren();const requested=location.hash.replace(/^#\//,"").split("?")[0];const page=Object.hasOwn(labels,requested)?requested:"overview";document.title=labels[page]+" · C01";document.querySelectorAll<HTMLAnchorElement>("[data-page]").forEach(a=>{a.classList.toggle("active",a.dataset.page===page);if(a.dataset.page===page)a.setAttribute("aria-current","page");else a.removeAttribute("aria-current");});({overview,research,experiments,knowledge,outputs} as Record<string,()=>void>)[page]();window.scrollTo(0,0);};
  try {const response=await fetch("/api/c01",{cache:"no-store"});if(!response.ok)throw new Error("本地分析记录不可用，请检查 C01 工作区。");data=await response.json() as Case;if(data.case_id!=="C01-TNZST"||!Array.isArray(data.rounds)||!Array.isArray(data.audit))throw new Error("案例记录格式不完整。");state.hidden=true;content.hidden=false;($<HTMLButtonElement>("download-pdf")).disabled=false;($<HTMLButtonElement>("download-zip")).disabled=false;window.addEventListener("hashchange",render);render();}
  catch(e){state.classList.add("error");$("state-title").textContent="C01 记录暂未读到";$("state-message").textContent=e instanceof Error?e.message:"请检查本地服务。";$("retry").hidden=false;$("retry").addEventListener("click",()=>location.reload());}
}
