"""Independent P02 iteration report and arithmetic reproduction artifacts.

No inference or fitting. Historical publication exporters remain unchanged.
"""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import zipfile

from .chemotopo_delivery import _safe
from .contracts import ResearchError, canonical
from .paper_export import _font_name, _markup
from .chemotopo_experiment_evidence import _safe_file, attachment
from .chemotopo_iteration_evidence import checked_files

ARTIFACT_LIMITS={'report.pdf':15_000_000,'comparison.png':5_000_000,'comparison.svg':3_000_000,
                 'iteration.json':3_000_000,'reproduction.zip':30_000_000}
POLICIES=('positive_equal_batch','positive_equal_section','recorded_equal_batch','recorded_equal_section')
LABELS=('B1 正计数／批次等权','B2 正计数／分区等权','A1 保留零值／批次等权','A2 保留零值／分区等权')


def _json(value):
    return (canonical(value)+'\n').encode('utf-8')


def _comparison_notes(view):
    notes=[]
    for c in view['comparisons']:
        total=len(c['policies'])
        improved=[p['policy'] for p in c['policies'] if p['delta_vs_alpha1']<0]
        worse=[p['policy'] for p in c['policies'] if p['delta_vs_alpha1']>0]
        additive=sum(p['delta_vs_additive']<0 for p in c['policies'])
        chemistry=sum(p['delta_vs_chemistry']<0 for p in c['policies'])
        notes.append(f"alpha={c['alpha']:g}：相对α1改善{len(improved)}/{total}规则、变差{len(worse)}/{total}；优于R54加性{additive}/{total}、优于化学{chemistry}/{total}。")
        if improved:notes.append('相对α1改善的规则：'+', '.join(improved)+'；不能概括为全部未改善。')
        if improved and worse:notes.append('该候选结果混合，不能只挑改善规则宣布整体成功。')
    if not notes:notes.append('本轮没有已完成的候选拟合，不能填写新增候选成绩或推断未测alpha的效果。')
    return notes


def read_iteration_artifacts(directory,view):
    """Return frozen bytes only when all five files bind the exact public view."""
    root=Path(directory).absolute()
    manifest=json.loads(_safe_file(root/'manifest.json',100_000))
    if (manifest.get('schema_version')!='p02-iteration-artifacts-v1'
            or manifest.get('snapshot_sha256')!=view['snapshot_sha256']
            or set(manifest.get('files',{}))!=set(ARTIFACT_LIMITS)):
        raise ResearchError('EVIDENCE_CHANGED','Iteration artifacts belong to a different snapshot or file set.')
    files={}
    for name,limit in ARTIFACT_LIMITS.items():
        raw=_safe_file(root/name,limit)
        if manifest['files'][name]!={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}:
            raise ResearchError('EVIDENCE_CHANGED','Iteration artifact bytes changed.')
        files[name]=raw
    if json.loads(files['iteration.json'])!=view:raise ResearchError('EVIDENCE_CHANGED','Iteration JSON does not match the current view.')
    return files


