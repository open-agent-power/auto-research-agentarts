"""Readable paper and an allowlisted public numerical reproduction attachment."""
import csv
import hashlib
import io
import json
from pathlib import Path
import platform
import zipfile
from xml.sax.saxutils import escape

from .c01_research import C01Research
from .contracts import canonical, fingerprint, ResearchError
from .paper_export import _font_name


def _abstract(research):
    fits = research['fits']
    steps = ['资料检索与配方执行']
    if any(item['action'] == 'inspect_dataset' for item in research['decisions']):
        steps.append('冻结数值与来源检查')
    if any(item['action'] == 'read_source' for item in research['decisions']):
        steps.append('固定来源分段阅读')
    if any(item['action'] == 'review_evidence' and item['parameters']['field'] != 'control_rationale' for item in research['decisions']):
        steps.append('资料条件核验（模型解读待复核）')
    if any(item['action'] == 'review_evidence' and item['parameters']['field'] == 'control_rationale' for item in research['decisions']):
        steps.append('控制理由评议（模型判断待复核）')
    if any(item['action'] == 'residuals' for item in research['diagnostics']):
        steps.append('误差诊断')
    if any(item['action'] == 'correlation' for item in research['diagnostics']):
        steps.append('关联稳定性检查')
    if any(a['recipe']['features'] == b['recipe']['features'] and a['recipe']['alpha'] != b['recipe']['alpha']
           for i, a in enumerate(fits) for b in fits[i+1:]):
        steps.append('收缩强度对照')
    if len({tuple(fit['recipe']['features']) for fit in fits}) > 1:
        steps.append('特征组比较')
    return ('本研究检查材料属性是否支持对体外细胞响应的可复算预测。账本记录了' + '、'.join(steps)
            + '。每项配方保留假设、预期结果、实际逐折预测和基线比较，失败与越界预测不被隐藏。'
              '报告依据已执行动作说明下一步决定；计算次数与报告长度不能代替研究质量。')


def public_record(state):
    """Keep research evidence and citation locations; do not redistribute paper excerpts."""
    if fingerprint({key: value for key, value in state.items() if key != 'observation_sha256'}) != state['observation_sha256']:
        raise ResearchError('INVALID_EVIDENCE', 'study observation fingerprint mismatch')
    fits, diagnostics, decisions = [], [], []
    for action in state['actions']:
        decisions.append({key: action[key] for key in
                          ('id', 'ordinal', 'action', 'request_id', 'observation_sha256', 'reason',
                           'parameters', 'source_citation_ids', 'evidence_action_ids', 'result_sha256')})
        common = {key: action[key] for key in ('id', 'reason', 'source_citation_ids', 'evidence_action_ids')}
        if action['action'] == 'fit':
            fits.append({**common, **{key: action['result'][key] for key in ('recipe', 'summary', 'predictions')}})
        elif action['action'] in {'residuals', 'correlation'}:
            diagnostics.append({**common, **{key: action[key] for key in ('action', 'parameters', 'result', 'result_sha256')}})
    return {'schema_version': 'c01-public-research-v1', 'goal': state['goal'], 'status': state['status'],
            'origin_observation_sha256': state['observation_sha256'],
            **{key: state[key] for key in ('archive_sha256', 'corpus_sha256', 'scientific_status', 'decision_origin')},
            'fits': fits, 'diagnostics': diagnostics, 'decisions': decisions,
            'references': [{key: citation[key] for key in ('citation_id', 'source', 'location')} for citation in state['citations']]}


def _label(fit, ordinal, *, chinese=False):
    features = set(fit['recipe']['features'])
    if len(features) == 4:
        group = '四特征' if chinese else 'All features'
    elif features == {'ecm_gpa', 'yield_mpa'}:
        group = '力学组' if chinese else 'Mechanical'
    elif features == {'water_contact_angle_deg', 'sfe_owrk_total_mn_m'}:
        group = '表面组' if chinese else 'Surface'
    else:
        group = f'{len(features)} features'
    return f"C{ordinal} {group}, alpha={fit['recipe']['alpha']:g}"


