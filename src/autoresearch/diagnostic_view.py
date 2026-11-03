"""Public, read-only projection of an iterative diagnosis and its native evidence."""
import copy
import hashlib
import json
from pathlib import Path

from .chemotopo_delivery import _safe
from .chemotopo_experiment_evidence import _safe_file
from .chemotopo_iteration_report import read_iteration_artifacts
from .chemotopo_iteration_view import _bind_native
from .contracts import ResearchError, canonical, fingerprint
from .iterative_diagnosis import IterativeDiagnosisCloudLoop, JUDGMENTS, project_context


def _require(condition,message):
    if not condition:raise ResearchError('EVIDENCE_CHANGED',message)


def _identities(root):
    result={}
    for name in ('iterative-diagnosis-study.sqlite','iterative-diagnosis-cloud.sqlite'):
        for suffix in ('','-wal'):
            path=root/(name+suffix);result[name+suffix]=hashlib.sha256(_safe_file(path,120_000_000)).hexdigest() if path.exists() else None
        _require(result[name] is not None,'Diagnostic study and controller journal are required.')
    return result


def _native_entries(rows,trace):
    entries=[]
    for row,item in zip(rows,trace):
        _require(row['status'] in {'applied','invalid'} and row['response_json'] is not None,'Unknown or unfinished native requests cannot be published.')
        response=json.loads(row['response_json']);message=response.get('message',{}) if type(response) is dict else {}
        content=message.get('content') if type(message) is dict else None;calls=message.get('tool_calls',[]) if type(message) is dict else []
        tools=[]
        if type(calls) is list:
            for call in calls:
                fn=call.get('function') if type(call) is dict else None
                if type(fn) is dict:tools.append({'name':fn.get('name'),'arguments':copy.deepcopy(fn.get('arguments'))})
        entries.append({**copy.deepcopy(item),'error_code':row['error_code'],'content':content if type(content) is str else None,'tool_calls':tools})
    return entries


def _assessment(annotation,state,source):
    if annotation is None:return {'status':'unreviewed','origin':'no_assessment','notes':[],'judgment_action_id':None}
    fields={'schema_version','source_snapshot_sha256','judgment_action_id','status','origin','notes'}
    ids={a['id'] for a in state['actions'] if a['action'] in JUDGMENTS}
    _require(type(annotation) is dict and set(annotation)==fields and annotation['schema_version']=='p02-diagnostic-assessment-v1'
             and annotation['source_snapshot_sha256']==source['snapshot_sha256'] and annotation['judgment_action_id'] in ids
             and annotation['status'] in {'unreviewed','needs_revision'} and annotation['origin']=='operator_assistant_inspection'
             and type(annotation['notes']) is list and 1<=len(annotation['notes'])<=5
             and all(type(note) is str and 1<=len(note)<=1000 for note in annotation['notes']), 'Assessment must bind the current source and actual judgment.')
    return copy.deepcopy(annotation)


