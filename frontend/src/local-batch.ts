/** Explicit bounded grants; transport and original-request recovery belong to the parent. */
import { el } from "./dom";

type Obj = Record<string, unknown>;
type Host = {
  submit(body: Obj, recover: boolean): Promise<Obj | null>;
  canRecover(body: Obj): boolean;
  announce(message: string, error?: boolean): void;
};
const object = (value: unknown): Obj => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const objects = (value: unknown): Obj[] => Array.isArray(value) ? value.map(object) : [];
const text = (value: unknown, fallback = "未记录"): string => typeof value === "string" && value.length ? value : fallback;
const sourceMethod = (id: string): boolean => ["research.source-selection", "p02.source-mapping-check"].includes(id);
const names: Record<string, string> = {
  "data.tabular-quality-audit": "表格质量与分组核对", "data.grouped-quality-profile": "分组质量画像",
  "data.numeric-association": "数值关联分析",
  "materials.saved-steel-audit": "钢材保存模型复核", "software.source-integrity-check": "软件文件完整性检查",
  "p02.saved-oof-residuals": "保存预测的残差诊断", "research.source-selection": "读取已登记来源", "p02.source-mapping-check": "读取已登记来源",
};
const states: Record<string, string> = {
  completed: "已完成", waiting: "等待后续条件", limit_reached: "达到授权步数", not_authorized: "下一方法未获本次授权",
  blocked: "条件或原额度阻断", failed: "执行失败，原记录保留", needs_review: "待核对，未知行动不重发",
  interrupted: "推进中断，可核对原批次", running: "原批次未收口", preparing: "原批次已预留", incomplete: "原批次未完成",
};
const resumable = (record: Obj): boolean => ["preparing", "incomplete"].includes(text(record.record_status, ""));

export function createLocalBatchPanel(host: Host): {
  element: HTMLElement; update(description: Obj, project: Obj): void; setLocked(value: boolean): void;
} {
  const section = el("section", "local-panel local-batch content-section");
  section.append(el("h2", "section-title", "有界连续推进"),
    el("p", "detail-note", "明确授权方法、已登记资料包和最多行动数后，由本地条件规则逐步推进。不是模型自主研究；不扩本地、来源或费用额度，登记资料也不会自动启动批次。"));
  const status = el("p", "notice", "先创建或选择项目，再明确授权。"); status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
  const form = el("form", "local-batch-form"), fields = el("fieldset", "local-fieldset");
  const methodList = el("div", "local-batch-methods"), receipts = el("div", "local-batch-sources");
  const limit = el("select"); limit.required = true;
  for (const [value, label] of [["", "明确选择最多行动数"], ["1", "最多1次行动"], ["2", "最多2次行动"]]) { const option = el("option", "", label); option.value = value; limit.append(option); }
  const reason = el("textarea"); reason.rows = 3; reason.maxLength = 4000; reason.required = true; reason.placeholder = "说明本次授权推进的范围与理由。";
  const labelled = (label: string, control: HTMLElement): HTMLElement => { const wrap = el("label", "local-field"); wrap.append(el("span", "local-label", label), control); return wrap; };
  const start = el("button", "action-button primary", "按本次授权连续推进"); start.type = "submit";
  fields.append(el("h3", "", "可授权的本地方法"), el("p", "detail-note", "默认均不勾选。勾选只限定允许范围，每一步仍由宿主重新核对条件；已完成结果复用。"), methodList,
    el("h3", "", "允许读取的确切未读资料包"), el("p", "detail-note", "只授权下方明确勾选的收据，不包含未来上传的资料；不勾选就不读取来源。"), receipts,
    labelled("本批最多行动数", limit), labelled("本次授权理由", reason));
  form.append(fields, start, el("p", "detail-note", "无候选、下一步未获授权、达到上限、失败或未知即停止。刷新与重开不自动继续；完成批次的旧ID只回读原结果。"));
  const history = el("div", "local-batch-history"); section.append(status, form, history);
  let description: Obj = {}, project: Obj = {}, projectId = "", locked = true;
  let methods = new Set<string>(), selectedReceipts = new Set<string>(), readerId = "";
  const recoveryButtons: { button: HTMLButtonElement; body: Obj }[] = [];
  const controls = (): void => {
    fields.disabled = locked || !projectId || typeof project.state_version !== "number";
    start.disabled = fields.disabled || !limit.value || !reason.value.trim() || (!methods.size && !selectedReceipts.size);
    for (const { button, body } of recoveryButtons) button.disabled = !host.canRecover(body);
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
    recoveryButtons.length = 0; history.replaceChildren(el("h3", "", "已保存批次 · 最近8条"));
    const records = objects(description.batches).slice(0, 8);
    if (!records.length) history.append(el("p", "detail-note", "尚无批次记录。不会因打开页面创建批次。"));
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
        resume.addEventListener("click", () => { if (host.canRecover(body)) void host.submit(body, true); });
        card.append(el("p", "detail-note", "使用宿主保存的原授权与原ID；需仍选中原项目。只恢复原步骤，遇到未知工具执行仍停止待核对，不自动重发。"), resume); recoveryButtons.push({ button: resume, body });
      }
      const raw = el("details", "local-advanced"); raw.append(el("summary", "", "原授权、每步父/子身份和完整停止记录"), el("pre", "project-source-text", JSON.stringify({ request_id: id, project_id: record.project_id, status: record.status, record_status: record.record_status, body, result: record.result }, null, 2)));
      card.append(raw);
      if (/^[A-Za-z0-9_.:-]{1,160}$/.test(id)) { const link = el("a", "text-button", "下载原批次 JSON ↓"); link.href = "/api/local-workbench/batch/" + encodeURIComponent(id) + ".json"; card.append(link); }
      history.append(card);
    }
  }
  form.addEventListener("submit", event => {
    event.preventDefault(); if (locked || !projectId || typeof project.state_version !== "number" || !form.reportValidity()) return;
    const allowed = [...methods]; if (selectedReceipts.size && readerId) allowed.push(readerId);
    if (!allowed.length || (selectedReceipts.size && !readerId)) { host.announce("请明确勾选实际方法或当前可读取的资料包。", true); return; }
    if (![1, 2].includes(Number(limit.value)) || !reason.value.trim()) { host.announce("请选择本批1或2次行动上限，并填写授权理由。", true); return; }
    void host.submit({ project_id: projectId, expected_state_version: project.state_version, max_actions: Number(limit.value),
      allowed_methods: allowed, source_receipt_sha256s: [...selectedReceipts], reason: reason.value.trim() }, false);
  });
  for (const control of [limit, reason]) control.addEventListener("input", controls);
  function update(nextDescription: Obj, nextProject: Obj): void {
    description = nextDescription; project = nextProject;
    const nextId = text(project.id, "");
    if (nextId !== projectId) { methods.clear(); selectedReceipts.clear(); reason.value = ""; limit.value = ""; }
    projectId = nextId; options(); savedBatches();
    status.textContent = projectId ? "本次授权只作用于当前项目；每一步保存原父/子记录，累计用量沿原账本。" : "先创建或选择项目，再明确授权；历史未完成批次仍可按原ID核对。";
    controls();
  }
  update({}, {});
  return { element: section, update, setLocked(value: boolean): void { locked = value; controls(); } };
}
