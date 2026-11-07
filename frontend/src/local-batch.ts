/** Explicit bounded grants; transport and original-request recovery belong to the parent. */
import { el } from "./dom";

type Obj = Record<string, unknown>;
type Command = "continue" | "batch";
type Host = {
  submit(body: Obj, recover: boolean, command: Command): Promise<Obj | null>;
  canRecover(body: Obj, command: Command): boolean;
  announce(message: string, error?: boolean): void;
};
const object = (value: unknown): Obj => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const objects = (value: unknown): Obj[] => Array.isArray(value) ? value.map(object) : [];
const text = (value: unknown, fallback = "未记录"): string => typeof value === "string" && value.length ? value : fallback;
const sourceMethod = (id: string): boolean => ["research.source-selection", "p02.source-mapping-check"].includes(id);
const names: Record<string, string> = {
  "data.tabular-quality-audit": "表格质量与分组核对", "data.grouped-quality-profile": "分组质量画像",
  "data.numeric-association": "数值关联分析",
  "data.workbook-projection-check": "CSV与工作簿保存值核对",
  "materials.saved-steel-audit": "钢材保存模型复核", "software.source-integrity-check": "软件文件完整性检查",
  "p02.saved-oof-residuals": "保存预测的残差诊断", "research.source-selection": "读取已登记来源", "p02.source-mapping-check": "读取已登记来源",
};
const states: Record<string, string> = {
  applied: "已采用", proposed: "待采用", prepared: "已保存，等待原回答", received: "已收到原回答",
  completed: "已完成", waiting: "等待后续条件", limit_reached: "达到授权步数", not_authorized: "下一方法未获本次授权",
  blocked: "条件或原额度阻断", failed: "执行失败，原记录保留", needs_review: "待核对，未知行动不重发",
  interrupted: "推进中断，可核对原批次", running: "原批次未收口", preparing: "原批次已预留", incomplete: "原批次未完成",
};
const resumable = (record: Obj): boolean => ["preparing", "incomplete"].includes(text(record.record_status, ""));
const phases: Record<string, string> = { plan: "取得计划建议", awaiting_adoption: "等待计划决定", actions: "推进行动", stopped: "已停止" };
const stopReasons: Record<string, string> = {
  PLAN_REQUIRED: "先保存一版研究计划，或选择取得计划建议。", HOST_GRANT_REQUIRED: "当前没有已授权模型名额，需先通过原模型流程明确授权。",
  HOST_DECISION_LIMIT: "原模型决策名额已用完，已有用量保留。", MODEL_DISABLED: "模型阶段需要已启用的服务CLI；恢复时须沿原请求配置。",
  CLI_NOT_FOUND: "未找到服务选定的CLI，请核对配置后继续原任务。", HOST_PLAN_PENDING: "等待原模型回答，沿本页原请求处理。",
  CONFIG_CHANGED: "原任务选定的CLI配置已变化，需先恢复原配置；不会切换提供方。",
  PLAN_ADOPTION_REQUIRED: "先在本页采用或拒绝原计划建议，再继续此任务。", PLAN_REJECTED: "原计划建议已拒绝，保留原决定。",
  NO_HOST_CANDIDATES: "当前没有可执行候选，需先补充实际条件或资料。", BUDGET_EXHAUSTED: "原本地工具额度已用完。",
  STALE_STATE: "项目在此任务之外发生了变化，请核对原阶段。", HOST_SELECTION_PENDING: "原模型请求仍未收口，请先核对。",
  BATCH_SCOPE_CHANGED: "当前候选超过本次允许的方法或资料范围。", MAX_ACTIONS: "已达到本次允许的行动数。",
  NOT_AUTHORIZED: "下一步超出本次勾选的方法或资料范围，原记录已保留。",
  WAITING: "当前反馈没有可继续执行的行动。请先核对缺少的资料或条件，再决定下一步。",
  ACTION_LIMIT: "已达到本次允许的行动数，原结果已保存。", EXECUTION_UNKNOWN: "原行动结果未知，保留原请求核对，不会重新发送。",
  BATCH_INTERRUPTED: "原批次中断，请核对并继续原任务。", CONTINUATION_INTERRUPTED: "原任务中断，请核对保存阶段后继续。",
  CODE_CHANGED: "原任务使用的代码版本已变化，需先核对原记录。", TOOL_FAILED: "原行动失败，已保留结果，没有自动重试。",
};
export const continuationStopReason = (stop: Obj): string => stopReasons[text(stop.code)] ?? text(stop.reason, "");

