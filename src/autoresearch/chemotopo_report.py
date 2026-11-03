"""Export checked P02 evidence as a Chinese report and bounded reproduction ZIP.

No fitting, inference, original data redistribution or model-response export.
"""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import zipfile

from . import chemotopo_experiment_evidence as experiment
from .chemotopo_delivery import _safe
from .chemotopo_study import ChemoTopoStudy
from .contracts import ResearchError, canonical, fingerprint
from .paper_export import _font_name, _markup


POLICIES=('recorded_equal_batch','positive_equal_batch','recorded_equal_section','positive_equal_section')
LABELS=('A1 保留零值／批次等权','B1 正计数／批次等权','A2 保留零值／分区等权','B2 正计数／分区等权')
SCIENTIFIC_FILES=('chemotopo_data.py','chemotopo_rebuild.py','chemotopo_prediction.py',
                  'contracts.py','archive_inventory.py','c01.py')


def _json(value):
    return (canonical(value)+'\n').encode('utf-8')


def _chart(prediction):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    metrics=prediction['metrics']
    fig,axes=plt.subplots(1,2,figsize=(10,3.6),layout='constrained')
    for ax,metric,title in zip(axes,('pooled_mae','pooled_spearman_midrank'),
                              ('Primary: pooled MAE (lower is better)','Secondary: Spearman (higher is better)')):
        for offset,recipe,label,color in ((-.18,'chemistry_ridge','Chemistry','#6c8863'),
                                         (.18,'chemistry_geometry_ridge','Chemistry + geometry','#b197bc')):
            values=[metrics[p][recipe][metric] for p in POLICIES]
            ax.bar([i+offset for i in range(4)],[float('nan') if v is None else v for v in values],width=.34,label=label,color=color)
        ax.set_xticks(range(4),['A1','B1','A2','B2']);ax.set_title(title,fontsize=10)
        ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    axes[0].legend(fontsize=8,frameon=False);fig.suptitle('P02 fixed raw-red proxy: held-out whole topographies',fontsize=12)
    output={}
    try:
        for suffix in ('png','svg'):
            stream=BytesIO();fig.savefig(stream,format=suffix,dpi=170,metadata={'Creator':'Auto Research P02'})
            output['prediction.'+suffix]=stream.getvalue()
    finally:plt.close(fig)
    return output


