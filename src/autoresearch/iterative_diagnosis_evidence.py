"""Frozen terminal followup evidence for revisable diagnosis, with no recomputation."""
import copy
import hashlib
import json
from pathlib import Path

from . import diagnostic_followup, diagnostic_followup_evidence
from .chemotopo_experiment_evidence import _safe_file
from .chemotopo_iteration_view import _bind_native
from .contracts import ResearchError, canonical, fingerprint


def _require(condition,message):
    if not condition:raise ResearchError('EVIDENCE_CHANGED',message)


def _identities(root):
    result={}
    for name in ('diagnostic-followup-study.sqlite','diagnostic-followup-cloud.sqlite'):
        for suffix in ('','-wal'):
            path=root/(name+suffix);result[name+suffix]=hashlib.sha256(_safe_file(path,120_000_000)).hexdigest() if path.exists() else None
        _require(result[name] is not None,'Complete followup study and journal required.')
    return result


def _invalid(row):
    response=json.loads(row['response_json']) if row['response_json'] is not None else {}
    message=response.get('message',{}) if type(response) is dict else {}
    content=message.get('content') if type(message) is dict else None
    calls=message.get('tool_calls',[]) if type(message) is dict else []
    entries=[]
    if type(calls) is list:
        for call in calls[:4]:
            fn=call.get('function') if type(call) is dict else None
            if type(fn) is dict:entries.append({'name':fn.get('name'),'arguments':copy.deepcopy(fn.get('arguments'))})
    return {'ordinal':row['ordinal'],'error_code':row['error_code'],'content':content if type(content) is str else None,'tool_calls':entries}


def _facts(source):
    summary=source['summary'];metrics=source['original_source']['summary']['candidate_metrics'];rows=[]
    for policy,info in sorted(summary['candidate_first_same_policy_chemistry_groups'].items()):
        candidate=metrics[policy];current=candidate['pooled_mae'];chemistry=candidate['r54_chemistry_mae'];delta=current-chemistry
        rows.append({'policy':policy,'candidate_mae':current,'chemistry_mae':chemistry,'delta_mae':delta,
                     'comparison':'worse' if delta>1e-12 else 'better' if delta < -1e-12 else 'tied',
                     'worse_groups':info['worse_groups'],'better_groups':info['better_groups'],'tied_groups':info['tied_groups'],'group_count':info['group_count'],
                     'n':info['n'],'top5_absolute_error_share':info['top5_absolute_error_share'],'top5_absolute_error_n':info['top5_absolute_error_n'],
                     'worst_groups':copy.deepcopy(info['worst_groups'])})
    _require(len(rows)==4,'Four actual candidate policy facts required.')
    return {'candidate_alpha':summary['candidate_alpha'],'candidate_id':summary['candidate_id'],'policies':rows,
            'policy_labels':copy.deepcopy(summary['policy_labels']),'limitations':copy.deepcopy(summary['limitations']),
            'interpretation':'MAE lower is better; delta is candidate MAE minus chemistry MAE within each policy. Worst groups are ranked by delta, not absolute MAE. Positive means Count > 0, not positive response. Policy target shifts do not identify a winning policy.',
            'new_fits':0,'scientific_validation':False}


def prepare_source(followup_workspace):
    root=Path(followup_workspace).absolute();before=_identities(root);loop=diagnostic_followup.DiagnosticFollowupCloudLoop(root)
    with loop._connect() as con:
        project,spec,state=loop._state(con);rows=[dict(row) for row in con.execute('SELECT * FROM calls ORDER BY ordinal')]
    _require(not any(row['status'] in {'sending','received'} for row in rows),'Unknown or in-flight native call blocks capture.')
    _require(state['status'] in {'paused','stopped'},'Prior study must be paused or stopped.')
    _require(state['new_fits']==0,'Prior followup must not fit.')
    bound,trace=_bind_native(loop,state,spec,rows,context_builder=diagnostic_followup.project_context,scope_fields=('source_snapshot_sha256','scope'))
    _require(bound=={a['id'] for a in state['actions']},'Prior study actions require actual native binding.')
    with loop.study._connect() as con:config,current,actions=loop.study._state(con)
    _require(current==state,'Prior state changed during capture.')
    source=loop.study._source(config)
    _require(source['snapshot_sha256']==state['source_snapshot_sha256'] and source['scope']==state['scope'],'Prior source scope changed.')
    _require(_identities(root)==before,'Prior journal changed during capture.')
    judgments=[a for a in actions if a['action'] in diagnostic_followup.JUDGMENTS]
    prior={'configuration_sha256':state['configuration_sha256'],'study_status':state['status'],'controller_status':project['status'],
           'max_requests':spec['max_requests'],'actions':copy.deepcopy(actions),'native_trace':trace,
           'invalid_requests':[_invalid(r) for r in rows if r['status']=='invalid'],'new_fits':0}
    result={'schema_version':'p02-iterative-diagnosis-source-v1','prior_source':source,'prior_study':prior,'scope':copy.deepcopy(state['scope']),
            'seed_judgment':copy.deepcopy(judgments[-1]) if judgments else None,'facts':_facts(source),
            'topography_available':state['topography_available'] and not any(a['action']=='inspect_topography' for a in actions)}
    result['snapshot_sha256']=fingerprint(result);validate_source(result);return result


def validate_source(payload):
    _require(type(payload) is dict and payload.get('schema_version')=='p02-iterative-diagnosis-source-v1' and payload.get('snapshot_sha256')==fingerprint({k:v for k,v in payload.items() if k!='snapshot_sha256'}),'Iterative source fingerprint changed.')
    source=payload['prior_source'];diagnostic_followup_evidence.validate_source(source);prior=payload['prior_study'];actions=prior['actions'];trace=prior['native_trace']
    _require(payload['scope']==source['scope'] and prior['new_fits']==0 and len(trace)<=prior['max_requests'] and all(x['status'] in {'applied','invalid'} for x in trace),'Prior scope, budget or trace changed.')
    _require(prior['study_status'] in {'paused','stopped'},'Prior study must be paused or stopped.')
    _require([t['ordinal'] for t in trace]==list(range(1,len(trace)+1)) and [t['action_id'] for t in trace if t['status']=='applied']==[a['id'] for a in actions],'Prior native action binding changed.')
    for ordinal,action in enumerate(actions,1):
        _require(action['ordinal']==ordinal and fingerprint(action['result'])==action['result_sha256'],'Prior result changed.')
    judgments=[a for a in actions if a['action'] in diagnostic_followup.JUDGMENTS]
    _require(payload['seed_judgment']==(judgments[-1] if judgments else None),'Seed judgment changed.')
    _require([x['ordinal'] for x in prior['invalid_requests']]==[t['ordinal'] for t in trace if t['status']=='invalid'],'Invalid prior request list changed.')
    _require(payload['facts']==_facts(source),'Saved numeric facts changed.')
    available=source['summary']['topography_available'] and not any(a['action']=='inspect_topography' for a in actions)
    _require(payload['topography_available']==available,'Topography availability changed.')


def inspect_topography(payload):
    validate_source(payload);_require(payload['topography_available'],'Prior topography analysis already exists.')
    return diagnostic_followup_evidence.inspect_topography(payload['prior_source'])
