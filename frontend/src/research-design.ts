/** Saved research designs and explicit project bindings share the workbench command journal. */
import { el, numeric, safeUrl } from "./dom";

type Obj = Record<string, unknown>;
type Host = {
  read(url: string): Promise<Obj>;
  submit(name: string, body: Obj): Promise<Obj | null>;
  announce(message: string, error?: boolean): void;
};
type Draft = { resource: string; prediction: string; reason: string; improvement: string; features: string[]; groups: string[]; fitLimit: number };
const object = (value: unknown): Obj => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const objects = (value: unknown): Obj[] => Array.isArray(value) ? value.map(object) : [];
const words = (value: unknown): string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
const text = (value: unknown, fallback = "未记录"): string => typeof value === "string" && value.length ? value : fallback;
const resourceKey = (value: Obj): string => String(value.id) + "@" + String(value.version);
const rawDesign = (resource: Obj): boolean => words(resource.checks).some(check => ["random_cv", "group_cv"].includes(check));
const resourceFields = ["schema_version", "id", "version", "title", "question", "claim", "alternatives", "checks", "sources", "parent_version", "change_reason"];
const checkNames: Record<string, string> = { baseline: "基线比较", grouped: "分组验证", sensitivity: "敏感性检查",
  random_cv: "随机五折验证", group_cv: "分组交叉验证", negative_control: "折内负对照" };
const statuses: Record<string, string> = { available: "可选择", candidate: "候选版本", validated: "验证记录已齐", completed: "已完成", failed: "失败", unknown: "待核对", running: "执行中", not_executed: "尚未执行" };
const reasons: Record<string, string> = {
  insufficient_samples: "可比较样本不足", insufficient_groups: "完整分组不足", constant_target: "参考误差为0，无法计算相对改善",
  groups_required: "需先声明分组字段", lower_mae_than_reference: "保存预测的平均绝对误差较低", no_lower_mae_than_reference: "保存预测的平均绝对误差未低于参考",
  reference_mae_underflow: "参考误差超出当前数值精度，无法计算相对改善",
  no_reordering_information: "当前条件内的重排没有提供可区分的信息，原配对关系尚待判断",
  improvement_conclusion_reversed_on_removal: "移除部分单位后，优于参考的结论发生变化",
};
const featureComparisonReasons: Record<string, string> = {
  RESOURCE_LINEAGE_MISMATCH: "两侧设计资源不符合相邻版本关系", PROJECT_MISMATCH: "两侧行动不属于同一项目",
  CHECK_MISMATCH: "两侧检查类型不同", SOURCE_SNAPSHOT_MISMATCH: "输入来源快照不同",
  TARGET_MISMATCH: "目标字段不同", TARGET_UNIT_MISMATCH: "目标单位不同", PROTOCOL_MISMATCH: "训练或评价协议不同",
  DUPLICATE_OOF_RECORD: "保存预测中存在重复评价记录", EMPTY_OOF: "缺少保存的折外预测",
  ROW_COVERAGE_MISMATCH: "评价行覆盖不同", ROW_COORDINATES_MISMATCH: "评价行原始坐标不同",
  OBSERVED_MISMATCH: "保存的目标观测值不同", GROUPS_MISMATCH: "评价记录的分组不同",
  FOLD_ASSIGNMENT_MISMATCH: "评价记录的折分配不同", REFERENCE_PREDICTION_MISMATCH: "参考预测不同",
  DUPLICATE_FOLD_RECORD: "存在重复折记录", FOLD_RECORDS_MISMATCH: "各折训练或评价记录缺失或不同",
  DUPLICATE_SPLIT_RECORD: "训练或评价划分内存在重复记录", MODEL_PARAMETERS_MISMATCH: "模型参数不同",
};
const percent = (value: unknown): string => typeof value === "number" && Number.isFinite(value) ? numeric(value * 100, 5) + "%" : "未计算";
const measure = (value: unknown): string => typeof value === "number" ? numeric(value) : "未计算";

function field(label: string, control: HTMLElement): HTMLElement {
  const wrap = el("label", "local-field"); wrap.append(el("span", "local-label", label), control); return wrap;
}

function list(parent: HTMLElement, title: string, values: string[]): void {
  if (!values.length) return;
  const content = el("ul"); for (const value of values) content.append(el("li", "", value));
  parent.append(el("h4", "", title), content);
}

function designCopy(parent: HTMLElement, resource: Obj): void {
  parent.append(el("h3", "", text(resource.title) + " · v" + String(resource.version)), el("p", "research-design-question", text(resource.question)),
    el("h4", "", "待验证的主张"), el("p", "", text(resource.claim)));
  list(parent, "竞争解释", words(resource.alternatives));
  list(parent, "检查计划", words(resource.checks).map(check => checkNames[check] ?? check));
}