export function createLocalBatchPanel(host: Host): {
  element: HTMLElement; update(description: Obj, project: Obj): void; setLocked(value: boolean): void;
} {
  const section = el("section", "local-panel local-batch content-section");
  section.append(el("h2", "section-title", "继续研究"),
    el("p", "detail-note", "沿当前计划推进行动，或先取得计划建议、明确采用后接着推进。选择本次范围，途中停下时保留原阶段和请求。"));
  const status = el("p", "notice", "先创建或选择项目，再明确授权。"); status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
  const form = el("form", "local-batch-form"), fields = el("fieldset", "local-fieldset");
  const methodList = el("div", "local-batch-methods"), receipts = el("div", "local-batch-sources");
  const planMode = el("select"), executionMode = el("select");
  for (const [value, label] of [["reuse", "沿当前已采用计划"], ["suggest", "先取得一份计划建议"]]) {
    const option = el("option", "", label); option.value = value; planMode.append(option);
  }
  for (const [value, label] of [["rules", "按当前条件规则选择"], ["model", "由已有CLI模型选择"]]) {
    const option = el("option", "", label); option.value = value; executionMode.append(option);
  }
  const limit = el("select"); limit.required = true;
  for (const [value, label] of [["", "明确选择最多行动数"], ["1", "最多1次行动"], ["2", "最多2次行动"]]) { const option = el("option", "", label); option.value = value; limit.append(option); }
  const reason = el("textarea"); reason.rows = 3; reason.maxLength = 4000; reason.required = true; reason.placeholder = "说明本次授权推进的范围与理由。";
  const labelled = (label: string, control: HTMLElement): HTMLElement => { const wrap = el("label", "local-field"); wrap.append(el("span", "local-label", label), control); return wrap; };
  const modes = el("div", "local-form-grid"); modes.append(labelled("计划从哪里继续", planMode), labelled("行动怎样选择", executionMode));
  const start = el("button", "action-button primary", "按本次范围继续研究"); start.type = "submit";
  fields.append(modes, el("p", "detail-note", "已启用CLI时，可用原模型名额取得计划建议；未启用时准备待导入的原请求。建议必须明确采用，行动沿原额度推进。"),
    el("h3", "", "允许执行的方法"), el("p", "detail-note", "每一步仍核对当前条件，已完成结果复用。"), methodList,
    el("h3", "", "允许读取的确切未读资料包"), el("p", "detail-note", "只授权下方明确勾选的收据，不包含未来上传的资料；不勾选就不读取来源。"), receipts,
    labelled("本次最多行动数", limit), labelled("本次范围与理由", reason));
  form.append(fields, start, el("p", "detail-note", "无候选、额度不足、未获本次授权、失败或未知即停止。刷新只读取；继续使用原ID及原范围。"));
  const history = el("div", "local-batch-history"); section.append(status, form, history);
  let description: Obj = {}, project: Obj = {}, projectId = "", locked = true;
  let methods = new Set<string>(), selectedReceipts = new Set<string>(), readerId = "";
  const recoveryButtons: { button: HTMLButtonElement; body: Obj; command: Command }[] = [];
  const controls = (): void => {
    fields.disabled = locked || !projectId || typeof project.state_version !== "number";
    const hasPlan = typeof object(object(project.research_plan).current).version === "number";
    start.disabled = fields.disabled || !limit.value || !reason.value.trim() || (!methods.size && !selectedReceipts.size)
      || planMode.value === "reuse" && !hasPlan;
    for (const { button, body, command } of recoveryButtons) button.disabled = !host.canRecover(body, command);
  };
  function checkbox(target: HTMLElement, label: string, id: string, selected: Set<string>): void {
    const row = el("label", "local-checkbox"), check = el("input"); check.type = "checkbox"; check.checked = selected.has(id);
    check.addEventListener("change", () => { if (check.checked) selected.add(id); else selected.delete(id); controls(); });
    row.append(check, el("span", "", label)); target.append(row);
  }
  function options(): void {
    methodList.replaceChildren(); receipts.replaceChildren();
    const available = objects(project.method_options), local = available.filter(option => !sourceMethod(text(option.method_id, "")));
    const ids = new Set(local.map(option => text(option.method_id, "")));
    methods = new Set([...methods].filter(id => ids.has(id)));
    for (const option of local) {
      const id = text(option.method_id, ""), condition = option.condition === "satisfied" ? "所列条件满足" : option.condition === "not_applicable" ? "当前不适用" : "条件待确认";
      if (id) checkbox(methodList, (names[id] ?? id) + " · " + (option.completed === true ? "已有完成结果" : condition), id, methods);
    }
    if (!local.length) methodList.append(el("p", "detail-note", "当前项目尚无可列出的白名单本地方法。"));
    readerId = text(available.find(option => sourceMethod(text(option.method_id, "")))?.method_id, "");
    const unread = objects(project.registered_evidence).filter(receipt => ["unread", "registered_unread"].includes(text(receipt.read_status, "")) && /^[a-f0-9]{64}$/.test(text(receipt.receipt_snapshot_sha256, "")));
    const hashes = new Set(unread.map(receipt => text(receipt.receipt_snapshot_sha256)));
    selectedReceipts = new Set([...selectedReceipts].filter(hash => hashes.has(hash)));
    for (const receipt of unread) {
      const hash = text(receipt.receipt_snapshot_sha256), row = el("div", "local-batch-receipt");
      checkbox(row, `资料包${String(receipt.ordinal ?? "")} · ${String(receipt.source_count ?? "?")}份原件 / ${String(receipt.selection_count ?? "?")}个选区 · SHA ${hash.slice(0, 12)}`, hash, selectedReceipts);
      const link = el("a", "text-button", "核对这份登记回执 JSON ↓"); link.href = "/api/project/evidence-receipt/" + hash + ".json"; row.append(link); receipts.append(row);
    }
    if (!unread.length) receipts.append(el("p", "detail-note", "当前没有已登记且未读的资料包；将来登记的资料不在本次授权内。"));
  }
  function savedBatches(): void {
    const linked = new Set(objects(description.continuations).map(record => object(record.batch_ref).request_id));
    const records = objects(description.batches).filter(record => !linked.has(record.request_id)).slice(0, 8);
    if (records.length) history.append(el("h3", "", "单独的行动批次"));
    for (const record of records) {
      const body = object(record.body), response = object(record.result), batch = object(response.batch), stop = object(batch.stop);
      const id = text(record.request_id, ""), card = el("details", "local-batch-record"), currentProject = record.project_id === projectId;
      card.append(el("summary", "", (currentProject ? "当前项目" : "其他项目") + " · " + (states[text(record.status)] ?? states[text(response.status)] ?? "状态待核对") + " · " + id));
      const grant = object(batch.grant), actualGrant = Object.keys(grant).length ? grant : body;
      const approved = Array.isArray(actualGrant.allowed_methods) ? actualGrant.allowed_methods.filter((item): item is string => typeof item === "string") : [];
      card.append(el("p", "detail-note", "原授权最多" + String(actualGrant.max_actions ?? "?") + "次行动；方法：" + (approved.map(method => names[method] ?? method).join("、") || "未记录")),
        el("p", "detail-note", "原授权理由：" + text(actualGrant.reason)));
      if (stop.code || stop.reason) card.append(el("p", "notice", "停止：" + text(stop.code, "") + " · " + text(stop.reason)));
      const steps = objects(batch.steps);
      for (const step of steps.slice(0, 8)) {
        const parent = object(step.parent), child = object(object(step.response).child);
        card.append(el("p", "detail-note", `第${String(step.ordinal ?? "?")}步 · ${names[text(step.method_id)] ?? text(step.method_id)} · ${states[text(step.status)] ?? text(step.status)}；父 ${text(step.request_id, text(parent.request_id))}；子 ${text(step.child_request_id, text(child.request_id, "无child记录"))}`));
      }
      if (resumable(record) && body.request_id === id && body.project_id === record.project_id) {
        const resume = el("button", "action-button", "核对并继续原批次"); resume.type = "button";
        resume.addEventListener("click", () => { if (host.canRecover(body, "batch")) void host.submit(body, true, "batch"); });
        card.append(el("p", "detail-note", "沿保存范围与原ID核对。未知行动不重发。"), resume); recoveryButtons.push({ button: resume, body, command: "batch" });
      }
      const raw = el("details", "local-advanced"); raw.append(el("summary", "", "原授权、每步父/子身份和完整停止记录"), el("pre", "project-source-text", JSON.stringify({ request_id: id, project_id: record.project_id, status: record.status, record_status: record.record_status, body, result: record.result }, null, 2)));
      card.append(raw);
      if (/^[A-Za-z0-9_.:-]{1,160}$/.test(id)) { const link = el("a", "text-button", "下载原批次 JSON ↓"); link.href = "/api/local-workbench/batch/" + encodeURIComponent(id) + ".json"; card.append(link); }
      history.append(card);
    }
  }
  function savedContinuations(): void {
    const opened = new Set([...history.querySelectorAll<HTMLDetailsElement>("details[data-request]")].filter(node => node.open).map(node => node.dataset.request));
    const existed = new Set([...history.querySelectorAll<HTMLDetailsElement>("details[data-request]")].map(node => node.dataset.request));
    recoveryButtons.length = 0; history.replaceChildren(el("h3", "", "继续记录"));
    const records = objects(description.continuations).slice(0, 8);
    if (!records.length) history.append(el("p", "detail-note", "尚无继续任务；查看页面不会创建请求。"));
    records.forEach((record, index) => {
      const body = object(record.body), stop = object(record.stop), plan = object(record.plan_ref), batch = object(record.batch_ref);
      const id = text(record.request_id, ""), card = el("details", "local-batch-record");
      card.dataset.request = id; card.open = opened.has(id) || !existed.has(id) && index === 0 && record.project_id === projectId;
      const phase = phases[text(record.phase)] ?? "阶段待核对";
      card.append(el("summary", "", phase + " · " + (states[text(record.status)] ?? "状态待核对") + " · " + id));
      card.append(el("p", "detail-note", "原范围最多" + String(body.max_actions ?? "?") + "次行动 · "
        + (body.plan_mode === "suggest" ? "先取得计划建议" : "沿已采用计划") + " · "
        + (body.execution_mode === "model" ? "CLI模型选择" : "条件规则选择")));
      if (Object.keys(plan).length) card.append(el("p", "detail-note", "研究计划："
        + (typeof plan.plan_version === "number" ? "第" + plan.plan_version + "版" : "尚未采用")
        + " · 原请求 " + text(plan.request_id)));
      if (Object.keys(batch).length) card.append(el("p", "detail-note", "行动批次：" + text(batch.request_id)
        + " · " + (states[text(batch.status)] ?? text(batch.status))));
      if (stop.code || stop.reason) card.append(el("p", "notice", continuationStopReason(stop)));
      for (const step of objects(record.steps)) card.append(el("p", "detail-note", "第" + String(step.ordinal ?? "?") + "阶段 · "
        + (step.phase === "plan" && body.plan_mode === "reuse" ? "沿已采用计划" : phases[text(step.phase)] ?? text(step.phase)) + " · " + (states[text(step.status)] ?? text(step.status))
        + "；原请求 " + text(step.request_id) + (step.child_request_id ? "；行动 " + text(step.child_request_id) : "")));
      if (record.phase === "awaiting_adoption") {
        const review = el("a", "text-button", "查看本页计划建议"); review.href = "#/research?focus=plan"; card.append(review);
      }
      if (resumable(record) && stop.resume_allowed === true && body.request_id === id && body.project_id === record.project_id) {
        const resume = el("button", "action-button", "核对并继续原任务"); resume.type = "button";
        resume.addEventListener("click", () => { if (host.canRecover(body, "continue")) void host.submit(body, true, "continue"); });
        card.append(resume); recoveryButtons.push({ button: resume, body, command: "continue" });
      }
      const raw = el("details", "local-advanced"); raw.append(el("summary", "", "原范围、阶段与完整停止记录"),
        el("pre", "project-source-text", JSON.stringify(record, null, 2))); card.append(raw);
      if (/^[A-Za-z0-9_.:-]{1,160}$/.test(id)) {
        const link = el("a", "text-button", "下载原继续记录 JSON ↓"); link.href = "/api/local-workbench/continue/" + encodeURIComponent(id) + ".json"; card.append(link);
      }
      history.append(card);
    });
  }
  form.addEventListener("submit", event => {
    event.preventDefault(); if (locked || !projectId || typeof project.state_version !== "number" || !form.reportValidity()) return;
    const allowed = [...methods]; if (selectedReceipts.size && readerId) allowed.push(readerId);
    if (!allowed.length || (selectedReceipts.size && !readerId)) { host.announce("请明确勾选实际方法或当前可读取的资料包。", true); return; }
    if (![1, 2].includes(Number(limit.value)) || !reason.value.trim()) { host.announce("请选择本批1或2次行动上限，并填写授权理由。", true); return; }
    void host.submit({ project_id: projectId, expected_state_version: project.state_version, max_actions: Number(limit.value),
      plan_mode: planMode.value, execution_mode: executionMode.value,
      allowed_methods: allowed, source_receipt_sha256s: [...selectedReceipts], reason: reason.value.trim() }, false, "continue");
  });
  for (const control of [limit, reason, planMode, executionMode]) control.addEventListener("input", controls);
  function update(nextDescription: Obj, nextProject: Obj): void {
    description = nextDescription; project = nextProject;
    const nextId = text(project.id, "");
    if (nextId !== projectId) { methods.clear(); selectedReceipts.clear(); reason.value = ""; limit.value = ""; planMode.value = "reuse"; executionMode.value = "rules"; }
    projectId = nextId; options(); savedContinuations(); savedBatches();
    const version = object(object(project.research_plan).current).version;
    status.textContent = projectId ? (typeof version === "number" ? "当前采用研究计划第" + version + "版。" : "先保存计划，或选择取得计划建议。")
      + " 本次沿原项目和累计额度继续。" : "先创建或选择项目，再明确本次推进范围。";
    controls();
  }
  update({}, {});
  return { element: section, update, setLocked(value: boolean): void { locked = value; controls(); } };
}
