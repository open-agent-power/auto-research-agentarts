/** Explicit reader for a fixed, external saved study; never imports it into a project. */
import { el, numeric, text } from "./dom";
import { createSavedCapsule } from "./saved-capsule";
import { createHypothesisSource } from "./hypothesis-source";
type Obj = Record<string, unknown>;
const obj = (value: unknown): Obj => value && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const list = (value: unknown): Obj[] => Array.isArray(value) ? value.map(obj) : [];
const labels: Record<string, string> = { generation: "生成", generate: "生成", kernel_warmup: "预热", warmup: "预热", kernel_timed: "计时", timed: "计时", kernel_correctness: "正确性核对", correctness: "正确性核对", kernel_total: "内核总调用", fenwick: "参考算法", oracle: "参考算法", brute: "穷举核对", bruteforce: "穷举核对", audit: "保存审计", saved_audit_attempts: "保存审计次数", primary: "主运行", primary_attempts: "主运行次数", scan_comparisons: "扫描比较", exhaustive_subsets: "穷举子集", maximum_elapsed_seconds: "最长秒数", research_concurrency: "并发上限", estimator_fits: "估计器拟合", model_sends: "模型发送", external_API: "外部 API", source_extraction: "来源提取" };
const projectBudgetLabels: Record<string, string> = { lineage_ref: "预算归属", historical_spend_cny: "历史费用（元）", historical_request_counts: "历史请求数", historical_unknowns_resolved: "历史未知项已核对", cash_settlement: "现金结算状态", existing_cash_cap_cny: "既有现金上限（元）", model_requests_allowed: "模型请求上限", new_model_requests: "原记录的新模型请求", model_requests_reserved: "原记录的模型预留", new_fits: "原记录的新拟合", local_tool_call_limit: "本地工具调用上限", evidence_read_limit: "资料读取上限" };
function section(title: string): HTMLElement { const node = el("section", "content-section saved-study-section"); node.append(el("h2", "section-title", title)); return node; }
function savedValue(value: unknown): string {
  if (value === null || value === undefined) return "未知 / 未记录";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "object") return JSON.stringify(value);
  return text(value, "未知 / 未记录");
}
function pairs(value: unknown, names: Record<string, string> = labels): HTMLElement {
  const dl = el("dl", "saved-study-pairs");
  for (const [key, entry] of Object.entries(obj(value))) { const row = el("div"); row.append(el("dt", "", names[key] || key), el("dd", "", savedValue(entry))); dl.append(row); }
  if (!dl.childElementCount) dl.append(el("p", "", "未记录"));
  return dl;
}
function drawProject(target: HTMLElement, project: Obj): void {
  const status = text(project.status, "unknown"), states: Record<string, string> = { no_active: "没有记录活动项目", unavailable: "项目原记录不可用", unknown: "项目状态未知", integrity_error: "项目记录完整性错误", partial: "项目记录不完整" };
  target.replaceChildren(el("h3", "", "当前项目 · 原记录"));
  if (status !== "available" && status !== "partial") { target.append(el("p", "", states[status] || "项目状态未知：" + status), el("p", "detail-note", text(project.reason, "未提供原因。"))); return; }
  if (status === "partial") target.append(el("p", "detail-note", "项目记录不完整：" + text(project.reason)));
  target.append(el("p", "", "以下为当前项目原记录，与独立研究分开；不从行动推算调用数或剩余额度。"));
  const facts = el("dl", "saved-study-identity");
  for (const [label, value] of [["项目 ID", project.project_id], ["状态版本", project.state_version], ["原代码身份", obj(project.producer).code_identity]] as const) { const row = el("div"); row.append(el("dt", "", label), el("dd", "", savedValue(value))); facts.append(row); }
  target.append(facts, el("p", "detail-note", "原预算是保存时的字段，不等于重新计算的已用或预留额度。费用和 token 未独立核实；缺失值为未知。"));
  const budget = el("details"); budget.open = true; budget.append(el("summary", "", "项目保存的预算字段"), pairs(project.stored_budget, projectBudgetLabels)); target.append(budget);
  const actions = list(project.stored_actions), details = el("details"), actionsRead = Array.isArray(project.stored_actions); details.open = true; details.append(el("summary", "", "项目保存的行动（" + (actionsRead ? actions.length : "未读取") + "）"));
  if (actionsRead && !actions.length) details.append(el("p", "detail-note", "原行动表没有记录。"));
  for (const action of actions) { const entry = el("div", "saved-study-reference"); entry.append(el("strong", "", text(action.id)), el("p", "", "状态：" + text(action.status) + " · 方法：" + text(obj(action.method).id, text(action.command, "未记录"))), el("p", "", "原请求：" + text(action.request_id)), el("p", "", "行动原代码身份：" + text(action.producer_code_identity, "未记录"))); details.append(entry); }
  target.append(details);
}
function draw(host: HTMLElement, data: Obj, project: Obj): void {
  const status = text(data.status, "unknown");
  const stateLabels: Record<string, string> = { completed: "已完成的保存记录", unavailable: "原始记录不可用", unknown: "状态未知", failed: "原研究失败", integrity_error: "完整性核对失败" };
  host.replaceChildren();
  const intro = section("独立研究 · 保存记录");
  intro.append(el("p", "saved-study-status", stateLabels[status] || "状态未知：" + status),
    el("p", "", "这是一项独立研究的保存引用，不属于当前项目；阅读不会导入、执行研究或改变项目预算。"));
  if (status !== "completed") { intro.append(el("p", "detail-note", text(data.reason, "未提供原因；请保留原状态并检查原始记录。"))); host.append(intro, createSavedCapsule()); const current = section("当前项目 · 原记录"); drawProject(current, project); host.append(current); return; }
  const summary = obj(data.saved_summary), cases = list(summary.performance_cases);
  intro.append(el("h3", "", "原假设未获支持"), el("p", "", "在预先指定的 12 个小规模案例中，阈值策略均慢于固定二分查找；保存的总体时间比为 " + numeric(summary.primary_policy_over_binary, 15) + "（大于 1 表示更慢）。"),
    el("p", "detail-note", "该结论限于保存的计时与原协议；本页没有重新计算、运行算法或验证更广泛的科学结论。"),
    createHypothesisSource(data.hypothesis_source, project)); host.append(intro, createSavedCapsule());
  const accounting = section("额度与归属"), columns = el("div", "saved-study-columns"), original = el("div"), current = el("div");
  original.append(el("h3", "", "独立研究"), el("p", "", "以下为原研究的计划和记录消耗，不计入当前项目。开发成本与 token 未知。"));
  const used = el("details"); used.open = true; used.append(el("summary", "", "实际消耗"), pairs(data.actual_spent));
  const planned = el("details"); planned.append(el("summary", "", "计划额度"), pairs(data.planned_budget)); original.append(used, planned);
  drawProject(current, project);
  columns.append(original, current); accounting.append(columns); host.append(accounting);
  const results = section("27 个保存案例"), tableWrap = el("div", "saved-study-table-wrap"), table = el("table", "saved-study-table"), head = el("thead"), hr = el("tr");
  for (const heading of ["案例", "规模 n", "种子", "阈值 / 二分", "结果", "原耗时与预热"]) hr.append(el("th", "", heading)); head.append(hr); table.append(head);
  const tbody = el("tbody"); for (const item of cases) {
    const tr = el("tr");
    for (const value of [text(item.case_id), text(item.n), text(item.seed), text(item.policy_over_binary), item.outcome === "slower" ? "较慢" : item.outcome === "faster" ? "较快" : text(item.outcome)]) tr.append(el("td", "", value));
    const cell = el("td"), detail = el("details"), medians = obj(item.median_ns), fields = el("dl", "saved-study-pairs saved-study-case-detail");
    for (const [label, value] of [["固定二分中位数（ns）", medians.fixed_binary], ["固定扫描中位数（ns）", medians.fixed_scan], ["阈值策略中位数（ns）", medians.threshold32]] as const) {
      const row = el("div"); row.append(el("dt", "", label), el("dd", "", text(value, "未记录"))); fields.append(row);
    }
    const invalid = Array.isArray(item.invalid_warmups) ? JSON.stringify(item.invalid_warmups) : "未记录";
    const row = el("div"); row.append(el("dt", "", "无效预热（原记录）"), el("dd", "", invalid)); fields.append(row);
    detail.append(el("summary", "", "查看"), fields); cell.append(detail); tr.append(cell); tbody.append(tr);
  } table.append(tbody); tableWrap.append(table); results.append(el("p", "detail-note", "比值按保存摘要显示；表格可横向滚动，每个案例可展开原耗时与预热记录。"), tableWrap); host.append(results);
  const identity = section("来源与原始记录"), info = el("dl", "saved-study-identity");
  for (const [label, value] of [["研究", data.study_id], ["原声明 SHA-256", data.claim_sha256], ["原生产源码 commit", data.source_commit], ["原运行环境身份", data.original_producer_runtime_identity]] as const) { const row = el("div"); row.append(el("dt", "", label), el("dd", "", text(value))); info.append(row); }
  identity.append(info, el("p", "detail-note", "原生产源码和运行环境身份属于这项独立研究，不是当前产品的版本。以下是原文件路径和校验值；本页不下载或展开原始大文件。哈希及本地审查不等于来源认证。"));
  const record = el("details"); record.append(el("summary", "", "原请求与保存审计"), pairs(data.request_ids), pairs(data.saved_audit)); identity.append(record);
  const refs = el("details"); refs.append(el("summary", "", "查看全部原文件引用（" + Object.keys(obj(data.raw_references)).length + "）"));
  for (const [name, raw] of Object.entries(obj(data.raw_references))) { const reference = obj(raw), block = el("div", "saved-study-reference"); block.append(el("strong", "", name), el("p", "", text(reference.path)), el("p", "", "SHA-256 " + text(reference.sha256) + " · " + text(reference.bytes) + " bytes")); refs.append(block); }
  identity.append(refs); const limits = Array.isArray(data.limitations) ? data.limitations : []; if (limits.length) { const detail = el("details"); detail.append(el("summary", "", "原记录的限制")); const ul = el("ul"); for (const limit of limits) ul.append(el("li", "", text(limit))); detail.append(ul); identity.append(detail); } host.append(identity);
}
export function createSavedStudy(): { element: HTMLElement; activate(): void; deactivate(): void } {
  const element = el("section", "project-workspace-page saved-study-page"), header = el("header", "page-heading"), copy = el("div"), body = el("div", "project-workspace-sections");
  copy.append(el("h1", "", "保存研究"), el("p", "", "独立保存的研究与当前项目分开阅读。")); header.append(copy); element.append(header, body);
  let generation = 0;
  function activate(): void {
    const request = ++generation; body.replaceChildren(el("p", "empty-state", "正在读取保存研究与当前项目原记录…"));
    const read = async (url: string): Promise<Obj> => { const response = await fetch(url, { cache: "no-store" }); if (!response.ok) throw Error("读取失败（HTTP " + response.status + "）。"); return response.json() as Promise<Obj>; };
    void Promise.allSettled([read("/api/local-workbench/saved-study-reference"), read("/api/local-workbench/project-summary")]).then(([study, project]) => {
      if (request !== generation) return;
      const failed = (result: PromiseRejectedResult): Obj => ({ status: "unknown", reason: result.reason instanceof Error ? result.reason.message : "服务暂不可用，请检查后重试。" });
      draw(body, study.status === "fulfilled" ? study.value : failed(study), project.status === "fulfilled" ? project.value : failed(project));
    });
  }
  return { element, activate, deactivate: () => { generation++; body.replaceChildren(); } };
}
