"""Bounded post-run model proposals and conditional memory; never runs fits."""
import copy
import hashlib
import json
import os
from pathlib import Path

from . import c01_cloud_loop, c01_local_loop, c01_native_tools, ollama_cloud, windows_network, contracts, chemotopo_data, research_memory
from .c01_research import C01Research, ACTION_FIELDS
from .c01_cloud_loop import C01CloudLoop, cloud_identity
from .c01_local_loop import C01LocalLoop
from .contracts import ResearchError, canonical, fingerprint, identifier
from .local_ollama import require

MAX_SOURCE_BYTES=5_000_000
TEXT_FIELDS=('hypothesis','next_check','success_criterion','failure_criterion')
CHOICES=('continue_regularization','change_hypothesis','stop_direction')


def evidence_module():
    from . import postrun_evidence
    return postrun_evidence


def code_identity():
    return hashlib.sha256(Path(__file__).read_bytes()+Path(evidence_module().__file__).read_bytes()+Path(research_memory.__file__).read_bytes()).hexdigest()


def source_ids(payload):
    return [item['action_id'] for item in payload['facts']]


def validate_request(request,state):
    if type(request) is not dict or set(request)!=ACTION_FIELDS: raise ResearchError('INVALID_DECISION','Exact native envelope required.')
    identifier(request['request_id'])
    if request['observation_sha256']!=state['observation_sha256']: raise ResearchError('STALE_OBSERVATION','Use current observation.')
    if type(request['reason']) is not str or not 1<=len(request['reason'].strip())<=2000: raise ResearchError('INVALID_DECISION','Bounded reason required.')
    if request['source_citation_ids']!=['p02-current-iteration']: raise ResearchError('INVALID_EVIDENCE','Cite the frozen current iteration.')
    ids=request['evidence_action_ids'];known=[a['id'] for a in state['actions']]
    if type(ids) is not list or any(type(x) is not str for x in ids) or len(ids)!=len(set(ids)) or not set(ids)<=set(known) or (known and known[-1] not in ids): raise ResearchError('INVALID_EVIDENCE','Cite latest current postrun action.')
    action=request['action'];params=request['parameters'];done={a['action'] for a in state['actions']}
    if action=='propose_next':
        if 'propose_next' in done or type(params) is not dict or set(params)!={'choice','source_action_ids',*TEXT_FIELDS} or params['choice'] not in CHOICES: raise ResearchError('INVALID_REQUEST','One structured proposal is permitted.')
        if any(type(params[k]) is not str or not 1<=len(params[k].strip())<=1000 for k in TEXT_FIELDS): raise ResearchError('INVALID_REQUEST','Proposal text must be bounded.')
        sources=params['source_action_ids']
        if type(sources) is not list or not 1<=len(sources)<=4 or any(type(x) is not str for x in sources) or len(sources)!=len(set(sources)) or not set(sources)<=set(state['source_action_ids']): raise ResearchError('INVALID_EVIDENCE','Cite actual source candidate action IDs.')
    elif action=='remember_observations':
        if params!={} or 'propose_next' not in done or action in done: raise ResearchError('ACTION_NOT_AVAILABLE','Remember requires one proposal and no previous remember.')
    elif action=='recall_observations':
        if params!={} or 'remember_observations' not in done or action in done: raise ResearchError('ACTION_NOT_AVAILABLE','Recall requires completed remember and occurs at most once.')
    elif action not in {'pause','stop'} or params!={}: raise ResearchError('ACTION_NOT_AVAILABLE','Unknown action.')


def parse_decision(content,state,request_id):
    value=json.loads(content)
    if type(value) is not dict or 'request_id' in value: raise ResearchError('INVALID_DECISION','Runner owns request identity.')
    result={'request_id':request_id,**value};validate_request(result,state);return result


