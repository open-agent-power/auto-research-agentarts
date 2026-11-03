"""Compact native selection over the unchanged configured numerical executor."""
import hashlib
import json
from pathlib import Path

from . import configured_iteration, ollama_cloud
from .contracts import ResearchError, canonical, fingerprint
from .local_ollama import require

SYSTEM='''You choose from a fixed operator-provided numerical menu. run_candidate needs only candidate_id and your reason; pause and stop need only your reason. Prior evidence is historical and is not a scientific verdict. Each candidate executes 140 local numerical fits, not LLM weight training; you may stop without running any candidate. The host binds observation and citations as execution metadata: they do not assert you independently chose citations or read an item. Your reason and candidate choice alone come from your tool call. No tool call grants spending permission or scientific validity. No changes to data, candidate parameters, protocol, bounds or source paths are allowed. ALP is unconfirmed; reused data with measured controls are not an independent blind test. Return one offered native tool, with precisely the requested fields; no arguments are repaired.'''


def host_binding(state):
    sources=[c['citation_id'] for c in state['citations']]
    require(sources==['p02-r54','p02-r59'],'EVIDENCE_CHANGED','Expected frozen source citations changed.')
    return {'observation_sha256':state['observation_sha256'],'source_citation_ids':sources,'evidence_action_ids':[state['actions'][-1]['id']] if state['actions'] else [],'origin':'host_bound_execution_metadata','notice':'Host binds metadata; this is not a model-selected citation or proof of model reading.'}


def project_context(state,remaining,errors):
    return {**configured_iteration.project_context(state,remaining,errors),'host_binding':host_binding(state)}


def tools_for(state,terminal=False):
    reserved={r['candidate_id'] for r in state['reservations']}
    remaining=[c['id'] for c in state['protocol']['candidates'] if c['id'] not in reserved]
    names=['pause','stop']
    if not terminal and remaining and state['budget']['fits_reserved']+140<=state['budget']['max_fits']:names.append('run_candidate')
    tools=[]
    for name in sorted(names):
        fields={'reason':{'type':'string','minLength':1,'maxLength':2000,'description':'Your reason; not scientific approval.'}}
        if name=='run_candidate': fields['candidate_id']={'type':'string','enum':remaining,'description':'One unreserved fixed-menu candidate.'}
        tools.append({'type':'function','function':{'name':name,'description':'Execute the fixed candidate with 140 numerical fits.' if name=='run_candidate' else 'Record a control decision without fitting.','parameters':{'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}}})
    return tools


def parse_compact(response,state,request_id,body):
    require(type(state) is dict and state.get('observation_sha256')==fingerprint({k:v for k,v in state.items() if k!='observation_sha256'}),'EVIDENCE_CHANGED','Observation fingerprint mismatch.')
    try:
        require(type(body) is dict and type(body.get('messages')) is list and len(body['messages'])==2,'EVIDENCE_CHANGED','Missing saved request context.')
        context=json.loads(body['messages'][1]['content']);remaining=context['budget']['remaining_model_requests'];errors=context['previous_rejections']
        require(type(remaining) is int and 1<=remaining<=state['protocol']['max_requests'] and type(errors) is list and all(type(e) is str for e in errors),'EVIDENCE_CHANGED','Invalid saved request context.')
        require(context==project_context(state,remaining,errors) and body['tools']==tools_for(state,remaining<=1),'EVIDENCE_CHANGED','Saved request binding or offered tools changed.')
    except (KeyError,TypeError,ValueError,json.JSONDecodeError):raise ResearchError('EVIDENCE_CHANGED','Saved request context or offered tools invalid.') from None
    message=response.get('message') if type(response) is dict else None;calls=message.get('tool_calls') if type(message) is dict else None
    require(type(calls) is list and len(calls)==1,'INVALID_TOOL_ARGUMENTS','Exactly one native tool call is required.')
    call=calls[0];function=call.get('function') if type(call) is dict else None
    require(type(function) is dict and type(function.get('name')) is str and call.get('type','function')=='function','INVALID_TOOL_ARGUMENTS','Native function call required.')
    name=function['name'];offered={t['function']['name'] for t in body['tools']}
    require(name in offered,'ACTION_NOT_AVAILABLE','Returned tool was not offered.')
    args=function.get('arguments');required={'reason','candidate_id'} if name=='run_candidate' else {'reason'}
    require(type(args) is dict and set(args)==required and type(args.get('reason')) is str and 1<=len(args['reason'].strip())<=2000,'INVALID_TOOL_ARGUMENTS','Exact compact arguments and bounded reason required.')
    if name=='run_candidate':
        allowed=next(t['function']['parameters']['properties']['candidate_id']['enum'] for t in body['tools'] if t['function']['name']==name)
        require(type(args['candidate_id']) is str and args['candidate_id'] in allowed,'INVALID_REQUEST','Candidate must be an offered fixed-menu ID.')
    binding=host_binding(state)
    request={'request_id':request_id,'observation_sha256':binding['observation_sha256'],'action':name,'reason':args['reason'],'source_citation_ids':binding['source_citation_ids'],'evidence_action_ids':binding['evidence_action_ids'],'parameters':{'candidate_id':args['candidate_id']} if name=='run_candidate' else {}}
    configured_iteration.validate_request(request,state)
    return request


class CompactCloudLoop(configured_iteration.ConfiguredCloudLoop):
    request_prefix='p02-compact-'
    def _code_identity(self):
        from . import prepared_continuation
        return hashlib.sha256(super()._code_identity().encode('ascii')+Path(__file__).read_bytes()+Path(prepared_continuation.__file__).read_bytes()).hexdigest()
    def _specification(self,identity,observation,max_requests):
        return {**super()._specification(identity,observation,max_requests),'schema':'p02-compact-native-cloud-v1','code_sha256':self._code_identity()}
    def _request(self,observation,remaining,errors,spec):
        require(not any(r['status']=='started' for r in observation['reservations']),'EVIDENCE_CHANGED','Unknown candidate outcome blocks new requests.')
        body={'model':ollama_cloud.MODEL,'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':canonical(project_context(observation,remaining,errors))}],'tools':tools_for(observation,remaining<=1),'stream':False,'think':spec['reasoning_effort'],'keep_alive':0,'options':{'temperature':0,'num_ctx':spec['context_tokens'],'num_predict':spec['max_output_tokens']}}
        require(len(canonical(body).encode('utf-8'))<=spec['max_request_bytes'],'PROMPT_TOO_LARGE','Bounded native context required.')
        return body
    def _parse_decision(self,response,observation,request_id,body):return parse_compact(response,observation,request_id,body)