function rawRecord(value: Obj, label: string): HTMLDetailsElement {
  const details = el("details", "research-design-raw");
  details.append(el("summary", "", label), el("pre", "project-source-text", JSON.stringify(value, null, 2))); return details;
}

function metricTable(headers: string[], rows: string[][]): HTMLElement {
  const scroll = el("div", "project-table-scroll"), table = el("table", "research-design-table");
  const head = el("thead"), top = el("tr"), body = el("tbody");
  for (const title of headers) { const cell = el("th", "", title); cell.scope = "col"; top.append(cell); }
  head.append(top);
  for (const values of rows) { const row = el("tr"); for (const value of values) row.append(el("td", "", value)); body.append(row); }
  table.append(head, body); scroll.append(table); return scroll;
}

function metricSummary(values: string[][], label: string): HTMLElement {
  const metrics = el("dl", "research-design-metrics"); metrics.setAttribute("aria-label", label); metrics.dataset.count = String(values.length);
  for (const [label, value] of values) {
    const metric = el("div"); metric.append(el("dt", "", label), el("dd", "", value)); metrics.append(metric);
  }
  return metrics;
}

function showMetrics(parent: HTMLElement, record: Obj): void {
  const summary = object(record.summary), details = object(record.details);
  parent.append(metricSummary([["可比较样本", measure(summary.n)], ["排除记录", measure(summary.excluded)],
    ["预测 MAE", measure(summary.candidate_mae)], ["参考 MAE", measure(summary.reference_mae)], ["相对改善", percent(summary.improvement)]], "本项检查的汇总指标"));
  const trained = ["random_cv", "group_cv"].includes(text(record.check));
  const reference = summary.reference_kind === "leave_group_out_mean" ? "排除整个当前组后的目标均值" : "排除当前样本后的目标均值";
  parent.append(el("p", "detail-note", "MAE 为平均绝对误差，越小越好。参考为" + (trained ? "各训练折的目标均值" : reference) + "；相对改善大于0表示本次预测误差较低。"));
  if (trained) parent.append(el("p", "detail-note", record.check === "random_cv" ? "随机五折固定 seed 11、Ridge alpha 1；每折分别拟合训练折的标准化器与模型。"
    : "按声明组拆分，折数为 min(5, 完整组数)、Ridge alpha 1；训练组与评价组分开，每折单独拟合标准化器与模型。"));
  const predictionRange = object(record.prediction_range);
  if (trained && Object.keys(predictionRange).length) {
    const n = measure(predictionRange.n);
    parent.append(el("h4", "", "保存预测范围"),
      el("p", "detail-note", "本次原目标范围 " + measure(predictionRange.observed_min) + " – " + measure(predictionRange.observed_max)
        + "；保存预测范围 " + measure(predictionRange.predicted_min) + " – " + measure(predictionRange.predicted_max) + "。"),
      el("p", "detail-note", "负预测 " + measure(predictionRange.negative_predictions) + " / " + n
        + "；低于本次观察范围 " + measure(predictionRange.below_observed_min) + " / " + n
        + "；高于本次观察范围 " + measure(predictionRange.above_observed_max) + " / " + n + "。"),
      el("p", "detail-note", "用于复核保存预测；适用约束按课题判断。"));
  }
  if (summary.reason) parent.append(el("p", "", reasons[text(summary.reason)] ?? text(summary.reason)));
  const groups = objects(details.groups);
  if (groups.length) parent.append(el("p", "research-design-table-hint", "左右滑动查看完整分组列"), metricTable(["原记录分组", "样本", "预测 MAE", "参考 MAE", "平均残差"], groups.map(group => [
    text(group.group, JSON.stringify(group.group)), measure(group.n), measure(group.candidate_mae), measure(group.reference_mae), measure(group.mean_residual),
  ])));
  if (record.check === "sensitivity") {
    const influential = object(details.most_influential), unit = details.unit_kind === "group" ? "组" : "记录";
    parent.append(el("p", "", "逐一移除" + unit + "重新比较，可计算单位 " + measure(details.computable_units) + "。"
      + (details.conclusion_reversed === true ? "已观察到比较结论变化。" : details.conclusion_reversed === false ? "已计算单位中未观察到比较结论变化。" : "当前结果尚不足以判断结论变化。")));
    if (Object.keys(influential).length) parent.append(el("p", "", "影响最大的" + unit + "为 " + text(influential.unit, JSON.stringify(influential.unit))
      + "，移除后剩余 " + measure(influential.remaining_n) + " 条，相对改善 " + percent(influential.improvement) + "。"));
  }
}

