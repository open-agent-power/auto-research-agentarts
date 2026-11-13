/** Read CPU comparison observations only; no ranking, solving, or command submission. */
import { el, numeric } from "./dom";
import { createRetrievalReader, type RetrievalReaderContext } from "./retrieval-reader";

type Obj = Record<string, unknown>;
type ResultTable = (caption: string, headings: string[], values: string[][]) => HTMLElement;
const object = (value: unknown): Obj => !!value && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const objects = (value: unknown): Obj[] => Array.isArray(value) ? value.filter(item => !!item && typeof item === "object" && !Array.isArray(item)) as Obj[] : [];
const text = (value: unknown): string => typeof value === "string" && value.length ? value : "未记录";
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const signed = (value: unknown): string => finite(value) ? (value > 0 ? "+" : "") + numeric(value) : "未记录";
const milliseconds = (value: unknown): string => finite(value) ? numeric(value * 1000) : "未记录";
const splitNames: Record<string, string> = { test: "测试", dev: "开发", validation: "验证" };
const splitName = (value: unknown): string => splitNames[text(value)] ?? text(value);
const metricNames: Record<string, string> = { "ndcg@10": "nDCG@10", "mrr@10": "MRR@10", "recall@5": "Recall@5", "recall@10": "Recall@10", "recall@20": "Recall@20" };
const metricKeys = ["ndcg@10", "mrr@10", "recall@5", "recall@10", "recall@20"];

function disclosure(title: string, content: HTMLElement): HTMLElement {
  const panel = el("details", "cpu-result-details");
  panel.append(el("summary", "", title), content);
  return panel;
}

function retrievalSummary(observation: Obj, table: ResultTable, relevance = false): HTMLElement {
  const wrap = el("div", "project-cpu-results cpu-result-summary cpu-retrieval-summary");
  wrap.dataset.cpuFamily = relevance ? "relevance" : "retrieval";
  const scope = object(observation.scope), summary = object(observation.summary);
  wrap.append(el("h4", "", relevance ? "文档相关性检索 · 保存结果" : "引用文献检索 · 保存结果"),
    el("p", "", `语料 ${numeric(scope.document_count)} 篇；原查询 ${numeric(scope.query_count)} 条；本次固定对照 ${numeric(summary.query_pairs)} 条。`),
    el("p", "detail-note", relevance
      ? "正相关性 grade 按大于 0 做二元投影；此 nDCG 不是 canonical graded BEIR 成绩。相同查询/文档 ID 在 top20 截断前排除，缺失正例仍计入分母；不自动成为官方划分、隐藏评价或生成式 RAG。"
      : "引用标签表示被引用的文献，不判定支持、反驳或答案正确性；固定公开结果不等同隐藏评价，也不代表生成式 RAG。"));
  const paired = object(summary.paired_summary), splits = object(paired.splits);
  const appendSplit = (name: string, value: Obj): HTMLElement => {
    const arms = object(value.arms), baseline = object(arms[relevance ? "bm25" : "tfidf_cosine"]), candidate = object(arms[relevance ? "tfidf_cosine" : "bm25"]);
    const baselineMetrics = object(baseline.metrics), candidateMetrics = object(candidate.metrics), deltas = object(value.paired_candidate_minus_baseline);
    return table(`${splitName(name)}集 · 基线 ${numeric(baseline.queries)} / 候选 ${numeric(candidate.queries)} 条查询`,
      ["指标", relevance ? "BM25 基线" : "TF-IDF 基线", relevance ? "TF-IDF 候选" : "BM25 候选", "候选 − 基线", "上升 / 持平 / 下降查询"], metricKeys.map(key => {
        const pair = object(deltas[key]);
        return [metricNames[key], numeric(baselineMetrics[key]), numeric(candidateMetrics[key]), signed(pair.mean),
          `${numeric(pair.wins)} / ${numeric(pair.ties)} / ${numeric(pair.losses)}`];
      }));
  };
  if (Object.keys(splits).length) {
    wrap.append(el("p", "detail-note", "各指标为查询等权宏平均，取值 0–1、无量纲；正差值表示候选更高，负差值表示下降。"));
    const test = object(splits.test);
    if (Object.keys(test).length) wrap.append(appendSplit("test", test));
    const declines = metricKeys.filter(key => finite(object(object(test.paired_candidate_minus_baseline)[key]).mean)
      && (object(object(test.paired_candidate_minus_baseline)[key]).mean as number) < 0);
    if (declines.length) wrap.append(el("p", "cpu-result-caution", "测试集下降项：" + declines.map(key => `${metricNames[key]} ${signed(object(object(test.paired_candidate_minus_baseline)[key]).mean)}`).join("；") + "。保留指标取舍，不据其他指标上升自动采用候选。"));
    const remaining = el("div");
    for (const name of ["dev", "validation"]) {
      const value = object(splits[name]);
      if (Object.keys(value).length) remaining.append(appendSplit(name, value));
    }
    if (remaining.children.length) wrap.append(disclosure("查看开发集与验证集的全部指标", remaining));
  } else wrap.append(el("p", "detail-note", "此保存诊断仅带查询计数；宏指标见前序固定对照的结果，完整诊断见本行动 JSON。"));
  wrap.append(el("p", "cpu-result-caution", `需要核对的查询：${numeric(summary.adverse_queries)}。集合包括任一指标下降，或任一臂 Recall@20 未覆盖全部${relevance ? "正相关例" : "引用"}；不表示这些查询全部是候选恶化。`));
  if (relevance) wrap.append(el("p", "detail-note", "两臂为固定算法对照；仅凭该差异不能证明记忆的因果收益。完整原始 grade、查询/文档坐标、排名与未召回结果保留在本行动 JSON。"));
  return wrap;
}

