(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const text = (value, fallback = "") => typeof value === "string" ? value : (typeof value === "number" && Number.isFinite(value) ? String(value) : fallback);
  const list = (value) => Array.isArray(value) ? value : [];
  const make = (tag, className, content) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (content !== undefined) element.textContent = text(content);
    return element;
  };
  const evidenceTargets = new Map();
  const figurePaths = ["/api/figures/validation.svg", "/api/figures/prediction.svg"];
  const exportPaths = { pdf: "/api/export/paper.pdf", reproduction: "/api/export/reproduction.zip" };
  let project = null;
  let csrfToken = "";
  let saving = false;
  let downloading = false;
  let sectionObserver = null;

  function finiteNumber(value) {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "未记录";
    if (value !== 0 && value < 0.0001) return value.toExponential(4);
    return new Intl.NumberFormat("zh-CN", { maximumSignificantDigits: 6 }).format(value);
  }

  function count(value, fallback) {
    return Number.isInteger(value) && value >= 0 ? value : fallback;
  }

  function dateText(value) {
    if (value === null || value === undefined || value === "") return "时间未提供";
    const date = new Date(typeof value === "number" && value < 1000000000000 ? value * 1000 : value);
    if (Number.isNaN(date.getTime())) return "时间未提供";
    return date.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
  }

  function httpsLink(value) {
    try {
      const url = new URL(value);
      return url.protocol === "https:" && !url.username && !url.password ? url.href : null;
    } catch (_) {
      return null;
    }
  }

  function feedback(id, message, state = "") {
    const element = byId(id);
    element.textContent = message;
    element.dataset.state = state;
  }

  function definition(container, label, value, className = "") {
    const row = make("div");
    row.append(make("dt", "", label), make("dd", className, value));
    container.append(row);
  }

  function references(ids, prefix = "关联证据") {
    const refs = list(ids);
    if (!refs.length) return null;
    const line = make("div", "evidence-links");
    line.append(make("span", "", prefix + "："));
    refs.forEach((id) => {
      const label = text(id);
      const target = evidenceTargets.get(label);
      const element = make(target ? "a" : "code", "", label || "未标识");
      if (target) element.href = "#" + target;
      line.append(element);
    });
    return line;
  }

  function setNavigationEnabled(enabled) {
    document.querySelectorAll("#chapter-nav a").forEach((link) => {
      link.setAttribute("aria-disabled", String(!enabled));
      if (enabled) link.removeAttribute("tabindex");
      else link.tabIndex = -1;
    });
  }

  function updateControls() {
    const ready = project !== null;
    const input = byId("next-question");
    input.disabled = !ready || !csrfToken || saving;
    byId("save-question").disabled = input.disabled || !input.value.trim();
    byId("save-question").textContent = saving ? "正在保存…" : "保存后续研究问题";
    byId("question-form").setAttribute("aria-busy", String(saving));
    Object.keys(exportPaths).forEach((format) => {
      const value = ready && project.exports && project.exports[format];
      byId("download-" + format).disabled = downloading || value !== exportPaths[format];
    });
  }

  function indexEvidence(data) {
    evidenceTargets.clear();
    list(data.sources).forEach((source, index) => {
      if (source && typeof source.id === "string") evidenceTargets.set(source.id, "source-" + index);
    });
    list(data.trials).forEach((trial, index) => {
      const id = trial && text(trial.id || trial.trial_id);
      if (id) evidenceTargets.set(id, "trial-" + index);
    });
    list(data.claims).forEach((claim, index) => {
      if (claim && typeof claim.id === "string") evidenceTargets.set(claim.id, "claim-" + index);
    });
  }

  function renderContext(data) {
    const labels = data.labels || {};
    const dataset = data.dataset || {};
    const scientific = text(labels.scientific_status || dataset.scientific_status);
    const scientificLabels = { benchmark_only: "公开基准验证，不能外推科研发现", engineering_only: "工程验证" };
    const context = byId("project-labels");
    context.replaceChildren();
    definition(context, "数据任务", text(labels.dataset || dataset.dataset_id, "未提供"));
    definition(context, "决策来源", text(labels.decision_origin, "脚本决策与真实训练"));
    definition(context, "证据状态", scientificLabels[scientific] || scientific || "未提供");
    definition(context, "平台接入", text(labels.cloud, "模型与 AgentArts 接入暂缓"));

    const sourceGoal = text(data.source_goal);
    byId("source-goal").textContent = sourceGoal ? "原始研究目标：" + sourceGoal : "本页依据当前冻结证据说明问题与边界。";
    const claims = byId("claims-list");
    claims.replaceChildren();
    list(data.claims).forEach((claim, index) => {
      if (!claim || typeof claim !== "object") return;
      const known = { observed: "记录事实", limitation: "适用边界", planned: "待执行计划" };
      const state = Object.hasOwn(known, claim.status) ? claim.status : "unconfirmed";
      const row = make("div", "claim " + state);
      row.id = "claim-" + index;
      row.append(make("span", "claim-label", known[state] || "状态待核对"), make("p", "", text(claim.statement, "未提供论断正文")));
      const refs = references(claim.evidence_ids);
      if (refs) row.append(refs);
      claims.append(row);
    });
    if (!claims.children.length) claims.append(make("p", "empty-state", "当前快照尚未提供可追溯的论断。"));

    const record = byId("dataset-record");
    const snapshot = data.snapshot || {};
    const splits = dataset.split_counts || {};
    record.replaceChildren();
    definition(record, "目标与单位", text(dataset.target, "未提供") + (dataset.target_unit ? " · " + text(dataset.target_unit) : ""));
    definition(record, "数据划分", ["train", "validation", "test"].map((key) => ({ train: "训练", validation: "验证", test: "测试" }[key] + " " + text(splits[key], "未提供"))).join(" / "));
    definition(record, "输入特征", list(dataset.feature_names).map((item) => text(item)).join("、") || "未提供");
    definition(record, "划分协议", text(dataset.split_protocol && (dataset.split_protocol.name || dataset.split_protocol.id), "未提供"), "mono");
    definition(record, "数据 SHA256", text(dataset.data_sha256 || dataset.raw_sha256, "未提供"), "mono");
    definition(record, "来源任务", text(snapshot.source_campaign_id, "未提供"), "mono");
    definition(record, "快照 SHA256", text(snapshot.sha256, "未提供"), "mono");
    definition(record, "快照时间", dateText(snapshot.created_at));
    list(dataset.limitations).forEach((item, index) => definition(record, "数据边界 " + (index + 1), text(item, "未提供")));
  }

  function renderSources(data) {
    const container = byId("sources-list");
    container.replaceChildren();
    list(data.sources).forEach((source, index) => {
      if (!source || typeof source !== "object") return;
      const item = make("li");
      item.id = "source-" + index;
      const title = make("p", "source-title");
      const url = httpsLink(source.url);
      if (url) {
        const link = make("a", "", text(source.title, "未命名来源"));
        link.href = url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        title.append(link);
      } else {
        title.textContent = text(source.title, "未命名来源");
        item.append(make("p", "small-note", "来源链接未提供或不符合 HTTPS 要求。"));
      }
      item.prepend(title);
      item.append(make("p", "source-description", text(source.description, "未提供来源说明。")));
      item.append(make("code", "source-id", text(source.id, "来源编号未提供")));
      container.append(item);
    });
    if (!container.children.length) container.append(make("li", "empty-state", "尚未提供可追溯的原始来源。"));
  }

  function renderTrials(data) {
    const trials = list(data.trials);
    const metrics = data.metrics || {};
    const unit = text(data.dataset && data.dataset.target_unit);
    const mseUnit = unit && unit !== "unitless" && unit !== "arbitrary" ? "（" + unit + "²）" : "";
    const strip = byId("metric-strip");
    strip.replaceChildren();
    const first = make("div");
    first.append(make("dt", "", "已记录试验"), make("dd", "", count(metrics.trials, trials.length) + " 次"));
    first.append(make("p", "metric-note", "保留 " + count(metrics.accepted, trials.filter((trial) => trial.status === "accepted").length) + " / 未晋升 " + count(metrics.rejected, trials.filter((trial) => trial.status === "rejected").length)));
    strip.append(first);
    definition(strip, "最佳验证 MSE" + mseUnit, finiteNumber(metrics.best_validation_mse));
    definition(strip, "终测 MSE" + mseUnit, finiteNumber(metrics.test_mse));
    byId("mse-heading").textContent = "验证 MSE" + mseUnit;
    const best = byId("best-trial");
    best.replaceChildren(make("span", "", "当前保留模型："));
    const bestId = text(metrics.best_trial_id);
    const target = evidenceTargets.get(bestId);
    const bestLink = make(target ? "a" : "code", "", bestId || "未记录");
    if (target) bestLink.href = "#" + target;
    best.append(bestLink);

    const body = byId("trials-body");
    body.replaceChildren();
    const states = { accepted: "保留", rejected: "未晋升", failed: "失败", running: "快照记录：在途" };
    trials.forEach((trial, index) => {
      if (!trial || typeof trial !== "object") return;
      const row = make("tr");
      row.id = "trial-" + index;
      const identity = make("td");
      identity.append(make("div", "trial-order", "第 " + count(trial.ordinal, index + 1) + " 次"));
      identity.append(make("code", "trial-name", text(trial.id || trial.trial_id, "试验编号缺失")));
      if (text(trial.id || trial.trial_id) === bestId) identity.append(make("span", "best-marker", "当前保留模型"));
      const recipe = make("td");
      const candidate = trial.candidate || {};
      recipe.append(make("span", "recipe-line", "多项式阶数 " + text(candidate.degree, "未提供")));
      recipe.append(make("span", "recipe-line", "正则系数 α " + finiteNumber(candidate.alpha)));
      const metric = make("td", "", finiteNumber(trial.metrics && trial.metrics.validation_mse));
      const decision = make("td");
      const state = Object.hasOwn(states, trial.status) ? trial.status : "unconfirmed";
      decision.append(make("span", "status " + state, states[state] || "状态待核对"));
      const audit = make("td");
      const details = make("details", "trial-details");
      details.append(make("summary", "", "依据与模型记录"));
      const reason = text(trial.decision_reason || trial.reason, "未提供判定依据。");
      details.append(make("p", "", reason));
      if (trial.proposal && trial.proposal.hypothesis) details.append(make("p", "", "提案假设：" + text(trial.proposal.hypothesis)));
      details.append(make("p", "mono", "父试验：" + text(trial.parent_trial_id, "无 / 未记录")));
      details.append(make("p", "mono", "模型 SHA256：" + text(trial.model_sha256, "未记录")));
      if (trial.error) details.append(make("p", "", "失败记录：" + text(trial.error.code, "失败原因未提供")));
      audit.append(details);
      row.append(identity, recipe, metric, decision, audit);
      body.append(row);
    });
    byId("trials-empty").hidden = body.children.length > 0;
    document.querySelector(".table-scroll").hidden = body.children.length === 0;
  }

  function renderFigures(data) {
    const container = byId("figures-list");
    container.replaceChildren();
    list(data.figures).forEach((figure, index) => {
      if (!figure || typeof figure !== "object") return;
      const item = make("figure", "figure");
      const title = text(figure.title, "结果图 " + (index + 1));
      item.append(make("h3", "", title));
      const wrap = make("div", "figure-image-wrap");
      if (figurePaths.includes(figure.url)) {
        const image = make("img");
        image.alt = title;
        image.loading = "lazy";
        image.decoding = "async";
        image.src = figure.url;
        image.addEventListener("error", () => {
          wrap.replaceChildren(make("p", "figure-error", "图表暂未载入，请刷新页面或查看复现附件。"));
        }, { once: true });
        wrap.append(image);
      } else {
        wrap.append(make("p", "figure-error", "未提供可用的本地图表。"));
      }
      item.append(wrap, make("figcaption", "", text(figure.caption, "未提供图表说明；请结合试验记录判断。")));
      container.append(item);
    });
    if (!container.children.length) container.append(make("p", "empty-state", "当前快照未提供结果图，页面不会生成替代图表。"));
  }

  function renderPaper(data) {
    const report = data.report || {};
    const container = byId("paper-preview");
    container.replaceChildren(make("h3", "", text(report.title, text(data.title, "研究报告"))));
    list(report.sections).forEach((section) => {
      if (typeof section === "string") {
        container.append(make("p", "", section));
        return;
      }
      if (!section || typeof section !== "object") return;
      if (section.heading) container.append(make("h4", "", text(section.heading)));
      list(section.paragraphs).forEach((paragraph) => {
        if (typeof paragraph === "string") container.append(make("p", "", paragraph));
      });
      const refs = references(section.claim_ids, "关联论断");
      if (refs) container.append(refs);
    });
    if (!list(report.sections).length) container.append(make("p", "empty-state", "当前快照未提供报告正文。"));
  }

  function renderQuestions() {
    const questions = list(project && project.next_questions);
    const container = byId("questions-list");
    container.replaceChildren();
    questions.slice().reverse().forEach((question) => {
      if (!question || typeof question !== "object") return;
      const item = make("li");
      item.append(make("p", "question-text", text(question.text, "问题正文未提供")));
      const meta = make("div", "question-meta");
      meta.append(make("span", "status", question.status === "saved_pending_execution" ? "待人工执行" : "状态待核对"));
      meta.append(make("time", "", dateText(question.created_at)));
      item.append(meta);
      container.append(item);
    });
    byId("questions-count").textContent = container.children.length + " 条";
    byId("questions-empty").hidden = container.children.length > 0;
  }

  function observeChapters() {
    if (sectionObserver) sectionObserver.disconnect();
    if (!("IntersectionObserver" in window)) return;
    sectionObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        document.querySelectorAll("#chapter-nav a").forEach((link) => {
          if (link.getAttribute("href") === "#" + entry.target.id) link.setAttribute("aria-current", "location");
          else link.removeAttribute("aria-current");
        });
      });
    }, { rootMargin: "-10% 0px -65% 0px", threshold: 0 });
    document.querySelectorAll(".reading-section").forEach((section) => sectionObserver.observe(section));
  }

  async function jsonRequest(path, options = {}) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(path, { ...options, signal: controller.signal, credentials: "same-origin", cache: "no-store" });
      let result;
      try { result = await response.json(); } catch (_) { throw new Error("服务返回的内容无法读取，请刷新后重试。"); }
      if (!result || typeof result !== "object") throw new Error("服务返回的数据格式无法确认，请刷新后重试。");
      if (response.status === 403) throw new Error("本地服务拒绝了请求，请使用当前服务地址刷新后重试。");
      if (!response.ok || result.ok === false) {
        const message = result && result.error && text(result.error.message);
        throw new Error(message ? message.slice(0, 400) : "本地服务未完成请求，请刷新后重试。");
      }
      return result;
    } finally {
      window.clearTimeout(timer);
    }
  }

  async function loadProject() {
    project = null;
    csrfToken = "";
    byId("load-state").hidden = false;
    byId("project-error").hidden = true;
    byId("project-content").hidden = true;
    byId("sidebar-title").textContent = "正在读取项目";
    byId("sidebar-status").textContent = "读取本地快照";
    setNavigationEnabled(false);
    updateControls();
    try {
      const data = await jsonRequest("/api/project");
      if (!data || typeof data !== "object" || !text(data.id) || !text(data.title)) throw new Error("项目快照缺少必要信息，请由操作者核对本地记录。");
      project = data;
      csrfToken = typeof data.csrf_token === "string" ? data.csrf_token : "";
      byId("project-title").textContent = data.title;
      byId("project-question").textContent = text(data.question, "当前快照未提供研究问题。");
      byId("sidebar-title").textContent = data.title;
      byId("sidebar-title").title = data.title;
      byId("sidebar-status").textContent = "现有快照已载入";
      byId("snapshot-mode").textContent = data.snapshot && data.snapshot.mode === "frozen_existing_evidence" ? "冻结的现有证据" : "快照模式待核对";
      document.title = data.title + " · 持续科研";
      indexEvidence(data);
      renderContext(data);
      renderSources(data);
      renderTrials(data);
      renderFigures(data);
      renderPaper(data);
      renderQuestions();
      byId("snapshot-footer").textContent = "快照时间：" + dateText(data.snapshot && data.snapshot.created_at) + " · 后续问题单独保存，不改变原试验证据。";
      feedback("export-feedback", "下载文件来自本地服务，不会触发模型或新试验。");
      feedback("save-feedback", csrfToken ? "" : "保存暂不可用，请刷新页面后重试。", csrfToken ? "" : "error");
      byId("load-state").hidden = true;
      byId("project-content").hidden = false;
      setNavigationEnabled(true);
      updateControls();
      observeChapters();
    } catch (error) {
      project = null;
      csrfToken = "";
      byId("load-state").hidden = true;
      byId("project-error").hidden = false;
      byId("sidebar-title").textContent = "项目尚未载入";
      byId("sidebar-status").textContent = "读取失败，可重试";
      byId("project-error-message").textContent = error.name === "AbortError" ? "读取本地快照超时，请确认服务状态后重试。" : text(error.message, "请确认本地研究服务可用，再重试。");
      updateControls();
    }
  }

  async function downloadExport(format) {
    if (!project || downloading || !project.exports || project.exports[format] !== exportPaths[format]) return;
    downloading = true;
    const button = byId("download-" + format);
    const original = button.textContent;
    button.textContent = format === "pdf" ? "正在获取 PDF…" : "正在获取复现附件…";
    button.setAttribute("aria-busy", "true");
    feedback("export-feedback", "正在从本地服务获取文件…");
    updateControls();
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 60000);
    try {
      const response = await fetch(exportPaths[format], { signal: controller.signal, credentials: "same-origin", cache: "no-store" });
      const contentType = (response.headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase();
      const allowedTypes = format === "pdf" ? ["application/pdf", "application/octet-stream"] : ["application/zip", "application/x-zip-compressed", "application/octet-stream"];
      if (!response.ok || !allowedTypes.includes(contentType)) throw new Error("文件暂不可用，请稍后重试；不会启动额外研究。");
      const blob = await response.blob();
      if (!blob.size) throw new Error("服务返回了空文件，请由操作者核对导出记录。");
      const url = URL.createObjectURL(blob);
      const anchor = make("a");
      anchor.href = url;
      anchor.download = format === "pdf" ? "研究报告.pdf" : "复现附件.zip";
      anchor.hidden = true;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 30000);
      feedback("export-feedback", "文件已交给浏览器下载，请查看浏览器的下载记录。");
    } catch (error) {
      feedback("export-feedback", error.name === "AbortError" ? "获取文件超时，请稍后重试。" : text(error.message, "下载未完成，请稍后重试。"), "error");
    } finally {
      window.clearTimeout(timer);
      downloading = false;
      button.textContent = original;
      button.removeAttribute("aria-busy");
      updateControls();
    }
  }

  async function saveQuestion(event) {
    event.preventDefault();
    if (!project || saving || !csrfToken) return;
    const input = byId("next-question");
    const value = input.value.trim();
    if (!value) {
      feedback("save-feedback", "请先写下一个后续研究问题。", "error");
      input.focus();
      return;
    }
    saving = true;
    feedback("save-feedback", "正在保存问题，不会启动模型或试验。");
    updateControls();
    try {
      const result = await jsonRequest("/api/questions", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Research-CSRF": csrfToken },
        body: JSON.stringify({ text: value }),
      });
      const question = result.question;
      if (result.ok !== true || !question || typeof question.id !== "string" || typeof question.text !== "string" || question.status !== "saved_pending_execution") throw new Error("保存结果无法确认，请刷新问题列表后再重试。");
      project.next_questions = list(project.next_questions);
      if (!project.next_questions.some((item) => item.id === question.id)) project.next_questions.push(question);
      input.value = "";
      byId("question-count").textContent = "已输入 0 字";
      renderQuestions();
      feedback("save-feedback", "已保存为待人工执行。未启动模型或试验。");
    } catch (error) {
      const message = error.name === "AbortError" || error instanceof TypeError ? "未确认是否保存成功。请刷新查看问题列表，再决定是否重试。" : text(error.message, "保存未完成，请刷新后重试。");
      feedback("save-feedback", message, "error");
    } finally {
      saving = false;
      updateControls();
    }
  }

  byId("retry-project").addEventListener("click", loadProject);
  byId("download-pdf").addEventListener("click", () => downloadExport("pdf"));
  byId("download-reproduction").addEventListener("click", () => downloadExport("reproduction"));
  byId("question-form").addEventListener("submit", saveQuestion);
  byId("next-question").addEventListener("input", () => {
    byId("question-count").textContent = "已输入 " + Array.from(byId("next-question").value).length + " 字";
    updateControls();
  });
  setNavigationEnabled(false);
  loadProject();
})();

