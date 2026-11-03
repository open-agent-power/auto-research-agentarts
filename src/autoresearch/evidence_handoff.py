"""Bounded, source-bound evidence selection and external-task handoff."""
import copy
import hashlib
import json
import os
from pathlib import Path

from . import diagnostic_research, chemotopo_data, reasoning_profile
from .c01_research import C01Research, ACTION_FIELDS
from .contracts import ResearchError, canonical, fingerprint, identifier
from .local_ollama import require

MAX_CATALOG_BYTES=25_000_000


def catalog_module():
    from . import evidence_catalog
    return evidence_catalog


def code_identity():
    return hashlib.sha256(Path(__file__).read_bytes()+Path(catalog_module().__file__).read_bytes()+Path(reasoning_profile.__file__).read_bytes()+diagnostic_research.code_identity().encode('ascii')).hexdigest()


def _fact_index(catalog):return {f['id']:f for f in catalog['facts']}
def _task_index(catalog):return {t['id']:t for t in catalog['tasks']}


def available_actions(state,terminal=False):
    available={'pause','stop'}
    if state['status']!='active':return available
    unread=set(state['fact_ids'])-set(state['read_fact_ids'])
    if not terminal and unread:available.add('read_evidence')
    if any(set(t['required_fact_ids'])<=set(state['read_fact_ids']) for t in state['tasks']):available.add('record_next_step')
    return available


def validate_request(request,state):
    require(type(request) is dict and set(request)==ACTION_FIELDS,'INVALID_DECISION','Exact host-bound envelope required.')
    identifier(request['request_id'])
    require(request['observation_sha256']==state['observation_sha256'],'STALE_OBSERVATION','Current observation required.')
    require(type(request['reason']) is str and 1<=len(request['reason'].strip())<=2000,'INVALID_DECISION','Bounded original reason required.')
    require(request['source_citation_ids']==['p02-evidence-catalog'] and request['evidence_action_ids']==([state['actions'][-1]['id']] if state['actions'] else []),'INVALID_EVIDENCE','Host must bind catalog and latest action.')
    action=request['action'];params=request['parameters'];require(type(action) is str and action in available_actions(state),'ACTION_NOT_AVAILABLE','Choose an available tool.')
    require(type(params) is dict,'INVALID_REQUEST','Exact tool parameters required.')
    if action in {'read_evidence','record_next_step'}:
        require(set(params)==({'fact_ids'} if action=='read_evidence' else {'task_id','fact_ids'}),'INVALID_REQUEST','Exact model-selected fields required.')
        ids=params['fact_ids'];require(type(ids) is list and 1<=len(ids)<=8 and all(type(v) is str for v in ids) and len(set(ids))==len(ids) and set(ids)<=set(state['fact_ids']),'INVALID_EVIDENCE','Choose 1..8 distinct known fact IDs.')
        if action=='read_evidence':require(bool(set(ids)-set(state['read_fact_ids'])),'INVALID_REQUEST','Read must include at least one not-yet-read fact.')
        else:
            task=next((t for t in state['tasks'] if t['id']==params['task_id']),None)
            require(task is not None and set(ids)<=set(state['read_fact_ids']) and set(task['required_fact_ids'])<=set(ids),'INVALID_EVIDENCE','Task facts must be read and include all required IDs.')
    else:require(params=={},'INVALID_REQUEST','Control tool takes no other parameters.')


