/** Read saved active-project facts; this page never submits research commands. */
import { $, el, field, numeric, safeUrl } from "./dom";
import { recipeName, recipeOrder, recipeReason } from "./local-recipe";

type Obj = Record<string, unknown>;
const isObject = (value: unknown): value is Obj => !!value && typeof value === "object" && !Array.isArray(value);
const object = (value: unknown): Obj => isObject(value) ? value : {};
const objects = (value: unknown): Obj[] => Array.isArray(value) ? value.filter(isObject) : [];
const words = (value: unknown): string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
const string = (value: unknown, fallback = "未记录"): string => typeof value === "string" && value.length ? value : fallback;
const pretty = (value: unknown): string => JSON.stringify(value, null, 2) ?? "未记录";

const states: Record<string, string> = {
  active: "可继续", waiting: "等待资料", stopped: "已停止", ready: "待执行", running: "执行中",
  pending: "等待结果", completed: "执行完成", failed: "执行失败", unknown: "结果未知",
  needs_review: "待核对", not_executed: "尚未执行", satisfied: "所列条件满足",
  uncertain: "条件待确认", not_applicable: "不适用", unresolved: "尚未解决",
};
const state = (value: unknown): string => states[string(value)] ?? "状态未记录";
const methodNames: Record<string, string> = {
  "p02.saved-oof-residuals": "保存预测的残差诊断",
  "p02.source-mapping-check": "来源与测量映射核对",
  "materials.saved-steel-audit": "钢材保存模型的预测复核",
  "software.source-integrity-check": "软件文件读取与完整性检查",
  "data.tabular-quality-audit": "表格质量与分组核对",
  "data.grouped-quality-profile": "分组质量画像",
  "data.workbook-projection-check": "CSV与工作簿保存值核对",
  "research.source-selection": "补充来源与条件证据",
};
const policyNames: Record<string, string> = {
  recorded_equal_batch: "保留零值 · 批次等权", recorded_equal_section: "保留零值 · 分区等权",
  positive_equal_batch: "仅正计数 · 批次等权", positive_equal_section: "仅正计数 · 分区等权",
};
const method = (value: unknown): string => methodNames[string(value)] ?? "后续检查";
const policy = (value: unknown): string => policyNames[string(value)] ?? string(value);
const dimension = (value: unknown): string => value === "chemistry" ? "化学分组" : value === "topography" ? "纹理分组" : "分组";
type Domain = "p02" | "materials" | "software" | "data" | "other";
function primaryMethod(project: Obj): string {
  return typeof project.primary_method === "string" ? project.primary_method
    : string(object(project.primary_method).id, string(object(project.initial_decision).method_id, ""));
}
function domain(project: Obj): Domain {
  const primary = primaryMethod(project);
  return primary.startsWith("materials.") ? "materials" : primary.startsWith("software.") ? "software"
    : primary.startsWith("p02.") ? "p02" : primary.startsWith("data.") ? "data" : "other";
}
const domainTitle: Record<Domain, string> = {
  p02: "P02 · 代理值诊断", materials: "材料 · 保存预测复核", software: "软件 · 文件读取核验", other: "项目 · 已保存状态",
  data: "数据 · 质量与分组核对",
};

function note(value: string, fallback: string): string {
  const tabularNeeds: Record<string, string> = {
    "Real task value and scientific source qualification remain unvalidated.": "真实任务价值与科学来源资格仍待验证。",
    "Original data provenance, access and license evidence; submitter declarations remain unverified.": "核对原始数据的来源、访问和许可证据，提交者声明仍未核验",
    "Confirm target meaning and unit before any scientific or training use.": "核对目标字段的含义和单位，再判断科研或训练用途",
    "Clarify the intended target or confirm this is an untargeted data-quality task.": "明确目标字段，或确认只做无目标字段的数据质量检查",
    "Confirm grouping and independence meaning against collection records.": "依据采集记录核对分组与样本独立性",
    "Obtain grouping or sampling-unit definitions; absent group columns do not prove independence.": "取得分组或采样单位定义，未声明分组不证明独立性",
    "Confirm the submitter-declared key's uniqueness and conflict-resolution rules.": "核对声明键的唯一性和冲突处理规则",
    "Original collection/group definitions and sample-unit records; grouped counts do not establish independence.": "补齐原始采集、分组定义与采样单位记录；分组计数不证明独立性",
    "Confirm target meaning, unit, zero/missing rules, provenance and license against original records.": "对照原始记录核对目标含义、单位、零值与缺失规则、来源及许可",
    "Resolve the original grouping fields for records counted separately as incomplete groups.": "为单独统计的分组不完整记录，查清原始分组字段",
    "Confirm the biological target/channel and actual units using source measurement records; raw red intensity is not approved as ALP.": "依据原始测量记录核对生物目标、通道及实际单位；原始红强度尚未确认可作为ALP",
    "Confirm group independence and technical-repeat semantics before any statistical learning; repeated group rows are not independent samples.": "在统计学习前核对分组独立性和技术重复含义；同组多行不等于独立样本",
    "No rows were removed or zeros imputed; table mechanics alone do not resolve prior processed-workbook column-role conflicts.": "原记录与零值均保留；机械核对仍不能解决既有处理工作簿的列角色冲突",
    "Three complete duplicate CSV records are retained; source/acquisition evidence must determine whether these are repeated measurements or accidental duplication, not automatic deduplication.": "3条完整重复记录仍保留；需用来源及采集记录区分重复测量或意外复制，不能自动删重",
    "Actual acquisition/run logs and original exported tables, plus the author conversion records or script linking them to the workbook and CSV rows.": "取得本次采集或运行日志、原始导出表，以及连接导出、工作簿和CSV行的作者转换记录或脚本",
    "Confirm endpoint identity and unit, zero/missing rules, provenance and license against original records.": "对照原始记录核对目标字段的含义与单位、零值与缺失规则、数据来源及许可",
    "Confirm grouping, sample units and independence; matching workbook caches do not establish these meanings.": "核对分组、采样单位和独立性；工作簿保存值相同不能证明这些含义",
    "Resolve the multiple exact candidate worksheets using original run and conversion records.": "用原始运行和转换记录，区分多个完全一致的候选工作表",
    "Identify the original worksheet and column transformation; no complete header candidate was found.": "查清原工作表和列转换；目前未找到完整列头匹配的候选",
    "completed quality feedback and a captured XLSX matching the submitted origin SHA": "先完成表格质量检查，并补充与声明来源一致的已捕获原工作簿",
  };
  if (tabularNeeds[value]) return tabularNeeds[value];
  const groupedPrefix = "Explain the observed group distributions without changing or deleting original values:";
  if (value.startsWith(groupedPrefix)) {
    const eventNames: Record<string, string> = { zero: "零值", empty: "空串", declared_missing: "声明缺失", invalid_numeric: "非法数值", nonfinite: "非有限值" };
    const events = value.slice(groupedPrefix.length).split(";").map(item => {
      const index = item.lastIndexOf(":");
      return index < 0 ? item.trim() : item.slice(0, index).trim() + "的" + (eventNames[item.slice(index + 1).trim()] ?? "事件");
    }).join("、");
    return "保留原值和全部行，解释这些组内分布：" + events;
  }
  if (value.startsWith("Resolve or explain observed mechanical flags without silently dropping rows or replacing values:"))
    return "解释已观察到的机械标记，保留原行与数值；详见完整记录";
  return /[\u3400-\u9fff]/.test(value) ? value : fallback;
}

function details(title: string, value: unknown, cls = ""): HTMLDetailsElement {
  const panel = el("details", "p02-original project-provenance " + cls);
  panel.append(el("summary", "", title), el("pre", "", pretty(value)));
  return panel;
}

function section(title: string, note?: string): HTMLElement {
  const panel = el("section", "project-section");
  const header = el("div", "section-header");
  header.append(el("h2", "section-title", title));
  if (note) header.append(el("p", "detail-note", note));
  panel.append(header);
  return panel;
}

function badge(value: unknown, prefix: string): HTMLElement {
  return el("span", "status-badge project-status", prefix + state(value));
}

