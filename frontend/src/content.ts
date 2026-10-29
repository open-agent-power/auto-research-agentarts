import type { Claim, Project, ResearchObject, SectionName, Source, Trial } from "./types";
import { date, el, field, heading, numeric, paragraph, safeUrl, text } from "./dom";
import { kindLabels, sectionObjects } from "./model";

export interface ContentContext {
  project: Project;
  objects: ResearchObject[];
  find: (rawId: string) => ResearchObject | undefined;
  open: (id: string) => void;
  download: (format: "pdf" | "reproduction") => void;
  draft: () => string;
  setDraft: (value: string) => void;
  save: (value: string) => Promise<void>;
  layout: { save: () => void; restore: () => void; reset: () => void };
}
export function badge(status: string, label?: string): HTMLElement {
  const labels: Record<string, string> = { accepted: "当次采用", rejected: "未晋升", failed: "失败", observed: "记录事实", limitation: "适用边界", planned: "待人工执行", saved_pending_execution: "待人工执行", running: "快照记录：在途" };
  return el("span", "status-badge " + (Object.hasOwn(labels, status) ? status : ""), label || labels[status] || "状态待核对");
}
function refs(container: HTMLElement, ids: string[], context: ContentContext): void {
  if (!ids.length) return;
  const list = el("div", "detail-ref-list");
  ids.forEach((id) => {
    const object = context.find(id);
    const item = object ? el("button", "ref-button", id.length > 20 ? id.slice(0, 12) + "…" : id) : el("code", "ref-button", id);
    item.title = id;
    if (object) item.addEventListener("click", () => context.open(object.id));
    list.append(item);
  });
  container.append(list);
}
export function figures(container: HTMLElement, context: ContentContext): void {
  const allow = ["/api/figures/validation.svg", "/api/figures/prediction.svg"];
  context.project.figures.forEach((figure) => {
    const block = el("figure", "figure-block");
    block.append(el("h4", "", figure.title));
    if (allow.includes(figure.url)) {
      const image = el("img"); image.src = figure.url; image.alt = figure.title; image.loading = "lazy";
      image.addEventListener("error", () => image.replaceWith(el("p", "figure-error", "图表未能载入，请刷新或查看复现附件。")), { once: true });
      block.append(image);
    } else block.append(el("p", "figure-error", "当前没有可用的本地图表。"));
    block.append(el("figcaption", "", figure.caption)); container.append(block);
  });
}
function report(container: HTMLElement, context: ContentContext): void {
  const article = el("article", "paper-text");
  article.append(el("h3", "", context.project.report.title));
  context.project.report.sections.forEach((section) => {
    if (typeof section === "string") { paragraph(article, section); return; }
    article.append(el("h4", "", section.heading));
    section.paragraphs.forEach((value) => paragraph(article, value));
    refs(article, section.claim_ids || [], context);
  });
  container.append(article);
}
let formSequence = 0;
export function questionForm(container: HTMLElement, context: ContentContext): void {
  paragraph(container, "问题保存到本地，待人工执行；不会调用模型或启动训练。", "detail-note");
  const form = el("form", "question-form");
  const id = "followup-" + (++formSequence);
  const label = el("label", "", "问题内容"); label.htmlFor = id;
  const input = el("textarea"); input.id = id; input.rows = 4; input.value = context.draft();
  input.placeholder = "例如：缺少加工条件是否限制了现有结论的解释？"; input.required = true;
  const meta = el("div", "form-meta");
  const counter = el("span", "", Array.from(input.value).length + " / 1500 字");
  meta.append(counter, el("span", "", "不含隐私或凭据"));
  const submit = el("button", "action-button primary", "保存后续研究问题"); submit.type = "submit";
  const feedback = el("p", "form-feedback"); feedback.setAttribute("role", "status"); feedback.setAttribute("aria-live", "polite");
  input.setAttribute("aria-describedby", id + "-help"); feedback.id = id + "-help";
  const saved = el("div");
  const renderSaved = () => {
    saved.replaceChildren();
    heading(saved, "已保存 · " + context.project.next_questions.length + " 条");
    if (!context.project.next_questions.length) paragraph(saved, "暂无待处理问题。", "empty-state");
    [...context.project.next_questions].reverse().forEach((question) => {
      const row = el("div", "saved-question");
      paragraph(row, question.text);
      row.append(badge(question.status), el("small", "", date(question.created_at)));
      saved.append(row);
    });
  };
  const update = () => {
    const length = Array.from(input.value).length;
    counter.textContent = length + " / 1500 字";
    submit.disabled = !context.project.csrf_token || !input.value.trim() || length > 1500;
  };
  input.addEventListener("input", () => { context.setDraft(input.value); update(); });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submit.disabled || input.disabled) return;
    const value = input.value.trim();
    submit.disabled = true; input.disabled = true; submit.textContent = "正在保存…"; form.setAttribute("aria-busy", "true");
    feedback.classList.remove("error"); feedback.textContent = "正在保存，不会执行研究。";
    try {
      await context.save(value);
      input.value = ""; context.setDraft(""); renderSaved();
      feedback.textContent = "已保存为待人工执行，未启动模型或试验。";
    } catch (error) {
      feedback.classList.add("error");
      feedback.textContent = error instanceof TypeError || (error instanceof DOMException && error.name === "AbortError") ? "未确认保存结果，请刷新查看列表后再决定是否重试。" : error instanceof Error ? error.message : "保存未完成，请重试。";
    } finally {
      input.disabled = false; submit.textContent = "保存后续研究问题"; form.setAttribute("aria-busy", "false"); update();
    }
  });
  form.append(label, input, meta, submit, feedback); container.append(form, saved); update(); renderSaved();
  if (!context.project.csrf_token) feedback.textContent = "保存暂不可用，请刷新当前页面后重试。";
}
export function renderDetails(container: HTMLElement, object: ResearchObject, context: ContentContext): void {
  container.replaceChildren();
  if (object.kind === "question") {
    heading(container, "当前研究问题"); paragraph(container, context.project.question);
    heading(container, "原始目标"); paragraph(container, context.project.source_goal);
    const record = el("dl", "detail-dl"); const data = context.project.dataset;
    field(record, "数据任务", text(data.dataset_id)); field(record, "反馈来源", context.project.labels.decision_origin);
    field(record, "研究状态", context.project.labels.scientific_status); field(record, "平台状态", context.project.labels.cloud);
    field(record, "快照时间", date(context.project.snapshot.created_at)); field(record, "快照 SHA", context.project.snapshot.sha256, true);
    field(record, "数据 SHA", text(data.data_sha256 || data.raw_sha256), true);
    const splits = data.split_counts as Record<string, unknown> | undefined;
    field(record, "固定划分", splits ? "训练 " + text(splits.train) + " / 验证 " + text(splits.validation) + " / 测试 " + text(splits.test) : "未提供");
    field(record, "输入特征", Array.isArray(data.feature_names) ? data.feature_names.map((value) => text(value)).join("、") : "未提供");
    container.append(record);
    paragraph(container, "本页为已有证据快照。布局不改变研究结果、父关系和引用。", "detail-note");
  } else if (object.kind === "source") {
    const source = object.data as Source;
    paragraph(container, "当前快照仅有摘记和来源信息，原文请访问原始来源。", "detail-note source-record-boundary");
    heading(container, "来源与使用范围"); paragraph(container, source.description);
    const url = safeUrl(source.url);
    if (url) { const link = el("a", "source-link", "打开原始来源 ↗"); link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer"; container.append(link); paragraph(container, url, "source-url"); }
    else paragraph(container, "链接未提供或不符合 HTTPS 要求。", "detail-note");
    const record = el("dl", "detail-dl"); field(record, "来源编号", source.id);
    container.append(record);
    paragraph(container, "版本、许可和使用范围见复现附件中的来源记录。", "detail-note");
  } else if (object.kind === "trial") {
    const trial = object.data as Trial; const metrics = trial.metrics || {};
    container.append(badge(trial.status));
    if (trial.id === context.project.metrics.best_trial_id) container.append(el("span", "status-badge", "当前保留模型"));
    const record = el("dl", "detail-dl");
    heading(container, "配方与真实指标");
    field(record, "多项式阶数", String(trial.candidate.degree)); field(record, "正则系数 α", numeric(trial.candidate.alpha));
    field(record, "训练 MSE", numeric(metrics.training_mse)); field(record, "验证 MSE", numeric(metrics.validation_mse));
    field(record, "特征数量", numeric(metrics.num_features)); field(record, "训练用时", numeric(metrics.training_seconds) + " 秒");
    container.append(record);
    heading(container, "原提案假设"); paragraph(container, trial.proposal?.hypothesis || trial.reason || "原始记录未提供。");
    if (trial.proposal?.expected_effect) { heading(container, "待检验的预期"); paragraph(container, trial.proposal.expected_effect); }
    heading(container, "采用／拒绝依据"); paragraph(container, trial.decision_reason || "原始记录未提供判定理由。");
    paragraph(container, "预期效果未经确认。当前结果只适用于固定数据和评价规则。", "detail-note");
    heading(container, "实际引用"); refs(container, object.references, context);
    const audit = el("dl", "detail-dl"); field(audit, "试验 ID", trial.id, true); field(audit, "父试验", trial.parent_trial_id || "无 / 未记录", true);
    field(audit, "模型 SHA", trial.model_sha256 || "未记录", true); field(audit, "配方 SHA", trial.recipe_sha256 || "未记录", true);
    container.append(audit);
    if (trial.error) paragraph(container, "失败记录：" + text(trial.error.code));
  } else if (object.kind === "claim") {
    const claim = object.data as Claim; container.append(badge(claim.status)); heading(container, "原始主张"); paragraph(container, claim.statement);
    heading(container, "引用的证据记录"); refs(container, claim.evidence_ids, context);
    paragraph(container, "连线表示原始引用；分组和位置不代表支持、反驳或因果。", "detail-note");
  } else if (object.kind === "paper") {
    paragraph(container, "由冻结证据生成的论文式报告；不是同行评审、临床验证或科研发现认证。", "detail-note");
    const controls = el("div", "detail-ref-list");
    for (const [title, format] of [["下载 PDF", "pdf"], ["下载复现附件", "reproduction"]] as const) {
      const button = el("button", "action-button", title); button.addEventListener("click", () => context.download(format)); controls.append(button);
    }
    container.append(controls); heading(container, "实际结果图"); figures(container, context); heading(container, "报告全文"); report(container, context);
  } else questionForm(container, context);
}
export function renderReading(container: HTMLElement, section: SectionName, context: ContentContext): void {
  container.replaceChildren();
  const selected = sectionObjects(context.objects, section);
  if (section === "paper" || section === "questions") {
    const object = selected[0]; if (object) renderDetails(container, object, context); return;
  }
  if (section === "overview") {
    const summary = el("section", "reading-section");
    summary.append(el("h2", "", "当前研究问题")); paragraph(summary, context.project.question);
    const stats = el("dl", "summary-stats");
    for (const [title, value] of [["已有试验", numeric(context.project.metrics.trials)], ["保留模型验证 MSE", numeric(context.project.metrics.best_validation_mse)], ["终测 MSE", numeric(context.project.metrics.test_mse)]] as const) {
      const item = el("div"); item.append(el("dt", "", title), el("dd", "", value)); stats.append(item);
    }
    summary.append(stats); paragraph(summary, context.project.labels.decision_origin + "。模型及平台接入暂缓；未记录终测时不填入测试成绩。", "detail-note"); container.append(summary);
  }
  for (const category of ["source", "trial", "claim"] as const) {
    const objects = selected.filter((object) => object.kind === category);
    if (!objects.length) continue;
    const block = el("section", "reading-section");
    if (section === "overview") block.append(el("h2", "", kindLabels[category]));
    objects.forEach((object) => {
      const button = el("button", "reading-row");
      const title = el("div", "reading-row-title"); title.append(el("span", "", object.title), badge(object.status, object.tag));
      button.append(title, el("p", "reading-row-summary", object.kind === "trial" ? object.summary + " · 验证 MSE " + numeric((object.data as Trial).metrics?.validation_mse) : object.kind === "claim" ? (object.data as Claim).statement : object.summary));
      button.append(el("p", "reading-row-meta", object.rawId.length > 20 ? object.rawId.slice(0, 12) + "… · 查看完整记录 ↗" : object.rawId + " · 查看完整记录 ↗"));
      button.addEventListener("click", () => context.open(object.id)); block.append(button);
    });
    container.append(block);
  }
  if (!container.children.length) paragraph(container, "当前快照未提供这类研究对象。", "empty-state");
  if (section === "overview") {
    const paperBlock = el("section", "reading-section"); paperBlock.append(el("h2", "", "论文式报告与实际图表")); figures(paperBlock, context); report(paperBlock, context); container.append(paperBlock);
    const questions = el("section", "reading-section"); questions.append(el("h2", "", "后续研究问题")); questionForm(questions, context); container.append(questions);
  }
}

