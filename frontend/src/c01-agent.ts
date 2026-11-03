/** Reading projections of completed external-Agent records; never dispatches research. */
import { el, numeric, safeUrl } from "./dom";
import type { Case, C01Card, C01KnowledgeItem, Figure, Round, Metric } from "./c01-app";

type Decision={id:string;ordinal:number;action:string;reason:string;parameters:Record<string,unknown>;source_citation_ids:string[];evidence_action_ids:string[]};
type Fit={id:string;recipe:{alpha:number;features:string[]};summary:Round;reason:string;source_citation_ids:string[];evidence_action_ids:string[]};
type Diagnostic={id:string;action:string;reason:string;source_citation_ids:string[];evidence_action_ids:string[];result:{fit_action_id?:string;n:number;interpretation:string;pearson_r?:number;sign_changes?:number;targets?:{target:string;sample_id:string;share_of_absolute_error:number}[];leave_one_out?:{sample_id:string;pearson_r:number}[]}};
type Reference={citation_id:string;source:{title:string;path:string;sha256:string;kind:string;source_url?:string|null};location:{page?:number;line_start?:number;line_end?:number}};
type Memory={record:{id:string;kind:string;review_status:string;scope:Record<string,string>;payload:{reason?:string;action?:string};provenance:{action_id:string;source_citation_ids:string[]}};inclusion_status:string;source_versions:unknown[]};
export type AgentDelivery={enabled:boolean;research:{goal:string;status:string;origin_observation_sha256:string;archive_sha256:string;fits:Fit[];diagnostics:Diagnostic[];decisions:Decision[];references:Reference[]};memory:{entries:Memory[];scope:Record<string,string>}|null;validation:{recipes_checked:number;diagnostics_checked:number;max_abs_prediction_error:number;scientific_validation:false}};

const figure:Figure={title:"模型配方与逐折均值基线",path:"research/comparison.png",caption:"真实逐折MAE与均值基线之比；同8个合金重复使用，未作独立验证。"};
const fieldNames:Record<string,string>={ecm_gpa:"弹性模量",yield_mpa:"屈服强度",water_contact_angle_deg:"水接触角",sfe_owrk_total_mn_m:"OWRK总表面自由能"};
const targetNames:Record<string,string>={cell_seeding_efficiency_24h_pct:"24小时接种率",dna_cell_count_d21:"DNA原表近似细胞数",alp_norm_d21:"ALP/DNA原表值",calcium_deposition_d21_ug_ml:"ARS原表读数（日期待核）"};
const section=(title:string):HTMLElement=>{const s=el("section","content-section");s.append(el("h2","section-title",title));return s;};
const paragraph=(parent:HTMLElement,text:string,cls=""):void=>{parent.append(el("p",cls,text));};
const anchor=(text:string,url:string,cls="text-button"):HTMLAnchorElement=>{const a=el("a",cls,text);a.href=url;return a;};
const fitLabel=(fit:Fit,i:number):string=>{const f=fit.recipe.features;const group=f.length===4?"四特征":f.every(k=>["ecm_gpa","yield_mpa"].includes(k))?"力学组":f.every(k=>["water_contact_angle_deg","sfe_owrk_total_mn_m"].includes(k))?"表面组":"特征子集";return `C${i+1} · ${group} · alpha ${numeric(fit.recipe.alpha)}`;};
const metricText=(m:Metric):string=>`${targetNames[m.target]||m.target_label}：MAE ${numeric(m.mae)}，均值基线 ${numeric(m.baseline_mae)}，R² ${numeric(m.r2)}。`;
const refIds=(cites:string[]):string[]=>cites.map(id=>"agent-ref-"+id);
export const agentState=(agent:AgentDelivery):string=>agent.research.status==="stopped"?"本轮已停止":agent.research.status==="paused"?"本轮已暂停":"已执行记录 · 非实时";