function schedulingSummary(observation: Obj, table: ResultTable): HTMLElement {
  const wrap = el("div", "project-cpu-results cpu-result-summary cpu-scheduling-summary");
  wrap.dataset.cpuFamily = "scheduling";
  const scope = object(observation.scope), summary = object(observation.summary), bySplit = object(summary.by_split), cases = objects(summary.per_case);
  wrap.append(el("h4", "", "加权区间调度 · 保存计时与目标"),
    el("p", "", `固定合成任务 ${numeric(scope.case_count)} 个，共 ${numeric(scope.job_count)} 个作业。基线为逐项扫描 DP，候选为二分查找 DP。`),
    el("p", "detail-note", "这是已知精确动态规划的合成工程对照；本地计时差异不代表新算法发现，也不自动产生方法晋级。"));
  const countRows = ["dev", "validation", "test"].filter(name => Object.keys(object(bySplit[name])).length).map(name => {
    const counts = object(bySplit[name]);
    return [splitName(name), numeric(counts.cases), numeric(counts.faster), numeric(counts.tie), numeric(counts.slower)];
  });
  if (countRows.length) {
    const counts = table("按保存的候选计时分类", ["划分", "任务数", "更快", "持平", "更慢"], countRows);
    counts.classList.add("cpu-split-counts"); wrap.append(counts);
  }
  const caseTable = (caption: string, rows: Obj[]): HTMLElement => table(caption,
    ["任务", "作业数", "扫描基线（ms）", "二分候选（ms）", "候选 − 基线（ms）", "基线 / 候选", "目标值 / 完整排程"], rows.map(row => {
      const times = object(row.median_seconds), difference = row.candidate_minus_baseline_seconds;
      const equality = row.exact_schedule_equal === true ? "相同" : row.exact_schedule_equal === false ? "不同" : "未记录";
      return [text(row.case_id), numeric(row.jobs), milliseconds(times.quadratic_scan_dp), milliseconds(times.binary_search_dp),
        finite(difference) ? signed(difference * 1000) : "未记录", finite(row.speedup_baseline_over_candidate) ? numeric(row.speedup_baseline_over_candidate) + "×" : "未记录",
        `${numeric(row.objective)} / ${equality}`];
    }));
  const adverse = cases.filter(row => row.candidate_timing === "slower" || row.candidate_timing === "tie");
  if (adverse.length) {
    wrap.append(el("p", "cpu-result-caution", `候选更慢或持平的保存任务：${numeric(adverse.length)} 个。下表完整保留这些任务。`),
      caseTable("慢例与持平例 · 原保存中位计时", adverse));
  } else wrap.append(el("p", "detail-note", cases.length ? "本观察的逐任务记录没有标为更慢或持平的任务；缺失的计时分类不能算作更快。" : "此观察没有逐任务计时，不能据此判断是否存在慢例。"));
  if (cases.length) wrap.append(disclosure(`查看全部 ${numeric(cases.length)} 个保存任务`, caseTable("全部保存任务 · 保持原顺序", cases)));
  wrap.append(el("p", "detail-note", "计时单位为毫秒；比值为基线时间 / 候选时间，小于 1 表示候选较慢。目标值为合成权重总和；“相同”仅指两法保存的完整排程相同，不是新算出的最优性证明。"));
  return wrap;
}

export function cpuResultSummary(observations: Obj[], table: ResultTable, context?: RetrievalReaderContext): HTMLElement | null {
  const retrieval = observations.find(item => item.kind === "citation_retrieval_pair" || item.kind === "saved_retrieval_error_audit");
  if (retrieval) {
    const summary = retrievalSummary(retrieval, table), reader = context ? createRetrievalReader(context, table) : null;
    if (reader) summary.append(reader);
    return summary;
  }
  const relevance = observations.find(item => item.kind === "relevance_retrieval_pair" || item.kind === "saved_relevance_error_audit");
  if (relevance) return retrievalSummary(relevance, table, true);
  const scheduling = observations.find(item => item.kind === "weighted_interval_fixed_pair" || item.kind === "saved_weighted_interval_audit");
  return scheduling ? schedulingSummary(scheduling, table) : null;
}
