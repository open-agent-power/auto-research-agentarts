"""Read-only, no-refit diagnostics of sealed grouped out-of-fold predictions."""
import copy
import hashlib
import json
import math
from pathlib import Path

from . import configured_iteration, prepared_continuation
from .c01_research import ACTION_FIELDS
from .chemotopo_experiment_evidence import _safe_file
from .chemotopo_iteration_report import read_iteration_artifacts
from .configured_iteration_view import _database_identities
from .contracts import ResearchError, canonical, fingerprint

METHODS=('chemistry','additive','interaction_alpha1','current_candidate')
CONTRASTS=(('zero_batch','recorded_equal_batch','positive_equal_batch'),('zero_section','recorded_equal_section','positive_equal_section'),('aggregation_recorded','recorded_equal_batch','recorded_equal_section'),('aggregation_positive','positive_equal_batch','positive_equal_section'))
LIMITATIONS=['Previously viewed grouped OOF predictions, not an independent blind test.', 'Measured within-section controls condition the targets; raw red proxy is not confirmed ALP.', 'Processing policies change targets; different-target MAE is not a policy leaderboard.', 'No spot-level noise, reliability, biological, causal or clinical conclusion; no new fits.']


def _require(condition,message):
    if not condition:raise ResearchError('EVIDENCE_CHANGED',message)


def _number(value):return type(value) in (int,float) and math.isfinite(value)


def prepare_source(source_study,iteration_directory):
    root=Path(source_study).absolute();directory=Path(iteration_directory).absolute();before=_database_identities(root)
    study=configured_iteration.ConfiguredStudy(root)
    with study._connect() as connection:config,state,actions=study._state(connection)
    _require(state['status']=='stopped','A stopped, sealed iteration is required.')
    inputs=study._inputs(config)
    view=json.loads(_safe_file(directory/'iteration.json',3_000_000));read_iteration_artifacts(directory,view)
    prepared_continuation.extend_inputs(inputs,state,view)
    completed=[a for a in actions if a['action']=='run_candidate']
    _require(len(completed)==1,'Exactly one completed candidate is required.')
    action=completed[0];candidate,artifact=study._read_complete({k:action[k] for k in ACTION_FIELDS},config,inputs)
    _require(artifact==action['result']['artifact'],'Candidate artifact differs from recorded action.')
    _require(_database_identities(root)==before,'Study changed while capturing source.')
    scope={'inputs_sha256':state['inputs_sha256'],'study_configuration_sha256':state['configuration_sha256'],
           'iteration_snapshot_sha256':view['snapshot_sha256'],'candidate_action_id':action['id'],
           'candidate_artifact_sha256':artifact['sha256'],'candidate_result_sha256':action['result_sha256']}
    payload={'schema_version':'p02-diagnostic-source-v1','iteration':view,'inputs':inputs,'candidate':candidate,'scope':scope,
             'summary':{'candidate_id':candidate['candidate_id'],'alpha':candidate['alpha'],'candidate_action_id':action['id'],
                        'candidate_metrics':copy.deepcopy(candidate['summary']['metrics']),'inputs_sha256':state['inputs_sha256'],
                        'iteration_snapshot_sha256':view['snapshot_sha256'],'candidate_artifact_sha256':artifact['sha256'],
                        'limitations':LIMITATIONS,'new_fits':0,'scientific_validation':False}}
    payload['snapshot_sha256']=fingerprint(payload);validate_source(payload);return payload


