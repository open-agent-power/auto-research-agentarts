import { Graph, Shape, Node } from "@antv/x6";
import type { Layout, Project, ResearchObject, Viewport } from "./types";
import { el, numeric } from "./dom";
import { kindLabels } from "./model";

const GROUPS = {
  evidence: { id: "group-evidence", title: "01  依据与研究线索", x: 36, color: "sage", width: 316 },
  experiments: { id: "group-experiments", title: "02  假设与真实试验", x: 394, color: "sand", width: 350 },
  conclusions: { id: "group-conclusions", title: "03  判断与研究成果", x: 794, color: "lavender", width: 350 },
};
const sizes = { question: { width: 350, height: 176 }, source: { width: 278, height: 175 }, trial: { width: 312, height: 202 }, claim: { width: 312, height: 151 }, paper: { width: 312, height: 158 }, questions: { width: 278, height: 160 } };
type Events = { select: (id: string) => void; change: (zoom: number, dirty: boolean) => void; message: (message: string, error?: boolean) => void; blank: () => void };
function isRecord(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === "object" && !Array.isArray(value); }
function finite(value: unknown, limit = 100000): value is number { return typeof value === "number" && Number.isFinite(value) && Math.abs(value) <= limit; }
function hasOnly(value: Record<string, unknown>, keys: string[]): boolean { return Object.keys(value).every((key) => keys.includes(key)); }

export class ResearchBoard {
  readonly graph: Graph;
  private project: Project;
  private objects: ResearchObject[];
  private elements = new Map<string, HTMLElement>();
  private defaults!: Layout;
  private ids = new Set<string>();
  private applying = true;
  private selected = "";
  readonly storageKey: string;

  constructor(container: HTMLElement, project: Project, objects: ResearchObject[], private events: Events) {
    this.project = project; this.objects = objects;
    this.storageKey = "autoresearch-layout:v1:" + encodeURIComponent(project.id) + ":" + project.snapshot.sha256;
    Shape.HTML.register({
      shape: "research-object", effect: ["data"], html: (cell) => this.card(cell as Node),
    });
    this.graph = new Graph({
      container, autoResize: true,
      grid: { size: 24, visible: true, type: "dot", args: { color: "#cfd7d6", thickness: 1.1 } },
      background: { color: "#f4f5f7" },
      scaling: { min: .35, max: 1.6 },
      panning: { enabled: true, eventTypes: ["leftMouseDown", "mouseWheel", "mouseWheelDown"] },
      mousewheel: { enabled: true, modifiers: ["ctrl", "meta"], zoomAtMousePosition: true, minScale: .35, maxScale: 1.6, factor: 1.12 },
      embedding: false,
      interacting: { nodeMovable: true, edgeMovable: false, edgeLabelMovable: false, magnetConnectable: false },
      connecting: { allowBlank: false, allowLoop: false, allowEdge: false, allowNode: false },
    });
    this.addNodes(); this.addEdges();
    this.graph.zoomTo(.86);
    this.graph.translate(window.innerWidth <= 720 ? 25 : (window.innerWidth <= 1150 ? 250 : 280), 110);
    this.defaults = this.capture();
    this.graph.on("node:click", ({ node }) => { if (this.objects.some((object) => object.id === node.id)) this.events.select(node.id); });
    this.graph.on("blank:click", () => this.events.blank());
    this.graph.on("node:moved", () => this.changed());
    this.graph.on("node:change:position", () => this.changed());
    this.graph.on("scale", () => this.changed());
    this.graph.on("translate", () => this.changed());
    this.applying = false;
    this.events.change(this.graph.zoom(), false);
    this.restore(false);
  }

