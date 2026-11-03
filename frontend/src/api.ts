import type { Project, Question } from "./types";
export async function requestJson(path: string, options: RequestInit = {}): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(path, { ...options, credentials: "same-origin", cache: "no-store", signal: controller.signal });
    let result: unknown;
    try { result = await response.json(); } catch { throw new Error("本地服务返回的内容无法读取，请刷新后重试。"); }
    if (!response.ok) {
      if (response.status === 403) throw new Error("保存校验已失效或请求被拒绝，请刷新当前页面后重试。");
      const message = result && typeof result === "object" && "error" in result ? (result as { error?: { message?: unknown } }).error?.message : null;
      throw new Error(typeof message === "string" ? message.slice(0, 300) : "本地服务未完成请求。");
    }
    return result;
  } finally { clearTimeout(timer); }
}
export async function loadProject(): Promise<Project> {
  const raw = await requestJson("/api/project");
  if (!raw || typeof raw !== "object") throw new Error("项目证据格式无法确认。");
  const project = raw as Project;
  if (typeof project.id !== "string" || typeof project.title !== "string" || !project.snapshot || typeof project.snapshot.sha256 !== "string") throw new Error("项目缺少必要的身份与快照记录。");
  for (const name of ["sources", "trials", "claims", "figures", "next_questions"] as const) if (!Array.isArray(project[name])) throw new Error("项目证据列表格式无法确认。");
  if (!project.report || !Array.isArray(project.report.sections)) throw new Error("报告结构无法确认。");
  return project;
}
export async function saveQuestion(token: string, value: string): Promise<Question> {
  if (!token) throw new Error("保存暂不可用，请刷新当前页面。");
  const raw = await requestJson("/api/questions", { method: "POST", headers: { "Content-Type": "application/json", "X-Research-CSRF": token }, body: JSON.stringify({ text: value }) });
  const result = raw as { ok?: boolean; question?: Question };
  if (result.ok !== true || !result.question || typeof result.question.id !== "string" || typeof result.question.text !== "string" || result.question.status !== "saved_pending_execution") throw new Error("保存结果无法确认，请刷新问题列表后再重试。");
  return result.question;
}
export async function download(format: "pdf" | "reproduction"): Promise<void> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 60000);
  try {
  const paths = { pdf: "/api/export/paper.pdf", reproduction: "/api/export/reproduction.zip" };
  const response = await fetch(paths[format], { credentials: "same-origin", cache: "no-store", signal: controller.signal });
  const mime = (response.headers.get("content-type") || "").split(";")[0].trim().toLowerCase();
  const allowed = format === "pdf" ? ["application/pdf", "application/octet-stream"] : ["application/zip", "application/x-zip-compressed", "application/octet-stream"];
  if (!response.ok || !allowed.includes(mime)) throw new Error("导出暂不可用，请检查本地服务后重试。");
  const blob = await response.blob();
  if (!blob.size) throw new Error("本地服务返回了空文件。");
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = format === "pdf" ? "研究报告.pdf" : "复现附件.zip"; link.hidden = true;
  document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000);
  } finally { clearTimeout(timer); }
}
