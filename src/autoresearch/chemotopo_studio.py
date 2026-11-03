"""Read-only loopback server for one frozen P02 evidence snapshot."""
import argparse
import json
import math
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from xml.sax.saxutils import escape

from .chemotopo_delivery import load_delivery
from .chemotopo_publication import load_publication, read_artifacts
from .contracts import canonical, fingerprint


def render_comparison(comparison):
    if comparison is None:
        return b''
    pairs = comparison['comparison']['pairs']
    if not isinstance(pairs, list) or len(pairs) > 6:
        raise ValueError('invalid policy pairs')
    labels={'recorded_equal_batch':'保留零记录 · 批次等权', 'recorded_equal_section':'保留零记录 · 分区等权',
            'positive_equal_batch':'仅正计数 · 批次等权', 'positive_equal_section':'仅正计数 · 分区等权'}
    rows=[]
    for i, pair in enumerate(pairs):
        value=pair['spearman_midrank']
        if type(value) not in (int,float) or not math.isfinite(value) or not -1 <= value <= 1:
            raise ValueError('invalid Spearman value')
        left=escape(labels.get(pair['left'],str(pair['left']))); right=escape(labels.get(pair['right'],str(pair['right'])))
        y=90+i*52; x=560+min(0,value)*200; width=abs(value)*200
        rows.append(f'<text x="16" y="{y+4}">{left}</text><text x="16" y="{y+22}" fill="#627174">与 {right}</text><rect x="{x:.2f}" y="{y}" width="{width:.2f}" height="19" rx="3" fill="#427e78"/><text x="780" y="{y+15}">{value:.4f}</text>')
    svg=('<svg xmlns="http://www.w3.org/2000/svg" width="850" height="430" viewBox="0 0 850 430" role="img">'
         '<title>四种处理规则的排序相关性</title><rect width="850" height="430" fill="white"/>'
         '<g font-family="Microsoft YaHei, sans-serif" font-size="13" fill="#23343a"><text x="16" y="25" font-size="19">四种处理规则的排序相关性</text>'
         '<text x="16" y="48">Spearman ρ · 原始红通道代理；高低不代表生物获益，尚未确认 ALP。</text>'
         '<path d="M360 80V405 M560 80V405 M760 80V405" stroke="#d7dfdd"/><text x="350" y="74">−1</text><text x="556" y="74">0</text><text x="755" y="74">1</text>' + ''.join(rows) + '</g></svg>')
    return svg.encode('utf-8')


def render_prediction(prediction):
    if prediction is None:
        return b''
    policies = [('recorded_equal_batch', '保留零记录 / 批次等权'), ('positive_equal_batch', '正计数记录 / 批次等权'),
                ('recorded_equal_section', '保留零记录 / 分区等权'), ('positive_equal_section', '正计数记录 / 分区等权')]
    recipes = [('train_mean', '#a5b8b2', '训练均值'), ('chemistry_ridge', '#357e72', '化学'),
               ('chemistry_geometry_ridge', '#b68e57', '化学 + 几何')]
    metrics = prediction['metrics']
    values = [metrics[p][r]['pooled_mae'] for p, _ in policies for r, _, _ in recipes]
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in values):
        raise ValueError('invalid prediction metrics')
    maximum = max(max(values), 1e-9) * 1.1
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1040" height="540" viewBox="0 0 1040 540" role="img">',
             '<title>四规则下的留出预测误差与排序相关</title><rect width="1040" height="540" fill="white"/>',
             '<g font-family="Microsoft YaHei,sans-serif" font-size="14" fill="#243e39">',
             '<text x="24" y="32" font-size="22">几何特征带来的变化</text>',
             '<text x="24" y="58">同一规则内比较 · 整组纹理留出 · 字面红通道代理，尚未确认 ALP</text>',
             '<text x="260" y="105">MAE ↓ 越低越好</text><text x="810" y="105">Spearman ρ ↑</text>',
             '<text x="800" y="130">化学</text><text x="893" y="130">化学 + 几何</text>']
    for i, (recipe, color, label) in enumerate(recipes):
        x = 480 + i * 160
        parts.append(f'<rect x="{x}" y="70" width="12" height="12" rx="2" fill="{color}"/><text x="{x+19}" y="82">{label}</text>')
    for i, (policy, label) in enumerate(policies):
        y = 156 + i * 85
        parts.append(f'<text x="24" y="{y+27}">{escape(label)}</text>')
        for j, (recipe, color, _) in enumerate(recipes):
            value = metrics[policy][recipe]['pooled_mae']; width = 435 * value / maximum
            parts.append(f'<rect x="260" y="{y+j*19}" width="{width:.3f}" height="13" rx="2" fill="{color}"/><text x="{270+width:.3f}" y="{y+j*19+12}">{value:.5f}</text>')
        for x, recipe in [(800, 'chemistry_ridge'), (900, 'chemistry_geometry_ridge')]:
            value = metrics[policy][recipe]['pooled_spearman_midrank']
            if value is not None and (type(value) not in (float, int) or not math.isfinite(value) or abs(value) > 1):
                raise ValueError('invalid rank metric')
            label = '未定义' if value is None else f'{value:.5f}'
            parts.append(f'<text x="{x}" y="{y+27}">{label}</text>')
    parts.append('<text x="24" y="520" fill="#657971">不跨规则选择赢家；排序改善与绝对误差改善分别判断。分组仍使用已测平坦对照。</text></g></svg>')
    return ''.join(parts).encode('utf-8')