function download(action: Obj): HTMLAnchorElement | null {
  if (typeof action.id !== "string" || !/^[A-Za-z0-9_.:-]{1,120}$/.test(action.id) || !action.artifact) return null;
  const link = el("a", "text-button", "下载本次完整结果 JSON ↓");
  link.href = "/api/project/artifact/" + encodeURIComponent(action.id);
  link.download = action.id + ".json";
  return link;
}

function sourceLink(value: unknown): HTMLAnchorElement | null {
  const url = safeUrl(value);
  if (!url) return null;
  const link = el("a", "text-button", "访问原始来源 ↗");
  link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer";
  return link;
}

function nextTitle(next: Obj): string {
  const action = object(next.next_action);
  if (action.kind === "reconcile_execution") return "先核对未知执行，保留原请求";
  if (action.kind === "review_saved_evidence") return "复用已有观察，继续核对证据";
  return method(action.method_id);
}

function resultTable(caption: string, headings: string[], values: string[][]): HTMLElement {
  const wrap = el("div", "project-comparison table-scroll");
  const table = el("table", "data-table");
  table.append(el("caption", "", caption));
  const head = el("thead"), header = el("tr");
  for (const title of headings) {
    const cell = el("th", "", title); cell.scope = "col"; header.append(cell);
  }
  head.append(header); table.append(head);
  const body = el("tbody");
  for (const cells of values) {
    const row = el("tr");
    cells.forEach((value, index) => {
      const cell = index === 0 ? el("th", "", value) : el("td", "", value);
      if (cell instanceof HTMLTableCellElement && index === 0) cell.scope = "row";
      row.append(cell);
    });
    body.append(row);
  }
  table.append(body); wrap.append(table); return wrap;
}

function comparison(action: Obj): HTMLElement {
  const observations = objects(action.observations);
  if (!observations.length) {
    const wrap = el("div", "project-comparison");
    wrap.append(el("p", "empty-state", "此行动尚无已保存观察。缺少结果不能记为成功或零误差。"));
    return wrap;
  }
  const grouped = observations.filter(item => item.kind === "grouped_oof_residuals");
  if (grouped.length) return resultTable("同一处理规则下，当前候选与化学基线比较",
    ["处理规则", "候选 MAE", "化学基线 MAE", "MAE 差值", "变差组 / 总组数"], grouped.map(observation => {
    const values = object(observation.values), candidate = object(values.current_candidate), baseline = object(values.chemistry);
    return [policy(observation.policy), numeric(candidate.mae), numeric(baseline.mae), numeric(candidate.delta_mae_vs_chemistry),
      `${numeric(candidate.worse_groups)} / ${numeric(candidate.group_count)}`];
  }));
  const steel = observations.filter(item => item.kind === "saved_steel_mse_audit");
  if (steel.length) {
    const counts = object(steel[0].sample_counts);
    return resultTable(`屈服强度预测 · 训练 ${numeric(counts.train)} 条 / 验证 ${numeric(counts.validation)} 条 · 保存模型复核`,
      ["多项式阶数", "正则 α", "训练 MSE（MPa²）", "验证 MSE（MPa²）", "原采用门槛下决定"], steel.map(observation => {
        const values = object(observation.values), candidate = object(values.candidate), scores = object(values.metrics);
        return [numeric(candidate.degree), numeric(candidate.alpha), numeric(scores.training_mse), numeric(scores.validation_mse),
          values.decision === "accepted" ? "保留" : values.decision === "rejected" ? "未采用" : "未记录"];
      }));
  }
  const audit = observations.find(item => item.kind === "tabular_quality_audit");
  if (audit) {
    const profile = object(audit.profile), groups = object(profile.group_columns), keys = object(profile.key_columns);
    const wrap = el("div", "project-tabular-quality"), summary = el("dl", "detail-dl");
    const measured = (value: unknown): string => typeof value === "number" ? numeric(value) : "未声明／未计算";
    const summaryRows: [string, unknown][] = [["数据记录", profile.rows], ["字段", profile.columns], ["完整重复的额外记录", profile.exact_duplicate_rows],
      ["完整分组数", groups.group_count], ["含多行的组数", groups.repeated_groups], ["分组字段缺失的记录", groups.incomplete_group_rows],
      ["声明键重复的额外记录", keys.duplicate_rows], ["同键内容不一致的组", keys.conflict_groups]];
    for (const [label, value] of summaryRows) field(summary, label, measured(value));
    wrap.append(el("p", "detail-note", profile.mechanical_status === "no_flags_in_selected_checks"
      ? "所列机械检查未见标记项；字段角色、单位与科学资格仍待核对。"
      : "机械检查发现需核对项；保留原记录，不自动填零或删行。"), summary,
      el("p", "detail-note", "重复分组表示同组含多行，不等于独立样本，也不自动判为错误。零值包含在有限值中；空值与声明缺失分别统计。"));
    wrap.append(resultTable("按声明的数值字段统计 · 保留原始缺失与非法值",
      ["字段", "有限值", "其中零值", "空值", "声明缺失", "非法数字", "非有限", "有限值范围"], objects(profile.numeric_columns).map(column => {
        const counts = object(column.counts);
        return [string(column.name), measured(counts.finite), measured(counts.zero), measured(counts.empty), measured(counts.declared_missing),
          measured(counts.invalid_numeric), measured(counts.nonfinite), typeof column.min === "number" && typeof column.max === "number" ? numeric(column.min) + " ～ " + numeric(column.max) : "未计算"];
      })), details("标记项、原始坐标与分组统计", { flags: profile.flags, examples: profile.examples, record_coordinates: profile.record_coordinates,
        group_columns: groups, key_columns: keys, scope: object(action.method_instance).scope }));
    const duplicates = objects(profile.examples).filter(item => item.kind === "exact_duplicate_row");
    if (duplicates.length) wrap.append(el("p", "detail-note", "完整重复代表定位（不含表头的数据记录）：" + duplicates.map(item =>
      `${numeric(item.logical_record)} ↔ ${numeric(item.first_logical_record)}（物理结束行 ${numeric(item.physical_line_end)} ↔ ${numeric(item.first_physical_line_end)}）`).join("；") + "。保留原行，仍需核对重复原因。"));
    return wrap;
  }
  const groupedQuality = observations.find(item => item.kind === "grouped_quality_profile");
  if (groupedQuality) {
    const summary = object(groupedQuality.summary), columns = objects(summary.numeric_columns);
    const kinds: [string, string][] = [["zero", "零值"], ["empty", "空串"], ["declared_missing", "声明缺失"],
      ["invalid_numeric", "非法数值"], ["nonfinite", "非有限"]];
    const wrap = el("div", "project-tabular-quality"), counts = el("dl", "detail-dl");
    for (const [label, value] of [["原记录", summary.rows], ["分组字段完整记录", summary.complete_group_rows],
      ["分组字段不完整记录", summary.incomplete_group_rows], ["完整组数", summary.group_count]] as [string, unknown][]) field(counts, label, numeric(value));
    wrap.append(el("p", "detail-note", "同一来源的后续方法，按原声明分组观察零值或缺失集中情况。原主方法和来源记录保留；不推断独立性或目标资格。"), counts,
      resultTable("完整组内事件数 / 受影响组数 · 最多显示8个数值字段", ["字段", ...kinds.map(([, label]) => label + "事件 / 组")], columns.slice(0, 8).map(column => {
        const concentration = object(column.concentration);
        return [string(column.name), ...kinds.map(([kind]) => {
          const item = object(concentration[kind]);
          return numeric(item.total) + " / " + numeric(item.affected_groups);
        })];
      })), el("p", "detail-note", "零值属于有限值；分组不完整记录另计，不参加完整组集中份额。组ID只标识原声明分组，不代表独立样本或新的类别。"));
    if (columns.length > 8) wrap.append(el("p", "detail-note", `其余 ${columns.length - 8} 个字段及全部分组见完整JSON。`));
    const examples = objects(groupedQuality.examples).slice(0, 5);
    if (examples.length) wrap.append(resultTable("代表定位 · 不含表头的逻辑记录 / 记录结束物理行（包含表头及带引号换行）",
      ["字段", "事件", "组ID节选", "逻辑记录 / 结束物理行"], examples.map(item => [string(item.column), kinds.find(([kind]) => kind === item.kind)?.[1] ?? "事件",
        item.group_id === null ? "分组不完整" : string(item.group_id).slice(0, 12), numeric(item.logical_record) + " / " + numeric(item.physical_line_end)])));
    else wrap.append(el("p", "detail-note", "没有所选事件的代表坐标；不据此批准数据或训练资格。"));
    wrap.append(details("完整集中统计、代表坐标与前序绑定", { summary, examples: groupedQuality.examples,
      predecessor: groupedQuality.predecessor, scope: groupedQuality.scope }));
    return wrap;
  }
  const workbookProjection = observations.find(item => item.kind === "workbook_projection_check");
  if (workbookProjection) {
    const summary = object(workbookProjection.summary), candidates = objects(workbookProjection.candidates);
    const wrap = el("div", "project-tabular-quality"), counts = el("dl", "detail-dl");
    for (const [label, value] of [["CSV数据记录", summary.csv_rows], ["CSV列数", summary.csv_columns],
      ["列头匹配的候选表", summary.candidate_sheet_count], ["完全一致候选", summary.exact_candidate_sheet_count]] as [string, unknown][]) field(counts, label, numeric(value));
    wrap.append(el("p", "detail-note", "比较已捕获原件的保存单元格。匹配结果是候选投影，实际运行、导出转换及样本含义仍需原记录核对。"), counts);
    if (candidates.length) {
      const comparison = resultTable("候选工作表",
      ["工作表", "逐字一致 / 比较格", "数值同、文本异", "值或类型不符", "缺行 / 多行", "公式缓存格"], candidates.slice(0, 6).map(candidate =>
        [string(candidate.sheet), numeric(candidate.exact_matches) + " / " + numeric(candidate.compared_cells),
          numeric(candidate.numeric_equal_text_diff), numeric(candidate.mismatch_cells),
          numeric(Array.isArray(candidate.missing_workbook_rows) ? candidate.missing_workbook_rows.length : null) + " / " +
            numeric(Array.isArray(candidate.extra_workbook_rows) ? candidate.extra_workbook_rows.length : null), numeric(candidate.formula_cells)]));
      comparison.querySelector("table")?.setAttribute("aria-label", "候选工作表");
      comparison.querySelector("caption")?.remove();
      wrap.append(el("h4", "", "候选工作表"), comparison);
      if (candidates.length > 6) wrap.append(el("p", "detail-note", `此处显示前6张，其余 ${candidates.length - 6} 张见下方完整候选定位。`));
    } else wrap.append(el("p", "detail-note", "没有完整列头匹配的候选。需核对实际工作表或列转换，不能视为核对通过。"));
    const exact = words(summary.exact_candidate_sheets);
    if (exact.length) wrap.append(el("p", "detail-note", "保存值完全一致候选：" + exact.slice(0, 6).join("、") +
      (exact.length > 1 ? "。多个候选仍有歧义，不能自动选择第一张。" : "。单一候选也不确认作者实际转换、ALP、单位或独立性。")));
    wrap.append(details("原件、前序与完整候选定位", { origin: workbookProjection.origin, predecessor: workbookProjection.predecessor,
      candidates: workbookProjection.candidates, scope: workbookProjection.scope }));
    return wrap;
  }
  const checks = observations.filter(item => item.kind === "software_file_io_check");
  if (checks.length) {
    const caseNames: Record<string, string> = { normal_capture: "正常来源读取", controlled_midread_append: "读取中追加内容",
      sha_mismatch: "内容 SHA 不匹配", task_mismatch: "任务绑定不匹配", path_traversal: "来源路径越界" };
    const codes: Record<string, string> = { EVIDENCE_CHANGED: "拒绝已变化来源", TASK_MISMATCH: "拒绝不匹配任务", UNSAFE_PATH: "拒绝越界路径" };
    return resultTable("本机文件读取检查 · 故障注入不代表真实生产事故", ["案例", "类型", "预期", "实际", "结果"], checks.map(observation => {
      const values = object(observation.values), normal = observation.classification === "actual_normal_io";
      return [caseNames[string(observation.case_id)] ?? "文件读取检查", normal ? "正常 I/O" : "受控故障注入",
        normal ? "完整读取且身份稳定" : codes[string(values.expected_code)] ?? "按约定拒绝",
        normal ? values.passed === true ? "已完整读取且元数据稳定" : "未满足原读取约定" : codes[string(values.actual_code)] ?? "见原始记录",
        values.passed === true ? "符合预期" : values.passed === false ? "不符合预期" : "未记录"];
    }));
  }
  return details("此方法的完整观察记录", observations);
}

