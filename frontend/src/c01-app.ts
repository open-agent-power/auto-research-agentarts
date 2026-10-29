import { Graph, Shape, Node } from "@antv/x6";
import { $, el, numeric } from "./dom";
import { mountC01Controls } from "./c01-controls";

type Metric = {target: string; target_label: string; target_unit: string; alpha: number; feature_names: string[]; mae: number; baseline_mae: number; r2: number; better_than_baseline: boolean};
type Figure = {title:string;path:string;caption:string};
type Round = {id: string; title: string; method: string; feedback: string; metrics: Metric[]; limitations: string|string[]; next_action: string; based_on_round?:string; domain_violations?:unknown[]};
type Case = {case_id: string; analysis_code_sha256?:string; source: {archive_sha256: string; doi: string}; data: {sample_count: number}; rounds: Round[]; audit: {field: string; issue: string; handling: string; origin?:string}[]; artifacts?: {figures?: Figure[]}};
type Followup={enabled:boolean;status?:string;actions?:{id:string;ordinal:number;title:string;reason:string;decision:string;evidence_ids:string[];result:{kind:string;interpretation:string;pearson_r?:number;sign_changes?:number;targets?:{target:string;sample_id:string;share_of_absolute_error:number}[];leave_one_out?:{sample_id:string;pearson_r:number}[]}}[]};
type Phase="evidence"|"experiments"|"conclusions";
type C01Card={id:string;title:string;kind:string;phase:Phase;tag:string;body:string;details:string[];refs:string[];figure?:Figure;metric?:string;metricLabel?:string};
type C01KnowledgeItem={card:C01Card;type:string;topics:string[];cover:string;label:string};
type CanvasLayout={schema_version:1;case_id:string;result_identity:string;scope:string;positions:Record<string,{x:number;y:number}>;viewport:{zoom:number;x:number;y:number}};

const targetLabel=(metric:Metric):string=>metric.target==="calcium_deposition_d21_ug_ml"?"ARS原表读数（21/28 d待核）":metric.target==="dna_cell_count_d21"?"DNA原表近似细胞数（换算待核）":metric.target==="alp_norm_d21"?"ALP/DNA归一化（原表单位待核）":metric.target_label;
const labels: Record<string,string> = {overview:"项目总览",research:"研究推进",experiments:"实验中心",knowledge:"知识空间",outputs:"成果与复现"};
const section = (title:string):HTMLElement => {const n=el("section","content-section");n.append(el("h2","section-title",title));return n;};
const p = (container:HTMLElement, value:string, cls=""):void => {container.append(el("p",cls,value));};
const button = (name:string, click:()=>void, cls="action-button"):HTMLButtonElement => {const b=el("button",cls,name); b.addEventListener("click",click); return b;};
const link = (name:string, url:string, cls="text-button"):HTMLAnchorElement => {const a=el("a",cls,name);a.href=url;return a;};
const describe = (v:unknown):string => Array.isArray(v) ? v.map(String).join(" ") : typeof v === "string" ? v : JSON.stringify(v);

const GROUPS:Record<Phase,{id:string;title:string;x:number;color:string}>={
  evidence:{id:"c01-group-evidence",title:"01  问题与资料",x:28,color:"sage"},
  experiments:{id:"c01-group-experiments",title:"02  本地分析",x:458,color:"sand"},
  conclusions:{id:"c01-group-conclusions",title:"03  判断与下一步",x:888,color:"lavender"},
};
const FIGURE_PATHS=["figures/loo_mae.svg","figures/loo_predictions.svg"];
function finite(v:unknown,limit=100000):v is number{return typeof v==="number"&&Number.isFinite(v)&&Math.abs(v)<=limit;}
function record(v:unknown):v is Record<string,unknown>{return !!v&&typeof v==="object"&&!Array.isArray(v);}
function only(v:Record<string,unknown>,keys:string[]):boolean{return Object.keys(v).every(k=>keys.includes(k));}

function cardVisual(card:C01Card):HTMLElement{
  const art=el("div","node-visual c01-node-visual");
  const fallback=()=>{
    const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");svg.setAttribute("viewBox","0 0 240 88");svg.setAttribute("aria-hidden","true");
    const drawings=card.phase==="experiments"?["M28 18v52h190M48 56V40h26v16M98 56V28h26v28M148 56V18h26v38"]:card.id==="c01-source"?["M40 12h160v63H40zM40 31h160M40 49h160M40 62h160M80 12v63M120 12v63M160 12v63"]:card.phase==="conclusions"?["M35 15h132v60H35zM52 30l5 5 10-12M83 31h63M52 52l5 5 10-12M83 53h42M190 29v36M172 47h36"]:["M28 13h132v48H80L59 76V61H28zM46 29h93M46 44h61M183 22h35v42h-35z"];
    drawings.forEach(d=>{const path=document.createElementNS("http://www.w3.org/2000/svg","path");path.setAttribute("d",d);svg.append(path);});
    art.replaceChildren(svg,el("span","node-visual-caption","类型图示 · "+card.kind));art.classList.remove("node-result-image");
  };
  if(card.figure&&FIGURE_PATHS.includes(card.figure.path)){
    art.classList.add("node-result-image");const img=el("img");img.src="/api/c01/"+card.figure.path;img.alt=card.figure.title;img.draggable=false;
    img.addEventListener("error",fallback,{once:true});art.append(img,el("span","node-visual-caption","本案例结果图 · 同8样本探索比较"));
  }else fallback();
  return art;
}