def _figures(research):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    import numpy as np
    colors = ['#a85d4c', '#527d74', '#ab8a52', '#7b739b', '#538caa', '#7b8765']
    fits = research['fits']
    labels = ['Seeding (24h)', 'DNA (as reported)', 'ALP (as reported)', 'ARS field (date conflict)']
    with plt.rc_context({'font.family': 'DejaVu Sans', 'font.size': 10, 'svg.hashsalt': 'c01-agent-evidence-v1'}):
        fig, ax = plt.subplots(figsize=(8.2, 4.3), layout='constrained')
        x, width = np.arange(4), .75 / len(fits)
        for i, fit in enumerate(fits):
            ratios = [metric['mae'] / metric['baseline_mae'] for metric in fit['summary']['metrics']]
            ax.bar(x + (i-(len(fits)-1)/2)*width, ratios, width=width*.92,
                   color=colors[i], label=_label(fit, i+1))
        ax.axhline(1, color='#394952', linestyle='--', linewidth=1, label='Fold-mean baseline = 1')
        ax.set_xticks(x, labels)
        ax.set_ylabel('MAE / fold-mean baseline MAE (lower is better)')
        ax.set_title('Eight alloy aggregates; reused leave-one-alloy-out evaluation', fontsize=11, pad=13)
        ax.grid(axis='y', alpha=.14)
        ax.set_axisbelow(True)
        ax.spines[['top', 'right']].set_visible(False)
        ax.legend(loc='upper center', bbox_to_anchor=(.5, -.12), ncol=2, frameon=False, fontsize=8.3)
        result = {}
        for suffix in ('png', 'svg'):
            stream = io.BytesIO()
            fig.savefig(stream, format=suffix, dpi=200, metadata={'Date': None} if suffix == 'svg' else {})
            result['figures/comparison.' + suffix] = stream.getvalue()
        plt.close(fig)
    return result


