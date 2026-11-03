"""Read-only loopback presentation of an independently computed C01 run."""
import argparse
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import os
import re
import secrets
import sqlite3
from pathlib import Path
import stat
import zipfile
from xml.sax.saxutils import escape
from urllib.parse import parse_qsl, urlsplit

from .paper_export import _font_name
from .c01_loop import C01Loop, LoopError
from .research_delivery import load_research_delivery
from .knowledge_browser import KnowledgeBrowser, KnowledgeBrowserError
from .knowledge import KINDS

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
        para("后续人工核对论文：细胞为 MC3T3-E1 小鼠前成骨细胞，每合金/时间点有三次测量，独立培养批次未确认；ALP 按 DNA 归一化。ARS 是染色矿化替代指标，正文/图注写 21 天而图4F轴写 28 天；下表保留原字段数值，日期未裁定。"),
        para("核验要点", head), para("以下问题清单包括人工预审和程序检查；完整逐项记录见附件 audit.csv。")]
    for issue in data["audit"][:11]:
        story.append(para(f"{issue['field']}：{issue['issue']}；处理：{issue['handling']}"))
    for i, round_ in enumerate(data["rounds"], 1):
        alpha = round_["metrics"][0].get("alpha")
        introduction = [para(f"第 {i} 轮：{round_['title']}", head), para("方法：每折拟合标准化与 Ridge，α = " + str(alpha) + "；四个特征为弹性模量、屈服强度、水接触角和 OWRK 总表面自由能。"), para("反馈：" + desc(round_["feedback"]))]
        rows = [[para(s, center) for s in ("体外终点", "模型 MAE", "留一均值 MAE", "R²")]]
        for m in round_["metrics"]:
            label = "ARS 染色原表值（日期冲突）" if m.get("target") == "calcium_deposition_d21_ug_ml" else m["target_label"]
            rows.append([para(label, cell)] + [para(f"{m[k]:,.4g}", center) for k in ("mae", "baseline_mae", "r2")])
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


def render_continuation_report(data, state):
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    out=BytesIO(); font=_font_name()
    body=ParagraphStyle("body",fontName=font,fontSize=9.5,leading=15,spaceAfter=5)
    title=ParagraphStyle("title",parent=body,fontSize=18,leading=26,spaceAfter=15)
    head=ParagraphStyle("head",parent=body,fontSize=13,leading=19,spaceBefore=6)
    def p(text,style=body): return Paragraph(escape(str(text)),style)
    story=[p("C01 后续研究记录",title),p("本记录引用已冻结的 C01 两轮分析，后续行动由本地确定性脚本选择；没有模型、云端或新细胞实验。"),
           p("父快照清单 SHA-256："+state["parent_snapshot_sha256"]),p("状态："+("等待领域复核" if state["status"]=="needs_review" else "已暂停，可继续")),
           p("来源：Torres-Sanchez 等，数据集 DOI 10.17632/tt7gwkpck8.1；对应论文 DOI 10.1016/j.bioadv.2023.213572。"),
           p("论文方法记载 MC3T3-E1 小鼠前成骨细胞，体外实验每合金与时间点为三次测量；独立培养批次未确认。ALP 按 DNA 归一化；ARS 染色时间的正文/图注与图轴存在冲突。")]
    for action in state["actions"]:
        story.extend([p(f"行动 {action['ordinal']}：{action['title']}",head),p("依据："+action["reason"]),p("观察指纹："+action["observation_sha256"])])
        result=action["result"]
        if result["kind"]=="held_out_error_influence":
            names={"cell_seeding_efficiency_24h_pct":"24小时细胞接种效率","dna_cell_count_d21":"第21天DNA原表值（换算待核）","alp_norm_d21":"第21天ALP原表值","calcium_deposition_d21_ug_ml":"ARS染色原表值（日期冲突）"}
            for v in result["targets"]:
                story.append(p(f"{names.get(v['target'],v['target'])}：最大单样本误差来自 {v['sample_id']}，占该目标总绝对误差 {v['share_of_absolute_error']*100:.1f}%。"))
        else:
            story.append(p(f"水接触角与24小时接种效率 Pearson r={result['pearson_r']:.4f}；逐一去除单个合金后符号改变 {result['sign_changes']} 次。"))
            values=result["leave_one_out"]
            rows=[]
            for i in range(0,len(values),2):
                pair=values[i:i+2]
                rows.append([p(f"去除 {v['sample_id']}：r={v['pearson_r']:.4f}") for v in pair])
            table=Table(rows,colWidths=[79*mm,79*mm]);table.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#f6f9f4")),("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),0)]));story.append(table)
        story.extend([p(result["interpretation"]),p("判断："+action["decision"]),Spacer(1,3*mm)])
    story.extend([p("研究限制与下一步",head),p("仅8个合金，变量对在查看数据后选取，属于探索；不构成预注册、独立验证、因果或临床结论。标签与重复结构需领域复核，并寻找独立数据。"),p("原报告与本后续记录是两个关联版本；逐项计算及验证脚本见后续复现附件。")])
    SimpleDocTemplate(out,pagesize=(210*mm,297*mm),leftMargin=23*mm,rightMargin=23*mm,topMargin=20*mm,bottomMargin=20*mm,title="C01 continuation").build(story)
    return out.getvalue()