function executionRecords(project: Obj): HTMLElement {
  const kind = domain(project);
  const notes: Record<Domain, string> = {
    p02: "数值负结果保留为有效观察。差值为正表示候选误差更高；不同目标处理规则不能排成优劣榜。",
    materials: "只复核保存模型与原采用门槛。MSE 单位为 MPa²；采用与科学有效性分别判断。",
    software: "展示实际文件读取和受控故障注入，保留预期、真实返回与未通过项，不推断生产事故。",
    data: "对本次捕获的表格做机械检查；字段角色和单位为提交者声明，检查完成不批准科研或训练资格。",
    other: "以下是实际保存的观察与决定；计划和下一任务不计为已经执行。",
  };
  const panel = section("实际执行与反馈", notes[kind]);
  panel.append(el("p", "project-table-hint", "左右滑动查看完整指标与分组数量。"));
  const list = el("div", "project-actions");
  for (const action of objects(project.actions)) {
    const card = el("article", "project-action evidence-card content-section");
    const title = action.command === "p02.saved-oof-residuals" ? dimension(action.dimension) + "残差诊断" : method(action.command);
    card.append(el("h3", "", title), badge(action.status, "执行："));
    card.append(comparison(action));
    const next = object(action.next_decision);
    if (Object.keys(next).length) card.append(el("p", "detail-note", "反馈后的决定：" + nextTitle(next) + "；下一任务仍需另行执行。"));
    if (action.failure) card.append(details("失败或未知的原始记录", action.failure));
    const link = download(action); if (link) card.append(link);
    card.append(details("行动身份与原始决策理由", { id: action.id, request_id: action.request_id,
      result_sha256: action.result_sha256, next_decision: action.next_decision }));
    list.append(card);
  }
  for (const action of objects(project.evidence_actions)) {
    const card = el("article", "project-action evidence-card content-section");
    card.append(el("h3", "", "读取已登记来源选区"), badge(action.status, "执行："),
      el("p", "", `已保存 ${objects(action.observations).length} 条提取观察。读取完成不表示资料解释或适用条件已获确认。`));
    const remaining = words(object(action.next_decision).remaining_questions);
    if (remaining.length) {
      const questions = el("ul", "project-questions");
      for (const question of remaining) questions.append(el("li", "", note(question, "仍有具体条件未确认，见原记录。")));
      card.append(el("h4", "", "仍缺的资料"), questions);
      card.append(details("未解决问题（完整原记录）", remaining));
    }
    const link = download(action); if (link) card.append(link);
    if (action.failure) card.append(details("失败或未知的原始记录", action.failure));
    list.append(card);
  }
  if (!list.children.length) list.append(el("p", "empty-state", "当前项目还没有执行记录；初始决定是待执行提案。"));
  panel.append(list); return panel;
}