def capture_diagnostic(workspace,iteration,assessment=None):
    _require(type(iteration) is dict and iteration.get('schema_version')=='p02-iteration-view-v1' and iteration.get('snapshot_sha256')==fingerprint({k:v for k,v in iteration.items() if k!='snapshot_sha256'}),'Intact iteration snapshot required.')
    root=Path(workspace).absolute();before=_identities(root);loop=IterativeDiagnosisCloudLoop(root)
    with loop._connect() as con:
        project,spec,state=loop._state(con);rows=[dict(row) for row in con.execute('SELECT * FROM calls ORDER BY ordinal')]
    _require(not any(row['status'] in {'sending','received'} for row in rows),'Unknown in-flight native request blocks publication.')
    bound,trace=_bind_native(loop,state,spec,rows,context_builder=project_context,scope_fields=('source_snapshot_sha256','scope'))
    _require(bound=={a['id'] for a in state['actions']},'All applied diagnostic actions require actual native binding.')
    with loop.study._connect() as con:config,current,actions=loop.study._state(con)
    _require(current==state,'Diagnostic state changed while capturing.')
    source=loop.study._source(config);prior=source['prior_source'];original=prior['original_source']
    _require(original['iteration']==iteration and state['scope']==source['scope'],'Iteration or study scope differs from frozen source.')
    prior_actions=prior['prior_study']['actions'];prior_results=[]
    for a in prior_actions:
        if a['action'] in {'inspect_residuals','compare_policies'}:
            prior_results.append({'id':a['id'],'action':a['action'],'parameters':copy.deepcopy(a['parameters']),'result_sha256':a['result_sha256'],'summary':copy.deepcopy(a['result']['summary'])})
    public_actions=[];topography=None
    for a in actions:
        public_actions.append({**{k:copy.deepcopy(a[k]) for k in ('id','ordinal','action','parameters','reason','result_sha256')},'summary':copy.deepcopy(a['result']['summary']),'model_selected':a['id'] in bound})
        if a['action']=='inspect_topography':
            result=a['result'];topography={'action_id':a['id'],'summary':copy.deepcopy(result['summary']),'groups':copy.deepcopy(result['groups']),'rankings':copy.deepcopy(result['rankings'])}
    chart=[]
    if topography:
        for group in topography['groups']:
            if group['method']=='current_candidate':chart.append({k:copy.deepcopy(group[k]) for k in ('policy','topography','n','mae','signed_bias','delta_mae_vs_chemistry')})
    terminal=state['status'] in {'paused','stopped'}
    view={'schema_version':'p02-diagnostic-view-v1','iteration_snapshot_sha256':iteration['snapshot_sha256'],
          'source_snapshot_sha256':source['snapshot_sha256'],'study_configuration_sha256':state['configuration_sha256'],
          'controller_configuration_sha256':fingerprint(spec),'goal':state['goal'],'study_status':state['status'],
          'controller_status':project['status'],'controller_reason':project['reason'],'terminal_control_applied':terminal,
          'incomplete_notice':None if terminal else 'Diagnostic study is active; no model pause or stop has been applied. Only recorded responses are shown.',
          'actions':public_actions,'native_trace':_native_entries(rows,trace),
          'prior_diagnostics':prior_results,'prior_judgment':copy.deepcopy(source['seed_judgment']),
          'prior_invalid_requests':copy.deepcopy(source['prior_study']['invalid_requests']),
          'candidate_facts':copy.deepcopy(source['facts']),'topography':topography,'topography_chart':chart,
          'assessment':_assessment(assessment,state,source),
          'execution':{'model':spec['model_identity']['model'],'requests_reserved':len(rows),'max_requests':spec['max_requests'],
                       'applied_calls':len(bound),'invalid_calls':sum(r['status']=='invalid' for r in rows),'unknown_requests':0,'new_fits':0},
          'limitations':['Recorded model judgments and explicit text are unreviewed assertions, not scientific facts.',
                         'Operator-assistant inspection is not model self-correction or scientific review.',
                         'MAE is lower-is-better; group ranking by candidate-minus-chemistry delta is not absolute MAE ranking.',
                         'Different processing policies change targets; no policy leaderboard or biological conclusion.',
                         'No statistical significance tests or p-values were calculated by these diagnostics.'],
          'scientific_validation':False,'llm_weight_training':False}
    _require(_safe(view)==view,'Public view contains local paths; cannot preserve original text safely.')
    _require(len(canonical(view).encode('utf-8'))<=3_000_000,'Bounded public diagnostic view exceeded.')
    _require(_identities(root)==before,'Diagnostic journal changed during capture.')
    view['snapshot_sha256']=fingerprint(view);return view


def export_diagnostic(workspace,iteration,output,assessment=None):
    root=Path(output).absolute();source=Path(workspace).absolute().resolve();target=root.resolve()
    _require(not(target==source or target.is_relative_to(source) or source.is_relative_to(target)),'Output must be separate from source study.')
    for path in (root,*root.parents):_require(not path.is_symlink() and not getattr(path,'is_junction',lambda:False)(),'Output cannot redirect.')
    _require(not root.exists(),'Use an exclusive new output directory.')
    view=capture_diagnostic(workspace,iteration,assessment);raw=(canonical(view)+'\n').encode('utf-8')
    manifest={'schema_version':'p02-diagnostic-artifacts-v1','snapshot_sha256':view['snapshot_sha256'],
              'iteration_snapshot_sha256':view['iteration_snapshot_sha256'],'files':{'diagnostic.json':{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}}}
    root.mkdir(parents=True,exist_ok=False)
    with (root/'diagnostic.json').open('xb') as stream:stream.write(raw)
    with (root/'manifest.json').open('xb') as stream:stream.write((canonical(manifest)+'\n').encode('utf-8'))
    return manifest


def read_diagnostic_artifacts(directory,iteration):
    root=Path(directory);manifest=json.loads(_safe_file(root/'manifest.json',100_000));raw=_safe_file(root/'diagnostic.json',3_000_000);view=json.loads(raw)
    _require(view.get('schema_version')=='p02-diagnostic-view-v1' and view.get('scientific_validation') is False
             and view.get('snapshot_sha256')==fingerprint({k:v for k,v in view.items() if k!='snapshot_sha256'})
             and view.get('iteration_snapshot_sha256')==iteration.get('snapshot_sha256') and _safe(view)==view,'Diagnostic view identity or iteration binding changed.')
    _require(manifest=={'schema_version':'p02-diagnostic-artifacts-v1','snapshot_sha256':view['snapshot_sha256'],
                        'iteration_snapshot_sha256':view['iteration_snapshot_sha256'],'files':{'diagnostic.json':{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}}},'Diagnostic manifest changed.')
    return {'diagnostic.json':raw}
