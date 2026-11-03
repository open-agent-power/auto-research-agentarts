"""Publish a native research ledger bound to an already prepared pipeline view."""
import copy
import hashlib
import json
import tempfile
from pathlib import Path

from . import evidence_submission as submission, knowledge_sources as guard
from .chemotopo_iteration_view import _bind_native
from .contracts import canonical, fingerprint
from .diagnostic_view import read_diagnostic_artifacts
from .handoff_view import _public_text, read_handoff_artifacts
from .pipeline_preparation_view import read_pipeline_preparation_artifacts
from .pipeline_research import PipelineResearchCloudLoop, project_context
from .postrun_view import _identities

LIMITS={'pipeline-research.json':1_000_000,'pipeline-research.md':100_000}
OPERATOR_NOTE={'origin':'operator_assistant_inspection','text':'DATA.csv 是保存的文件名字段；同一模块还保存 Use the object name for the file name?:Yes，不能据此确认实际导出文件名或文件存在。'}


def _require(condition,message):submission._require(condition,message)
def _hash(raw):return hashlib.sha256(raw).hexdigest()


def capture_pipeline_research(workspace,pipeline_input):
    _require(type(pipeline_input) is dict and pipeline_input.get('schema_version')=='p02-pipeline-preparation-view-v1' and pipeline_input.get('snapshot_sha256')==fingerprint({k:v for k,v in pipeline_input.items() if k!='snapshot_sha256'}),'Intact pipeline input required.')
    loop=PipelineResearchCloudLoop(workspace);paths=[loop.db,loop.study.db,loop.study.root/'source.json'];before=_identities(paths)
    _require(all(before[str(p)] is not None for p in paths),'Study, native journal and frozen source required.')
    status=loop.status()
    with loop._connect() as con:
        controller,spec,state=loop._state(con);rows=[dict(row) for row in con.execute('SELECT * FROM calls ORDER BY ordinal')]
    _require(not any(r['status'] in {'sending','received'} for r in rows),'Unknown or unfinished request cannot be published.')
    _require(controller['status']!='active' or state['status']!='active','A terminal or budget-bounded study is required.')
    bound,trace=_bind_native(loop,state,spec,rows,context_builder=project_context,scope_fields=('source_snapshot_sha256','prior_budget_history'))
    _require(bound=={a['id'] for a in state['actions']},'All committed actions must bind to native calls.')
    with loop.study._connect() as con:config,current,actions=loop.study._state(con)
    source=loop.study._source(config)
    _require(source==pipeline_input and current==state and status['study']==state and status['configuration_sha256']==fingerprint(spec) and status['budget']=={'max_requests':spec['max_requests'],'requests_reserved':len(rows)},'Frozen pipeline, controller or study state differs.')
    public_actions=[]
    for a in actions:
        _public_text({'reason':a['reason'],'parameters':a['parameters']})
        aliases=[m['alias'] for m in a['result']['modules']] if a['action']=='read_groups' else []
        public_actions.append({**{k:copy.deepcopy(a[k]) for k in ('id','ordinal','action','reason','parameters','result_sha256')},'read_aliases':aliases,'model_selected':a['id'] in bound})
    entries=[{**item,'error_code':row['error_code']} for row,item in zip(rows,trace)]
    modules={f"m{m['module_number']:02d}":m for m in pipeline_input['modules']}
    _require(all(alias in modules for alias in state['read_aliases']),'Read module missing from bound pipeline input.')
    read_modules=[{'alias':alias,**{k:copy.deepcopy(modules[alias][k]) for k in ('module','module_number','enabled','line_start','line_end','finding_id','chunk_ids')}} for alias in state['read_aliases']]
    revisions=[a for a in public_actions if a['action']=='revise_collection']
    _require(len(revisions)<=1,'Only one revision action is permitted.')
    view={'schema_version':'p02-pipeline-research-view-v1','pipeline_input_snapshot_sha256':pipeline_input['snapshot_sha256'],
          'handoff_snapshot_sha256':pipeline_input['handoff_snapshot_sha256'],'study_configuration_sha256':state['configuration_sha256'],
          'controller_configuration_sha256':fingerprint(spec),'goal':state['goal'],'study_status':state['status'],
          'controller_status':controller['status'],'controller_reason':controller['reason'],
          'execution':{'model':spec['model_identity']['model'],'requests_reserved':len(rows),'max_requests':spec['max_requests'],
                       'applied_calls':len(bound),'invalid_calls':sum(r['status']=='invalid' for r in rows),
                       'unknown_requests':0,'native_usage':copy.deepcopy(status['native_usage']),'new_fits':0},
          'prior_budget_history':copy.deepcopy(state['prior_budget_history']),'read_groups':list(state['read_groups']),
          'read_aliases':list(state['read_aliases']),'read_modules':read_modules,'actions':public_actions,'native_trace':entries,
          'revision':copy.deepcopy(revisions[0]) if revisions else None,'operator_note':copy.deepcopy(OPERATOR_NOTE),
          'configured_settings_only':True,'execution_proven':False,'biological_endpoint_eligible':False,'scientific_validation':False,'new_fits':0,
          'notice':'Read groups and aliases are model selections; group expansion and source/latest IDs are host metadata. Model reasons are unreviewed. Saved settings do not prove pipeline execution or actual export files.'}
    _public_text({'goal':view['goal'],'actions':public_actions,'native_trace':entries})
    _require(_identities(paths)==before,'Source or journal changed during capture.')
    view['snapshot_sha256']=fingerprint(view);return view