class PostrunStudy(C01Research):
    def __init__(self,workspace):
        super().__init__(workspace);self.db=self.root/'postrun-study.sqlite'

    def create(self,source_study,baseline_publication_directory,memory_workspace,goal,max_requests=6):
        if type(goal) is not str or not 1<=len(goal.strip())<=2000 or type(max_requests) is not int or not 2<=max_requests<=6: raise ResearchError('INVALID_REQUEST','Bounded goal and 2..6 requests required.')
        self._guard()
        if self.root.exists() and any(self.root.iterdir()): raise ResearchError('ALREADY_EXISTS','New workspace required.')
        root=self.root.resolve();memory=Path(memory_workspace).absolute().resolve()
        for loc in (source_study,baseline_publication_directory,memory):
            path=Path(loc).absolute().resolve()
            if root==path or root.is_relative_to(path) or path.is_relative_to(root): raise ResearchError('UNSAFE_PATH','Postrun workspace must be separate from sources and memory.')
        for loc in (source_study,baseline_publication_directory):
            path=Path(loc).absolute().resolve()
            if memory==path or memory.is_relative_to(path) or path.is_relative_to(memory): raise ResearchError('UNSAFE_PATH','Memory workspace must be separate from sources.')
        payload=evidence_module().prepare_source(source_study,baseline_publication_directory)
        raw=canonical(payload).encode();research_memory.validate_scope(payload['scope']);source_ids(payload)
        if not 0<len(raw)<=MAX_SOURCE_BYTES: raise ResearchError('INVALID_REQUEST','Source snapshot exceeds bound.')
        config={'schema':'p02-postrun-study-v1','goal':goal,'max_requests':max_requests,'source_sha256':hashlib.sha256(raw).hexdigest(),'source_bytes':len(raw),'code_sha256':code_identity(),'memory_workspace':str(memory),'private_sources':{'study':str(Path(source_study).absolute()),'baseline':str(Path(baseline_publication_directory).absolute())}}
        self.root.mkdir(parents=True,exist_ok=True)
        with (self.root/'source.json').open('xb') as stream: stream.write(raw);stream.flush();os.fsync(stream.fileno())
        with self.db.open('xb'):pass
        with self._connect(True) as con:
            con.executescript('CREATE TABLE meta(config TEXT NOT NULL,sha256 TEXT NOT NULL,status TEXT NOT NULL);CREATE TABLE actions(ordinal INTEGER PRIMARY KEY,id TEXT UNIQUE,request_id TEXT UNIQUE,request_sha256 TEXT,record TEXT);CREATE TABLE imports(request_id TEXT PRIMARY KEY,status TEXT NOT NULL);')
            con.execute('INSERT INTO meta VALUES(?,?,?)',(canonical(config),fingerprint(config),'active'))
        return self.observe()

    def _source(self,config):
        return json.loads(chemotopo_data._captured(self.root/'source.json',config['source_sha256'],config['source_bytes']))

    def _state(self,con):
        row=con.execute('SELECT * FROM meta').fetchone();config=json.loads(row['config'])
        if fingerprint(config)!=row['sha256'] or config['code_sha256']!=code_identity(): raise ResearchError('CODE_CHANGED','Frozen configuration or code changed.')
        payload=self._source(config);actions=[]
        for row_action in con.execute('SELECT * FROM actions ORDER BY ordinal'):
            a=json.loads(row_action['record'])
            if a['ordinal']!=len(actions)+1 or a['ordinal']!=row_action['ordinal'] or a['id']!=row_action['id'] or a['request_id']!=row_action['request_id'] or fingerprint({k:a[k] for k in ACTION_FIELDS})!=row_action['request_sha256'] or fingerprint(a['result'])!=a['result_sha256']: raise ResearchError('EVIDENCE_CHANGED','Stored action changed.')
            actions.append(a)
        memory=research_memory.ResearchMemory(config['memory_workspace']).recall(payload['scope'],limit=8)
        pending=con.execute("SELECT request_id FROM imports WHERE status='pending'").fetchall()
        state={'schema_version':config['schema'],'configuration_sha256':row['sha256'],'status':row['status'],'goal':config['goal'],'source_snapshot_sha256':payload['snapshot_sha256'],'scope':payload['scope'],'facts':payload['facts'],'source_action_ids':source_ids(payload),'prior_evidence':payload['view'].get('prior_evidence',{}),'actions':actions,'memory_context':memory,'citations':[{'citation_id':'p02-current-iteration','source_sha256':payload['snapshot_sha256']}],'pending_import':bool(pending),'max_requests':config['max_requests'],'scientific_validation':False}
        state['observation_sha256']=fingerprint(state);return config,state,actions

    def observe(self):
        with self._connect() as con:return self._state(con)[1]

    def _finish(self,record,replayed,config):
        if record['action']=='remember_observations':
            try:
                research_memory.ResearchMemory(config['memory_workspace'])._import_derived(record['result']['derived'])
                with self._connect(True) as con: con.execute("UPDATE imports SET status='complete' WHERE request_id=?",(record['request_id'],))
            except Exception as error: raise ResearchError('EVIDENCE_CHANGED','Memory import pending; replay the same request to recover.') from error
        return {'action':record,'replayed':replayed}

    def apply(self,request):
        if type(request) is not dict: raise ResearchError('INVALID_DECISION','Request object required.')
        digest=fingerprint(request)
        with self._connect(True) as con:
            con.execute('BEGIN IMMEDIATE');config,state,actions=self._state(con)
            old=con.execute('SELECT * FROM actions WHERE request_id=?',(request.get('request_id'),)).fetchone()
            if old:
                if old['request_sha256']!=digest: raise ResearchError('IDEMPOTENCY_CONFLICT','Request differs from original.')
                record=json.loads(old['record']);replayed=True
            else:
                if state['pending_import']: raise ResearchError('EVIDENCE_CHANGED','Pending memory import must be recovered first.')
                validate_request(request,state)
                if state['status']!='active': raise ResearchError('NOT_ACTIVE','Study is terminal.')
                action=request['action']
                if action=='propose_next':result={'model_assertion':copy.deepcopy(request['parameters']),'assertion_verified':False,'scientific_validation':False}
                elif action=='remember_observations':
                    proposal=next(a for a in actions if a['action']=='propose_next');derived=evidence_module().derive_entries(self._source(config),proposal)
                    result={'derived':derived,'entry_ids':[v['id'] for v in derived['entries']],'scope':derived['scope'],'persistence':'conditional memory imported idempotently','scientific_validation':False}
                    con.execute("INSERT INTO imports VALUES(?,'pending')",(request['request_id'],))
                elif action=='recall_observations':result=research_memory.ResearchMemory(config['memory_workspace']).recall(state['scope'],limit=8)
                else:result={'decision':action,'fits_executed':0,'scientific_validation':False}
                record={**copy.deepcopy(request),'id':'p02post-'+fingerprint({'request_id':request['request_id'],'request_sha256':digest})[:32],'ordinal':len(actions)+1,'result':result,'result_sha256':fingerprint(result)}
                con.execute('INSERT INTO actions VALUES(?,?,?,?,?)',(record['ordinal'],record['id'],request['request_id'],digest,canonical(record)))
                if action in {'pause','stop'}:con.execute('UPDATE meta SET status=?',('paused' if action=='pause' else 'stopped',))
                replayed=False
        return self._finish(record,replayed,config)