def _charts(view):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    prior=view['prior_evidence']['metrics'];comparisons=view['comparisons']
    fig,axes=plt.subplots(1,2,figsize=(11,4.2),layout='constrained')
    series=[('Chemistry',[prior[p]['chemistry'] for p in POLICIES],'#526e60'),
            ('Additive',[prior[p]['additive'] for p in POLICIES],'#99af8e'),
            ('Interaction a=1',[prior[p]['interaction'] for p in POLICIES],'#c3ad78')]
    palette=('#438ca0','#d58b45','#6f92c2','#c55d91')
    other_alphas=[]
    for comparison in comparisons:
        by_policy={r['policy']:r for r in comparison['policies']}
        alpha=comparison['alpha']
        if alpha not in (10,100) and alpha not in other_alphas:other_alphas.append(alpha)
        color='#9b83b2' if alpha==10 else '#be7b70' if alpha==100 else palette[other_alphas.index(alpha)%len(palette)]
        series.append((f"Interaction a={comparison['alpha']:g}",
                       [{'pooled_mae':by_policy[p]['mae'],'pooled_spearman_midrank':by_policy[p]['spearman']} for p in POLICIES],
                       color))
    width=.8/len(series)
    for ax,key,title in zip(axes,('pooled_mae','pooled_spearman_midrank'),
                            ('Primary MAE: lower is better','Secondary Spearman: higher is better')):
        for i,(label,values,color) in enumerate(series):
            ax.bar([n-.4+width*(i+.5) for n in range(4)],
                   [float('nan') if v[key] is None else v[key] for v in values],width=width,label=label,color=color)
        ax.set_xticks(range(4),['B1','B2','A1','A2']);ax.set_title(title,fontsize=10)
        ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True);ax.spines[['top','right']].set_visible(False)
    fig.legend(*axes[0].get_legend_handles_labels(),loc='outside lower center',ncol=3,frameon=False,fontsize=8)
    result={}
    try:
        for suffix in ('png','svg'):
            stream=BytesIO();fig.savefig(stream,format=suffix,dpi=170,metadata={'Creator':'Auto Research P02 iteration'})
            result['comparison.'+suffix]=stream.getvalue()
    finally:plt.close(fig)
    return result