def _markdown(view):
    e=view['execution'];lines=['# 管线资料研究记录','','模型实际读取的组：'+(', '.join(view['read_groups']) or '无'),'读取模块别名：'+(', '.join(view['read_aliases']) or '无'),
        '新请求：'+str(e['requests_reserved'])+' / '+str(e['max_requests'])+'；研究状态：'+view['study_status']+'；控制器状态：'+view['controller_status'],'',
        '旧评议预算与未知请求继续保留；本轮读取不表示实际执行管线或生物学结论获批。','','## 实际行动','']
    for a in view['actions']:
        lines.extend(['- '+str(a['ordinal'])+'. '+a['action']+'；理由（模型原文，未审定）：'+a['reason'],
                      '  - 参数：`'+canonical(a['parameters'])+'`；读取别名：'+(', '.join(a['read_aliases']) or '无')])
    lines+=['','## 已读模块坐标','']
    for m in view['read_modules']:
        lines.append('- '+m['alias']+' '+m['module']+'；原始逻辑行 '+str(m['line_start'])+'–'+str(m['line_end'])+'；设置及来源见绑定的 pipeline-input.json。')
    lines+=['','## 操作员核对','',view['operator_note']['text'],'', '没有取证修订。' if view['revision'] is None else '已有未审定的模型取证修订，详细参数见 JSON。','']
    return '\n'.join(lines).encode('utf-8')


def _manifest(view,files):
    return {'schema_version':'p02-pipeline-research-artifacts-v1','snapshot_sha256':view['snapshot_sha256'],
            'pipeline_input_snapshot_sha256':view['pipeline_input_snapshot_sha256'],'handoff_snapshot_sha256':view['handoff_snapshot_sha256'],
            'files':{k:{'sha256':_hash(v),'bytes':len(v)} for k,v in files.items()}}


def read_pipeline_research_artifacts(directory,pipeline_input):
    root=submission._root(directory);manifest=guard._json(guard._read(root,'manifest.json',100_000));files={k:guard._read(root,k,n) for k,n in LIMITS.items()};view=guard._json(files['pipeline-research.json'])
    _require(pipeline_input.get('snapshot_sha256')==fingerprint({k:v for k,v in pipeline_input.items() if k!='snapshot_sha256'}) and view.get('schema_version')=='p02-pipeline-research-view-v1' and view.get('snapshot_sha256')==fingerprint({k:v for k,v in view.items() if k!='snapshot_sha256'}) and view.get('pipeline_input_snapshot_sha256')==pipeline_input['snapshot_sha256'] and view.get('handoff_snapshot_sha256')==pipeline_input['handoff_snapshot_sha256'] and view.get('configured_settings_only') is True and all(view.get(k) is False for k in ('execution_proven','biological_endpoint_eligible','scientific_validation')) and view.get('new_fits')==view.get('execution',{}).get('new_fits')==0 and view.get('operator_note')==OPERATOR_NOTE,'Published research identity or limitations changed.')
    _require(manifest==_manifest(view,files) and files['pipeline-research.md']==_markdown(view),'Published research artifacts changed.')
    return files


def export_pipeline_research(workspace,pipeline_input_directory,handoff_directory,diagnostic_directory,output):
    target=submission._root(output);_require(not target.exists(),'Use a fresh publication directory.')
    for path in (workspace,pipeline_input_directory,handoff_directory,diagnostic_directory):
        source=submission._root(path)
        _require(not(target==source or target.is_relative_to(source) or source.is_relative_to(target)),'Output overlaps source.')
    droot=submission._root(diagnostic_directory);diagnostic=guard._json(guard._read(droot,'diagnostic.json',3_000_000))
    read_diagnostic_artifacts(droot,{'snapshot_sha256':diagnostic['iteration_snapshot_sha256']})
    handoff=guard._json(read_handoff_artifacts(handoff_directory,diagnostic)['handoff.json'])
    pipeline_input=guard._json(read_pipeline_preparation_artifacts(pipeline_input_directory,handoff)['pipeline-input.json'])
    view=capture_pipeline_research(workspace,pipeline_input);files={'pipeline-research.json':(canonical(view)+'\n').encode('utf-8'),'pipeline-research.md':_markdown(view)}
    _require(all(len(v)<=LIMITS[k] for k,v in files.items()),'Publication exceeds bounds.')
    target.parent.mkdir(parents=True,exist_ok=True);submission._root(target.parent)
    with tempfile.TemporaryDirectory(prefix='.pipeline-research-',dir=target.parent) as temp:
        stage=Path(temp)/'view';stage.mkdir()
        for k,v in files.items():
            with (stage/k).open('xb') as f:f.write(v)
        with (stage/'manifest.json').open('xb') as f:f.write((canonical(_manifest(view,files))+'\n').encode('utf-8'))
        read_pipeline_research_artifacts(stage,pipeline_input)
        _require(not target.exists(),'Output appeared during sealing.');stage.rename(target)
    return _manifest(view,files)
