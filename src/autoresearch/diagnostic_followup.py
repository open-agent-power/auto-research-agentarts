"""Named-tool followup over saved diagnostics; proposals remain unreviewed."""
import copy
import hashlib
import json
import os
from pathlib import Path

from . import diagnostic_research, chemotopo_data
from .c01_research import C01Research, ACTION_FIELDS
from .contracts import canonical, fingerprint, identifier, ResearchError
from .local_ollama import require

JUDGMENTS=('investigate_data_mapping','investigate_target_definition','investigate_feature_representation','recommend_stop_direction')


def evidence_module():
    from . import diagnostic_followup_evidence
    return diagnostic_followup_evidence


def code_identity():
    return hashlib.sha256(Path(__file__).read_bytes()+Path(evidence_module().__file__).read_bytes()
                          +diagnostic_research.code_identity().encode('ascii')).hexdigest()


def available_actions(state,terminal=False):
    available={'pause','stop'}
    if not terminal and not any(a['action'] in JUDGMENTS for a in state['actions']):
        if state['topography_available'] and not any(a['action']=='inspect_topography' for a in state['actions']):available.add('inspect_topography')
        if state['prior_analysis_count'] or any(a['action']=='inspect_topography' for a in state['actions']):available.update(JUDGMENTS)
    return available


def validate_request(request,state):
    require(type(request) is dict and set(request)==ACTION_FIELDS,'INVALID_DECISION','Exact host-bound envelope required.')
    identifier(request['request_id'])
    require(request['observation_sha256']==state['observation_sha256'],'STALE_OBSERVATION','Current observation required.')
    require(type(request['reason']) is str and 1<=len(request['reason'].strip())<=2000,'INVALID_DECISION','Bounded original reason required.')
    require(request['source_citation_ids']==['p02-diagnostic-followup-source']
            and request['evidence_action_ids']==([state['actions'][-1]['id']] if state['actions'] else []),
            'INVALID_EVIDENCE','Host must bind current source and latest current-study action.')
    action=request['action'];params=request['parameters']
    require(type(action) is str and action in available_actions(state),'ACTION_NOT_AVAILABLE','Named action is not available.')
    require(type(params) is dict,'INVALID_REQUEST','Exact named-tool fields required.')
    if action in JUDGMENTS:
        require(set(params)=={'finding','next_check'} and all(type(params[k]) is str and 1<=len(params[k].strip())<=1000 for k in params),
                'INVALID_REQUEST','Finding and next_check are bounded original text; no direction argument.')
    else:require(params=={},'INVALID_REQUEST','No domain parameters accepted.')


