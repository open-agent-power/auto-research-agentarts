"""Protocol-driven, bounded numerical iteration with immutable prepared inputs."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import uuid

import numpy
import sklearn

from . import experiment_protocol, chemotopo_iteration_study, chemotopo_rebuild, chemotopo_data
from . import c01_cloud_loop, c01_local_loop, c01_native_tools, ollama_cloud, windows_network, contracts
from .c01_research import C01Research, ACTION_FIELDS
from .c01_cloud_loop import C01CloudLoop, cloud_identity
from .c01_local_loop import C01LocalLoop
from .contracts import ResearchError, canonical, fingerprint, identifier
from .local_ollama import require


MAX_INPUT_BYTES=10_000_000
MAX_ARTIFACT_BYTES=10_000_000


def code_identity():
    versions={'python':platform.python_version(),'numpy':numpy.__version__,'scikit_learn':sklearn.__version__}
    return hashlib.sha256((experiment_protocol.code_identity()+canonical(versions)).encode('utf-8')+Path(__file__).read_bytes()+Path(chemotopo_iteration_study.__file__).read_bytes()).hexdigest()


def _metrics(rows,predictions,prior):
    target=[r['target'] for r in rows];errors=[abs(a-b) for a,b in zip(target,predictions)]
    ry=chemotopo_rebuild._ranks(target);rp=chemotopo_rebuild._ranks(predictions)
    return {'pooled_mae':statistics.mean(errors),'pooled_rmse':math.sqrt(statistics.mean((a-b)**2 for a,b in zip(target,predictions))),
            'pooled_spearman_midrank':statistics.correlation(ry,rp) if len(set(ry))>1 and len(set(rp))>1 else None,
            'macro_fold_mae':statistics.mean(statistics.mean(errors[i] for i,r in enumerate(rows) if r['fold']==f) for f in range(1,36)),
            'r59_alpha1_mae':prior['interaction']['pooled_mae'],'r54_additive_mae':prior['additive']['pooled_mae'],
            'r54_chemistry_mae':prior['chemistry']['pooled_mae']}


def _validate_plan(inputs):
    """Check every frozen fold and chemistry before spending any candidate fits."""
    cohorts=[]
    for policy in inputs['policies']:
        rows=inputs['rows_by_policy'][policy];folds=inputs['folds_by_policy'][policy]
        keys=[(r['topography'],r['chemistry']) for r in rows]
        if len(rows)!=870 or len(set(keys))!=870 or len(folds)!=35:raise ResearchError('EVIDENCE_CHANGED','Frozen cohort or fold count changed.')
        if any(type(r.get('geometry')) is not list or len(r['geometry'])!=10 or any(type(v) not in (int,float) or not math.isfinite(v) for v in [r.get('target'),*r['geometry']]) for r in rows):
            raise ResearchError('EVIDENCE_CHANGED','Frozen numerical inputs are invalid.')
        groups=sorted({r['topography'] for r in rows})
        if len(groups)!=35:raise ResearchError('EVIDENCE_CHANGED','Frozen topography count changed.')
        for number,topography in enumerate(groups,1):
            held=[r for r in rows if r['topography']==topography];train=[r for r in rows if r['topography']!=topography];fold=folds[number-1]
            if (fold['fold']!=number or fold['held_out_topography']!=topography
                or fold['test_keys']!=[[r['topography'],r['chemistry']] for r in held]
                or fold['train_keys']!=[[r['topography'],r['chemistry']] for r in train]
                or any(r['fold']!=number for r in held) or not {r['chemistry'] for r in held}<={r['chemistry'] for r in train}):
                raise ResearchError('EVIDENCE_CHANGED','Frozen split or known-chemistry condition changed.')
        cohorts.append(set(keys))
    if len(cohorts)!=4 or any(keys!=cohorts[0] for keys in cohorts):raise ResearchError('EVIDENCE_CHANGED','Policy cohorts differ.')


def _compute(inputs,config,request,candidate):
    _validate_plan(inputs)
    output=[];folds={};metrics={}
    for policy in inputs['policies']:
        rows=inputs['rows_by_policy'][policy]
        predicted,ledger=chemotopo_iteration_study.candidate_predictions(rows,candidate['alpha'])
        if len(rows)!=870 or len(ledger)!=35:raise ResearchError('EVIDENCE_CHANGED','Candidate coverage differs from frozen input.')
        for actual,expected in zip(ledger,inputs['folds_by_policy'][policy]):
            if any(actual[k]!=expected[k] for k in ('fold','held_out_topography','train_keys','test_keys')):raise ResearchError('EVIDENCE_CHANGED','Candidate grouped folds differ from frozen input.')
        for row,value in zip(rows,predicted):output.append({'policy':policy,'topography':row['topography'],'chemistry':row['chemistry'],'fold':row['fold'],'target':row['target'],'prediction':value})
        folds[policy]=ledger;metrics[policy]=_metrics(rows,predicted,inputs['prior_evidence']['metrics'][policy])
    if len(output)!=3480:raise ResearchError('EVIDENCE_CHANGED','Incomplete candidate results.')
    summary={'candidate_id':candidate['id'],'alpha':candidate['alpha'],'fit_count':140,'metrics':metrics,
             'scientific_validation':False,'model_weight_training':False,
             'limits':['Fixed raw-red proxy and measured controls; not confirmed ALP, independent biological validation or final blind test.']}
    return {'schema_version':'configured-candidate-result-v1','request_sha256':fingerprint(request),'configuration_sha256':fingerprint(config),
            'inputs_sha256':config['inputs_sha256'],'candidate_id':candidate['id'],'alpha':candidate['alpha'],
            'summary':summary,'predictions':output,'folds':folds}


def _verify_output(value,inputs,config,request):
    candidates={c['id']:c for c in config['protocol']['candidates']};candidate=candidates[request['parameters']['candidate_id']]
    if (value.get('schema_version')!='configured-candidate-result-v1' or value.get('request_sha256')!=fingerprint(request)
        or value.get('configuration_sha256')!=fingerprint(config) or value.get('inputs_sha256')!=config['inputs_sha256']
        or value.get('candidate_id')!=candidate['id'] or value.get('alpha')!=candidate['alpha']):raise ResearchError('EVIDENCE_CHANGED','Candidate artifact identity changed.')
    summary=value.get('summary',{});output=value.get('predictions');folds=value.get('folds')
    if (type(output) is not list or len(output)!=3480 or type(folds) is not dict or set(folds)!=set(inputs['policies'])
        or summary.get('candidate_id')!=candidate['id'] or summary.get('alpha')!=candidate['alpha'] or summary.get('fit_count')!=140
        or summary.get('scientific_validation') is not False or summary.get('model_weight_training') is not False
        or set(summary.get('metrics',{}))!=set(inputs['policies'])):raise ResearchError('EVIDENCE_CHANGED','Candidate result shape changed.')
    seen=set()
    for policy in inputs['policies']:
        actual=sorted((v for v in output if v.get('policy')==policy),key=lambda v:(v['topography'],v['chemistry']))
        expected=sorted(inputs['rows_by_policy'][policy],key=lambda v:(v['topography'],v['chemistry']))
        if len(actual)!=870 or len(folds[policy])!=35:raise ResearchError('EVIDENCE_CHANGED','Candidate result coverage changed.')
        predictions=[]
        for row,source in zip(actual,expected):
            key=(policy,row['topography'],row['chemistry']);value_number=row['prediction']
            if key in seen or any(row[k]!=source[k] for k in ('topography','chemistry','fold','target')) or type(value_number) not in (int,float) or not math.isfinite(value_number):raise ResearchError('EVIDENCE_CHANGED','Candidate row differs from input.')
            seen.add(key);predictions.append(value_number)
        for actual_fold,source_fold in zip(folds[policy],inputs['folds_by_policy'][policy]):
            if any(actual_fold[k]!=source_fold[k] for k in ('fold','held_out_topography','train_keys','test_keys')):raise ResearchError('EVIDENCE_CHANGED','Candidate fold differs from input.')
        actual_metrics=_metrics(expected,predictions,inputs['prior_evidence']['metrics'][policy]);saved=summary['metrics'][policy]
        if set(actual_metrics)!=set(saved) or any(not ((v is None and saved[k] is None) or (v is not None and type(saved[k]) in (int,float) and math.isfinite(saved[k]) and math.isclose(v,saved[k],rel_tol=1e-10,abs_tol=1e-12))) for k,v in actual_metrics.items()):raise ResearchError('EVIDENCE_CHANGED','Candidate metric arithmetic differs.')
    if len(seen)!=3480:raise ResearchError('EVIDENCE_CHANGED','Candidate row identities differ.')


class ConfiguredStudy(C01Research):
    def __init__(self,workspace):
        super().__init__(workspace);self.db=self.root/'configured-study.sqlite'

    def create(self,source,baseline,interaction,protocol,prior_publication=None):
        protocol=experiment_protocol.validate_protocol(protocol);self._guard()
        if self.root.exists() and any(self.root.iterdir()):raise ResearchError('ALREADY_EXISTS','New workspace required.')
        root=self.root.resolve()
        for location in (source,baseline,interaction,prior_publication):
            if location is None:continue
            path=Path(location).absolute().resolve()
            if root==path or root.is_relative_to(path) or path.is_relative_to(root):raise ResearchError('UNSAFE_PATH','Workspace must be separate from evidence sources.')
        inputs=experiment_protocol.prepare_inputs(source,baseline,interaction,prior_publication=prior_publication)
        _validate_plan(inputs)
        payload=canonical(inputs).encode('utf-8')
        if not 0<len(payload)<=MAX_INPUT_BYTES:raise ResearchError('INVALID_REQUEST','Prepared input snapshot exceeds bound.')
        config={'schema':'configured-iteration-study-v1','protocol':protocol,'inputs_sha256':hashlib.sha256(payload).hexdigest(),
                'inputs_bytes':len(payload),'code_sha256':code_identity(),
                'private_sources':{'source':str(Path(source).absolute()),'baseline':str(Path(baseline).absolute()),
                                   'interaction':str(Path(interaction).absolute()),'prior_publication':str(Path(prior_publication).absolute()) if prior_publication else None}}
        self.root.mkdir(parents=True,exist_ok=True)
        with (self.root/'inputs.json').open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
        with self.db.open('xb'):pass
        with self._connect(True) as con:
            con.executescript('CREATE TABLE meta(config TEXT NOT NULL,sha256 TEXT NOT NULL,status TEXT NOT NULL);CREATE TABLE actions(ordinal INTEGER PRIMARY KEY,id TEXT UNIQUE,request_id TEXT UNIQUE,request_sha256 TEXT,record TEXT);CREATE TABLE reservations(request_id TEXT PRIMARY KEY,request_sha256 TEXT NOT NULL,request_json TEXT NOT NULL,candidate_id TEXT UNIQUE NOT NULL,status TEXT NOT NULL);')
            con.execute('INSERT INTO meta VALUES(?,?,?)',(canonical(config),fingerprint(config),'active'))
        return self.observe()

    def _inputs(self,config):
        size=config['inputs_bytes']
        if type(size) is not int or not 0<size<=MAX_INPUT_BYTES:raise ResearchError('EVIDENCE_CHANGED','Invalid input size.')
        return json.loads(chemotopo_data._captured(self.root/'inputs.json',config['inputs_sha256'],size))

    def _artifact_path(self,request_id):
        path=self.root/'artifacts'/hashlib.sha256(request_id.encode()).hexdigest()
        for item in (path,*path.parents):
            if item.is_symlink() or getattr(item,'is_junction',lambda:False)():raise ResearchError('UNSAFE_PATH','Artifact path cannot redirect.')
        return path

    def _read_complete(self,request,config,inputs):
        root=self._artifact_path(request['request_id'])
        try:
            from .chemotopo_experiment_evidence import _safe_file
            manifest=json.loads(_safe_file(root/'complete.json',10000))
            if (manifest.get('complete') is not True or manifest.get('request_sha256')!=fingerprint(request)
                or manifest.get('configuration_sha256')!=fingerprint(config) or manifest.get('inputs_sha256')!=config['inputs_sha256']
                or type(manifest.get('bytes')) is not int or not 0<manifest['bytes']<=MAX_ARTIFACT_BYTES):raise ValueError('invalid completion manifest')
            payload=chemotopo_data._captured(root/'result.json',manifest['sha256'],manifest['bytes']);value=json.loads(payload)
            _verify_output(value,inputs,config,request)
            return value,{'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)}
        except (OSError,ValueError,KeyError,TypeError,ResearchError):raise ResearchError('EVIDENCE_CHANGED','Candidate incomplete or invalid; no automatic rerun.') from None

    def _write_complete(self,request,config,inputs,value):
        root=self._artifact_path(request['request_id']);root.mkdir(parents=True,exist_ok=False)
        payload=canonical(value).encode('utf-8')
        if not 0<len(payload)<=MAX_ARTIFACT_BYTES:raise ResearchError('EVIDENCE_CHANGED','Candidate output exceeds bound.')
        with (root/'result.tmp').open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
        os.replace(root/'result.tmp',root/'result.json')
        manifest={'complete':True,'request_sha256':fingerprint(request),'configuration_sha256':fingerprint(config),
                  'inputs_sha256':config['inputs_sha256'],'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)}
        with (root/'complete.tmp').open('xb') as stream:stream.write(canonical(manifest).encode('utf-8'));stream.flush();os.fsync(stream.fileno())
        os.replace(root/'complete.tmp',root/'complete.json')
        return self._read_complete(request,config,inputs)

    def _state(self,con):
        meta=con.execute('SELECT * FROM meta').fetchone();config=json.loads(meta['config'])
        if fingerprint(config)!=meta['sha256'] or config['code_sha256']!=code_identity():raise ResearchError('CODE_CHANGED','Frozen protocol or code identity changed.')
        inputs=self._inputs(config);actions=[]
        for row in con.execute('SELECT * FROM actions ORDER BY ordinal'):
            action=json.loads(row['record'])
            if (action['ordinal']!=len(actions)+1 or action['ordinal']!=row['ordinal'] or action['id']!=row['id']
                or action['request_id']!=row['request_id'] or fingerprint({k:action[k] for k in ACTION_FIELDS})!=row['request_sha256']
                or fingerprint(action['result'])!=action['result_sha256']):raise ResearchError('EVIDENCE_CHANGED','Stored action changed.')
            if action['action']=='run_candidate':
                verified,artifact=self._read_complete({k:action[k] for k in ACTION_FIELDS},config,inputs)
                if verified['summary']!=action['result']['summary'] or artifact!=action['result']['artifact']:raise ResearchError('EVIDENCE_CHANGED','Action differs from candidate artifact.')
            actions.append(action)
        reservations=[dict(row) for row in con.execute('SELECT * FROM reservations ORDER BY rowid')]
        candidates={c['id'] for c in config['protocol']['candidates']}
        if len(reservations)*140>config['protocol']['max_fits'] or len(reservations)>len(candidates):raise ResearchError('EVIDENCE_CHANGED','Candidate reservation exceeds budget.')
        for item in reservations:
            saved=json.loads(item['request_json']);linked=next((a for a in actions if a['request_id']==item['request_id']),None)
            if (item['status'] not in {'started','committed'} or fingerprint(saved)!=item['request_sha256'] or saved.get('request_id')!=item['request_id']
                or saved.get('action')!='run_candidate' or saved.get('parameters',{}).get('candidate_id')!=item['candidate_id'] or item['candidate_id'] not in candidates
                or (item['status']=='committed')!=(linked is not None) or (linked and fingerprint({k:linked[k] for k in ACTION_FIELDS})!=item['request_sha256'])):
                raise ResearchError('EVIDENCE_CHANGED','Candidate reservation binding changed.')
        citations=[{'citation_id':'p02-r54','source_sha256':inputs['prior_evidence']['r54_manifest_sha256']},
                   {'citation_id':'p02-r59','source_sha256':inputs['prior_evidence']['r59_manifest_sha256']}]
        state={'schema_version':config['schema'],'configuration_sha256':meta['sha256'],'status':meta['status'],
               'protocol':config['protocol'],'inputs_sha256':config['inputs_sha256'],'prior_evidence':inputs['prior_evidence'],
               'limits':inputs['limits'],'citations':citations,'actions':actions,
               'reservations':[{'candidate_id':r['candidate_id'],'status':r['status']} for r in reservations],
               'budget':{'fits_reserved':len(reservations)*140,'max_fits':config['protocol']['max_fits']},
               'endpoint_gate':{'biological_fit_eligible':False,'numerical_proxy_fit_eligible':True,'ALP_eligible':False},
               'scientific_validation':False}
        state['observation_sha256']=fingerprint(state)
        return config,state,actions

    def observe(self):
        with self._connect() as con:return self._state(con)[1]

    def apply(self,request):
        if type(request) is not dict:raise ResearchError('INVALID_DECISION','Request object required.')
        digest=fingerprint(request);compute=False
        with self._connect(True) as con:
            con.execute('BEGIN IMMEDIATE');config,state,actions=self._state(con);inputs=self._inputs(config)
            old=con.execute('SELECT * FROM actions WHERE request_id=?',(request.get('request_id'),)).fetchone()
            if old:
                if old['request_sha256']!=digest:raise ResearchError('IDEMPOTENCY_CONFLICT','Request differs from committed action.')
                return {'action':json.loads(old['record']),'replayed':True}
            reservation=con.execute('SELECT * FROM reservations WHERE request_id=?',(request.get('request_id'),)).fetchone()
            if reservation:
                if reservation['request_sha256']!=digest:raise ResearchError('IDEMPOTENCY_CONFLICT','Request differs from reservation.')
            else:
                validate_request(request,state)
                if state['status']!='active':raise ResearchError('NOT_ACTIVE','Study is terminal.')
                if any(r['status']=='started' for r in state['reservations']):raise ResearchError('EVIDENCE_CHANGED','Previous candidate outcome unknown; no automatic rerun.')
                if request['action']=='run_candidate':
                    candidate_id=request['parameters']['candidate_id']
                    if any(r['candidate_id']==candidate_id for r in state['reservations']) or state['budget']['fits_reserved']+140>state['budget']['max_fits']:raise ResearchError('BUDGET_EXHAUSTED','Candidate already reserved or budget exhausted.')
                    con.execute('INSERT INTO reservations VALUES(?,?,?,?,?)',(request['request_id'],digest,canonical(request),candidate_id,'started'));compute=True
                else:
                    result={'decision':request['action'],'scientific_validation':False,'model_weight_training':False}
                    record={**copy.deepcopy(request),'id':'p02cfg-'+uuid.uuid4().hex,'ordinal':len(actions)+1,'result':result,'result_sha256':fingerprint(result)}
                    con.execute('INSERT INTO actions VALUES(?,?,?,?,?)',(record['ordinal'],record['id'],request['request_id'],digest,canonical(record)))
                    con.execute('UPDATE meta SET status=?',('paused' if request['action']=='pause' else 'stopped',))
                    return {'action':record,'replayed':False}
        if compute:
            candidate=next(c for c in config['protocol']['candidates'] if c['id']==request['parameters']['candidate_id'])
            try:self._write_complete(request,config,inputs,_compute(inputs,config,request,candidate))
            except Exception as error:raise ResearchError('EVIDENCE_CHANGED','Candidate interrupted or failed; reservation retained, no automatic rerun.') from error
        complete,artifact=self._read_complete(request,config,inputs)
        with self._connect(True) as con:
            con.execute('BEGIN IMMEDIATE');_,_,actions=self._state(con)
            old=con.execute('SELECT * FROM actions WHERE request_id=?',(request['request_id'],)).fetchone()
            if old:
                if old['request_sha256']!=digest:raise ResearchError('IDEMPOTENCY_CONFLICT','Committed request changed.')
                return {'action':json.loads(old['record']),'replayed':True}
            result={'summary':complete['summary'],'artifact':artifact}
            record={**copy.deepcopy(request),'id':'p02cfg-'+uuid.uuid4().hex,'ordinal':len(actions)+1,'result':result,'result_sha256':fingerprint(result)}
            con.execute('INSERT INTO actions VALUES(?,?,?,?,?)',(record['ordinal'],record['id'],request['request_id'],digest,canonical(record)))
            con.execute("UPDATE reservations SET status='committed' WHERE request_id=? AND status='started'",(request['request_id'],))
        return {'action':record,'replayed':False}


def validate_request(request,state):
    if type(request) is not dict or set(request)!=ACTION_FIELDS:raise ResearchError('INVALID_DECISION','Exact native envelope required.')
    identifier(request['request_id'])
    if request['observation_sha256']!=state['observation_sha256']:raise ResearchError('STALE_OBSERVATION','Use current observation.')
    if type(request['reason']) is not str or not 1<=len(request['reason'].strip())<=2000:raise ResearchError('INVALID_DECISION','Bounded reason required.')
    action=request['action'];params=request['parameters']
    if action=='run_candidate':
        if type(params) is not dict or set(params)!={'candidate_id'} or type(params['candidate_id']) is not str or params['candidate_id'] not in {c['id'] for c in state['protocol']['candidates']}:raise ResearchError('INVALID_REQUEST','Candidate ID must come from frozen protocol.')
    elif action not in {'pause','stop'} or params!={}:raise ResearchError('ACTION_NOT_AVAILABLE','Only frozen candidates and controls are available.')
    source=request['source_citation_ids'];actions=request['evidence_action_ids'];known_source={c['citation_id'] for c in state['citations']};known_actions={a['id'] for a in state['actions']}
    if type(source) is not list or any(type(v) is not str for v in source) or len(source)!=len(set(source)) or not {'p02-r54','p02-r59'}<=set(source) or not set(source)<=known_source:raise ResearchError('INVALID_EVIDENCE','Cite both frozen baseline sources only.')
    if type(actions) is not list or any(type(v) is not str for v in actions) or len(actions)!=len(set(actions)) or not set(actions)<=known_actions or (state['actions'] and state['actions'][-1]['id'] not in actions):raise ResearchError('INVALID_EVIDENCE','Cite current latest action ID.')


def parse_decision(content,state,request_id):
    value=json.loads(content)
    if type(value) is not dict or 'request_id' in value:raise ResearchError('INVALID_DECISION','Runner owns request identity.')
    request={'request_id':request_id,**value};validate_request(request,state);return request

SYSTEM='''You control a bounded configured numerical iteration. The goal and fixed
candidate menu were assigned by the operator; prior evidence, including any R61
observation, is historical input, not your action or a scientific verdict. Select
one offered candidate ID only if useful; prior results and actual new feedback must
inform your own decision. You may pause or stop without running any candidate.
Each candidate consumes 140 local Ridge fits, not LLM weight training. Do not
change parameters, data, evaluator, bounds or source paths. ALP identity is not
confirmed. This is exploratory on reused data and measured controls, not an
independent blind test, causal proof or clinical claim. Cite both p02-r54 and
p02-r59 as source IDs and the latest actual study action when one exists. Prior iteration snapshot IDs are historical context, never current action IDs. Return exactly one offered
native tool call; no arguments are repaired. Final request is control only.'''


def schema_for(state,terminal=False):
    reserved={v['candidate_id'] for v in state['reservations']}
    remaining=[c['id'] for c in state['protocol']['candidates'] if c['id'] not in reserved]
    available=['pause','stop']
    if not terminal and remaining and state['budget']['fits_reserved']+140<=state['budget']['max_fits']:available.append('run_candidate')
    actions=state['actions'];source_ids=[c['citation_id'] for c in state['citations']]
    common={'observation_sha256':{'type':'string','enum':[state['observation_sha256']]},
            'reason':{'type':'string','minLength':1,'maxLength':2000},
            'source_citation_ids':{'type':'array','items':{'type':'string','enum':source_ids},'minItems':2,'maxItems':len(source_ids),'uniqueItems':True,
                                   'description':'Cite both p02-r54 and p02-r59; prior iteration snapshot IDs are context, not action IDs.'},
            'evidence_action_ids':{'type':'array','items':{'type':'string','enum':[a['id'] for a in actions]},'maxItems':6,'uniqueItems':True,
                                   'description':'Only executed current action IDs; cite the latest when present.'}}
    if actions:common['evidence_action_ids']['contains']={'enum':[actions[-1]['id']]}
    variants=[]
    for action in sorted(available):
        fields={'candidate_id':{'type':'string','enum':remaining,'description':'An unreserved candidate ID from the frozen operator protocol.'}} if action=='run_candidate' else {}
        props={**copy.deepcopy(common),'action':{'type':'string','enum':[action]},'parameters':{'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}}
        variants.append({'type':'object','properties':props,'required':list(props),'additionalProperties':False,
                         'description':'Execute one fixed candidate and reserve 140 numerical fits.' if action=='run_candidate' else 'Record your own control decision without fitting.'})
    return {'oneOf':variants}


def project_context(state,remaining,errors):
    def excerpt(value):
        raw=value.encode('utf-8');return {'excerpt':raw[:768].decode('utf-8','ignore'),'truncated':len(raw)>768}
    actions=[{'id':a['id'],'ordinal':a['ordinal'],'action':a['action'],'parameters':a['parameters'],
              'result_sha256':a['result_sha256'],'summary':a['result'].get('summary',a['result']),'reason':excerpt(a['reason'])} for a in state['actions']]
    return {'goal':state['protocol']['goal'],'observation_sha256':state['observation_sha256'],
            'frozen_protocol':state['protocol'],'inputs_sha256':state['inputs_sha256'],
            'prior_evidence':state['prior_evidence'],'prior_evidence_notice':'Historical, source-bound observation; model reasoning is not a verified scientific fact.',
            'actions':actions,'citations':state['citations'],'latest_action_id':actions[-1]['id'] if actions else None,
            'budget':{**state['budget'],'remaining_model_requests':remaining},'reservations':state['reservations'],
            'endpoint_gate':state['endpoint_gate'],'limits':state['limits'],'previous_rejections':list(errors[-8:]),'scientific_validation':False}


class ConfiguredCloudLoop(C01CloudLoop):
    request_prefix='p02-configured-'
    def __init__(self,workspace):
        self.study=ConfiguredStudy(workspace);self.db=self.study.root/'configured-cloud.sqlite'
    def _state(self,con):return C01LocalLoop._state(self,con)
    def status(self):return C01LocalLoop.status(self)
    def configure(self,weights,*,max_requests=None):
        fixed=self.study.observe()['protocol']['max_requests']
        require(max_requests is None or max_requests==fixed,'CONFIG_CHANGED','Request limit is frozen in protocol.')
        return super().configure(weights,max_requests=fixed)
    def _code_identity(self):
        modules=(c01_cloud_loop,c01_local_loop,c01_native_tools,ollama_cloud,windows_network,contracts)
        return hashlib.sha256((code_identity()+c01_local_loop.code_identity()).encode('ascii')+b''.join(Path(m.__file__).read_bytes() for m in modules)).hexdigest()
    def _specification(self,identity,observation,max_requests):
        return {'schema':'p02-configured-native-cloud-v1','model_identity':cloud_identity(identity),'code_sha256':self._code_identity(),
                'study_sha256':observation['configuration_sha256'],'max_requests':max_requests,'max_output_tokens':2048,
                'prompt_token_evidence_cap':30720,'context_tokens':32768,'request_seconds':90,'max_request_bytes':65536,
                'reasoning_effort':ollama_cloud.THINKING,'included_credit_floor_usd':1.0,'credit_reserve_per_request_usd':.10,
                'purchased_credit_fallback':False,'provider_hard_spending_limit':False,'scientific_validation':False}
    def _request(self,observation,remaining,errors,spec):
        require(not any(r['status']=='started' for r in observation['reservations']),'EVIDENCE_CHANGED','Unknown candidate outcome blocks new requests.')
        body={'model':ollama_cloud.MODEL,'messages':[{'role':'system','content':SYSTEM},
              {'role':'user','content':canonical(project_context(observation,remaining,errors))}],
              'tools':c01_native_tools.tools_from_schema(schema_for(observation,remaining<=1)),
              'stream':False,'think':spec['reasoning_effort'],'keep_alive':0,
              'options':{'temperature':0,'num_ctx':spec['context_tokens'],'num_predict':spec['max_output_tokens']}}
        require(len(canonical(body).encode('utf-8'))<=spec['max_request_bytes'],'PROMPT_TOO_LARGE','Bounded native context required.')
        return body
    def _parse_decision(self,response,observation,request_id,body):
        return c01_native_tools.parse_tool_decision(response,observation,request_id,body,decision_parser=parse_decision)
