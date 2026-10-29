import type { Project, ResearchObject, Trial } from "./types";
import type { ContentContext } from "./content";
import { badge, figures, questionForm, renderDetails } from "./content";
import { date, el, field, numeric, paragraph, safeUrl, text } from "./dom";
import { knowledgeItems, knowledgeCard, filterKnowledge, knowledgeTypes, knowledgeTopics, type KnowledgeType, type KnowledgeTopic } from "./knowledge";

export type Page = "overview" | "research" | "experiments" | "knowledge" | "outputs" | "read";
export const pageLabels: Record<Page, string> = { overview: "项目总览", research: "研究推进", experiments: "实验中心", knowledge: "知识空间", outputs: "成果与复现", read: "记录阅读" };
export interface Route { page: Page; id?: string; type: KnowledgeType; topics: KnowledgeTopic[]; view: "cards" | "relations"; researchView: "flow" | "records"; panorama: boolean; from: string; }
export interface PageContext extends ContentContext { read: (id: string) => void; navigate: (hash: string) => void; returnFromReader: () => void; }
export function parseRoute(hash: string): Route {
  const [path, query = ""] = hash.replace(/^#\/?/, "").split("?");
  const [name, rawId] = path.split("/");
  const params = new URLSearchParams(query);
  const page: Page = Object.hasOwn(pageLabels, name) ? name as Page : "overview";
  let id = ""; try { id = decodeURIComponent(rawId || ""); } catch { /* unknown object is displayed as empty */ }
  const type = params.get("type");
  const topics = knowledgeTopics.filter((topic)=>params.getAll("topic").includes(topic));
  const from = params.get("from") || "#/knowledge";
  return { page, id, type: knowledgeTypes.includes(type as KnowledgeType) ? type as KnowledgeType : "全部", topics, view: params.get("view") === "relations" ? "relations" : "cards", researchView: params.get("view")==="records"||params.get("section")==="questions"?"records":"flow", panorama: params.get("scope") === "all", from: /^#\/(overview|research|experiments|knowledge|outputs)(\?|$)/.test(from) ? from : "#/knowledge" };
}
export function knowledgeHash(route: Partial<Route>): string {
  const params = new URLSearchParams();
  if (route.type && route.type !== "全部") params.set("type", route.type);
  knowledgeTopics.filter((topic)=>route.topics?.includes(topic)).forEach((topic)=>params.append("topic",topic));
  if (route.view === "relations") params.set("view", "relations");
  if (route.panorama) params.set("scope", "all");
  return "#/knowledge" + (params.size ? "?" + params.toString() : "");
}
export function researchHash(route:Partial<Route>):string{
  const params=new URLSearchParams();
  if(route.researchView==="records")params.set("view","records");
  if(route.panorama)params.set("scope","all");
  return "#/research"+(params.size?"?"+params.toString():"");
}
function action(label: string, click: () => void, cls = "quiet-button"): HTMLButtonElement { const button = el("button", cls, label); button.addEventListener("click", click); return button; }
function pageHead(container: HTMLElement, page: Page, subtitle: string): HTMLElement {
  const head = el("header", "page-heading"); const title = el("div");
  title.append(el("h1", "", pageLabels[page]), el("p", "", subtitle)); head.append(title); container.append(head); return head;
}
function section(title: string): HTMLElement { const block = el("section", "content-section"); block.append(el("h2", "section-title", title)); return block; }
function figureOne(project: Project, index = 0): HTMLElement {
  const figure = project.figures[index]; const block = el("figure", "figure-block");
  if (!figure) { paragraph(block, "当前快照未提供结果图。", "empty-state"); return block; }
  block.append(el("h3", "", figure.title));
  if (["/api/figures/validation.svg", "/api/figures/prediction.svg"].includes(figure.url)) {
    const image = el("img"); image.src = figure.url; image.alt = figure.title; image.loading = "lazy"; image.addEventListener("error", () => image.replaceWith(el("p", "figure-error", "图表暂未载入，可查看复现附件。")), { once: true }); block.append(image);
  }
  block.append(el("figcaption", "", figure.caption)); return block;
}
function objectFor(context: PageContext, raw: string): ResearchObject | undefined { return context.objects.find((object) => object.rawId === raw); }
function viewButton(context: PageContext, object: ResearchObject | undefined, label = "查看完整记录 ↗"): HTMLElement {
  const button = action(label, () => { if (object) context.open(object.id); }, "text-button"); button.disabled = !object; if (object) button.dataset.focusId = object.id; return button;
}
function metric(label: string, value: string, foot: string): HTMLElement { const block = el("div", "metric-item"); block.append(el("dt", "", label), el("dd", "", value), el("small", "", foot)); return block; }
function splits(project: Project): string { const s = project.dataset.split_counts as Record<string, unknown> | undefined; return s ? text(s.train) + " / " + text(s.validation) + " / " + text(s.test) : "未提供"; }

function overview(container: HTMLElement, context: PageContext): void {
  const p = context.project;
  pageHead(container, "overview", "研究目标、已有结果与待处理问题。");
  const hero = el("section", "project-hero"); const copy = el("div", "hero-copy");
  const label = el("div", "eyebrow-line"); label.append(el("span", "pill sage", p.labels.scientific_status || "现有证据"), el("span", "muted", "研究问题"));
  copy.append(label, el("h2", "", p.question), el("p", "hero-description", "已有研究记录"));
  const heroActions = el("div", "hero-actions"); heroActions.append(action("查看研究推进 →", () => context.navigate("#/research"), "action-button primary"), action("了解数据与来源 ↗", () => context.navigate("#/knowledge"), "text-button")); copy.append(heroActions);
  const visual = el("div", "hero-archive"); visual.setAttribute("aria-hidden", "true");
  visual.append(el("span", "archive-top", "研究档案")); const orbit = el("div", "archive-orbit"); orbit.append(el("span", "", "成分"), el("span", "", "比较"), el("span", "", "判断"), el("b", "", "研究\n档案")); visual.append(orbit, el("span", "archive-foot", "已有记录"));
  hero.append(copy, visual); container.append(hero);
  const stats = el("dl", "progress-strip"); stats.append(metric("已有真实试验", numeric(p.metrics.trials), numeric(p.metrics.accepted) + " 次采用 / " + numeric(p.metrics.rejected) + " 次未晋升"), metric("当前保留 · 验证 MSE", numeric(p.metrics.best_validation_mse), "固定验证集上的保留模型"), metric("独立终测", p.metrics.test_mse === null ? "尚未执行" : numeric(p.metrics.test_mse), "终测与验证成绩分开记录")); container.append(stats);
  const grid = el("div", "overview-grid");
  const results = section("当前结果");
  const retained = p.trials.find((trial) => trial.id === p.metrics.best_trial_id);
  if (retained) { results.append(el("h3", "retained-title", retained.candidate.degree + " 阶配方 · α = " + numeric(retained.candidate.alpha)), el("p", "", "当前保留的试验 " + String(retained.ordinal).padStart(2, "0") + "，与历史候选的单次采用状态分开。"), viewButton(context, objectFor(context, retained.id), "查看保留模型与判定 ↗")); }
  else paragraph(results, "当前快照未提供保留模型。", "empty-state");
  p.claims.filter((claim) => claim.status === "observed").slice(-2).forEach((claim) => {
    const row = el("div", "insight-line"); row.append(el("span", "insight-mark", "◇"), el("p", "", claim.statement)); results.append(row);
  });
  const next = section("待处理问题"); next.classList.add("sand-panel");
  if (p.next_questions.length) paragraph(next, p.next_questions[p.next_questions.length - 1].text, "next-question-text");
  else { paragraph(next, "暂无待处理问题。", "next-question-text"); paragraph(next, "可记录需要补充的数据、比较实验或评价问题。", "muted"); }
  next.append(el("span", "pill sand", "待人工安排 · 不自动执行"), action("添加问题 →", () => context.navigate("#/research?view=records&section=questions"), "text-button"));
  grid.append(results, next); container.append(grid);
  const bottom = el("div", "overview-bottom"); const data = section("数据与评价范围");
  data.append(el("h3", "", text(p.dataset.dataset_id)), el("p", "", "训练 / 验证 / 测试：" + splits(p) + "。输入为 " + (Array.isArray(p.dataset.feature_names) ? p.dataset.feature_names.length : "未提供") + " 个特征。"), el("p", "muted", "本项目自定义组成分组 holdout；不等同于官方 Matbench 五折成绩。"), action("阅读数据来源 ↗", () => context.navigate(knowledgeHash({type:"数据集"})), "text-button"));
  bottom.append(data, figureOne(p)); container.append(bottom);
  const boundary = el("p", "page-boundary", p.labels.decision_origin + "。" + p.labels.cloud + "；现有记录不构成医疗、跨域或科研发现验证。"); container.append(boundary);
}

function researchRecords(container: HTMLElement, context: PageContext): void {
  const p = context.project;
  const body = el("div", "research-layout"); const history = section("研究过程");
  const timeline = el("ol", "research-timeline");
  p.trials.forEach((trial) => {
    const row = el("li", "timeline-item"); const num = el("div", "timeline-index", String(trial.ordinal).padStart(2, "0")); const content = el("article", "timeline-content");
    const meta = el("div", "timeline-meta"); meta.append(el("span", "overline", "试验 " + String(trial.ordinal).padStart(2, "0")), badge(trial.status)); if (trial.id === p.metrics.best_trial_id) meta.append(el("span", "pill sage", "当前保留"));
    content.append(meta, el("h3", "", trial.candidate.degree + " 阶特征 × α " + numeric(trial.candidate.alpha)));
    const steps = el("dl", "progress-steps"); field(steps, "原始提案", trial.proposal?.hypothesis || trial.reason || "未记录"); field(steps, "实际尝试", "真实训练，验证 MSE " + numeric(trial.metrics?.validation_mse)); field(steps, "记录判定", trial.decision_reason || "未记录"); content.append(steps);
    if (trial.parent_trial_id) { const parent = p.trials.find((item) => item.id === trial.parent_trial_id); paragraph(content, "保留父模型：" + (parent ? "试验 " + String(parent.ordinal).padStart(2, "0") : trial.parent_trial_id), "timeline-parent"); }
    content.append(viewButton(context, objectFor(context, trial.id), "查看假设、引用与工件 ↗")); row.append(num, content); timeline.append(row);
  });
  if (!p.trials.length) paragraph(history, "快照中没有试验轨迹。", "empty-state"); history.append(timeline);
  const right = el("div", "research-side"); const notes = section("待处理问题"); notes.id = "research-questions"; questionForm(notes, context); right.append(notes);
  const limits = section("研究限制"); p.claims.filter((claim) => claim.status === "limitation").forEach((claim) => { const line = el("div", "limitation-item"); line.append(el("p", "", claim.statement), viewButton(context, objectFor(context, claim.id), "查看依据 ↗")); limits.append(line); }); right.append(limits);
  body.append(history, right); container.append(body);
}

function research(container:HTMLElement,route:Route,context:PageContext):ReturnType<typeof renderKnowledge>|undefined{
  pageHead(container,"research","当前研究流程、实验判定和待处理问题。");
  const change=(patch:Partial<Route>)=>context.navigate(researchHash({...parseRoute(location.hash),...patch}));
  const bar=el("div","research-viewbar glass");const views=el("div","segmented");views.setAttribute("role","group");views.setAttribute("aria-label","研究推进视图");
  for(const [value,label] of [["flow","流程画布"],["records","过程记录"]] as const){const button=action(label,()=>change({researchView:value}),route.researchView===value?"active":"");button.dataset.researchView=value;button.setAttribute("aria-pressed",String(route.researchView===value));views.append(button);}
  const questions=action("待处理问题 "+context.project.next_questions.length+" →",()=>context.navigate("#/research?view=records&section=questions"),"quiet-button research-questions-link");questions.dataset.questionsLink="true";bar.append(views,questions);container.append(bar);
  if(route.researchView==="records"){researchRecords(container,context);return;}
  const controls=el("div","research-flow-controls");const scopes=el("div","segmented");scopes.setAttribute("aria-label","画布记录范围");
  for(const [all,label] of [[false,"当前流程"],[true,"全景展开"]] as const){const button=action(label,()=>change({panorama:all}),route.panorama===all?"active":"");button.dataset.researchScope=all?"all":"current";button.setAttribute("aria-pressed",String(route.panorama===all));scopes.append(button);}
  controls.append(scopes,el("p","","连线表示原记录引用；流程顺序用于浏览。"));container.append(controls);
  const panel=el("div","relation-board research-board");panel.id="relation-board";const graph=el("div","graph-surface");graph.id="graph";graph.tabIndex=0;graph.setAttribute("role","region");graph.setAttribute("aria-label","研究流程画布。拖动空白平移，Ctrl或⌘加滚轮缩放，Enter查看节点记录。");panel.append(graph);container.append(panel);
  paragraph(container,context.project.labels.decision_origin+"。当前为已有证据快照，模型与平台接入暂缓。","page-boundary");
  return {items:knowledgeItems(context.objects,context.project),boardContainer:panel};
}

function experiments(container: HTMLElement, context: PageContext): void {
  const p = context.project; pageHead(container, "experiments", "候选配方、评价指标与保留结果。");
  const retained = p.trials.find((trial) => trial.id === p.metrics.best_trial_id);
  const model = el("section", "retained-model"); const copy = el("div"); copy.append(el("span", "overline", "当前保留模型"), el("h2", "", retained ? "试验 " + String(retained.ordinal).padStart(2, "0") + " · " + retained.candidate.degree + " 阶配方" : "暂无保留模型"), el("p", "", retained ? "正则系数 α = " + numeric(retained.candidate.alpha) + "。保留状态依据既定晋升规则，不直接取所有候选中的最小原始误差。" : "快照中未提供保留状态。"));
  const metrics = el("dl", "retained-metrics"); metrics.append(metric("保留模型验证 MSE", numeric(p.metrics.best_validation_mse), "验证比较"), metric("终测 MSE", p.metrics.test_mse === null ? "尚未执行" : numeric(p.metrics.test_mse), "不以验证成绩替代"));
  model.append(copy, metrics); container.append(model);
  const tableSection = section("候选比较"); const wrap = el("div", "table-scroll"); wrap.tabIndex = 0; wrap.setAttribute("aria-label", "试验比较表，可横向滚动");
  const table = el("table", "trial-table"); const caption = el("caption", "sr-only", "所有已有试验的配方、误差和晋升结果"); const thead = el("thead"), hr = el("tr"); ["试验", "配方", "训练 MSE", "验证 MSE", "状态", "记录"].forEach((label) => { const th = el("th", "", label); th.scope = "col"; hr.append(th); }); thead.append(hr); const tbody = el("tbody");
  p.trials.forEach((trial) => {
    const tr = el("tr", trial.id === p.metrics.best_trial_id ? "is-retained" : "");
    tr.append(el("td", "trial-ordinal", String(trial.ordinal).padStart(2, "0")), el("td", "", trial.candidate.degree + " 阶 · α " + numeric(trial.candidate.alpha)), el("td", "tabular", numeric(trial.metrics?.training_mse)), el("td", "tabular", numeric(trial.metrics?.validation_mse)));
    const status = el("td"); status.append(badge(trial.status)); if (trial.id === p.metrics.best_trial_id) status.append(el("small", "retained-note", "当前保留")); const record = el("td"); record.append(viewButton(context, objectFor(context, trial.id), "详情 ↗")); tr.append(status, record); tbody.append(tr);
  }); table.append(caption, thead, tbody); wrap.append(table); tableSection.append(wrap); if (!p.trials.length) paragraph(tableSection, "暂无试验记录。", "empty-state");
  paragraph(tableSection, "左右滑动查看完整实验表", "mobile-table-hint");
  paragraph(tableSection, "“当次采用”记录那次判定；“当前保留”只标记当前模型。未晋升的候选保留其指标与原因，不从表中删除。", "detail-note"); container.append(tableSection);
  const charts = section("结果图"); const chartGrid = el("div", "figure-grid"); figures(chartGrid, context); charts.append(chartGrid); container.append(charts);
  const protocol = section("评价协议与复核"); const dl = el("dl", "protocol-grid"); field(dl, "数据集", text(p.dataset.dataset_id)); field(dl, "固定划分 · 训练 / 验证 / 测试", splits(p)); field(dl, "目标及单位", text(p.dataset.target) + " / " + text(p.dataset.target_unit)); field(dl, "快照来源", p.snapshot.source_campaign_id, true); protocol.append(dl, el("p", "detail-note", "自定义组成分组 holdout，与官方 Matbench 五折协议及排行榜指标不可直接比较。"));
  const rejected = p.trials.filter((trial) => trial.status === "rejected"); if (rejected.length) { const negative = el("div", "negative-results"); negative.append(el("h3", "", "未晋升候选的原始判定")); rejected.forEach((trial) => { const row = el("div"); row.append(el("strong", "", "试验 " + String(trial.ordinal).padStart(2, "0")), el("p", "", trial.decision_reason || "原记录未提供。"), viewButton(context, objectFor(context, trial.id), "阅读负结果 ↗")); negative.append(row); }); protocol.append(negative); } container.append(protocol);
}

export function renderKnowledge(container: HTMLElement, route: Route, context: PageContext): { items: ReturnType<typeof knowledgeItems>; boardContainer?: HTMLElement } {
  const all = knowledgeItems(context.objects, context.project); const selected = filterKnowledge(all, route.type, route.topics);
  const change = (patch: Partial<Route>) => context.navigate(knowledgeHash({...parseRoute(location.hash), ...patch}));
  const head = pageHead(container, "knowledge", "来源摘记、研究判断与引用记录。"); head.append(el("span", "page-count", all.length + " 项现有记录"));
  const toolbar = el("div", "knowledge-toolbar glass"); const tabs = el("div", "type-tabs"); tabs.setAttribute("role", "group"); tabs.setAttribute("aria-label", "资料类型");
  knowledgeTypes.forEach((type) => { const count = type === "全部" ? all.length : all.filter((item) => item.type === type).length; const button = action(type + " " + count, () => change({type}), "type-tab" + (route.type === type ? " active" : "")); button.dataset.type=type;button.setAttribute("aria-pressed", String(route.type === type)); tabs.append(button); });
  const lower = el("div", "knowledge-toolbar-bottom"); const topicPanel=el("div","topic-panel");
  const semantics=el("div","topic-semantics");semantics.append(el("span","","研究主题 · 可多选"),el("small","","主题间任一匹配（OR），与类型同时满足（AND）"));
  const chips=el("div","topic-chips");chips.setAttribute("role","group");chips.setAttribute("aria-label","研究主题，多选时任一匹配，并与资料类型同时满足");
  knowledgeTopics.forEach((topic)=>{
    const button=action(topic,()=>{const latest=parseRoute(location.hash);const topics=latest.topics.includes(topic)?latest.topics.filter((value)=>value!==topic):[...latest.topics,topic];change({topics});},"topic-chip"+(route.topics.includes(topic)?" active":""));
    button.dataset.topic=topic;button.setAttribute("aria-pressed",String(route.topics.includes(topic)));chips.append(button);
  });
  const clear=action("清除主题",()=>change({topics:[]}),"topic-clear");clear.dataset.clearTopics="true";clear.disabled=!route.topics.length;chips.append(clear);
  topicPanel.append(semantics,chips);
  const view = el("div", "segmented"); for (const [key, label] of [["cards", "▤ 资料卡片"], ["relations", "⌁ 关系视图"]] as const) { const button = action(label, () => change({view:key}), route.view === key ? "active" : ""); button.dataset.knowledgeView=key;button.setAttribute("aria-pressed", String(route.view === key)); view.append(button); }
  lower.append(topicPanel,view);toolbar.append(tabs,lower,el("p","filter-summary",selected.length+" 项匹配 · "+(route.topics.length?"已选 "+route.topics.join("、"):"未限主题")));container.append(toolbar);
  if (route.type === "研究记忆") {
    const empty = el("div", "knowledge-empty"); empty.append(el("span", "empty-symbol", "◇"), el("h2", "", "暂无已确认的研究记忆"), el("p", "", "当前只有研究判断及引用，尚未形成经确认、可跨课题复用的条件记忆。"), action("查看研究判断 ↗", () => change({type:"文献与证据",topics:[],view:"cards"}), "quiet-button")); container.append(empty); return { items:selected };
  }
  if (route.view === "relations") {
    const info = el("div", "relation-heading"); const scope = el("div", "segmented"); for (const [all, label] of [[false,"当前流程"],[true,"全景展开"]] as const) { const button = action(label, () => change({panorama:all}), route.panorama === all ? "active" : ""); button.setAttribute("aria-pressed", String(route.panorama === all)); scope.append(button); }
    info.append(el("p", "", route.type !== "全部" || route.topics.length ? "显示筛选记录及其引用。阶段顺序不代表支持或因果关系。" : "按研究流程排列。阶段顺序用于浏览，连线仅表示记录中的引用。"), scope); container.append(info);
    const boardContainer = el("div", "relation-board"); boardContainer.id = "relation-board"; const graph = el("div", "graph-surface"); graph.id = "graph"; graph.tabIndex = 0; graph.setAttribute("role","region"); graph.setAttribute("aria-label", "研究引用画布。拖动空白平移，Ctrl或⌘加滚轮缩放，Enter查看卡片。"); boardContainer.append(graph); container.append(boardContainer); return { items:selected, boardContainer };
  }
  if (!selected.length) { const empty = el("div", "knowledge-empty"); empty.append(el("h2", "", "暂无匹配记录"), el("p", "", "请调整资料类型或主题。")); container.append(empty); }
  else { const cards = el("div", "knowledge-grid"); selected.forEach((item) => cards.append(knowledgeCard(item, context.open, context.read))); container.append(cards); }
  paragraph(container, "分类按现有来源与记录整理。“类型图示”为本地图形，不是原文插图。", "page-boundary");
  return { items:selected };
}

function outputs(container: HTMLElement, context: PageContext): void {
  const p = context.project; pageHead(container, "outputs", "报告正文、结果图和复现附件。");
  const exportBar = el("section", "export-banner"); const copy = el("div"); copy.append(el("span", "overline", "研究交付"), el("h2", "", "报告与复现"), el("p", "", "下载 PDF 报告或复现附件，核对模型、数据和结果。")); const actions = el("div", "export-actions"); actions.append(action("下载研究报告 PDF ↓", () => context.download("pdf"), "action-button primary"), action("下载复现附件 ZIP ↓", () => context.download("reproduction"), "action-button")); exportBar.append(copy, actions); container.append(exportBar);
  const layout = el("div", "document-layout"); const toc = el("aside", "document-toc"); toc.setAttribute("aria-label", "报告章节目录"); toc.append(el("span", "overline", "报告目录")); const article = el("article", "report-document solid-panel"); article.append(el("div", "document-label", "论文式报告 · 冻结证据"), el("h2", "document-title", p.report.title), el("p", "document-intro", "报告来自当前快照，仅反映本地工程验证。未经同行评审或临床验证。"));
  p.report.sections.forEach((section, index) => {
    const id = "report-section-" + index; const button = action(String(index + 1).padStart(2,"0") + "  " + section.heading, () => document.getElementById(id)?.scrollIntoView({block:"start"}), "toc-item"); toc.append(button);
    const block = el("section", "report-section"); block.id = id; block.append(el("h3", "", section.heading)); section.paragraphs.forEach((value) => paragraph(block, value));
    const refs = el("div", "citation-list"); (section.claim_ids || []).forEach((ref) => { const object = objectFor(context, ref); if (object) refs.append(viewButton(context, object, "[" + ref + "]")); }); block.append(refs); article.append(block);
  });
  const graphSection = el("section", "report-section"); graphSection.id = "report-figures"; graphSection.append(el("h3", "", "实际结果图")); figures(graphSection, context); article.append(graphSection); toc.append(action("图表  实际结果图", () => graphSection.scrollIntoView({block:"start"}), "toc-item"));
  const sources = el("section", "report-section"); sources.id = "report-sources"; sources.append(el("h3", "", "来源与方法")); p.sources.forEach((source) => { const row = el("div", "reference-entry"); row.append(el("strong", "", "[" + source.id + "] " + source.title), el("p", "", source.description)); const url = safeUrl(source.url); if (url) { const link = el("a", "source-link", "原始来源 ↗"); link.href=url; link.target="_blank"; link.rel="noopener noreferrer"; row.append(link); } sources.append(row); }); article.append(sources); toc.append(action("来源  数据与方法", () => sources.scrollIntoView({block:"start"}), "toc-item"));
  const version = el("div", "toc-version"); version.append(el("span", "overline", "证据版本"), el("code", "mono", p.snapshot.sha256.slice(0,16) + "…"), el("small", "", date(p.snapshot.created_at))); toc.append(version); layout.append(toc, article); container.append(layout);
}

export function renderReader(container: HTMLElement, object: ResearchObject | undefined, context: PageContext): void {
  const top = el("div", "reader-top"); top.append(action("← 返回原位置", context.returnFromReader, "quiet-button"), el("span", "muted", object?.kind === "source" ? "资料记录阅读" : "完整记录阅读")); container.append(top);
  if (!object) { pageHead(container, "read", "这个对象不在当前证据快照中。"); return; }
  const layout = el("div", "document-layout reader-layout"); const toc = el("aside", "document-toc"); toc.setAttribute("aria-label", "阅读目录"); toc.append(el("span", "overline", "阅读目录")); const article = el("article", "reader-document solid-panel"); const meta = knowledgeItems(context.objects).find((item) => item.object.id === object.id);
  article.append(el("div", "document-label", (meta?.label || "原始研究记录") + " / " + object.rawId), el("h1", "document-title", object.title)); const content = el("div", "full-record"); renderDetails(content, object, context); article.append(content);
  content.querySelectorAll("h3").forEach((heading, index) => { heading.id = "record-heading-" + index; toc.append(action(heading.textContent || "内容", () => heading.scrollIntoView({block:"start"}), "toc-item")); });
  if (object.kind === "source" && meta?.type === "数据集") { const dataset = section("数据使用记录"); const dl = el("dl", "detail-dl"); field(dl,"数据集",text(context.project.dataset.dataset_id)); field(dl,"预测目标",text(context.project.dataset.target) + " / " + text(context.project.dataset.target_unit)); field(dl,"固定划分",splits(context.project)); field(dl,"许可",text(context.project.dataset.license)); field(dl,"输入特征",Array.isArray(context.project.dataset.feature_names) ? context.project.dataset.feature_names.map((value) => text(value)).join("、") : "未提供"); field(dl,"数据 SHA",text(context.project.dataset.data_sha256),true); dataset.append(dl); const limits = context.project.dataset.limitations; if (Array.isArray(limits)) limits.forEach((limit) => paragraph(dataset,text(limit),"detail-note")); dataset.id="dataset-usage"; article.append(dataset); toc.append(action("项目数据使用与边界",()=>dataset.scrollIntoView({block:"start"}),"toc-item")); }
  const related = context.objects.filter((item) => item.id !== object.id && (object.references.includes(item.rawId) || item.references.includes(object.rawId)));
  const relations = section("关联记录"); relations.id="reader-relations";
  if (!related.length) paragraph(relations,"暂无直接引用记录。","detail-note");
  related.forEach((item) => relations.append(viewButton(context,item,item.rawId + " · " + item.title)));
  article.append(relations); toc.append(action("关联记录",()=>relations.scrollIntoView({block:"start"}),"toc-item"));
  const version = el("div", "toc-version"); version.append(el("span", "overline", "当前证据快照"), el("code", "mono", context.project.snapshot.sha256.slice(0,16)+"…")); toc.append(version); layout.append(toc,article); container.append(layout);
}

export function renderPage(container: HTMLElement, route: Route, context: PageContext): ReturnType<typeof renderKnowledge> | undefined {
  container.replaceChildren();
  if (route.page === "overview") overview(container, context);
  else if (route.page === "research") return research(container, route, context);
  else if (route.page === "experiments") experiments(container, context);
  else if (route.page === "knowledge") return renderKnowledge(container, route, context);
  else if (route.page === "outputs") outputs(container, context);
  else renderReader(container, context.objects.find((object)=>object.id===route.id), context);
  return undefined;
}