_VERIFY = '''import hashlib,json,pathlib
from c01_loop import residual_influence,correlation_influence
p=pathlib.Path(__file__).resolve().parent
s=json.loads((p/'continuation.json').read_text(encoding='utf-8'))
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha((p/'c01_loop.py').read_bytes()) == s['analysis_code_sha256'], 'code mismatch'
assert sha((p/'parent-manifest.json').read_bytes()) == s['parent_snapshot_sha256'], 'parent mismatch'
for name,digest in s['inputs'].items(): assert sha((p/name).read_bytes()) == digest, 'input mismatch: '+name
functions={'inspect_residual_influence':lambda:residual_influence((p/'loo_predictions.csv').read_bytes()),'inspect_pair_sensitivity':lambda:correlation_influence((p/'cleaned_samples.csv').read_bytes())}
for action in s['actions']:
 assert functions[action['action']]()==action['result'], 'result mismatch: '+action['id']
print('Verified',len(s['actions']),'local analysis actions; not independent scientific validation.')
'''


def continuation_bundle(state, files, manifest_raw, parent_bundle):
    out=BytesIO(); code=_read_safe(Path(__file__).with_name("c01_loop.py"))
    if hashlib.sha256(code).hexdigest()!=state["analysis_code_sha256"]: raise ValueError("continuation code changed")
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt","C01 continuation: run python verify_continuation.py. Parent-reproduction.zip contains the attributed input and original analysis. All results are exploratory on reused samples, not independent verification or clinical evidence.\n")
        z.writestr("continuation.json",json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False))
        z.writestr("parent-manifest.json",manifest_raw)
        z.writestr("parent-reproduction.zip",parent_bundle)
        z.writestr("c01_loop.py",code)
        z.writestr("verify_continuation.py",_VERIFY)
        for name in ("loo_predictions.csv","cleaned_samples.csv"): z.writestr(name,files[name])
    return out.getvalue()


