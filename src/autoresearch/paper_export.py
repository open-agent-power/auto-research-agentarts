"""Render a bounded Chinese paper from prepared evidence, without executing research.

The caller owns project validation, figure generation, the evidence snapshot and
the reproduction archive. This module reads only the supplied project and two
local PNGs. Report text is always literal text, never ReportLab paragraph markup.
"""

from io import BytesIO
import hashlib
import math
import os
from pathlib import Path
import tempfile
import threading
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

from .contracts import ResearchError


_FONT_LOCK = threading.Lock()
_PAGE_COUNT = 5
_SOURCE_LIMIT = 3
_QUESTION_LIMIT = 5
_TRIAL_LIMIT = 5
_CLAIM_LIMIT = 8
_DASHES = str.maketrans({"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
                           "\u2014": "-", "\u2212": "-"})


def _text(value, limit=1000):
    """Bound raw text before parsing; retain no XML control characters."""
    if value is None:
        return "未登记"
    text = str(value)
    shortened = len(text) > limit
    text = text[:limit].translate(_DASHES)
    text = "".join(c for c in text if ord(c) >= 32 or c in "\n\t")
    return text.strip() + ("（节选，全文见附件）" if shortened else "")


def _markup(value, limit=1000):
    return escape(_text(value, limit), {'"': "&quot;", "'": "&apos;"}).replace("\n", "<br/>")


def _https_url(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 2048:
        return None
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or (port is not None and not 1 <= port <= 65535)):
        return None
    return value


def _number(value, digits=2):
    if type(value) not in (int, float) or not math.isfinite(value):
        return "未取得"
    return f"{value:,.{digits}f}"


def _font_name():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont

    requested = os.environ.get("AUTORESEARCH_PDF_FONT")
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    candidates = [Path(requested).expanduser()] if requested else [fonts / "simsun.ttf", fonts / "simsun.ttc"]
    with _FONT_LOCK:
        for path in candidates:
            try:
                path = path.resolve()
                if not path.is_file() or path.suffix.lower() not in {".ttf", ".ttc"}:
                    if requested:
                        raise ResearchError("PDF_FONT_INVALID", "configured PDF font must be a local TTF or TTC")
                    continue
                identity = f"{path}:{path.stat().st_mtime_ns}".encode("utf-8")
                name = "ARChinese-" + hashlib.sha256(identity).hexdigest()[:16]
                if name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(name, str(path), subfontIndex=0))
                return name
            except ResearchError:
                raise
            except Exception:
                if requested:
                    raise ResearchError("PDF_FONT_INVALID", "configured local font could not be loaded") from None
        name = "STSong-Light"
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeCIDFont(name))
        return name


def _sections(project):
    result = {}
    report = project.get("report", {})
    for section in report.get("sections", [])[:12]:
        if not isinstance(section, dict):
            continue
        heading = _text(section.get("heading", ""), 80)
        paragraphs = section.get("paragraphs", [])
        if not isinstance(paragraphs, list):
            paragraphs = []
        result[heading] = {"paragraphs": paragraphs[:12], "claim_ids": section.get("claim_ids", [])}
    return result