function excerpts(project: Obj): HTMLElement {
  const panel = section("已读取的来源片段", "展开查看完整提取文本和原始定位。这里只覆盖实际选区，提交者概括与来源正文分别保留。");
  const list = el("div", "project-excerpts");
  for (const action of objects(project.evidence_actions)) {
    for (const observation of objects(action.observations)) {
      const refs = objects(observation.evidence_refs), first = refs[0] ?? {}, locator = object(first.locator);
      const item = el("details", "project-source p02-original evidence-card");
      item.append(el("summary", "", `${string(observation.selection_id, "来源选区")} · ${string(locator.kind, "定位")} ${string(locator.value, "未提供")}`));
      item.append(el("p", "detail-note", "提取观察已保存；资料解释与适用条件仍待核对。"));
      item.append(el("pre", "project-source-text", string(observation.exact_text, "此记录没有可显示的提取文本。")));
      const claim = object(observation.submitted_claim);
      if (typeof claim.text === "string") {
        item.append(el("h4", "", "提交者概括 · 尚未核验"), el("p", "", claim.text));
      }
      const link = sourceLink(first.url); if (link) item.append(link);
      if (typeof first.license_note === "string") item.append(el("p", "detail-note", first.license_note));
      item.append(details("完整来源坐标、SHA 与提交身份", { evidence_refs: refs, contributor: claim.contributor,
        mapping_status: observation.mapping_status, endpoint_eligibility: observation.endpoint_eligibility }));
      list.append(item);
    }
  }
  if (!list.children.length) list.append(el("p", "empty-state", "尚无已保存的来源提取观察。登记来源或提出取证任务，都不等于已经读取。"));
  panel.append(list); return panel;
}

function methods(project: Obj): HTMLElement {
  const panel = section("当前方法条件", "条件满足只表示可执行该范围内的检查，不保证研究结论成立。");
  const list = el("div", "project-methods");
  for (const option of objects(project.method_options)) {
    const card = el("article", "project-method evidence-card content-section");
    card.append(el("h3", "", method(option.method_id)), badge(option.condition, "条件："));
    if (option.completed === true) card.append(el("p", "", "相同范围已有完整结果，优先复用原观察。"));
    if (typeof option.source_readable === "number") card.append(el("p", "", `已登记可读选区：${numeric(option.source_readable)}；可读不表示条件已确认。`));
    const missing = words(option.missing_information);
    if (missing.length) card.append(el("p", "detail-note", "仍缺：" + missing.map(value => note(value, "所需输入或条件资料，见原记录")).join("；")));
    card.append(details("条件依据与允许参数（原记录）", { reasons: option.reasons,
      missing_information: missing, parameters: option.parameters, reusable_action_ids: option.reusable_action_ids,
      unresolved_execution_ids: option.unresolved_execution_ids }));
    list.append(card);
  }
  if (!list.children.length) list.append(el("p", "empty-state", "当前快照没有方法条件记录。"));
  panel.append(list); return panel;
}

function searchHit(hit: Obj): HTMLElement {
  const card = el("article", "project-search-hit evidence-card content-section");
  const source = object(hit.source), metadata = object(source.metadata), locator = object(metadata.locator);
  card.append(el("h3", "", string(source.title, "来源检索片段")),
    el("p", "detail-note", `${string(locator.kind, "来源定位")} ${string(locator.value, "见完整引用")} · 宿主本地检索，未作科学批准`));
  card.append(el("blockquote", "project-source-text", string(hit.quote, "没有可显示的原文节选。")));
  const link = sourceLink(source.source_url); if (link) card.append(link);
  card.append(details("引用身份与完整定位", { citation_id: hit.citation_id, source_sha256: source.sha256,
    locator: metadata.locator, location: hit.location, source_id: metadata.source_id }));
  return card;
}

function search(project: Obj): HTMLElement {
  const panel = section("在已读取来源中查找", "只检索已提取并保存的本地片段；命中不代表模型已经使用，更不代表科学结论成立。");
  panel.classList.add("project-search");
  const form = el("form", "project-search-form question-form"), controls = el("div", "project-search-controls");
  const pointLabel = el("label", "", "用于哪一步判断"), point = el("select", "project-search-point");
  point.id = "project-knowledge-point"; point.name = "point";
  for (const [value, label] of [["clarification", "问题澄清"], ["design", "方法选择"], ["preparation", "执行准备"], ["interpretation", "反馈解释"]]) {
    const option = el("option", "", label); option.value = value; point.append(option);
  }
  point.value = "interpretation"; pointLabel.htmlFor = point.id; pointLabel.append(point);
  const needLabel = el("label", "", "需要核对什么"), input = el("input", "project-search-input");
  input.id = "project-knowledge-need"; input.name = "need"; input.type = "search"; input.required = true; input.maxLength = 512;
  const placeholders: Record<Domain, string> = { p02: "例如 CropRed、NaN、batch 或导出列",
    data: "例如 group_columns、missing_tokens、target_unit 或字段定义",
    materials: "例如 heat treatment、composition 或加工条件", software: "例如 ctime、SHA、任务绑定或读取中变更", other: "输入来源中的关键词" };
  input.placeholder = placeholders[domain(project)]; needLabel.htmlFor = input.id; needLabel.append(input);
  const submit = el("button", "action-button", "查找来源片段"); submit.type = "submit";
  const status = el("p", "project-search-status form-feedback", "选择判断环节，输入原文关键词后查找。");
  status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite"); status.setAttribute("aria-atomic", "true");
  const results = el("div", "project-search-results");
  controls.append(pointLabel, needLabel, submit); form.append(controls, status); panel.append(form, results);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity() || submit.disabled) return;
    const need = input.value.trim();
    if (!need) { status.textContent = "请输入要核对的关键词。"; input.focus(); return; }
    submit.disabled = true; submit.textContent = "正在查找…"; results.replaceChildren();
    results.setAttribute("aria-busy", "true"); status.textContent = "正在读取本地来源片段…";
    try {
      const params = new URLSearchParams({ need, point: point.value });
      const response = await fetch("/api/project/knowledge?" + params.toString(), { cache: "no-store", signal: AbortSignal.timeout(15000) });
      if (!response.ok) throw Error("来源检索暂不可用，请保留关键词后重试。");
      const value: unknown = await response.json();
      if (!isObject(value) || !Array.isArray(value.evidence)) throw Error("来源检索返回的记录不完整，请重试。");
      if (!panel.isConnected) return;
      const hits = objects(value.evidence);
      if (hits.length) {
        for (const hit of hits) results.append(searchHit(hit));
        status.textContent = `找到 ${hits.length} 个已保存片段。相关性不代表证据有效性。`;
      } else {
        status.textContent = "当前选区没有匹配结果。";
        results.append(el("p", "empty-state", "可更换原文关键词。零命中只说明当前已提取选区未匹配，不表示原文件或所需证据不存在。"));
      }
    } catch (error) {
      if (panel.isConnected) status.textContent = error instanceof Error && error.name === "TimeoutError"
        ? "检索超时，请稍后重试；输入内容已保留。"
        : "来源检索暂不可用，请稍后重试；输入内容已保留。";
    } finally {
      submit.disabled = false; submit.textContent = "查找来源片段"; results.removeAttribute("aria-busy");
    }
  });
  return panel;
}