/** C01 projection on X6: stage order is layout; only declared feedback is an edge. */
class C01Board{
  readonly graph:Graph;readonly storageKey:string;private elements=new Map<string,HTMLElement>();private ids=new Set<string>();private applying=true;private selected="";private defaults!:CanvasLayout;
  constructor(container:HTMLElement,private data:Case,private cards:C01Card[],private identity:string,private scope:string,private events:{open:(id:string)=>void;change:(zoom:number,dirty:boolean)=>void;message:(text:string,error?:boolean)=>void}){
    this.storageKey="autoresearch-c01-layout:v1:"+encodeURIComponent(data.case_id)+":"+identity+":"+scope;
    Shape.HTML.register({shape:"c01-research-record-v1",effect:["data"],html:node=>this.card(node as Node)});
    this.graph=new Graph({container,autoResize:true,grid:{size:24,visible:true,type:"dot",args:{color:"#cfd7d6",thickness:1.1}},background:{color:"#f4f5f7"},scaling:{min:.35,max:1.6},panning:{enabled:true,eventTypes:["leftMouseDown","mouseWheel","mouseWheelDown"]},mousewheel:{enabled:true,modifiers:["ctrl","meta"],zoomAtMousePosition:true,minScale:.35,maxScale:1.6,factor:1.12},embedding:false,interacting:{nodeMovable:true,edgeMovable:false,edgeLabelMovable:false,magnetConnectable:false},connecting:{allowBlank:false,allowLoop:false,allowEdge:false,allowNode:false}});
    for(const [phase,group] of Object.entries(GROUPS)){
      const members=cards.filter(c=>c.phase===phase);const height=85+members.reduce((sum,c)=>sum+this.height(c)+24,0);
      const parent=this.graph.addNode({id:group.id,shape:"rect",x:group.x,y:24,width:364,height:Math.max(220,height),zIndex:0,attrs:{body:{fill:"var(--ar-group-"+group.color+"-surface)",stroke:"var(--ar-group-"+group.color+"-border)",strokeWidth:1,rx:18,ry:18},label:{text:group.title+" · "+(members.length?members.length+"项":"暂无记录"),fill:"var(--ar-group-"+group.color+"-ink)",fontSize:13,fontWeight:600,fontFamily:"Segoe UI,Microsoft YaHei,sans-serif",refX:20,refY:34,textAnchor:"start",textVerticalAnchor:"middle"}}});this.ids.add(group.id);
      let y=105;members.forEach(c=>{const node=this.graph.addNode({id:c.id,shape:"c01-research-record-v1",x:group.x+20,y,width:324,height:this.height(c),zIndex:3,data:c});parent.addChild(node);this.ids.add(c.id);y+=this.height(c)+24;});
    }
    for(const card of cards)for(const id of card.refs){if(!cards.some(c=>c.id===id))continue;this.graph.addEdge({source:{cell:id,anchor:{name:"left"}},target:{cell:card.id,anchor:{name:"left"}},zIndex:1,router:{name:"orth"},connector:{name:"rounded",args:{radius:10}},attrs:{line:{stroke:"#91a886",strokeWidth:1.4,targetMarker:{name:"classic",size:5}}},data:{relation:"declared_analysis_feedback",based_on_round:id,round_id:card.id}});}
    this.routeEdges();this.graph.zoomTo(Math.max(.68,Math.min(.92,(container.clientWidth-45)/1280)));this.graph.translate(12,18);this.defaults=this.capture();
    this.graph.on("node:click",({node})=>{if(cards.some(c=>c.id===node.id))events.open(node.id);});this.graph.on("blank:click",()=>this.select(""));
    this.graph.on("node:change:position",()=>{if(!this.applying)this.routeEdges();this.changed();});this.graph.on("scale",()=>this.changed());this.graph.on("translate",()=>this.changed());
    this.applying=false;events.change(this.graph.zoom(),false);this.restore(false);
  }
  private height(c:C01Card):number{return c.phase==="experiments"?324:286;}
  private card(node:Node):HTMLElement{
    const c=node.getData<C01Card>(),card=el("div","research-card c01-research-card");card.dataset.objectId=c.id;card.dataset.focusId=c.id;card.dataset.phase=c.phase;card.tabIndex=0;card.setAttribute("role","button");card.setAttribute("aria-pressed",String(c.id===this.selected));card.setAttribute("aria-label",c.kind+"："+c.title+"，Enter查看记录");
    const meta=el("div","node-meta");meta.append(el("span","node-category",c.kind),el("span","node-tag",c.tag));card.append(meta,cardVisual(c),el("h3","node-title",c.title));
    if(c.metric){const metric=el("div","node-metric");metric.append(document.createTextNode(c.metric),el("small","",c.metricLabel));card.append(metric);}
    card.append(el("p","node-summary",c.body));const foot=el("div","node-footer");foot.append(el("span","",c.id),el("span","node-arrow","查看记录 ↗"));card.append(foot);
    card.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();e.stopPropagation();this.events.open(c.id);}const moves:Record<string,[number,number]>={ArrowLeft:[-24,0],ArrowRight:[24,0],ArrowUp:[0,-24],ArrowDown:[0,24]};if(Object.hasOwn(moves,e.key)){e.preventDefault();e.stopPropagation();const a=node.position(),d=moves[e.key];node.position(a.x+d[0],a.y+d[1]);}});this.elements.set(c.id,card);return card;
  }
  private routeEdges():void{for(const edge of this.graph.getEdges()){const a=edge.getSourceCell(),b=edge.getTargetCell();if(!a||!b)continue;const from=a.getBBox(),to=b.getBBox(),x=Math.min(from.x,to.x)-48;edge.setVertices([{x,y:from.center.y},{x,y:to.center.y}]);}}
  private changed():void{if(!this.applying)this.events.change(this.graph.zoom(),true);}
  select(id:string):void{this.selected=id;this.elements.forEach((n,key)=>{n.classList.toggle("selected",id===key);n.setAttribute("aria-pressed",String(id===key));});}
  focusStage(phase:Phase):void{const c=this.cards.find(c=>c.phase===phase);if(c)this.focus(c.id);}
  private focus(id:string):void{const cell=this.graph.getCellById(id);if(!cell)return;const b=cell.getBBox(),zoom=Math.max(.75,this.graph.zoom());this.graph.zoomTo(zoom);this.graph.translate(this.graph.container.clientWidth/2-b.center.x*zoom,(this.graph.container.clientHeight-75)/2-b.center.y*zoom);}
  focusElement(id:string):boolean{const n=this.elements.get(id);if(!n?.isConnected)return false;const b=n.getBoundingClientRect(),f=this.graph.container.getBoundingClientRect();if(b.right<=Math.max(f.left,0)+8||b.left>=Math.min(f.right,innerWidth)-8||b.bottom<=Math.max(f.top,0)+8||b.top>=Math.min(f.bottom,innerHeight-(innerWidth<=720?88:0))-8)this.focus(id);this.select(id);n.focus({preventScroll:true});return document.activeElement===n;}
  zoom(delta:number):void{this.graph.zoomTo(Math.min(1.6,Math.max(.35,this.graph.zoom()+delta)));}
  zoomReset():void{this.graph.zoomTo(1);}
  fit():void{this.graph.zoomToFit({padding:{top:30,bottom:110,left:30,right:30},minScale:.35,maxScale:1,useCellGeometry:true});}
  capture():CanvasLayout{const positions:CanvasLayout["positions"]={};for(const n of this.graph.getNodes())positions[n.id]={...n.position()};const t=this.graph.translate();return{schema_version:1,case_id:this.data.case_id,result_identity:this.identity,scope:this.scope,positions,viewport:{zoom:this.graph.zoom(),x:t.tx,y:t.ty}};}
  private validate(v:unknown):CanvasLayout{if(!record(v)||!only(v,["schema_version","case_id","result_identity","scope","positions","viewport"])||v.schema_version!==1||v.case_id!==this.data.case_id||v.result_identity!==this.identity||v.scope!==this.scope||!record(v.positions)||!record(v.viewport))throw Error("invalid layout");const w=v.viewport;if(!only(w,["zoom","x","y"])||!finite(w.zoom,2)||w.zoom<.35||w.zoom>1.6||!finite(w.x,1000000)||!finite(w.y,1000000))throw Error("invalid viewport");for(const [id,p]of Object.entries(v.positions))if(!this.ids.has(id)||!record(p)||!only(p,["x","y"])||!finite(p.x)||!finite(p.y))throw Error("invalid position");return v as unknown as CanvasLayout;}
  restoreSession(value:unknown,dirty=false):void{try{const v=this.validate(value);this.applying=true;for(const[id,p]of Object.entries(v.positions)){const n=this.graph.getCellById(id);if(n?.isNode())n.position(p.x,p.y);}this.graph.zoomTo(v.viewport.zoom);this.graph.translate(v.viewport.x,v.viewport.y);this.routeEdges();this.applying=false;this.events.change(this.graph.zoom(),dirty);}catch{this.applying=false;this.events.message("已忽略不适用的布局，研究记录不受影响。",true);}}
  save():void{try{localStorage.setItem(this.storageKey,JSON.stringify(this.validate(this.capture())));this.events.change(this.graph.zoom(),false);this.events.message("布局已保存在本浏览器，不改变研究记录。");}catch{this.events.message("布局未能保存；记录阅读和下载仍可使用。",true);}}
  restore(notify=true):void{try{const raw=localStorage.getItem(this.storageKey);if(!raw){if(notify)this.events.message("本浏览器尚无此结果版本的布局。");return;}if(raw.length>262144)throw Error("large layout");this.restoreSession(this.validate(JSON.parse(raw)));if(notify)this.events.message("已恢复本浏览器布局。");}catch{this.events.message("已忽略损坏的浏览器布局，记录仍可查看。",true);}}
  reset():void{this.restoreSession(this.defaults);try{localStorage.removeItem(this.storageKey);this.events.message("已重置本浏览器布局。");}catch{this.events.message("视图已重置，但旧保存布局未能清除。",true);}}
  dispose():void{this.graph.dispose();}
}