def validate_source(payload):
    _require(type(payload) is dict and payload.get('schema_version')=='p02-diagnostic-source-v1' and payload.get('snapshot_sha256')==fingerprint({k:v for k,v in payload.items() if k!='snapshot_sha256'}),'Diagnostic source snapshot changed.')
    inputs=payload['inputs'];candidate=payload['candidate'];view=payload['iteration'];scope=payload['scope']
    _require(view.get('snapshot_sha256')==fingerprint({k:v for k,v in view.items() if k!='snapshot_sha256'}) and view.get('status')=='stopped','Iteration identity or status changed.')
    _require(fingerprint(inputs)==scope['inputs_sha256']==view['inputs_sha256']==candidate['inputs_sha256'] and view['study_configuration_sha256']==scope['study_configuration_sha256']==candidate['configuration_sha256'] and view['snapshot_sha256']==scope['iteration_snapshot_sha256'],'Source input or configuration binding changed.')
    raw=canonical(candidate).encode('utf-8');_require(hashlib.sha256(raw).hexdigest()==scope['candidate_artifact_sha256'],'Candidate artifact hash changed.')
    acts=[a for a in view['actions'] if a['action']=='run_candidate'];_require(len(acts)==1,'Exactly one completed candidate required.')
    action=acts[0];_require(action['id']==scope['candidate_action_id'] and action['summary']==candidate['summary'] and action['result_sha256']==scope['candidate_result_sha256']==fingerprint({'summary':candidate['summary'],'artifact':{'sha256':scope['candidate_artifact_sha256'],'bytes':len(raw)}}),'Candidate action binding changed.')
    _require(candidate.get('schema_version')=='configured-candidate-result-v1' and candidate['candidate_id']==action['parameters']['candidate_id'],'Candidate identity changed.')
    _joined(payload)


def _joined(payload):
    inputs=payload['inputs'];predictions=payload['candidate']['predictions'];policies=inputs['policies']
    _require(type(policies) is list and len(policies)==4 and set(policies)=={p for _,left,right in CONTRASTS for p in (left,right)} and len(set(policies))==4,'Four exact policies required.')
    _require(type(predictions) is list,'Candidate predictions required.')
    result={};cohort=None
    for policy in policies:
        rows=inputs['rows_by_policy'][policy];seen={};actual={}
        for row in rows:
            key=(row['topography'],row['chemistry']);_require(key not in seen,'Duplicate frozen key.')
            _require(all(_number(row.get(k)) for k in ('target','chemistry_prediction','additive_prediction','interaction_prediction')),'Nonfinite frozen target or prediction.')
            seen[key]=row
        for row in predictions:
            if row.get('policy')!=policy:continue
            key=(row['topography'],row['chemistry']);_require(key not in actual and key in seen,'Candidate keys differ.')
            source=seen[key];_require(all(row[k]==source[k] for k in ('topography','chemistry','fold','target')) and _number(row.get('prediction')),'Candidate row differs from frozen target/fold.')
            actual[key]=row
        _require(seen and set(actual)==set(seen),'Candidate coverage differs from frozen keys.')
        keys=set(seen);_require(cohort is None or keys==cohort,'Policies require identical keys.');cohort=keys
        result[policy]={}
        for key in sorted(keys):
            row=seen[key];target=row['target'];values={'chemistry':row['chemistry_prediction'],'additive':row['additive_prediction'],'interaction_alpha1':row['interaction_prediction'],'current_candidate':actual[key]['prediction']}
            result[policy][key]={'policy':policy,'topography':key[0],'chemistry':key[1],'fold':row['fold'],'target':target,'predictions':values,'residuals':{k:v-target for k,v in values.items()}}
    _require(len(predictions)==sum(len(v) for v in result.values()),'Candidate rows include unknown policy or duplicates.')
    return result


def _mean(values):return math.fsum(values)/len(values)


def _stats(rows,method):
    residuals=[row['residuals'][method] for row in rows];errors=[abs(v) for v in residuals];reference=[abs(row['residuals']['chemistry']) for row in rows]
    return {'n':len(rows),'mae':_mean(errors),'signed_bias':_mean(residuals),'delta_mae_vs_chemistry':_mean(errors)-_mean(reference)}