export function agentCards(agent:AgentDelivery,data:Case):C01Card[]{
  const r=agent.research,used=new Set(r.decisions.flatMap(d=>d.source_citation_ids));
  const sources=r.references.filter(ref=>used.has(ref.citation_id));
  const sourceDetails=sources.flatMap(ref=>[ref.source.title+" · "+(ref.location.page?`PDF第${ref.location.page}页`:`第${ref.location.line_start}-${ref.location.line_end}行`),ref.source.path]);
  const cards:C01Card[]=[
    {id:"agent-question",phase:"evidence",kind:"研究问题",tag:"医疗 × 材料",title:"材料属性能否支持体外细胞响应预测",body:r.goal,details:[r.goal,"8个合金汇总样本；这是既有测量的探索性研究，不是新增细胞实验。"],refs:[]},
    {id:"c01-source",phase:"evidence",kind:"原始数据",tag:"固定公开输入",title:"8个钛合金的材料与细胞记录",body:"材料属性作输入，四项体外终点分别评价。每折留出一个完整合金。",details:[`数据DOI：${data.source.doi}`,`原包SHA256：${r.archive_sha256}`,"每折只在另7个合金上拟合标准化与Ridge；SD、不同时间点没有扩成独立材料样本。","DNA、ALP与ARS的字段解释及日期限制须一并阅读。"],refs:[]},
    {id:"agent-evidence-group",phase:"evidence",kind:"引用依据",tag:sources.length+"处原文定位",title:"数据核对与方法适用条件",body:"来源记录与论文方法分开保留；命中一篇论文不等于它适用于本案例。",details:sourceDetails,refs:["c01-source"]},
  ];
  for(const ref of sources){const loc=ref.location;cards.push({id:"agent-ref-"+ref.citation_id,phase:"evidence",kind:ref.source.kind==="research_paper"?"方法文献":"核对笔记",tag:loc.page?`PDF第${loc.page}页`:`第${loc.line_start}-${loc.line_end}行`,title:ref.source.title,body:"保留原文定位与文件指纹；本视图提供来源元数据。",details:[`来源类型：${ref.source.kind}`,`定位：${JSON.stringify(loc)}`,`本地参考库位置：${ref.source.path}`,ref.source.source_url?`原始链接：${ref.source.source_url}`:"这是项目派生核对笔记，不能代替原始研究证据。",`文件SHA256：${ref.source.sha256}`,"本交付没有论文全文或检索摘录；来源适用性仍需判断。"],refs:[]});}
  for(const d of r.decisions.filter(d=>d.action==="search"))cards.push({id:d.id,phase:"evidence",kind:"资料查询",tag:`动作 ${String(d.ordinal).padStart(2,"0")}`,title:String(d.parameters.query||"资料检索"),body:d.reason,details:[d.reason,"查询："+String(d.parameters.query||""),"已执行的查询记录；分发投影不包含每次命中的原文摘录。"],refs:[]});
  r.fits.forEach((fit,i)=>{const d=r.decisions.find(d=>d.id===fit.id),count=fit.summary.metrics.filter(m=>m.mae<m.baseline_mae).length;cards.push({id:fit.id,phase:"experiments",kind:"模型配方",tag:`动作 ${String(d?.ordinal||0).padStart(2,"0")} · 已训练`,title:fitLabel(fit,i),body:fit.reason,details:[fit.reason,"假设："+String(d?.parameters.hypothesis||"见原记录"),"预期与失败条件："+String(d?.parameters.expected_effect||"见原记录"),"特征："+fit.recipe.features.map(k=>fieldNames[k]||k).join("、"),...fit.summary.metrics.map(metricText),fit.summary.feedback,"同8个合金重复LOO；未独立验证，不据此晋升材料或确认机制。"],refs:[...fit.evidence_action_ids,...refIds(fit.source_citation_ids)],figure,metric:`${count} / 4`,metricLabel:"MAE较低终点 · 探索性"});});
  cards.push({id:"agent-fit-group",phase:"experiments",kind:"配方对照",tag:`${r.fits.length}项配方 · 本地已执行`,title:r.fits.length>1?"配方与反馈对照":"本轮模型配方",body:"保留逐折结果、均值基线和越界警告；详细记录包含每项配方的理由与反馈。",details:r.fits.flatMap((fit,i)=>[fitLabel(fit,i),fit.reason,...fit.summary.metrics.map(metricText)]),refs:["agent-evidence-group"],figure,metric:String(r.fits.length*32),metricLabel:"逐折Ridge拟合 · 非LLM训练"});
  for(const d of r.diagnostics){const result=d.result,correlation=d.action==="correlation",main=result.targets?.find(t=>t.target==="cell_seeding_efficiency_24h_pct"),flip=result.leave_one_out?.find(v=>v.pearson_r*(result.pearson_r||0)<0);const body=correlation?`全部合金 r=${numeric(result.pearson_r,4)}；${flip?`排除${flip.sample_id}后为${numeric(flip.pearson_r,4)}`:"逐一排除结果见记录"}。`:main?`${main.sample_id}占接种率总绝对误差${numeric(main.share_of_absolute_error*100,4)}%。`:"检查误差是否集中于少数合金。";cards.push({id:d.id,phase:"experiments",kind:"诊断",tag:"已执行 · 描述性",title:correlation?"接触角与接种率的稳定性":"误差集中度",body,details:[d.reason,result.interpretation,...(result.targets||[]).map(t=>`${targetNames[t.target]||t.target}：${t.sample_id}占总绝对误差${numeric(t.share_of_absolute_error*100,4)}%。`),...(result.leave_one_out||[]).map(v=>`排除${v.sample_id}：r=${numeric(v.pearson_r,5)}。`)],refs:[...d.evidence_action_ids,...refIds(d.source_citation_ids)],metric:correlation?numeric(result.pearson_r,4):main?numeric(main.share_of_absolute_error*100,4)+"%":undefined,metricLabel:correlation?"全样本相关 · 非因果":"接种率误差占比"});}
  const end=r.decisions.filter(d=>["stop","pause"].includes(d.action)).at(-1);
  if(end)cards.push({id:end.id,phase:"conclusions",kind:"研究决定",tag:agentState(agent),title:end.action==="pause"?"暂停与适用条件":"停止与适用条件",body:end.reason.length>110?end.reason.slice(0,110)+"…":end.reason,details:[end.reason,"这是一项Agent控制决定，不是科学结论的自动认证。"],refs:[...end.evidence_action_ids,...refIds(end.source_citation_ids)]});
  const memories=agent.memory?.entries||[];
  cards.push({id:"agent-memory-group",phase:"conclusions",kind:"条件记忆",tag:`${memories.length}项 · 待科学评审`,title:"记忆与适用条件",body:"观察与判断分开；数据、输入、代码和协议必须匹配，撤回资格随来源更新保留。",details:[`${memories.length}项历史记忆快照；不是实时数据库状态。`,"数值观察已复算，科学有效性仍未认证。","不同数据或评估器不会继承这些数值经验。","每项记忆分别保存来源版本与资格；来源更新不会自动恢复已撤回资格。"],refs:end?[end.id]:[]},
    {id:"agent-next",phase:"conclusions",kind:"后续条件",tag:"待核验 · 未执行",title:"先补数据定义与独立证据",body:"标签、重复结构、量纲与时间点需要核对，再固定新一轮问题与评估。",details:["当前没有新增独立生物实验，也没有后台模型或AgentArts调用。","下一项工作需要兼容的独立数据与方法核验；不能在已见8个合金上反复选择后宣称科学提升。"],refs:end?[end.id]:[]});
  return cards;
}