SYSTEM='''You choose a bounded postrun research proposal, not an experiment. Actual candidate facts are from the sealed current iteration; prior iteration results are historical, never actions in this study. Choose continue_regularization, change_hypothesis, or stop_direction only if justified; an unchanged baseline may remain better. Proposal reasoning, hypotheses and criteria are model assertions, not validated facts. Remember and recall are explicit optional tools. No fit, code execution, budget increase, biological validation, or LLM weight training occurs. Cite p02-current-iteration and actual candidate source_action_ids for a proposal; evidence_action_ids refer only to current postrun actions and include the latest. You may stop or pause without proposing or remembering. Return one offered tool call; arguments are not repaired.'''


def schema_for(state,terminal=False):
    done={a['action'] for a in state['actions']};available=['pause','stop']
    if not terminal and not state['pending_import']:
        if 'propose_next' not in done and state['source_action_ids']:available.append('propose_next')
        if 'propose_next' in done and 'remember_observations' not in done:available.append('remember_observations')
        if 'remember_observations' in done and 'recall_observations' not in done:available.append('recall_observations')
    common={'observation_sha256':{'type':'string','enum':[state['observation_sha256']]},'reason':{'type':'string','minLength':1,'maxLength':2000},'source_citation_ids':{'type':'array','items':{'type':'string','enum':['p02-current-iteration']},'minItems':1,'maxItems':1,'uniqueItems':True},'evidence_action_ids':{'type':'array','items':{'type':'string','enum':[a['id'] for a in state['actions']]},'maxItems':6,'uniqueItems':True}}
    if state['actions']:common['evidence_action_ids']['contains']={'enum':[state['actions'][-1]['id']]}
    variants=[]
    for action in sorted(available):
        fields={}
        if action=='propose_next':
            fields={'choice':{'type':'string','enum':list(CHOICES)},**{k:{'type':'string','minLength':1,'maxLength':1000} for k in TEXT_FIELDS},'source_action_ids':{'type':'array','items':{'type':'string','enum':state['source_action_ids']},'minItems':1,'maxItems':min(4,len(state['source_action_ids'])),'uniqueItems':True}}
        props={**copy.deepcopy(common),'action':{'type':'string','enum':[action]},'parameters':{'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}}
        variants.append({'type':'object','properties':props,'required':list(props),'additionalProperties':False})
    return {'oneOf':variants}


def project_context(state,remaining,errors):
    def excerpt(value):
        raw=value.encode('utf-8');return {'excerpt':raw[:512].decode('utf-8','ignore'),'truncated':len(raw)>512}
    actions=[{'id':a['id'],'ordinal':a['ordinal'],'action':a['action'],'result_sha256':a['result_sha256'],'result':a['result'] if a['action']=='recall_observations' else ({'entry_ids':a['result']['entry_ids'],'scope':a['result']['scope']} if a['action']=='remember_observations' else ({'model_assertion':{k:excerpt(v) if isinstance(v,str) and k in TEXT_FIELDS else v for k,v in a['result']['model_assertion'].items()},'assertion_verified':False} if a['action']=='propose_next' else a['result'])),'reason':excerpt(a['reason'])} for a in state['actions']]
    return {'goal':state['goal'],'observation_sha256':state['observation_sha256'],'source_snapshot_sha256':state['source_snapshot_sha256'],'source_facts':state['facts'],'prior_evidence':state['prior_evidence'],'historical_notice':'Prior evidence is historical, not this study action; no scientific approval.','citations':state['citations'],'actions':actions,'memory_context':{'scope':state['scope'],'entries':[{'id':e['record']['id'],'inclusion_status':e['inclusion_status']} for e in state['memory_context']['entries']]},'remaining_model_requests':remaining,'previous_rejections':list(errors[-8:]),'scientific_validation':False}


class PostrunCloudLoop(C01CloudLoop):
    request_prefix='p02-postrun-'
    def __init__(self,workspace):
        self.study=PostrunStudy(workspace);self.db=self.study.root/'postrun-cloud.sqlite'
    def _state(self,con):return C01LocalLoop._state(self,con)
    def status(self):return C01LocalLoop.status(self)
    def configure(self,weights,*,max_requests=None):
        fixed=self.study.observe()['max_requests'];require(max_requests is None or max_requests==fixed,'CONFIG_CHANGED','Request limit is frozen.')
        return super().configure(weights,max_requests=fixed)
    def _code_identity(self):
        modules=(c01_cloud_loop,c01_local_loop,c01_native_tools,ollama_cloud,windows_network,contracts,research_memory)
        return hashlib.sha256((code_identity()+c01_local_loop.code_identity()).encode('ascii')+b''.join(Path(m.__file__).read_bytes() for m in modules)).hexdigest()
    def _specification(self,identity,observation,max_requests):
        return {'schema':'p02-postrun-native-cloud-v1','model_identity':cloud_identity(identity),'code_sha256':self._code_identity(),'study_sha256':observation['configuration_sha256'],'max_requests':max_requests,'max_output_tokens':2048,'prompt_token_evidence_cap':30720,'context_tokens':32768,'request_seconds':90,'max_request_bytes':65536,'reasoning_effort':ollama_cloud.THINKING,'included_credit_floor_usd':1.0,'credit_reserve_per_request_usd':.10,'purchased_credit_fallback':False,'provider_hard_spending_limit':False,'scientific_validation':False}
    def _request(self,observation,remaining,errors,spec):
        require(not observation['pending_import'],'EVIDENCE_CHANGED','Pending memory import must be recovered.')
        body={'model':ollama_cloud.MODEL,'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':canonical(project_context(observation,remaining,errors))}],'tools':c01_native_tools.tools_from_schema(schema_for(observation,remaining<=1)),'stream':False,'think':spec['reasoning_effort'],'keep_alive':0,'options':{'temperature':0,'num_ctx':spec['context_tokens'],'num_predict':spec['max_output_tokens']}}
        require(len(canonical(body).encode('utf-8'))<=spec['max_request_bytes'],'PROMPT_TOO_LARGE','Bounded native context required.');return body
    def _parse_decision(self,response,observation,request_id,body):return c01_native_tools.parse_tool_decision(response,observation,request_id,body,decision_parser=parse_decision)