class EvidenceHandoffStudy(C01Research):
    def __init__(self,workspace):
        super().__init__(workspace);self.db=self.root/'evidence-handoff-study.sqlite'

    def create(self,diagnostic_directory,iteration_directory,baseline_directory,inventory,goal,max_requests=4):
        require(type(goal) is str and 1<=len(goal.strip())<=2000 and type(max_requests) is int and 2<=max_requests<=4,'INVALID_REQUEST','Bounded goal and 2..4 requests required.')
        self._guard();root=self.root.resolve()
        require(not self.root.exists() or not any(self.root.iterdir()),'ALREADY_EXISTS','Use a new handoff workspace.')
        for location in (diagnostic_directory,iteration_directory,baseline_directory,inventory):
            path=Path(location).absolute().resolve()
            require(not(root==path or root.is_relative_to(path) or path.is_relative_to(root)),'UNSAFE_PATH','Workspace must be separate from evidence.')
        catalog=catalog_module().build_catalog(diagnostic_directory,iteration_directory,baseline_directory,inventory);catalog_module().validate_catalog(catalog)
        require(all(1<=len(t['required_fact_ids'])<=8 for t in catalog['tasks']),'INVALID_REQUEST','Task must require 1..8 facts.')
        raw=canonical(catalog).encode('utf-8');require(0<len(raw)<=MAX_CATALOG_BYTES,'INVALID_REQUEST','Catalog exceeds size bound.')
        config={'schema':'p02-evidence-handoff-study-v1','goal':goal,'max_requests':max_requests,'code_sha256':code_identity(),
                'catalog_sha256':hashlib.sha256(raw).hexdigest(),'catalog_bytes':len(raw),
                'private_sources':{'diagnostic_directory':str(Path(diagnostic_directory).absolute()),'iteration_directory':str(Path(iteration_directory).absolute()),'baseline_directory':str(Path(baseline_directory).absolute()),'inventory':str(Path(inventory).absolute())}}
        self.root.mkdir(parents=True,exist_ok=True)
        with (self.root/'catalog.json').open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        with self.db.open('xb'):pass
        with self._connect(True) as con:
            con.executescript('CREATE TABLE meta(config TEXT NOT NULL,sha256 TEXT NOT NULL,status TEXT NOT NULL);CREATE TABLE actions(ordinal INTEGER PRIMARY KEY,id TEXT UNIQUE,request_id TEXT UNIQUE,request_sha256 TEXT,record TEXT);')
            con.execute('INSERT INTO meta VALUES(?,?,?)',(canonical(config),fingerprint(config),'active'))
        return self.observe()

    def _catalog(self,config):
        value=json.loads(chemotopo_data._captured(self.root/'catalog.json',config['catalog_sha256'],config['catalog_bytes']))
        catalog_module().validate_catalog(value);return value

    def _state(self,con):
        row=con.execute('SELECT * FROM meta').fetchone();config=json.loads(row['config'])
        require(fingerprint(config)==row['sha256'] and config['code_sha256']==code_identity(),'CODE_CHANGED','Frozen handoff configuration or code changed.')
        catalog=self._catalog(config);actions=[];read_ids=[]
        for item in con.execute('SELECT * FROM actions ORDER BY ordinal'):
            a=json.loads(item['record'])
            require(a['ordinal']==len(actions)+1 and a['ordinal']==item['ordinal'] and a['id']==item['id'] and a['request_id']==item['request_id'] and fingerprint({k:a[k] for k in ACTION_FIELDS})==item['request_sha256'] and fingerprint(a['result'])==a['result_sha256'],'EVIDENCE_CHANGED','Saved handoff action changed.')
            if a['action']=='read_evidence':
                facts=catalog_module().read_facts(catalog,a['parameters']['fact_ids'])
                require(a['result']['facts']==facts,'EVIDENCE_CHANGED','Read facts differ from frozen catalog.')
                for fact in facts:
                    if fact['id'] not in read_ids:read_ids.append(fact['id'])
            elif a['action']=='record_next_step':
                task=_task_index(catalog).get(a['parameters']['task_id']);ids=a['parameters']['fact_ids']
                require(task is not None and set(ids)<=set(read_ids) and set(task['required_fact_ids'])<=set(ids) and a['result']['task']==task and a['result']['cited_facts']==catalog_module().read_facts(catalog,ids) and a['result']['model_reason']==a['reason'],'EVIDENCE_CHANGED','Recorded handoff differs from read evidence and template.')
            actions.append(a)
        state={'schema_version':config['schema'],'configuration_sha256':row['sha256'],'status':row['status'],'goal':config['goal'],
               'catalog_snapshot_sha256':catalog['snapshot_sha256'],'fact_index':[{'id':f['id'],'label':f['label'],'kind':f['kind']} for f in catalog['facts']],
               'fact_ids':[f['id'] for f in catalog['facts']],'tasks':copy.deepcopy(catalog['tasks']),'read_fact_ids':read_ids,
               'citations':[{'citation_id':'p02-evidence-catalog','source_sha256':catalog['snapshot_sha256']}],
               'actions':actions,'max_requests':config['max_requests'],'new_fits':0,'scientific_validation':False}
        state['observation_sha256']=fingerprint(state);return config,state,actions

    def observe(self):
        with self._connect() as con:return self._state(con)[1]

    def apply(self,request):
        require(type(request) is dict,'INVALID_DECISION','Tool request required.');digest=fingerprint(request)
        with self._connect(True) as con:
            con.execute('BEGIN IMMEDIATE');config,state,actions=self._state(con)
            old=con.execute('SELECT * FROM actions WHERE request_id=?',(request.get('request_id'),)).fetchone()
            if old:
                require(old['request_sha256']==digest,'IDEMPOTENCY_CONFLICT','Original request differs.')
                return {'action':json.loads(old['record']),'replayed':True}
            validate_request(request,state);require(state['status']=='active','NOT_ACTIVE','Study is terminal.')
            action=request['action'];params=request['parameters']
            if action=='read_evidence':
                facts=catalog_module().read_facts(self._catalog(config),params['fact_ids'])
                result={'facts':facts,'fact_ids_from_tool_arguments':True,'scientific_validation':False}
            elif action=='record_next_step':
                catalog=self._catalog(config);task=copy.deepcopy(_task_index(catalog)[params['task_id']]);facts=catalog_module().read_facts(catalog,params['fact_ids'])
                result={'task':task,'cited_facts':facts,'model_reason':request['reason'],'task_and_fact_ids_from_tool_arguments':True,'reason_interpretation':'unreviewed_model_assertion',
                        'external_task_executed':False,'waiting_for_external_input':True,'scientific_validation':False}
            else:result={'decision':action,'new_fits':0,'scientific_validation':False}
            record={**copy.deepcopy(request),'id':'p02handoff-'+fingerprint({'request_id':request['request_id'],'request_sha256':digest})[:32],
                    'ordinal':len(actions)+1,'result':result,'result_sha256':fingerprint(result)}
            con.execute('INSERT INTO actions VALUES(?,?,?,?,?)',(record['ordinal'],record['id'],request['request_id'],digest,canonical(record)))
            if action in {'pause','stop','record_next_step'}:con.execute('UPDATE meta SET status=?',('paused' if action!='stop' else 'stopped',))
        return {'action':record,'replayed':False}


