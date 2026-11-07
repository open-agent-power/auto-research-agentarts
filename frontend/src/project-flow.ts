/** Real saved project objects on the existing X6 research surface. */
import { el } from "./dom";
import { C01Board, type C01Card } from "./c01-app";

type Obj = Record<string, unknown>;
const object = (value: unknown): Obj => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const objects = (value: unknown): Obj[] => Array.isArray(value) ? value.map(object) : [];
const text = (value: unknown, fallback = "未记录"): string => typeof value === "string" && value.length ? value : fallback;
const methodNames: Record<string, string> = {
  "data.tabular-quality-audit": "表格质量与分组核对", "data.grouped-quality-profile": "分组质量画像",
  "data.numeric-association": "数值关联分析",
  "materials.saved-steel-audit": "保存钢材模型复核", "software.source-integrity-check": "文件完整性检查",
  "p02.saved-oof-residuals": "保存预测残差诊断", "research.source-selection": "读取来源选区", "p02.source-mapping-check": "读取来源选区",
};
const states: Record<string, string> = { completed: "已完成", failed: "失败，记录保留", unknown: "未知，待核对", running: "执行中", waiting: "等待资料", active: "可继续", consumed: "已消费", external_wait: "本次等待" };

export function createProjectFlow(announce: (message: string, error?: boolean) => void): {
  element: HTMLElement; update(project: Obj): void; activate(): void;
} {
  const section = el("section", "project-flow-surface"), toolbar = el("div", "project-flow-toolbar glass");
  const viewport = el("div", "project-flow-viewport"), canvas = el("div", "project-flow-canvas"), detail = el("aside", "project-flow-detail content-section"); detail.hidden = true;
  viewport.append(canvas);
  canvas.setAttribute("aria-label", "当前项目真实研究记录画布；可拖动、缩放，Enter阅读节点");
  const zoom = el("span", "detail-note", "100%");
  let project: Obj = {}, board: C01Board | null = null, identity = "", mountedIdentity = "";
  let cards: C01Card[] = [], values = new Map<string, Obj>();
  const action = (label: string, callback: () => void): void => { const button = el("button", "quiet-button", label); button.type = "button"; button.addEventListener("click", callback); toolbar.append(button); };
  action("放大", () => board?.zoom(.1)); action("缩小", () => board?.zoom(-.1)); action("适应全图", () => board?.fit());
  action("问题与来源", () => board?.focusStage("evidence")); action("执行记录", () => board?.focusStage("experiments")); action("反馈与待办", () => board?.focusStage("conclusions"));
  action("保存布局", () => board?.save()); action("恢复布局", () => board?.restore()); action("重置布局", () => board?.reset()); toolbar.append(zoom);
  section.append(toolbar, viewport, detail,
    el("p", "project-flow-legend", "实线：原记录中的引用或前序绑定；虚线：项目包含的记录。分组和排列不表示因果或推断的执行顺序。拖动节点、Ctrl/⌘+滚轮缩放；布局仅存本浏览器。"));
  function open(id: string): void {
    const card = cards.find(item => item.id === id), value = values.get(id); if (!card || !value) return;
    const close = el("button", "quiet-button", "关闭记录"); close.type = "button";
    close.addEventListener("click", () => { detail.hidden = true; board?.focusElement(id); });
    const raw = el("details", "local-advanced"); raw.append(el("summary", "", "完整原记录与身份"), el("pre", "project-source-text", JSON.stringify(value, null, 2)));
    detail.replaceChildren(close, el("h3", "", card.title), el("p", "", card.body), raw);
    if (value.artifact && /^[A-Za-z0-9_.:-]+$/.test(text(value.id, ""))) { const link = el("a", "text-button", "下载完整行动 JSON ↓"); link.href = "/api/project/artifact/" + text(value.id); detail.append(link); }
    detail.hidden = false; close.focus({ preventScroll: true }); board?.select(id);
  }
  detail.addEventListener("keydown", event => { if (event.key === "Escape") { detail.hidden = true; canvas.focus({ preventScroll: true }); } });
  canvas.tabIndex = -1;
  function update(nextProject: Obj): void {
    project = nextProject; identity = text(project.id, "") + ":" + text(project.snapshot_ref, "");
    if (identity === mountedIdentity) return;
    board?.dispose(); board = null; mountedIdentity = ""; detail.hidden = true; canvas.replaceChildren();
    cards = []; values = new Map();
    if (!project.id) { canvas.append(el("p", "empty-state", "先在项目总览创建或选择课题，再查看真实研究流程。")); return; }
    const add = (id: string, title: string, kind: string, phase: C01Card["phase"], value: Obj, body: string, refs: string[] = []): void => {
      values.set(id, value); cards.push({ id, title, kind, phase, body: body.slice(0, 240), tag: states[text(value.status)] ?? text(value.status, "保存记录"), details: [], refs });
    };
    const root = "project-" + text(project.id);
    add(root, text(project.goal), "研究课题", "evidence", project, "当前项目的真实目标、来源范围与累计用量。" + (states[text(project.research_status)] ?? text(project.research_status)));
    const actions = [...objects(project.actions), ...objects(project.evidence_actions)];
    for (const receipt of objects(project.registered_evidence)) {
      const id = "receipt-" + text(receipt.receipt_snapshot_sha256);
      add(id, "已登记资料包 " + String(receipt.ordinal ?? ""), "来源原件", "evidence", receipt,
        `${String(receipt.source_count ?? "?")}份原件、${String(receipt.selection_count ?? "?")}个选区；${receipt.read_status === "unread" ? "尚未读取" : receipt.read_status === "completed" ? "读取完成" : "读取状态见原记录"}。登记不表示科学确认。`);
    }
    for (const record of objects(object(project.selection_history).records)) {
      const child = object(record.child), refs: string[] = [];
      add("parent-" + text(record.request_id), record.decision_kind === "external_wait" ? "已保存的本次等待" : "已提交的方法选择", "选择父请求", "evidence", record, text(record.rationale), refs);
      if (child.id) refs.push(text(child.id));
    }
    for (const action of actions) {
      const parameters = object(object(action.method_instance).parameters), refs: string[] = [];
      if (parameters.based_on_action_id) refs.push(text(parameters.based_on_action_id));
      if (action.receipt_snapshot_sha256) refs.push("receipt-" + text(action.receipt_snapshot_sha256));
      for (const record of objects(object(project.selection_history).records)) if (object(record.child).id === action.id) refs.push("parent-" + text(record.request_id));
      add(text(action.id), methodNames[text(action.command)] ?? text(action.command), "实际行动", "experiments", action,
        `${states[text(action.status)] ?? text(action.status)}；${objects(action.observations).length}条原观察。${text(object(action.failure).message, "完整结果及失败记录可展开核对。")}`, refs);
      if (action.next_decision) add("feedback-" + text(action.id), "工具反馈与下一决定", "保存反馈", "conclusions", object(action.next_decision), text(object(action.next_decision).reason), [text(action.id)]);
    }
    const next = object(project.next_decision), task = object(next.next_action);
    const refs = typeof next.based_on_action_id === "string" ? [next.based_on_action_id] : [];
    add("next-" + text(project.id), "当前待办 · 尚未执行", "下一任务", "conclusions", next,
      text(next.reason, methodNames[text(task.method_id)] ?? "等待补充实际资料与条件。"), refs);
    // A selection contains its child identity; only the child draws the parent binding.
    for (const card of cards.filter(item => item.id.startsWith("parent-"))) card.refs = [];
  }
  function activate(): void {
    if (!project.id || section.closest("[hidden]")) return;
    requestAnimationFrame(() => {
      if (section.closest("[hidden]")) return;
      if (!board) {
        try {
          board = new C01Board(canvas, { case_id: text(project.id) }, cards, text(project.snapshot_ref), "active-project-flow", {
            open, message: announce, change: (scale, dirty) => { zoom.textContent = Math.round(scale * 100) + "%" + (dirty ? " · 布局未保存" : ""); },
          }, { groupLabels: { evidence: "问题与来源", experiments: "实际行动", conclusions: "反馈与待办" }, minScale: .25 });
          mountedIdentity = identity;
          for (const edge of board.graph.getEdges()) edge.setData({ relation: "saved_reference" });
          const root = "project-" + text(project.id);
          for (const card of cards) if (card.id !== root) board.graph.addEdge({ source: root, target: card.id, zIndex: 0,
            connector: { name: "rounded", args: { radius: 10 } }, attrs: { line: { stroke: "#9eaaa2", strokeWidth: 1, strokeDasharray: "4 5", targetMarker: null } }, data: { relation: "project_contains" } });
        } catch { canvas.replaceChildren(el("p", "notice", "画布暂未载入。实验中心、知识空间和原记录仍可阅读；请只读刷新后重试。")); }
      } else board.graph.resize(canvas.clientWidth, canvas.clientHeight);
    });
  }
  return { element: section, update, activate };
}
