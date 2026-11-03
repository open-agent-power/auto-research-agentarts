export function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", value?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (value !== undefined) node.textContent = value;
  return node;
}
export function $<T extends HTMLElement = HTMLElement>(id: string): T {
  const node = document.getElementById(id);
  if (!node) throw new Error("Missing interface element: " + id);
  return node as T;
}
export function numeric(value: unknown, digits = 6): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "未记录";
  if (value !== 0 && Math.abs(value) < .0001) return value.toExponential(3);
  return new Intl.NumberFormat("zh-CN", { maximumSignificantDigits: digits }).format(value);
}
export function date(value: unknown): string {
  if (typeof value !== "string" && typeof value !== "number") return "时间未提供";
  const time = new Date(typeof value === "number" && value < 1e12 ? value * 1000 : value);
  return Number.isNaN(time.getTime()) ? "时间未提供" : time.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
}
export function text(value: unknown, fallback = "未提供"): string {
  return typeof value === "string" ? value : (typeof value === "number" && Number.isFinite(value) ? String(value) : fallback);
}
export function safeUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  try { const url = new URL(value); return url.protocol === "https:" && !url.username && !url.password ? url.href : null; } catch { return null; }
}
export function field(container: HTMLElement, label: string, value: string, mono = false): void {
  const row = el("div", "detail-field"); row.append(el("dt", "", label), el("dd", mono ? "mono" : "", value)); container.append(row);
}
export function heading(container: HTMLElement, value: string): void { container.append(el("h3", "detail-heading", value)); }
export function paragraph(container: HTMLElement, value: string, cls = ""): void { container.append(el("p", cls, value)); }