def render_iteration_comparison(view):
    """Separate rule facets; MAE primary and Spearman secondary."""
    if view is None: return b''
    policies=[('recorded_equal_batch','保留零值 · 批次等权'),('positive_equal_batch','正计数 · 批次等权'),
              ('recorded_equal_section','保留零值 · 分区等权'),('positive_equal_section','正计数 · 分区等权')]
    prior=view['prior_evidence']['metrics']; candidates=view['comparisons']
    if not isinstance(candidates,list) or len(candidates)>(4 if 'protocol' in view else 2): raise ValueError('invalid iteration candidates')
    if any(type(c['alpha']) not in (int,float) or not math.isfinite(c['alpha']) or not 0.01 <= c['alpha'] <= 1000 for c in candidates) or len({c['alpha'] for c in candidates})!=len(candidates): raise ValueError('unexpected candidate alpha')
    if 'protocol' not in view and any(c['alpha'] not in (10,100) for c in candidates): raise ValueError('unexpected candidate alpha')
    groups=[]
    for policy,label in policies:
        base=prior[policy]
        values=[('仅化学',base['chemistry']['pooled_mae'],base['chemistry']['pooled_spearman_midrank'],'#97aaa3'),
                ('化学 + 几何',base['additive']['pooled_mae'],base['additive']['pooled_spearman_midrank'],'#b38f60'),
                ('交互 α=1',base['interaction']['pooled_mae'],base['interaction']['pooled_spearman_midrank'],'#9c9cbd')]
        for candidate_index,candidate in enumerate(sorted(candidates,key=lambda c:c['alpha'])):
            selected=[r for r in candidate['policies'] if r['policy']==policy]
            if len(selected)!=1: raise ValueError('candidate policy missing or duplicated')
            row=selected[0];values.append((f"交互 α={candidate['alpha']}",row['mae'],row['spearman'],['#3f8277','#6a72a5','#b26b50','#527da0'][candidate_index]))
        for _,mae,rho,_ in values:
            if type(mae) not in (int,float) or not math.isfinite(mae) or mae<0 or (rho is not None and (type(rho) not in (int,float) or not math.isfinite(rho) or abs(rho)>1)):
                raise ValueError('invalid iteration metric')
        groups.append((label,values))
    maximum=max((v[1] for _,rows in groups for v in rows),default=0) or 1
    panel_height=max(350,110+48*(3+len(candidates)))
    height=82+2*(panel_height+20)+28
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}" role="img">',
           f'<title>四种规则下的迭代预测比较</title><rect width="1200" height="{height}" fill="white"/>',
           '<g font-family="Microsoft YaHei,sans-serif" font-size="13" fill="#243e39">',
           '<text x="24" y="32" font-size="22">预测比较：同一规则内对照</text>',
           '<text x="24" y="59">MAE 越低越好；ρ 为次要指标。原始红通道代理尚未确认 ALP。</text>']
    for index,(label,rows) in enumerate(groups):
        x=20+(index%2)*590;y=82+(index//2)*(panel_height+20)
        parts.append(f'<rect x="{x}" y="{y}" width="570" height="{panel_height}" rx="12" fill="#f7faf6" stroke="#dce8dd"/>')
        parts.append(f'<text x="{x+18}" y="{y+30}" font-size="16">{escape(label)}</text><text x="{x+400}" y="{y+52}">MAE ↓</text><text x="{x+490}" y="{y+52}">ρ ↑</text>')
        for j,(name,mae,rho,color) in enumerate(rows):
            yy=y+78+j*48;width=235*mae/maximum;corr='未定义' if rho is None else f'{rho:.4f}'
            parts.append(f'<text x="{x+18}" y="{yy+13}">{escape(name)}</text><rect x="{x+145}" y="{yy}" width="{width:.2f}" height="16" rx="3" fill="{color}"/><text x="{x+400}" y="{yy+13}">{mae:.4f}</text><text x="{x+490}" y="{yy+13}">{corr}</text>')
    parts.append(f'<text x="24" y="{height-12}" fill="#657971">前期结果由操作员运行；新候选由模型选择并执行固定数值拟合，不是 LLM 权重训练。</text></g></svg>')
    return ''.join(parts).encode('utf-8')


def create_server(workspace=None, port=8770, *, archive_receipt=None, memory_workspace=None, report_directory=None, iteration_workspace=None, iteration_report_directory=None, configured_iteration_workspace=None, postrun_directory=None, configured_native_interface="legacy", publication_directory=None, diagnostic_directory=None, handoff_directory=None, source_progress_directory=None, prepared_input_directory=None, source_continuation_directory=None, pipeline_input_directory=None, pipeline_research_directory=None, tabular_research_directory=None):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('invalid port')
    if iteration_workspace and configured_iteration_workspace: raise ValueError('iteration workspaces are mutually exclusive')
    if configured_native_interface not in ('legacy','compact-v1'): raise ValueError('invalid configured native interface')
    def sealed_json(directory,filename,schema):
        from .chemotopo_experiment_evidence import _safe_file
        from .chemotopo_delivery import _safe
        value=json.loads(_safe_file(Path(directory)/filename,3_000_000))
        if (value.get('schema_version')!=schema or value.get('scientific_validation') is not False
            or value.get('snapshot_sha256')!=fingerprint({k:v for k,v in value.items() if k!='snapshot_sha256'}) or _safe(value)!=value):
            raise ValueError('sealed view identity differs')
        return value
    if publication_directory is not None:
        if workspace is not None or archive_receipt or memory_workspace or iteration_workspace or configured_iteration_workspace:
            raise ValueError('sealed publication mode cannot reopen mutable research workspaces')
        if report_directory and Path(report_directory).resolve()!=Path(publication_directory).resolve():raise ValueError('different baseline report directory')
        snapshot=sealed_json(publication_directory,'research.json','p02-workbench-v1');report_directory=publication_directory
    else:
        if workspace is None:raise ValueError('workspace or sealed publication directory required')
        snapshot=load_publication(workspace,archive_receipt=archive_receipt,memory_workspace=memory_workspace)
    artifacts=read_artifacts(report_directory,snapshot) if report_directory else {}
    iteration=None;iteration_artifacts={}
    if iteration_workspace:
        from .chemotopo_iteration_view import load_iteration_view
        iteration=load_iteration_view(iteration_workspace,snapshot)
    elif configured_iteration_workspace:
        from .configured_iteration_view import load_configured_view
        iteration=load_configured_view(configured_iteration_workspace,snapshot,native_interface=configured_native_interface)
    if iteration_report_directory:
        if iteration is None and publication_directory is not None:
            iteration=sealed_json(iteration_report_directory,'iteration.json','p02-iteration-view-v1')
            if iteration.get('baseline_publication_sha256')!=snapshot['snapshot_sha256']:raise ValueError('iteration baseline identity differs')
        if iteration is None: raise ValueError('iteration report requires iteration workspace')
        from .chemotopo_iteration_report import read_iteration_artifacts
        iteration_artifacts=read_iteration_artifacts(iteration_report_directory,iteration)
    postrun_raw=None
    if postrun_directory:
        if iteration is None: raise ValueError('postrun requires iteration workspace')
        from .postrun_view import read_postrun_artifacts, allowed_iteration_snapshots
        postrun_raw=read_postrun_artifacts(postrun_directory,iteration)['postrun.json']
        postrun=json.loads(postrun_raw)
        if postrun.get('iteration_snapshot_sha256') not in allowed_iteration_snapshots(iteration): raise ValueError('postrun iteration identity mismatch')
    diagnostic=None;diagnostic_raw=None;handoff_artifacts={}
    if diagnostic_directory is not None:
        if iteration is None:raise ValueError('diagnostic requires iteration')
        from .diagnostic_view import read_diagnostic_artifacts
        diagnostic_raw=read_diagnostic_artifacts(diagnostic_directory,iteration)['diagnostic.json'];diagnostic=json.loads(diagnostic_raw)
    if handoff_directory is not None:
        if diagnostic is None:raise ValueError('handoff requires diagnostic')
        from .handoff_view import read_handoff_artifacts
        handoff_artifacts=read_handoff_artifacts(handoff_directory,diagnostic)
    source_progress_artifacts={}
    if source_progress_directory is not None:
        if not handoff_artifacts or diagnostic is None:raise ValueError('source progress requires handoff and diagnostic')
        from .source_assessment_view import read_source_progress_artifacts
        source_progress_artifacts=read_source_progress_artifacts(source_progress_directory)
        progress=json.loads(source_progress_artifacts['progress.json'])
        handoff=json.loads(handoff_artifacts['handoff.json'])
        if progress['handoff_snapshot_sha256']!=handoff['snapshot_sha256']:raise ValueError('source progress handoff identity differs')
    source_continuation_artifacts={}
    if source_continuation_directory is not None:
        if not source_progress_artifacts:raise ValueError('source continuation requires original progress')
        from .source_continuation_view import read_source_continuation_artifacts
        source_continuation_artifacts=read_source_continuation_artifacts(source_continuation_directory,progress)
    prepared_input_artifacts={}
    if prepared_input_directory is not None:
        if not handoff_artifacts:raise ValueError('prepared input requires handoff')
        from .tabular_preparation_view import read_tabular_preparation_artifacts
        prepared_input_artifacts=read_tabular_preparation_artifacts(prepared_input_directory,json.loads(handoff_artifacts['handoff.json']))
    pipeline_input_artifacts={}
    if pipeline_input_directory is not None:
        if not handoff_artifacts:raise ValueError('pipeline input requires handoff')
        from .pipeline_preparation_view import read_pipeline_preparation_artifacts
        pipeline_input_artifacts=read_pipeline_preparation_artifacts(pipeline_input_directory,json.loads(handoff_artifacts['handoff.json']))
    pipeline_research_artifacts={}
    if pipeline_research_directory is not None:
        if not pipeline_input_artifacts:raise ValueError('pipeline research requires prepared pipeline input')
        from .pipeline_research_view import read_pipeline_research_artifacts
        pipeline_research_artifacts=read_pipeline_research_artifacts(pipeline_research_directory,json.loads(pipeline_input_artifacts['pipeline-input.json']))
    tabular_research_artifacts={}
    if tabular_research_directory is not None:
        if not prepared_input_artifacts:raise ValueError('tabular research requires prepared tabular input')
        from .tabular_research_view import read_tabular_research_artifacts
        tabular_research_artifacts=read_tabular_research_artifacts(tabular_research_directory,json.loads(prepared_input_artifacts['prepared-input.json']))
    downloads=canonical({'report_pdf':bool(artifacts),'reproduction_zip':bool(artifacts),'iteration_report_pdf':bool(iteration_artifacts),'iteration_reproduction_zip':bool(iteration_artifacts)}).encode('utf-8')
    research=canonical(snapshot).encode('utf-8')
    memory=canonical(snapshot['memory']).encode('utf-8')
    svg=render_comparison(snapshot['comparison'])
    prediction_svg=render_prediction(snapshot['prediction'])
    assets=Path(__file__).with_name('web')
    static={}
    for route,name,mime in [('/', 'index.html','text/html; charset=utf-8'),('/app.js','app.js','text/javascript; charset=utf-8'),('/app.css','app.css','text/css; charset=utf-8'),('/vendor-licenses.txt','vendor-licenses.txt','text/plain; charset=utf-8')]:
        body=(assets/name).read_bytes()
        if route=='/':
            if b'<body>' not in body: raise ValueError('unexpected workbench HTML')
            body=body.replace(b'<body>',b'<body data-case="p02">',1)
        static[route]=(body,mime,None)
    routes={**static,'/api/p02/research':(research,'application/json; charset=utf-8',None),
            '/api/p02/downloads':(downloads,'application/json; charset=utf-8',None),
            '/api/p02/research.json':(research,'application/json; charset=utf-8','p02-research.json'),
            '/api/p02/memory.json':(memory,'application/json; charset=utf-8','p02-memory.json')}
    if svg: routes['/api/p02/policy-comparison.svg']=(svg,'image/svg+xml',None)
    if snapshot['archive'] is not None:
        routes['/api/p02/archive.json']=(canonical(snapshot['archive']).encode('utf-8'),'application/json; charset=utf-8','p02-operator-archive.json')
    if prediction_svg: routes['/api/p02/prediction.svg']=(prediction_svg,'image/svg+xml',None)
    if iteration is not None:
        raw=(canonical(iteration)+'\n').encode('utf-8')
        routes['/api/p02/iteration']=(raw,'application/json; charset=utf-8',None)
        routes['/api/p02/iteration.json']=(raw,'application/json; charset=utf-8','p02-iteration.json')
        routes['/api/p02/iteration-comparison.svg']=(render_iteration_comparison(iteration),'image/svg+xml',None)
    if postrun_raw is not None:
        routes['/api/p02/postrun']=(postrun_raw,'application/json; charset=utf-8',None)
        routes['/api/p02/postrun.json']=(postrun_raw,'application/json; charset=utf-8','p02-postrun.json')
    if diagnostic_raw is not None:
        from .diagnostic_figure import render_diagnostic
        routes['/api/p02/diagnostic']=(diagnostic_raw,'application/json; charset=utf-8',None)
        routes['/api/p02/diagnostic.json']=(diagnostic_raw,'application/json; charset=utf-8','p02-diagnostic.json')
        if diagnostic['topography_chart']:routes['/api/p02/diagnostic-comparison.svg']=(render_diagnostic(diagnostic),'image/svg+xml',None)
    if handoff_artifacts:
        routes['/api/p02/handoff']=(handoff_artifacts['handoff.json'],'application/json; charset=utf-8',None)
        routes['/api/p02/handoff.json']=(handoff_artifacts['handoff.json'],'application/json; charset=utf-8','p02-evidence-handoff.json')
        routes['/api/p02/handoff.md']=(handoff_artifacts['handoff.md'],'text/markdown; charset=utf-8','p02-evidence-handoff.md')
        handoff=json.loads(handoff_artifacts['handoff.json'])
        if handoff.get('selected_task'):
            from .evidence_draft import template_zip_bytes
            routes['/api/p02/evidence-return-template.zip']=(template_zip_bytes(handoff),'application/zip','p02-evidence-return-template.zip')
    if source_progress_artifacts:
        routes['/api/p02/source-progress']=(source_progress_artifacts['progress.json'],'application/json; charset=utf-8',None)
        routes['/api/p02/source-progress.json']=(source_progress_artifacts['progress.json'],'application/json; charset=utf-8','p02-source-progress.json')
        routes['/api/p02/source-progress.md']=(source_progress_artifacts['progress.md'],'text/markdown; charset=utf-8','p02-source-progress.md')
    if source_continuation_artifacts:
        routes['/api/p02/source-continuation']=(source_continuation_artifacts['continuation.json'],'application/json; charset=utf-8',None)
        routes['/api/p02/source-continuation.json']=(source_continuation_artifacts['continuation.json'],'application/json; charset=utf-8','p02-source-continuation.json')
        routes['/api/p02/source-continuation.md']=(source_continuation_artifacts['continuation.md'],'text/markdown; charset=utf-8','p02-source-continuation.md')
    if pipeline_research_artifacts:
        for name,mime in [('pipeline-research.json','application/json; charset=utf-8'),('pipeline-research.md','text/markdown; charset=utf-8')]:
            routes['/api/p02/'+name]=(pipeline_research_artifacts[name],mime,'p02-'+name)
        routes['/api/p02/pipeline-research']=(pipeline_research_artifacts['pipeline-research.json'],'application/json; charset=utf-8',None)
    if tabular_research_artifacts:
        for name,mime in [('tabular-research.json','application/json; charset=utf-8'),('tabular-research.md','text/markdown; charset=utf-8')]:
            routes['/api/p02/'+name]=(tabular_research_artifacts[name],mime,'p02-'+name)
        routes['/api/p02/tabular-research']=(tabular_research_artifacts['tabular-research.json'],'application/json; charset=utf-8',None)
    if pipeline_input_artifacts:
        routes['/api/p02/pipeline-input']=(pipeline_input_artifacts['pipeline-input.json'],'application/json; charset=utf-8',None)
        routes['/api/p02/pipeline-input.json']=(pipeline_input_artifacts['pipeline-input.json'],'application/json; charset=utf-8','p02-pipeline-input.json')
        routes['/api/p02/pipeline-input.md']=(pipeline_input_artifacts['pipeline-input.md'],'text/markdown; charset=utf-8','p02-pipeline-input.md')
    if prepared_input_artifacts:
        routes['/api/p02/prepared-input']=(prepared_input_artifacts['prepared-input.json'],'application/json; charset=utf-8',None)
        routes['/api/p02/prepared-input.json']=(prepared_input_artifacts['prepared-input.json'],'application/json; charset=utf-8','p02-prepared-input.json')
        routes['/api/p02/prepared-input.md']=(prepared_input_artifacts['prepared-input.md'],'text/markdown; charset=utf-8','p02-prepared-input.md')
    if iteration_artifacts:
        routes['/api/p02/iteration-report.pdf']=(iteration_artifacts['report.pdf'],'application/pdf','p02-iteration-report.pdf')
        routes['/api/p02/iteration-reproduction.zip']=(iteration_artifacts['reproduction.zip'],'application/zip','p02-iteration-reproduction.zip')
    if artifacts:
        routes['/api/p02/report.pdf']=(artifacts['report.pdf'],'application/pdf','p02-research-report.pdf')
        routes['/api/p02/reproduction.zip']=(artifacts['reproduction.zip'],'application/zip','p02-reproduction.zip')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def host_ok(self):
            return self.headers.get_all('Host',[]) in [[f'127.0.0.1:{self.server.server_port}'],[f'localhost:{self.server.server_port}']]
        def send_data(self,status,body,mime,filename=None):
            self.send_response(status); self.send_header('Content-Type',mime); self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            if filename: self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
            self.end_headers(); self.wfile.write(body)
        def do_GET(self):
            if not self.host_ok(): return self.send_error(403)
            if self.path=='/favicon.ico': self.send_response(204); self.end_headers(); return
            if self.path not in routes: return self.send_error(404)
            self.send_data(200,*routes[self.path])
        def deny(self):
            self.close_connection=True
            if not self.host_ok(): return self.send_error(403)
            return self.send_data(405,b'{"error":"read-only"}','application/json; charset=utf-8')
        do_POST=do_PUT=do_PATCH=do_DELETE=do_OPTIONS=do_HEAD=do_TRACE=do_CONNECT=deny
    class SnapshotServer(ThreadingHTTPServer):
        allow_reuse_address=False
        def server_bind(self):
            if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
                self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            super().server_bind()
    server=SnapshotServer(('127.0.0.1',port),Handler)
    server.daemon_threads=True
    return server


def main():
    parser=argparse.ArgumentParser(description='Read-only P02 workbench')
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--workspace');source.add_argument('--publication-directory')
    parser.add_argument('--port',type=int,default=8770)
    parser.add_argument('--diagnostic-directory');parser.add_argument('--handoff-directory');parser.add_argument('--source-progress-directory');parser.add_argument('--prepared-input-directory');parser.add_argument('--source-continuation-directory');parser.add_argument('--pipeline-input-directory');parser.add_argument('--pipeline-research-directory');parser.add_argument('--tabular-research-directory')
    parser.add_argument('--archive-receipt');parser.add_argument('--memory-workspace');parser.add_argument('--report-directory')
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--iteration-workspace');group.add_argument('--configured-iteration-workspace')
    parser.add_argument('--iteration-report-directory');parser.add_argument('--postrun-directory');parser.add_argument('--configured-native-interface',choices=('legacy','compact-v1'),default='legacy')
    args=parser.parse_args(); server=create_server(args.workspace,args.port,archive_receipt=args.archive_receipt,
        memory_workspace=args.memory_workspace,report_directory=args.report_directory,iteration_workspace=args.iteration_workspace,iteration_report_directory=args.iteration_report_directory,configured_iteration_workspace=args.configured_iteration_workspace,postrun_directory=args.postrun_directory,configured_native_interface=args.configured_native_interface,publication_directory=args.publication_directory,diagnostic_directory=args.diagnostic_directory,handoff_directory=args.handoff_directory,source_progress_directory=args.source_progress_directory,prepared_input_directory=args.prepared_input_directory,source_continuation_directory=args.source_continuation_directory,pipeline_input_directory=args.pipeline_input_directory,pipeline_research_directory=args.pipeline_research_directory,tabular_research_directory=args.tabular_research_directory)
    print(f'P02 workbench: http://127.0.0.1:{server.server_port}/',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__=='__main__': main()
