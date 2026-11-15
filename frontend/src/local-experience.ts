/** Explicit project-local snapshots of historical method cases. */
import { el } from "./dom";
import { cpuResultSummary } from "./cpu-results";

type Obj = Record<string, unknown>;
type Host = {
  read(url: string): Promise<Obj>;
  submit(command: "experience-import" | "experience-status" | "experience-resume", body: Obj, recover?: boolean): Promise<Obj | null>;
  canRecover(body: Obj): boolean;
  methodTitle(methodId: string): string;
  announce(message: string, error?: boolean): void;
};
type Draft = { name: string; encoded: string; preview: Obj; reason: string; loading: boolean; submitted: boolean; statusReasons: Map<string, string>; boundVersion?: unknown; boundSnapshot?: unknown; fileChoice?: number };
const object = (value: unknown): Obj => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const objects = (value: unknown): Obj[] => Array.isArray(value) ? value.map(object) : [];
const text = (value: unknown, fallback = "未记录"): string => typeof value === "string" && value.length ? value : fallback;
const strings = (value: unknown): string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
const numeric = (value: unknown): string => typeof value === "number" && Number.isFinite(value) ? String(value) : "未记录";

export function isStagedExperienceSchema(value: unknown): boolean {
  return ["staged-retrieval-experience-bundle-v1", "staged-retrieval-experience-bundle-v2", "staged-retrieval-experience-bundle-v3", "staged-retrieval-wait-experience-bundle-v1"].includes(text(value, ""));
}

export function isSupportedExperienceSchema(value: unknown): boolean {
  return isStagedExperienceSchema(value) || ["project-experience-bundle-v1", "cpu-project-experience-bundle-v1", "posthoc-validation-loss-experience-bundle-v1"].includes(text(value, ""));
}