function boundaries(project: Obj): HTMLElement {
  const panel = section("范围与资源记录"); panel.classList.add("project-boundary", "content-section", "notice");
  const scopeNotes: Record<Domain, string> = {
    data: "本次只检查声明的CSV字段、缺失、重复与分组。分组键不证明记录或样本独立性；目标含义与单位仍需来源核对，原文、缺失与零值均保留。",
    p02: "当前诊断限定原始红通道代理值与冻结的探索性 OOF，不确认 ALP、机制或独立外部泛化。来源读取和格式校验也不提供科学批准。",
    materials: "当前任务复核钢材屈服强度的保存模型，采用自定义组成分组划分；不是 Matbench 官方五折成绩，不证明新材料效果、加工机制或独立外部泛化。",
    software: "当前记录限定本机文件读取与五项受控检查。故障注入不是生产事故，也不证明所有操作系统、文件系统或安全边界均已验证。",
    other: "结果仅适用于已登记来源、工具与执行环境；未记录的外部验证和真实使用收益保持未知。",
  };
  const hasSelections = objects(object(project.selection_history).records).length > 0;
  panel.append(el("p", "", hasSelections ? "本页只读展示已保存行动、固定建议与提交的选择。查看、检索和下载不会执行新研究。" : "本页只读展示已保存行动。下一决定由固定本地规则产生，不是研究模型自主判断；查看、检索和下载不会执行新研究。"),
    el("p", "", scopeNotes[domain(project)]));
  const budget = object(project.budget), summary = el("dl", "project-budget detail-dl");
  const count = (value: unknown): string => typeof value === "number" && Number.isFinite(value) ? numeric(value) : "未知";
  for (const [label, value] of [
    ["本地工具检查", `${count(budget.local_tool_calls_used)} 次已用 / ${count(budget.local_tool_call_limit)} 次上限；预留 ${count(budget.local_tool_calls_reserved)}`],
    ["来源读取", `${count(budget.evidence_reads_used)} 次已用 / ${count(budget.evidence_read_limit)} 次上限；预留 ${count(budget.evidence_reads_reserved)}`],
    ...(typeof budget.source_request_limit === "number" ? [["公开来源 GET", `${count(budget.source_requests_used)} 次已用 / ${count(budget.source_request_limit)} 次上限；预留 ${count(budget.source_requests_reserved)}`]] : []),
    ["原生模型请求", `${count(budget.new_model_requests)} 次；本切片允许 ${count(budget.model_requests_allowed)} 次`],
    ["原生模型请求预留", count(budget.model_requests_reserved)],
    ["新增拟合", count(budget.new_fits)],
    ["历史模型请求", budget.historical_request_counts === null || budget.historical_request_counts === undefined ? "未知，未导入；不按 0 处理" : pretty(budget.historical_request_counts)],
    ["历史现金", budget.historical_spend_cny === null || budget.historical_spend_cny === undefined ? "未知，结算状态未确认；不按 0 处理" : `${count(budget.historical_spend_cny)} 元`],
  ]) field(summary, label, value);
  panel.append(summary, el("p", "detail-note", "CLI和子代理用量在“研究推进”中单独记录。历史预算引用只记录归属，不增加模型额度。原有现金上限与未知结算状态保留；AgentArts 产品接入仍暂缓。"),
    details("项目、预算归属与索引身份", { id: project.id, state_version: project.state_version,
      lineage_ref: budget.lineage_ref, cash_settlement: budget.cash_settlement,
      existing_cash_cap_cny: budget.existing_cash_cap_cny, domain_scope: project.domain_scope,
      primary_method: project.primary_method, knowledge_refs: project.knowledge_refs }));
  return panel;
}

function reportState(project: Obj): { ready: boolean; message: string } {
  const report = object(project.report);
  if (report.stale === true) return { ready: false, message: "项目已有更新，原报告不再对应当前快照；重新导出后可下载。" };
  if (report.available === true) return { ready: true, message: "报告已绑定当前项目快照，包含已保存观察、下一决定与未完成边界。" };
  return { ready: false, message: "当前项目快照尚无可用报告，导出后再下载。" };
}

function reports(project: Obj): HTMLElement {
  const panel = section("当前快照报告"), status = reportState(project), actions = el("div", "hero-actions project-report-actions");
  panel.append(el("p", "detail-note", status.message));
  for (const [href, filename, label] of [
    ["/api/project/report.pdf", "project-report.pdf", "当前快照报告 PDF ↓"],
    ["/api/project/report.json", "project-report.json", "当前快照报告 JSON ↓"],
    ["/api/project/report.md", "project-report.md", "Markdown 正文 ↓"],
    ["/api/project/input.json", "project-input.json", "复现输入 JSON ↓"],
  ]) {
    if (status.ready) {
      const link = el("a", "action-button", label);
      link.href = href; link.download = filename; actions.append(link);
    } else {
      const button = el("button", "action-button", label); button.type = "button"; button.disabled = true;
      button.title = status.message; actions.append(button);
    }
  }
  panel.append(actions); return panel;
}

function choiceTitle(project: Obj, action: Obj): string {
  if (action.kind === "external_wait") return "本次选择等待";
  const parameters = object(action.parameters);
  if (typeof parameters.receipt_snapshot_sha256 === "string") {
    const receipt = parameters.receipt_snapshot_sha256;
    const registered = objects(project.registered_evidence).find(item => item.receipt_snapshot_sha256 === receipt);
    const saved = objects(project.evidence_actions).find(item => item.receipt_snapshot_sha256 === receipt && item.status === "completed");
    const names = new Set(objects(saved?.observations).flatMap(item => objects(item.evidence_refs).map(ref => string(ref.source_id, ""))).filter(Boolean));
    const label = typeof registered?.ordinal === "number" ? `第${numeric(registered.ordinal)}份登记资料` : "已登记资料";
    return label + (names.size ? " · " + [...names].join("、") : registered?.read_status === "unread" ? "（尚未读取）" : "");
  }
  return method(action.method_id) + (parameters.dimension ? " · " + dimension(parameters.dimension) : "");
}

function selectionCard(project: Obj, record: Obj): HTMLElement {
  const card = el("article", "project-selection-card"), action = { kind: record.decision_kind, method_id: record.method_id, parameters: record.parameters };
  const provider = object(record.provider_claim), child = object(record.child), baseline = object(record.baseline_decision);
  const recipeDecision = object(record.recipe_decision), recipe = object(recipeDecision.recipe), isRecipe = recipeDecision.schema_version === "research-recipe-decision-v1";
  const providerNames: Record<string, string> = { operator_assistant: "开发助手", human: "人工提交", external_model: "外部模型声明" };
  card.append(el("h3", "", choiceTitle(project, action)));
  const statuses = el("div", "project-status-row");
  statuses.append(el("span", "status-badge project-status", record.decision_kind === "external_wait" ? "本请求没有新行动" : "关联行动：" + state(child.status ?? record.status)));
  card.append(statuses, el("p", isRecipe ? "detail-note project-recipe-note" : "detail-note", isRecipe ? `确定性科研配方：${recipeName(recipe)} · ${string(recipeDecision.recipe_id)} v${String(recipeDecision.recipe_version)}；选择不调用模型。`
    : "提交来源：" + (providerNames[string(provider.kind)] ?? "未记录") + "；来源声明尚未核验。"),
    el("p", "project-selection-rationale", isRecipe ? recipeReason(recipeDecision.reason) : string(record.rationale, "未保存选择理由。")));
  if (isRecipe) {
    card.append(el("p", "detail-note project-recipe-note", "方法顺序：" + recipeOrder(recipe)));
    for (const item of objects(recipeDecision.method_decisions)) card.append(el("p", "detail-note project-recipe-note",
      (item.outcome === "selected" ? "选用" : "跳过") + method(item.method_id) + "：" + recipeReason(item.reason) + "。"));
  }
  if (record.decision_kind === "external_wait") card.append(el("p", isRecipe ? "detail-note project-recipe-note" : "detail-note", isRecipe
    ? "这次等待没有创建新行动。取得新资料后可用新请求重新决定。"
    : "这次等待没有创建新行动。项目仍可继续，尚未读取的资料保留供下一次决定。"));
  const comparison = el("div", "project-selection-compare");
  for (const [label, title] of [["这次提交的选择", choiceTitle(project, action)], ["当时的固定建议", choiceTitle(project, object(baseline.next_action))]]) {
    const part = el("div", "project-selection-cell"); part.append(el("p", "overline", label), el("p", "", title)); comparison.append(part);
  }
  card.append(comparison);
  const evidence = objects(record.evidence), citations = el("details", "project-selection-citations");
  citations.append(el("summary", "", `查看本次引用（${evidence.length}处）`));
  for (const hit of evidence) {
    const source = object(hit.source), locator = object(source.locator), quote = el("div", "project-selection-citation");
    quote.append(el("p", "detail-note", `${string(locator.kind, "来源定位")} ${string(locator.value, "见完整记录")}`), el("blockquote", "project-source-text", string(hit.quote)));
    if (hit.quote_truncated === true) quote.append(el("p", "detail-note", "此处是当时选择上下文保存的节选，完整原文需核对来源。"));
    const link = sourceLink(source.url); if (link) quote.append(link);
    quote.append(details("引用身份与定位", { citation_id: hit.citation_id, source, location: hit.location })); citations.append(quote);
  }
  if (!evidence.length) citations.append(el("p", "detail-note", isRecipe ? "本次按宿主候选和配方顺序决定，未调用模型；没有声明引用来源摘录。"
    : "本次提案没有声明引用上下文片段；不能据此推断模型已读取资料。"));
  card.append(citations);
  if (typeof record.request_id === "string" && /^[A-Za-z0-9_.:-]{1,80}$/.test(record.request_id)) {
    const link = el("a", "text-button", "下载这次选择的完整记录 JSON ↓");
    link.href = "/api/project/selection-request/" + encodeURIComponent(record.request_id) + ".json"; link.download = record.request_id + ".json"; card.append(link);
  }
  card.append(details("选择、上下文与关联行动的身份", { request_id: record.request_id, context_sha256: record.context_sha256,
    snapshot_ref_before: record.snapshot_ref_before, state_version_before: record.state_version_before,
    request_sha256: record.request_sha256, decision_sha256: record.decision_sha256, child,
    provider_claim: provider, provider_verified: record.provider_verified, model_execution_verified: record.model_execution_verified,
    recipe_decision: record.recipe_decision,
    controller_code_identity: record.controller_code_identity, project_code_identity: record.project_code_identity }));
  return card;
}