def host_binding(state):
    return {'observation_sha256':state['observation_sha256'],'source_citation_ids':['p02-evidence-catalog'],
            'evidence_action_ids':[state['actions'][-1]['id']] if state['actions'] else [],
            'origin':'host_bound_execution_metadata','notice':'Observation/source/latest-action metadata are host-bound; fact IDs and task ID are model-selected.'}


def tools_for(state,terminal=False):
    result=[]
    for action in sorted(available_actions(state,terminal)):
        fields={'reason':{'type':'string','minLength':1,'maxLength':2000}}
        if action=='read_evidence':fields['fact_ids']={'type':'array','items':{'type':'string','enum':state['fact_ids']},'minItems':1,'maxItems':8,'uniqueItems':True}
        if action=='record_next_step':
            ready=[t['id'] for t in state['tasks'] if set(t['required_fact_ids'])<=set(state['read_fact_ids'])]
            fields.update({'task_id':{'type':'string','enum':ready},'fact_ids':{'type':'array','items':{'type':'string','enum':state['read_fact_ids']},'minItems':1,'maxItems':8,'uniqueItems':True}})
        description={'read_evidence':'Read selected fact IDs and their exact source pointers. Include at least one unread fact.',
                     'record_next_step':'Choose a ready host-curated external task and the already-read supporting facts; save it and pause. It does not execute the task.',
                     'pause':'Pause without creating a handoff.','stop':'Stop without creating a handoff.'}[action]
        result.append({'type':'function','function':{'name':action,'description':description,'parameters':{'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}}})
    return result


def project_context(state,remaining,errors):
    return {'goal':state['goal'],'observation_sha256':state['observation_sha256'],'catalog_snapshot_sha256':state['catalog_snapshot_sha256'],
            'facts_available':state['fact_index'],'task_templates':state['tasks'],'read_fact_ids':state['read_fact_ids'],
            'actions':[{**{k:a[k] for k in ('id','ordinal','action','parameters','reason','result_sha256')},'result':a['result']} for a in state['actions']],
            'host_binding':host_binding(state),'remaining_model_requests':remaining,'previous_rejections':list(errors[-8:]),
            'limits':['Fact and task IDs are selected by the model; observation and execution citation IDs are host-bound.',
                      'Templates are operator-curated; recording does not execute external work or validate scientific claims.',
                      'The reason is an unreviewed model assertion; no inferred data, fit or independent biological validation.'],
            'new_fits':0,'scientific_validation':False}


SYSTEM='''Select useful evidence from the catalog and, if justified, one fixed external
handoff task. read_evidence explicitly chooses fact IDs and returns exact values and
provenance. record_next_step must choose a ready task and cite already-read fact IDs,
including all that task requires; the host supplies the fixed template, records your
unreviewed reason, and pauses for outside input. The task is not executed and there
is no new fitting, arbitrary analysis, external data retrieval or scientific approval.
Fact and task IDs are yours; observation/source/latest-action IDs are host metadata,
not model-selected citations. Never infer facts from IDs alone. You may pause or stop
at any time; final request permits an eligible task or control. Return exactly one
offered native tool with its exact fields, without extra arguments or repairs.'''


def parse_compact(response,state,request_id,body):
    require(state['observation_sha256']==fingerprint({k:v for k,v in state.items() if k!='observation_sha256'}),'EVIDENCE_CHANGED','Observation changed.')
    try:
        context=json.loads(body['messages'][1]['content']);remaining=context['remaining_model_requests'];errors=context['previous_rejections']
        require(type(remaining) is int and 1<=remaining<=state['max_requests'] and type(errors) is list and all(type(v) is str for v in errors),'EVIDENCE_CHANGED','Invalid captured budget or feedback.')
        require(len(body['messages'])==2 and body['messages'][0]=={'role':'system','content':SYSTEM} and context==project_context(state,remaining,errors) and body['tools']==tools_for(state,remaining<=1),'EVIDENCE_CHANGED','Captured context or tools differ.')
    except (KeyError,ValueError,TypeError,IndexError):raise ResearchError('EVIDENCE_CHANGED','Invalid saved handoff request.') from None
    message=response.get('message') if type(response) is dict else None;calls=message.get('tool_calls') if type(message) is dict else None
    require(type(calls) is list and len(calls)==1,'INVALID_TOOL_ARGUMENTS','Exactly one native call required.')
    call=calls[0];function=call.get('function') if type(call) is dict else None
    require(type(function) is dict and call.get('type','function')=='function','INVALID_TOOL_ARGUMENTS','Native function required.')
    name=function.get('name');offered={t['function']['name']:t['function'] for t in body['tools']}
    require(type(name) is str and name in offered,'ACTION_NOT_AVAILABLE','Tool not offered.')
    args=function.get('arguments');require(type(args) is dict and set(args)==set(offered[name]['parameters']['required']),'INVALID_TOOL_ARGUMENTS','Exact native arguments required.')
    binding=host_binding(state);request={'request_id':request_id,'action':name,'reason':args['reason'],'observation_sha256':binding['observation_sha256'],
             'source_citation_ids':binding['source_citation_ids'],'evidence_action_ids':binding['evidence_action_ids'],'parameters':{k:v for k,v in args.items() if k!='reason'}}
    validate_request(request,state);return request


class EvidenceHandoffCloudLoop(diagnostic_research.DiagnosticCloudLoop):
    request_prefix='p02-evidence-handoff-'
    def __init__(self,workspace):
        self.study=EvidenceHandoffStudy(workspace);self.db=self.study.root/'evidence-handoff-cloud.sqlite'
    def _code_identity(self):return hashlib.sha256((super()._code_identity()+code_identity()).encode('ascii')).hexdigest()
    def _specification(self,identity,observation,max_requests):
        return {**super()._specification(identity,observation,max_requests),'schema':'p02-evidence-handoff-native-cloud-v1','reasoning_effort':'high','max_output_tokens':4096,'prompt_token_evidence_cap':28672,'context_tokens':32768}
    def _request(self,observation,remaining,errors,spec):
        body={'model':diagnostic_research.ollama_cloud.MODEL,'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':canonical(project_context(observation,remaining,errors))}],
              'tools':tools_for(observation,remaining<=1),'stream':False,'think':spec['reasoning_effort'],'keep_alive':0,'options':{'temperature':0,'num_ctx':spec['context_tokens'],'num_predict':spec['max_output_tokens']}}
        require(len(canonical(body).encode('utf-8'))<=spec['max_request_bytes'],'PROMPT_TOO_LARGE','Bounded handoff context required.');return body
    def _parse_decision(self,response,observation,request_id,body):return parse_compact(response,observation,request_id,body)