export function agentFlowCards(cards:C01Card[],all:boolean):C01Card[]{
  if(all)return cards;
  const chosen=cards.filter(c=>c.kind!=="资料查询"&&c.kind!=="模型配方"&&!c.id.startsWith("agent-ref-"));
  const fits=new Set(cards.filter(c=>c.kind==="模型配方").map(c=>c.id));
  return chosen.map(c=>({...c,refs:[...new Set(c.refs.map(id=>fits.has(id)?"agent-fit-group":id.startsWith("agent-ref-")?"agent-evidence-group":id))].filter(id=>id!==c.id)}));
}

export function agentKnowledgeItems(agent:AgentDelivery,data:Case):C01KnowledgeItem[]{
  const cards=agentCards(agent,data),items:C01KnowledgeItem[]=[];
  for(const card of cards){if(card.id==="c01-source")items.push({card,type:"数据集",topics:["材料表征","体外细胞"],cover:"sage",label:"原始数据 · 固定公开输入"});else if(card.id.startsWith("agent-ref-"))items.push({card,type:"文献与证据",topics:["数据核验","统计与评价"],cover:"lavender",label:card.kind+" · 来源元数据"});else if(card.kind==="模型配方"||card.kind==="诊断")items.push({card,type:"方法与工具",topics:["统计与评价"],cover:"sand",label:card.kind+" · 本地已执行"});}
  const order=new Map(agent.research.decisions.map(d=>[d.id,d.ordinal]));
  const memories=[...(agent.memory?.entries||[])].sort((a,b)=>(order.get(a.record.provenance.action_id)||0)-(order.get(b.record.provenance.action_id)||0));
  for(const memory of memories){const entry=memory.record,fit=agent.research.fits.find(f=>f.id===entry.provenance.action_id),diagnostic=agent.research.diagnostics.find(d=>d.id===entry.provenance.action_id);const index=agent.research.fits.findIndex(f=>f.id===entry.provenance.action_id);const title=fit?fitLabel(fit,index)+" · 数值观察":diagnostic?diagnostic.action==="correlation"?"关联不稳定的观察":"误差集中度的观察":"本轮停止的条件与依据";const original=cards.find(c=>c.id===entry.provenance.action_id);items.push({type:"研究记忆",topics:["材料表征","体外细胞","统计与评价","研究边界"],cover:"lavender",label:entry.kind==="agent_decision"?"Agent判断 · 待科学评审":"条件观察 · 待科学评审",card:{id:"agent-memory-"+entry.id,kind:"条件记忆",phase:"conclusions",tag:"历史快照 · 有适用条件",title,body:fit?`${fit.recipe.features.length}项特征，alpha ${numeric(fit.recipe.alpha)}；保存实际指标与来源。`:diagnostic?"保留本数据下的诊断结果，不推广为一般规律。":"记录当时为什么停止，不自动变成后续研究指令。",details:[`角色：${entry.kind}；资格：${memory.inclusion_status}；科学评审：未完成。`,...Object.entries(entry.scope).map(([key,value])=>`${key}：${value}`),`来源版本数：${memory.source_versions.length}`,"仅在数据与评估器条件完全匹配时召回；不是跨数据集的科学规律。",...(original?.details||[entry.payload.reason||"原始判断见研究记录。"]),`原动作ID：${entry.provenance.action_id}`],refs:original?[original.id]:[],figure:fit?figure:undefined}});}
  return items;
}