function selections(project: Obj): HTMLElement {
  const panel = section("方法选择记录", "固定建议与提交的选择分别保存。来源声明和引用不等于模型使用记录或科学批准。"), history = object(project.selection_history);
  panel.classList.add("project-selections");
  const records = objects(history.records);
  if (history.available !== true) panel.append(el("p", "notice", "选择记录暂不可核对，请重新读取项目；此处不将读取失败当作空记录。"));
  else if (!records.length) panel.append(el("p", "empty-state", "该项目尚无外部提交的选择记录。已有工具结果与固定建议仍按原记录展示。"));
  else {
    panel.append(el("p", "overline", "最近一次提交"), selectionCard(project, records[0]));
    if (records.length > 1) {
      const previous = el("details", "project-selection-history"); previous.append(el("summary", "", `查看较早的选择（${records.length - 1}条）`));
      for (const record of records.slice(1)) previous.append(selectionCard(project, record)); panel.append(previous);
    }
    if (typeof history.omitted === "number" && history.omitted > 0) panel.append(el("p", "detail-note", `另有${numeric(history.omitted)}条较早记录，见完整项目快照。`));
  }
  const controls = el("div", "hero-actions project-selection-controls"), load = el("button", "quiet-button", "查看当前可选行动"); load.type = "button";
  const status = el("p", "form-feedback", "只读核对当前条件，不执行研究。"), list = el("div", "project-selection-candidates");
  status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite"); list.id = "project-selection-candidates"; load.setAttribute("aria-controls", list.id);
  const snapshot = string(project.snapshot_ref, ""), url = "/api/project/selection-context.json" + (/^[a-f0-9]{64}$/.test(snapshot) ? "?snapshot_ref=" + snapshot : "");
  const download = el("a", "text-button", "下载当前选择上下文 JSON ↓"); download.href = url; download.download = "selection-context.json";
  controls.append(load, download); panel.append(controls, status, list);
  load.addEventListener("click", async () => {
    load.disabled = true; status.textContent = "正在核对当前可用条件…"; list.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(15000) });
      if (!response.ok) throw Error(response.status === 409 ? "项目已经更新，请重新读取页面后再核对。" : "当前条件暂不可读取，请稍后重试。");
      const context: unknown = await response.json();
      if (!isObject(context) || context.schema_version !== "project-selection-context-v1" || context.scientific_validation !== false
          || context.project_id !== project.id || (snapshot && context.snapshot_ref !== snapshot) || !Array.isArray(context.candidates)) throw Error("当前条件的身份无法核对，请重新读取项目。");
      if (!panel.isConnected) return;
      const candidates = objects(context.candidates); list.replaceChildren();
      status.textContent = candidates.length ? `当前有${candidates.length}个可选行动；本页不会提交或执行。` : "当前没有新的可执行候选；已完成结果或仍缺条件见原记录。";
      for (const candidate of candidates) {
        const item = el("article", "project-selection-cell"); item.append(el("h3", "", choiceTitle(project, candidate)), details("允许参数与评价（原记录）", candidate)); list.append(item);
      }
      list.append(details("当前条件、阻断原因与预算", { state_version: context.state_version, context_sha256: context.context_sha256,
        conditions: context.conditions, blockers: context.blockers, budget: context.budget }));
    } catch (error) { if (panel.isConnected) status.textContent = error instanceof Error && /^(项目|当前)/.test(error.message)
      ? error.message : "当前条件暂不可读取，请稍后重试。"; }
    finally { load.disabled = false; list.removeAttribute("aria-busy"); }
  });
  return panel;
}

function standaloneHeader(project: Obj): void {
  const goal = string(project.goal, "当前项目"), status = reportState(project);
  document.title = goal + " · 空间研究";
  $("project-title").textContent = goal; $("nav-project-title").textContent = goal;
  $("project-label").textContent = domainTitle[domain(project)];
  const navNote = document.querySelector<HTMLElement>(".nav-note p");
  if (navNote) navNote.textContent = "项目：" + state(project.research_status) + "。来源、反馈与未决事项按已保存记录展示。";
  for (const [id, format, label] of [["download-pdf", "pdf", "当前报告 PDF ↓"], ["download-zip", "json", "当前快照 JSON ↓"]]) {
    const button = $<HTMLButtonElement>(id); button.textContent = label; button.disabled = !status.ready;
    button.title = status.message; button.setAttribute("aria-label", label.replace(" ↓", ""));
    button.onclick = () => { if (status.ready) location.assign("/api/project/report." + format); };
  }
}

export type ActiveProjectPage = "overview" | "research" | "experiments" | "knowledge" | "outputs";

export function progressFeedback(action: Obj, source: boolean): string {
  if (action.status !== "completed") {
    if (["unknown", "needs_review"].includes(string(action.status, ""))) return "原请求的结果尚待核对。";
    return action.status === "failed" ? "失败记录已保存，详细结果见原行动。" : "此行动尚无已完成的结果。";
  }
  const observations = objects(action.observations);
  if (source) return `已保存 ${observations.length} 条来源观察，原文与定位可在知识页查看。`;
  const audit = observations.find(item => item.kind === "tabular_quality_audit");
  if (audit) {
    const profile = object(audit.profile);
    const events = objects(profile.numeric_columns).flatMap(column => {
      const counts = object(column.counts);
      return ["zero", "empty", "declared_missing", "invalid_numeric", "nonfinite"].flatMap(kind => {
        const labels: Record<string, string> = { zero: "零值", empty: "空值", declared_missing: "声明缺失", invalid_numeric: "非法数值", nonfinite: "非有限值" };
        const count = counts[kind];
        return typeof count === "number" && count > 0 ? [`${string(column.name)} ${labels[kind]} ${numeric(count)}`] : [];
      });
    });
    return `已核对 ${numeric(profile.rows)} 条记录、${numeric(profile.columns)} 个字段，完整重复的额外记录 ${numeric(profile.exact_duplicate_rows)} 条。`
      + (events.length ? events.slice(0, 2).join("，") + (events.length > 2 ? "等标记可在实验页核对。" : "。") : "");
  }
  const grouped = observations.find(item => item.kind === "grouped_quality_profile");
  if (grouped) {
    const summary = object(grouped.summary);
    return `已查看 ${numeric(summary.rows)} 条记录的分组分布，完整组 ${numeric(summary.group_count)} 个，分组字段不完整的记录 ${numeric(summary.incomplete_group_rows)} 条。`;
  }
  const workbook = observations.find(item => item.kind === "workbook_projection_check");
  if (workbook) {
    const summary = object(workbook.summary);
    return `已比较 ${numeric(summary.csv_rows)} 条CSV记录与捕获的工作簿，完全一致候选表 ${numeric(summary.exact_candidate_sheet_count)} 张。`;
  }
  return `已保存 ${observations.length} 条实际观察，具体指标与原决定见实验页。`;
}