function showNegativeControl(parent: HTMLElement, record: Obj): void {
  const summary = object(record.summary), protocol = object(record.protocol), withinFolds = protocol.grouping === "within_oof_folds";
  parent.append(metricSummary([["原始 MAE", measure(summary.original_mae)], ["置换中位数", measure(summary.permutation_median)],
    ["条件秩", measure(summary.conditional_rank)], ["随机种子", measure(protocol.seed)], ["置换次数", measure(protocol.repeats)],
    ["置换 5%–95%", measure(summary.permutation_p05) + " – " + measure(summary.permutation_p95)]], "折内负对照指标"),
    el("p", "detail-note", (withinFolds ? "此项沿已保存的OOF折进行折内条件诊断" : "此项沿已保存的组进行组内条件诊断")
      + "，核对打乱后的误差分布。条件秩依赖当前划分与置换方式，解释时结合原协议。"));
  if (summary.reason) parent.append(el("p", "", reasons[text(summary.reason)] ?? text(summary.reason)));
  if (typeof summary.alignment_supported === "boolean") parent.append(el("p", "", summary.alignment_supported
    ? "本次条件诊断支持原预测与标签的配对关系。" : "本次条件诊断未支持原预测与标签的配对关系。"));
}

function showFeatureComparisons(parent: HTMLElement, records: Obj[]): void {
  const comparisons = records.filter(record => record.schema_version === "feature-comparison-v1");
  if (!comparisons.length) return;
  parent.append(el("h3", "", "同协议特征对照"));
  for (const record of comparisons) {
    const entry = el("article", "research-design-result"), comparable = record.status === "comparable";
    entry.append(el("h4", "", (checkNames[text(record.check)] ?? text(record.check)) + " · " + (comparable ? "可比较" : "暂不可比较")));
    for (const [label, reference] of [["基准", object(record.baseline_ref)], ["候选", object(record.candidate_ref)]] as const) {
      entry.append(el("p", "", label + " · 项目设计修订 " + measure(reference.design_version) + " · 资源 " + text(reference.resource_id)
        + " v" + measure(reference.resource_version) + "；特征 " + (words(reference.feature_columns).join("、") || "未记录") + "。"));
    }
    if (comparable) {
      const metrics = object(record.metrics), n = measure(record.matched_rows);
      entry.append(el("p", "", "可比较行数 · " + n),
        metricSummary([["基准 MAE", measure(metrics.baseline_mae)], ["候选 MAE", measure(metrics.candidate_mae)],
          ["MAE 差值", measure(metrics.mae_change)], ["相对改善", percent(metrics.relative_improvement)],
          ["基准负预测", measure(metrics.baseline_negative_predictions) + " / " + n],
          ["候选负预测", measure(metrics.candidate_negative_predictions) + " / " + n]], "同协议特征对照指标"),
        el("p", "detail-note", "MAE 差值为候选减基准，负值表示候选误差较低。此处仅比较本次保存结果。"));
    } else {
      const codes = words(record.reason_codes);
      if (codes.length) list(entry, "不能比较的原因", codes.map(code => featureComparisonReasons[code] ?? code));
      else entry.append(el("p", "", "当前记录尚未提供可比较依据。"));
    }
    entry.append(rawRecord(record, "查看两侧行动与对照原记录")); parent.append(entry);
  }
}

function columnChecks(parent: HTMLElement, columns: string[], checked: string[], change: (values: string[]) => void): void {
  parent.replaceChildren();
  if (!columns.length) { parent.append(el("p", "detail-note", "当前没有可选择的声明字段。")); return; }
  for (const column of columns) {
    const label = el("label", "local-checkbox"), input = el("input"); input.type = "checkbox"; input.value = column; input.checked = checked.includes(column);
    input.addEventListener("change", () => change([...parent.querySelectorAll<HTMLInputElement>("input:checked")].map(value => value.value)));
    label.append(input, el("span", "", column)); parent.append(label);
  }
}

