import { el, numeric } from "./dom";
import { requestJson } from "./api";

type Trial = { id: string; ordinal: number; status: string; candidate: {degree: number; alpha: number}; metrics?: Record<string, number>; decision_reason?: string; error_code?: string; proposal?: {hypothesis?: string; expected_effect?: string; evidence_trial_ids?: string[]} };
type Job = { job_id: string; request_id: string; status: string; trial_id: string | null; error_code: string | null };
type State = { enabled: boolean; status: "disabled" | "idle" | "running" | "paused" | "completed" | "needs_review" | "failed"; origin: string; parent_snapshot_sha256: string; independent_run: boolean; consumed: number; max_trials: number; cloud_calls: number; model_calls: number; can_step: boolean; job_id: string | null; reason: string | null; jobs: Job[]; trials: Trial[] };

// Retain an unresolved request across view changes. An uncertain POST is only
// retried with the same id; querying status never starts a job.
let pendingRequest: string | null = null;
let pendingKey = "";
let submitting = false;

function checked(value: unknown, snapshot: string): State {
  if (!value || typeof value !== "object") throw new Error("本地实验状态无法读取。");
  const state = value as State;
  const states = ["disabled", "idle", "running", "paused", "completed", "needs_review", "failed"];
  if (typeof state.enabled !== "boolean" || !states.includes(state.status) || state.origin !== "local_script_not_llm" || state.parent_snapshot_sha256 !== snapshot || state.independent_run !== true || state.cloud_calls !== 0 || state.model_calls !== 0 || !Array.isArray(state.trials) || !Array.isArray(state.jobs) || !Number.isInteger(state.consumed) || state.max_trials !== 2 || typeof state.can_step !== "boolean") throw new Error("本地实验状态与当前快照不匹配，请检查服务。");
  return state;
}