function resultFigure():HTMLElement{const fig=el("figure","figure-block"),img=el("img");img.src="/api/c01/research/comparison.png";img.alt=figure.title;img.loading="lazy";img.addEventListener("error",()=>img.replaceWith(el("p","figure-error","图表暂未载入，指标与复现附件仍可查看。")),{once:true});fig.append(el("h3","","本轮图表摘要"),img,el("figcaption","",figure.caption));return fig;}

export function renderAgentOverview(content:HTMLElement,agent:AgentDelivery):void{
  const r=agent.research,hero=el("section","project-hero"),copy=el("div","hero-copy"),archive=el("div","hero-archive");copy.append(el("span","pill sage",agentState(agent)+" · 外部Agent记录"),el("h2","","材料属性能否支持体外细胞响应预测？"),el("p","hero-description","查询依据、提出配方、读取真实结果，再决定是否继续。"));const actions=el("div","hero-actions");actions.append(anchor("查看本轮研究 →","#/research","action-button primary"),anchor("阅读报告与复现 →","#/outputs"));copy.append(actions);archive.append(el("span","archive-top","已执行研究"),el("div","archive-orbit",r.decisions.length+" 步"),el("span","archive-foot","外置Agent选择 · 本地计算"));hero.append(copy,archive);content.append(hero);
  const grid=el("div","overview-grid"),progress=section("本轮推进"),decision=section("当前决定");paragraph(progress,`${r.decisions.length}项已执行动作 · ${r.fits.length}组配方 · ${r.fits.length*32}次逐折拟合`);paragraph(progress,`${r.diagnostics.length}项敏感性诊断 · ${agent.memory?.entries.length||0}项带条件记忆`);progress.append(anchor("追溯依据与反馈 →","#/research"));paragraph(decision,agentState(agent));paragraph(decision,"已见数据上的改善仍需要独立证据，不能据此选择最佳材料或确认机制。");decision.append(anchor("阅读停止依据 →","#/research?view=records"));grid.append(progress,decision);content.append(grid);
  const summary=el("div","overview-bottom"),notes=section("配方比较");for(const fit of r.fits){const count=fit.summary.metrics.filter(m=>m.mae<m.baseline_mae).length;paragraph(notes,`${fitLabel(fit,r.fits.indexOf(fit))}：${count}/4项终点MAE低于逐折均值基线。`);}paragraph(notes,"所有比较复用同8个合金；指标变化与科学有效性分别判断。","detail-note");notes.append(anchor("比较配方与真实指标 →","#/experiments"));summary.append(notes,resultFigure());content.append(summary);paragraph(content,"这是已完成动作的只读记录。后台模型、平台调用、独立科学验证与LLM权重训练尚未接通或验收。","page-boundary");
}

