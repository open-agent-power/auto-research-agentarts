/** Explicitly save a successor plan; preserve its original request across uncertainty. */
import { el } from "./dom";

type Obj = Record<string, unknown>;
const object = (value: unknown): Obj => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const array = (value: unknown): Obj[] => Array.isArray(value) ? value.map(object) : [];
const id = (value: unknown): value is string => typeof value === "string" && value.length > 0 && value.length <= 160;
const hash = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const version = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
const MARKER_KEY = "autoresearch.local-workbench.staged-successor.marker.v1";
const SESSION_KEY = "autoresearch.local-workbench.staged-successor.session.v1";
const LOCK = "autoresearch.local-workbench.staged-successor-save.v1";
const equal = (a: unknown, b: unknown): boolean => {
  if (a === b) return true;
  if (Array.isArray(a) || Array.isArray(b)) return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((v,i) => equal(v,b[i]));
  if (a === null || b === null || typeof a !== "object" || typeof b !== "object") return false;
  const x = object(a), y = object(b), keys = Object.keys(x).sort(), ys = Object.keys(y).sort();
  return keys.length === ys.length && keys.every((k,i) => k === ys[i] && equal(x[k],y[k]));
};
const sha = async (value: string): Promise<string> => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value))), b => b.toString(16).padStart(2,"0")).join("");