class DiagnosticFollowupStudy(C01Research):
    def __init__(self,workspace):
        super().__init__(workspace);self.db=self.root/'diagnostic-followup-study.sqlite'

    def create(self,diagnostic_workspace,goal,max_requests=4):
        require(type(goal) is str and 1<=len(goal.strip())<=2000 and type(max_requests) is int and 2<=max_requests<=4,
                'INVALID_REQUEST','Bounded goal and 2..4 cumulative requests required.')
        self._guard();root=self.root.resolve();source=Path(diagnostic_workspace).absolute().resolve()
        require(not self.root.exists() or not any(self.root.iterdir()),'ALREADY_EXISTS','Use a fresh followup workspace.')
        require(not(root==source or root.is_relative_to(source) or source.is_relative_to(root)),
                'UNSAFE_PATH','Followup workspace must be separate from prior diagnostics.')
        payload=evidence_module().prepare_source(diagnostic_workspace);evidence_module().validate_source(payload)
        summary=evidence_module().decision_summary(payload)
        require(type(summary) is dict and len(canonical(summary).encode('utf-8'))<=32_000,'EVIDENCE_CHANGED','Bounded prior diagnosis summary required.')
        raw=canonical(payload).encode('utf-8')
        require(0<len(raw)<=diagnostic_research.MAX_SOURCE_BYTES,'INVALID_REQUEST','Frozen source exceeds size bound.')
        config={'schema':'p02-diagnostic-followup-study-v1','goal':goal,'max_requests':max_requests,'code_sha256':code_identity(),
                'source_sha256':hashlib.sha256(raw).hexdigest(),'source_bytes':len(raw),
                'private_sources':{'diagnostic_workspace':str(Path(diagnostic_workspace).absolute())}}
        self.root.mkdir(parents=True,exist_ok=True)
        with (self.root/'source.json').open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        with self.db.open('xb'):pass
        with self._connect(True) as con:
            con.executescript('CREATE TABLE meta(config TEXT NOT NULL,sha256 TEXT NOT NULL,status TEXT NOT NULL);CREATE TABLE actions(ordinal INTEGER PRIMARY KEY,id TEXT UNIQUE,request_id TEXT UNIQUE,request_sha256 TEXT,record TEXT);')
            con.execute('INSERT INTO meta VALUES(?,?,?)',(canonical(config),fingerprint(config),'active'))
        return self.observe()

    def _source(self,config):
        payload=json.loads(chemotopo_data._captured(self.root/'source.json',config['source_sha256'],config['source_bytes']))
        evidence_module().validate_source(payload);return payload

    def _state(self,con):
        row=con.execute('SELECT * FROM meta').fetchone();config=json.loads(row['config'])
        require(fingerprint(config)==row['sha256'] and config['code_sha256']==code_identity(),'CODE_CHANGED','Frozen followup configuration changed.')
        payload=self._source(config);actions=[]
        for item in con.execute('SELECT * FROM actions ORDER BY ordinal'):
            a=json.loads(item['record'])
            require(a['ordinal']==len(actions)+1 and a['ordinal']==item['ordinal'] and a['id']==item['id']
                    and a['request_id']==item['request_id'] and fingerprint({k:a[k] for k in ACTION_FIELDS})==item['request_sha256']
                    and fingerprint(a['result'])==a['result_sha256'],'EVIDENCE_CHANGED','Stored followup action changed.')
            actions.append(a)
        prior=payload['prior_study']['actions'];summary=evidence_module().decision_summary(payload)
        require(type(summary) is dict and len(canonical(summary).encode('utf-8'))<=32_000,'EVIDENCE_CHANGED','Prior summary exceeds bound.')
        state={'schema_version':config['schema'],'configuration_sha256':row['sha256'],'status':row['status'],'goal':config['goal'],
               'source_snapshot_sha256':payload['snapshot_sha256'],'scope':payload['scope'],'prior_summary':summary,
               'prior_action_index':[{k:a[k] for k in ('id','ordinal','action','parameters','result_sha256')} for a in prior],
               'prior_analysis_count':sum(a['action'] in {'inspect_residuals','compare_policies'} for a in prior),
               'topography_available':summary['topography_available'],
               'citations':[{'citation_id':'p02-diagnostic-followup-source','source_sha256':payload['snapshot_sha256']}],
               'actions':actions,'max_requests':config['max_requests'],'new_fits':0,'scientific_validation':False}
        state['observation_sha256']=fingerprint(state);return config,state,actions

    def observe(self):
        with self._connect() as con:return self._state(con)[1]

    def apply(self,request):
        require(type(request) is dict,'INVALID_DECISION','Named-tool request required.');digest=fingerprint(request)
        with self._connect(True) as con:
            con.execute('BEGIN IMMEDIATE');config,state,actions=self._state(con)
            old=con.execute('SELECT * FROM actions WHERE request_id=?',(request.get('request_id'),)).fetchone()
            if old:
                require(old['request_sha256']==digest,'IDEMPOTENCY_CONFLICT','Request differs from committed action.')
                return {'action':json.loads(old['record']),'replayed':True}
            validate_request(request,state);require(state['status']=='active','NOT_ACTIVE','Study is terminal.')
            action=request['action']
            if action=='inspect_topography':result=evidence_module().inspect_topography(self._source(config))
            elif action in JUDGMENTS:
                result={'summary':{'named_tool':action,'model_assertion':copy.deepcopy(request['parameters']),
                                   'assertion_verified':False,'scientific_validation':False},
                        'assertion_verified':False,'scientific_validation':False}
            else:result={'summary':{'decision':action,'new_fits':0,'scientific_validation':False}}
            require(type(result) is dict and type(result.get('summary')) is dict
                    and len(canonical(result).encode('utf-8'))<=diagnostic_research.MAX_RESULT_BYTES
                    and len(canonical(result['summary']).encode('utf-8'))<=diagnostic_research.MAX_SUMMARY_BYTES,
                    'EVIDENCE_CHANGED','Followup result or summary exceeds bounds.')
            record={**copy.deepcopy(request),'id':'p02diagfollow-'+fingerprint({'request_id':request['request_id'],'request_sha256':digest})[:32],
                    'ordinal':len(actions)+1,'result':result,'result_sha256':fingerprint(result)}
            con.execute('INSERT INTO actions VALUES(?,?,?,?,?)',(record['ordinal'],record['id'],request['request_id'],digest,canonical(record)))
            if action in {'pause','stop'}:con.execute('UPDATE meta SET status=?',('paused' if action=='pause' else 'stopped',))
        return {'action':record,'replayed':False}


