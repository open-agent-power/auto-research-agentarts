"""Capture terminal diagnostic evidence for a bounded no-refit continuation."""
import copy
import hashlib
import json
from pathlib import Path

from . import diagnostic_research, residual_diagnostics
from .chemotopo_experiment_evidence import _safe_file
from .chemotopo_iteration_view import _bind_native
from .c01_research import ACTION_FIELDS
from .contracts import ResearchError, canonical, fingerprint

MAX_DB_BYTES=120_000_000


def _require(condition,message):
    if not condition:raise ResearchError('EVIDENCE_CHANGED',message)


def _db_identities(root):
    result={}
    for name in ('diagnostic-study.sqlite','diagnostic-cloud.sqlite'):
        for suffix in ('','-wal'):
            path=root/(name+suffix)
            result[name+suffix]=hashlib.sha256(_safe_file(path,MAX_DB_BYTES)).hexdigest() if path.exists() else None
        _require(result[name] is not None,'A complete diagnostic study and native journal are required.')
    return result


def _invalid_call(row):
    response=json.loads(row['response_json']) if row['response_json'] is not None else {}
    message=response.get('message',{}) if type(response) is dict else {}
    calls=message.get('tool_calls',[]) if type(message) is dict else []
    supplied=[]
    if type(calls) is list:
        for call in calls[:4]:
            fn=call.get('function') if type(call) is dict else None
            if type(fn) is dict:
                supplied.append({'tool_name':fn.get('name'),'arguments':copy.deepcopy(fn.get('arguments'))})
    return {'ordinal':row['ordinal'],'error_code':row['error_code'],'tool_calls':supplied}


def prepare_source(diagnostic_workspace):
    root=Path(diagnostic_workspace).absolute();before=_db_identities(root);loop=diagnostic_research.DiagnosticCloudLoop(root)
    with loop._connect() as con:
        project,spec,state=loop._state(con);rows=[dict(row) for row in con.execute('SELECT * FROM calls ORDER BY ordinal')]
    _require(state['status'] in {'paused','stopped'},'Diagnostic study must be terminal.')
    _require(not any(row['status'] in {'sending','received'} for row in rows),'Unknown native request blocks capture.')
    _require(state['new_fits']==0,'Diagnostic study must not fit.')
    bound,trace=_bind_native(loop,state,spec,rows,context_builder=diagnostic_research.project_context,scope_fields=('source_snapshot_sha256','scope'))
    _require(bound=={action['id'] for action in state['actions']},'All prior actions must bind actual native calls.')
    with loop.study._connect() as con:config,current,actions=loop.study._state(con)
    _require(current==state,'Diagnostic state changed during capture.')
    original=loop.study._source(config)
    _require(original['snapshot_sha256']==state['source_snapshot_sha256'] and original['scope']==state['scope'],'Diagnostic source scope changed.')
    _require(_db_identities(root)==before,'Diagnostic journal changed during capture.')
    prior={'configuration_sha256':state['configuration_sha256'],'status':state['status'],'actions':copy.deepcopy(actions),'native_trace':trace,
           'invalid_requests':[_invalid_call(row) for row in rows if row['status']=='invalid'],
           'controller_status':project['status'],'max_requests':spec['max_requests'],'new_fits':0}
    payload={'schema_version':'p02-diagnostic-followup-source-v1','original_source':original,'prior_study':prior,'scope':copy.deepcopy(state['scope'])}
    payload['summary']=_summary(payload);payload['snapshot_sha256']=fingerprint(payload);validate_source(payload);return payload