def inspect_residuals(payload,dimension='topography'):
    _require(dimension in ('topography','chemistry'),'Only topography or chemistry grouping is permitted.');validate_source(payload);joined=_joined(payload);groups=[];rankings=[];policies={}
    for policy,lookup in joined.items():
        rows=list(lookup.values());values=sorted({r[dimension] for r in rows});methods={}
        for method in METHODS:
            grouped=[]
            for value in values:
                selected=[r for r in rows if r[dimension]==value];stats=_stats(selected,method);entry={'policy':policy,'method':method,dimension:value,**stats};groups.append(entry);grouped.append(entry)
            total=_stats(rows,method);deltas=[g['delta_mae_vs_chemistry'] for g in grouped];worst=sorted(grouped,key=lambda g:(-g['delta_mae_vs_chemistry'],g[dimension]))
            error_groups=sorted(grouped,key=lambda g:(-g['mae']*g['n'],g[dimension]));denominator=math.fsum(g['mae']*g['n'] for g in grouped)
            rankings.append({'policy':policy,'method':method,'worst5_delta':[copy.deepcopy(g) for g in worst[:5]],'top5_absolute_error_groups':[{'group':g[dimension],'n':g['n'],'absolute_error_sum':g['mae']*g['n']} for g in error_groups[:5]]})
            methods[method]={**total,'worse_groups':sum(d>1e-12 for d in deltas),'better_groups':sum(d < -1e-12 for d in deltas),'tied_groups':sum(abs(d)<=1e-12 for d in deltas),'group_count':len(grouped),'worst_groups':[ {dimension:g[dimension],'n':g['n'],'delta_mae_vs_chemistry':g['delta_mae_vs_chemistry']} for g in worst[:2]],'worst_groups_limit':2,'top5_absolute_error_share':math.fsum(g['mae']*g['n'] for g in error_groups[:5])/denominator if denominator else None,'top5_absolute_error_group_count':min(5,len(grouped)),'top5_absolute_error_n':sum(g['n'] for g in error_groups[:5])}
        policies[policy]={'methods':methods}
    summary={'dimension':dimension,'policies':policies,'groups_truncated':True,'limitations':LIMITATIONS,'new_fits':0,'scientific_validation':False}
    return {'schema_version':'p02-residual-diagnostics-v1','source_snapshot_sha256':payload['snapshot_sha256'],'dimension':dimension,'summary':summary,'groups':groups,'rankings':rankings,'rows':[v for policy in joined.values() for v in policy.values()]}


def compare_policies(payload):
    validate_source(payload);joined=_joined(payload);rows=[];contrasts=[]
    for name,left,right in CONTRASTS:
        for method in METHODS:
            records=[]
            for key in sorted(joined[left]):
                a=joined[left][key];b=joined[right][key]
                _require(a['fold']==b['fold'],'Paired policies disagree on fold.')
                row={'contrast':name,'left_policy':left,'right_policy':right,'method':method,'topography':key[0],'chemistry':key[1],'fold':a['fold'],
                     'left_target':a['target'],'right_target':b['target'],'target_shift':b['target']-a['target'],
                     'left_residual':a['residuals'][method],'right_residual':b['residuals'][method],'residual_shift':b['residuals'][method]-a['residuals'][method]}
                rows.append(row);records.append(row)
            contrasts.append({'contrast':name,'left_policy':left,'right_policy':right,'method':method,'paired_n':len(records),
                              'mean_target_shift':_mean([r['target_shift'] for r in records]),'mean_absolute_target_shift':_mean([abs(r['target_shift']) for r in records]),
                              'mean_residual_shift':_mean([r['residual_shift'] for r in records]),'left_mae':_mean([abs(r['left_residual']) for r in records]),'right_mae':_mean([abs(r['right_residual']) for r in records])})
    return {'schema_version':'p02-policy-diagnostics-v1','source_snapshot_sha256':payload['snapshot_sha256'],
            'summary':{'contrasts':contrasts,'limitations':LIMITATIONS,'new_fits':0,'scientific_validation':False},'rows':rows}