export function researcherFeedbackItems(project: Obj, limit: number): HTMLElement {
  const list = el("div", "researcher-feedback-records"), records = objects(project.researcher_feedback);
  if (!records.length) list.append(el("p", "empty-state", "尚未记录研究者反馈，可以补充卡点、判断或下一步建议。"));
  for (const record of records.slice(-limit).reverse()) {
    const item = el("article", "researcher-feedback-record"), plan = typeof record.plan_version === "number" ? "计划 v" + record.plan_version : "尚无计划";
    const comment = string(record.comment, ""), next = string(record.next_step, "");
    item.append(el("h3", "", string(record.author) + " · " + plan), el("p", "researcher-feedback-copy", comment.length > 240 ? comment.slice(0, 240) + "…" : comment));
    if (next) item.append(el("h4", "", "后续建议"), el("p", "researcher-feedback-copy", next.length > 160 ? next.slice(0, 160) + "…" : next));
    if (record.action_id) {
      const action = [...objects(project.actions), ...objects(project.evidence_actions)].find(action => action.id === record.action_id);
      item.append(el("p", "detail-note", "关联工作 · " + method(action?.command)));
    }
    const full = el("details", "researcher-feedback-full");
    full.append(el("summary", "", "查看完整意见与原记录"), el("p", "researcher-feedback-copy", comment));
    if (next) full.append(el("p", "researcher-feedback-copy", next));
    full.append(details("原反馈记录 JSON", record)); item.append(full); list.append(item);
  }
  return list;
}

function savedProgress(project: Obj): HTMLElement {
  const methods = objects(project.actions), sources = objects(project.evidence_actions);
  const panel = section("已保存的工作", `方法行动 ${methods.length} 项，来源读取 ${sources.length} 项。`);
  panel.classList.add("project-progress");
  const list = el("ul", "project-progress-list");
  const visible = [...methods.slice(-3).map(action => ({ action, source: false })), ...sources.slice(-2).map(action => ({ action, source: true }))];
  for (const { action, source } of visible) {
    const item = el("li", "project-progress-item"), heading = el("div", "project-progress-heading");
    heading.append(el("h3", "", source ? "来源读取" : method(action.command)), badge(action.status, ""));
    item.append(heading, el("p", "project-progress-copy", progressFeedback(action, source))); list.append(item);
  }
  if (visible.length) panel.append(list);
  else panel.append(el("p", "empty-state", "当前还没有保存的执行结果。可以先查看研究计划和当前候选。"));
  const hidden = methods.length + sources.length - visible.length;
  if (hidden > 0) panel.append(el("p", "detail-note", `另有 ${hidden} 条保存记录，可在实验与知识页完整查看。`));
  if (objects(project.researcher_feedback).length) panel.append(el("h3", "project-progress-follow-up", "研究者反馈"), researcherFeedbackItems(project, 2));
  const links = el("div", "project-progress-actions");
  for (const [label, href] of [["查看方法结果", "#/experiments"], ["阅读来源与定位", "#/knowledge"], ["查看报告与成果", "#/outputs"], ["补充研究反馈", "#/research?focus=feedback"]]) {
    const link = el("a", "text-button", label); link.href = href; links.append(link);
  }
  panel.append(links); return panel;
}

function currentProgressNext(project: Obj, context: Obj | null): HTMLElement {
  const panel = section("当前下一步"); panel.classList.add("project-progress");
  const current = context?.schema_version === "project-selection-context-v1" && context.project_id === project.id
    && typeof project.state_version === "number" && context.state_version === project.state_version ? context : null;
  const actions = [...objects(project.actions), ...objects(project.evidence_actions)];
  const unresolved = ["unknown", "needs_review", "running", "pending"];
  let label = "查看当前候选";
  if (unresolved.includes(string(project.execution_status, "")) || actions.some(action => unresolved.includes(string(action.status, "")))) {
    panel.append(el("p", "project-progress-copy", "先核对原请求。已有执行的结果尚未确认，请在研究推进中查看原请求与保存状态。"));
    label = "核对原请求";
  } else if (!current) {
    panel.append(el("p", "project-progress-copy", "当前候选待刷新。重新读取当前项目状态后，再查看可选方法与条件。"));
    label = "查看研究推进";
  } else {
    const blockers = objects(current.blockers), candidates = objects(current.candidates);
    if (blockers.length) {
      const reasons: Record<string, string> = {
        EXECUTION_UNKNOWN: "原执行尚未确认，先核对原请求。", PROJECT_BUSY: "已有请求尚未结束，先核对其保存状态。",
        CODE_CHANGED: "项目记录与当前代码版本不同，先核对项目版本。", BUDGET_EXHAUSTED: "原调用额度已用完，先核对已保存结果与资源记录。",
        MISSING_SOURCE: "当前所需来源尚未登记，先补充对应资料。", METHOD_NOT_SUPPORTED: "当前输入尚无对应的执行方法。",
        PROJECT_WAITING: "当前研究在等待资料或条件，请先核对具体缺口。",
      };
      for (const blocker of blockers.slice(0, 3)) panel.append(el("p", "project-progress-copy",
        reasons[string(blocker.code, "")] ?? note(string(blocker.reason, ""), "当前条件阻止推进，请在研究页核对。")));
      label = "核对条件与原请求";
    } else if (candidates.length) {
      panel.append(el("p", "project-progress-copy", candidates.length > 1
        ? "当前有多个候选，可查看各项方法和条件后决定下一步。" : "当前候选可在研究推进中查看，并结合计划决定下一步。"));
      const choices = el("ul", "project-progress-candidates");
      for (const candidate of candidates.slice(0, 4)) choices.append(el("li", "", choiceTitle(project, candidate)));
      panel.append(choices);
      if (candidates.length > 4) panel.append(el("p", "detail-note", `其余 ${candidates.length - 4} 个候选见研究推进。`));
    } else {
      const exhausted = objects(current.conditions).some(condition => words(condition.execution_blockers).includes("BUDGET_EXHAUSTED"));
      panel.append(el("p", "project-progress-copy", exhausted
        ? "当前没有方法候选，部分方法已达到原调用额度。可核对保存结果、资料缺口和资源记录。"
        : "当前没有方法候选。可查看已保存的未决问题，决定补充资料或调整研究计划。"));
      label = "查看资料与条件";
    }
  }
  const feedback = string(object(object(project.research_plan).current).expected_feedback, "");
  const next = object(project.next_decision), task = object(next.next_action);
  const questions = [...new Set([...words(next.remaining_questions), ...words(task.required_evidence), ...words(next.retained_unresolved_requirements)])];
  if (feedback || questions.length) panel.append(el("h3", "project-progress-follow-up", "继续条件与未决问题"));
  if (feedback) panel.append(el("p", "project-progress-copy", feedback.length > 280 ? feedback.slice(0, 280) + "…" : feedback));
  if (questions.length) {
    const list = el("ul", "project-questions");
    for (const question of questions.slice(0, 3)) list.append(el("li", "", note(question, question)));
    panel.append(list);
    if (questions.length > 3) panel.append(details(`查看全部 ${questions.length} 项未决问题`, questions));
  }
  const links = el("div", "project-progress-actions"), link = el("a", "text-button", label);
  link.href = "#/research?focus=operations"; links.append(link); panel.append(links); return panel;
}