def host_binding(state):
    return {'observation_sha256':state['observation_sha256'],'source_citation_ids':['p02-diagnostic-followup-source'],
            'evidence_action_ids':[state['actions'][-1]['id']] if state['actions'] else [],
            'origin':'host_bound_execution_metadata','notice':'Host attaches source and latest IDs, not model-selected citations.'}


def tools_for(state,terminal=False):
    tools=[]
    for name in sorted(available_actions(state,terminal)):
        fields={'reason':{'type':'string','minLength':1,'maxLength':2000}}
        if name in JUDGMENTS:fields.update({k:{'type':'string','minLength':1,'maxLength':1000} for k in ('finding','next_check')})
        description=('Record one unreviewed finding and next check for this named direction; never execute it.' if name in JUDGMENTS
                     else 'Inspect saved residuals by topography once; no refitting or redoing chemistry/policy analysis.' if name=='inspect_topography'
                     else 'End this bounded followup with the original reason.')
        tools.append({'type':'function','function':{'name':name,'description':description,
                      'parameters':{'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}}})
    return tools


def project_context(state,remaining,errors):
    return {'goal':state['goal'],'observation_sha256':state['observation_sha256'],'source_snapshot_sha256':state['source_snapshot_sha256'],
            'scope':state['scope'],'prior_actual_diagnostics':state['prior_summary'],'prior_action_index':state['prior_action_index'],
            'actions':[{**{k:a[k] for k in ('id','ordinal','action','parameters','reason','result_sha256')},'summary':a['result']['summary']} for a in state['actions']],
            'host_binding':host_binding(state),'remaining_model_requests':remaining,'previous_rejections':list(errors[-8:]),
            'new_fits':0,'scientific_validation':False}


SYSTEM='''Choose a bounded followup based on the actual saved R75 diagnostics, not a new experiment.
Prior chemistry-group and policy-contrast analyses are already executed. Do not redo them;
only optional unseen topography analysis is offered. Prior invalid attempts remain invalid,
their model text is not repaired or scientific evidence. Candidate-first group counts and
policy labels are literal: positive means Count>0, not positive performance. Residual is
prediction minus target; contrasts are right minus left on changing targets, not a policy
leaderboard, measurement reliability, causal effect or confirmed ALP. No new fits, alpha
sweep, arbitrary code, paths or spending permission exists. Select one named investigation
or stop-direction recommendation with finding, next_check and reason. There is NO direction
argument. Each is an unreviewed assertion, never a verified fact or executed proposal. After
one judgment only pause/stop remains; any earlier step may also stop. Last request controls
are budget management, not scientific success. IDs are host-bound execution metadata from
saved observation, not model-selected citations or proof of reading. Return one offered
native tool with precisely its fields. Do not repair arguments or promote model prose.'''


def parse_compact(response,state,request_id,body):
    require(state['observation_sha256']==fingerprint({k:v for k,v in state.items() if k!='observation_sha256'}),'EVIDENCE_CHANGED','Observation changed.')
    try:
        context=json.loads(body['messages'][1]['content']);remaining=context['remaining_model_requests'];errors=context['previous_rejections']
        require(type(remaining) is int and 1<=remaining<=state['max_requests'] and type(errors) is list and all(type(v) is str for v in errors),
                'EVIDENCE_CHANGED','Invalid captured budget or errors.')
        require(len(body['messages'])==2 and body['messages'][0]=={'role':'system','content':SYSTEM}
                and context==project_context(state,remaining,errors) and body['tools']==tools_for(state,remaining<=1),
                'EVIDENCE_CHANGED','Captured context or offered named tools differ.')
    except (KeyError,ValueError,TypeError,IndexError):raise ResearchError('EVIDENCE_CHANGED','Invalid saved followup request.') from None
    message=response.get('message') if type(response) is dict else None;calls=message.get('tool_calls') if type(message) is dict else None
    require(type(calls) is list and len(calls)==1,'INVALID_TOOL_ARGUMENTS','Exactly one native call required.')
    call=calls[0];function=call.get('function') if type(call) is dict else None
    require(type(function) is dict and call.get('type','function')=='function','INVALID_TOOL_ARGUMENTS','Native named function required.')
    name=function.get('name');offered={t['function']['name']:t['function'] for t in body['tools']}
    require(type(name) is str and name in offered,'ACTION_NOT_AVAILABLE','Named tool was not offered.')
    args=function.get('arguments')
    require(type(args) is dict and set(args)==set(offered[name]['parameters']['required']),'INVALID_TOOL_ARGUMENTS','Exact named-tool arguments required.')
    binding=host_binding(state)
    request={'request_id':request_id,'action':name,'reason':args['reason'],'observation_sha256':binding['observation_sha256'],
             'source_citation_ids':binding['source_citation_ids'],'evidence_action_ids':binding['evidence_action_ids'],
             'parameters':{k:v for k,v in args.items() if k!='reason'}}
    validate_request(request,state);return request


class DiagnosticFollowupCloudLoop(diagnostic_research.DiagnosticCloudLoop):
    request_prefix='p02-diagnostic-followup-'
    def __init__(self,workspace):
        self.study=DiagnosticFollowupStudy(workspace);self.db=self.study.root/'diagnostic-followup-cloud.sqlite'
    def _code_identity(self):
        return hashlib.sha256((super()._code_identity()+code_identity()).encode('ascii')).hexdigest()
    def _specification(self,identity,observation,max_requests):
        return {**super()._specification(identity,observation,max_requests),'schema':'p02-diagnostic-followup-native-cloud-v1'}
    def _request(self,observation,remaining,errors,spec):
        body={'model':diagnostic_research.ollama_cloud.MODEL,'messages':[{'role':'system','content':SYSTEM},
              {'role':'user','content':canonical(project_context(observation,remaining,errors))}],
              'tools':tools_for(observation,remaining<=1),'stream':False,'think':spec['reasoning_effort'],'keep_alive':0,
              'options':{'temperature':0,'num_ctx':spec['context_tokens'],'num_predict':spec['max_output_tokens']}}
        require(len(canonical(body).encode('utf-8'))<=spec['max_request_bytes'],'PROMPT_TOO_LARGE','Bounded followup context required.')
        return body
    def _parse_decision(self,response,observation,request_id,body):return parse_compact(response,observation,request_id,body)