def _report(view,chart):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle
    font=_font_name();ink=colors.HexColor('#294337')
    body=ParagraphStyle('I62Body',fontName=font,fontSize=10,leading=16,spaceAfter=8,textColor=ink,wordWrap='CJK')
    small=ParagraphStyle('I62Small',parent=body,fontSize=8.5,leading=13,spaceAfter=6)
    title=ParagraphStyle('I62Title',parent=body,fontSize=23,leading=32,spaceAfter=16)
    heading=ParagraphStyle('I62Heading',parent=body,fontSize=14,leading=22,spaceBefore=8,spaceAfter=9)
    p=lambda text,style=body,limit=1200:Paragraph(_markup(text,limit),style)
    x=view['execution'];prior=view['prior_evidence']['metrics'];comparisons=view['comparisons']
    protocol=view.get('protocol');configured=protocol is not None
    candidate_text='、'.join(f"{c['id']}(alpha={c['alpha']:g})" for c in protocol['candidates']) if configured else 'alpha10与alpha100'
    candidate_total=len(protocol['candidates']) if configured else 2
    story=[p('P02 数值迭代研究报告',title),p('受委托研究 · 原生工具选择 · 实际CPU拟合 · 科学解释仍有限',small),
           p('一、任务与实际执行',heading),p(f'研究目标由操作者设定。模型可在固定{candidate_text}工具范围内选择实验、暂停或停止；实际目标与已执行行动如下，不从工具是否存在推断它已经执行。'),
           p('研究目标原文：'+view['goal'],small,2000),
           p(f"真实模型：{x['model']}；原生请求{x['requests_reserved']}次，已提交{x['applied_calls']}项，无效{x['invalid_calls']}次。完成候选{x['completed_candidates']}个，本轮真实CPU拟合{x['completed_fits']}次，预算{x['max_fits']}次。"),
           p(f"本轮已完成{x['completed_fits']}次CPU拟合，与R54操作者420次、R59操作者140次分别计数；没有LLM权重训练。历史基线从已保存结果核对，没有重新拟合。")]
    if x.get('native_interface')=='compact-v1':
        story.append(p('紧凑原生接口中，模型选择候选／暂停／停止及理由；observation、来源与最新行动ID由宿主从已保存观察绑定，不表示模型主动引用来源或已经阅读证据。',small))
    for a in view['actions']:
        name={'fit_alpha10':'选择alpha10','fit_alpha100':'选择alpha100','stop':'停止','pause':'暂停'}.get(a['action'],a['action'])
        if a['action']=='run_candidate':name=f"选择{a['summary']['candidate_id']} (alpha={a['summary']['alpha']:g})"
        if a['action'] in ('fit_alpha10','fit_alpha100'):name+=f"，已完成{a['summary']['fit_count']}次CPU拟合"
        elif a['action']=='run_candidate':name+=f"，已完成{a['summary']['fit_count']}次CPU拟合"
        story.append(p(f"{a['ordinal']}. {name} · {'已绑定原生模型选择' if a.get('model_selected') else '行动记录'}",heading))
    if configured:story.append(p(f"协议候选共{candidate_total}项，已完成{x['completed_candidates']}项，尚未完成{candidate_total-x['completed_candidates']}项；累计请求{x['requests_reserved']}/{x['max_requests']}。候选、拟合与请求预算分别核对。",small))
    elif x['completed_candidates']==2:story.append(p('两个固定候选均已完成，预定候选范围已耗尽。',small))
    else:story.append(p(f"已完成{x['completed_candidates']}个候选；未完成候选不能标为已检验或耗尽。",small))
    story.extend([p('完整工件恢复只核对身份和数值，不重新拟合；模型请求、实验行动与完成工件分别核验。',small),PageBreak(),p('二、四规则主指标比较',title)])
    by_alpha={c['alpha']:{r['policy']:r for r in c['policies']} for c in comparisons}
    rows=[[p(t,small) for t in ['规则','化学','加性','交互α1',*[f'交互α{a:g}' for a in by_alpha]]]]
    for policy,label in zip(POLICIES,LABELS):
        vals=[prior[policy][r]['pooled_mae'] for r in ('chemistry','additive','interaction')]+[by_alpha[a][policy]['mae'] for a in by_alpha]
        rows.append([p(label,small)]+[p(f'{v:.6f}',small) for v in vals])
    cols=[47*mm]+[(127/(len(rows[0])-1))*mm]*(len(rows[0])-1)
    table=Table(rows,colWidths=cols);table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf2e8')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),.35,colors.HexColor('#dce5da')),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4)]));story.append(table)
    story.extend([Image(BytesIO(chart),width=174*mm,height=66.4*mm),p('B1/B2：仅正计数；A1/A2：保留原始有限零值。1为批次等权，2为分区等权。图中MAE为主指标，Spearman为次项；目标不同，不能跨处理规则挑优胜者。',small)])
    for note in _comparison_notes(view):story.append(p(note,small))
    story.extend([PageBreak(),p('三、模型理由与事实分开',title)])
    for a in view['actions']:
        story.extend([p(f"{a['ordinal']}. {a['action']} 原始显式理由（未验证节选）",heading),p(a['reason'],small,1100)])
    story.extend([p('事实核对',heading),p(view['interpretation_notice'],body,2000),
                  p('以上理由为原始显式记录，未经科学审定。请与逐规则数值事实核对；工具调用有效不保证理由正确，停止也不等于全部候选已检验，不能由此宣称科学策略正确或强化训练成功。'),
                  PageBreak(),p('四、来源、适用条件与复现',title),
                  p('870个四规则共同三批次组合，Topography=2…36整组留出35折；化学独热、训练折标准化10几何及全部交互，固定Ridge SVD。各alpha反复使用已看过的探索折，不是无偏最终盲测。'),
                  p('适用范围限已知化学、现有批次和已测同分区平坦对照。ALP通道、原导出映射及零对象规则仍未确认；没有独立生物或新实验室验证。交互与主效应冗余也影响Ridge有效惩罚，不以此归因生物机制。'),
                  p('公开来源',heading),p('作者数据：https://data.mendeley.com/datasets/57nrc49stj/1；数据DOI：10.17632/57nrc49stj.1。论文DOI：10.1016/j.biomaterials.2021.120740。',small),
                  p('复现包只包含固定数值工件、脱敏迭代投影与标准库verify.py；不含原始作者文件、数据库、原生响应、思维链、账号或浏览器信息。',small),
                  p(('在新目录解压后执行 python verify.py，核对allowlist与SHA，从inputs.json封存输入复算既有基线和候选的MAE、RMSE、Spearman及逐折均值，并核对目标、折分与协议绑定。' if configured else '在新目录解压后执行 python verify.py，核对allowlist与SHA，再独立核对R54／R59／候选之间的目标、折分、已有基线预测以及MAE、RMSE、Spearman和逐折均值。')+'0次重训，不要求下载数据。该核对证明包内数值一致性，不证明来源真实性或科学有效性。',small),
                  p('本报告为本机可追踪研究证据，不是已发表论文。操作者归档与模型remember分别计数；本报告不新增模型记忆。',small),
                  p('旧报告快照：'+view['baseline_publication_sha256'],small),p('本次迭代快照：'+view['snapshot_sha256'],small)])
    out=BytesIO();doc=SimpleDocTemplate(out,pagesize=A4,leftMargin=18*mm,rightMargin=18*mm,topMargin=18*mm,bottomMargin=18*mm,title='P02数值迭代研究报告',author='Auto Research')
    def footer(canvas,document):
        canvas.setFont(font,8);canvas.setFillColor(colors.HexColor('#607367'));canvas.drawString(18*mm,10*mm,'P02 · 数值代理值 / 有界模型选择 / 未获科学批准');canvas.drawRightString(192*mm,10*mm,str(document.page))
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()