def _paper(research, reproduction, figure):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak, CondPageBreak, Image
    font = _font_name()
    body = ParagraphStyle('c01-body', fontName=font, fontSize=10, leading=16, spaceAfter=8, wordWrap='CJK')
    title = ParagraphStyle('c01-title', parent=body, fontSize=22, leading=31, spaceAfter=16)
    heading = ParagraphStyle('c01-heading', parent=body, fontSize=13, leading=21, spaceBefore=9, spaceAfter=8)
    cell = ParagraphStyle('c01-cell', parent=body, fontSize=8.5, leading=13, spaceAfter=0)
    small = ParagraphStyle('c01-small', parent=body, fontSize=8, leading=12, textColor=colors.HexColor('#52636b'))

    def p(value, style=body):
        display = str(value).translate(str.maketrans({'\u2011': '-', '\u2013': '-', '\u2014': '-', '\u2212': '-'}))
        return Paragraph(escape(display).replace('\n', '<br/>'), style)

    def table(rows, widths):
        result = Table([[p(value, cell) for value in row] for row in rows], colWidths=[value*mm for value in widths], repeatRows=1)
        result.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e9efeb')),
                                   ('LINEBELOW', (0, 0), (-1, 0), .7, colors.HexColor('#9db4a5')),
                                   ('LINEBELOW', (0, 1), (-1, -1), .25, colors.HexColor('#d9dfdc')),
                                   ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                   ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
        return result

    fits, decisions = research['fits'], research['decisions']
    story = [p('材料属性与体外细胞响应', title), p('证据驱动的持续研究记录 / C01', heading),
             p(research['goal']),
             p(f"公开历史数据：8个合金汇总样本 | {len(fits)}项配方 | {len(fits)*32}次逐折Ridge拟合 | {len(decisions)}项Agent动作 | 状态：{research['status']}", small),
             p('摘要', heading),
             p(_abstract(research)),
             p('1. 数据与方法', heading),
             p('输入为C01原包中的8个TiNbZrSnTa合金汇总记录。四项允许特征是弹性模量、屈服强度、水接触角和OWRK总表面自由能。每次留出一个完整合金，在另7个合金上拟合StandardScaler与Ridge（SVD求解），同时用这7个目标的均值作为基线。四个终点分开评价，不平均不同单位的误差。'),
             p('数据DOI：10.17632/tt7gwkpck8.1。来源及许可声明保留在附件；原包与论文许可分别核对。这里使用公开历史数据，没有新增细胞实验。'),
             p('数据解释边界', heading),
             p('细胞为MC3T3-E1体外体系。独立培养批次、标签星号和部分量纲／换算仍未充分核实。项目后续方法核对笔记记载ALP按DNA归一化；不能把原始审计中“归一化未确认”的旧措辞当作最新结论。DNA原表近似细胞数与论文浓度需区分，ARS是染色替代指标，21/28天冲突未裁定。表中沿用原始字段数值，不将它们解释为临床疗效。'),
             p('本报告汇总提交到研究账本的决策与本地计算，不单独认证选择动作的模型身份。若由模型驱动，原生请求、响应与额度记录保存在独立控制器账本；本附件不认证AgentArts接入或LLM权重训练。Ridge系数拟合确实执行。', small),
             CondPageBreak(130*mm), p('2. 计算结果', heading),
             p('下图以各终点逐折均值基线MAE为1，柱越低越好。同8个合金反复参与了配方调整，因此它是探索性比较，不能充当独立验证。'),
             Image(io.BytesIO(figure), width=166*mm, height=87*mm)]
    metric_rows = [['配方', '接种率MAE', 'DNA原表MAE', 'ALP原表MAE', 'ARS字段MAE']]
    metric_rows.append(['逐折均值'] + [f"{metric['baseline_mae']:.6g}" for metric in fits[0]['summary']['metrics']])
    metric_rows += [[f'C{i+1}'] + [f"{metric['mae']:.6g}" for metric in fit['summary']['metrics']] for i, fit in enumerate(fits)]
    story += [Spacer(1, 4*mm), table(metric_rows, [26, 35, 35, 35, 35])]
    for i, fit in enumerate(fits):
        story.append(p(_label(fit, i+1, chinese=True), small))
    r2_rows = [['配方 / R2', '接种率', 'DNA原表', 'ALP原表', 'ARS字段']]
    r2_rows += [[f'C{i+1}'] + [f"{metric['r2']:.4f}" for metric in fit['summary']['metrics']] for i, fit in enumerate(fits)]
    story += [table(r2_rows, [26, 35, 35, 35, 35]),
              p('R2对整体样本均值的描述性参照，与每折可实际使用的7合金均值基线不同；优于逐折基线也不等于通过独立检验。候选晋升没有独立评估，附件保留完整逐折预测。', small),
              PageBreak(), p('3. Agent如何推进', heading)]
    action_names = {'search': '查找与复核资料', 'read_source': '读取固定来源的原片段', 'inspect_dataset': '检查冻结数值与单元格来源', 'review_evidence': '记录资料判断（待科学复核）',
                    'propose_control': '提出待评议的控制决定',
                    'fit': '执行可检验配方', 'residuals': '检查误差集中度', 'correlation': '检查关联稳定性'}
    for decision in decisions:
        if decision['action'] in {'stop', 'pause'}:
            continue
        story += [p(f"{decision['ordinal']:02d}  {action_names[decision['action']]}", heading), p(decision['reason'])]
        if decision['action'] == 'propose_control':
            story += [p('提议：' + decision['parameters']['decision'] + '。此动作只保存原理由，未暂停或停止研究；评议及其后的选择均需保留证据，不能当作科学认证。', small)]
        if decision['action'] == 'inspect_dataset':
            story += [p('读取的是本轮执行器冻结的输入。数值、字段摘要与原始单元格来源保存在原账本；此动作不更改数据，不认定单位、样本映射或科研含义。附件验证器复算所附数值结果，不认证此读取过程。', small)]
        if decision['action'] == 'read_source':
            value = decision['parameters']
            story += [p(f"文档：{value['document_id']}；从零基片段{value['start_chunk']}读取最多{value['count']}段。原片段在原账本保存，本附件不分发原文；窗口不代表全文已读。", small)]
        if decision['action'] == 'review_evidence':
            value = decision['parameters']
            story += [p(f"字段：{value['field']}；模型判断：{value['status']}（原文关联已核，含义未作科学认证）", small),
                      p(value['question']), p(value['finding']), p('下一项核验：' + value['next_check'])]
    story += [CondPageBreak(100*mm), p('4. 研究决定与适用条件', heading)]
    for decision in decisions:
        if decision['action'] in {'stop', 'pause'}:
            story += [p('模型控制决定（理由待科学复核）：' + decision['action']), p(decision['reason'])]
    story += [p('可积累的研究记忆', heading),
              p('这些记录只适用于本包指纹绑定的数据、特征、协议及已试配方。新项目应先检查字段定义、批次与材料条件是否可比；不能将当前误差、相关方向或消融排序跨数据集复用为规律。旧审计、检索结果和后续核对须保留版本与冲突，不能覆盖成无条件的“知识”。'),
              p('继续研究需要什么', heading),
              p('优先核实样本标签、独立重复、DNA/ALP/ARS测量定义与时间点，再选择兼容独立数据、预先固定研究问题和评估。其他论文的自适应检验保证不能自动套用于本轮；这里没有建立这类统计保证。'),
              p('计算可复现与科学有效性分别判断。附件验证器独立复算保存配方，不调用模型、不联网、不执行参考仓库。匹配只能证明所附输入和方法能重算结果。'),
              PageBreak(), p('5. 引用与复现', heading),
              p('主要数据：Mendeley Data v1，DOI 10.17632/tt7gwkpck8.1；关联论文：DOI 10.1016/j.bioadv.2023.213572。来源页列明作者与版本；本报告未重新完成独立实验或全文同行评议。'),
              p('本轮实际采用的检索依据如下。外部论文只保留引用位置与文件指纹，附件不分发论文全文或检索摘录。', small)]
    used = {citation for decision in decisions for citation in decision['source_citation_ids']}
    for reference in research['references']:
        if reference['citation_id'] not in used:
            continue
        source = reference['source']
        location = reference['location']
        position = 'PDF第'+str(location['page'])+'页' if 'page' in location else f"第{location['line_start']}-{location['line_end']}行"
        story += [p(source['title'] + ' / ' + position, heading), p(source['path'], small),
                  p(source.get('source_url') or '项目派生核对笔记；原始来源见数据DOI与笔记引用。', small),
                  p('SHA256: ' + source['sha256'], small)]
    story += [p('复现步骤', heading),
              p('将reproduction.zip解压到新目录，使用已安装NumPy与scikit-learn的Python运行 python verify_results.py。环境版本见environment.json；验证器不导入包内source或访问网络。README说明验证范围、失败处理与数据出处。'),
              p('原研究观察指纹：' + research['origin_observation_sha256'], small),
              p('原始输入包指纹：' + research['archive_sha256'], small),
              p('计算身份：' + reproduction['analysis_code_sha256'], small)]
    stream = io.BytesIO()

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#dce5df'))
        canvas.line(22*mm, 16*mm, 188*mm, 16*mm)
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor('#62736a'))
        canvas.drawString(22*mm, 11*mm, 'C01 / 公开数据探索 / 非独立验证')
        canvas.drawRightString(188*mm, 11*mm, str(document.page))
        canvas.restoreState()

    SimpleDocTemplate(stream, pagesize=(210*mm, 297*mm), leftMargin=22*mm, rightMargin=22*mm,
                      topMargin=20*mm, bottomMargin=23*mm, title='C01 evidence-driven research record',
                      author='Auto Research project team').build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()