export function createResearchDesignPanel(host: Host): {
  element: HTMLElement; libraryElement: HTMLElement; update(project: Obj): Promise<void>;
  invalidate(): void; setLocked(value: boolean, libraryValue?: boolean): void; resolved(name: string, requestId: string): boolean;
} {
  const section = el("section", "local-panel content-section research-design"), library = el("section", "local-panel content-section research-design-library");
  section.id = "research-design";
  section.append(el("h2", "section-title", "研究设计与验证"));
  const status = el("p", "research-design-status", "正在读取研究设计…"); status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
  const bindingNote = el("p", "detail-note"), copy = el("div", "research-design-copy");
  const form = el("form", "research-design-form"), fields = el("fieldset", "local-fieldset"); form.setAttribute("aria-label", "选择研究设计与输入声明");
  const selection = el("select"), prediction = el("select"); selection.required = true; prediction.required = true;
  const reason = el("textarea"); reason.rows = 2; reason.required = true; reason.maxLength = 2000;
  reason.placeholder = "说明为何采用该设计，以及这列预测的来源与比较目的";
  const columns = el("div", "local-form-grid"), targetNote = el("p", "detail-note");
  const predictionField = field("CSV 中已保存的预测列", prediction);
  columns.append(field("研究设计与配方版本", selection), predictionField);
  const training = el("div", "research-design-training"), trainingColumns = el("div", "local-form-grid");
  const features = el("fieldset", "local-fieldset research-design-columns"), splitGroups = el("fieldset", "local-fieldset research-design-columns");
  const featureOptions = el("div", "research-design-column-options"), groupOptions = el("div", "research-design-column-options");
  features.append(el("legend", "local-label", "用于训练的数值特征（1至16列）"), featureOptions);
  splitGroups.append(el("legend", "local-label", "用于分组拆分的声明字段"), groupOptions); trainingColumns.append(features, splitGroups);
  const fitLimit = el("input"); fitLimit.type = "number"; fitLimit.min = "1"; fitLimit.max = "40"; fitLimit.step = "1"; fitLimit.value = "20";
  training.hidden = true;
  training.append(el("p", "detail-note", "明确选择特征与分组。目标字段和已声明分组字段不进入特征；执行需至少10条完整记录、2个完整组。"), trainingColumns,
    field("累计 fit 尝试上限", fitLimit), el("p", "detail-note", "上限为1至40次，默认20。每折包含标准化器与Ridge各1次fit，两类合计2次。累计已用与预留沿项目保存，调整设计继续读取原消耗。"),
    el("p", "detail-note", "固定比较随机五折（seed 11）与分组 min(5, 组数) 折，Ridge alpha 为1。标准化在各训练折内拟合。"));
  const fitBudget = el("div", "research-design-fit-budget"); fitBudget.hidden = true;
  const bind = el("button", "action-button primary", "保存研究设计与预测列"); bind.type = "submit";
  const formDetails = el("details", "research-design-editor");
  formDetails.append(el("summary", "", "选择或调整研究设计"));
  fields.append(columns, targetNote, training, field("采用理由", reason), bind); form.append(fields); formDetails.append(form);
  const results = el("div", "research-design-results"), assessment = el("div", "research-design-assessment");
  const next = el("a", "text-button", "选择并明确执行下一项验证"); next.href = "#/research?focus=operations";
  const improve = el("details", "research-design-improvement"), improveForm = el("form"), improveFields = el("fieldset", "local-fieldset");
  const improveReason = el("textarea"); improveReason.rows = 2; improveReason.required = true; improveReason.maxLength = 2000;
  improveReason.placeholder = "指出本次基线反馈还未排除的解释，以及增加验证的理由";
  const improveButton = el("button", "action-button", "根据实际反馈生成候选新版"); improveButton.type = "submit";
  improveFields.append(field("改进理由", improveReason), improveButton); improveForm.append(improveFields);
  improve.append(el("summary", "", "从真实反馈改进研究设计"), el("p", "detail-note", "依据已完成的基线记录，生成包含分组与敏感性检查的候选版本。生成后可在目录中查看，并明确选择采用。"), improveForm);
  section.append(status, bindingNote, copy, formDetails, fitBudget, assessment, next, results, improve);
  library.append(el("h2", "section-title", "研究设计资源目录"), el("p", "detail-note", "查看可复用的主张、竞争解释与检查计划。版本的使用次数与验证记录来自已保存项目。"));
  const libraryStatus = el("p", "research-design-status", "正在读取资源目录…"), libraryItems = el("div", "research-design-resources");
  const importDetails = el("details", "research-design-import"), importForm = el("form"), importFields = el("fieldset", "local-fieldset");
  const importFile = el("input"); importFile.type = "file"; importFile.accept = ".json,application/json";
  const importStatus = el("p", "detail-note", "选择本目录导出的JSON或符合资源协议的文件。相同版本内容一致时沿用已有资源。");
  importStatus.setAttribute("role", "status");
  const importButton = el("button", "action-button", "导入研究设计资源"); importButton.type = "submit";
  importFields.append(field("研究设计资源 JSON", importFile), importStatus, importButton); importForm.append(importFields);
  importDetails.append(el("summary", "", "导入研究设计资源"), importForm);
  libraryStatus.setAttribute("role", "status"); library.append(libraryStatus, importDetails, libraryItems);
  let project: Obj = {}, catalog: Obj = {}, projectId = "", locked = true, libraryLocked = true, ready = false, generation = 0;
  let importedResource: Obj | null = null, readingImport = false, importGeneration = 0;
  const drafts = new Map<string, Draft>(), libraryChoices: HTMLButtonElement[] = [];
  const draft = (): Draft => {
    let value = drafts.get(projectId);
    if (!value) {
      const saved = catalog.project_id === projectId ? object(object(catalog.binding).training) : {};
      value = { resource: "", prediction: "", reason: "", improvement: "", features: words(saved.feature_columns), groups: words(saved.split_group_columns),
        fitLimit: typeof saved.fit_limit === "number" ? saved.fit_limit : 20 }; drafts.set(projectId, value);
    }
    return value;
  };
  const resources = (): Obj[] => objects(catalog.resources);
  const selected = (): Obj | undefined => resources().find(resource => resourceKey(resource) === selection.value);
  const binding = (): Obj => object(catalog.binding);
  function controls(): void {
    const editable = ready && !locked && !!projectId && catalog.project_id === projectId && catalog.state_version === project.state_version;
    fields.disabled = !editable;
    const raw = rawDesign(selected() ?? {}), fit = fitLimit.valueAsNumber, budget = object(catalog.budget);
    const minimumFit = Math.max(1, typeof budget.fit_limit === "number" ? budget.fit_limit : 1); fitLimit.min = String(minimumFit);
    const featureCount = featureOptions.querySelectorAll("input:checked").length;
    for (const input of featureOptions.querySelectorAll<HTMLInputElement>("input")) input.disabled = featureCount >= 16 && !input.checked;
    const trainingReady = featureCount > 0 && featureCount <= 16 && groupOptions.querySelectorAll("input:checked").length > 0
      && Number.isInteger(fit) && fit >= minimumFit && fit <= 40;
    bind.disabled = !editable || !catalog.target_column || !selected() || !(raw ? trainingReady : prediction.value) || !reason.value.trim();
    improveFields.disabled = !editable;
    improveButton.disabled = !editable || catalog.suggested_improvement !== true || !improveReason.value.trim();
    importFields.disabled = !ready || libraryLocked || readingImport;
    importButton.disabled = importFields.disabled || !importedResource;
    for (const button of libraryChoices) button.disabled = !editable;
  }
  function showSelection(): void {
    copy.replaceChildren(); const resource = selected();
    const raw = rawDesign(resource ?? {}); training.hidden = !raw; predictionField.hidden = raw; prediction.required = !raw; fitLimit.required = raw; fitLimit.disabled = !raw;
    bind.textContent = raw ? "保存原始数据训练设计" : "保存研究设计与预测列";
    reason.placeholder = raw ? "说明特征、分组划分和比较目的，以及采用该设计的依据" : "说明为何采用该设计，以及这列预测的来源与比较目的";
    if (raw) {
      const saved = draft(), groupColumns = words(catalog.group_columns);
      columnChecks(featureOptions, words(catalog.numeric_columns).filter(column => column !== catalog.target_column && !groupColumns.includes(column)), saved.features,
        values => { draft().features = values; controls(); });
      columnChecks(groupOptions, groupColumns, saved.groups, values => { draft().groups = values; controls(); }); fitLimit.value = String(saved.fitLimit);
    }
    if (resource) {
      designCopy(copy, resource);
      if (resourceKey(resource) !== resourceKey(object(binding().resource))) copy.append(el("p", "detail-note", "所选版本尚待明确保存为项目研究设计。"));
    }
    showFitBudget();
    controls();
  }
  function showFitBudget(): void {
    fitBudget.replaceChildren(); fitBudget.hidden = !rawDesign(selected() ?? {}) && !rawDesign(object(binding().resource));
    if (fitBudget.hidden) return;
    const budget = object(catalog.budget), count = (value: unknown): string => typeof value === "number" ? measure(value) : "未取得";
    fitBudget.append(el("h3", "", "当前项目的拟合用量"), el("p", "detail-note", "当前累计 fit 上限 " + count(budget.fit_limit) + " 次。"),
      metricSummary([["fit 尝试已用", count(budget.fit_attempts_used)], ["fit 已预留", count(budget.fits_reserved)],
      ["模型拟合", count(budget.new_fits)], ["预处理拟合", count(budget.preprocessing_fits)]], "当前项目累计拟合用量"));
  }
  function showResults(): void {
    results.replaceChildren(); const records = objects(catalog.checks);
    if (!records.length) results.append(el("p", "detail-note", "当前设计尚无验证结果。保存设计后，可到下方操作区选择实际候选并执行一步。"));
    else results.append(el("h3", "", "已保存的验证结果"));
    for (const record of records) {
      const entry = el("details", "research-design-result"); entry.open = records.length === 1;
      const predictionRange = object(record.prediction_range), n = predictionRange.n, negative = predictionRange.negative_predictions;
      const rangeNote = ["random_cv", "group_cv"].includes(text(record.check)) && typeof n === "number" && Number.isFinite(n)
        && typeof negative === "number" && Number.isFinite(negative) ? " · 负预测 " + measure(negative) + " / " + measure(n) : "";
      entry.append(el("summary", "", (checkNames[text(record.check)] ?? text(record.check)) + " · " + (statuses[text(record.status)] ?? text(record.status)) + rangeNote));
      if (Object.keys(object(record.summary)).length) {
        if (record.check === "negative_control") showNegativeControl(entry, record); else showMetrics(entry, record);
      }
      list(entry, "结果边界", words(record.limitations));
      if (record.protocol) entry.append(rawRecord(object(record.protocol), "查看本次划分、训练与评价协议"));
      entry.append(rawRecord(record, "查看指标、发现与行动原记录")); results.append(entry);
    }
    showFeatureComparisons(results, objects(catalog.feature_comparisons));
  }
  function showAssessment(): void {
    assessment.replaceChildren(); const value = object(catalog.assessment), bound = binding(), resource = object(bound.resource);
    const raw = rawDesign(resource), boundTraining = object(bound.training);
    bindingNote.textContent = text(resource.id, "") ? "已采用 " + text(resource.title, text(resource.id)) + " v" + String(resource.version)
      + (raw ? " · 特征 " + words(boundTraining.feature_columns).join("、") + " · 拆分组 " + words(boundTraining.split_group_columns).join("、")
        : " · 保存预测列 " + text(bound.prediction_column)) + " · 项目设计修订 " + String(bound.version)
      : "尚未绑定研究设计。选择库内版本、核对输入声明并填写采用理由。";
    const title = value.status === "review_ready" ? "规定检查记录已齐" : value.status === "incomplete" ? "验证尚未完成" : "等待选择研究设计";
    assessment.append(el("h3", "", title), el("p", "", text(value.reason)));
    const missing = words(value.missing_checks);
    if (missing.length) assessment.append(el("p", "", "下一项验证 · " + (checkNames[missing[0]] ?? missing[0])), el("p", "detail-note", "待完成 · " + missing.map(check => checkNames[check] ?? check).join("、")));
    if (words(value.skipped_checks).includes("grouped")) assessment.append(el("p", "detail-note", "分组核对未适用 · 当前项目未声明分组字段。"));
    if (typeof value.claim_supported === "boolean") assessment.append(el("p", "", value.claim_supported ? "当前样本中的误差比较支持所声明主张。" : "当前检查结果尚未支持所声明主张。"));
    const comparison = object(value.comparison);
    const comparisonMetrics: string[][] = [];
    for (const [key, label] of [["random_cv_mae", "随机验证 MAE"], ["group_cv_mae", "分组验证 MAE"],
      ["group_to_random_mae_ratio", "分组 / 随机 MAE"], ["conditional_rank", "负对照条件秩"]]) {
      const value = comparison[key];
      if (typeof value === "number" && Number.isFinite(value)) comparisonMetrics.push([label, measure(value) + (key === "group_to_random_mae_ratio" ? " 倍" : "")]);
    }
    if (comparisonMetrics.length) assessment.append(metricSummary(comparisonMetrics, "已保存的评价指标"));
    const sizes = object(comparison.train_sizes);
    const trainingSizes: string[] = [];
    for (const [key, label] of [["random_cv", "随机"], ["group_cv", "按组"]]) {
      const value = sizes[key], counts = Array.isArray(value) ? value.filter((item): item is number => typeof item === "number" && Number.isFinite(item)) : [];
      if (counts.length) trainingSizes.push(label + " " + measure(Math.min(...counts)) + "–" + measure(Math.max(...counts)));
    }
    if (raw && trainingSizes.length) assessment.append(el("p", "detail-note", "每折训练样本数：" + trainingSizes.join("；") + "。"
      + (trainingSizes.length === 2 ? "样本量与组分布可能同时改变，误差差异不能单独归因于分组。" : "")));
    if (comparison.all_groups_singleton === true) assessment.append(el("p", "detail-note", "当前每个声明组都只有1条记录，本次比较没有检验组内重复跨折带来的偏差。"));
    if (catalog.model_calls === 0) assessment.append(el("p", "detail-note", "本次研究设计操作的语言模型调用为0。"));
    next.hidden = !text(resource.id, ""); improve.hidden = !text(resource.id, "") || raw;
    if (bound.reason) assessment.append(el("p", "detail-note", "本次采用理由 · " + text(bound.reason)));
    if (text(resource.id, "")) assessment.append(rawRecord(bound, "查看已采用设计与绑定原记录"));
  }
  function choose(resource: Obj): void {
    draft().resource = resourceKey(resource); selection.value = draft().resource; showSelection(); formDetails.open = true;
    location.hash = "#/research?focus=design";
    host.announce(rawDesign(resource) ? "已选择资源版本，请明确选择训练特征、拆分组与累计fit上限，再填写采用理由。" : "已选择资源版本，请核对保存预测列并填写采用理由。");
  }
  function showLibrary(): void {
    libraryItems.replaceChildren(); libraryChoices.length = 0;
    const entries = resources(); libraryStatus.textContent = entries.length ? "共 " + entries.length + " 个资源版本。" : "资源目录暂无可用设计。";
    for (const resource of entries) {
      const item = el("article", "research-design-resource"), heading = el("header", "research-design-resource-heading");
      heading.append(el("h3", "", text(resource.title)), el("span", "research-design-version", "v" + String(resource.version) + " · " + (statuses[text(resource.status)] ?? text(resource.status))));
      const usage = typeof resource.usage_count === "number" ? "已用于 " + resource.usage_count + " 个项目" : "使用次数未记录";
      item.append(heading, el("p", "detail-note", usage + (resource.parent_version ? " · 由 v" + String(resource.parent_version) + " 修订" : " · 初始版本")), el("p", "", text(resource.claim)));
      const details = el("details", "research-design-resource-details"), content = el("div", "research-design-copy");
      details.append(el("summary", "", "查看问题、竞争解释与检查计划")); designCopy(content, resource);
      content.append(el("h4", "", "版本形成依据"), el("p", "", text(resource.change_reason)));
      const sources = el("ul");
      for (const source of words(resource.sources)) {
        const row = el("li"), url = safeUrl(source);
        if (url) { const link = el("a", "text-button", source); link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer"; row.append(link); }
        else row.textContent = source;
        sources.append(row);
      }
      if (sources.childElementCount) content.append(el("h4", "", "来源"), sources);
      details.append(content, rawRecord(resource, "查看资源 JSON")); item.append(details);
      const actions = el("div", "local-actions"), select = el("button", "quiet-button", "选择此版本"); select.type = "button";
      select.hidden = !projectId; select.addEventListener("click", () => choose(resource)); libraryChoices.push(select);
      const download = el("button", "text-button", "导出 JSON"); download.type = "button";
      download.addEventListener("click", () => {
        const url = URL.createObjectURL(new Blob([JSON.stringify(resource, null, 2) + "\n"], { type: "application/json" }));
        const link = el("a"); link.href = url; link.download = text(resource.id, "research-design") + "-v" + String(resource.version) + ".json"; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      });
      actions.append(select, download); item.append(actions); libraryItems.append(item);
    }
  }
  function invalidate(): void {
    generation++; ready = false; status.textContent = "正在核对当前研究设计…"; libraryStatus.textContent = "正在读取资源目录…";
    bindingNote.textContent = ""; copy.replaceChildren(); results.replaceChildren(); assessment.replaceChildren(); next.hidden = true; improve.hidden = true;
    fitBudget.replaceChildren();
    section.setAttribute("aria-busy", "true"); controls();
  }
  async function update(value: Obj): Promise<void> {
    const token = ++generation; ready = false; project = value; projectId = text(value.id, ""); controls();
    try {
      const result = await host.read("/api/local-workbench/designs");
      if (token !== generation) return;
      if (result.schema_version !== "research-design-catalog-v1" || result.project_id !== (projectId || null) || projectId && result.state_version !== project.state_version)
        throw Error("研究设计与当前项目版本不一致，请只读刷新后核对。");
      catalog = result; const saved = draft(), bound = binding();
      if (!saved.resource && object(bound.resource).id) saved.resource = resourceKey(object(bound.resource));
      if (!saved.prediction && bound.prediction_column) saved.prediction = text(bound.prediction_column, "");
      selection.replaceChildren(); const placeholder = el("option", "", "选择研究设计版本"); placeholder.value = ""; selection.append(placeholder);
      for (const resource of resources()) { const option = el("option", "", text(resource.title) + " · v" + String(resource.version) + " · " + (statuses[text(resource.status)] ?? text(resource.status))); option.value = resourceKey(resource); selection.append(option); }
      selection.value = saved.resource;
      prediction.replaceChildren(); const empty = el("option", "", "选择 CSV 中已保存的预测列"); empty.value = ""; prediction.append(empty);
      for (const column of words(result.prediction_columns)) { const option = el("option", "", column); option.value = column; prediction.append(option); }
      prediction.value = saved.prediction; reason.value = saved.reason; improveReason.value = saved.improvement;
      targetNote.textContent = result.target_column ? "比较目标为已声明字段 " + text(result.target_column) + "。保存预测设计读取现有预测列；原始数据设计按所选特征在训练折内拟合。" : "当前尚未声明目标字段，请先核对项目输入与字段声明。";
      status.textContent = projectId ? "核对主张和竞争解释，再按检查计划验证。" : "先在项目总览创建或选择课题。知识空间可直接浏览研究设计资源。";
      status.classList.remove("error"); libraryStatus.classList.remove("error"); if (!bound.resource) formDetails.open = true;
      ready = true; showSelection(); showResults(); showAssessment(); showLibrary();
    } catch (error) {
      if (token !== generation) return;
      const message = error instanceof Error ? error.message : "研究设计读取失败，请只读刷新保存状态。";
      status.textContent = message; libraryStatus.textContent = message; status.classList.add("error"); libraryStatus.classList.add("error");
    } finally { if (token === generation) { section.setAttribute("aria-busy", "false"); controls(); } }
  }
  selection.addEventListener("change", () => { draft().resource = selection.value; showSelection(); });
  prediction.addEventListener("change", () => { draft().prediction = prediction.value; controls(); });
  reason.addEventListener("input", () => { draft().reason = reason.value; controls(); });
  improveReason.addEventListener("input", () => { draft().improvement = improveReason.value; controls(); });
  fitLimit.addEventListener("input", () => { draft().fitLimit = fitLimit.valueAsNumber; controls(); });
  form.addEventListener("submit", event => {
    event.preventDefault(); const resource = selected(); if (bind.disabled || !resource || !form.reportValidity()) return;
    const body = { project_id: projectId, expected_state_version: project.state_version, resource_id: resource.id, resource_version: resource.version, reason: reason.value.trim() };
    void host.submit("design-bind", rawDesign(resource) ? { ...body, prediction_column: null,
      training: { feature_columns: draft().features, split_group_columns: draft().groups, fit_limit: fitLimit.valueAsNumber } }
      : { ...body, prediction_column: prediction.value });
  });
  improveForm.addEventListener("submit", event => {
    event.preventDefault(); if (improveButton.disabled || !improveForm.reportValidity()) return;
    void host.submit("design-improve", { project_id: projectId, expected_state_version: project.state_version, reason: improveReason.value.trim() });
  });
  importFile.addEventListener("change", () => { void (async () => {
    const file = importFile.files?.[0], token = ++importGeneration; importedResource = null; readingImport = !!file; controls();
    importStatus.classList.remove("error");
    if (!file) { importStatus.textContent = "尚未选择资源文件。"; return; }
    importStatus.textContent = "正在读取资源 JSON…";
    try {
      if (file.size > 4 * 1024 * 1024) throw Error("资源JSON文件上限为4 MiB，请核对文件。");
      const parsed = object(JSON.parse(await file.text())); if (token !== importGeneration) return;
      if (parsed.schema_version !== "research-design-resource-v1" || resourceFields.some(key => !(key in parsed))) throw Error("请选择包含完整研究设计协议字段的 research-design-resource-v1 文件。");
      importedResource = Object.fromEntries(resourceFields.map(key => [key, parsed[key]]));
      importStatus.textContent = "已读取 " + text(parsed.title, text(parsed.id)) + " v" + String(parsed.version) + "。点击导入后保存到资源目录。";
    } catch (error) {
      if (token !== importGeneration) return;
      importStatus.textContent = error instanceof Error ? error.message : "资源读取失败，请核对JSON内容。"; importStatus.classList.add("error");
    } finally { if (token === importGeneration) { readingImport = false; controls(); } }
  })(); });
  importForm.addEventListener("submit", event => { event.preventDefault(); void (async () => {
    if (importButton.disabled || !importedResource) return;
    const result = await host.submit("design-import", { resource: importedResource });
    importStatus.classList.toggle("error", !result);
    importStatus.textContent = result ? "研究设计资源已保存，可在下方目录查看并选择。" : "导入尚未确认完成，请查看页面顶部提示并核对原请求。文件内容已保留。";
  })(); });
  controls();
  return { element: section, libraryElement: library, update, invalidate, setLocked(value, libraryValue = value) { locked = value; libraryLocked = libraryValue; controls(); },
    resolved(name, requestId) { return ["design-bind", "design-improve", "design-import"].includes(name) && (words(catalog.completed_requests).includes(requestId)
      || name === "design-bind" && binding().request_id === requestId); } };
}