export function mountLocalDemo(host: HTMLElement, token: string, snapshot: string): void {
  const storageKey = "autoresearch-demo-request:v1:" + snapshot;
  let storageAvailable = true;
  if (pendingKey !== storageKey) {
    pendingKey = storageKey;
    pendingRequest = null;
    try {
      const saved = sessionStorage.getItem(storageKey);
      if (saved && /^studio-[A-Za-z0-9-]{1,64}$/.test(saved)) pendingRequest = saved;
      else if (saved) sessionStorage.removeItem(storageKey);
    } catch { storageAvailable = false; }
  } else {
    try { sessionStorage.getItem(storageKey); } catch { storageAvailable = false; }
  }
  let current: State | null = null;
  let message = "";
  let failed = false;
  let timer = 0;
  let revision = 0;
  const alive = () => host.isConnected;
  const requestId = () => "studio-" + crypto.randomUUID();
  const clearPending = () => {
    pendingRequest = null;
    try { sessionStorage.removeItem(storageKey); } catch { storageAvailable = false; }
  };

  function draw(): void {
    if (!alive()) return;
    host.replaceChildren();
    const intro = el("div", "demo-heading");
    const copy = el("div"); copy.append(el("span", "demo-kicker", "独立本地演示"), el("h2", "", "运行与记录"), el("p", "", "使用固定公开钢材数据和脚本策略，每次运行一个真实训练实验。"));
    intro.append(copy);
    const panel = el("div", "demo-panel");
    panel.append(intro, el("p", "demo-boundary", "这是独立的工程演示，不继承历史模型或预算；脚本策略不是大语言模型。原研究快照和待处理问题不会被改写。顶部下载仍是原快照的报告与附件，本页实验尚未纳入导出。"));
    const feedback = el("p", "demo-feedback" + (failed ? " error" : ""), message); feedback.setAttribute("role", "status"); feedback.setAttribute("aria-live", "polite");
    if (!current) {
      panel.append(feedback);
      const retry = el("button", "quiet-button", "重新读取状态"); retry.addEventListener("click", () => { void refresh(); }); panel.append(retry); host.append(panel); return;
    }
    const labels: Record<State["status"], string> = {disabled:"未启用",idle:"尚未开始",running:"执行中",paused:"已暂停",completed:"次数用尽",needs_review:"需要核查",failed:"执行失败"};
    const summary = el("div", "demo-summary");
    for (const [name,value] of [["运行状态",labels[current.status]],["已执行实验",`${current.consumed} / ${current.max_trials}`],["决策方式","本地脚本"]] as const) { const block=el("div");block.append(el("span","",name),el("strong","",value));summary.append(block); }
    panel.append(summary);
    if (!current.enabled) panel.append(el("p", "detail-note", "当前服务以查看模式启动。启用本地演示后可从这里执行实验。"));
    if (!storageAvailable) panel.append(el("p", "detail-note", "浏览器会话存储不可用，暂不能安全提交实验。阅读不受影响。"));
    if (current.status === "needs_review") panel.append(el("p", "detail-note", "存在未确认的任务。请核查运行进程和记录；系统不会自动重跑。"));
    if (current.status === "failed") panel.append(el("p", "detail-note", "实验未完成。错误记录已保留，不会自动重试。"));
    if (current.status === "completed") panel.append(el("p", "detail-note", "本地演示已达到两次实验上限。"));
    const reasons: Record<string,string> = {step_in_progress:"实验正在运行。",step_finished:"本次实验已完成，可以继续下一次。",trial_budget_exhausted:"已达到本地演示次数上限。",pending_worker_state_unconfirmed:"未确认任务是否完成，请先核查。",trial_state_unconfirmed:"实验状态尚未确认，请先核查。",execution_failed_requires_review:"执行失败，请先核查记录。",local_storage_requires_review:"本地记录需要核查。"};
    if (current.reason && current.status !== "completed") panel.append(el("p", "demo-reason", reasons[current.reason] || "请查看本地运行记录。"));
    const actions = el("div", "demo-actions");
    const run = el("button", "action-button primary", current.status === "completed" ? "实验次数已用完" : pendingRequest ? "重试同一请求" : current.consumed ? "继续下一次实验" : "开始第一次实验");
    run.disabled = !current.enabled || !token || !storageAvailable || submitting || (!pendingRequest && !current.can_step) || current.status === "running" || current.status === "needs_review" || current.status === "failed" || current.status === "completed";
    run.addEventListener("click", () => { void step(); });
    const refreshButton = el("button", "action-button", "刷新状态"); refreshButton.disabled = submitting; refreshButton.addEventListener("click", () => { void refresh(); });
    actions.append(run, refreshButton); panel.append(actions, feedback);
    const results = el("div", "demo-results"); results.append(el("h3", "", "实验记录"));
    if (!current.trials.length) results.append(el("p", "empty-state", "暂无实验记录。"));
    current.trials.forEach((trial) => {
      const row = el("article", "demo-trial"); const top = el("div", "demo-trial-title");
      const labels: Record<string,string>={accepted:"当次采用",rejected:"未晋升",running:"执行中",failed:"失败"};
      top.append(el("strong", "", "实验 " + String(trial.ordinal).padStart(2,"0")),el("span", "status-badge " + trial.status, labels[trial.status] || "状态待核对"));
      row.append(top,el("p", "", `${numeric(trial.candidate.degree)} 阶 · α ${numeric(trial.candidate.alpha)}`));
      if (trial.proposal?.hypothesis) row.append(el("p", "demo-detail", "脚本提案：" + trial.proposal.hypothesis));
      const cited = trial.proposal?.evidence_trial_ids || [];
      if (cited.length) row.append(el("p", "demo-detail", "依据：" + cited.map((id) => { const previous = current?.trials.find((item) => item.id === id); return previous ? "实验 " + String(previous.ordinal).padStart(2,"0") : id; }).join("、")));
      if (trial.metrics) row.append(el("p", "demo-metric", "验证 MSE  " + numeric(trial.metrics.validation_mse)));
      const decisions: Record<string,string> = {"fixed validation improvement gate passed":"达到预设验证门槛。", "no required validation improvement; previous model retained":"未达到预设改善门槛，保留前一个模型。"};
      if (trial.decision_reason) row.append(el("p", "demo-detail", decisions[trial.decision_reason] || trial.decision_reason));
      if (trial.error_code) row.append(el("p", "demo-detail", "错误代码：" + trial.error_code));
      results.append(row);
    });
    host.append(panel, results);
  }

  async function refresh(): Promise<void> {
    const seq = ++revision; window.clearTimeout(timer);
    try {
      const state = checked(await requestJson("/api/local-demo"), snapshot);
      if (!alive() || seq !== revision) return;
      current = state;
      if (pendingRequest && state.jobs.some((job) => job.request_id === pendingRequest)) clearPending();
      if (!pendingRequest) { message = ""; failed = false; }
      else { message = "上次提交结果未确认。可使用同一请求编号重试，或刷新状态。"; failed = true; }
      draw();
      if (state.status === "running" || submitting) timer = window.setTimeout(() => { if (alive()) void refresh(); }, 1500);
    } catch (error) {
      if (!alive() || seq !== revision) return;
      current = null; message = error instanceof Error ? error.message : "状态读取失败。"; failed = true; draw();
    }
  }

  async function step(): Promise<void> {
    if (submitting || !storageAvailable || !current?.enabled || (!pendingRequest && !current.can_step) || !token) return;
    pendingRequest ||= requestId();
    try { sessionStorage.setItem(storageKey, pendingRequest); }
    catch { storageAvailable = false; message = "浏览器会话存储不可用，未提交实验。"; failed = true; draw(); return; }
    submitting = true; message = "正在提交本地实验…"; failed = false; draw();
    try {
      const response = await requestJson("/api/local-demo/step", { method:"POST", headers:{"Content-Type":"application/json", "X-Research-CSRF":token}, body:JSON.stringify({request_id:pendingRequest}) }) as {ok?:boolean; result?:unknown};
      if (response.ok !== true) throw new Error("未能确认提交结果。");
      checked(response.result, snapshot);
      clearPending();
      message = "请求已接收，正在读取执行状态。";
    } catch {
      message = "提交结果未确认。刷新状态，或使用同一请求编号重试。"; failed = true;
    } finally {
      submitting = false;
      if (alive()) { draw(); await refresh(); }
    }
  }
  void refresh();
}
