import type { Project, ResearchObject } from "./types";
import { el } from "./dom";

const NS="http://www.w3.org/2000/svg";
const drawings: Record<ResearchObject["kind"], string[]> = {
  question:["M28 14h112a12 12 0 0 1 12 12v25a12 12 0 0 1-12 12H77L57 77V63H28a12 12 0 0 1-12-12V26a12 12 0 0 1 12-12Z","M43 30h77M43 44h54","M177 22h39v40h-39zM186 34h20M186 47h13"],
  source:["M28 13h102v62H28zM28 31h102M61 13v62M95 13v62M28 47h102M28 62h102","M163 18h43l15 15v40h-58zM206 18v15h15M176 44h29M176 56h22"],
  trial:["M28 18v52h191M48 57V42h25v15M94 57V30h25v27M140 57V21h25v36","M43 19h23M92 13h23M140 6h23","M186 25v22M175 36h22"],
  claim:["M26 14h141v62H26zM44 30l5 5 9-10M44 52l5 5 9-10M75 31h69M75 53h52","M188 21l24 9v18c0 13-24 25-24 25s-24-12-24-25V30z","M180 45l7 7 14-16"],
  paper:["M52 8h108l18 18v52H52zM160 8v18h18M71 23h53M71 40h85M71 51h85M71 62h57","M30 22v62h129"],
  questions:["M35 18h154v56H35zM51 34h110M51 49h77","M172 57h41M192 37v40","M57 10V4M81 10V4M105 10V4"],
};
function illustration(object:ResearchObject):HTMLElement{
  const visual=el("div","node-visual node-illustration");visual.dataset.illustration=object.kind;
  const sourceText=object.kind==="source"?object.title+" "+object.summary:"";
  const subtype=object.kind==="source"?(/数据与|数据集/.test(sourceText)?"数据集":/Ridge|scikit-learn|方法文档/.test(sourceText)?"方法与工具":"文献资料"):({question:"研究问题",trial:"配方试验",claim:"研究判断",paper:"报告",questions:"待处理问题"} as Partial<Record<ResearchObject["kind"],string>>)[object.kind];
  let paths=drawings[object.kind];
  if(subtype==="数据集")paths=["M40 12h160v63H40zM40 31h160M40 49h160M40 62h160M80 12v63M120 12v63M160 12v63"];
  else if(subtype==="文献资料")paths=["M48 13h61l11 10 11-10h61v61h-61l-11 8-11-8H48zM120 23v59M64 30h31M64 43h31M64 56h20M143 30h32M143 43h32M143 56h20"];
  else if(subtype==="方法与工具")paths=["M46 13h148v62H46zM77 30l-14 13 14 13M163 30l14 13-14 13M130 25l-17 36M95 44h12M140 44h8"];
  const svg=document.createElementNS(NS,"svg");svg.setAttribute("viewBox","0 0 240 88");svg.setAttribute("aria-hidden","true");
  paths.forEach((drawing)=>{const path=document.createElementNS(NS,"path");path.setAttribute("d",drawing);svg.append(path);});
  visual.append(svg,el("span","node-visual-caption","类型图示 · "+subtype));return visual;
}
export function nodeVisual(object:ResearchObject,project:Project):HTMLElement{
  const hasTrialReference=object.references.some((id)=>project.trials.some((trial)=>trial.id===id));
  const eligible=object.kind==="trial"&&object.rawId===project.metrics.best_trial_id || object.kind==="claim"&&object.status==="observed"&&hasTrialReference&&/验证|MSE|误差/.test(object.title);
  const figure=eligible?project.figures.find((item)=>item.url==="/api/figures/validation.svg"):undefined;
  if(!figure)return illustration(object);
  const visual=el("div","node-visual node-result-image");const image=el("img");image.src=figure.url;image.alt="本项目已有试验的训练与验证误差比较图";image.draggable=false;
  image.addEventListener("error",()=>visual.replaceWith(illustration(object)),{once:true});visual.append(image,el("span","node-visual-caption","本项目结果图 · 全部候选比较"));return visual;
}