/** Explicit active-project sections; never adapt CSV records into historical trials. */
export function renderProjectPage(container: HTMLElement, value: Obj, page: ActiveProjectPage, context: Obj | null): void {
  if (page === "overview") {
    const plan = object(object(value.research_plan).current), intro = section("当前研究问题");
    const hasPlan = typeof plan.version === "number" && typeof plan.question === "string";
    intro.classList.add("project-progress");
    intro.append(el("p", "project-progress-question", hasPlan ? string(plan.question) : string(value.goal)));
    const status = el("div", "project-progress-status");
    status.append(badge(value.research_status, ""), badge(value.execution_status, "")); intro.append(status);
    if (hasPlan) {
      const steps = string(plan.steps, "当前计划尚未记录步骤。"), reason = string(plan.reason, "未记录修订理由。");
      intro.append(el("h3", "", `已采用研究计划 v${numeric(plan.version)}`),
        el("p", "project-progress-copy", steps.length > 280 ? steps.slice(0, 280) + "…" : steps),
        el("p", "detail-note", "本次修订依据 " + (reason.length > 160 ? reason.slice(0, 160) + "…" : reason)));
    } else intro.append(el("p", "project-progress-copy", "还未保存研究计划，可以先写清步骤和预期反馈。"));
    const links = el("div", "project-progress-actions"), planLink = el("a", "text-button", hasPlan ? "查看或修改计划" : "制定研究计划");
    planLink.href = "#/research?focus=plan"; links.append(planLink); intro.append(links);
    const scope = el("details", "project-progress-scope"); scope.append(el("summary", "", "范围与资源记录"), boundaries(value));
    container.replaceChildren(intro, savedProgress(value), currentProgressNext(value, context), scope);
  } else if (page === "research") container.replaceChildren(selections(value), methods(value));
  else if (page === "experiments") container.replaceChildren(executionRecords(value));
  else if (page === "knowledge") {
    const registered = section("已登记资料与原件");
    const receipts = objects(value.registered_evidence);
    if (!receipts.length) registered.append(el("p", "empty-state", "当前项目尚无已登记资料。请在研究推进中明确登记，登记不会自动读取。"));
    for (const receipt of receipts) {
      const hash = string(receipt.receipt_snapshot_sha256, ""); if (!/^[a-f0-9]{64}$/.test(hash)) continue;
      const row = el("div", "project-registered-source");
      row.append(el("h3", "", `资料包 ${String(receipt.ordinal ?? "")} · ${String(receipt.source_count ?? "?")} 份原件`),
        el("p", "", receipt.read_status === "completed" ? "已完成读取，见下方原文及出处。" : receipt.read_status === "failed" ? "读取失败，原记录和原件保留。" : receipt.read_status === "unknown" ? "读取状态待核对，不自动重发。" : "已登记，尚未读取。"));
      const link = el("a", "text-button", "核对完整回执与来源声明 JSON ↓"); link.href = "/api/project/evidence-receipt/" + hash + ".json"; row.append(link); registered.append(row);
    }
    container.replaceChildren(registered, excerpts(value), search(value));
  } else container.replaceChildren(reports(value));
}

export async function renderProject(container: HTMLElement): Promise<void> {
  if (document.body.dataset.case === "project") {
    for (const id of ["download-pdf", "download-zip"]) {
      const button = $<HTMLButtonElement>(id); button.disabled = true; button.title = "正在核对当前快照报告状态。";
    }
  }
  const host = el("div", "project-view");
  const loading = el("p", "notice project-loading", "正在读取项目的已保存记录…"); loading.setAttribute("role", "status");
  host.append(loading); container.replaceChildren(host);
  try {
    const response = await fetch("/api/project", { cache: "no-store", signal: AbortSignal.timeout(15000) });
    if (!response.ok) throw Error(response.status === 404 ? "当前没有挂载可读项目。请选择已有项目后重试。" : "项目记录暂不可读取，请重试。");
    const value: unknown = await response.json();
    if (!isObject(value) || value.schema_version !== "active-project-view-v1" || value.scientific_validation !== false
      || typeof value.goal !== "string" || !Array.isArray(value.actions) || !Array.isArray(value.evidence_actions)) throw Error("项目记录的身份或范围不完整，无法安全展示。");
    if (!container.contains(host)) return;
    if (document.body.dataset.case === "project") standaloneHeader(value);
    const intro = el("section", "project-intro content-section");
    intro.append(el("p", "overline", "当前研究项目 · 保存状态"), el("h1", "", value.goal));
    const statuses = el("div", "project-status-row"); statuses.append(badge(value.research_status, "项目："), badge(value.execution_status, "执行："));
    intro.append(statuses);
    const next = object(value.next_decision), first = object(value.initial_decision), task = object(next.next_action);
    const nextCard = el("div", "project-next");
    const hasSelections = objects(object(value.selection_history).records).length > 0;
    nextCard.append(el("h2", "section-title", hasSelections ? "工具反馈后的固定建议" : "接下来需要什么"),
      el("p", "", Object.keys(next).length ? nextTitle(next) : method(first.method_id)),
      el("p", "detail-note", task.kind === "reconcile_execution" ? "执行结果仍未知，先核对原请求；不会自动重发。" : hasSelections ? "这是固定本地规则保存的建议。最近提交的选择见下方记录，页面不会自动继续研究。" : "这是保存的下一决定，尚未执行。页面不会自动继续研究。"));
    if (typeof next.reason === "string" && /[\u3400-\u9fff]/.test(next.reason)) nextCard.append(el("p", "project-next-reason", next.reason));
    const required = words(task.required_evidence);
    if (required.length) nextCard.append(el("p", "", "待取得：" + [...new Set(required.map(item => note(item, "原始条件或验证资料，见完整任务要求")))].join("；")));
    if (Object.keys(next).length) nextCard.append(details("固定规则的原始理由与反馈引用", next));
    intro.append(nextCard);
    host.replaceChildren(intro, selections(value), executionRecords(value), excerpts(value), methods(value), search(value), reports(value), boundaries(value));
    const heading = intro.querySelector<HTMLElement>("h1");
    if (heading) { heading.tabIndex = -1; if (document.body.dataset.case === "project") requestAnimationFrame(() => heading.focus({ preventScroll: true })); }
  } catch (error) {
    if (!container.contains(host)) return;
    const message = el("p", "notice", error instanceof Error && error.name === "TimeoutError"
      ? "项目记录读取超时，请稍后重试。"
      : error instanceof Error && /^(项目|当前)/.test(error.message) ? error.message : "项目记录暂不可读取，请稍后重试。");
    message.setAttribute("role", "alert");
    const retry = el("button", "quiet-button", "重新读取项目"); retry.type = "button";
    retry.addEventListener("click", () => { void renderProject(container); });
    host.replaceChildren(message, retry);
  }
}

export async function mountStandaloneProject(): Promise<void> {
  document.body.classList.add("project-standalone");
  $("page-state").hidden = true; $("page-content").hidden = false;
  for (const id of ["inspector", "inspector-backdrop", "search-results"]) $(id).hidden = true;
  const searchWrap = document.querySelector<HTMLElement>(".search-wrap"); if (searchWrap) searchWrap.hidden = true;
  $<HTMLInputElement>("search").disabled = true;
  const nav = $("sections"), home = el("a", "nav-item active");
  home.href = "#/project"; home.dataset.page = "project"; home.setAttribute("aria-current", "page");
  home.append(el("span", "nav-icon", "◈"), el("span", "", "当前项目")); nav.replaceChildren(home);
  const brand = document.querySelector<HTMLAnchorElement>(".brand"); if (brand) brand.href = "#/project";
  const local = document.querySelector<HTMLElement>(".project-local"); if (local) local.textContent = "本地保存记录";
  const topStatus = document.querySelector<HTMLElement>(".topbar-status"); if (topStatus) topStatus.textContent = "只读项目记录";
  const footer = document.querySelector<HTMLElement>(".nav-footer>span:nth-child(2)"); if (footer) footer.textContent = "本地状态 · 只读";
  for (const id of ["download-pdf", "download-zip"]) $<HTMLButtonElement>(id).disabled = true;
  $("download-pdf").textContent = "当前报告 PDF ↓"; $("download-zip").textContent = "当前快照 JSON ↓";
  $("project-title").textContent = "正在读取项目"; $("nav-project-title").textContent = "正在读取项目";
  $("project-label").textContent = "当前项目 · 已保存状态";
  const route = async (): Promise<void> => {
    if (location.hash !== "#/project") history.replaceState(null, "", "#/project");
    await renderProject($("page-content"));
  };
  home.addEventListener("click", event => {
    if (location.hash !== "#/project") return;
    event.preventDefault(); $("page-content").querySelector<HTMLElement>("h1")?.focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "instant" });
  });
  document.querySelector(".skip-link")?.addEventListener("click", event => {
    event.preventDefault(); $("main-content").focus({ preventScroll: true }); $("main-content").scrollIntoView({ block: "start" });
  });
  window.addEventListener("hashchange", () => { void route(); });
  await route();
}