export async function mountC01():Promise<void> {
  let data:Case;let followup:Followup|null=null;let board:C01Board|null=null;let lastFocus:HTMLElement|null=null;let identity="";let activeHash="";let selected="";let dirty=false;let cards:C01Card[]=[];
  const sessions=new Map<string,{layout:CanvasLayout;dirty:boolean}>(),bookmarks=new Map<string,{scroll:number;focus:string}>(),origins=new Map<string,string>();
  const content=$("page-content"), state=$("page-state");
  $("project-title").textContent="C01 · 钛合金与体外细胞"; $("nav-project-title").textContent="C01 · 钛合金与体外细胞";
  $("project-label").textContent="医疗 × 材料 · 本地研究";
  const note=document.querySelector(".nav-note p"); if(note) note.textContent="8 个合金 · 体外数据；真实模型与平台暂未接入。";
  const search=document.querySelector<HTMLElement>(".search-wrap"); if(search) search.hidden=true;
  const status=document.querySelector<HTMLElement>(".topbar-status"); if(status) status.textContent="独立案例 · 本地分析";
  $("download-pdf").addEventListener("click",()=>{location.href="/api/c01/report.pdf";});
  $("download-zip").addEventListener("click",()=>{location.href="/api/c01/reproduction.zip";});
  const message=(text:string,error=false):void=>{const n=$("toast");n.textContent=text;n.classList.toggle("error",error);n.hidden=false;window.setTimeout(()=>{if(n.textContent===text)n.hidden=true;},error?8000:5000);};
  const remember=(focus=""):void=>{if(activeHash)bookmarks.set(activeHash,{scroll:scrollY,focus:focus||(document.activeElement as HTMLElement)?.closest<HTMLElement>("[data-focus-id]")?.dataset.focusId||bookmarks.get(activeHash)?.focus||""});};
  const navigate=(hash:string):void=>{if(hash!==location.hash){remember();location.hash=hash;}};
  const cache=():void=>{if(board)sessions.set(board.storageKey,{layout:board.capture(),dirty});};
  const close=(restoreFocus=true):void=>{$("inspector").hidden=true;$("inspector-backdrop").hidden=true;$("project-nav").inert=false;$("app-main").inert=false;document.body.classList.remove("has-inspector");if(restoreFocus&&lastFocus?.isConnected)lastFocus.focus({preventScroll:true});lastFocus=null;};
  $("close-inspector").addEventListener("click",()=>close()); $("inspector-backdrop").addEventListener("click",()=>close());
  $("read-object").hidden=true;
  document.addEventListener("keydown",(event)=>{const dialog=$("inspector");if(dialog.hidden)return;if(event.key==="Escape"){event.preventDefault();close();}else if(event.key==="Tab"){const controls=Array.from(dialog.querySelectorAll<HTMLElement>("button:not([hidden]):not(:disabled),a[href],input:not(:disabled),[tabindex='0']")).filter(n=>n.getClientRects().length>0);const first=controls[0],last=controls[controls.length-1];if(!first)return;if(event.shiftKey&&(document.activeElement===first||document.activeElement===$("inspector-title"))){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}});
  document.querySelector(".skip-link")?.addEventListener("click",event=>{event.preventDefault();$("main-content").focus();});
  const isSourceRecord=(id:string):boolean=>["c01-source","c01-audit","c01-paper"].includes(id);
  const show=(title:string, paragraphs:string[],id=""):void=>{if($("inspector").hidden)lastFocus=document.activeElement instanceof HTMLElement?document.activeElement:null;selected=id;board?.select(id);$("inspector-title").textContent=title;$("inspector-kind").textContent="C01 · 记录预览"; const body=$("inspector-body");body.replaceChildren();paragraphs.forEach(t=>p(body,t));const read=$<HTMLButtonElement>("read-object");read.hidden=!id;read.textContent=isSourceRecord(id)?"阅读资料记录 ↗":"完整记录 ↗";$("inspector").hidden=false;$("inspector-backdrop").hidden=false;$("project-nav").inert=true;$("app-main").inert=true;document.body.classList.add("has-inspector");$("inspector-title").focus({preventScroll:true});document.querySelector(".inspector-scroll")?.scrollTo(0,0);};
  const open=(id:string):void=>{const card=cards.find(c=>c.id===id)||knowledgeItems().find(item=>item.card.id===id)?.card;if(card)show(card.title,card.details,id);};
  $("read-object").addEventListener("click",()=>{if(!selected)return;const id=selected;close(false);remember(id);const from=activeHash.startsWith("#/read/")?new URLSearchParams(activeHash.split("?")[1]).get("from")||"#/research":activeHash||"#/research";const hash="#/read/"+encodeURIComponent(id)+"?from="+encodeURIComponent(from);origins.set(hash,from);navigate(hash);});
  const allCards=():C01Card[]=>{
    const fig=data.artifacts?.figures?.find(f=>f.path==="figures/loo_mae.svg");
    const base:C01Card[]=[
      {id:"c01-question",kind:"研究问题",phase:"evidence",tag:"当前问题",title:"钛合金材料特征与体外细胞终点",body:`同一公开数据集的${data.data.sample_count}个合金，核对材料表征与体外数值。`,details:["研究问题：材料性质与体外细胞终点在这8个合金中如何对应？","样本为合金聚合行；SD和不同日期没有扩成独立样本。","这是既有体外实验数据的本地复算，不是新做的细胞实验，不支持临床或因果结论。"],refs:[]},
      {id:"c01-source",kind:"数据来源",phase:"evidence",tag:"原始包已归档",title:"C01 原始资料与分析输入",body:"主工作簿中的材料特征与四项体外终点；逐折仅使用7个合金训练。",details:["当前只展示本地资料记录，不是原论文全文。",`来源DOI：${data.source.doi}`,`原始包SHA-256：${data.source.archive_sha256}`,"分析输入为主表确认的材料字段，生物终点只作为目标，不作为预测特征。","原包、工作簿和逐折数据见复现附件；字段单位与映射限制须同时核对。"],refs:[]},
      {id:"c01-audit",kind:"字段审计",phase:"evidence",tag:data.audit.length+"项记录",title:"人工预审与程序核对",body:"保留增殖率定义、删失值、单位与标签映射疑点。",details:data.audit.map(a=>`${a.origin==="manual_pre_review"?"人工预审":"程序核对"} · ${a.field}：${a.issue}；${a.handling}`),refs:[]},
    ];
    data.rounds.forEach((r,index)=>{const better=r.metrics.filter(m=>m.better_than_baseline).length;base.push({id:r.id,kind:"分析 "+String(index+1).padStart(2,"0"),phase:"experiments",tag:r.based_on_round?"基于前轮反馈":"固定初始协议",title:r.title,body:describe(r.feedback).split(" 数值域警告")[0],details:[`方法：${describe(r.method)}`,`配置：α=${numeric(r.metrics[0]?.alpha)}；${r.metrics[0]?.feature_names?.join("、")||"见指标记录"}`,`实际反馈：${describe(r.feedback)}`,...r.metrics.map(m=>`${targetLabel(m)}（字段 ${m.target}）：MAE ${numeric(m.mae)}；逐折均值基线 ${numeric(m.baseline_mae)}；R² ${numeric(m.r2)}。`),`局限：${describe(r.limitations)}`,`后续建议（未执行）：${describe(r.next_action)}`],refs:r.based_on_round&&data.rounds.some(other=>other.id===r.based_on_round)?[r.based_on_round]:[],figure:fig,metric:better+" / "+r.metrics.length,metricLabel:"MAE较低目标 · 探索性"});});
    for(const action of followup?.actions||[]){
      const r=action.result;const details=[`行动依据：${action.reason}`,`实际结果：${r.interpretation}`];let summary="检查逐折误差是否集中于少数合金。";
      if(r.kind==="held_out_error_influence")for(const v of r.targets||[])details.push(`${v.target}：${v.sample_id} 占总绝对误差 ${numeric(v.share_of_absolute_error*100,4)}%。`);
      if(r.kind==="pair_correlation_influence"){summary=`全部合金 r=${numeric(r.pearson_r,4)}，逐一剔除后有 ${r.sign_changes||0} 次方向改变。`;details.push(summary);for(const v of r.leave_one_out||[])details.push(`剔除 ${v.sample_id}：r=${numeric(v.pearson_r,4)}。`);}
      details.push(`判断：${action.decision}`,"数据已见；这是本地脚本结果，不是独立验证或新增细胞实验。");
      base.push({id:action.id,kind:"后续行动 0"+action.ordinal,phase:"experiments",tag:"本地脚本 · 已执行",title:action.title,body:summary,details,refs:action.evidence_ids,metric:action.ordinal===2?numeric(r.pearson_r,4):undefined,metricLabel:"全部样本相关系数 · 探索"});
    }
    const last=data.rounds[data.rounds.length-1],lastAction=followup?.actions?.at(-1);
    base.push({id:"c01-feedback",kind:"研究判断",phase:"conclusions",tag:"探索性结果",title:"比较结果与适用范围",body:"分析误差的变化来自同一8样本重复使用，不能当作独立验证。",details:[...data.rounds.map(r=>`${r.id}：${describe(r.feedback)}`),"不据此指定最佳材料、确认机制或宣称临床效果。"],refs:[],figure:fig},
      {id:"c01-limitations",kind:"研究限制",phase:"conclusions",tag:"未独立验证",title:"标签、重复与数值域限制",body:"部分单位和实验重复结构待核；越界预测未裁剪，不解释为有效生物预测。",details:[...new Set(data.rounds.flatMap(r=>Array.isArray(r.limitations)?r.limitations:[r.limitations]))],refs:[]},
      {id:"c01-next",kind:"待处理问题",phase:"conclusions",tag:lastAction?"等待复核":"建议 · 未执行",title:"补充核验与独立样本",body:lastAction?.decision||describe(last?.next_action||"尚无后续记录。"),details:[lastAction?.decision||describe(last?.next_action||"尚无后续记录。"),"需要原论文方法、标签与重复结构的核对，以及独立数据或专业实验反馈。","此节点是待处理建议；查看和移动节点不会运行研究。"],refs:lastAction?[lastAction.id]:[]});return base;
  };
  const head=(page:string, subtitle:string):void=>{const h=el("header","page-heading"),d=el("div");d.append(el("h1","",labels[page]),el("p","",subtitle));h.append(d);content.append(h);};
  const overview=():void=>{
    head("overview","材料性质与体外细胞反应：证据、分析和下一步。");
    const hero=el("section","project-hero"),copy=el("div","hero-copy"),vis=el("div","hero-archive");
    copy.append(el("span","pill sage","医疗 × 材料 · 探索性分析"),el("h2","","钛合金材料特征与MC3T3-E1体外终点如何对应？"),el("p","hero-description","以公开实验数据核对问题，保留模型失败和数据疑点。"));
    const actions=el("div","hero-actions");actions.append(link("查看研究推进 →","#/research","action-button primary"),link("阅读数据与来源 ↗","#/knowledge"));copy.append(actions);
    vis.append(el("span","archive-top","C01 研究档案"),el("div","archive-orbit","材料 → 细胞"),el("span","archive-foot","公开体外实验数据"));hero.append(copy,vis);content.append(hero);
    const grid=el("div","overview-grid"),a=section("当前研究"),b=section("还需要确认");
    p(a,`${data.data.sample_count} 个合金 · 两轮既有分析 · ${followup?.actions?.length||0} 项后续检查`);p(a,"后续检查沿用同一数据，不是独立验证。");a.append(link("查看研究推进 →","#/research"));
    p(b,"合金与生物标签的权威映射、星号含义、重复结构与部分字段单位仍待原论文或作者资料确认。");b.append(link("查看核验记录 →","#/knowledge"));grid.append(a,b);content.append(grid);
    p(content,"公开数据的历史测量并非新做的细胞实验。关联、模型结果都不能推断临床疗效或因果机制。","page-boundary");
  };
  const research=():void=>{
    head("research","问题与资料、本地分析、判断与下一步。阶段顺序用于浏览，线条仅表示记录中的前轮反馈依赖。");
    const params=new URLSearchParams(location.hash.split("?")[1]),records=params.get("view")==="records",all=params.get("scope")==="all";
    const update=(key:string,value:string)=>{const current=new URLSearchParams(location.hash.split("?")[1]);if(value)current.set(key,value);else current.delete(key);navigate("#/research"+(current.size?"?"+current.toString():""));};
    const bar=el("div","research-viewbar glass"),views=el("div","segmented");views.setAttribute("aria-label","C01研究推进视图");
    for(const[value,label]of [["","流程画布"],["records","过程记录"]]){const active=records===(value==="records"),b=button(label,()=>update("view",value),active?"active":"");b.dataset.c01View=value||"flow";b.setAttribute("aria-pressed",String(active));views.append(b);}
    bar.append(views,el("span","c01-view-note","已有分析记录 · 本地可复算"));content.append(bar);
    if(records){
      const list=section("研究记录");list.classList.add("c01-process-records");cards.forEach(c=>{const row=button("",()=>open(c.id),"c01-record-row");row.dataset.focusId=c.id;row.append(el("span","overline",c.kind+" · "+c.tag),el("strong","",c.title),el("p","",c.body),el("span","text-button","查看记录 ↗"));list.append(row);});content.append(list);
    }else{
      const settings=el("div","research-flow-controls"),scopes=el("div","segmented");for(const[value,label]of [["","当前流程"],["all","全景展开"]]){const active=all===(value==="all"),b=button(label,()=>update("scope",value),active?"active":"");b.dataset.c01Scope=value||"current";b.setAttribute("aria-pressed",String(active));scopes.append(b);}settings.append(scopes,el("p","","连线只表示记录中的反馈与证据引用，不推断因果或新增实验。"));content.append(settings);
      const chosen=all?cards:cards.filter(c=>!["c01-audit","c01-limitations"].includes(c.id));
      const box=el("div","relation-board research-board c01-workflow-board has-flow-header"),surface=el("div","graph-surface");surface.id="c01-graph";surface.tabIndex=0;surface.setAttribute("role","region");surface.setAttribute("aria-label","C01研究流程画布，空白拖动平移，Ctrl或⌘加滚轮缩放，Enter查看节点，方向键移动节点。");box.append(surface);
      const flow=el("div","workflow-strip glass");for(const[phase,number,title]of [["evidence","01","问题与资料"],["experiments","02","本地分析"],["conclusions","03","判断与下一步"]] as const){if(flow.childElementCount)flow.append(el("span","workflow-arrow","→"));const b=button("",()=>board?.focusStage(phase),"workflow-step");b.dataset.c01Stage=phase;b.append(el("small","",number),el("span","",title));flow.append(b);}box.append(flow);
      const dock=el("div","canvas-dock glass"),zoom=button("100%",()=>board?.zoomReset(),"zoom-value"),layout=el("span","layout-state","本浏览器布局");zoom.setAttribute("aria-label","恢复100%缩放");
      const add=(title:string,action:()=>void,key:string,cls="dock-button")=>{const b=button(title,action,cls);b.dataset.c01Canvas=key;dock.append(b);return b;};
      add("−",()=>board?.zoom(-.1),"zoom-out","dock-icon").setAttribute("aria-label","缩小");dock.append(zoom);add("＋",()=>board?.zoom(.1),"zoom-in","dock-icon").setAttribute("aria-label","放大");dock.append(el("span","dock-divider"));add("适应全图",()=>board?.fit(),"fit");dock.append(el("span","dock-divider"));
      add("保存布局",()=>{board?.save();cache();},"save");add("恢复",()=>{board?.restore();cache();},"restore");add("重置",()=>{board?.reset();cache();},"reset");dock.append(layout);box.append(dock,el("p","canvas-hint","拖动排布 · Ctrl/⌘ + 滚轮缩放 · 布局仅存本浏览器"));content.append(box);
      try{board=new C01Board(surface,data,chosen,identity,all?"all":"current",{open,change:(z,changed)=>{dirty=changed;zoom.textContent=Math.round(z*100)+"%";layout.textContent=changed?"布局未保存":"本浏览器布局";},message});const saved=sessions.get(board.storageKey);if(saved)board.restoreSession(saved.layout,saved.dirty);}catch{board=null;box.replaceChildren(el("p","knowledge-empty","画布暂未载入，可切到过程记录继续阅读。"));}
    }
    const controls=el("section","c01-controls-host");controls.id="c01-controls";content.append(controls);mountC01Controls(controls);
  };
  const reader=():void=>{
    const [path,query]=location.hash.split("?");let id="";try{id=decodeURIComponent(path.split("/")[2]||"");}catch{}const card=cards.find(c=>c.id===id)||knowledgeItems().find(item=>item.card.id===id)?.card;const params=new URLSearchParams(query);const from=params.get("from")||"#/research";
    const top=el("div","reader-top");top.append(button("← 返回原位置",()=>{if(origins.has(location.hash))history.back();else navigate(/^#\/(research|overview|experiments|knowledge|outputs)(\?|$)/.test(from)?from:"#/research");},"quiet-button"),el("span","muted",isSourceRecord(id)?"资料记录阅读":"完整记录阅读"));content.append(top);
    if(!card){p(content,"当前案例没有该记录。","knowledge-empty");return;}
    const layout=el("div","document-layout reader-layout"),toc=el("aside","document-toc"),article=el("article","reader-document solid-panel");toc.setAttribute("aria-label","C01记录阅读目录");toc.append(el("span","overline","阅读目录"));article.append(el("div","document-label",card.kind+" / "+card.id),el("h1","document-title",card.title));
    const body=el("div","full-record");body.id="c01-full-record";card.details.forEach(text=>p(body,text));article.append(body);toc.append(button("记录内容",()=>body.scrollIntoView({block:"start"}),"toc-item"));
    if(card.figure&&FIGURE_PATHS.includes(card.figure.path)){const fig=el("figure","figure-block");fig.id="c01-record-figure";const image=el("img");image.src="/api/c01/"+card.figure.path;image.alt=card.figure.title;image.addEventListener("error",()=>image.replaceWith(el("p","figure-error","图表暂未载入，可查看复现附件。")),{once:true});fig.append(el("h3","",card.figure.title),image,el("figcaption","",card.figure.caption+" 原图术语来自冻结记录，ARS日期与指标解释仍需人工核验。"));article.append(fig);toc.append(button("本案例结果图",()=>fig.scrollIntoView({block:"start"}),"toc-item"));}
    if(card.id==="c01-source")article.append(link("打开原始数据来源 ↗","https://data.mendeley.com/datasets/tt7gwkpck8/1"));
    if(card.id==="c01-paper")article.append(link("访问原论文 ↗","https://doi.org/10.1016/j.bioadv.2023.213572"));
    if(card.refs.length){const refs=section("前轮反馈依据");card.refs.forEach(ref=>{const item=cards.find(c=>c.id===ref);if(item)refs.append(button(item.id+" · "+item.title,()=>open(item.id),"text-button"));});article.append(refs);}
    const version=el("div","toc-version");version.append(el("span","overline","结果与来源身份"),el("code","mono",identity.slice(0,16)+"…"));toc.append(version);layout.append(toc,article);content.append(layout);
  };
  const reviewNotice=():HTMLElement=>{
    const block=section("人工核验补充");block.classList.add("c01-review-notice");
    p(block,"依据原论文 §2.4–2.5 及图4的后续人工核验；不是程序自主发现。原快照与字段名未改写。","detail-note");
    const list=el("ul");[
      "细胞为MC3T3-E1小鼠前成骨细胞。每合金/时间点3次测量，尚未证实为独立批次，不能扩为独立样本。",
      "ALP按DNA归一化；DNA图4D为ng/mL，与工作簿近似细胞数的换算未明。",
      "ARS为染色读数，并非直接元素钙测量；图4F的28 d与正文、图注及表内21 d冲突，日期待核。",
      "论文粗糙度单位为Ra nm、RSm μm，工作簿为mm；本次没有使用这些存疑特征。",
    ].forEach(text=>list.append(el("li","",text)));block.append(list);return block;
  };
  const experiments=():void=>{
    head("experiments","真实计算结果；留一基线每折只使用另外 7 个合金。");content.append(reviewNotice());
    data.rounds.forEach((r,i)=>{const s=section(`${String(i+1).padStart(2,"0")} · ${r.title}`);p(s,`逐折标准化 + Ridge · α = ${numeric(r.metrics[0]?.alpha)} · 特征：弹性模量、屈服强度、水接触角、OWRK 总表面自由能`,"muted");p(s,describe(r.feedback),"c01-feedback");const wrap=el("div","table-scroll"),table=el("table","trial-table"),thead=el("thead"),tr=el("tr");["体外终点","模型 MAE","留一均值 MAE","R²","比较"].forEach(v=>{const th=el("th","",v);th.scope="col";tr.append(th);});thead.append(tr);const body=el("tbody");r.metrics.forEach(m=>{const row=el("tr");[targetLabel(m),numeric(m.mae),numeric(m.baseline_mae),numeric(m.r2),m.better_than_baseline?"误差较低":"未优于基线"].forEach(v=>row.append(el("td","",v)));body.append(row);});table.append(thead,body);wrap.append(table);s.append(wrap);p(s,describe(r.limitations),"detail-note");content.append(s);});
    const charts=section("分析图表");const figures=el("div","figure-grid");(data.artifacts?.figures||[]).forEach(f=>{if(!["figures/loo_mae.svg","figures/loo_predictions.svg"].includes(f.path))return;const figure=el("figure","figure-block"),img=el("img");img.src="/api/c01/"+f.path;img.alt=f.title;img.loading="lazy";img.addEventListener("error",()=>img.replaceWith(el("p","figure-error","图表暂未载入，可查看复现附件。")));figure.append(el("h3","",f.title),img,el("figcaption","",f.caption+" 原图术语保留自快照，ARS日期与指标解释须结合人工核验补充阅读。"));figures.append(figure);});if(!figures.childElementCount)p(charts,"当前运行未生成图表，可查看逐折结果表。","muted");charts.append(figures);content.append(charts);
    p(content,"两轮在同一组样本上进行，不能把第二轮结果当作独立验证；具体数值和每折预测见复现附件。","page-boundary");
  };
  // A reading projection of existing records. These items do not create canvas nodes or research memory.
  const knowledgeItems=():C01KnowledgeItem[]=>{
    const items:C01KnowledgeItem[]=[];
    const add=(id:string,type:string,topics:string[],cover:string,label:string):void=>{const card=cards.find(c=>c.id===id);if(card)items.push({card,type,topics,cover,label});};
    add("c01-source","数据集",["材料表征","体外细胞"],"sage","公开数据 · 原始包已归档");
    items.push({type:"文献与证据",topics:["材料表征","体外细胞","数据核验"],cover:"lavender",label:"原论文 · 本地资料记录",card:{id:"c01-paper",kind:"论文来源",phase:"evidence",tag:"原文见来源",title:"钛合金与体外细胞研究 · 原论文",body:"C01公开数据对应的论文来源；本地保留摘记、来源信息和人工核验提示。",details:["当前快照仅有摘记和来源信息，原文请访问原始来源。","论文DOI：10.1016/j.bioadv.2023.213572。","对应数据：Torres-Sanchez 等，Mendeley Data，Version 1，数据DOI 10.17632/tt7gwkpck8.1，数据许可 CC BY 4.0。","后续人工核验：细胞为MC3T3-E1小鼠前成骨细胞；每合金/时间点3次测量，尚未证实为独立批次。","ALP按DNA归一化；DNA图4D的ng/mL与工作簿近似细胞数换算未明。","ARS是染色读数，不是直接元素钙测量；图4F的28 d与正文、图注及表内21 d冲突，日期待核。","粗糙度论文Ra nm、RSm μm与工作簿mm冲突；本次未使用这些存疑特征。","以上方法核验由人工提供，不是程序自主发现；原始快照与字段名未修改。"],refs:[]}});
    add("c01-audit","文献与证据",["数据核验"],"sage","人工预审与程序核对 · 保留来源区别");
    for(const card of cards.filter(c=>c.phase==="experiments"))items.push({card,type:"方法与工具",topics:["统计与评价"],cover:"sand",label:card.kind+" · 本地已执行记录"});
    add("c01-feedback","文献与证据",["统计与评价","研究边界"],"lavender","研究判断 · 非条件记忆");
    add("c01-limitations","文献与证据",["数据核验","研究边界"],"lavender","研究限制 · 未独立验证");
    return items;
  };
  const knowledge=():void=>{
    head("knowledge","按类型与主题浏览资料、分析方法和研究判断。");
    const types=["全部","文献与证据","数据集","方法与工具","研究记忆"],topics=["材料表征","体外细胞","统计与评价","数据核验","研究边界"];
    const readFilters=():{type:string;topics:string[]}=>{const params=new URLSearchParams(location.hash.split("?")[1]);const type=params.get("type")||"全部";return{type:types.includes(type)?type:"全部",topics:topics.filter(topic=>(params.get("topics")||"").split(",").includes(topic))};};
    const update=(type?:string,topic?:string,clear=false):void=>{const current=readFilters();const next=clear?{type:"全部",topics:[]}:current;if(type)next.type=type;if(topic)next.topics=next.topics.includes(topic)?next.topics.filter(t=>t!==topic):[...next.topics,topic];const params=new URLSearchParams();if(next.type!=="全部")params.set("type",next.type);if(next.topics.length)params.set("topics",topics.filter(t=>next.topics.includes(t)).join(","));navigate("#/knowledge"+(params.size?"?"+params.toString():""));};
    const filters=readFilters(),items=knowledgeItems(),selectedItems=items.filter(item=>(filters.type==="全部"||filters.type===item.type)&&(!filters.topics.length||filters.topics.some(topic=>item.topics.includes(topic))));
    const toolbar=el("div","knowledge-toolbar glass c01-knowledge-toolbar"),tabs=el("div","type-tabs");tabs.setAttribute("aria-label","资料类型");
    for(const type of types){const active=filters.type===type,b=button(type+" "+(type==="全部"?items.length:items.filter(item=>item.type===type).length),()=>update(type),"type-tab"+(active?" active":""));b.dataset.c01Type=type;b.dataset.focusId="knowledge-type-"+type;b.setAttribute("aria-pressed",String(active));tabs.append(b);}toolbar.append(tabs);
    const panel=el("div","topic-panel"),semantics=el("div","topic-semantics");semantics.append(el("span","","研究主题"),el("small","","多选主题任一匹配，再与资料类型同时满足"));panel.append(semantics);
    const chips=el("div","topic-chips");chips.setAttribute("role","group");chips.setAttribute("aria-label","研究主题，可多选");for(const topic of topics){const active=filters.topics.includes(topic),b=button(topic,()=>update(undefined,topic),"topic-chip"+(active?" active":""));b.dataset.c01Topic=topic;b.dataset.focusId="knowledge-topic-"+topic;b.setAttribute("aria-pressed",String(active));chips.append(b);}const clear=button("清除筛选",()=>update(undefined,undefined,true),"topic-clear");clear.dataset.c01Clear="";clear.disabled=filters.type==="全部"&&!filters.topics.length;chips.append(clear);panel.append(chips);
    const bottom=el("div","knowledge-toolbar-bottom");bottom.append(panel);toolbar.append(bottom);const count=el("p","filter-summary",selectedItems.length+" / "+items.length+" 条记录 · "+filters.type+(filters.topics.length?" · "+filters.topics.join(" / "):""));count.setAttribute("role","status");toolbar.append(count);content.append(toolbar);
    const read=(id:string):void=>{remember(id);const from=activeHash,hash="#/read/"+encodeURIComponent(id)+"?from="+encodeURIComponent(from);origins.set(hash,from);navigate(hash);};
    const cover=(item:C01KnowledgeItem):HTMLElement=>{const visual=el("div","type-cover "+item.cover);visual.setAttribute("aria-hidden","true");const lines=el("span","cover-lines");lines.append(el("i"),el("i"),el("i"));visual.append(el("span","cover-label","类型图示 · "+item.type),el("span","cover-symbol",item.type==="数据集"?"▦":item.type==="方法与工具"?"ƒ":item.card.id==="c01-paper"?"▤":"◇"),lines,el("span","cover-id",item.card.id));return visual;};
    if(!selectedItems.length){const empty=el("div","knowledge-empty");empty.append(el("h2","",filters.type==="研究记忆"?"尚无经过复核的研究记忆":"暂无匹配资料"),el("p","",filters.type==="研究记忆"?"研究判断和方法核验保留为原始记录，没有升级为条件记忆。":"可调整资料类型或取消部分主题。"),button("清除筛选",()=>update(undefined,undefined,true),"quiet-button"));content.append(empty);}
    else{const grid=el("div","knowledge-grid c01-knowledge-grid");for(const item of selectedItems){const c=item.card,card=el("article","knowledge-card");card.id="item-"+c.id;card.dataset.c01KnowledgeId=c.id;
      if(c.figure&&FIGURE_PATHS.includes(c.figure.path)){const visual=el("div","knowledge-figure"),img=el("img");img.src="/api/c01/"+c.figure.path;img.alt=c.figure.title;img.loading="lazy";img.addEventListener("error",()=>visual.replaceWith(cover(item)),{once:true});visual.append(img,el("span","","本案例结果图 · 同8样本探索比较"));card.append(visual);}else card.append(cover(item));
      const body=el("div","knowledge-card-body");body.append(el("span","overline",item.label),el("h2","",c.title),el("p","card-summary",c.body));const tags=el("div","topic-tags");item.topics.forEach(topic=>tags.append(el("span","",topic)));body.append(tags);const actions=el("div","card-actions"),peek=button("预览摘要",()=>open(c.id),"quiet-button"),full=button(isSourceRecord(c.id)?"阅读资料记录 ↗":"完整记录 ↗",()=>read(c.id),"text-button");peek.dataset.focusId=c.id;peek.dataset.c01Preview=c.id;full.dataset.focusId=c.id;full.dataset.c01Read=c.id;actions.append(peek,full);body.append(actions);card.append(body);grid.append(card);
    }content.append(grid);}
    p(content,"卡片按现有记录整理；类型图示不是论文插图。结果图来自本地复算，不代表独立验证。","page-boundary");
    const sources=section("原始来源");sources.classList.add("c01-knowledge-sources");sources.append(link("数据集 · Mendeley Data ↗","https://data.mendeley.com/datasets/tt7gwkpck8/1"),link("原论文 · DOI ↗","https://doi.org/10.1016/j.bioadv.2023.213572"));p(sources,"数据集版本1 · CC BY 4.0；数据许可不代表论文插图可任意复用。","detail-note");p(sources,"原始包 SHA-256："+data.source.archive_sha256,"mono");content.append(sources,reviewNotice());
  };
  const outputs=():void=>{head("outputs","本案例的分析报告与可复算材料。");content.append(reviewNotice());const s=section("C01 原研究记录");p(s,"原案例报告包含后续论文方法核验提示，原附件对应原始运行快照；续研行动单独记录。");const actions=el("div","hero-actions");actions.append(link("下载 C01 报告 PDF ↓","/api/c01/report.pdf","action-button primary"),link("下载复现附件 ZIP ↓","/api/c01/reproduction.zip","action-button"));s.append(actions);content.append(s);if(followup?.actions?.length){const more=section("后续研究记录");p(more,"后续分析沿用既有公开数据，与原报告关联但分开保存；不能作为独立验证。");const links=el("div","hero-actions");links.append(link("下载后续报告 PDF ↓","/api/c01/continuation/report.pdf","action-button primary"),link("下载后续复现附件 ↓","/api/c01/continuation/reproduction.zip","action-button"));more.append(links);content.append(more);}};
  const render=():void=>{
    remember();close(false);cache();board?.dispose();board=null;dirty=false;content.replaceChildren();activeHash=location.hash||"#/overview";
    const requested=location.hash.replace(/^#\//,"").split("?")[0],isReader=requested.startsWith("read/");const fromPage=(new URLSearchParams(location.hash.split("?")[1]).get("from")||"#/research").replace(/^#\//,"").split("?")[0];const page=isReader?(Object.hasOwn(labels,fromPage)?fromPage:"research"):Object.hasOwn(labels,requested)?requested:"overview";
    document.title=(isReader?"记录阅读":labels[page])+" · C01";document.querySelectorAll<HTMLAnchorElement>("[data-page]").forEach(a=>{a.classList.toggle("active",a.dataset.page===page);if(a.dataset.page===page)a.setAttribute("aria-current","page");else a.removeAttribute("aria-current");});
    if(isReader)reader();else({overview,research,experiments,knowledge,outputs} as Record<string,()=>void>)[page]();
    const saved=bookmarks.get(activeHash),expected=activeHash;requestAnimationFrame(()=>{if(activeHash!==expected)return;window.scrollTo({top:saved?.scroll||0,behavior:"instant"});const title=content.querySelector<HTMLElement>("h1");if(title)title.tabIndex=-1;const focus=(attempt=0):void=>{if(activeHash!==expected)return;if(saved?.focus&&board?.focusElement(saved.focus))return;const node=saved?.focus?Array.from(content.querySelectorAll<HTMLElement>("[data-focus-id]")).find(n=>n.dataset.focusId===saved.focus):null;if(node){node.focus({preventScroll:true});return;}if(saved?.focus&&board&&attempt<3){requestAnimationFrame(()=>focus(attempt+1));return;}title?.focus({preventScroll:true});};focus();});
  };
  try {const response=await fetch("/api/c01",{cache:"no-store"});if(!response.ok)throw new Error("本地分析记录不可用，请检查 C01 工作区。");data=await response.json() as Case;if(data.case_id!=="C01-TNZST"||!Array.isArray(data.rounds)||!Array.isArray(data.audit))throw new Error("案例记录格式不完整。");try{const extra=await fetch("/api/c01/continuation",{cache:"no-store"});if(extra.ok)followup=await extra.json() as Followup;}catch{/* frozen parent remains readable */}const bytes=new TextEncoder().encode(JSON.stringify({case_id:data.case_id,source:data.source.archive_sha256,code:data.analysis_code_sha256,rounds:data.rounds,audit:data.audit}));identity=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes))).map(v=>v.toString(16).padStart(2,"0")).join("");cards=allCards();state.hidden=true;content.hidden=false;($<HTMLButtonElement>("download-pdf")).disabled=false;($<HTMLButtonElement>("download-zip")).disabled=false;window.addEventListener("hashchange",render);window.addEventListener("c01-continuation-changed",(event)=>{followup=(event as CustomEvent<Followup>).detail;cards=allCards();if(location.hash.startsWith("#/research"))render();});render();}
  catch(e){state.classList.add("error");$("state-title").textContent="C01 记录暂未读到";$("state-message").textContent=e instanceof Error?e.message:"请检查本地服务。";$("retry").hidden=false;$("retry").addEventListener("click",()=>location.reload());}
}