def _pdf(publication,chart):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    font=_font_name();ink=colors.HexColor('#294337');muted=colors.HexColor('#607367')
    body=ParagraphStyle('P02Body',fontName=font,fontSize=10,leading=16,textColor=ink,spaceAfter=8,wordWrap='CJK')
    small=ParagraphStyle('P02Small',parent=body,fontSize=8,leading=12,spaceAfter=5)
    title=ParagraphStyle('P02Title',parent=body,fontSize=23,leading=32,spaceAfter=14)
    heading=ParagraphStyle('P02Heading',parent=body,fontSize=14,leading=21,spaceBefore=9,spaceAfter=8)
    p=lambda text,style=body,limit=1200:Paragraph(_markup(text,limit),style)
    story=[];prediction=publication.get('prediction')
    metrics=prediction['metrics'] if prediction else {}
    execution=publication['execution'];archive=publication.get('archive');actions=publication['actions']
    story.extend([p('P02 研究证据报告',title),p('固定红通道代理值 · 未见纹理诊断 · 非生物学批准',small),
        p('一、主结果与方法',heading)])
    if prediction:
        higher=sum(metrics[k]['chemistry_geometry_ridge']['pooled_mae']>metrics[k]['chemistry_ridge']['pooled_mae'] for k in POLICIES)
        rank_higher=sum(metrics[k]['chemistry_geometry_ridge']['pooled_spearman_midrank'] is not None and metrics[k]['chemistry_ridge']['pooled_spearman_midrank'] is not None and metrics[k]['chemistry_geometry_ridge']['pooled_spearman_midrank']>metrics[k]['chemistry_ridge']['pooled_spearman_midrank'] for k in POLICIES)
        story.append(p(f'在{higher}/4种固定处理规则中，加入10个几何字段后合并MAE更差；{rank_higher}/4种规则的Spearman更高。主指标没有因此改为排序指标，不跨规则挑选“最佳”处理。'))
        story.append(p(f"{prediction.get('keys',870)}个共同三批次组合，{prediction.get('folds',35)}个整纹理留出组；训练均值、化学Ridge、化学＋几何Ridge三种固定方法。此前{prediction.get('prior_fits',420)}次CPU拟合由操作者脚本执行，本次导出没有重新拟合。",small))
        story.append(Image(BytesIO(chart),width=174*mm,height=62.6*mm))
        rows=[[p(v,small) for v in ('规则','训练均值MAE','化学MAE','联合MAE')]]
        for key,label in zip(POLICIES,LABELS):
            rows.append([p(label,small)]+[p(f"{metrics[key][r]['pooled_mae']:.6f}",small) for r in ('train_mean','chemistry_ridge','chemistry_geometry_ridge')])
        table=Table(rows,colWidths=[65*mm,36*mm,36*mm,36*mm]);table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf2e8')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),.35,colors.HexColor('#dce5da')),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),4)]));story.append(table)
    else:story.append(p('本快照未挂载已验证预测诊断，因此不填写预测成绩。'))
    story.extend([p('已知化学类别、现有批次及已测同section平坦对照下的探索性评价；这批数据此前已查看，不是未触碰的最终盲测。',small),PageBreak(),p('二、真实模型行动与判断',title)])
    model_memories=len(publication.get('memory',{}).get('entries',[]))
    story.append(p(f"模型：{execution['model']}。真实请求{execution['requests_reserved']}次，已执行{execution['applied_calls']}次，无效{execution['invalid_calls']}次；当前研究记忆{model_memories}项，显式召回{execution['explicit_recalls']}次。模型没有创建上述CPU拟合。"))
    for action in actions:
        label={'inspect_source':'核验来源','inspect_prediction':'读取并复算已有预测','review_prediction':'证据绑定预测评议','pause':'暂停','remember_evidence':'记忆写入','recall_evidence':'记忆召回','inspect_project':'项目读取'}.get(action['action'],action['action'])
        story.append(p(f"{action['ordinal']}. {label} · {'模型选择' if action.get('model_selected') else '工具记录'}",heading))
        if action['action']=='review_prediction':
            params=action.get('parameters',{})
            story.extend([p('原始决定（未经科学批准）：'+str(params.get('decision','未提供')),small),
                          p('原始hypothesis（未验证）：'+str(params.get('hypothesis','未提供')),small,700),
                          p('原始next_check（未验证）：'+str(params.get('next_check','未提供')),small,700)])
        elif action['action']=='pause':story.append(p('原始暂停理由（未验证，节选）：'+action['reason'],small,850))
    story.append(p('本例区分主MAE与次项排序，不等于证明创新策略或持续研究成功。ALP及导出映射不足会阻止生物解释，但不自动阻止字面代理值的继续数值诊断。',small))
    story.extend([PageBreak(),p('三、归档、来源与复核',title)])
    if archive:
        story.extend([p(f"操作者运行后归档：{len(archive['entries'])}项条件观察。触发者为{archive['persistence_trigger']}；模型选择remember：{archive['model_selected_remember']}。这与原研究记忆{model_memories}项分别计数。"),p('共享库本机读回不证明真实LLM复用；模型假设、评议和暂停文字没有被晋升为已核验数值事实。')])
    else:story.append(p('未附加经过验证的操作者归档收据；不填归档成绩。'))
    story.append(p('固定来源与复现范围',heading))
    for source in publication['source_manifest']:
        story.append(p(f"{source.get('file',source.get('name','作者来源'))} · {source.get('bytes','')}字节",small))
        story.append(p('SHA-256：'+source.get('sha256','未提供'),small))
    story.extend([p('数据入口：https://data.mendeley.com/datasets/57nrc49stj/1',small),
        p('研究DOI：10.1016/j.biomaterials.2021.120740；数据DOI：10.17632/57nrc49stj.1。原始数据不随本包分发，须按源指纹另取。',small),
        p('复核路径',heading),p('reproduction.zip含固定协议、逐折材料键、留出预测、完整指标和最小科学源码。verify.py仅核对文件SHA及从已保存CSV复算指标，0次拟合；重新训练是另一个可选步骤，固定420次CPU拟合。',small),
        p('没有对象测量输出与原工作簿列的唯一映射，没有确认ALP通道和零对象转换规则。几何MAE未改善不是生物学阴性结论，也不证明所有几何模型无效。',small),
        p('这是可追踪的本机研究证据报告，不是已发表论文、独立生物验证或平台部署。',small),
        p('快照SHA-256：'+publication['snapshot_sha256'],small)])
    stream=BytesIO();doc=SimpleDocTemplate(stream,pagesize=A4,leftMargin=18*mm,rightMargin=18*mm,topMargin=18*mm,bottomMargin=17*mm,title='P02研究证据报告',author='Auto Research')
    def footer(canvas,_doc):
        canvas.setFont(font,8);canvas.setFillColor(muted);canvas.drawString(18*mm,10*mm,'P02 · 固定证据 / 数值代理值 / 科学资格未批准');canvas.drawRightString(192*mm,10*mm,str(_doc.page))
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return stream.getvalue()


