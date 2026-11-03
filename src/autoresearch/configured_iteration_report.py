"""Export frozen configured-iteration evidence without source reads or fits."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import zipfile

from .chemotopo_delivery import _safe
from .chemotopo_experiment_evidence import _safe_file
from .chemotopo_iteration_report import ARTIFACT_LIMITS, _charts, _report
from .contracts import ResearchError, canonical


def _json(value):
    return (canonical(value)+'\n').encode('utf-8')


VERIFY_SCRIPT=r'''"""Frozen configured inputs + predictions: standard library, zero fits."""
import hashlib,json,math,statistics
from pathlib import Path
root=Path(__file__).resolve().parent
def encoded(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def sha(v):return hashlib.sha256(v).hexdigest()
def fingerprint(v):return sha(encoded(v))
def read(name):return json.loads((root/name).read_text(encoding='utf-8'))
manifest=read('package-manifest.json')
if {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}!=set(manifest['files'])|{'package-manifest.json'}:raise ValueError('missing or extra package files')
for name,meta in manifest['files'].items():
    path=root/name
    if Path(name).is_absolute() or '..' in Path(name).parts or path.is_symlink():raise ValueError('unsafe package path')
    raw=path.read_bytes()
    if len(raw)!=meta['bytes'] or sha(raw)!=meta['sha256']:raise ValueError('package checksum differs')
view=read('iteration.json');inputs=read('inputs.json')
if view['snapshot_sha256']!=fingerprint({k:v for k,v in view.items() if k!='snapshot_sha256'}) or manifest['snapshot_sha256']!=view['snapshot_sha256']:raise ValueError('view identity differs')
if sha((root/'inputs.json').read_bytes())!=view['inputs_sha256']:raise ValueError('frozen input identity differs')
if inputs['prior_evidence']!=view['prior_evidence']:raise ValueError('prior evidence differs')
protocol=view['protocol'];candidates={c['id']:c for c in protocol['candidates']}
if protocol['executor_id']!=inputs['executor_id'] or len(candidates)!=len(protocol['candidates']):raise ValueError('protocol identity differs')
def close(a,b):
    if (a is None)!=(b is None) or a is not None and not math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-12):raise ValueError('metric arithmetic differs')
def ranks(xs):
    order=sorted(range(len(xs)),key=xs.__getitem__);out=[0.]*len(xs);i=0
    while i<len(xs):
        j=i+1
        while j<len(xs) and xs[order[i]]==xs[order[j]]:j+=1
        for k in order[i:j]:out[k]=(i+1+j)/2
        i=j
    return out
def calc(rows,column):
    y=[r['target'] for r in rows];p=[r[column] for r in rows]
    if not all(type(v) in (float,int) and math.isfinite(v) for v in y+p):raise ValueError('nonfinite values')
    errors=[abs(a-b) for a,b in zip(y,p)];folds={}
    for row,e in zip(rows,errors):folds.setdefault(row['fold'],[]).append(e)
    a,b=ranks(y),ranks(p)
    return {'pooled_mae':statistics.mean(errors),'pooled_rmse':math.sqrt(statistics.mean((a-b)**2 for a,b in zip(y,p))),
            'pooled_spearman_midrank':statistics.correlation(a,b) if len(set(a))>1 and len(set(b))>1 else None,
            'macro_fold_mae':statistics.mean(statistics.mean(v) for v in folds.values())}
def indexed(rows):
    values={(r['topography'],r['chemistry']):r for r in rows}
    if len(values)!=870 or len(rows)!=870 or {r['topography'] for r in rows}!=set(range(2,37)):raise ValueError('material cohort differs')
    return values
def folds_match(folds,reference,rows):
    if len(folds)!=35 or len(reference)!=35:raise ValueError('fold count differs')
    allkeys={(r['topography'],r['chemistry']) for r in rows}
    for fold,expected in zip(folds,reference):
        for field in ('fold','held_out_topography','train_keys','test_keys'):
            if fold[field]!=expected[field]:raise ValueError('fold identity differs')
        test={(r['topography'],r['chemistry']) for r in rows if r['fold']==fold['fold']};train=allkeys-test
        if test!={tuple(k) for k in fold['test_keys']} or train!={tuple(k) for k in fold['train_keys']}:raise ValueError('grouped keys differ')
        if {k[0] for k in test}!={fold['held_out_topography']} or any(k[0]==fold['held_out_topography'] for k in train) or not {k[1] for k in test}<={k[1] for k in train}:raise ValueError('group leakage or unknown chemistry')
policies=inputs['policies'];base={};common=None
if len(policies)!=4 or len(set(policies))!=4 or set(inputs['rows_by_policy'])!=set(policies):raise ValueError('policy set differs')
for policy in policies:
    rows=inputs['rows_by_policy'][policy];base[policy]=indexed(rows)
    if common is not None and common!=set(base[policy]):raise ValueError('policy cohorts differ')
    common=set(base[policy]);folds=inputs['folds_by_policy'][policy];folds_match(folds,folds,rows)
    for row in rows:
        if len(row['geometry'])!=10 or not all(type(v) in (int,float) and math.isfinite(v) for v in row['geometry']):raise ValueError('geometry differs')
    for name,column in (('chemistry','chemistry_prediction'),('additive','additive_prediction'),('interaction','interaction_prediction')):
        for metric,value in calc(rows,column).items():close(value,inputs['prior_evidence']['metrics'][policy][name][metric])
files=manifest['candidate_files'];seen=set();prediction_rows=0
actions={a['id']:a for a in view['actions']};completed={a['parameters']['candidate_id']:a for a in view['actions'] if a['action']=='run_candidate'}
if len(files)!=len(completed):raise ValueError('candidate action count differs')
for name in files:
    value=read(name);cid=value['candidate_id'];candidate=candidates[cid];summary=value['summary']
    if cid in seen or cid not in completed or value['alpha']!=candidate['alpha'] or summary['alpha']!=candidate['alpha'] or summary['candidate_id']!=cid or summary['fit_count']!=140:raise ValueError('candidate protocol differs')
    seen.add(cid);action=completed[cid]
    if value['inputs_sha256']!=view['inputs_sha256'] or value['configuration_sha256']!=view['study_configuration_sha256'] or action['summary']!=summary:raise ValueError('candidate input/config/summary binding differs')
    result={'summary':summary,'artifact':{'sha256':sha(encoded(value)),'bytes':len(encoded(value))}}
    if fingerprint(result)!=action['result_sha256']:raise ValueError('action result identity differs')
    rows=value['predictions'];comparison=next(c for c in view['comparisons'] if c['action_id']==action['id'])
    if len(rows)!=3480 or set(r['policy'] for r in rows)!=set(policies) or comparison['alpha']!=candidate['alpha']:raise ValueError('candidate population differs')
    for policy in policies:
        current=[r for r in rows if r['policy']==policy];bykey=indexed(current)
        if set(bykey)!=set(base[policy]):raise ValueError('candidate keys differ')
        for key,r in bykey.items():
            original=base[policy][key]
            if r['target']!=original['target'] or r['fold']!=original['fold']:raise ValueError('candidate targets or folds differ')
        folds_match(value['folds'][policy],inputs['folds_by_policy'][policy],current)
        calculated=calc(current,'prediction');saved=summary['metrics'][policy]
        for metric,n in calculated.items():close(n,saved[metric])
        public=next(p for p in comparison['policies'] if p['policy']==policy)
        close(public['mae'],calculated['pooled_mae']);close(public['spearman'],calculated['pooled_spearman_midrank'])
        for suffix,old,field in (('alpha1','interaction','r59_alpha1_mae'),('additive','additive','r54_additive_mae'),('chemistry','chemistry','r54_chemistry_mae')):
            baseline=inputs['prior_evidence']['metrics'][policy][old]['pooled_mae'];close(saved[field],baseline);close(public[suffix+'_mae'],baseline);close(public['delta_vs_'+suffix],calculated['pooled_mae']-baseline)
    prediction_rows+=len(rows)
if view['execution']['completed_candidates']!=len(seen) or view['execution']['completed_fits']!=len(seen)*140:raise ValueError('execution count differs')
print(json.dumps({'verified_files':len(manifest['files']),'input_rows':sum(len(v) for v in inputs['rows_by_policy'].values()),'candidate_rows':prediction_rows,'new_fits':0,'model_calls':0}))
'''


def _package(view,private):
    raw=private['inputs_bytes']
    if not isinstance(raw,bytes) or hashlib.sha256(raw).hexdigest()!=view['inputs_sha256'] or json.loads(raw)!=private['inputs']:
        raise ResearchError('EVIDENCE_CHANGED','Exact frozen input bytes differ.')
    if private['config']['protocol']!=view['protocol']:raise ResearchError('EVIDENCE_CHANGED','Frozen protocol differs from the view.')
    files={'inputs.json':raw,'iteration.json':_json(view),'verify.py':VERIFY_SCRIPT.encode('utf-8')};candidate_files=[]
    for action in view['actions']:
        if action['id'] not in private['candidate_artifacts']:continue
        value=private['candidate_artifacts'][action['id']];cid=value['candidate_id']
        if not cid.isidentifier() or _safe(value)!=value:raise ResearchError('EVIDENCE_CHANGED','Unsafe candidate projection.')
        name='candidates/'+cid+'.json';files[name]=_json(value);candidate_files.append(name)
    if _safe(private['inputs'])!=private['inputs']:raise ResearchError('EVIDENCE_CHANGED','Frozen input projection contains private paths.')
    files['README.md']=f'''# 配置化P02迭代：封存输入算术复核

在新目录解压，运行 `python -B verify.py`（Python 3.11+标准库）。脚本不读取原始xlsx、不安装科学库、不重建来源、不训练或调用模型。输入由创建时核验并封存，原来源后来变化不自动修改本包。

输入是4种规则各870行公有派生数值（含10几何、目标、已有基线预测与35折）。脚本重算三条已有基线及所有已完成候选的MAE/RMSE/Spearman/macro MAE，核对材料键、目标、分组、protocol/config/inputs/action summary哈希及公开差值。0候选时只复算已有基线，不补候选。

本轮已完成{view['execution']['completed_candidates']}个候选、{view['execution']['completed_fits']}次CPU拟合；这不包含R54操作者420次、R59操作者140次或原R61的280次。研究目标与候选来自操作者协议，不是LLM权重训练，模型原理由未审定。

原ALP身份、导出映射与零对象规则仍未批准；同一已看过探索折上的比较不是独立盲测。哈希与算术一致性不是重新科学验证。旧alpha10/100仅为封存历史摘要；如需独立重算旧候选，使用其旧复核ZIP。

不含数据库、原生响应/thinking、账户、cookies、本机绝对路径或原始作者数据。作者入口 https://data.mendeley.com/datasets/57nrc49stj/1 ，DOI 10.17632/57nrc49stj.1；论文DOI 10.1016/j.biomaterials.2021.120740。
'''.encode('utf-8')
    if view['execution'].get('native_interface')=='compact-v1':
        files['README.md']+='\n紧凑原生接口仅将候选／暂停／停止及reason记为模型选择；observation、source及latest action IDs由宿主从已保存观察绑定。这不代表模型主动引用来源或已经阅读证据。\n'.encode('utf-8')
    files['package-manifest.json']=_json({'schema_version':'configured-iteration-reproduction-v1','snapshot_sha256':view['snapshot_sha256'],
        'candidate_files':candidate_files,'files':{name:{'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)} for name,payload in sorted(files.items())}})
    out=BytesIO()
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,payload in sorted(files.items()):archive.writestr(name,payload)
    return out.getvalue()


def export_configured(workspace,publication,output,*,native_interface='legacy'):
    """Create the existing five-artifact report contract from frozen inputs only."""
    from .configured_iteration_view import capture_configured
    target=Path(output).absolute();source=Path(workspace).absolute()
    if target==source or target.is_relative_to(source) or source.is_relative_to(target):raise ResearchError('INVALID_OUTPUT','Output overlaps configured study.')
    if target.exists():raise ResearchError('ALREADY_EXISTS','Use a new report output directory.')
    view,private=capture_configured(workspace,publication,native_interface=native_interface)
    if _safe(view)!=view:raise ResearchError('EVIDENCE_CHANGED','Iteration view contains private paths.')
    for location in private['config'].get('private_sources',{}).values():
        if location is None:continue
        path=Path(location).absolute()
        if target==path or target.is_relative_to(path) or path.is_relative_to(target):raise ResearchError('INVALID_OUTPUT','Output overlaps protected original evidence.')
    target.mkdir(parents=True,exist_ok=False)
    files=_charts(view)
    files.update({'iteration.json':_json(view),'report.pdf':_report(view,files['comparison.png']),'reproduction.zip':_package(view,private)})
    for name,payload in files.items():
        if len(payload)>ARTIFACT_LIMITS[name]:raise ResearchError('ARTIFACT_TOO_LARGE','Report artifact exceeds bounds.')
        (target/name).write_bytes(payload)
    manifest={'schema_version':'p02-iteration-artifacts-v1','snapshot_sha256':view['snapshot_sha256'],
              'files':{name:{'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)} for name,payload in sorted(files.items())}}
    (target/'manifest.json').write_bytes(_json(manifest))
    return manifest
