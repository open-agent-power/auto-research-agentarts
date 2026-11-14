/** Read bounded, already-saved query evidence only after an explicit user request. */
import { el, field, numeric } from "./dom";

type Obj = Record<string, unknown>;
type ResultTable = (caption: string, headings: string[], values: string[][]) => HTMLElement;
export type RetrievalReaderContext = { project: Obj; action: Obj };
const object = (value: unknown): Obj => !!value && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const records = (value: unknown): Obj[] => Array.isArray(value) ? value.map(object) : [];
const text = (value: unknown): string => typeof value === "string" && value.length ? value : "未记录";
const boundedText = (value: unknown, maximum: number): value is string => typeof value === "string" && Array.from(value).length <= maximum;
const strings = (value: unknown): string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
const sha = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const identifier = (value: unknown): value is string => typeof value === "string" && /^[A-Za-z0-9_.:-]{1,120}$/.test(value);
const natural = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
const splitNames: Record<string, string> = { dev: "开发", validation: "验证", test: "测试" };
const categories: Record<string, string> = { metric_loss: "存在指标下降", no_metric_loss_both_incomplete: "无指标下降，两臂召回均不全", no_metric_loss_baseline_only_incomplete: "无指标下降，仅基线召回不全", no_metric_loss_other: "无指标下降，其他保存召回不足情况" };
const metricNames: Record<string, string> = { "ndcg@10": "nDCG@10", "mrr@10": "MRR@10", "recall@5": "Recall@5", "recall@10": "Recall@10", "recall@20": "Recall@20" };
const methods: Record<string, string> = { tfidf_cosine: "TF-IDF 基线", bm25: "BM25 候选" };
const relevanceMethods: Record<string, string> = { bm25: "BM25 基线", tfidf_cosine: "TF-IDF 候选" };
const relevancePrimary = "research.relevance-fixed-pair", relevanceAudit = "research.relevance-saved-error-audit";
const relevanceContract: Obj = { id: "relevance-retrieval-fixed-pair-v1", qrels_semantics: "positive_relevance_binary_projection",
  baseline: "bm25", candidate: "tfidf_cosine", ignore_identical_ids: true, missing_document_policy: "retain_in_denominator" };
const exactKeys = (value: Obj, keys: string[]): boolean => Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const grade = (value: unknown): value is number => typeof value === "number" && Number.isInteger(value) && (value === 1 || value === 2);
const validMetrics = (value: unknown): boolean => {
  const entry = object(value);
  return exactKeys(entry, Object.keys(metricNames)) && Object.values(entry).every(number => typeof number === "number" && Number.isFinite(number) && number >= 0 && number <= 1);
};

function provenance(binding: Obj): HTMLElement {
  const panel = el("details", "retrieval-reader-provenance"), values = el("dl", "detail-dl");
  panel.append(el("summary", "", "核对原行动、快照与来源"), values);
  for (const [key, label] of [["action_id", "当前行动"], ["result_sha256", "行动结果 SHA"], ["primary_action_id", "原检索行动"],
    ["primary_result_sha256", "原检索结果 SHA"], ["source_snapshot_sha256", "原输入 SHA"], ["snapshot_ref", "项目快照"]]) field(values, label, text(binding[key]), true);
  return panel;
}