VERIFY_SCRIPT=r'''"""Standalone arithmetic verification. Standard library only; never fits."""
import csv,hashlib,io,json,math,statistics
from pathlib import Path
root=Path(__file__).resolve().parent
manifest=json.loads((root/'package-manifest.json').read_text(encoding='utf-8'))
if {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}!=set(manifest['files'])|{'package-manifest.json'}:raise ValueError('missing or extra package files')
for name,meta in manifest['files'].items():
    path=root/name
    if Path(name).is_absolute() or '..' in Path(name).parts or path.is_symlink():raise ValueError('unsafe package path')
    raw=path.read_bytes()
    if len(raw)!=meta['bytes'] or hashlib.sha256(raw).hexdigest()!=meta['sha256']:raise ValueError('package hash mismatch: '+name)
def read(name):return json.loads((root/name).read_text(encoding='utf-8'))
def csvrows(name):
    with (root/name).open(encoding='utf-8',newline='') as stream:return list(csv.DictReader(stream))
def close(a,b):
    if (a is None)!=(b is None) or a is not None and not math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-12):raise ValueError('arithmetic mismatch')
def ranks(values):
    order=sorted(range(len(values)),key=values.__getitem__);out=[0.]*len(values);i=0
    while i<len(values):
        j=i+1
        while j<len(values) and values[order[i]]==values[order[j]]:j+=1
        for k in order[i:j]:out[k]=(i+1+j)/2
        i=j
    return out
def metrics(rows,prediction):
    y=[float(r['target']) for r in rows];pred=[float(r[prediction]) for r in rows]
    if not all(math.isfinite(v) for v in y+pred):raise ValueError('nonfinite value')
    errors=[abs(a-b) for a,b in zip(y,pred)];folds={}
    for row,e in zip(rows,errors):folds.setdefault(int(row['fold']),[]).append(e)
    a,b=ranks(y),ranks(pred)
    return {'pooled_mae':statistics.mean(errors),'pooled_rmse':math.sqrt(statistics.mean((a-b)**2 for a,b in zip(y,pred))),
            'pooled_spearman_midrank':statistics.correlation(a,b) if len(set(a))>1 and len(set(b))>1 else None,
            'macro_fold_mae':statistics.mean(statistics.mean(v) for v in folds.values())}
def key(row):return (int(row['topography']),int(row['chemistry']))
def indexed(rows):
    result={key(r):r for r in rows}
    if len(rows)!=870 or len(result)!=870 or {int(r['topography']) for r in rows}!=set(range(2,37)):raise ValueError('population mismatch')
    return result
def equal_rows(left,right,fields):
    if set(left)!=set(right):raise ValueError('material keys differ')
    for k,a in left.items():
        b=right[k]
        if int(a['fold'])!=int(b['fold']):raise ValueError('fold mismatch')
        for first,second in fields:close(float(a[first]),float(b[second]))
def check_folds(folds,reference,rows):
    if len(folds)!=35 or len(reference)!=35:raise ValueError('fold count mismatch')
    for a,b in zip(folds,reference):
        for field in ('fold','held_out_topography','train_keys','test_keys'):
            if a[field]!=b[field]:raise ValueError('fold identity mismatch')
        actual={key(r) for r in rows if int(r['fold'])==a['fold']}
        if actual!={tuple(v) for v in a['test_keys']} or {tuple(v) for v in a['train_keys']}&actual:raise ValueError('test keys or group leak')
        if any(k[0]!=a['held_out_topography'] for k in actual) or any(v[0]==a['held_out_topography'] for v in a['train_keys']):raise ValueError('topography leakage')
view=read('iteration.json');r54=csvrows('r54/results.csv');r59=csvrows('r59/results.csv')
base_summary=read('r54/summary.json');old_summary=read('r59/summary.json');base_folds=read('r54/folds.json');old_folds=read('r59/folds.json')
policies=set(old_summary['metrics']);baseline={};total=0
for policy in policies:
    group={}
    for recipe in ('train_mean','chemistry_ridge','chemistry_geometry_ridge'):
        rows=[r for r in r54 if r['policy']==policy and r['recipe']==recipe];group[recipe]=indexed(rows)
        computed=metrics(rows,'prediction')
        for name,value in computed.items():close(value,base_summary['metrics'][policy][recipe][name])
    rows=[r for r in r59 if r['policy']==policy];old=indexed(rows)
    equal_rows(old,group['chemistry_ridge'],[('target','target'),('chemistry_prediction','prediction')])
    equal_rows(old,group['chemistry_geometry_ridge'],[('target','target'),('additive_prediction','prediction')])
    check_folds(old_folds[policy],base_folds[policy],rows)
    for recipe,pred in (('interaction','interaction_prediction'),('additive','additive_prediction'),('chemistry','chemistry_prediction')):
        for name,value in metrics(rows,pred).items():close(value,old_summary['metrics'][policy][recipe][name])
    baseline[policy]=old
if len(r54)!=10440 or len(r59)!=3480:raise ValueError('baseline row count mismatch')
for filename in manifest['candidate_files']:
    candidate=read(filename);alpha=candidate['alpha'];rows=candidate['predictions'];summary=candidate['summary']
    if len(rows)!=3480 or summary['fit_count']!=140 or summary['alpha']!=alpha or {r['policy'] for r in rows}!=policies:raise ValueError('candidate identity mismatch')
    comparison=next(c for c in view['comparisons'] if c['alpha']==alpha)
    action=next(a for a in view['actions'] if a['id']==comparison['action_id'])
    if action['action']!=candidate['action'] or action['summary']!=summary:raise ValueError('view/action/candidate differs')
    for policy in policies:
        subset=[r for r in rows if r['policy']==policy];current=indexed(subset)
        equal_rows(current,baseline[policy],[('target','target')]);check_folds(candidate['folds'][policy],base_folds[policy],subset)
        calc=metrics(subset,'prediction');saved=summary['metrics'][policy]
        for name,value in calc.items():close(value,saved[name])
        close(saved['r59_alpha1_mae'],old_summary['metrics'][policy]['interaction']['pooled_mae'])
        close(saved['r54_additive_mae'],old_summary['metrics'][policy]['additive']['pooled_mae'])
        close(saved['r54_chemistry_mae'],old_summary['metrics'][policy]['chemistry']['pooled_mae'])
        public=next(p for p in comparison['policies'] if p['policy']==policy)
        close(public['mae'],calc['pooled_mae']);close(public['spearman'],calc['pooled_spearman_midrank'])
        for suffix,field in (('alpha1','r59_alpha1_mae'),('additive','r54_additive_mae'),('chemistry','r54_chemistry_mae')):close(public['delta_vs_'+suffix],calc['pooled_mae']-saved[field])
    total+=len(rows)
print(json.dumps({'verified_files':len(manifest['files']),'r54_rows':len(r54),'r59_rows':len(r59),'candidate_rows':total,'new_fits':0,'model_calls':0}))
'''