  private card(node: Node): HTMLElement {
    const object = node.getData<ResearchObject>();
    const card = el("div", "research-card" + (this.selected === object.id ? " selected" : ""));
    card.dataset.kind = object.kind; card.dataset.objectId = object.id; card.tabIndex = 0;
    card.setAttribute("role", "button"); card.setAttribute("aria-label", kindLabels[object.kind] + "：" + object.title + "，Enter查看详情");
    card.setAttribute("aria-pressed", String(this.selected === object.id));
    const meta = el("div", "node-meta");
    meta.append(el("span", "node-category", kindLabels[object.kind]), el("span", "node-tag " + (["rejected", "limitation"].includes(object.status) ? object.status : ""), object.tag));
    card.append(meta, el("div", "node-title", object.title));
    if (object.kind === "trial") {
      const metric = el("div", "node-metric");
      const trial = object.data as Project["trials"][number];
      metric.append(document.createTextNode(numeric(trial.metrics?.validation_mse)), el("small", "", "验证 MSE"));
      card.append(metric);
    }
    card.append(el("p", "node-summary", object.summary));
    const footer = el("div", "node-footer");
    const label = object.kind === "trial" && object.rawId === this.project.metrics.best_trial_id ? "当前保留模型" : (object.rawId.length > 22 ? object.rawId.slice(0, 10) + "…" : object.rawId);
    footer.append(el("span", "", label), el("span", "node-arrow", "↗")); card.append(footer);
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.stopPropagation(); this.events.select(object.id); }
      const movement: Record<string, [number, number]> = { ArrowLeft: [-24, 0], ArrowRight: [24, 0], ArrowUp: [0, -24], ArrowDown: [0, 24] };
      if (Object.hasOwn(movement, event.key)) {
        event.preventDefault(); event.stopPropagation();
        const position = node.position(); const delta = movement[event.key];
        node.position(position.x + delta[0], position.y + delta[1]); this.changed();
      }
    });
    this.elements.set(object.id, card);
    return card;
  }

  private addNodes(): void {
    const groupNodes = new Map<string, Node>();
    for (const [key, group] of Object.entries(GROUPS)) {
      const members = this.objects.filter((object) => object.group === key);
      const height = 76 + members.reduce((sum, object) => sum + sizes[object.kind].height + 18, 0);
      const node = this.graph.addNode({
        id: group.id, shape: "rect", x: group.x, y: 252, width: group.width, height: Math.max(190, height), zIndex: 0,
        attrs: {
          body: { fill: "var(--ar-group-" + group.color + "-surface)", stroke: "var(--ar-group-" + group.color + "-border)", strokeWidth: 1, rx: 18, ry: 18 },
          label: { text: group.title, fill: "var(--ar-group-" + group.color + "-ink)", fontSize: 12, fontWeight: 600, fontFamily: "Segoe UI, Microsoft YaHei, sans-serif", refX: 20, refY: 29, textAnchor: "start", textVerticalAnchor: "middle" },
        },
      });
      groupNodes.set(key, node); this.ids.add(group.id);
    }
    const offsets: Record<string, number> = { evidence: 309, experiments: 309, conclusions: 309 };
    // Place the report first in the conclusions column; all claims keep their original IDs.
    const ordered = [...this.objects].sort((a, b) => (a.kind === "paper" ? -1 : 0) - (b.kind === "paper" ? -1 : 0));
    ordered.forEach((object) => {
      const size = sizes[object.kind];
      const group = object.group ? GROUPS[object.group] : null;
      const x = group ? group.x + 19 : 394;
      const y = object.group ? offsets[object.group] : 35;
      const node = this.graph.addNode({ id: object.id, shape: "research-object", x, y, ...size, zIndex: 3, data: object });
      this.ids.add(object.id);
      if (object.group) {
        groupNodes.get(object.group)?.addChild(node);
        offsets[object.group] += size.height + 18;
      }
    });
  }

  private addEdges(): void {
    const raw = new Map(this.objects.map((object) => [object.rawId, object]));
    const seen = new Set<string>();
    for (const object of this.objects) {
      for (const id of object.references) {
        const source = raw.get(id);
        if (!source || source.id === object.id) continue;
        const pair = source.id + "->" + object.id;
        if (seen.has(pair)) continue;
        seen.add(pair);
        this.graph.addEdge({
          source: { cell: source.id }, target: { cell: object.id }, zIndex: 1,
          router: { name: "orth" }, connector: { name: "rounded", args: { radius: 10 } },
          attrs: { line: { stroke: "#a8b8b0", strokeWidth: 1.15, strokeOpacity: .72, targetMarker: { name: "classic", size: 5 } } },
          data: { relation: "recorded_reference", source_id: source.rawId, target_id: object.rawId },
        });
      }
    }
  }

  private changed(): void { if (!this.applying) this.events.change(this.graph.zoom(), true); }
  select(id: string): void {
    this.selected = id;
    for (const [key, element] of this.elements) {
      element.classList.toggle("selected", key === id); element.setAttribute("aria-pressed", String(key === id));
    }
  }
  focus(id: string): void {
    const cell = this.graph.getCellById(id);
    if (!cell || !cell.isNode()) return;
    const box = cell.getBBox(); const width = this.graph.container.clientWidth; const height = this.graph.container.clientHeight;
    const mobile = width <= 720; const left = mobile ? 18 : (width <= 1150 ? 245 : 275);
    const right = !mobile && document.body.classList.contains("has-inspector") ? 455 : 25;
    const top = mobile ? 260 : 145; const bottom = 105;
    const zoom = Math.max(this.graph.zoom(), .75);
    this.graph.zoomTo(zoom);
    this.graph.translate((left + width - right) / 2 - (box.x + box.width / 2) * zoom, (top + height - bottom) / 2 - (box.y + box.height / 2) * zoom);
  }
  focusGroup(name: string): void {
    const group = (GROUPS as Record<string, { id: string }>)[name]; if (group) this.focus(group.id);
  }
  zoom(delta: number): void { this.graph.zoomTo(Math.max(.35, Math.min(1.6, this.graph.zoom() + delta))); }
  zoomReset(): void { this.graph.zoomTo(1); }
  viewport(): Viewport { const value = this.graph.translate(); return { zoom: this.graph.zoom(), x: value.tx, y: value.ty }; }
  restoreViewport(value: Viewport): void { this.graph.zoomTo(value.zoom); this.graph.translate(value.x, value.y); }
  fit(): void {
    const width = this.graph.container.clientWidth;
    this.graph.zoomToFit({ padding: { top: width <= 720 ? 260 : 150, bottom: 110, left: width <= 720 ? 20 : (width <= 1150 ? 245 : 280), right: width > 720 && document.body.classList.contains("has-inspector") ? 455 : 35 }, maxScale: 1, minScale: .35, useCellGeometry: true });
  }
  capture(): Layout {
    const positions: Layout["positions"] = {};
    for (const node of this.graph.getNodes()) positions[node.id] = { ...node.position() };
    const translation = this.graph.translate();
    return { schema_version: 1, project_id: this.project.id, snapshot_sha256: this.project.snapshot.sha256, positions, viewport: { zoom: this.graph.zoom(), x: translation.tx, y: translation.ty } };
  }
  private validate(value: unknown): Layout {
    if (!isRecord(value) || !hasOnly(value, ["schema_version", "project_id", "snapshot_sha256", "positions", "viewport"]) || value.schema_version !== 1 || value.project_id !== this.project.id || value.snapshot_sha256 !== this.project.snapshot.sha256 || !isRecord(value.positions) || !isRecord(value.viewport)) throw new Error("布局身份或结构不匹配。");
    const viewport = value.viewport;
    if (!hasOnly(viewport, ["zoom", "x", "y"]) || !finite(viewport.zoom, 2) || viewport.zoom < .35 || viewport.zoom > 1.6 || !finite(viewport.x, 1000000) || !finite(viewport.y, 1000000)) throw new Error("布局视口数据无效。");
    for (const [id, position] of Object.entries(value.positions)) {
      if (!this.ids.has(id) || !isRecord(position) || !hasOnly(position, ["x", "y"]) || !finite(position.x) || !finite(position.y)) throw new Error("布局包含未知对象或无效坐标。");
    }
    return value as unknown as Layout;
  }
  private apply(layout: Layout): void {
    this.applying = true;
    for (const [id, position] of Object.entries(layout.positions)) {
      const node = this.graph.getCellById(id); if (node?.isNode()) node.position(position.x, position.y);
    }
    this.graph.zoomTo(layout.viewport.zoom); this.graph.translate(layout.viewport.x, layout.viewport.y);
    this.applying = false; this.events.change(this.graph.zoom(), false);
  }
  save(): void {
    try { const value = this.validate(this.capture()); localStorage.setItem(this.storageKey, JSON.stringify(value)); this.events.change(this.graph.zoom(), false); this.events.message("布局已保存在本浏览器，不改变研究记录。"); }
    catch { this.events.message("浏览器布局未能保存。查看、问题保存和下载仍可使用。", true); }
  }
  restore(notify = true): void {
    try {
      const saved = localStorage.getItem(this.storageKey);
      if (!saved) { if (notify) this.events.message("本浏览器尚无这个证据版本的布局。"); return; }
      if (saved.length > 262144) throw new Error("oversized layout");
      this.apply(this.validate(JSON.parse(saved)));
      if (notify) this.events.message("已恢复本浏览器保存的布局。");
    } catch { this.events.message("已忽略损坏或不适用的浏览器布局，研究证据仍可查看。", true); }
  }
  reset(): void {
    this.apply(this.defaults);
    try { localStorage.removeItem(this.storageKey); this.events.message("已重置本浏览器布局，原研究证据未改变。"); }
    catch { this.events.message("已恢复初始视图，但无法清除浏览器中的旧布局。", true); }
  }
  updateObjects(objects: ResearchObject[]): void {
    this.objects = objects;
    for (const object of objects) if (object.kind === "questions") {
      const cell = this.graph.getCellById(object.id);
      cell?.setData(object, { overwrite: true });
    }
  }
  dispose(): void { this.graph.dispose(); }
}

