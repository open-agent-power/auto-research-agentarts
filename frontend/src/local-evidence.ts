/** Stage task-bound original files; explicit reading stays in the parent's candidate flow. */
import { el, safeUrl } from "./dom";

type Obj = Record<string, unknown>;
type Selection = { id: string; kind: HTMLSelectElement; value: HTMLInputElement; claim: HTMLTextAreaElement; element: HTMLElement };
type Source = { id: string; name: string; size: number; encoded: string; url: HTMLInputElement; media: HTMLInputElement; license: HTMLTextAreaElement; selections: Selection[]; element: HTMLElement };
type Draft = { projectId: string; sources: Source[]; nextSource: number; nextSelection: number; questions: HTMLTextAreaElement; files: HTMLElement; loading: boolean; submitting: boolean; submitted: boolean; receipt: string | null };
type Host = { read(path: string): Promise<Obj>; submit(body: Obj): Promise<Obj | null>; announce(message: string, error?: boolean): void };
const object = (value: unknown): Obj => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const objects = (value: unknown): Obj[] => Array.isArray(value) ? value.map(object) : [];
const string = (value: unknown, fallback = "未记录"): string => typeof value === "string" && value.length ? value : fallback;
const strings = (value: unknown): string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
const sha = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const safeId = (value: unknown): value is string => typeof value === "string" && /^[A-Za-z0-9_.:-]{1,80}$/.test(value);
const MAX_FILE = 32 * 1024 * 1024, MAX_TOTAL = 64 * 1024 * 1024;

function field(label: string, control: HTMLElement, hint?: string): HTMLElement {
  const wrap = el("label", "local-field"); wrap.append(el("span", "local-label", label), control);
  if (hint) wrap.append(el("small", "detail-note", hint)); return wrap;
}
function input(maximum: number, value = ""): HTMLInputElement { const control = el("input"); control.type = "text"; control.maxLength = maximum; control.value = value; return control; }
function encode(bytes: Uint8Array): string {
  const parts: string[] = []; for (let index = 0; index < bytes.length; index += 8192) parts.push(String.fromCharCode(...bytes.subarray(index, index + 8192)));
  return btoa(parts.join(""));
}
function formatBytes(value: number): string { return value.toLocaleString("zh-CN") + "字节"; }