def _package(view,private):
    config=private['config']
    baseline=attachment(config['baseline'],config['source'],config['r54_manifest'])
    old=checked_files(config['interaction'],config['r59_manifest'])
    files={'iteration.json':_json(view),'verify.py':VERIFY_SCRIPT.encode('utf-8'),
           'r54/manifest.json':_json(baseline['manifest'])}
    for name,payload in baseline['files'].items():files['r54/'+name]=payload
    files['r59/manifest.json']=_safe_file(Path(config['interaction'])/'manifest.json',100_000)
    for name,payload in old['files'].items():files['r59/'+name]=payload
    candidates=[]
    for action in view['actions']:
        if action['id'] not in private['candidate_artifacts']:continue
        value=private['candidate_artifacts'][action['id']]
        if _safe(value)!=value:raise ResearchError('EVIDENCE_CHANGED','Candidate contains an unsafe public string.')
        name='candidates/'+value['action']+'.json';files[name]=_json(value);candidates.append(name)
    notes='\n'.join(_comparison_notes(view))
    files['README.md']=(f'''# P02 原生数值迭代：独立算术复核

本包只包含已完成的数值工件和脱敏公开迭代记录。没有原模型响应、thinking、账户、数据库、作者原数据或本机绝对路径。研究目标由操作者设定，原文见iteration.json；候选选择与停止均按已绑定实际行动报告，不是模型自主提出研究目标，也不是LLM权重训练。

解压到新目录，运行 `python verify.py`（Python 3.11+标准库）。不下载数据，不安装科学库，不重新训练。脚本核对包内SHA、R54/R59/候选材料键、目标、折分及旧基线预测，并复算MAE、RMSE、Spearman和macro fold MAE，核对公开delta。原拟合数：R54操作者420，R59操作者140，本轮已完成{view['execution']['completed_fits']}；复核新增0次。

{notes}

原显式理由保留为未经科学审定的解释；本包按实际数值复核，不保证模型文字真实，不从停止行为推断候选耗尽或策略正确。

同一870材料键/35纹理折已反复查看，成绩为探索性。已知化学、现有批次、已测平坦对照；没有确认ALP，原导出映射与零对象规则仍缺。作者入口 https://data.mendeley.com/datasets/57nrc49stj/1 ，数据DOI 10.17632/57nrc49stj.1，论文DOI 10.1016/j.biomaterials.2021.120740 。包内哈希证明一致性，不是作者签名或独立科学验证。
''').encode('utf-8')
    files['package-manifest.json']=_json({'schema_version':'p02-iteration-reproduction-v1','snapshot_sha256':view['snapshot_sha256'],
        'candidate_files':candidates,'files':{name:{'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)} for name,payload in sorted(files.items())}})
    output=BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,payload in sorted(files.items()):archive.writestr(name,payload)
    return output.getvalue()


def export_iteration(workspace,publication,output):
    """Export a view bound to an existing checked publication, without fitting."""
    from .chemotopo_iteration_view import capture_iteration
    target=Path(output).absolute();study=Path(workspace).absolute()
    if target==study or target.is_relative_to(study) or study.is_relative_to(target):raise ResearchError('INVALID_OUTPUT','Output overlaps iteration workspace.')
    if target.exists():raise ResearchError('ALREADY_EXISTS','A fresh output directory is required.')
    view,private=capture_iteration(workspace,publication)
    if _safe(view)!=view:raise ResearchError('EVIDENCE_CHANGED','Iteration view is not a safe public projection.')
    for key in ('source','baseline','interaction'):
        protected=Path(private['config'][key]).absolute()
        if target==protected or target.is_relative_to(protected) or protected.is_relative_to(target):raise ResearchError('INVALID_OUTPUT','Output overlaps frozen source evidence.')
    target.mkdir(parents=True,exist_ok=False)
    files=_charts(view)
    files.update({'iteration.json':_json(view),'report.pdf':_report(view,files['comparison.png']),
                  'reproduction.zip':_package(view,private)})
    for name,payload in files.items():
        if len(payload)>ARTIFACT_LIMITS[name]:raise ResearchError('ARTIFACT_TOO_LARGE','Iteration output exceeds allowed size.')
        (target/name).write_bytes(payload)
    manifest={'schema_version':'p02-iteration-artifacts-v1','snapshot_sha256':view['snapshot_sha256'],
              'files':{name:{'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)} for name,payload in sorted(files.items())}}
    (target/'manifest.json').write_bytes(_json(manifest))
    return manifest