def render_paper(project: dict, figure_directory: Path, output: Path) -> dict:
    """Write a five-page evidence paper; no model, database or dataset is accessed.

    ``project`` follows the prepared-project contract. The only filesystem inputs
    are a trusted local font and ``validation.png`` / ``prediction.png``. Long
    paragraphs are excerpted, with the complete project retained by the caller.
    """
    if not isinstance(project, dict) or not isinstance(project.get("dataset"), dict):
        raise ResearchError("PDF_PROJECT_INVALID", "a prepared project with dataset evidence is required")
    if project.get("snapshot", {}).get("mode") != "frozen_existing_evidence":
        raise ResearchError("PDF_PROJECT_INVALID", "paper export requires a frozen existing-evidence snapshot")
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.utils import ImageReader
        from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        raise ResearchError("PDF_DEPENDENCY_REQUIRED", "install the documented reports dependencies for PDF export") from None

    font = _font_name()
    green = colors.HexColor("#244A3B")
    grey = colors.HexColor("#5A625E")
    pale = colors.HexColor("#F1F5F2")
    width, height = A4
    margin = 49
    usable = width - margin * 2
    body = ParagraphStyle("ARBody", fontName=font, fontSize=10.3, leading=15.5,
                          textColor=colors.black, spaceAfter=7, wordWrap="CJK", splitLongWords=1)
    small = ParagraphStyle("ARSmall", parent=body, fontSize=8.6, leading=12.3, spaceAfter=4)
    note = ParagraphStyle("ARNote", parent=small, textColor=grey)
    heading = ParagraphStyle("ARHeading", parent=body, fontSize=12.2, leading=18,
                             textColor=green, spaceBefore=9, spaceAfter=8, keepWithNext=True)
    title = ParagraphStyle("ARTitle", parent=body, fontSize=18, leading=25,
                           spaceAfter=11, textColor=colors.black)
    table_body = ParagraphStyle("ARTable", parent=small, fontSize=8.8, leading=12.5, spaceAfter=0)
    table_header = ParagraphStyle("ARTableHeader", parent=table_body, textColor=green)
    caption = ParagraphStyle("ARCaption", parent=small, alignment=TA_CENTER, spaceBefore=5, spaceAfter=9)
    sections = _sections(project)
    dataset = project["dataset"]
    metrics = project.get("metrics", {})
    trials = project.get("trials", [])[:_TRIAL_LIMIT]
    snapshot = project.get("snapshot", {})
    story = []

    def p(value, style=body, limit=1000):
        return Paragraph(_markup(value, limit), style)

    def h(value):
        story.append(p(value, heading, 100))

    def section(name, budget, *, style=body, default=None):
        item = sections.get(name, {})
        values = item.get("paragraphs", [])
        remaining = budget
        shown = False
        for value in values:
            if not isinstance(value, str) or not value.strip():
                continue
            if remaining <= 0:
                break
            story.append(p(value, style, remaining))
            remaining -= min(len(value), remaining)
            shown = True
        if not shown and default:
            story.append(p(default, style, budget))
        claim_ids = item.get("claim_ids", [])
        if isinstance(claim_ids, list) and claim_ids:
            story.append(p("关联主张：" + "、".join(_text(x, 18) for x in claim_ids[:8]), note, 200))

    def table(headers, rows, proportions, *, compact=False):
        cell_style = (ParagraphStyle("ARIndex", parent=table_body, fontSize=8.2, leading=11.4)
                      if compact else table_body)
        data = [[p(x, table_header, 120) for x in headers]]
        data.extend([[p(x, cell_style, 300) for x in row] for row in rows])
        result = Table(data, colWidths=[usable * part for part in proportions], repeatRows=1,
                       hAlign="LEFT", splitByRow=1)
        result.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), pale),
            ("LINEABOVE", (0, 0), (-1, 0), .7, green),
            ("LINEBELOW", (0, 0), (-1, 0), .45, green),
            ("LINEBELOW", (0, -1), (-1, -1), .4, colors.HexColor("#BAC7BF")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFBFA")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 3 if compact else 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3 if compact else 6),
        ]))
        story.append(result)
        story.append(Spacer(1, 7))

    def figure(name, maximum_height):
        directory = Path(figure_directory).resolve()
        path = (directory / name).resolve()
        if not path.is_relative_to(directory) or not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
            raise ResearchError("PDF_FIGURE_INVALID", "a bounded local PNG figure is required: " + name)
        try:
            with path.open("rb") as stream:
                if stream.read(8) != b"\x89PNG\r\n\x1a\n":
                    raise ValueError("not PNG")
            image_width, image_height = ImageReader(str(path)).getSize()
            if not image_width or not image_height or image_width * image_height > 24_000_000:
                raise ValueError("invalid dimensions")
        except Exception:
            raise ResearchError("PDF_FIGURE_INVALID", "local figure could not be read: " + name) from None
        factor = min(usable / image_width, maximum_height / image_height)
        story.append(Image(str(path), width=image_width * factor, height=image_height * factor, hAlign="CENTER"))

    # Page 1: an argument and a question, not a decorative cover or execution log.
    paper_title = project.get("report", {}).get("title") or project.get("title") or "公开材料数据上的研究方法验证"
    story.append(p(paper_title, title, 100))
    story.append(p("已有证据的冻结研究快照 | " + _text(snapshot.get("created_at"), 50), note, 120))
    story.append(p("本报告组织已有实验和来源，不发起新的模型调用、训练或终测。完整段落及复现细节保留在项目附件中。", small))
    labels = project.get("labels", {})
    if isinstance(labels, dict) and labels:
        label_names = {"dataset": "数据集", "decision_origin": "决策来源",
                       "scientific_status": "证据状态", "cloud": "平台状态"}
        label_text = "；".join(f"{_text(label_names.get(key, key), 35)}：{_text(value, 90)}"
                             for key, value in list(labels.items())[:6])
        story.append(p(label_text, note, 380))
    h("摘要")
    section("摘要", 410, default="本报告根据保存的研究快照整理方法、实际结果和结论边界。")
    h("1 研究问题与依据")
    section("研究问题与依据", 430, default=project.get("question", project.get("source_goal")))
    h("2 研究假设")
    section("研究假设", 280, default="候选假设及预期与实际结果分开记录；证据不足时不提升结论等级。")
    story.append(PageBreak())

    # Page 2: fixed design and the method actually used by this project.
    h("3 数据与评价设计")
    section("数据与评价设计", 420)
    counts = dataset.get("split_counts", {})
    features = dataset.get("feature_names", [])
    table(["设计项", "本项目记录"], [
        ["数据与目标", f"{dataset.get('dataset_id', '未登记')}；{dataset.get('target', '未登记')}"],
        ["样本划分", f"训练 {counts.get('train', '未登记')} / 验证 {counts.get('validation', '未登记')} / 终测保留 {counts.get('test', '未登记')}"],
        ["输入与单位", f"输入字段 {len(features)} 个；目标单位 {dataset.get('target_unit', '未登记')}"],
        ["证据性质", f"{dataset.get('evidence_type', '未登记')}；{dataset.get('scientific_status', '未登记')}"],
        ["终测状态", "本快照未取得终测结果；不以验证误差充当终测成绩。" if metrics.get("test_mse") is None else "终测指标见完整证据附件；不回流后续选参。"],
    ], [.22, .78])
    h("4 模型与复算方法")
    section("模型与复算方法", 450)
    story.append(p("解释范围：同一项目中的候选比较只支持已记录数据、划分和评价协议下的判断。官方基准成绩、跨域价值及科学机制须另有相应证据。", small))
    story.append(PageBreak())

    # Page 3: measured values remain distinct from proposed effects.
    h("5 实际结果与候选比较")
    section("结果与比较", 370)
    statuses = {"accepted": "当次采用", "rejected": "未采用", "failed": "失败", "running": "运行中"}
    rows = []
    for index, trial in enumerate(trials, 1):
        candidate = trial.get("candidate", {})
        measured = trial.get("metrics", {})
        rows.append([f"T{index}", candidate.get("degree", "未登记"), _number(candidate.get("alpha"), 3),
                     _number(measured.get("training_mse")), _number(measured.get("validation_mse")),
                     statuses.get(trial.get("status"), trial.get("status", "未登记"))])
    if not rows:
        rows.append(["-", "-", "-", "未取得", "未取得", "无试验记录"])
    table(["试验", "阶数", "alpha", "训练 MSE", "验证 MSE", "决定"], rows, [.07, .08, .12, .25, .26, .22])
    story.append(p("MSE单位为目标单位的平方；表中数值按两位小数显示，alpha按三位小数显示，完整精度见复现附件。采用状态与科学假设成立分开。", note))
    figure("validation.png", 230)
    story.append(p("图1 保存的候选验证误差比较。图中数据来自同一冻结项目；未重新训练或补造实验。", caption))
    story.append(PageBreak())

    # Page 4: the retained model's validation predictions are not terminal evidence.
    h("6 保留模型的验证集表现")
    figure("prediction.png", 260)
    story.append(p("图2 最佳保留模型在验证集上的预测与观测比较。验证集参与候选选择，本图不能作为独立终测或临床有效性的证明。", caption))
    story.append(p("最佳保留模型验证 MSE：" + _number(metrics.get("best_validation_mse"))
                   + "。该值描述已保存结果，不构成模型优于外部基线或材料机制成立的主张。", small))
    h("7 局限与结论")
    section("局限与结论", 620)
    story.append(p("当前报告的事实边界：已有本地计算、脚本fixture决策与真实LLM推理分别认定；完整云端编排、真实跨域效果和科学解释须按对应证据验收。", small))
    story.append(PageBreak())

    # Page 5: references, claim linkage and a saved continuation, not invented work.
    h("8 后续研究与复现")
    section("后续研究与复现", 220, style=small)
    questions = project.get("next_questions", [])
    if questions:
        for index, question in enumerate(questions[:_QUESTION_LIMIT], 1):
            text = question.get("text", "") if isinstance(question, dict) else question
            story.append(p(f"后续 {index}：{_text(text, 85)}（已保存，尚未执行）", small, 150))
        if len(questions) > _QUESTION_LIMIT:
            story.append(p("其余后续问题见项目附件；正文最多展示5项。", note))
    else:
        story.append(p("尚未保存新的后续问题；重新打开项目后可基于现有证据继续规划。", small))
    h("参考文献与数据来源")
    for source in project.get("sources", [])[:_SOURCE_LIMIT]:
        source_id = _text(source.get("id", ""), 16)
        story.append(p(f"[{source_id}] {_text(source.get('title', '未登记来源'), 125)}", small, 150))
        url = _https_url(source.get("url"))
        if url:
            safe = escape(url, {'"': "&quot;", "'": "&apos;"})
            story.append(Paragraph(f'<link href="{safe}" color="#244A3B">{escape(_text(url, 150))}</link>', note))
        else:
            story.append(p("来源地址未通过HTTPS校验；请按复现附件中的来源记录核对。", note))
    h("主张与证据索引")
    aliases = {trial.get("id"): f"T{i}" for i, trial in enumerate(trials, 1)}
    aliases[project.get("id")] = "项目快照"
    claim_rows = []
    for claim in project.get("claims", [])[:_CLAIM_LIMIT]:
        evidence_ids = claim.get("evidence_ids", [])
        evidence = "、".join(_text(aliases.get(item, item), 22) for item in evidence_ids[:8])
        claim_rows.append([claim.get("id", ""), _text(claim.get("statement", ""), 48), evidence or "见项目附件"])
    if claim_rows:
        table(["主张", "有据陈述（节选）", "证据"], claim_rows, [.10, .62, .28], compact=True)
    trial_range = "T1" if len(trials) == 1 else f"T1至T{len(trials)}" if trials else "试验编号"
    story.append(p(trial_range + "按本报告试验顺序对应完整trial_id；原始结果、代码／配置、模型与图表输入、来源及完整主张保存在复现包。保存后续问题不等于已执行。", note, 200))
    story.append(p("证据快照：" + _text(snapshot.get("sha256"), 64), note, 100))

    pages = []

    def page_frame(canvas, document):
        pages.append(document.page)
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(grey)
        canvas.drawString(margin, height - 30, "AutoResearch | 论文式方法验证与复现")
        canvas.drawRightString(width - margin, 27, f"第 {document.page} 页")
        canvas.setStrokeColor(colors.HexColor("#D7DFD9"))
        canvas.setLineWidth(.35)
        canvas.line(margin, 40, width - margin, 40)
        canvas.restoreState()

    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=margin, leftMargin=margin,
                                 topMargin=49, bottomMargin=53, title=_text(paper_title, 100),
                                 author="AutoResearch", pageCompression=1, allowSplitting=1)
    try:
        document.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    except Exception:
        raise ResearchError("PDF_RENDER_FAILED", "prepared evidence could not be laid out as a paper") from None
    count = max(pages, default=0)
    if count != _PAGE_COUNT:
        raise ResearchError("PDF_LAYOUT_LIMIT", "bounded paper exceeded its five-page layout; review section lengths")
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".paper-", suffix=".tmp", dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(buffer.getvalue())
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return {"path": str(output), "pages": count, "font": font, "generated_from_existing_evidence": True}