export function createLocalEvidencePanel(host: Host): {
  element: HTMLElement; setLocked(value: boolean): void; refresh(projectId: string, project: Obj): Promise<void>; acceptRegistered(result: Obj): void;
} {
  const section = el("section", "local-panel local-evidence content-section");
  section.append(el("h2", "section-title", "补充资料 · 先登记，再明确读取"), el("p", "detail-note", "上传原文件并声明选区，只登记到当前取证任务。读取仍需在上方选择真实来源候选并明确执行，不会自动扣读取次数。"));
  const taskStatus = el("p", "notice", "创建并执行检查后，可补充实际来源资料。"); taskStatus.setAttribute("role", "status"); taskStatus.setAttribute("aria-live", "polite");
  const taskDetails = el("details", "local-advanced"); taskDetails.append(el("summary", "", "当前取证任务与绑定"));
  const taskText = el("pre", "project-source-text"); taskDetails.append(taskText);
  const form = el("form", "local-evidence-form"), fields = el("fieldset", "local-fieldset");
  const chooser = el("input"); chooser.type = "file"; chooser.multiple = true; chooser.accept = ".txt,.md,.html,.htm,.csv,.tsv,.json,.pdf,.xlsx";
  chooser.setAttribute("aria-label", "选择补充资料文件，可多选");
  const fileStatus = el("p", "detail-note", "1至8个文件；每份不超过32MiB，总计不超过64MiB。原件不会被执行。"); fileStatus.setAttribute("aria-live", "polite");
  const draftHost = el("div", "local-evidence-draft");
  const stage = el("button", "action-button primary", "登记资料，不读取"); stage.type = "submit";
  fields.append(field("选择补充资料文件", chooser), fileStatus, draftHost);
  form.append(fields, stage, el("p", "detail-note", "来源URL、许可及选区主张均为未核验声明。登记不提取文本，不建FTS，也不批准科学映射；读取时才核对保存的选区是否可提取。"));
  const packages = el("div", "local-evidence-packages");
  section.append(taskStatus, taskDetails, form, packages);
  const drafts = new Map<string, Draft>();
  let active = "", project: Obj = {}, task: Obj | null = null, locked = true, loadingTask = false, refreshId = 0;

  function draftFor(projectId: string): Draft {
    const old = drafts.get(projectId); if (old) return old;
    const questions = el("textarea"); questions.rows = 3; questions.placeholder = "仍未解决的问题，每行一条；可留空。";
    const draft: Draft = { projectId, sources: [], nextSource: 1, nextSelection: 1, questions, files: el("div", "local-evidence-files"), loading: false, submitting: false, submitted: false, receipt: null };
    questions.addEventListener("input", () => changed(draft)); drafts.set(projectId, draft); return draft;
  }
  function changed(draft: Draft): void { draft.submitted = false; controls(); }
  function acceptRegistered(result: Obj): void {
    if (result.status !== "registered") return;
    const draft = drafts.get(string(result.project_id, "")); if (!draft) return;
    draft.submitted = true; draft.receipt = string(object(result.registration).receipt_snapshot_sha256, "");
    if (active === draft.projectId) fileStatus.textContent = "原件和选区已登记，尚未自动读取。请到上方选择已登记来源候选并明确执行一次。";
    controls();
  }
  function current(): Draft | null { return active ? draftFor(active) : null; }
  function selectionCount(draft: Draft): number { return draft.sources.reduce((count, source) => count + source.selections.length, 0); }
  function controls(): void {
    const draft = current(), disabled = locked || !task || loadingTask || !!draft?.loading || !!draft?.submitting;
    fields.disabled = disabled; stage.disabled = disabled || !draft?.sources.length || !selectionCount(draft) || draft.submitted;
    stage.textContent = draft?.submitted ? "资料已登记，尚未自动读取" : "登记资料，不读取";
  }
  function addSelection(draft: Draft, source: Source): void {
    if (selectionCount(draft) >= 32) { host.announce("每次最多登记32个选区。", true); return; }
    const card = el("div", "local-evidence-selection"), kind = el("select"), value = input(2000), claim = el("textarea");
    claim.rows = 2; claim.maxLength = 4000; claim.required = true; value.required = true;
    for (const [name, label] of [["text_lines", "UTF-8文本物理行"], ["pdf_page", "PDF页或页内字符"], ["xlsx_cell", "工作簿单元格"]]) { const option = el("option", "", label); option.value = name; kind.append(option); }
    kind.value = /\.pdf$/i.test(source.name) ? "pdf_page" : /\.xlsx$/i.test(source.name) ? "xlsx_cell" : "text_lines";
    const hint = el("p", "detail-note");
    const explain = (): void => {
      value.placeholder = kind.value === "pdf_page" ? "例如 3:0-800，或单页3" : kind.value === "xlsx_cell" ? "例如 Sheet!A1:C6" : "例如 1-10";
      hint.textContent = kind.value === "pdf_page" ? "页码从1起；页内偏移是提取文本的0基Unicode码点，end排除，不是PDF原字节。没有OCR。"
        : kind.value === "xlsx_cell" ? "填写真实sheet与单元格；只读保存值/公式缓存，不执行公式。"
          : /\.html?$/i.test(source.name) ? "从1起的原始HTML物理行，最多256行；保留标签与脚本字面文本，按保存原件定位。"
            : "从1起的物理行，最多256行；包含表头及带引号换行，不是CSV逻辑记录号。";
    };
    const selection: Selection = { id: "selection-" + draft.nextSelection++, kind, value, claim, element: card };
    const remove = el("button", "quiet-button", "移除此选区"); remove.type = "button";
    remove.addEventListener("click", () => { source.selections = source.selections.filter(item => item !== selection); card.remove(); changed(draft); });
    for (const control of [kind, value, claim]) control.addEventListener("input", () => changed(draft));
    kind.addEventListener("change", explain); explain();
    card.append(el("h4", "", "选区 " + selection.id), field("定位类型", kind), field("实际选区（必须明确填写）", value), hint,
      field("这段来源能说明什么（提交者主张）", claim, "请保留不确定性，不能把配置或文件名写成已确认的科学结论。"), remove);
    source.selections.push(selection); source.element.querySelector<HTMLElement>(".local-evidence-selections")?.append(card); changed(draft);
  }
  function addSource(draft: Draft, file: File, encoded: string): void {
    const card = el("article", "local-evidence-file evidence-card"), url = input(4000), media = input(160), license = el("textarea");
    url.required = true; media.required = true; license.required = true; license.rows = 2; license.maxLength = 4000; license.value = "许可与访问范围尚待核验";
    url.placeholder = "实际来源URL或明确的本地资料URN；不会自动访问";
    media.value = /\.pdf$/i.test(file.name) ? "application/pdf" : /\.xlsx$/i.test(file.name) ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
      : /\.html?$/i.test(file.name) ? "text/html" : /\.json$/i.test(file.name) ? "application/json" : /\.csv$/i.test(file.name) ? "text/csv" : file.type || "text/plain";
    const source: Source = { id: "source-" + draft.nextSource++, name: file.name, size: file.size, encoded, url, media, license, selections: [], element: card };
    const remove = el("button", "quiet-button", "移除此草稿文件"); remove.type = "button";
    remove.addEventListener("click", () => { draft.sources = draft.sources.filter(item => item !== source); card.remove(); changed(draft); });
    const add = el("button", "quiet-button", "为此文件添加选区"); add.type = "button"; add.addEventListener("click", () => addSelection(draft, source));
    for (const control of [url, media, license]) control.addEventListener("input", () => changed(draft));
    const metadata = el("div", "local-form-grid"); metadata.append(field("来源URL或本地标识", url), field("媒体类型（声明）", media));
    card.append(el("h3", "", file.name), el("p", "detail-note", source.id + " · " + formatBytes(file.size)), metadata, field("许可及访问范围（声明）", license),
      el("div", "local-evidence-selections"), add, remove);
    draft.sources.push(source); draft.files.append(card); addSelection(draft, source); changed(draft);
  }
  chooser.addEventListener("change", () => { void (async () => {
    const draft = current(), files = Array.from(chooser.files ?? []); chooser.value = "";
    if (!draft || !files.length) return;
    try {
      if (draft.sources.length + files.length > 8) throw Error("每次登记最多8个来源文件；现有草稿已保留。");
      if (draft.sources.reduce((total, source) => total + source.size, 0) + files.reduce((total, file) => total + file.size, 0) > MAX_TOTAL) throw Error("来源总字节超过64MiB；现有草稿已保留。");
      if (files.some(file => !file.size || file.size > MAX_FILE || file.name.length > 160 || /[<>:"/\\|?*\u0000-\u001f]/.test(file.name))) throw Error("文件须非空、每份不超过32MiB，并使用安全文件名。");
      draft.loading = true; controls(); fileStatus.textContent = "正在准备所选原字节，尚未上传、登记或读取…";
      for (const file of files) addSource(draft, file, encode(new Uint8Array(await file.arrayBuffer())));
      if (draft.projectId === active) fileStatus.textContent = `草稿共${draft.sources.length}份来源、${selectionCount(draft)}个选区；请填写来源及真实坐标后登记。`;
    } catch (error) { host.announce(error instanceof Error ? error.message : "文件准备未完成，草稿保留。", true); }
    finally { draft.loading = false; controls(); }
  })(); });

  function sourceDownloads(target: HTMLElement, receipt: Obj, expectedProject: string): void {
    if (object(receipt.task_ref).project_id !== expectedProject) throw Error("回执不属于当前项目，不能作为本次来源展示。");
    const digest = receipt.snapshot_sha256;
    if (!sha(digest)) throw Error("来源回执SHA不完整。");
    for (const source of objects(receipt.sources)) {
      const row = el("div", "local-evidence-original"); row.append(el("strong", "", string(source.id)),
        el("p", "detail-note", string(source.media_type) + " · SHA " + string(source.sha256).slice(0, 12)),
        el("p", "detail-note", "来源声明：" + string(source.url)), el("p", "detail-note", "许可声明：" + string(source.license_note)));
      if (safeId(source.id) && sha(source.sha256)) { const link = el("a", "text-button", "下载这份已捕获原件 ↓"); link.href = "/api/project/evidence-source/" + digest + "/" + encodeURIComponent(source.id); row.append(link); }
      const external = safeUrl(source.url); if (external) { const link = el("a", "text-button", "访问声明的原始来源 ↗"); link.href = external; link.target = "_blank"; link.rel = "noopener noreferrer"; row.append(link); }
      target.append(row);
    }
    const details = el("details", "local-advanced"); details.append(el("summary", "", "完整回执、原件SHA与选区声明"), el("pre", "project-source-text", JSON.stringify(receipt, null, 2))); target.append(details);
  }
  function registered(): void {
    packages.replaceChildren(el("h3", "", "已保存的资料包"));
    const records = objects(project.registered_evidence), unread = records.filter(record => ["unread", "registered_unread"].includes(string(record.read_status, ""))).length;
    packages.append(el("p", "detail-note", `共${records.length}个已登记包，其中${unread}个尚未读取；登记不等于提取或科学批准。`));
    const status: Record<string, string> = { unread: "已登记，尚未读取", registered_unread: "已登记，尚未读取", completed: "读取完成", failed: "读取失败，原记录保留", unknown: "读取状态待核对，不自动重发" };
    for (const record of records) {
      const digest = record.receipt_snapshot_sha256; if (!sha(digest)) continue;
      const row = el("details", "local-evidence-receipt"), summary = el("summary", "", `资料包${String(record.ordinal ?? "")} · ${status[string(record.read_status)] ?? "状态未记录"} · ${String(record.source_count ?? "?")}份原件 / ${String(record.selection_count ?? "?")}个选区`);
      const link = el("a", "text-button", "下载登记回执 JSON ↓"); link.href = "/api/project/evidence-receipt/" + digest + ".json"; link.download = "evidence-" + digest.slice(0, 12) + ".json";
      const content = el("div"); content.append(link); row.append(summary, content); let loaded = false;
      const projectId = active;
      row.addEventListener("toggle", () => { if (!row.open || loaded) return; loaded = true; void (async () => {
        try { const value = await host.read(link.href); if (projectId !== active) return; sourceDownloads(content, object(value.receipt).schema_version ? object(value.receipt) : value, projectId); }
        catch (error) { loaded = false; content.append(el("p", "notice", error instanceof Error ? error.message : "回执读取失败；收起再展开可只读核对。")); }
      })(); }); packages.append(row);
    }
  }
  form.addEventListener("submit", event => { event.preventDefault(); void (async () => {
    const draft = current(); if (!draft || !task || locked || draft.loading || draft.submitting || !form.reportValidity()) return;
    try {
      const taskRef = object(task.task_ref), selections = draft.sources.flatMap(source => source.selections.map(selection => ({ id: selection.id, source_id: source.id,
        locator: { kind: selection.kind.value, value: selection.value.value.trim() }, claim: selection.claim.value.trim() })));
      if (!draft.sources.length || draft.sources.length > 8 || !selections.length || selections.length > 32) throw Error("需要1至8个来源文件和1至32个明确选区。");
      if (selections.some(selection => !selection.locator.value || !selection.claim || !["text_lines", "pdf_page", "xlsx_cell"].includes(selection.locator.kind))) throw Error("每个选区都需明确坐标与提交者主张，不能以空坐标默认读取全文。");
      const questions = draft.questions.value.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
      if (questions.length > 64 || questions.some(line => line.length > 4000)) throw Error("未决问题最多64条，每条不超过4000字符。");
      if (task.project_id !== active || taskRef.project_id !== active || typeof task.state_version !== "number") throw Error("当前取证任务尚未核对，请只读刷新后重新提交。");
      const body = { project_id: active, expected_state_version: task.state_version, task_ref: taskRef,
        contributor: { role: "operator_assistant", label: "本地工作台提交（操作者身份未核验）" },
        sources: draft.sources.map(source => ({ id: source.id, file_name: source.name, bytes_base64: source.encoded, url: source.url.value.trim(), media_type: source.media.value.trim(), license_note: source.license.value.trim() })),
        selections, remaining_questions: questions };
      draft.submitting = true; controls();
      const result = await host.submit(body);
      if (result) acceptRegistered(result);
    } catch (error) { host.announce(error instanceof Error ? error.message : "登记未完成，资料草稿已保留。", true); }
    finally { draft.submitting = false; controls(); }
  })(); });

  async function refresh(projectId: string, nextProject: Obj): Promise<void> {
    const token = ++refreshId; active = projectId; project = nextProject; task = null; loadingTask = !!active;
    draftHost.replaceChildren(); registered(); controls();
    const draft = current();
    if (!draft) { taskStatus.textContent = "先创建或选择项目，再执行检查产生实际取证任务。"; taskText.textContent = "尚无活动项目。"; return; }
    draftHost.append(draft.files, field("本次仍未解决的问题（可选，每行一条）", draft.questions));
    fileStatus.textContent = draft.sources.length ? `本项目资料草稿保留${draft.sources.length}份来源；草稿仅在当前页面内存保留。` : "请选择实际资料文件；登记与读取分开进行。";
    taskStatus.textContent = "正在只读核对当前取证任务…";
    try {
      const value = await host.read("/api/project/evidence-task.json"); if (token !== refreshId || active !== projectId) return;
      if (value.project_id !== active || object(value.task_ref).project_id !== active || typeof value.state_version !== "number") throw Error("取证任务不属于当前项目或缺少版本，不能提交。");
      task = value; taskText.textContent = JSON.stringify({ task_ref: value.task_ref, state_version: value.state_version, snapshot_ref: value.snapshot_ref, requirements_from_action_id: value.requirements_from_action_id, required_evidence: strings(value.required_evidence) }, null, 2);
      taskStatus.textContent = "已绑定当前项目的实际取证任务。只登记资料，读取仍需另行明确选择。";
    } catch (error) {
      if (token !== refreshId) return;
      const message = error instanceof Error ? error.message : "当前取证任务暂不可读取。";
      taskStatus.textContent = message.includes("TASK_NOT_AVAILABLE") ? "先执行一次检查产生取证任务；当前创建、选择或已有候选操作不受此面板影响。" : "取证任务尚未核对，先只读刷新；资料草稿保留。";
      taskText.textContent = message;
    } finally { if (token === refreshId) { loadingTask = false; controls(); } }
  }
  controls(); registered();
  return { element: section, setLocked(value: boolean): void { locked = value; controls(); }, refresh, acceptRegistered };
}