def export_study(workspace, output):
    from .c01_research_verifier import validate_record
    exported = C01Research(workspace).export()
    research, reproduction = public_record(exported['state']), exported['reproduction']
    validation = validate_record(research, reproduction)
    if not research['fits']:
        raise ResearchError('NO_RESULTS', 'paper requires at least one executed fit')
    # Freeze the actual source bytes before rendering; never reread a newer version into this package.
    source_names = ('c01.py', 'c01_loop.py', 'knowledge.py', 'c01_research.py', 'contracts.py')
    sources = {'source/' + name: Path(__file__).with_name(name).read_bytes() for name in source_names}
    identity = hashlib.sha256(b''.join(sources['source/' + name] for name in source_names[:4])).hexdigest()
    if identity != reproduction['analysis_code_sha256']:
        raise ResearchError('CODE_CHANGED', 'bundled analysis source differs from the frozen research')
    output = Path(output).absolute()
    if output.exists():
        raise ResearchError('ALREADY_EXISTS', 'preserve old reports; output directory must be new')
    for parent in (output, *output.parents):
        if parent.is_symlink() or getattr(parent, 'is_junction', lambda: False)():
            raise ResearchError('UNSAFE_PATH', 'report output cannot cross redirected paths')
    figures = _figures(research)
    files = {'research.json': (json.dumps(research, ensure_ascii=False, indent=2)+'\n').encode(),
             'reproduction.json': (json.dumps(reproduction, ensure_ascii=False, indent=2)+'\n').encode(), **figures}
    rows = io.StringIO(newline='')
    writer = csv.writer(rows)
    writer.writerow(['candidate_id', 'label', 'alpha', 'features', 'target', 'mae', 'baseline_mae', 'mae_ratio', 'r2'])
    for i, fit in enumerate(research['fits']):
        for metric in fit['summary']['metrics']:
            writer.writerow([fit['id'], _label(fit, i+1), fit['recipe']['alpha'], ';'.join(fit['recipe']['features']),
                             metric['target'], metric['mae'], metric['baseline_mae'], metric['mae']/metric['baseline_mae'], metric['r2']])
    files['comparison.csv'] = rows.getvalue().encode('utf-8')
    files['paper.pdf'] = _paper(research, reproduction, figures['figures/comparison.png'])
    import numpy, sklearn, reportlab
    files['environment.json'] = canonical({'python': platform.python_version(), 'numpy': numpy.__version__,
                                           'scikit_learn': sklearn.__version__, 'reportlab': reportlab.Version}).encode()
    files.update(sources)
    files['verify_results.py'] = Path(__file__).with_name('c01_research_verifier.py').read_bytes()
    files['README.md'] = ("# C01公开数值研究：复现附件\n\n"
        "在新目录解压，使用已安装NumPy/scikit-learn的Python运行 `python verify_results.py`。验证器独立计算每配方32折预测和指标，不联网，不导入source中的代码，不需要模型密钥。environment.json记录本次版本。\n\n"
        "数据来源DOI 10.17632/tt7gwkpck8.1，关联论文DOI 10.1016/j.bioadv.2023.213572；数据版本、原包SHA和来源单元格在reproduction.json。原始数值按公开输入包整理，未执行Excel公式。许可声明随source保留，论文许可单独核对；附件不包含论文全文、检索摘录或参考仓库。\n\n"
        "research.json为分发投影，保留实验、决策、引用位置及原研究观察锚点；因为移除了外部摘录，不能从此投影重建原观察哈希。package-manifest.json仅校验传输完整性，不是签名或科学认证。\n\n"
        "同8个合金重复LOO用于探索；不能据此宣称独立验证、最优材料、因果或临床效果。本包不包含或认证规划器原生HTTP身份与云调用记录；模型驱动过程需另查独立控制器账本。资料判断属于待复核的模型解读，数值验证器不核验原文含义；Ridge拟合不是LLM权重训练。\n").encode('utf-8')
    files['package-manifest.json'] = canonical({'schema_version': 'c01-reproduction-package-v1',
                                               'files': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}).encode()
    output.mkdir(parents=True)
    for name, data in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    archive_path = output / 'reproduction.zip'
    with zipfile.ZipFile(archive_path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    # Extra authoring evidence is outside the allowlisted reproduction payload.
    (output / 'authoring-validation.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'output': str(output), 'paper': str(output/'paper.pdf'), 'reproduction': str(archive_path),
            'recipes': len(research['fits']), 'scientific_validation': False}