export function createRetrievalReader(context: RetrievalReaderContext, table: ResultTable, family: "citation" | "relevance" = "citation"): HTMLElement | null {
  const { project, action } = context;
  const relevance = family === "relevance", actionIsRelevance = action.command === relevancePrimary || action.command === relevanceAudit;
  if (relevance !== actionIsRelevance || relevance && (project.primary_method !== relevancePrimary
      || object(project.domain_scope).contract !== relevanceContract.id || object(project.domain_scope).qrels_semantics !== relevanceContract.qrels_semantics)) return null;
  if (action.status !== "completed" || !identifier(project.id) || !identifier(action.id) || !sha(project.snapshot_ref)
      || !sha(action.result_sha256) || !sha(action.source_snapshot_sha256)) return null;
  const armMethods = relevance ? relevanceMethods : methods, methodOrder = Object.keys(armMethods);
  const expected = { project_id: project.id, snapshot_ref: project.snapshot_ref, action_id: action.id,
    result_sha256: action.result_sha256, source_snapshot_sha256: action.source_snapshot_sha256 };
  const reader = el("section", "retrieval-adverse-reader"); reader.dataset.actionId = action.id;
  if (relevance) reader.dataset.retrievalFamily = "relevance";
  const heading = el("h4", "", "不利查询原记录"), notice = el("p", "detail-note", relevance
    ? "按需读取已保存的相关性查询、排名和原文，不重新检索或评分，也不补算逐文档分数。原 grade 1/2 保留，指标按正相关例做二元投影；缺失正例仍计入召回分母。相同查询/文档 ID 已在 top20 截断前排除；程序划分与公开标签不构成封存盲测，固定算法差异不能证明记忆的因果收益。"
    : "按需读取已有查询、排名和原文定位，不重新检索或评分。没有保存逐文档检索分数；引用标签不表示支持、反驳或答案正确性。"),
    load = el("button", "quiet-button", "查看不利查询原记录"), status = el("p", "retrieval-reader-status"), pageContent = el("div", "retrieval-reader-page"), detail = el("section", "retrieval-query-detail");
  load.type = "button"; load.dataset.readerControl = "load"; heading.tabIndex = -1; detail.tabIndex = -1; detail.hidden = true;
  status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
  reader.append(heading, notice, load, status, pageContent, detail);
  let busy = false, generation = 0, offset = 0, loaded = false, lastTrigger: HTMLButtonElement | null = null, listTop = 0;
  let list: HTMLOListElement | null = null;
  const controls = (): void => { for (const button of reader.querySelectorAll<HTMLButtonElement>("button[data-reader-control]")) button.disabled = busy || button.dataset.unavailable === "true"; };
  const setBusy = (value: boolean): void => { busy = value; reader.setAttribute("aria-busy", String(value)); controls(); };
  const button = (label: string, name: string, callback: () => void): HTMLButtonElement => {
    const node = el("button", "quiet-button", label); node.type = "button"; node.dataset.readerControl = name; node.addEventListener("click", callback); return node;
  };
  function validateBinding(value: Obj): Obj {
    if (relevance) {
      const contract = object(value.contract);
      if (!exactKeys(contract, Object.keys(relevanceContract)) || Object.entries(relevanceContract).some(([key, expected]) => contract[key] !== expected)) throw Error("保存记录的相关性合同或算法角色不一致，未显示内容。");
    } else if (value.contract !== undefined) throw Error("相关性合同不能替换当前引用检索记录，未显示内容。");
    const binding = object(value.binding);
    if (Object.entries(expected).some(([key, original]) => binding[key] !== original)) throw Error("读取结果与当前项目、行动或保存快照不一致，请刷新项目后再核对。");
    const primary = records(project.actions).find(item => item.id === binding.primary_action_id);
    if (!primary || primary.status !== "completed" || primary.result_sha256 !== binding.primary_result_sha256
        || primary.source_snapshot_sha256 !== expected.source_snapshot_sha256 || !sha(binding.primary_result_sha256)) throw Error("原检索行动与当前项目中的保存记录不一致。");
    if (relevance && (primary.command !== relevancePrimary || (action.command === relevancePrimary ? primary.id !== action.id : primary.id === action.id))) throw Error("相关性原检索行动与当前行动类型不一致。");
    return binding;
  }
  async function read(path: string, parameters: Record<string, string>): Promise<Obj> {
    const query = new URLSearchParams({ project_id: expected.project_id, snapshot_ref: expected.snapshot_ref, action_id: expected.action_id, ...parameters });
    const response = await fetch(path + "?" + query, { method: "GET", cache: "no-store", credentials: "same-origin", signal: AbortSignal.timeout(15000) });
    const length = Number(response.headers.get("Content-Length"));
    if (Number.isFinite(length) && length > 1048576) throw Error("保存记录超过有界读取大小，未显示内容。");
    if (!response.ok) throw Error(response.status === 409 ? "项目快照或服务已变化，请刷新项目再核对（HTTP 409）。" : `原记录读取失败（HTTP ${response.status}），没有执行研究。`);
    const raw = await response.text();
    if (new TextEncoder().encode(raw).length > 1048576) throw Error("保存记录超过有界读取大小，未显示内容。");
    let value: Obj;
    try { value = object(JSON.parse(raw)); } catch { throw Error("保存记录响应不是有效 JSON。"); }
    validateBinding(value); return value;
  }
  function renderPage(value: Obj, requestedOffset: number): void {
    const pagination = object(value.pagination), counts = object(value.counts), rows = records(value.items), total = pagination.total;
    if (value.schema_version !== (relevance ? "saved-relevance-adverse-page-v1" : "saved-retrieval-adverse-page-v1") || pagination.offset !== requestedOffset || pagination.limit !== 25
        || !natural(total) || total > (relevance ? 2000 : 1200) || counts.total !== total || !Array.isArray(value.items)
        || rows.length !== Math.min(25, Math.max(0, total - requestedOffset))
        || pagination.next_offset !== (requestedOffset + rows.length < total ? requestedOffset + rows.length : null)
        || Object.keys(categories).some(key => !natural(counts[key])) || !natural(counts.no_metric_loss_total)
        || Number(counts.metric_loss) + Number(counts.no_metric_loss_total) !== total
        || Number(counts.no_metric_loss_both_incomplete) + Number(counts.no_metric_loss_baseline_only_incomplete) + Number(counts.no_metric_loss_other) !== counts.no_metric_loss_total
        || rows.some(row => !identifier(row.query_id) || !Object.hasOwn(splitNames, text(row.split)) || !Object.hasOwn(categories, text(row.category))
          || relevance && (!exactKeys(object(row.metrics), methodOrder) || methodOrder.some(method => !validMetrics(object(row.metrics)[method]))))) throw Error("保存查询分页或分类结构不完整，未替换原页面。");
    offset = requestedOffset; reader.dataset.offset = String(offset); loaded = true;
    const summary = el("p", "retrieval-reader-counts", `共 ${numeric(total)} 条需核对查询：${numeric(counts.metric_loss)} 条存在指标下降；${numeric(counts.no_metric_loss_total)} 条无指标下降但召回不全（两臂 ${numeric(counts.no_metric_loss_both_incomplete)}、仅基线 ${numeric(counts.no_metric_loss_baseline_only_incomplete)}、其他 ${numeric(counts.no_metric_loss_other)}）。`);
    list = el("ol", "retrieval-adverse-list"); list.start = offset + 1; list.tabIndex = 0; list.setAttribute("aria-label", "本页不利查询，可上下滚动");
    for (const row of rows) {
      const item = el("li", "retrieval-adverse-item"), identity = el("div", "retrieval-adverse-identity"), open = button("阅读查询 " + text(row.query_id), "query", () => { void loadQuery(row, open); });
      item.dataset.queryId = text(row.query_id); item.dataset.split = text(row.split); open.dataset.queryId = text(row.query_id); open.dataset.split = text(row.split);
      identity.append(el("strong", "", "query " + text(row.query_id)), el("span", "", splitNames[text(row.split)] + "集"));
      const losses = strings(row.metric_losses);
      item.append(identity, el("p", "", categories[text(row.category)] + (losses.length ? "；下降指标：" + losses.map(key => metricNames[key] ?? key).join("、") : "")), open); list.append(item);
    }
    const navigation = el("div", "retrieval-reader-pagination"), previous = button("上一页", "previous", () => { void loadPage(Math.max(0, offset - 25)); }),
      next = button("下一页", "next", () => { if (natural(pagination.next_offset)) void loadPage(pagination.next_offset); });
    previous.dataset.unavailable = String(offset === 0); next.dataset.unavailable = String(pagination.next_offset === null);
    navigation.append(previous, el("span", "", total ? `第 ${numeric(offset + 1)}–${numeric(offset + rows.length)} 条 / 共 ${numeric(total)} 条` : "没有保存的不利查询"), next);
    pageContent.replaceChildren(summary, list, navigation, provenance(object(value.binding))); controls();
  }
  function renderQuery(value: Obj, row: Obj): void {
    const query = object(value.query), arms = records(value.arms);
    if (value.schema_version !== (relevance ? "saved-relevance-query-v1" : "saved-retrieval-query-v1") || query.id !== row.query_id || query.split !== row.split || value.category !== row.category
        || !natural(query.line) || query.line === 0 || !sha(query.source_sha256) || !boundedText(query.text, 4096)
        || arms.length !== 2 || new Set(arms.map(arm => arm.method)).size !== 2 || arms.some(arm => !Object.hasOwn(armMethods, text(arm.method))
          || !Array.isArray(arm.documents) || records(arm.documents).length > 20 || records(arm.documents).some((doc, index) => doc.rank !== index + 1 || !identifier(doc.id)
            || !natural(doc.line) || doc.line === 0 || !sha(doc.source_sha256) || !boundedText(doc.title, 512) || !boundedText(doc.text, 4096)))) throw Error("保存查询或原文定位不完整，未显示此查询。");
    if (relevance) {
      const invalid = arms.some((arm, index) => {
        const qrel = object(arm.qrel), ids = strings(qrel.doc_ids), missing = strings(qrel.missing_doc_ids), grades = object(qrel.grades), documents = records(arm.documents);
        return arm.method !== methodOrder[index] || !validMetrics(arm.metrics)
          || Object.keys(metricNames).some(key => object(arm.metrics)[key] !== object(object(row.metrics)[text(arm.method)])[key])
          || !exactKeys(qrel, ["doc_ids", "source_sha256", "role", "grades", "missing_doc_ids"])
          || !Array.isArray(qrel.doc_ids) || ids.length !== qrel.doc_ids.length || !ids.length || new Set(ids).size !== ids.length || ids.some(id => !identifier(id))
          || !sha(qrel.source_sha256) || qrel.role !== (query.split === "test" ? "test_qrels" : "train_qrels")
          || !exactKeys(grades, ids) || Object.values(grades).some(value => !grade(value))
          || !Array.isArray(qrel.missing_doc_ids) || missing.length !== qrel.missing_doc_ids.length || new Set(missing).size !== missing.length || missing.some(id => !ids.includes(id))
          || new Set(documents.map(doc => doc.id)).size !== documents.length
          || documents.some(doc => doc.id === query.id || missing.includes(text(doc.id))
            || !(doc.original_grade === null || grade(doc.original_grade)) || doc.original_grade !== (Object.hasOwn(grades, text(doc.id)) ? grades[text(doc.id)] : null)
            || doc.relevant !== grade(doc.original_grade) || typeof doc.title_truncated !== "boolean" || typeof doc.text_truncated !== "boolean");
      });
      if (invalid || typeof query.text_truncated !== "boolean" || JSON.stringify(object(arms[0].qrel)) !== JSON.stringify(object(arms[1].qrel))) throw Error("保存相关性 grade、缺失正例、算法角色或指标绑定不完整，未显示此查询。");
    }
    const heading = el("h4", "", `${splitNames[text(query.split)]}集 · query ${text(query.id)}`), back = button("返回查询列表", "back", () => {
      detail.hidden = true; if (list) list.scrollTop = listTop;
      if (lastTrigger?.isConnected) lastTrigger.focus(); else { heading.blur(); pageContent.scrollIntoView({ block: "start" }); reader.querySelector<HTMLButtonElement>("button[data-reader-control=load]")?.focus(); }
    });
    const queryText = el("p", "retrieval-query-text", query.text), location = el("p", "retrieval-reader-location", `原 queries.jsonl 第 ${numeric(query.line)} 行 · SHA ${text(query.source_sha256)}`);
    const byMethod = Object.fromEntries(arms.map(arm => [text(arm.method), object(arm.metrics)]));
    const metrics = table("当前查询的保存指标 · 无量纲", ["指标", armMethods[methodOrder[0]], armMethods[methodOrder[1]]], Object.keys(metricNames).map(key => [metricNames[key], numeric(byMethod[methodOrder[0]][key]), numeric(byMethod[methodOrder[1]][key])]));
    metrics.classList.add("retrieval-query-metrics"); metrics.tabIndex = 0; metrics.setAttribute("aria-label", "当前查询保存指标，可左右滚动");
    const panels = el("div", "retrieval-query-arms");
    for (const method of methodOrder) {
      const arm = arms.find(item => item.method === method)!, section = el("section", "retrieval-query-arm"), qrel = object(arm.qrel), documents = records(arm.documents), citations = strings(qrel.doc_ids);
      section.dataset.method = method;
      const grades = object(qrel.grades), missing = strings(qrel.missing_doc_ids);
      section.append(el("h5", "", armMethods[method]), el("p", relevance ? "retrieval-reader-location" : "detail-note", relevance
        ? `原保存顺序 ${numeric(documents.length)} 篇；原正相关文档与 grade：${citations.map(id => `${id} (grade ${numeric(grades[id])})`).join("、")}。原 grade 保留，指标按 grade>0 做二元投影。`
        : `原保存顺序 ${numeric(documents.length)} 篇；原引用文档：${citations.join("、") || "未记录"}。`));
      if (relevance && missing.length) section.append(el("p", "retrieval-missing-positives retrieval-reader-location", `语料中缺失的正例文档：${missing.join("、")}。保留在召回分母；无可展示的原文或排名，不补造内容。`));
      const originals = el("ol", "retrieval-ranked-documents"); originals.tabIndex = 0; originals.setAttribute("aria-label", armMethods[method] + "保存排名，可上下滚动");
      for (const doc of documents) {
        const item = el("li", "retrieval-ranked-document"), full = el("details"), original = el("summary", "", `${numeric(doc.rank)}. ${text(doc.title)}`);
        item.dataset.documentId = text(doc.id); item.dataset.rank = String(doc.rank);
        full.append(original, el("p", "retrieval-document-text", doc.text as string));
        if (doc.title_truncated === true || doc.text_truncated === true) full.append(el("p", "detail-note", "此处标题或原文已截断展示；原输入仍完整保留，定位与身份不变。"));
        const marker = relevance ? grade(doc.original_grade) ? `原相关性 grade ${numeric(doc.original_grade)}（正相关标签）` : "原 qrels 未标注（不等于确证无关或 grade 0）"
          : doc.relevant === true ? "原引用标签命中" : doc.relevant === false ? "不在原引用标签中" : "原引用标记未记录";
        item.append(full, el("p", "retrieval-reader-location", `文档 ${text(doc.id)} · 原 corpus.jsonl 第 ${numeric(doc.line)} 行 · ${marker}`), el("p", "retrieval-reader-location", "SHA " + text(doc.source_sha256))); originals.append(item);
      }
      section.append(originals, el("p", "retrieval-reader-location", "原 qrels SHA " + text(qrel.source_sha256))); panels.append(section);
    }
    detail.dataset.queryId = text(query.id); detail.dataset.split = text(query.split); detail.hidden = false;
    detail.replaceChildren(heading, back, el("p", "retrieval-query-category", categories[text(value.category)]), queryText, location);
    if (query.text_truncated === true) detail.append(el("p", "detail-note", "查询文本已截断展示，原输入与定位保持。"));
    detail.append(metrics, el("p", "detail-note", relevance
      ? "以下仅展示原保存序位及原相关性 grade，不提供或补算逐文档检索分数。原 qrels 未标注不等于确证无关或 grade 0；缺失正例保留在分母，不补造文档。"
      : "以下仅展示原保存序位及引用标签，不提供或补算逐文档检索分数；未列入引用不等于文献与查询无关。"), panels, provenance(object(value.binding)));
  }
  async function loadPage(nextOffset: number): Promise<void> {
    if (busy || !reader.isConnected) return;
    const token = ++generation; setBusy(true); status.classList.remove("notice"); status.textContent = "正在读取原保存查询列表…";
    try {
      const value = await read("/api/project/retrieval-adverse.json", { offset: String(nextOffset), limit: "25" });
      if (!reader.isConnected || token !== generation) return;
      renderPage(value, nextOffset); status.textContent = "已读取原保存列表；选择查询按需核对原文与定位。";
    } catch (error) {
      if (!reader.isConnected || token !== generation) return;
      status.classList.add("notice"); status.textContent = (error instanceof Error ? error.message : "读取失败。") + (loaded ? " 当前仍保留上次核对的分页，可重新读取。" : " 可再次点击读取；不会执行研究。");
    } finally { if (token === generation) setBusy(false); }
  }
  async function loadQuery(row: Obj, trigger: HTMLButtonElement): Promise<void> {
    if (busy || !reader.isConnected) return;
    const token = ++generation; lastTrigger = trigger; listTop = list?.scrollTop ?? 0;
    setBusy(true); detail.hidden = true; detail.replaceChildren(); status.classList.remove("notice"); status.textContent = `正在读取 query ${text(row.query_id)} 的保存排名与原文…`;
    try {
      const value = await read("/api/project/retrieval-query.json", { query_id: text(row.query_id), split: text(row.split) });
      if (!reader.isConnected || token !== generation) return;
      renderQuery(value, row); status.textContent = `已核对 query ${text(row.query_id)} 的原保存记录，没有重新检索或评分。`; detail.focus({ preventScroll: true }); detail.scrollIntoView({ block: "start" });
    } catch (error) {
      if (!reader.isConnected || token !== generation) return;
      status.classList.add("notice"); status.textContent = (error instanceof Error ? error.message : "读取失败。") + " 可再次选择原查询，不会创建新研究请求。";
    } finally { if (token === generation) setBusy(false); }
  }
  load.addEventListener("click", () => { void loadPage(offset); });
  return reader;
}