export function createStagedSuccessorSavePanel(deps: {
  current(): Obj; context(): Obj | null; active(): string; readDraft(): Obj | null;
  scanNow(projectId: string, snapshot: string): Promise<Obj>;
  post(name: "staged-feedback-plan" | "staged-feedback-plan-resume", body: string): Promise<Obj>;
  read(path: string): Promise<Obj>; enabled(): boolean; generation(): number; setBusy(value: boolean): void; onState(): void; refresh(): Promise<void>;
}): { element: HTMLElement; update(project: Obj): void; setLocked(value: boolean): void; pending(): boolean; recover(): Promise<void> } {
  const section = el("section", "local-panel"), title = el("h3", "", "保存反馈后的后续计划"),
    details = el("p", "detail-note", "先在研究计划中填写可编辑草稿，再明确选择已完成的原反馈。此操作保存计划与原链引用，可能补原 manager 回执，不派发工具、模型或拟合；历史费用未知。旧项目 pin 不自动升级。"),
    select = el("select"), info = el("p", "detail-note"), status = el("p", "detail-note"), actions = el("div", "local-actions"),
    submit = el("button", "local-primary", "保存关联原反馈的计划"), resume = el("button", "text-button", "只核对原后续计划请求");
  details.textContent += " 原计划如已不是最新版本，页面保留原正文并停查。存储清理不具跨存储事务保证。";
  section.dataset.testid = "staged-successor-save"; select.setAttribute("aria-label", "选择原已完成反馈"); submit.type = resume.type = "button";
  actions.append(submit, resume); section.append(title, details, el("p", "detail-note", "正文保留在本标签的 sessionStorage，非正文身份哨兵保存在本浏览器 localStorage；二者并非安全持久存储。仅协调同源合作标签；双存储均被清除或跨设备时无法识别。"), select, info, actions, status);
  let locked = true, inFlight = false, snapshot = "";
  function pending(): boolean { try { return localStorage.getItem(MARKER_KEY) !== null || sessionStorage.getItem(SESSION_KEY) !== null; } catch { return true; } }
  function choices(): {parent: Obj; choice: Obj; feedback: Obj}[] {
    const project = deps.current(), context = deps.context(), parents = object(project.staged_feedback_parents), projection = object(project.staged_primary_choices);
    if (!context || !id(project.id) || !id(project.run_id) || project.id !== deps.active() || !hash(project.snapshot_ref) || !version(project.state_version)
      || context.project_id !== project.id || context.run_id !== project.run_id || context.snapshot_ref !== project.snapshot_ref || context.state_version !== project.state_version || !hash(context.context_sha256)
      || !Array.isArray(context.blockers) || context.blockers.length !== 0 || context.staged_evaluation !== undefined || !equal(context.hypothesis_feedback, project.hypothesis_feedback)
      || parents.schema_version !== "staged-feedback-parent-view-v1" || parents.verification !== "state_fields_only_not_claim_sql_or_artifacts" || parents.project_id !== project.id || parents.run_id !== project.run_id || parents.snapshot_ref !== project.snapshot_ref || parents.state_version !== project.state_version
      || projection.schema_version !== "staged-primary-choices-v1" || projection.verification !== "registration_metadata_only" || projection.manager_ownership_verified !== false || projection.project_id !== project.id || projection.snapshot_ref !== project.snapshot_ref || projection.state_version !== project.state_version
      || !Array.isArray(parents.items) || !Array.isArray(projection.items) || !Array.isArray(object(context.hypothesis_feedback).items)) return [];
    const parentRows = array(parents.items), choiceRows = array(projection.items), feedbackRows = array(object(context.hypothesis_feedback).items);
    if (new Set(parentRows.map(p => p.request_id)).size !== parentRows.length || parentRows.some(p => !id(p.request_id))
      || new Set(choiceRows.map(p => p.registration_request_id)).size !== choiceRows.length || choiceRows.some(p => !id(p.registration_request_id))) return [];
    return parentRows.flatMap(parent => {
      const candidates = choiceRows.filter(c => c.registration_request_id === parent.registration_request_id && c.registration_sha256 === parent.registration_sha256);
      const feedbacks = feedbackRows.filter(f => f.request_id === parent.registration_request_id && f.registration_sha256 === parent.registration_sha256 && f.action_id === parent.primary_action_id && f.result_sha256 === parent.primary_result_sha256);
      if (candidates.length !== 1 || feedbacks.length !== 1) return [];
      const choice = candidates[0], feedback = feedbacks[0], actions = array(project.actions).filter(a => a.id === parent.primary_action_id && a.result_sha256 === parent.primary_result_sha256 && a.command === "research.relevance-validation-pair" && a.status === "completed");
      const values = feedback.value, conditions = array(object(feedback.condition).all), candidate = object(choice.candidate);
      if (parent.project_id !== project.id || parent.run_id !== project.run_id || !hash(parent.registration_sha256) || !id(parent.primary_action_id) || !hash(parent.primary_result_sha256)
        || !((parent.decision === "wait" && parent.status === "waiting" && parent.child_request_id === null) || (parent.decision === "audit" && parent.status === "completed" && id(parent.child_request_id)))
        || !["condition_met", "condition_not_met"].includes(String(feedback.outcome)) || feedback.unknown_reason !== null || feedback.controller_request_id !== choice.controller_request_id
        || !Array.isArray(values) || values.length !== 2 || values.some(v => typeof v !== "number" || !Number.isFinite(v) || v < -1 || v > 1)
        || conditions.length !== 2 || new Set(conditions.map(c => c.metric)).size !== 2 || conditions.some(c => !["recall@20", "mrr@10"].includes(String(c.metric)) || !["gt", "gte", "lt", "lte", "eq"].includes(String(c.operator)) || typeof c.threshold !== "number" || !Number.isFinite(c.threshold))
        || candidate.method_id !== "research.relevance-validation-pair" || candidate.evaluation_ref !== "staged-relevance-development-v1" || Object.keys(object(candidate.parameters)).length !== 0 || !equal(candidate,feedback.candidate)
        || choice.plan_matches !== true || choice.source_matches !== true || choice.code_matches !== true || !version(choice.plan_version) || choice.plan_version !== object(context.research_plan).version
        || !hash(choice.plan_sha256) || !hash(choice.source_snapshot_sha256) || choice.source_snapshot_sha256 !== context.source_snapshot_sha256 || actions.length !== 1) return [];
      const check = (c:Obj, v:number):boolean => c.operator === "gt" ? v > Number(c.threshold) : c.operator === "gte" ? v >= Number(c.threshold) : c.operator === "lt" ? v < Number(c.threshold) : c.operator === "lte" ? v <= Number(c.threshold) : v === Number(c.threshold);
      if ((feedback.outcome === "condition_met") !== conditions.every((c,i) => check(c, values[i] as number))) return [];
      return [{parent, choice, feedback}];
    });
  }
  function controls(): void {
    const found = choices().filter(c => c.parent.request_id === select.value), hasPending = pending();
    select.disabled = locked || inFlight || hasPending || choices().length === 0;
    submit.disabled = locked || inFlight || hasPending || found.length !== 1 || !deps.enabled();
    resume.hidden = !hasPending; resume.disabled = inFlight || !deps.enabled();
    const c = found.length === 1 ? found[0] : null;
    info.textContent = c ? `原反馈 ${String(c.parent.request_id)} · 登记 ${String(c.parent.registration_request_id)} · SHA ${String(c.parent.registration_sha256)} · primary ${String(c.parent.primary_action_id)} · 结果 SHA ${String(c.parent.primary_result_sha256)} · 原计划 ${String(c.choice.plan_version)} / ${String(c.choice.plan_sha256)} · 反馈 ${String(c.feedback.outcome)} · 原选择 ${String(c.parent.decision)}。这些只作快照身份对照，提交时服务端另核原链。` : "选择当前项目快照中的已知、完成原反馈。未知或身份不匹配时停查；不得把 S108 子集当成本次总体反馈。";
  }
  function update(project: Obj): void {
    const next = typeof project.snapshot_ref === "string" ? project.snapshot_ref : "", previous = next === snapshot ? select.value : ""; snapshot = next;
    select.replaceChildren(); const blank = el("option", "", "请选择原反馈"); blank.value = ""; select.append(blank);
    for (const c of choices()) { const option = el("option", "", `${String(c.parent.request_id)} · ${String(c.feedback.outcome)} · ${String(c.parent.decision)}`); option.value = String(c.parent.request_id); select.append(option); }
    select.value = [...select.options].some(o => o.value === previous) ? previous : "";
    section.hidden = project.primary_method !== "research.relevance-validation-pair" && !pending(); controls();
  }
  function scanValid(scan: Obj, project: Obj, request: string | null): boolean {
    if (scan.schema_version !== "staged-successor-pending-v1" || scan.verification !== "manager_rows_only_not_project_claims" || scan.status !== "available"
      || scan.project_id !== project.id || scan.run_id !== project.run_id || scan.snapshot_ref !== project.snapshot_ref || scan.state_version !== project.state_version
      || !version(scan.total) || !version(scan.shown) || scan.shown !== Math.min(scan.total,8) || scan.truncated !== (scan.total > 8) || scan.truncated || !Array.isArray(scan.items)) return false;
    const records = array(scan.items);
    if (records.length !== scan.shown || records.some(v => !id(v.request_id) || v.status !== "preparing") || new Set(records.map(v => v.request_id)).size !== records.length) return false;
    return request === null ? scan.total === 0 : scan.total === 0 || (scan.total === 1 && records[0].request_id === request);
  }
  function stable(project: Obj): boolean { const now = deps.current(); return deps.active() === project.id && now.id === project.id && now.run_id === project.run_id && now.snapshot_ref === project.snapshot_ref && now.state_version === project.state_version; }
  function validReceipt(r: Obj, body: Obj, identity: Obj, replayed: boolean): boolean {
    const ref = object(r.staged_feedback_ref);
    return Object.keys(r).sort().join(",") === "based_on_state_version,command,plan_sha256,plan_version,project_id,replayed,request_id,schema_version,staged_feedback_ref,status"
      && r.schema_version === "staged-successor-plan-receipt-v1" && r.command === "save_staged_feedback_plan" && r.status === "completed" && r.replayed === replayed
      && r.request_id === body.request_id && r.project_id === body.project_id && r.based_on_state_version === body.expected_state_version
      && version(r.plan_version) && r.plan_version === Number(identity.original_plan_version) + 1 && hash(r.plan_sha256)
      && ref.schema_version === "staged-feedback-plan-reference-v1" && ref.feedback_parent_request_id === body.feedback_request_id
      && ref.registration_request_id === identity.registration_request_id && ref.registration_sha256 === identity.registration_sha256
      && ref.original_plan_version === identity.original_plan_version && ref.original_plan_sha256 === identity.original_plan_sha256
      && ref.source_snapshot_sha256 === identity.source_snapshot_sha256 && ref.primary_parent_request_id === identity.primary_parent_request_id
      && ref.primary_action_id === identity.primary_action_id && ref.primary_result_sha256 === identity.primary_result_sha256
      && ref.feedback_outcome === identity.feedback_outcome && ref.decision === identity.decision;
  }
  async function finish(record: Obj, markerRaw: string, sessionRaw: string, first: Obj | null, generation: number): Promise<void> {
    const bodyRaw = record.body; if (typeof bodyRaw !== "string") throw Error("原正文不可用；停止核对。");
    const body = object(JSON.parse(bodyRaw)), identity = object(record.identity), marker = object(JSON.parse(markerRaw));
    if (!id(body.request_id) || !id(body.project_id) || marker.project_id !== body.project_id || marker.request_id !== body.request_id
      || marker.schema_version !== "staged-successor-request-marker-v1" || !id(marker.owner) || !hash(marker.body_sha256)
      || marker.body_sha256 !== await sha(bodyRaw) || identity.project_id !== body.project_id || deps.active() !== body.project_id || deps.current().id !== body.project_id
      || deps.current().run_id !== identity.run_id) throw Error("原请求正文或项目身份不一致；保留原记录。");
    const localProject = deps.current(), managerBefore = await deps.read("/api/local-workbench"), project = await deps.read("/api/project");
    if (managerBefore.active_project_id !== body.project_id || project.id !== body.project_id || project.run_id !== identity.run_id || !hash(project.snapshot_ref) || !version(project.state_version)
      || !stable(localProject) || deps.generation() !== generation
      || !scanValid(await deps.scanNow(String(project.id),String(project.snapshot_ref)), project, String(body.request_id)) || !stable(localProject) || deps.generation() !== generation)
      throw Error("未决状态或项目快照不可核对；保留原记录。");
    const checked = await deps.post("staged-feedback-plan-resume", bodyRaw);
    if (!validReceipt(checked,body,identity,true) || first && !equal({...first,replayed:true},checked)) throw Error("原回执身份不一致；保留原正文。");
    const manager = await deps.read("/api/local-workbench"), latest = await deps.read("/api/project");
    if (!stable(localProject) || deps.generation() !== generation || manager.active_project_id !== body.project_id
      || latest.id !== body.project_id || latest.run_id !== identity.run_id || latest.snapshot_ref !== project.snapshot_ref || latest.state_version !== project.state_version)
      throw Error("项目已切换或快照不可核对；保留原正文。");
    const projection = object(latest.staged_successor_plan_identity);
    if (projection.schema_version !== "staged-successor-plan-identity-v1" || projection.verification !== "state_fields_only_not_claim_sql_or_artifacts"
      || projection.project_id !== body.project_id || projection.run_id !== identity.run_id || projection.snapshot_ref !== latest.snapshot_ref
      || projection.state_version !== latest.state_version || projection.plan_request_id !== body.request_id || projection.plan_version !== checked.plan_version
      || projection.plan_sha256 !== checked.plan_sha256) throw Error("原计划不再是可核对的最新修订，或 SHA 不一致；保留原正文。");
    const revisions = array(object(latest.research_plan).revisions).filter(r => r.request_id === body.request_id);
    if (revisions.length !== 1 || revisions[0].version !== checked.plan_version || revisions[0].based_on_state_version !== body.expected_state_version
      || !equal(revisions[0].staged_feedback_ref,checked.staged_feedback_ref)) throw Error("保存的原计划身份不匹配；保留原正文。");
    const finalScan = await deps.scanNow(String(latest.id), String(latest.snapshot_ref));
    const managerFinal = await deps.read("/api/local-workbench"), projectFinal = await deps.read("/api/project");
    if (!scanValid(finalScan, latest, null) || projectFinal.id !== latest.id || projectFinal.run_id !== latest.run_id
      || projectFinal.state_version !== latest.state_version || projectFinal.snapshot_ref !== latest.snapshot_ref
      || !equal(projectFinal.staged_successor_plan_identity, projection) || !stable(localProject) || deps.generation() !== generation || managerFinal.active_project_id !== body.project_id || localStorage.getItem(MARKER_KEY) !== markerRaw || sessionStorage.getItem(SESSION_KEY) !== sessionRaw)
      throw Error("未决状态或原存储身份已改变；保留原记录。");
    if (localStorage.getItem(MARKER_KEY) !== markerRaw) throw Error("原哨兵已改变；停止清理。");
    localStorage.removeItem(MARKER_KEY); if (localStorage.getItem(MARKER_KEY) !== null) throw Error("原哨兵未能清除。");
    try {
      if (sessionStorage.getItem(SESSION_KEY) !== sessionRaw) throw Error("原会话正文已改变。");
      sessionStorage.removeItem(SESSION_KEY);
      if (sessionStorage.getItem(SESSION_KEY) !== null) throw Error("会话正文未能清除。");
    } catch (error) {
      // Same-origin cooperative tabs are serialized by the lock, but neither storage is transactional.
      // Restore only an absent marker; never overwrite a marker installed by another actor.
      try { if (localStorage.getItem(MARKER_KEY) === null) localStorage.setItem(MARKER_KEY, markerRaw); } catch { /* Preserve whatever remains for manual inspection. */ }
      throw error;
    }
    status.textContent = "原后续计划与 manager claim 已由 resume-only 核对；必要时补了原回执。未派发研究。";
    await deps.refresh();
  }
  async function withLock(work: () => Promise<void>): Promise<void> {
    if (inFlight || !deps.enabled()) return;
    inFlight = true; deps.setBusy(true); controls(); deps.onState();
    try {
      if (!navigator.locks || !crypto.subtle || !crypto.randomUUID) throw Error("浏览器不支持所需锁或存储核验，不能发送。");
      await navigator.locks.request(LOCK, {ifAvailable:true}, async lock => { if (!lock) throw Error("另一标签正在核对原请求；本次未发送。"); await work(); });
    } catch (error) { status.textContent = (error instanceof Error ? error.message : "请求状态未知。") + " 原 ID 和正文若已保存则保留；不得以新 ID 替代。"; }
    finally { inFlight = false; deps.setBusy(false); controls(); deps.onState(); }
  }
  async function recover(): Promise<void> {
    await withLock(async () => {
      const markerRaw = localStorage.getItem(MARKER_KEY), sessionRaw = sessionStorage.getItem(SESSION_KEY);
      if (!markerRaw || !sessionRaw) throw Error("缺少原哨兵或本标签原正文，停止；不能从当前草稿重建。");
      const saved = object(JSON.parse(sessionRaw)); if (saved.schema_version !== "staged-successor-session-v1") throw Error("原会话身份异常。");
      await finish(saved, markerRaw, sessionRaw, null, deps.generation());
    });
  }
  submit.addEventListener("click", () => { if (submit.disabled) return; void withLock(async () => {
    const generation = deps.generation(), project = deps.current(), entries = choices().filter(c => c.parent.request_id === select.value), draft = deps.readDraft();
    if (entries.length !== 1 || !draft || !stable(project) || draft.project_id !== project.id || draft.expected_state_version !== project.state_version || pending()) throw Error("当前计划、反馈或项目快照不可用。");
    const scan = await deps.scanNow(String(project.id), String(project.snapshot_ref));
    const latestEntries = choices().filter(c => c.parent.request_id === select.value);
    if (!stable(project) || deps.generation() !== generation || !scanValid(scan,project,null) || latestEntries.length !== 1 || !equal(entries[0], latestEntries[0]) || pending()) throw Error("项目快照或未决状态已变化，未发送。");
    const c = entries[0], request = `local-successor-plan-${crypto.randomUUID()}`, body = {request_id:request, project_id:project.id, expected_state_version:project.state_version,
      feedback_request_id:c.parent.request_id, plan:draft.plan, reason:draft.reason}, bodyRaw = JSON.stringify(body);
    if (new TextEncoder().encode(bodyRaw).length > 192 * 1024) throw Error("计划正文超出大小限制。");
    const identity = {project_id:project.id, run_id:project.run_id, snapshot_ref:project.snapshot_ref, original_plan_version:c.choice.plan_version,
      original_plan_sha256:c.choice.plan_sha256, source_snapshot_sha256:c.choice.source_snapshot_sha256, registration_request_id:c.parent.registration_request_id,
      registration_sha256:c.parent.registration_sha256, primary_parent_request_id:c.choice.controller_request_id, primary_action_id:c.parent.primary_action_id,
      primary_result_sha256:c.parent.primary_result_sha256, feedback_outcome:c.feedback.outcome, decision:c.parent.decision};
    const markerRaw = JSON.stringify({schema_version:"staged-successor-request-marker-v1",project_id:project.id,request_id:request,owner:crypto.randomUUID(),body_sha256:await sha(bodyRaw)});
    const sessionRaw = JSON.stringify({schema_version:"staged-successor-session-v1",body:bodyRaw,identity});
    if (!stable(project) || deps.generation() !== generation || pending()) throw Error("项目或原请求状态变化，未发送。");
    localStorage.setItem(MARKER_KEY,markerRaw); if (localStorage.getItem(MARKER_KEY) !== markerRaw) throw Error("哨兵写入核对失败，未发送。");
    sessionStorage.setItem(SESSION_KEY,sessionRaw); if (sessionStorage.getItem(SESSION_KEY) !== sessionRaw || localStorage.getItem(MARKER_KEY) !== markerRaw) throw Error("原正文写入核对失败，未发送。");
    if (!stable(project) || deps.generation() !== generation) throw Error("项目快照变化，未发送；保留原正文。");
    const saved = await deps.post("staged-feedback-plan",bodyRaw);
    if (!validReceipt(saved,body,identity,false)) throw Error("保存回执无法核对；状态未知。");
    await finish(object(JSON.parse(sessionRaw)),markerRaw,sessionRaw,saved,generation);
  }); });
  resume.addEventListener("click", () => { if (!resume.disabled) void recover(); });
  select.addEventListener("change", controls);
  window.addEventListener("storage", event => { if (event.key === MARKER_KEY || event.key === null) { controls(); deps.onState(); } });
  controls(); return {element:section, update, setLocked(value):void { locked = value; controls(); }, pending, recover};
}