export function renderAgentExperiments(content:HTMLElement,agent:AgentDelivery):void{
  const intro=section("相同协议下的四终点比较");paragraph(intro,"每折只用另7个合金拟合StandardScaler与Ridge。各终点分别与训练集均值比较，未单独保留新的外验样本。");intro.append(resultFigure());content.append(intro);
  agent.research.fits.forEach((fit,i)=>{const s=section(fitLabel(fit,i));paragraph(s,"特征："+fit.recipe.features.map(f=>fieldNames[f]||f).join("、"),"muted");paragraph(s,fit.reason);paragraph(s,fit.summary.feedback,"c01-feedback");const wrap=el("div","table-scroll"),table=el("table","trial-table"),head=el("thead"),row=el("tr");for(const text of ["体外终点","模型MAE","逐折均值MAE","R²","比较"]){const th=el("th","",text);th.scope="col";row.append(th);}head.append(row);const body=el("tbody");for(const metric of fit.summary.metrics){const tr=el("tr");for(const text of [targetNames[metric.target]||metric.target_label,numeric(metric.mae),numeric(metric.baseline_mae),numeric(metric.r2),metric.mae<metric.baseline_mae?"MAE较低":"未优于基线"])tr.append(el("td","",text));body.append(tr);}table.append(head,body);wrap.append(table);s.append(wrap);paragraph(s,"预测未裁剪。DNA、ALP、ARS原表字段与测量日期仍须按方法记录解读；这不是临床效用评价。","detail-note");content.append(s);});
}

export function renderAgentOutputs(content:HTMLElement,agent:AgentDelivery):void{
  const actions=section("本轮报告与复现附件");paragraph(actions,`${agent.research.decisions.length}项已执行动作、${agent.research.fits.length}组配方及其诊断。附件提供独立复算入口；启动时已核对保存预测与指标一致。`);const links=el("div","hero-actions");links.append(anchor("阅读报告 PDF ↓","/api/c01/research/report.pdf","action-button primary"),anchor("下载复现附件 ZIP ↓","/api/c01/research/reproduction.zip","action-button"));actions.append(links);content.append(actions);
  const layout=el("div","document-layout reader-layout"),toc=el("aside","document-toc"),article=el("article","reader-document solid-panel");toc.setAttribute("aria-label","本轮报告阅读目录");toc.append(el("span","overline","报告导读"));article.append(el("div","document-label","C01 / Agent研究记录"),el("h1","document-title","材料属性与体外细胞响应"));
  const add=(id:string,title:string,texts:string[])=>{const s=section(title);s.id=id;texts.forEach(t=>paragraph(s,t));article.append(s);const b=el("button","toc-item",title);b.addEventListener("click",()=>s.scrollIntoView({block:"start"}));toc.append(b);};
  add("agent-paper-goal","问题与方法",[agent.research.goal,"8个合金汇总样本；留一合金、逐折拟合标准化与Ridge，逐折训练集均值为基线。"]);article.append(resultFigure());
  add("agent-paper-result","实际结果",agent.research.fits.map((fit,i)=>fitLabel(fit,i)+"。"+fit.summary.metrics.map(metricText).join(" ")));
  add("agent-paper-decision","研究决定",agent.research.decisions.filter(d=>["stop","pause"].includes(d.action)).map(d=>d.reason));
  add("agent-paper-reproduction","如何复算",["将ZIP解压到新目录，使用已安装NumPy与scikit-learn的Python运行 python verify_results.py。验证器独立复算预测、指标与敏感性诊断，不联网，不执行附件source。","文件哈希与重算一致不证明数据真实性、LLM身份或科学有效性。分发附件只含引用元数据，原始论文全文与检索摘录不在ZIP中。"]);
  const refs=section("本轮采用的依据");const used=new Set(agent.research.decisions.flatMap(d=>d.source_citation_ids));for(const ref of agent.research.references.filter(ref=>used.has(ref.citation_id))){paragraph(refs,ref.source.title+" · "+(ref.location.page?`PDF第${ref.location.page}页`:`第${ref.location.line_start}-${ref.location.line_end}行`));const url=safeUrl(ref.source.source_url);if(url)refs.append(anchor("访问原始来源 ↗",url));}article.append(refs);layout.append(toc,article);content.append(layout);
}
