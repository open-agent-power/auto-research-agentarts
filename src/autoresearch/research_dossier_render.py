"""Readable PDF/Markdown exports of existing P02 research; never execute a study."""
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

from .contracts import ResearchError, canonical
from .paper_export import _font_name
from .research_dossier import dossier_data

POLICIES = {
    'positive_equal_batch': '正计数 · 批次等权',
    'positive_equal_section': '正计数 · 分区等权',
    'recorded_equal_batch': '保留零值 · 批次等权',
    'recorded_equal_section': '保留零值 · 分区等权',
}
QUESTIONS = {'antibody_channel': '抗体与图像通道', 'object_export': '对象测量与导出列',
             'aggregation': '对照与聚合规则', 'zero_objects': '零对象与缺失值'}


def report_sections(data):
    """Create one shared reading structure for PDF and Markdown."""
    sections = {s['id']: s['data'] for s in data['sections']}
    required = {'baseline', 'iteration', 'diagnostic', 'handoff', 'pipeline_research', 'tabular_research', 'source_continuation'}
    if not required <= sections.keys():
        raise ResearchError('DOSSIER_INPUT_INCOMPLETE', 'This P02 dossier needs numeric, pipeline and tabular research snapshots.')
    baseline = sections['baseline']['prediction']; iteration = sections['iteration']
    pipeline = sections['pipeline_research']; tabular = sections['tabular_research']
    if baseline.get('ALP_approved') is not False or tabular.get('biological_endpoint_eligible') is not False:
        raise ResearchError('DOSSIER_INPUT_UNSUPPORTED', 'This report is for the unresolved P02 biological endpoint.')
    handoff = sections['handoff']; task = handoff['selected_task']
    comparisons = iteration['comparisons']
    if len(comparisons) != 1:
        raise ResearchError('DOSSIER_INPUT_UNSUPPORTED', 'This report layout requires one completed numeric candidate.')
    candidate = comparisons[0]
    rows = sorted(candidate['policies'], key=lambda r: list(POLICIES).index(r['policy']))
    worse = sum(r['mae'] > r['chemistry_mae'] for r in rows)
    better = sum(r['mae'] < r['chemistry_mae'] for r in rows)
    output = []
    def chapter(title):
        blocks = []; output.append({'title': title, 'blocks': blocks}); return blocks
    def paragraph(blocks, text, kind='paragraph'): blocks.append({'kind': kind, 'text': str(text)})
    def table(blocks, headings, values, widths=None): blocks.append({'kind': 'table', 'headings': headings, 'rows': values, 'widths': widths})

    b = chapter('研究问题与当前结论')
    paragraph(b, '材料表面纹理能否在化学组成之外，改善细胞图像代理值的分组预测？', 'lead')
    paragraph(b, '本报告整理当前封存研究的证据链：公开资料 → 分组预测 → 模型选择候选 → 误差诊断 → 取证 → 资料评议。目的在于支持继续、修订或停止研究，不能替代作者原始记录或独立实验。')
    table(b, ['研究对象', '当前范围'], [
        ['共同覆盖的材料组合', str(baseline['keys'])], ['留出纹理组', str(baseline['folds'])],
        ['最新候选', f"交互 Ridge，alpha = {candidate['alpha']}"],
        ['该候选实际拟合', str(iteration['execution']['completed_fits'])],
        ['目标值', '同分区对照归一化的原始红通道代理；ALP身份未确认'],
    ], [135, 356])
    paragraph(b, f"候选在 {len(rows)} 种处理规则中，{better} 种MAE低于化学基线、{worse} 种更高。各规则采用不同的目标构造，不能跨规则按MAE大小选‘最佳处理方式’。", 'lead')
    table(b, ['已经取得', '仍需解决'], [
        ['可复查的来源、数值结果和模型行动', '实际导出列 → 对象 → 染色通道的作者映射'],
        [f"模型已读取{len(pipeline['read_aliases'])}个管线模块、{len(tabular['read_aliases'])}个表格片段", '保存配置与真实执行结果的对应'],
        [f"{len(tabular['answers'])}项有原文引用的评议", '评议的科学准确性及数值分析漏项'],
    ], [245, 246])
    paragraph(b, '报告生成本身新增模型调用0次、拟合0次。既有拟合是数值模型实验，不是大语言模型权重训练；当前记录未证明策略自主改进。', 'note')

    b = chapter('数值实验与误差分布')
    paragraph(b, f"固定共同覆盖的{baseline['keys']}个组合，按{baseline['folds']}个纹理组留一评估。所有比较来自已保存的折外预测；使用已测对照构造目标，并非独立盲测或未来实验效果。")
    table(b, ['处理规则', '化学基线MAE', '候选MAE', '差值'], [
        [POLICIES[r['policy']], f"{r['chemistry_mae']:.6f}", f"{r['mae']:.6f}", f"{r['delta_vs_chemistry']:+.6f}"] for r in rows
    ], [191, 100, 100, 100])
    b.append({'kind': 'chart', 'rows': rows, 'alpha': candidate['alpha']})
    paragraph(b, '图：每组内比较化学基线与候选，横轴为MAE（越低越好）。相同颜色不代表不同处理规则的目标可直接比较。', 'note')
    summary = sections['diagnostic']['topography']['summary']['policies']
    table(b, ['候选相对化学基线', '改善纹理组', '变差纹理组'], [
        [POLICIES[key], str(summary[key]['methods']['current_candidate']['better_groups']), str(summary[key]['methods']['current_candidate']['worse_groups'])] for key in POLICIES
    ], [281, 105, 105])
    paragraph(b, '总体误差更高并不意味着每个纹理组都更差。该诊断未计算显著性或证明因果；原模型曾混淆比较对象，相关原文及操作员核对保存在附带JSON中。', 'note')

    b = chapter('管线研读与暂停依据')
    ex = pipeline['execution']
    paragraph(b, f"模型：{ex['model']}。本段预留{ex['requests_reserved']}/{ex['max_requests']}次请求，{ex['applied_calls']}项行动有效。研究状态：{pipeline['study_status']}。读取配置不代表已运行管线。")
    table(b, ['引用', '保存模块', '原文行', '配置状态'], [
        [m['alias'], m['module'], f"{m['line_start']}–{m['line_end']}", '启用' if m['enabled'] else '禁用'] for m in pipeline['read_modules']
    ], [45, 305, 75, 66])
    for action in pipeline['actions']:
        if action['action'] in {'pause', 'stop'}:
            paragraph(b, '模型暂停理由（原文，未科学审定）', 'subheading')
            paragraph(b, action['reason'], 'quote')
    paragraph(b, pipeline.get('operator_note', {}).get('text', ''), 'note')
    old = sections['source_continuation']['budget']
    paragraph(b, f"早期资料评议另有{old['total_reserved']}/{old['max_requests']}次请求已预留，其中旧未知{old['old_unknown_reserved']}次仍保留。该历史不因后续新资料任务而清零，也没有被本报告重新发送。", 'note')

    b = chapter('工作簿评议：模型原答')
    ex = tabular['execution']
    paragraph(b, f"模型实际读取{len(tabular['read_aliases'])}个片段；{ex['requests_reserved']}/{ex['max_requests']}次请求，{ex['applied_calls']}项行动有效、{ex['invalid_calls']}次未应用。下列回答通过格式检查，但尚未科学审定。")
    for answer in tabular['answers']:
        paragraph(b, QUESTIONS.get(answer['question_id'], answer['question_id']), 'subheading')
        paragraph(b, f"状态：{answer['status']}；引用：{', '.join(answer['evidence_ids'])}", 'note')
        paragraph(b, answer['answer'], 'quote')
    paragraph(b, '请连同下一页的操作员核对阅读。原答保留其局限，没有用人工修正覆盖为“模型自我修正”。', 'note')

    b = chapter('人工核对与单元格出处')
    for note in tabular.get('operator_notes', []):
        paragraph(b, note['text'], 'note')
    selections = data['sources']['prepared_selections']
    aliases = []
    for alias in tabular['alias_map']:
        matches = [s for s in selections if alias['chunk_id'] in s['chunk_ids']]
        locator = '; '.join(s['original_locator']['value'] for s in matches) or alias['locator']['value']
        aliases.append([alias['alias'], locator, f"{alias['start_char']}–{alias['end_char']}"])
    table(b, ['引用', '原文件选区 / 物理行', '派生文本字符区间'], aliases, [45, 291, 155])
    paragraph(b, '字符区间针对派生JSON，不是原工作簿文件的字节偏移。每个引用的完整原文、派生文件SHA、原文件SHA和定位均在research-dossier.json中保留。', 'note')
    paragraph(b, '这里的数值对应只能支持指定坐标的算术核对，不能推出作者采用了何种公式，也不能仅凭“红通道”或列名认定ALP终点。')

    b = chapter('下一步取证与研究决策')
    paragraph(b, task['title'], 'lead')
    paragraph(b, '任务由模型选择；交付模板来自宿主。记录仍在等待外部材料，本报告不把任务选择当成实际取证完成。')
    paragraph(b, '需要交回的材料', 'subheading')
    for value in task['deliverables']: paragraph(b, value)
    paragraph(b, '接收与判断标准', 'subheading')
    for value in task['acceptance']: paragraph(b, value)
    paragraph(b, '从这些原始来源开始', 'subheading')
    for url in task['source_urls']: paragraph(b, url, 'url')
    paragraph(b, '收到新材料后，先登记来源与准确坐标，再决定是否具备继续研究条件。只找到部分内容时，提交部分证据并保留未解决问题；不凭空补齐映射，也不为了得到一份完整回答重复耗尽同一资料预算。')
    for text in data['limitations']: paragraph(b, text, 'note')

    b = chapter('来源与版本索引')
    paragraph(b, '下面的哈希用来定位本报告所依据的封存版本；它们证明内容身份，不证明科学结论。完整行动、原文与来源记录见同目录JSON。', 'note')
    origin = data['sources'].get('pipeline_origin') or {}
    if origin:
        paragraph(b, f"管线原件：{origin.get('project_file', '')}")
        paragraph(b, origin.get('source_url', ''), 'url')
        paragraph(b, f"HDF5定位：{origin.get('hdf5_data_path', '')}", 'note')
    for source in data['sources']['baseline_manifest']:
        paragraph(b, f"{source['file']}  SHA256: {source['sha256']}", 'hash')
    paragraph(b, '本报告与封存来源', 'subheading')
    paragraph(b, '报告数据：' + data['snapshot_sha256'], 'hash')
    paragraph(b, '工作台清单：' + data['bundle_manifest_sha256'], 'hash')
    for name, digest in data['source_snapshots'].items():
        paragraph(b, name.removesuffix('_snapshot_sha256') + ': ' + str(digest), 'hash')
    return output


