/** Fixed saved review capsule. Only a deliberate click fetches file bytes. */
import { el } from "./dom";
const metadataPath = "/api/local-workbench/study-capsule";
const filePath = "/api/local-workbench/study-capsule.zip";
const filename = "study-review-capsule.zip";
const expectedBytes = 4671421;
const expectedSha = "3c12efc995a4a4e4e61763150b1d5de818755dbbdf6e892c15d43c9c96a0c598";
type Obj = Record<string, unknown>;
const asObject = (value: unknown): Obj => value && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};

export function createSavedCapsule(): HTMLElement {
  const section = el("section", "content-section saved-study-section"), status = el("p", "detail-note", "正在核对原证据包…"), actions = el("div", "local-actions");
  status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
  const download = el("button", "action-button primary", "下载原研究证据包"), retry = el("button", "quiet-button", "重新核对证据包");
  download.type = retry.type = "button"; download.disabled = true; retry.disabled = true;
  actions.append(download, retry);
  const identity = el("details"); identity.append(el("summary", "", "文件校验信息"), el("p", "", "SHA-256：" + expectedSha));
  section.append(el("h2", "section-title", "原研究证据包"), el("p", "", "已保存的独立研究代码和审阅证据，4,671,421 字节（约 4.46 MiB）。原研究源码 62f09ed、文档 93bb5d9；不包含完整运行环境或全部历史原件。"),
    el("p", "detail-note", "这是原研究的审阅包，不是当前产品报告；复制包、声明或更换 ID、目录都不重置原研究额度。校验哈希不代表来源认证或新的科学验证。"), status, actions, identity);
  let generation = 0, available = false, busy = false;
  const control = (): void => { download.disabled = !available || busy; retry.disabled = busy; };
  async function check(): Promise<void> {
    const token = ++generation; available = false; busy = true; status.textContent = "正在核对原证据包…"; control();
    try {
      const response = await fetch(metadataPath, { cache: "no-store" });
      if (!response.ok) throw Error("本地服务未能核对证据包（HTTP " + response.status + "）。");
      const value = asObject(await response.json());
      if (!section.isConnected || token !== generation) return;
      const exact = value.schema_version === "saved-study-capsule-v1" && value.expected_bytes === expectedBytes && value.expected_sha256 === expectedSha && value.filename === filename;
      if (!exact) throw Error("证据包身份无法确认。");
      if (value.status !== "available") {
        const states: Record<string, string> = { unavailable: "原证据包不可用", unknown: "原证据包状态未知", integrity_error: "原证据包完整性核对失败" };
        status.textContent = (states[String(value.status)] || "原证据包状态无法确认") + (typeof value.reason === "string" ? "：" + value.reason : "。"); return;
      }
      available = true; status.textContent = "已核对原文件；点击后才下载。";
    } catch (error) {
      if (section.isConnected && token === generation) status.textContent = error instanceof Error ? error.message : "原证据包暂不可用。";
    } finally { if (token === generation) { busy = false; control(); } }
  }
  retry.addEventListener("click", () => { void check(); });
  download.addEventListener("click", () => { void (async () => {
    if (!available || busy) return;
    busy = true; control(); status.textContent = "正在读取并校验证据包…";
    try {
      const response = await fetch(filePath, { cache: "no-store" });
      if (!response.ok) {
        const error = asObject(await response.json().catch(() => ({})));
        throw Error(typeof error.reason === "string" ? error.reason : "原证据包无法下载（HTTP " + response.status + "）。");
      }
      if ((response.headers.get("content-type") || "").split(";")[0].trim().toLowerCase() !== "application/zip"
          || response.headers.get("content-length") !== String(expectedBytes)) throw Error("证据包响应身份无法确认。");
      const raw = await response.arrayBuffer();
      if (raw.byteLength !== expectedBytes || !globalThis.crypto?.subtle) throw Error("证据包长度或校验能力无法确认。");
      const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", raw)), byte => byte.toString(16).padStart(2, "0")).join("");
      if (hash !== expectedSha) throw Error("下载内容与原证据包的 SHA-256 不一致。");
      if (!section.isConnected) return;
      const url = URL.createObjectURL(new Blob([raw], { type: "application/zip" })), link = el("a");
      link.href = url; link.download = filename; link.hidden = true; document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30000); status.textContent = "文件已交给浏览器下载；保存位置由浏览器决定。";
    } catch (error) { available = false; if (section.isConnected) status.textContent = error instanceof Error ? error.message : "下载未完成，请重新核对。"; }
    finally { busy = false; control(); }
  })(); });
  // Wait until draw() has inserted the section; never fetch the ZIP here.
  queueMicrotask(() => { if (section.isConnected) void check(); });
  return section;
}