def create_server(workspace, archive, port=8769, *, continuation=None, research_delivery=None, knowledge_index=None):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("invalid port")
    data, files, source, script, manifest = _load(workspace, archive)
    raw = files["summary.json"]
    report = render_report(data)
    bundle = reproduction(data, files, source, script, manifest)
    research = None if research_delivery is None else load_research_delivery(research_delivery, data['source']['archive_sha256'])
    knowledge = None if knowledge_index is None else KnowledgeBrowser(knowledge_index, research['research'] if research is not None else None)
    research_raw = json.dumps({'enabled': False} if research is None else {
        'enabled': True, 'research': research['research'], 'memory': research['memory'], 'validation': research['validation']},
        ensure_ascii=False, allow_nan=False).encode('utf-8')
    memory_raw = json.dumps(research['memory'] if research is not None and research['memory'] is not None else {'enabled': False},
                            ensure_ascii=False, allow_nan=False).encode('utf-8')
    loop = None
    token = secrets.token_urlsafe(32)
    if continuation is not None:
        child = Path(continuation).resolve()
        parent = Path(workspace).resolve()
        source_path = Path(archive).resolve()
        if child == parent or child.is_relative_to(parent) or parent.is_relative_to(child) or source_path.is_relative_to(child):
            raise ValueError("continuation must be separate from frozen data and archive")
        loop = C01Loop(continuation,manifest,files)
    assets = Path(__file__).with_name("web")
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def send_data(self, status, body, mime="application/json; charset=utf-8", filename=None):
            self.send_response(status)
            self.send_header("Content-Type",mime); self.send_header("Content-Length",str(len(body))); self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff"); self.send_header("Referrer-Policy","no-referrer")
            self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            if filename: self.send_header("Content-Disposition",f'attachment; filename="{filename}"')
            self.end_headers(); self.wfile.write(body)
        def json_reply(self,status,value):
            self.send_data(status,json.dumps(value,ensure_ascii=False,allow_nan=False).encode("utf-8"))
        def host_ok(self):
            return self.headers.get_all("Host", []) in [[f"127.0.0.1:{self.server.server_port}"], [f"localhost:{self.server.server_port}"]]
        def do_GET(self):
            if not self.host_ok():
                return self.send_error(403)
            if self.path.split('?', 1)[0] == '/api/c01/knowledge' or self.path.startswith('/api/c01/knowledge/'):
                try:
                    if len(self.path) > 8192 or not self.path.isascii() or re.search(r'%(?![0-9a-fA-F]{2})', self.path):
                        raise KnowledgeBrowserError('INVALID_REQUEST', 'invalid or oversized knowledge URI', 400)
                    parsed = urlsplit(self.path)
                    if parsed.scheme or parsed.netloc or parsed.fragment:
                        raise KnowledgeBrowserError('INVALID_REQUEST', 'knowledge URI requires a local path', 400)
                    pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True,
                                      encoding='utf-8', errors='strict', max_num_fields=3)
                    if len(pairs) != len({key for key, _ in pairs}):
                        raise KnowledgeBrowserError('INVALID_REQUEST', 'duplicate query parameter', 400)
                    params = dict(pairs)
                    if parsed.path == '/api/c01/knowledge':
                        if params: raise KnowledgeBrowserError('INVALID_REQUEST', 'metadata accepts no query parameters', 400)
                        return self.json_reply(200, {'enabled': False} if knowledge is None else knowledge.metadata())
                    if parsed.path == '/api/c01/knowledge/search':
                        if set(params) - {'q', 'kind', 'limit'} or 'q' not in params:
                            raise KnowledgeBrowserError('INVALID_REQUEST', 'search accepts q, optional kind and limit', 400)
                        if not re.fullmatch('[1-8]', params.get('limit', '5')):
                            raise KnowledgeBrowserError('INVALID_REQUEST', 'limit must be 1..8', 400)
                        if not 1 <= len(params['q']) <= 512 or not params['q'].strip() or ('kind' in params and params['kind'] not in KINDS):
                            raise KnowledgeBrowserError('INVALID_REQUEST', 'q requires 1..512 characters and kind must be known', 400)
                        if knowledge is None: raise KnowledgeBrowserError('KNOWLEDGE_DISABLED', 'no indexed snapshot is mounted', 503)
                        return self.json_reply(200, knowledge.search(params['q'], kind=params.get('kind'), limit=int(params.get('limit', '5'))))
                    prefix = '/api/c01/knowledge/citation/'
                    if parsed.path.startswith(prefix):
                        citation_id = parsed.path[len(prefix):]
                        if params or not re.fullmatch('[0-9a-f]{64}', citation_id):
                            raise KnowledgeBrowserError('INVALID_REQUEST', 'citation lookup accepts one 64-hex ID and no query', 400)
                        if knowledge is None: raise KnowledgeBrowserError('KNOWLEDGE_DISABLED', 'no indexed snapshot is mounted', 503)
                        return self.json_reply(200, knowledge.citation(citation_id))
                    return self.json_reply(404, {'error': {'code': 'NOT_FOUND', 'message': 'knowledge route not found'}})
                except KnowledgeBrowserError as error:
                    return self.json_reply(error.status, {'error': {'code': error.code, 'message': str(error)}})
                except (ValueError, UnicodeError):
                    return self.json_reply(400, {'error': {'code': 'INVALID_REQUEST', 'message': 'invalid knowledge query encoding'}})
            if self.path == "/api/c01/research":
                return self.send_data(200, research_raw)
            if self.path == "/api/c01/research/memory":
                return self.send_data(200, memory_raw)
            research_files = {'/api/c01/research/report.pdf': ('report.pdf', 'application/pdf', 'c01-agent-research-report.pdf'),
                              '/api/c01/research/reproduction.zip': ('reproduction.zip', 'application/zip', 'c01-agent-reproduction.zip'),
                              '/api/c01/research/comparison.png': ('comparison.png', 'image/png', None)}
            if self.path in research_files:
                if research is None: return self.send_error(404)
                name, mime, filename = research_files[self.path]
                return self.send_data(200, research['files'][name], mime, filename)
            if self.path == "/api/c01/continuation":
                if loop is None: return self.json_reply(200,{"enabled":False})
                try: return self.json_reply(200,{"enabled":True,"csrf_token":token,**loop.status()})
                except (LoopError,sqlite3.Error,OSError,ValueError): return self.json_reply(409,{"enabled":True,"error":"研究账本不完整或不可读取；不会自动重跑。"})
            if self.path in {"/api/c01/continuation/evidence.json","/api/c01/continuation/report.pdf","/api/c01/continuation/reproduction.zip"}:
                if loop is None: return self.send_error(404)
                try:
                    state=loop.status()
                    if not state["actions"]: return self.send_error(409)
                    evidence=json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False).encode("utf-8")
                    if self.path.endswith("evidence.json"):
                        return self.send_data(200,evidence,filename="c01-continuation-evidence.json")
                    if self.path.endswith("report.pdf"):
                        return self.send_data(200,render_continuation_report(data,state),"application/pdf","c01-continuation-report.pdf")
                    return self.send_data(200,continuation_bundle(state,files,manifest,bundle),"application/zip","c01-continuation-reproduction.zip")
                except (LoopError,sqlite3.Error,OSError,ValueError): return self.json_reply(409,{"error":"研究记录不可读取。"})
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
            self.send_data(200,body,mime,filename)
        def do_POST(self):
            if not self.host_ok(): return self.send_error(403)
            origins=self.headers.get_all("Origin",[])
            if len(origins)>1 or (origins and origins[0] not in {f"http://127.0.0.1:{self.server.server_port}",f"http://localhost:{self.server.server_port}"}): return self.send_error(403)
            if self.path.split('?', 1)[0] == '/api/c01/knowledge' or self.path.startswith('/api/c01/knowledge/'):
                self.close_connection = True
                return self.json_reply(405, {'error': 'Indexed knowledge snapshots are read-only.'})
            if self.path == "/api/c01/research" or self.path.startswith("/api/c01/research/"):
                self.close_connection = True
                return self.json_reply(405, {'error': 'Completed research and memory snapshots are read-only.'})
            tokens=self.headers.get_all("X-Research-CSRF",[])
            if len(tokens)!=1 or not tokens[0].isascii() or not hmac.compare_digest(tokens[0],token): return self.send_error(403)
            if self.path != "/api/c01/continuation/step" or loop is None: return self.send_error(404)
            lengths=self.headers.get_all("Content-Length",[])
            if self.headers.get("Transfer-Encoding") or len(lengths)!=1 or not lengths[0].isascii() or not lengths[0].isdigit() or not 1<=int(lengths[0])<=1024 or self.headers.get_content_type()!="application/json": return self.send_error(400)
            try:
                self.connection.settimeout(5)
                raw=self.rfile.read(int(lengths[0]))
                pairs=json.loads(raw.decode("utf-8"),object_pairs_hook=lambda p:p)
                if len(raw)!=int(lengths[0]) or not isinstance(pairs,list) or len(pairs)!=2 or {p[0] for p in pairs}!={"request_id","observation_sha256"}: raise ValueError("body")
                values=dict(pairs)
                return self.json_reply(200,loop.step(values["request_id"],values["observation_sha256"]))
            except LoopError as exc: return self.json_reply(409,{"code":exc.code,"error":str(exc)})
            except (OSError,sqlite3.Error,ValueError,TypeError,UnicodeError,IndexError): return self.json_reply(400,{"code":"INVALID_REQUEST","error":"请求或本地账本不可用；未自动重试。"})
    server = ThreadingHTTPServer(("127.0.0.1",port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description="Read-only C01 local research workspace")
    parser.add_argument("--workspace",required=True); parser.add_argument("--archive",required=True); parser.add_argument("--port",type=int,default=8769)
    parser.add_argument("--continuation",help="Separate local directory for bounded continuation; opt-in")
    parser.add_argument("--research-delivery",help="Read-only completed public research delivery; never starts a model")
    parser.add_argument("--knowledge-index",help="Read-only frozen knowledge.sqlite; does not rebuild or execute references")
    args = parser.parse_args()
    with create_server(args.workspace,args.archive,args.port,continuation=args.continuation,research_delivery=args.research_delivery,knowledge_index=args.knowledge_index) as server:
        print(json.dumps({"url":f"http://127.0.0.1:{server.server_port}/#/overview","cloud_calls":0},ensure_ascii=False),flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass


if __name__ == "__main__":
    main()
