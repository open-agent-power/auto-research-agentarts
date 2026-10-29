import { el, numeric } from "./dom";

type Action={id:string; request_id:string; ordinal:number; title:string; reason:string; decision:string; result:{kind:string;targets?:{target:string;sample_id:string;share_of_absolute_error:number}[];pearson_r?:number;leave_one_out?:{sample_id:string;pearson_r:number}[];interpretation:string}};
type State={enabled:boolean;error?:string;csrf_token?:string;parent_snapshot_sha256?:string;observation_sha256?:string;status?:string;next_action?:string;actions?:Action[];budget?:{used:number;max:number}};
const labels:Record<string,string>={cell_seeding_efficiency_24h_pct:"24 小时细胞接种效率",dna_cell_count_d21:"第 21 天 DNA（换算待核）",alp_norm_d21:"第 21 天 ALP",calcium_deposition_d21_ug_ml:"ARS 染色指标（日期有冲突）"};
const item=(tag:keyof HTMLElementTagNameMap,text:string,cls=""):HTMLElement=>el(tag,cls,text);

export function mountC01Controls(container:HTMLElement):void{
  let data:State|null=null,busy=false,pending="",message="",error=false,key="";
  const savePending=(id:string):boolean=>{try{sessionStorage.setItem(key,id);return true;}catch{return false;}};
  const clearPending=():void=>{try{sessionStorage.removeItem(key);}catch{} pending="";};
  async function refresh():Promise<void>{
    try{
      const response=await fetch("/api/c01/continuation",{cache:"no-store"});const value=await response.json() as State;
      if(!response.ok)throw new Error(value.error||"后续研究状态不可读取。");
      data=value;
      if(data.enabled&&data.parent_snapshot_sha256){
        key="c01-continuation-pending:"+data.parent_snapshot_sha256;
        try{pending=sessionStorage.getItem(key)||"";}catch{pending="";}
        if(pending&&data.actions?.some(a=>a.request_id===pending))clearPending();
      }
    }catch(e){data=null;message=e instanceof Error?e.message:"研究状态不可读取。";error=true;}
    render();
  }
  async function step():Promise<void>{
    if(!data?.csrf_token||!data.observation_sha256||busy||!key)return;
    if(!pending){const id="c01-"+crypto.randomUUID();if(!savePending(id)){message="浏览器会话存储不可用，未提交行动。";error=true;render();return;}pending=id;}
    busy=true;message="正在执行本地分析…";error=false;render();
    try{
      const response=await fetch("/api/c01/continuation/step",{method:"POST",headers:{"Content-Type":"application/json","X-Research-CSRF":data.csrf_token},body:JSON.stringify({request_id:pending,observation_sha256:data.observation_sha256})});
      const value=await response.json() as {state?:State;error?:string;code?:string};
      if(!response.ok){if(value.code==="STALE_OBSERVATION"||value.code==="BUDGET_EXHAUSTED")clearPending();throw new Error(value.error||"行动未确认，请使用原请求重试。");}
      if(!value.state?.actions?.some(a=>a.request_id===pending))throw new Error("结果未确认，请使用原请求重试。");
      clearPending();data={...value.state,enabled:true,csrf_token:data.csrf_token};message="本次行动已保存。";error=false;
      window.dispatchEvent(new CustomEvent("c01-continuation-changed",{detail:data}));
    }catch(e){message=e instanceof Error?e.message:"结果未确认，请使用原请求重试。";error=true;}
    finally{busy=false;render();}
  }
  function render():void{
    container.replaceChildren(); const heading=el("div","c01-cont-head");heading.append(item("span","LOCAL RESEARCH","overline"),item("h2","继续研究"),item("p","从已冻结的两轮结果出发，逐步检查数据中的不稳定性。每一步由本地脚本执行；不调用大模型。","muted"));container.append(heading);
    if(!data){container.append(item("p",message||"正在读取研究状态。","detail-note"));return;}
    if(!data.enabled){container.append(item("p","当前工作台仅查看冻结结果；启用独立后续研究工作区后可继续。","detail-note"));return;}
    const status=data.status==="needs_review"?"等待领域复核":data.status==="paused"?"已暂停，可继续":"尚未开始";
    const info=el("div","c01-cont-status");info.append(item("span",status,"pill sage"),item("span",`本地分析 ${data.budget?.used??0} / ${data.budget?.max??2}`,"muted"));container.append(info);
    container.append(item("p","下一步："+(data.next_action||"核查当前状态。"),"c01-cont-next"));
    const go=el("button","action-button primary",pending?"确认或重试上次行动":data.status==="needs_review"?"等待复核":data.status==="paused"?"继续下一步":"开始第一步");go.disabled=busy||(!pending&&data.status==="needs_review");go.addEventListener("click",()=>{void step();});container.append(go);
    if(message)container.append(item("p",message,"demo-feedback"+(error?" error":"")));
    for(const a of data.actions||[]){
      const block=el("article","c01-cont-action");block.append(item("span",`行动 ${String(a.ordinal).padStart(2,"0")} · 本地脚本`,"overline"),item("h3",a.title),item("p",a.reason,"muted"));
      if(a.result.kind==="held_out_error_influence")for(const v of a.result.targets||[])block.append(item("p",`${labels[v.target]||v.target}：${v.sample_id} 占总绝对误差 ${numeric(v.share_of_absolute_error*100,4)}%。`,"c01-cont-result"));
      if(a.result.kind==="pair_correlation_influence"){
        block.append(item("p",`全部 8 个合金：r = ${numeric(a.result.pearson_r,4)}。`,"c01-cont-result"));
        for(const v of a.result.leave_one_out||[])if((a.result.pearson_r||0)*v.pearson_r<0)block.append(item("p",`去掉 ${v.sample_id}：r = ${numeric(v.pearson_r,4)}，关联方向改变。`,"c01-cont-result"));
      }
      block.append(item("p",a.result.interpretation,"detail-note"),item("p","判断："+a.decision,"muted"));container.append(block);
    }
    if(data.actions?.length){const downloads=el("div","hero-actions");for(const [title,url] of [["后续研究报告 PDF ↓","/api/c01/continuation/report.pdf"],["后续复现附件 ↓","/api/c01/continuation/reproduction.zip"],["研究记录 JSON ↓","/api/c01/continuation/evidence.json"]]){const a=el("a","action-button",title);a.href=url;downloads.append(a);}container.append(downloads);container.append(item("p","后续报告与原 C01 报告独立保存；两轮沿用已有公开数据，不是新实验或独立验证。","page-boundary"));}
  }
  void refresh();
}
