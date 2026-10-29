"""Read-only loopback presentation of an independently computed C01 run."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import os
from pathlib import Path
import stat
import zipfile
from xml.sax.saxutils import escape

from .paper_export import _font_name

_REQUIRED = {"summary.json", "source-manifest.json", "audit.csv", "cleaned_samples.csv", "loo_predictions.csv", "rounds.csv", "evidence/input.zip",
             "evidence/attachments/TNZST_Summary table.xlsx", "evidence/attachments/TNZST_Summary table_bio.xlsx",
             "evidence/attachments/TNZST_SFE calculation ver 3.xlsx", "evidence/attachments/TNZST_XRD.xlsx",
             "evidence/attachments/TNZST_Eng_Stress_vs_Eng_Strain.csv"}
_FIGURES = {"figures/loo_mae.svg", "figures/loo_predictions.svg"}


def _read_safe(path, max_bytes=20_000_000):
    path = Path(os.path.abspath(path))
    if os.path.normcase(str(path.resolve())) != os.path.normcase(str(path)):
        raise ValueError("redirected paths are not accepted")
    for item in (path, *path.parents):
        if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
            raise ValueError("linked paths are not accepted")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > max_bytes:
        raise ValueError("unsafe or oversized artifact")
    content = path.read_bytes()
    if len(content) > max_bytes:
        raise ValueError("oversized artifact")
    return content


def _load(workspace, archive):
    root = Path(os.path.abspath(workspace))
    source = Path(os.path.abspath(archive))
    manifest_raw = _read_safe(root / "output-manifest.json", 100_000)
    manifest = json.loads(manifest_raw)
    if manifest.get("schema_version") != "c01-output-manifest-v1" or not isinstance(manifest.get("files"), dict):
        raise ValueError("invalid output manifest")
    names = set(manifest["files"])
    if not _REQUIRED <= names or names - (_REQUIRED | _FIGURES):
        raise ValueError("unexpected or missing manifest files")
    files = {name: _read_safe(root / name) for name in sorted(names)}
    if any(hashlib.sha256(files[name]).hexdigest() != digest for name, digest in manifest["files"].items()):
        raise ValueError("result artifact differs from manifest")
    raw = files["summary.json"]
    data = json.loads(raw)
    if data.get("schema_version") != "c01-analysis-v1" or data.get("case_id") != "C01-TNZST":
        raise ValueError("invalid C01 analysis")
    source_bytes = _read_safe(source)
    if hashlib.sha256(source_bytes).hexdigest() != data["source"]["archive_sha256"]:
        raise ValueError("source archive hash differs from analysis")
    if files["evidence/input.zip"] != source_bytes:
        raise ValueError("evidence archive differs from supplied input")
    script = _read_safe(Path(__file__).with_name("c01.py"))
    if hashlib.sha256(script).hexdigest() != data.get("analysis_code_sha256"):
        raise ValueError("analysis code differs from recorded run; use the matching code or recompute")
    if len(data.get("rounds", [])) != 2:
        raise ValueError("two analysis records required")
    described = {item["path"] for item in data.get("artifacts", {}).get("figures", [])}
    if described != names & _FIGURES or described not in (set(), _FIGURES) or (data.get("figure_status") == "generated") != bool(described):
        raise ValueError("figure list does not match output manifest")
    return data, files, source_bytes, script, manifest_raw


def render_report(data):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

    out = BytesIO()
    font = _font_name()
    normal = ParagraphStyle("body", fontName=font, fontSize=9.5, leading=15, spaceAfter=6)
    title = ParagraphStyle("title", parent=normal, fontSize=19, leading=26, spaceAfter=14)
    head = ParagraphStyle("head", parent=normal, fontSize=13, leading=19, spaceBefore=8)
    cell = ParagraphStyle("cell", parent=normal, fontSize=8, leading=13, spaceAfter=0)
    center = ParagraphStyle("center", parent=cell, alignment=TA_CENTER)
    def para(value, style=normal):
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), style)
    def desc(value):
        if isinstance(value, list):
            return " ".join(map(str, value))
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    story = [para("C01 研究记录：钛合金与体外成骨细胞", title),
        para("研究问题：8 种 TiNbZrSnTa 合金的材料性质与体外成骨细胞终点之间是否存在可检验的联系？"),
        para("本记录是对公开历史数据的探索性复算，分析由本地脚本执行；不是新增细胞实验、真实大模型自主研究或临床结论。"),
        para("数据来源与边界", head),
        para("Torres-Sanchez 等，Mendeley Data Version 1，DOI 10.17632/tt7gwkpck8.1；数据集页面标示 CC BY 4.0。对应论文 DOI 10.1016/j.bioadv.2023.213572。"),
        para("原始输入包 SHA-256：" + data["source"]["archive_sha256"]),
        para("仅 8 个合金；标签映射、星号含义、实验重复和部分单位仍待核验。关联不表示因果或临床疗效。"),
        para("核验要点", head), para("以下问题清单包括人工预审和程序检查；完整逐项记录见附件 audit.csv。")]
    for issue in data["audit"][:11]:
        story.append(para(f"{issue['field']}：{issue['issue']}；处理：{issue['handling']}"))
    for i, round_ in enumerate(data["rounds"], 1):
        alpha = round_["metrics"][0].get("alpha")
        introduction = [para(f"第 {i} 轮：{round_['title']}", head), para("方法：每折拟合标准化与 Ridge，α = " + str(alpha) + "；四个特征为弹性模量、屈服强度、水接触角和 OWRK 总表面自由能。"), para("反馈：" + desc(round_["feedback"]))]
        rows = [[para(s, center) for s in ("体外终点", "模型 MAE", "留一均值 MAE", "R²")]]
        for m in round_["metrics"]:
            rows.append([para(m["target_label"], cell)] + [para(f"{m[k]:,.4g}", center) for k in ("mae", "baseline_mae", "r2")])
        table = Table(rows, colWidths=[58*mm, 33*mm, 38*mm, 25*mm], repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#eaf1e9")), ("GRID",(0,0),(-1,-1),.35,colors.HexColor("#cbd9cc")),("VALIGN",(0,0),(-1,-1),"TOP"), ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4)]))
        story.extend([KeepTogether(introduction + [table]), Spacer(1, 4*mm), para("下一步：" + desc(round_["next_action"]))])
    story.extend([para("局限与后续", head), para(desc(data["rounds"][-1]["limitations"])), para("两轮重复使用同一批数据，第二轮只是敏感性比较，不是独立验证。基线按每折训练集均值计算；不能基于该样本宣称稳健预测、最优材料或新机制。"), para("完整逐折预测、源数据、脚本和依赖版本见独立复现附件。")])
    SimpleDocTemplate(out, pagesize=(210*mm,297*mm), leftMargin=23*mm, rightMargin=23*mm, topMargin=20*mm, bottomMargin=20*mm, title="C01 research record").build(story)
    return out.getvalue()


def reproduction(data, files, archive_bytes, script, manifest_raw):
    import numpy
    import sklearn
    out = BytesIO()
    instructions = ("C01 reproducibility / 本地复算\n"
        "Source: https://data.mendeley.com/datasets/tt7gwkpck8/1 (CC BY 4.0); preserve attribution.\n"
        "Original study: https://doi.org/10.1016/j.bioadv.2023.213572\n"
        f"Input SHA-256: {data['source']['archive_sha256']}\n"
        f"Runtime: Python >=3.11; numpy {numpy.__version__}; scikit-learn {sklearn.__version__}.\n"
        "Run: python c01.py --archive input.zip --output recomputed\n"
        "Compare the recomputed tables with results/. This is an exploratory comparison on 8 alloys, not independent validation.\n")
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", instructions)
        z.writestr("input.zip", archive_bytes)
        z.writestr("c01.py", script)
        z.writestr("results/output-manifest.json", manifest_raw)
        for name, content in files.items():
            z.writestr("results/" + name, content)
    return out.getvalue()


def create_server(workspace, archive, port=8769):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("invalid port")
    data, files, source, script, manifest = _load(workspace, archive)
    raw = files["summary.json"]
    report = render_report(data)
    bundle = reproduction(data, files, source, script, manifest)
    assets = Path(__file__).with_name("web")
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            if self.headers.get_all("Host", []) not in [[f"127.0.0.1:{self.server.server_port}"], [f"localhost:{self.server.server_port}"]]:
                return self.send_error(403)
            entries = {"/api/c01": (raw,"application/json; charset=utf-8",None),
                       "/api/c01/report.pdf": (report,"application/pdf","c01-research-report.pdf"),
                       "/api/c01/reproduction.zip": (bundle,"application/zip","c01-reproduction.zip")}
            for fig in ("loo_mae.svg", "loo_predictions.svg"):
                name = "figures/" + fig
                if name in files:
                    entries["/api/c01/" + name] = (files[name], "image/svg+xml", None)
            static = {"/": ("index.html","text/html; charset=utf-8"),"/app.js": ("app.js","text/javascript; charset=utf-8"),"/app.css": ("app.css","text/css; charset=utf-8"),"/vendor-licenses.txt": ("vendor-licenses.txt","text/plain; charset=utf-8")}
            if self.path in entries:
                body, mime, filename = entries[self.path]
            elif self.path in static:
                name, mime = static[self.path]; body = (assets / name).read_bytes(); filename = None
                if self.path == "/": body = body.replace(b"<body>", b'<body data-case="c01">', 1)
            elif self.path == "/favicon.ico":
                self.send_response(204); self.end_headers(); return
            else:
                return self.send_error(404)
            self.send_response(200)
            self.send_header("Content-Type",mime); self.send_header("Content-Length",str(len(body))); self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff"); self.send_header("Referrer-Policy","no-referrer")
            self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            if filename: self.send_header("Content-Disposition",f'attachment; filename="{filename}"')
            self.end_headers(); self.wfile.write(body)
    server = ThreadingHTTPServer(("127.0.0.1",port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description="Read-only C01 local research workspace")
    parser.add_argument("--workspace",required=True); parser.add_argument("--archive",required=True); parser.add_argument("--port",type=int,default=8769)
    args = parser.parse_args()
    with create_server(args.workspace,args.archive,args.port) as server:
        print(json.dumps({"url":f"http://127.0.0.1:{server.server_port}/#/overview","cloud_calls":0},ensure_ascii=False),flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass


if __name__ == "__main__":
    main()
