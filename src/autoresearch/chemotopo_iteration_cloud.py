"""Native cloud controller for isolated P02 regularization iteration."""
import copy
import hashlib
from pathlib import Path

from . import c01_cloud_loop, c01_local_loop, c01_native_tools, chemotopo_iteration_evidence, chemotopo_iteration_study, ollama_cloud, windows_network, contracts
from .c01_cloud_loop import C01CloudLoop, cloud_identity
from .c01_local_loop import C01LocalLoop
from .contracts import canonical
from .local_ollama import require

SYSTEM='''You control a bounded, isolated raw-red proxy numerical iteration.
R54 and R59 are prior operator-run evidence, not your work. R59 alpha1 interaction
had no support against additive MAE in four policies. You may choose one or both
fixed alpha10 and alpha100 candidates, or pause/stop without fitting. Each fit
executes 140 Ridge fits, not LLM weight training; no other alpha, dataset, feature,
or policy is available. Both retain R59 chemistry one-hot, ten train-standardized
geometry features, all main effects and chemistry-by-geometry interactions, with
35 held-out-topography folds under each of four policies; only penalty changes. Current feedback follows actual completed computation.
Cite both p02-r54 and p02-r59 in source_citation_ids; cite the latest current
study action in evidence_action_ids when one exists. Source IDs and action IDs
are distinct. No argument is repaired. ALP is unconfirmed, controls are measured,
cohort selected post hoc; this is not independent biological or final blind test.
Unresolved ALP identity restricts biological conclusions; it does not prevent the
offered literal raw-red proxy numerical experiments. Choose according to evidence.
The final request offers pause/stop only for budget control, not scientific approval.
Return exactly one offered native function call. Reason is your unverified judgment.'''


def schema_for(state,terminal=False):
    actions=state['actions'];reserved={r['action'] for r in state['reservations']}
    available={'pause','stop'}
    if not terminal and state['budget']['fits_reserved']<280:available|=set(chemotopo_iteration_study.CANDIDATES)-reserved
    common={'observation_sha256':{'type':'string','enum':[state['observation_sha256']]},
            'reason':{'type':'string','minLength':1,'maxLength':2000},
            'source_citation_ids':{'type':'array','items':{'type':'string','enum':['p02-r54','p02-r59']},'minItems':2,'maxItems':2,'uniqueItems':True,'description':'Cite both p02-r54 and p02-r59.'},
            'evidence_action_ids':{'type':'array','items':{'type':'string','enum':[a['id'] for a in actions]},'maxItems':6,'uniqueItems':True,'description':'Current executed action IDs only.'}}
    if actions:common['evidence_action_ids']['contains']={'enum':[actions[-1]['id']]}
    variants=[]
    for action in sorted(available):
        props={**copy.deepcopy(common),'action':{'type':'string','enum':[action]},'parameters':{'type':'object','properties':{},'required':[],'additionalProperties':False}}
        variants.append({'type':'object','properties':props,'required':list(props),'additionalProperties':False,
                         'description':('Run the fixed '+str(chemotopo_iteration_study.CANDIDATES[action])+' interaction penalty once; 140 local numerical fits.' if action in chemotopo_iteration_study.CANDIDATES else 'Record your own '+action+' decision; no fitting.')})
    return {'oneOf':variants}


def project_context(state,remaining,errors):
    def excerpt(value):
        raw=value.encode('utf-8');return {'excerpt':raw[:768].decode('utf-8','ignore'),'truncated':len(raw)>768}
    actions=[{'id':a['id'],'ordinal':a['ordinal'],'action':a['action'],'result_sha256':a['result_sha256'],
              'summary':a['result'].get('summary',a['result']),'reason':excerpt(a['reason'])} for a in state['actions']]
    return {'goal':state['goal'],'observation_sha256':state['observation_sha256'],'prior_evidence':state['prior_evidence'],
            'actions':actions,'source_ids':['p02-r54','p02-r59'],'latest_action_id':actions[-1]['id'] if actions else None,
            'budget':{**state['budget'],'remaining_model_requests':remaining},'reservations':state['reservations'],
            'endpoint_gate':state['endpoint_gate'],'previous_rejections':list(errors[-8:]),'scientific_validation':False}


class IterationCloudLoop(C01CloudLoop):
    request_prefix='p02-iteration-'
    def __init__(self,workspace):
        self.study=chemotopo_iteration_study.IterationStudy(workspace);self.db=self.study.root/'iteration-cloud.sqlite'
    def _state(self,con):return C01LocalLoop._state(self,con)
    def status(self):return C01LocalLoop.status(self)
    def configure(self,weights,*,max_requests=6):
        require(type(max_requests) is int and 1<=max_requests<=6,'INVALID_REQUEST','At most six native requests.')
        return super().configure(weights,max_requests=max_requests)
    def _code_identity(self):
        modules=(c01_cloud_loop,c01_local_loop,c01_native_tools,chemotopo_iteration_evidence,chemotopo_iteration_study,ollama_cloud,windows_network,contracts)
        return hashlib.sha256(c01_local_loop.code_identity().encode('ascii')+b''.join(Path(m.__file__).read_bytes() for m in modules)+Path(__file__).read_bytes()).hexdigest()
    def _specification(self,identity,observation,max_requests):
        return {'schema':'p02-native-iteration-cloud-v1','model_identity':cloud_identity(identity),'code_sha256':self._code_identity(),
                'study_sha256':observation['configuration_sha256'],'max_requests':max_requests,'max_output_tokens':2048,
                'prompt_token_evidence_cap':30720,'context_tokens':32768,'request_seconds':90,'max_request_bytes':65536,
                'reasoning_effort':ollama_cloud.THINKING,'included_credit_floor_usd':1.0,'credit_reserve_per_request_usd':.10,
                'purchased_credit_fallback':False,'provider_hard_spending_limit':False,'scientific_validation':False}
    def _request(self,observation,remaining,errors,spec):
        require(not any(r['status']=='started' for r in observation['reservations']),'EVIDENCE_CHANGED','A candidate reservation has an unknown outcome; no new request may start.')
        body={'model':ollama_cloud.MODEL,'messages':[{'role':'system','content':SYSTEM},
              {'role':'user','content':canonical(project_context(observation,remaining,errors))}],
              'tools':c01_native_tools.tools_from_schema(schema_for(observation,remaining<=1)),
              'stream':False,'think':spec['reasoning_effort'],'keep_alive':0,
              'options':{'temperature':0,'num_ctx':spec['context_tokens'],'num_predict':spec['max_output_tokens']}}
        require(len(canonical(body).encode('utf-8'))<=spec['max_request_bytes'],'PROMPT_TOO_LARGE','Bounded native context required.')
        return body
    def _parse_decision(self,response,observation,request_id,body):
        return c01_native_tools.parse_tool_decision(response,observation,request_id,body,decision_parser=chemotopo_iteration_study.parse_decision)