def _summary(payload):
    prior=payload['prior_study'];original=payload['original_source'];actions=prior['actions']
    chemistry=next((a for a in actions if a['action']=='inspect_residuals' and a['parameters'].get('dimension')=='chemistry'),None)
    comparison=next((a for a in actions if a['action']=='compare_policies'),None)
    candidate={};secondary={}
    if chemistry:
        for policy,values in chemistry['result']['summary']['policies'].items():
            methods=values['methods'];row=methods['current_candidate']
            candidate[policy]={k:copy.deepcopy(row[k]) for k in ('n','mae','signed_bias','delta_mae_vs_chemistry','worse_groups','better_groups','tied_groups','group_count','worst_groups','worst_groups_limit','top5_absolute_error_share','top5_absolute_error_group_count','top5_absolute_error_n')}
            secondary[policy]={name:{k:copy.deepcopy(methods[name][k]) for k in ('n','mae','signed_bias','delta_mae_vs_chemistry')} for name in ('chemistry','additive','interaction_alpha1')}
    contrasts=[copy.deepcopy(c) for c in comparison['result']['summary']['contrasts'] if c['method']=='current_candidate'] if comparison else []
    return {'candidate_id':original['summary']['candidate_id'],'candidate_alpha':original['summary']['alpha'],
            'candidate_first_same_policy_chemistry_groups':candidate,'secondary_method_totals':secondary,'candidate_policy_contrasts':contrasts,
            'chemistry_analysis_action_id':chemistry['id'] if chemistry else None,'policy_comparison_action_id':comparison['id'] if comparison else None,
            'topography_available':not any(a['action']=='inspect_residuals' and a['parameters'].get('dimension')=='topography' for a in actions),
            'invalid_requests':[{'ordinal':i['ordinal'],'error_code':i['error_code'],'tool_names':[c['tool_name'] for c in i['tool_calls']]} for i in prior['invalid_requests']],
            'policy_labels':{'positive':'Count > 0; not positive biological response','recorded':'includes finite zero-count records','equal_batch':'batch aggregation','equal_section':'section aggregation'},
            'interpretation':'Counts compare candidate MAE with chemistry baseline within the same processing policy. Worst groups rank signed delta MAE, not intrinsic or biological difficulty. Top-five share ranks groups by total absolute error, including their sample counts. Policy target shifts do not select a winning policy.',
            'limitations':copy.deepcopy(original['summary']['limitations']),'new_fits':0,'scientific_validation':False}


def validate_source(payload):
    _require(type(payload) is dict and payload.get('schema_version')=='p02-diagnostic-followup-source-v1' and payload.get('snapshot_sha256')==fingerprint({k:v for k,v in payload.items() if k!='snapshot_sha256'}),'Followup snapshot changed.')
    original=payload['original_source'];residual_diagnostics.validate_source(original);prior=payload['prior_study'];actions=prior['actions'];trace=prior['native_trace']
    _require(payload['scope']==original['scope'] and prior['status'] in {'paused','stopped'} and prior['new_fits']==0,'Frozen scope, status or fit count changed.')
    _require(type(actions) is list and type(trace) is list and len(trace)<=prior['max_requests'] and all(t['status'] in {'applied','invalid'} for t in trace),'Native trace incomplete or unknown.')
    ids=[]
    for ordinal,action in enumerate(actions,1):
        _require(action['ordinal']==ordinal and action['id'] not in ids and fingerprint(action['result'])==action['result_sha256'] and set(ACTION_FIELDS)<=set(action),'Prior action identity changed.')
        ids.append(action['id'])
        if action['action'] in {'inspect_residuals','compare_policies'}:
            _require(action['result'].get('source_snapshot_sha256')==original['snapshot_sha256'],'Prior result belongs to another source.')
    _require([t['ordinal'] for t in trace]==list(range(1,len(trace)+1)) and [t['action_id'] for t in trace if t['status']=='applied']==ids,'Native applied action binding changed.')
    invalid=[t['ordinal'] for t in trace if t['status']=='invalid']
    _require([x['ordinal'] for x in prior['invalid_requests']]==invalid,'Invalid request trace changed.')
    _require(payload['summary']==_summary(payload) and len(canonical(payload['summary']).encode('utf-8'))<=16000,'Decision summary changed or exceeds bound.')


def decision_summary(payload):
    validate_source(payload);return copy.deepcopy(payload['summary'])


def inspect_topography(payload):
    validate_source(payload)
    _require(payload['summary']['topography_available'],'Topography diagnostic was already completed.')
    return residual_diagnostics.inspect_residuals(payload['original_source'],'topography')