def render_markdown(chapters):
    lines = ['# P02 研究证据报告', '', '公开材料—细胞案例 · 封存记录汇总', '']
    def cell(value): return str(value).replace('|', '\\|').replace('\n', '<br>')
    for chapter in chapters:
        lines.extend(['## ' + chapter['title'], ''])
        for block in chapter['blocks']:
            kind = block['kind']
            if kind == 'table':
                lines.append('| ' + ' | '.join(map(cell, block['headings'])) + ' |')
                lines.append('| ' + ' | '.join('---' for _ in block['headings']) + ' |')
                lines.extend('| ' + ' | '.join(map(cell, row)) + ' |' for row in block['rows'])
            elif kind == 'chart': continue
            elif kind == 'quote': lines.extend('> ' + line for line in block['text'].splitlines())
            elif kind == 'subheading': lines.append('### ' + block['text'])
            else: lines.append(block['text'])
            lines.append('')
    return '\n'.join(lines)


def render_pdf(chapters, target):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import Paragraph, Table, TableStyle, Spacer, PageBreak, SimpleDocTemplate
    from reportlab.graphics.shapes import Drawing, Rect, String, Line
    font = _font_name(); ink = colors.HexColor('#203a40'); teal = colors.HexColor('#357b72')
    body = ParagraphStyle('body', fontName=font, fontSize=10, leading=15, spaceAfter=9, textColor=ink, wordWrap='CJK')
    styles = {'paragraph': body,
        'lead': ParagraphStyle('lead', parent=body, fontSize=13, leading=20, spaceAfter=16),
        'subheading': ParagraphStyle('sub', parent=body, fontSize=12, leading=19, spaceBefore=7, spaceAfter=8, textColor=teal),
        'note': ParagraphStyle('note', parent=body, fontSize=9, leading=14, textColor=colors.HexColor('#536569')),
        'quote': ParagraphStyle('quote', parent=body, fontSize=10, leading=15, backColor=colors.HexColor('#f1f5f3'), borderPadding=8, spaceBefore=5, spaceAfter=14),
        'hash': ParagraphStyle('hash', parent=body, fontSize=8, leading=12, spaceAfter=7),
        'url': ParagraphStyle('url', parent=body, fontSize=9, leading=14, textColor=teal),
        'cell': ParagraphStyle('cell', parent=body, fontSize=9, leading=13, spaceAfter=0)}
    title = ParagraphStyle('title', parent=body, fontSize=22, leading=30, spaceAfter=20)
    def p(text, kind='paragraph'):
        safe = escape(str(text)).replace('\n', '<br/>')
        if kind == 'url' and str(text).startswith('https://'):
            safe = '<link href="' + escape(str(text), {'"': '&quot;'}) + '">' + safe + '</link>'
        return Paragraph(safe, styles.get(kind, body))
    story = []
    for number, chapter in enumerate(chapters, 1):
        if number > 1: story.append(PageBreak())
        story.extend([p(f'P02  /  RESEARCH RECORD  /  {number:02d}', 'note'), Paragraph(escape(chapter['title']), title)])
        for block in chapter['blocks']:
            kind = block['kind']
            if kind == 'table':
                rows = [[p(c, 'cell') for c in row] for row in [block['headings'], *block['rows']]]
                table = Table(rows, colWidths=block.get('widths'), repeatRows=1, hAlign='LEFT')
                table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dcebe5')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#f5f7f5'),colors.white]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,0),.5,colors.HexColor('#c6d9d1'))]))
                story.extend([table, Spacer(1,12)])
            elif kind == 'chart':
                drawing = Drawing(491, 205); chart_rows=block['rows']; xmax=max(max(r['mae'], r['chemistry_mae']) for r in chart_rows)*1.2
                for idx, r in enumerate(chart_rows):
                    y=164-idx*38
                    drawing.add(String(0,y+3,POLICIES[r['policy']],fontName=font,fontSize=9,fillColor=ink))
                    for dy,value,color in [(2,r['chemistry_mae'],teal),(-11,r['mae'],colors.HexColor('#b47852'))]:
                        drawing.add(Rect(132,y+dy,value/xmax*300,9,fillColor=color,strokeColor=None))
                        drawing.add(String(137+value/xmax*300,y+dy,f'{value:.4f}',fontName=font,fontSize=8,fillColor=ink))
                drawing.add(Line(132,32,432,32,strokeColor=colors.HexColor('#c5cecb')))
                for i in range(4):
                    value=xmax*i/3;drawing.add(String(132+i*100,18,f'{value:.2f}',fontName=font,fontSize=8,fillColor=ink))
                drawing.add(String(132,194,'化学基线',fontName=font,fontSize=9,fillColor=teal))
                drawing.add(String(242,194,f"候选 alpha={block['alpha']}",fontName=font,fontSize=9,fillColor=colors.HexColor('#b47852')))
                story.append(drawing)
            elif block['text']: story.append(p(block['text'], kind))
    def page(canvas, doc):
        canvas.setFillColor(teal); canvas.rect(46,A4[1]-34,28,3,fill=1,stroke=0)
        canvas.setFont(font,8);canvas.setFillColor(colors.HexColor('#536569'))
        canvas.drawString(46,27,'P02 · 研究证据报告 | 既有记录汇总，科学结论待核验')
        canvas.drawRightString(A4[0]-46,27,str(doc.page))
    document=SimpleDocTemplate(str(target),pagesize=A4,leftMargin=46,rightMargin=46,topMargin=49,bottomMargin=47,title='P02 研究证据报告',author='Auto Research 团队')
    document.build(story,onFirstPage=page,onLaterPages=page)


def export_dossier(bundle, output):
    root=Path(bundle).absolute();target=Path(output).absolute()
    for path in (root,target):
        if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in (path,*path.parents)):
            raise ResearchError('DOSSIER_PATH_INVALID','Plain local paths required.')
    if target.exists() or target==root or target.is_relative_to(root) or root.is_relative_to(target):
        raise ResearchError('DOSSIER_PATH_INVALID','Fresh output outside the sealed bundle required.')
    data=dossier_data(root);chapters=report_sections(data)
    target.mkdir(parents=True,exist_ok=False)
    (target/'research-dossier.json').write_text(canonical(data)+'\n',encoding='utf-8')
    (target/'research-dossier.md').write_text(render_markdown(chapters),encoding='utf-8')
    render_pdf(chapters,target/'research-dossier.pdf')
    files={p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in target.iterdir()}
    result={'schema_version':'p02-research-dossier-export-v1','snapshot_sha256':data['snapshot_sha256'],'bundle_manifest_sha256':data['bundle_manifest_sha256'],'files':files,'model_calls':0,'new_fits':0}
    (target/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'directory':str(target),**result}