VERIFY_SCRIPT = r'''"""Hash and arithmetic verification only; no sklearn imports or fits."""
import csv, hashlib, json, math, statistics
from pathlib import Path
root=Path(__file__).resolve().parent
manifest=json.loads((root/'package-manifest.json').read_text(encoding='utf-8'))
expected=set(manifest['files'])|{'package-manifest.json'}
actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
if actual!=expected: raise ValueError('unlisted or missing package files')
for name,meta in manifest['files'].items():
    path=root/name
    if path.is_symlink() or '..' in Path(name).parts: raise ValueError('unsafe package path')
    raw=path.read_bytes()
    if len(raw)!=meta['bytes'] or hashlib.sha256(raw).hexdigest()!=meta['sha256']: raise ValueError('package checksum mismatch: '+name)
summary=json.loads((root/'experiment/summary.json').read_text(encoding='utf-8'))
def ranks(xs):
    order=sorted(range(len(xs)),key=xs.__getitem__);result=[0.]*len(xs);i=0
    while i<len(xs):
        j=i+1
        while j<len(xs) and xs[order[i]]==xs[order[j]]:j+=1
        for k in order[i:j]:result[k]=(i+1+j)/2
        i=j
    return result
groups={}
with (root/'experiment/results.csv').open(encoding='utf-8',newline='') as f:
    for row in csv.DictReader(f): groups.setdefault((row['policy'],row['recipe']),[]).append(row)
expected_groups={(p,r) for p in summary['metrics'] for r in summary['metrics'][p]}
if set(groups)!=expected_groups or sum(map(len,groups.values()))!=summary['keys']*len(expected_groups):raise ValueError('prediction population mismatch')
maes={}
for (policy,recipe),rows in groups.items():
    if len({(r['topography'],r['chemistry']) for r in rows})!=summary['keys'] or len({r['topography'] for r in rows})!=summary['folds']:raise ValueError('duplicate or incomplete prediction keys')
    y=[float(r['target']) for r in rows];pred=[float(r['prediction']) for r in rows]
    errors=[abs(a-b) for a,b in zip(y,pred)];mae=statistics.mean(errors);maes[policy,recipe]=mae
    folds={}
    for r,e in zip(rows,errors):folds.setdefault(r['topography'],[]).append(e)
    a,b=ranks(y),ranks(pred)
    rho=statistics.correlation(a,b) if len(set(a))>1 and len(set(b))>1 else None
    values={'pooled_mae':mae,'pooled_rmse':math.sqrt(statistics.mean((x-z)**2 for x,z in zip(y,pred))),
            'macro_fold_mae':statistics.mean(statistics.mean(v) for v in folds.values()),'pooled_spearman_midrank':rho}
    for key,value in values.items():
        saved=summary['metrics'][policy][recipe][key]
        if (value is None)!=(saved is None) or value is not None and not math.isclose(value,saved,rel_tol=1e-10,abs_tol=1e-12):raise ValueError('metric mismatch: '+key)
for (policy,recipe),mae in maes.items():
    base=maes[policy,'train_mean'];skill=None if base==0 else 1-mae/base;saved=summary['metrics'][policy][recipe]['skill_vs_oof_train_mean_mae']
    if (skill is None)!=(saved is None) or skill is not None and not math.isclose(skill,saved,rel_tol=1e-10,abs_tol=1e-12):raise ValueError('skill mismatch')
print(json.dumps({'verified_files':len(manifest['files']),'rows':sum(map(len,groups.values())),'new_fits':0,'model_calls':0}))
'''