function field(label: string, control: HTMLElement): HTMLElement {
  const wrap = el("label", "local-field"); wrap.append(el("span", "local-label", label), control); return wrap;
}
function encoded(bytes: Uint8Array): string {
  const parts: string[] = []; for (let index = 0; index < bytes.length; index += 8192) parts.push(String.fromCharCode(...bytes.subarray(index, index + 8192)));
  return btoa(parts.join(""));
}
function download(value: Obj, label: string): void {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json;charset=utf-8" }));
  const link = el("a"); link.href = url; link.download = label.replace(/[^A-Za-z0-9_.-]/g, "_") + ".json"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function summaryText(summary: Obj): string {
  const labels: Record<string, string> = { n: "评价行数", input_n: "原输入行数", excluded: "排除行数", candidate_mae: "MAE",
    reference_mae: "训练均值参考 MAE", negative_predictions: "负预测数" };
  return Object.entries(labels).filter(([key]) => typeof summary[key] === "number" && Number.isFinite(summary[key]))
    .map(([key, label]) => label + " " + numeric(summary[key])).join("；");
}
function parentComparison(article: HTMLElement, comparison: Obj): void {
  if (comparison.status !== "comparable") return;
  const concise = (value: unknown): string => typeof value === "number" && Number.isFinite(value) ? String(Number(value.toPrecision(7))) : "未记录";
  const metrics = object(comparison.metrics), rows = object(comparison.row_summary), groups = object(comparison.group_summary);
  const relative = typeof metrics.relative_improvement === "number" ? concise(metrics.relative_improvement * 100) + "%" : "未计算";
  article.append(el("h4", "", "原项目保存的父版对照"),
    el("p", "", `父版 MAE ${concise(metrics.baseline_mae)} → 候选 MAE ${concise(metrics.candidate_mae)}；候选−父版 ${concise(metrics.mae_change)}；相对父版误差降低 ${relative}。`),
    el("p", "", `逐行绝对误差：${numeric(rows.improved_rows)} 改善、${numeric(rows.worsened_rows)} 恶化、${numeric(rows.tied_rows)} 持平（共 ${numeric(rows.n)} 行）。`));
  if (comparison.group_summary !== null)
    article.append(el("p", "", `按声明组 MAE：${numeric(groups.improved_groups)} 改善、${numeric(groups.worsened_groups)} 恶化、${numeric(groups.tied_groups)} 持平（共 ${numeric(groups.group_count)} 组）。`));
  const ranges = object(comparison.prediction_ranges);
  for (const [key, label] of [["baseline", "父版"], ["candidate", "候选"]]) {
    const range = object(ranges[key]);
    article.append(el("p", "", `${label}预测 ${concise(range.predicted_min)} 至 ${concise(range.predicted_max)}；负预测 ${numeric(range.negative_predictions)}；低于／高于原观察范围 ${numeric(range.below_observed_min)}／${numeric(range.above_observed_max)}。`));
  }
  article.append(el("p", "detail-note", "以上只描述原项目的保存对照；误差降低不表示本项目收益或科学确认，声明组也不自动成为独立样本。"));
}

function cpuTable(caption: string, headings: string[], values: string[][]): HTMLElement {
  const wrap = el("div", "project-comparison table-scroll"), table = el("table", "data-table");
  table.append(el("caption", "", caption));
  const head = el("thead"), header = el("tr");
  for (const title of headings) { const cell = el("th", "", title); cell.scope = "col"; header.append(cell); }
  head.append(header); table.append(head);
  const body = el("tbody");
  for (const cells of values) {
    const row = el("tr");
    cells.forEach((value, index) => { const cell = index === 0 ? el("th", "", value) : el("td", "", value);
      if (cell instanceof HTMLTableCellElement && index === 0) cell.scope = "row"; row.append(cell); });
    body.append(row);
  }
  table.append(body); wrap.append(table); return wrap;
}

function cpuObservation(article: HTMLElement, observation: Obj, scope: Obj): void {
  const method = text(observation.method_id, ""), counts = object(observation.saved_counts);
  const kinds: Record<string, string> = { "research.retrieval-fixed-pair": "citation_retrieval_pair",
    "research.relevance-fixed-pair": "relevance_retrieval_pair",
    "research.weighted-interval-fixed-pair": "weighted_interval_fixed_pair" };
  const paired = object(observation.paired_summary);
  const summary = method === "research.weighted-interval-fixed-pair" ? paired : {
    paired_summary: paired, query_pairs: typeof counts.metric_rows === "number" ? counts.metric_rows / 2 : undefined,
    adverse_queries: counts.adverse_queries };
  const view = cpuResultSummary([{ kind: kinds[method], scope, summary }], cpuTable);
  if (view) article.append(view);
  else article.append(el("p", "detail-note", "此CPU方法没有可展示的保存汇总，请查看原案例记录。"));
  article.append(el("p", "detail-note", "以上是原项目保存的结果与仅限保存值的核对，不是当前项目的新观察或科学评审。完整结果与原协议保留在案例快照中。"));
}

export function stagedWaitObservation(article: HTMLElement, observation: Obj): void {
  const feedback = object(observation.feedback);
  const labels: Record<string, string> = { condition_met: "条件满足", condition_not_met: "条件未满足", unknown: "未知" };
  article.append(el("p", "", "原条件等待 · " + text(labels[text(feedback.outcome, "")], "未记录")),
    el("p", "detail-note", "事前条件 · " + (feedback.condition === undefined ? "未记录" : JSON.stringify(feedback.condition))),
    el("p", "detail-note", "反馈值 · " + (feedback.value === undefined ? "未记录" : JSON.stringify(feedback.value))),
    el("p", "detail-note", "当时 final 未测；等待不限制后续路线。未知不等于零，离线来源绑定需回查原件。"));
}

export function stagedObservation(article: HTMLElement, observation: Obj, scope: Obj): void {
  const splits = object(object(observation.paired_summary).splits);
  const methods = object(observation.comparison);
  const delta = (name: string, metric: string): unknown =>
    object(object(object(splits[name]).paired_candidate_minus_baseline)[metric]).mean;
  article.append(el("p", "detail-note", "原检索来源 · " + text(scope.dataset_label)
    + "；原协议 · " + text(observation.evaluation_ref)),
    el("p", "detail-note", "基线方法 · " + text(methods.baseline) + "；候选方法 · " + text(methods.candidate) + "。"));
  for (const [name, label] of [["dev", "开发"], ["validation", "验证"]]) {
    article.append(el("p", "", `${label}集候选减基线：Recall@20 ${numeric(delta(name, "recall@20"))}；MRR@10 ${numeric(delta(name, "mrr@10"))}。`));
  }
  const feedback = object(observation.preregistered_feedback);
  if (Object.keys(feedback).length) {
    const labels: Record<string, string> = { condition_met: "条件满足", condition_not_met: "条件未满足", unknown: "未知" };
    article.append(el("h4", "", "原项目的事前反馈"),
      el("p", "", "原判定 · " + text(labels[text(feedback.outcome, "")], "未记录") + "。"),
      el("p", "detail-note", "原条件 · " + (feedback.condition === undefined ? "未记录" : JSON.stringify(feedback.condition))),
      el("p", "detail-note", "原反馈值 · " + (feedback.value === undefined ? "未记录" : JSON.stringify(feedback.value))));
    if (feedback.outcome === "unknown") article.append(el("p", "detail-note", "未知不是零，也不授权自动执行。"));
  } else {
    article.append(el("p", "detail-note", "此案例没有已记录的事前反馈绑定。"));
  }
  const shadow = object(observation.shadow_comparison), comparison = object(shadow.comparison);
  if (Object.keys(shadow).length) {
    const states: Record<string, string> = { condition_met: "本样本预定目标满足", condition_not_met: "本样本预定目标未满足", unknown: "未知" };
    const choices = "A · " + text(comparison.A_method) + "；B · " + text(comparison.B_method);
    const shadowValue = object(shadow.value), means = Array.isArray(shadowValue.means) ? shadowValue.means : [];
    article.append(el("h4", "", "外层规则比较"), el("p", "", choices + "；比较结果 · " + text(states[text(comparison.outcome, "")], "未记录") + "。"),
      el("p", "detail-note", "外层规则条件 · " + (shadow.condition === undefined ? "未记录" : JSON.stringify(shadow.condition))),
      el("p", "detail-note", "原验证值：Recall@20 差 " + numeric(means[0]) + "；MRR@10 差 " + numeric(means[1])
        + "；Recall@20 留一最小值 " + numeric(object(shadowValue.leave_one_out).minimum) + "。"));
    if (comparison.outcome === "unknown" && comparison.reason === "same_arm")
      article.append(el("p", "detail-note", "两条规则选择同一方法，无法据此比较；B−A 未知，不是零。"));
    else if (comparison.outcome === "unknown")
      article.append(el("p", "detail-note", "缺少可比较结果时保持未知，不用零代替。"));
    else if (comparison.outcome === "condition_met" || comparison.outcome === "condition_not_met") {
      const difference = object(comparison.B_minus_A);
      article.append(el("p", "", "已测两臂的 B−A：Recall@20 " + numeric(difference["recall@20"])
        + "；MRR@10 " + numeric(difference["mrr@10"]) + "。"));
    } else article.append(el("p", "detail-note", "比较状态未记录，不能推断是否测量了两臂。"));
    article.append(el("p", "detail-note", "外层规则锚是未验证的操作者声明，不是第二条原生事前登记；离线来源绑定及锚前快照须回查原件。"));
  }
  const final = object(observation.final), summary = object(final.summary), selected = object(summary.selected);
  const baseline = object(summary.baseline), finalDelta = object(summary.delta);
  article.append(el("h4", "", "原项目最终聚合"),
    el("p", "", "原选择 · " + text(final.selected_method) + "；查询数 " + numeric(final.query_count)
      + "；Recall@20 " + numeric(selected["recall@20"]) + "；MRR@10 " + numeric(selected["mrr@10"]) + "。"));
  if (final.comparison_status === "selected_equals_baseline_single_computation" && final.selected_method === "bm25")
    article.append(el("p", "detail-note", "最终只计算了 BM25 单臂；零差是结构值，最终 TF-IDF 未测，不能称为打平。"));
  else if (final.comparison_status === "distinct_selected_and_baseline")
    article.append(el("p", "", "原基线 · " + text(final.baseline_method) + "；Recall@20 " + numeric(baseline["recall@20"])
      + "；MRR@10 " + numeric(baseline["mrr@10"]) + "。"),
      el("p", "", "保存的所选减基线：Recall@20 " + numeric(finalDelta["recall@20"])
        + "；MRR@10 " + numeric(finalDelta["mrr@10"]) + "。"),
      el("p", "detail-note", "原最终结果包含所选方法和基线两臂；数值仅属于原项目。"));
  else article.append(el("p", "detail-note", "最终对照状态未记录，不能推断未测方法的结果。"));
  article.append(el("p", "detail-note", "历史案例仅供参考，不是当前项目的新证据；原策略与最终聚合的离线来源绑定须回查原项目。"));
}

export function createLocalExperiencePanel(host: Host): {
  element: HTMLElement; setLocked(value: boolean): void; refresh(projectId: string, project: Obj, pendingRequests?: Obj[]): Promise<void>;
  resolved(command: string, requestId: string): boolean;
} {
  const section = el("section", "local-panel local-experience content-section");
  section.append(el("h2", "section-title", "其他项目的方法案例"),
    el("p", "detail-note", "阅读历史项目的方法、观察与限制，供本项目计划参考。案例中的数值属于原项目；导入后仍需核对本项目的方法条件。"));
  const status = el("p", "notice", "创建或选择项目后可导入案例快照。"); status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
  const recovery = el("div", "local-experience-recovery"), list = el("div", "local-experience-cases"), editor = el("details", "local-advanced local-experience-import");
  editor.append(el("summary", "", "导入一个案例快照"));
  const form = el("form", "local-experience-form"), fields = el("fieldset", "local-fieldset"), chooser = el("input");
  chooser.type = "file"; chooser.accept = ".json,application/json"; chooser.setAttribute("aria-label", "选择方法案例快照 JSON");
  const fileStatus = el("p", "detail-note", "选择不超过4MiB的案例JSON；选择文件只准备草稿。"), reason = el("textarea");
  reason.rows = 3; reason.maxLength = 2000; reason.required = true;
  const save = el("button", "action-button primary", "导入为本项目参考"); save.type = "submit";
  fields.disabled = true; save.disabled = true;
  fields.append(field("案例快照文件", chooser), fileStatus, field("本次导入理由", reason)); form.append(fields, save); editor.append(form);
  section.append(status, recovery, editor, list);
  const drafts = new Map<string, Draft>(), statusButtons: { button: HTMLButtonElement; reason: HTMLTextAreaElement }[] = [];
  const recoveryButtons: { button: HTMLButtonElement; body: Obj }[] = [];
  let active = "", project: Obj = {}, view: Obj = {}, pending: Obj[] = [], locked = true, loading = false, generation = 0, fileChoiceGeneration = 0;

  function draftFor(projectId: string): Draft {
    const old = drafts.get(projectId); if (old) return old;
    const draft: Draft = { name: "", encoded: "", preview: {}, reason: "", loading: false, submitted: false, statusReasons: new Map() };
    drafts.set(projectId, draft); return draft;
  }
  function controls(): void {
    const draft = active ? draftFor(active) : null, disabled = locked || loading || !active || !Number.isSafeInteger(project.state_version) || !!draft?.loading;
    fields.disabled = disabled; save.disabled = disabled || !draft?.encoded || !draft.reason.trim() || draft.submitted;
    save.textContent = draft?.submitted ? "案例快照已导入" : "导入为本项目参考";
    for (const entry of statusButtons) { entry.reason.disabled = disabled; entry.button.disabled = disabled || !entry.reason.value.trim(); }
    for (const entry of recoveryButtons) entry.button.disabled = !host.canRecover(entry.body);
  }
  function draftText(): void {
    const draft = active ? draftFor(active) : null;
    reason.value = draft?.reason ?? "";
    const stagedSchema = isStagedExperienceSchema(draft?.preview.schema_version);
    const posthoc = draft?.preview.schema_version === "posthoc-validation-loss-experience-bundle-v1";
    fileStatus.textContent = draft?.name ? draft.name + " · " + (posthoc ? "事后验证子集聚合" : draft.preview.schema_version === "staged-retrieval-wait-experience-bundle-v1" ? "阶段检索条件等待" : stagedSchema ? "阶段检索保存结果" : draft.preview.schema_version === "cpu-project-experience-bundle-v1" ? "CPU保存结果" : "Ridge保存结果")
      + " · 案例 " + text(draft.preview.id) + " · v" + numeric(draft.preview.version)
      + (draft.submitted ? " · 已从保存记录确认导入。" : " · 草稿已准备，尚未提交。")
      + (posthoc ? " 文件自述的上游 primary 来源引用：" + text(object(object(draft.preview.record).provenance).action_id) + "；提交后由服务端核验。仅绑定已发布字节，未重算或验证签名；已曝光事后子集，不证明因果或匿名，也不会自动引用到计划。" : "") : "选择不超过4MiB的案例JSON；选择文件只准备草稿。";
  }
  function resolved(command: string, requestId: string): boolean {
    return ["experience-import", "experience-status", "experience-resume"].includes(command)
      && !pending.some(record => record.request_id === requestId)
      && objects(view.history).some(revision => revision.request_id === requestId);
  }
  function renderRecovery(): void {
    recoveryButtons.length = 0; recovery.replaceChildren();
    for (const record of pending.filter(item => item.project_id === active && ["import_experience", "set_experience_status"].includes(text(item.command, "")))) {
      const id = text(record.request_id, ""), sourceProject = active, body = { request_id: id, project_id: sourceProject };
      const row = el("div", "notice"), button = el("button", "action-button", "核对原案例请求"); button.type = "button";
      row.append(el("p", "", "原案例请求待核对 · " + id), el("p", "detail-note", "核对沿用首次保存的文件与参数，不读取当前导入草稿。"), button);
      button.addEventListener("click", () => { if (!button.disabled) void (async () => {
        const result = await host.submit("experience-resume", body, true); if (result?.status !== "completed") return;
        const draft = draftFor(sourceProject);
        if (record.command === "import_experience" && draft.encoded) draft.submitted = true;
        const revision = objects(view.history).find(item => item.request_id === id);
        if (revision?.case_id) draft.statusReasons.delete(text(revision.case_id, ""));
        if (active === sourceProject) { draftText(); renderCases(); }
      })(); });
      recoveryButtons.push({ button, body }); recovery.append(row);
    }
    controls();
  }
  function caseRecord(record: Obj): HTMLElement {
    const article = el("article", "evidence-card local-experience-case"), card = object(record.method_card), origin = object(record.origin_evidence);
    const observation = object(record.observation), scope = object(record.source_scope), id = text(record.case_id, ""), sourceProject = active;
    const retired = record.inclusion_status === "retired", draft = draftFor(sourceProject);
    const cpu = observation.kind === "saved_cpu_fixed_pair", wait = observation.kind === "staged_wait_feedback";
    const posthoc = observation.kind === "posthoc_validation_loss";
    const staged = observation.kind === "saved_staged_retrieval" || wait;
    article.append(el("h3", "", text(card.question, id)), el("p", "detail-note", id + " · v" + numeric(record.case_version)
      + " · " + (retired ? "已从后续建议撤回" : "当前用于参考")), el("p", "", text(card.rationale)),
      el("p", "detail-note", "源项目 · " + text(origin.project_id)));
    if (posthoc) {
      const cell = object(observation.cell);
      article.append(el("p", "detail-note", "事后分析：已曝光验证集，Recall@20 差在 ±1e-12 内且 MRR@10 下降的子集。"));
      article.append(el("p", "", cell.status === "available"
        ? "该子集 " + numeric(cell.count) + " 题；平均下降 " + numeric(cell.mean_mrr_loss) + "（四位舍入）。"
        : "子集数量与均值未供应。"));
      article.append(el("p", "detail-note", "仅匹配已发布聚合；导入时未重算，离线须回查原件。原 primary 仅为来源引用；非总体均值、因果或匿名保证。"));
    } else if (staged) {
      if (wait) stagedWaitObservation(article, observation);
      else stagedObservation(article, observation, scope);
    } else if (cpu) {
      const comparison = object(observation.comparison);
      article.append(el("p", "detail-note", "原方法 · " + host.methodTitle(text(observation.method_id)) + "；原协议 · " + text(observation.evaluation_ref)),
        el("p", "detail-note", "基线 · " + text(comparison.baseline) + "；候选 · " + text(comparison.candidate)));
      cpuObservation(article, observation, scope);
    } else {
      article.append(el("p", "detail-note", "原方法 · " + objects(card.method_refs).map(item => host.methodTitle(text(item.method_id))).join("、")
        + "；原检查 · " + text(observation.check)), el("p", "detail-note", "原目标 · " + text(scope.target_column) + "；原单位 · " + text(scope.target_unit)));
      const numbers = summaryText(object(observation.numerical_summary)); if (numbers) article.append(el("p", "", "来源观察 · " + numbers));
      const summary = object(observation.numerical_summary);
      if ([summary.observed_min, summary.observed_max, summary.predicted_min, summary.predicted_max].every(value => typeof value === "number" && Number.isFinite(value)))
        article.append(el("p", "detail-note", `原观察范围 ${numeric(summary.observed_min)}至${numeric(summary.observed_max)}；保存预测范围 ${numeric(summary.predicted_min)}至${numeric(summary.predicted_max)}。`));
      parentComparison(article, object(observation.saved_parent_comparison));
    }
    const limits = strings(record.limitations);
    if (limits.length) { const ul = el("ul"); for (const limit of limits) ul.append(el("li", "", limit)); article.append(el("h4", "", "适用边界与反例"), ul); }
    const original = el("details", "local-advanced"); original.append(el("summary", "", "查看方法卡、原协议与出处"));
    const applicability = object(card.applicability);
    for (const [key, label] of [["requires", "需要的条件"], ["not_applicable", "不适用情形"], ["uncertain", "尚未确定"]]) {
      const values = strings(applicability[key]), ul = el("ul"); for (const value of values) ul.append(el("li", "", value));
      if (values.length) original.append(el("h4", "", label), ul);
    }
    if (posthoc) {
      original.append(el("h4", "", "事后分析的来源身份"),
        el("p", "detail-note", "原 primary 来源引用：" + text(origin.action_id) + "；原结果 SHA-256：" + text(origin.result_sha256)),
        el("p", "detail-note", "公开聚合 SHA-256：" + text(origin.published_result_sha256) + "；原协议 SHA-256：" + text(origin.protocol_sha256)));
    } else if (staged) {
      original.append(el("h4", "", "原阶段检索来源身份"),
        el("p", "", "原行动：" + text(origin.action_id) + "；原项目版本 " + numeric(origin.state_version)),
        el("p", "detail-note", "原来源快照 SHA-256：" + text(origin.source_snapshot_sha256)),
        el("p", "detail-note", "原结果 SHA-256：" + text(origin.result_sha256)),
        el("p", "detail-note", "此处显示案例摘要；未重新排名、评分或读取最终逐题数据。"));
    } else if (cpu) {
      original.append(el("h4", "", "原固定协议与来源身份"),
        el("p", "", "评价协议：" + text(observation.evaluation_ref) + "；来源范围：" + text(scope.dataset_label)),
        el("p", "detail-note", "原行动：" + text(origin.action_id) + "；原项目版本 " + numeric(origin.state_version)),
        el("p", "detail-note", "原结果生产代码：" + text(origin.producer_code_identity)),
        el("p", "detail-note", "来源快照 SHA-256：" + text(origin.source_snapshot_sha256)),
        el("p", "detail-note", "原结果 SHA-256：" + text(origin.result_sha256)),
        el("p", "detail-note", "原来源文件按 SHA-256 引用；原文未随案例快照附带。已保存值按绑定与算术核对，未重算检索得分或求解。"));
    } else {
    const protocol = object(observation.protocol);
    original.append(el("h4", "", "原计算协议"), el("p", "", text(protocol.splitter) + " · " + numeric(protocol.n_splits) + " 折；Ridge alpha " + numeric(protocol.ridge_alpha)),
      el("p", "", "原输入列：" + strings(protocol.feature_columns).join("、") + "；分组列：" + strings(protocol.split_group_columns).join("、")),
      el("p", "", "模型输入项：" + strings(protocol.model_input_terms).join("、")), el("p", "", "预处理：" + text(protocol.preprocessing)),
      el("p", "", "出处行动：" + text(origin.action_id) + "；原项目版本 " + numeric(origin.state_version)));
    const comparison = object(observation.saved_parent_comparison);
    if (comparison.status === "comparable") {
      for (const [key, label] of [["baseline_ref", "父版"], ["candidate_ref", "候选"]]) {
        const reference = object(comparison[key]);
        original.append(el("p", "", `${label}：项目设计 v${numeric(reference.design_version)}；资源 ${text(reference.resource_id)} v${numeric(reference.resource_version)}；行动 ${text(reference.action_id)}。`),
          el("p", "", label + "保存的模型输入项：" + strings(reference.model_input_terms ?? reference.feature_columns).join("、")));
      }
      original.append(el("p", "detail-note", "父版生产代码：" + text(origin.parent_producer_code_identity)),
        el("p", "detail-note", "候选生产代码：" + text(origin.producer_code_identity)));
    }
    }
    const raw = el("details", "local-advanced"); raw.append(el("summary", "", cpu || staged ? "案例摘要 JSON（完整结果在原导入包）" : "完整案例记录 JSON"), el("pre", "project-source-text", JSON.stringify(record, null, 2)));
    original.append(raw); article.append(original);
    const actions = el("div", "local-actions"), recordDownload = el("button", "quiet-button", cpu || staged ? "下载案例摘要 JSON" : "下载这条案例记录 JSON"); recordDownload.type = "button";
    recordDownload.addEventListener("click", () => download(record, id + "-v" + numeric(record.case_version) + (cpu || staged ? "-summary" : ""))); actions.append(recordDownload);
    const statusForm = el("form", "local-experience-status"), statusReason = el("textarea"), button = el("button", "action-button");
    statusReason.rows = 2; statusReason.maxLength = 2000; statusReason.required = true; statusReason.value = draft.statusReasons.get(id) ?? "";
    button.type = "submit"; button.textContent = retired ? "恢复参考" : "从后续建议撤回";
    statusReason.addEventListener("input", () => { draft.statusReasons.set(id, statusReason.value); controls(); });
    statusForm.append(field(retired ? "恢复理由" : "撤回理由", statusReason), button);
    statusForm.addEventListener("submit", event => { event.preventDefault(); void (async () => {
      if (button.disabled || !statusForm.reportValidity()) return;
      const result = await host.submit("experience-status", { project_id: sourceProject, expected_state_version: project.state_version,
        case_id: id, status: retired ? "active" : "retired", reason: statusReason.value });
      if (result?.status === "completed") { draft.statusReasons.delete(id); if (active === sourceProject) renderCases(); }
    })(); });
    statusButtons.push({ button, reason: statusReason }); article.append(actions, statusForm); return article;
  }
  function renderCases(): void {
    statusButtons.length = 0; list.replaceChildren();
    const cases = objects(view.cases);
    if (!cases.length) list.append(el("p", "empty-state", "本项目尚未导入其他项目的方法案例。"));
    for (const record of cases) list.append(caseRecord(record));
    if (objects(view.history).length) {
      const history = el("details", "local-advanced"), changes = el("ol"); history.append(el("summary", "", "查看本项目的案例状态历史"));
      for (const revision of objects(view.history)) {
        const action = revision.command === "import_experience" ? "导入" : revision.inclusion_status === "active" ? "恢复参考" : "撤回参考";
        changes.append(el("li", "", text(revision.case_id) + " v" + numeric(revision.case_version) + " · " + action + "：" + text(revision.reason)));
      }
      const raw = el("details", "local-advanced"); raw.append(el("summary", "", "完整状态历史 JSON"), el("pre", "project-source-text", JSON.stringify(view.history, null, 2)));
      history.append(changes, raw);
      const saveHistory = el("button", "quiet-button", "下载案例状态历史 JSON"); saveHistory.type = "button";
      saveHistory.addEventListener("click", () => download({ project_id: active, history: view.history }, "experience-history")); history.append(saveHistory); list.append(history);
    }
    controls();
  }
  chooser.addEventListener("change", () => { void (async () => {
    const file = chooser.files?.[0], sourceProject = active; chooser.value = ""; if (!file || !sourceProject) return;
    const sourceGeneration = generation, sourceVersion = project.state_version, sourceSnapshot = project.snapshot_ref;
    const choice = ++fileChoiceGeneration, draft = draftFor(sourceProject); draft.fileChoice = choice; draft.loading = true; controls();
    try {
      if (!file.size || file.size > 4 * 1024 * 1024) throw Error("案例JSON须非空且不超过4MiB，原草稿保留。");
      const bytes = new Uint8Array(await file.arrayBuffer()), preview = object(JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)));
      if (choice !== fileChoiceGeneration) return;
      if (!isSupportedExperienceSchema(preview.schema_version)
          || typeof preview.id !== "string" || typeof preview.version !== "number")
        throw Error("请选择导出的项目案例快照，原草稿保留。");
      if (preview.schema_version === "posthoc-validation-loss-experience-bundle-v1"
          && (generation !== sourceGeneration || active !== sourceProject || project.state_version !== sourceVersion || project.snapshot_ref !== sourceSnapshot))
        throw Error("项目或快照已变化，请重新选择事后案例文件。");
      draft.name = file.name; draft.encoded = encoded(bytes); draft.preview = preview; draft.submitted = false;
      if (preview.schema_version === "posthoc-validation-loss-experience-bundle-v1") {
        draft.boundVersion = sourceVersion; draft.boundSnapshot = sourceSnapshot;
      }
      if (active === sourceProject) draftText();
    } catch (error) { if (active === sourceProject && choice === fileChoiceGeneration) host.announce(error instanceof Error ? error.message : "文件读取未完成，原草稿保留。", true); }
    finally { if (draft.fileChoice === choice) draft.loading = false; controls(); }
  })(); });
  reason.addEventListener("input", () => { if (active) { const draft = draftFor(active); draft.reason = reason.value; draft.submitted = false; } controls(); });
  form.addEventListener("submit", event => { event.preventDefault(); void (async () => {
    const sourceProject = active, draft = sourceProject ? draftFor(sourceProject) : null;
    if (!draft || save.disabled || !form.reportValidity()) return;
    const result = await host.submit("experience-import", { project_id: sourceProject, expected_state_version: project.state_version,
      bundle_base64: draft.encoded, reason: draft.reason });
    if (result?.status === "completed") { draft.submitted = true; if (active === sourceProject) { draftText(); controls(); } }
  })(); });
  async function refresh(projectId: string, current: Obj, pendingRequests: Obj[] = []): Promise<void> {
    if (active && active !== projectId) {
      fileChoiceGeneration++;
      const old = draftFor(active);
      if (old.preview.schema_version === "posthoc-validation-loss-experience-bundle-v1") {
        old.name = ""; old.encoded = ""; old.preview = {}; old.submitted = false;
      }
    }
    const selected = projectId ? draftFor(projectId) : null;
    if (selected?.preview.schema_version === "posthoc-validation-loss-experience-bundle-v1"
        && (selected.boundVersion !== current.state_version || selected.boundSnapshot !== current.snapshot_ref)) {
      selected.name = ""; selected.encoded = ""; selected.preview = {}; selected.submitted = false;
    }
    const token = ++generation; active = projectId; project = current; view = {}; pending = pendingRequests; loading = true;
    list.replaceChildren(); draftText(); renderRecovery(); controls();
    if (!projectId || current.id !== projectId) { loading = false; status.textContent = "创建或选择项目后可导入案例快照。"; controls(); return; }
    status.textContent = "正在读取当前项目的案例快照…";
    try {
      const value = await host.read("/api/local-workbench/experiences");
      if (token !== generation || projectId !== active) return;
      if (value.schema_version !== "project-experience-view-v1" || value.project_id !== projectId || value.state_version !== current.state_version)
        throw Error("案例快照与当前项目版本不一致，请只读刷新后核对。");
      view = value; renderCases(); status.textContent = "这些是历史方法案例。原数值保留其来源范围，本项目的行动仍由当前条件和额度决定。";
    } catch (error) {
      if (token !== generation || projectId !== active) return;
      status.textContent = error instanceof Error ? error.message : "案例快照读取未完成，请只读刷新后核对。";
    } finally { if (token === generation) { loading = false; controls(); } }
  }
  return { element: section, setLocked(value): void { locked = value; controls(); }, refresh, resolved };
}
