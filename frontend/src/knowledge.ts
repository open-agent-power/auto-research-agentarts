import type { Project, ResearchObject, Source } from "./types";
import { el } from "./dom";

export const knowledgeTypes = ["全部", "文献与证据", "数据集", "方法与工具", "研究记忆"] as const;
export const knowledgeTopics = ["材料性能", "模型与评价", "研究边界"] as const;
export type KnowledgeType = typeof knowledgeTypes[number];
export type KnowledgeTopic = typeof knowledgeTopics[number];
export interface KnowledgeItem { object: ResearchObject; type: KnowledgeType; topics: KnowledgeTopic[]; cover: "sage" | "sand" | "lavender"; label: string; figure?: Project["figures"][number]; }

/** UI classification is a projection of existing records, never a new scientific assertion. */
export function knowledgeItems(objects: ResearchObject[], project?: Project): KnowledgeItem[] {
  return objects.filter((object) => object.kind === "source" || object.kind === "claim").map((object) => {
    if (object.kind === "claim") return {
      object, type: "文献与证据", topics: object.status === "limitation" ? ["研究边界"] : /数据|样本|312/.test(object.title) ? ["材料性能"] : ["模型与评价"],
      cover: "lavender", label: object.status === "limitation" ? "适用边界" : "研究判断 · 非条件记忆",
      figure: object.status === "observed" && /验证|MSE|RMSE|误差/.test(object.title) && object.references.some((ref) => objects.some((record) => record.rawId === ref && record.kind === "trial")) ? project?.figures.find((figure)=>figure.url==="/api/figures/validation.svg") : undefined,
    };
    const source = object.data as Source;
    const value = (source.title + " " + source.description + " " + source.url).toLowerCase();
    if (/\.json(?:\.gz)?|数据与使用范围/.test(value)) return { object, type: "数据集", topics: ["材料性能"], cover: "sage", label: "公开数据来源" };
    if (/scikit-learn|ridge|方法文档/.test(value)) return { object, type: "方法与工具", topics: ["模型与评价"], cover: "sand", label: "方法文档" };
    return { object, type: "文献与证据", topics: /matbench|材料/.test(value) ? ["材料性能", "模型与评价"] : ["模型与评价"], cover: "lavender", label: "文献来源" };
  });
}
export function filterKnowledge(items: KnowledgeItem[], type: string, topics: KnowledgeTopic[]): KnowledgeItem[] {
  return items.filter((item) => (type === "全部" || item.type === type) && (!topics.length || topics.some((topic) => item.topics.includes(topic))));
}
export function typeCover(item: KnowledgeItem): HTMLElement {
  const cover = el("div", "type-cover " + item.cover);
  cover.setAttribute("aria-hidden", "true");
  cover.append(el("span", "cover-label", "类型图示 · " + item.type), el("span", "cover-symbol", item.type === "数据集" ? "▦" : item.type === "方法与工具" ? "ƒ" : item.object.kind === "claim" ? "◇" : "▤"));
  const lines = el("span", "cover-lines"); lines.append(el("i"), el("i"), el("i")); cover.append(lines, el("span", "cover-id", item.object.rawId));
  return cover;
}
export function knowledgeCard(item: KnowledgeItem, preview: (id: string) => void, read: (id: string) => void): HTMLElement {
  const object = item.object;
  const card = el("article", "knowledge-card"); card.id = "item-" + object.id;
  if(item.figure){
    const visual=el("div","knowledge-figure");const image=el("img");image.src=item.figure.url;image.alt="本项目验证结果图";image.loading="lazy";
    image.addEventListener("error",()=>visual.replaceWith(typeCover(item)),{once:true});visual.append(image,el("span","","本项目结果图 · 非原文插图"));card.append(visual);
  } else card.append(typeCover(item));
  const body = el("div", "knowledge-card-body");
  body.append(el("span", "overline", item.label), el("h2", "", object.title), el("p", "card-summary", object.kind === "claim" ? object.summary : object.summary));
  const tags = el("div", "topic-tags"); item.topics.forEach((topic) => tags.append(el("span", "", topic))); body.append(tags);
  const actions = el("div", "card-actions");
  const peek = el("button", "quiet-button", "预览摘要"); peek.dataset.focusId = object.id; peek.addEventListener("click", () => preview(object.id));
  const full = el("button", "text-button", object.kind === "source" ? "阅读资料记录 ↗" : "完整记录 ↗"); full.dataset.readId=object.id;full.addEventListener("click", () => read(object.id));
  actions.append(peek, full); body.append(actions); card.append(body); return card;
}

/** The default flow includes limited context plus actual trial citations, without inferred edges. */
export function relationObjects(project: Project, objects: ResearchObject[], items: KnowledgeItem[], all: boolean, hasFilter: boolean): ResearchObject[] {
  if (all && !hasFilter) return objects;
  const selected = new Set<string>();
  if (hasFilter) items.forEach((item) => selected.add(item.object.rawId));
  else {
    objects.filter((object)=>object.kind==="question"||object.kind==="questions").forEach((object)=>selected.add(object.rawId));
    const sources=knowledgeItems(objects).filter((item)=>item.object.kind==="source");
    const data=sources.find((item)=>item.type==="数据集");const method=sources.find((item)=>item.type==="方法与工具");
    for(const item of [data,method])if(item)selected.add(item.object.rawId);
    if(!data&&!method&&sources[0])selected.add(sources[0].object.rawId);
    if (project.metrics.best_trial_id) selected.add(project.metrics.best_trial_id);
    objects.filter((object)=>object.kind==="trial").forEach((object)=>selected.add(object.rawId));
    objects.filter((object) => object.kind === "claim" && object.references.includes(project.metrics.best_trial_id)&&/验证|MSE|误差|改善/.test(object.title)).slice(0,2).forEach((object) => selected.add(object.rawId));
  }
  // Only follow recorded citations. No inferred source-to-trial or scientific support edges.
  let changed = true;
  while (changed) {
    changed = false;
    for (const object of objects) if (selected.has(object.rawId)) for (const ref of object.references) {
      if (!selected.has(ref) && objects.some((candidate) => candidate.rawId === ref)) { selected.add(ref); changed = true; }
    }
  }
  return objects.filter((object) => selected.has(object.rawId));
}