def _bundle(publication,attached):
    protocol=json.loads(attached['files']['protocol.json']);versions=protocol['versions']
    package={'research.json':_json(publication),'experiment/manifest.json':_json(attached['manifest']),
             **{'experiment/'+name:payload for name,payload in attached['files'].items()},
             'verify.py':VERIFY_SCRIPT.encode('utf-8'),'src/autoresearch/__init__.py':b'"""Frozen P02 numerical reproduction subset."""\n'}
    if publication.get('archive') is not None:package['operator-archive.json']=_json(publication['archive'])
    here=Path(__file__).parent
    for name in SCIENTIFIC_FILES:package['src/autoresearch/'+name]=(here/name).read_bytes()
    project=here.parents[1]
    for name in ('rebuild_chemotopo.py','predict_chemotopo_proxy.py'):package['scripts/'+name]=(project/'scripts'/name).read_bytes()
    requirements=f"numpy=={versions['numpy']}\nscikit-learn=={versions['scikit_learn']}\n"
    package['requirements.txt']=requirements.encode('utf-8')
    sources='\n'.join(f"- {s['file']}: {s['sha256']} ({s['bytes']} bytes)" for s in protocol['sources'])
    package['README.md']=f'''# P02 固定数值诊断复核

本包不是已发表论文或生物学批准。原420次CPU拟合为操作者脚本执行；模型只读、评议和暂停。operator-archive.json（如有）是独立操作者归档投影，不能计为模型remember。

## 先做0拟合复核

将ZIP解到新目录，使用Python {versions['python']}运行 `python verify.py`。只检查allowlist/SHA并从保存CSV复算MAE、RMSE、Spearman、macro MAE及skill，不拟合、不联网、不调用模型。哈希证明包内一致性，不是作者身份签名或独立生物验证。

## 可选：从作者文件重跑420次CPU拟合

此步骤不属于verify.py，也未由解压自动执行。Python {versions['python']}，依赖见requirements.txt。另从 https://data.mendeley.com/datasets/57nrc49stj/1 取得以下原件并按SHA核对；本包不分发原数据。DOI: 10.17632/57nrc49stj.1；论文DOI: 10.1016/j.biomaterials.2021.120740。

{sources}

```powershell
python -m pip install -r requirements.txt
$env:PYTHONPATH='src'
python scripts/predict_chemotopo_proxy.py --source <verified-author-files> --output <new-output-directory>
```

该命令固定35整纹理折×四规则×三方法=420次拟合。输出目录须不存在；不调参、不挑policy，不宣称未来实验室或未见化学泛化。也可用scripts/rebuild_chemotopo.py --directory <verified-author-files> --output <new-directory>仅重建四规则。

研究与归档JSON为脱敏公共投影，不包含原模型响应、thinking、账户或浏览器状态；原始本机路径不随包分发。科学边界：raw-red proxy不是已确认ALP，导出映射与零对象规则仍未决。
'''.encode('utf-8')
    package['package-manifest.json']=_json({'schema_version':'p02-reproduction-package-v1','snapshot_sha256':publication['snapshot_sha256'],
        'files':{name:{'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)} for name,payload in sorted(package.items())}})
    stream=BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,payload in sorted(package.items()):archive.writestr(name,payload)
    return stream.getvalue()


def export_report(workspace,output,*,archive_receipt=None,memory_workspace=None):
    """Create new artifacts from checked frozen inputs, without dispatch or fits."""
    from .chemotopo_publication import load_publication
    target=Path(output).absolute();source=Path(workspace).absolute()
    if target==source or target.is_relative_to(source) or source.is_relative_to(target):raise ResearchError('INVALID_OUTPUT','Report output must be separate from the study.')
    if target.exists():raise ResearchError('ALREADY_EXISTS','Use a new report output directory.')
    publication=load_publication(workspace,archive_receipt=archive_receipt,memory_workspace=memory_workspace)
    study=ChemoTopoStudy(workspace)
    with study._connect() as con:config,_,_=study._state(con)
    if not publication.get('prediction') or not config.get('prediction_directory'):raise ResearchError('NO_EVIDENCE','Report requires a pinned prediction attachment.')
    for location in (config['source_directory'],config['prediction_directory'],config['memory_workspace'],memory_workspace):
        if location is not None:
            protected=Path(location).absolute()
            if target==protected or target.is_relative_to(protected) or protected.is_relative_to(target):raise ResearchError('INVALID_OUTPUT','Report output overlaps protected input storage.')
    attached=experiment.attachment(config['prediction_directory'],config['source_directory'],config['prediction_attachment']['manifest_sha256'])
    if attached['protocol_sha256']!=config['prediction_attachment']['protocol_sha256']:raise ResearchError('EVIDENCE_CHANGED','Prediction protocol changed.')
    publication=_safe(publication)
    target.mkdir(parents=True,exist_ok=False)
    artifacts=_chart(publication['prediction'])
    artifacts.update({'research.json':_json(publication),'report.pdf':_pdf(publication,artifacts['prediction.png']),
                      'reproduction.zip':_bundle(publication,attached)})
    # Recheck live identities before publishing a completion manifest.
    if fingerprint(load_publication(workspace,archive_receipt=archive_receipt,memory_workspace=memory_workspace))!=fingerprint(publication):raise ResearchError('EVIDENCE_CHANGED','Publication changed during export.')
    for name,payload in artifacts.items():(target/name).write_bytes(payload)
    manifest={'schema_version':'p02-publication-artifacts-v1','snapshot_sha256':publication['snapshot_sha256'],
              'files':{name:{'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)} for name,payload in sorted(artifacts.items())}}
    (target/'manifest.json').write_bytes(_json(manifest))
    return manifest
