"""One explicit same-budget continuation after an unknown native request.

Original R83 study and controller ledgers are read-only. Disposition and the
new request are separate append-only artifacts under the existing workflow root.
"""
import copy
import hashlib
import json
import os
from pathlib import Path

from . import source_assessment, evidence_workflow, reasoning_profile, ollama_cloud, c01_cloud_loop
from .chemotopo_experiment_evidence import _safe_file
from .chemotopo_iteration_view import _bind_native
from .contracts import ResearchError, canonical, fingerprint
from .local_ollama import require

MAX_DOCUMENT=20_000_000


def code_identity():
    from . import source_continuation_transport
    modules=(source_assessment,evidence_workflow,reasoning_profile,ollama_cloud,c01_cloud_loop,source_continuation_transport)
    return hashlib.sha256(Path(__file__).read_bytes()+b''.join(Path(m.__file__).read_bytes() for m in modules)).hexdigest()


def _write(path,value):
    raw=(canonical(value)+'\n').encode('utf-8')
    with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())


def _read(path):return json.loads(_safe_file(path,MAX_DOCUMENT))


def _hash_path(path):
    if not path.exists():return None
    return hashlib.sha256(_safe_file(path,MAX_DOCUMENT)).hexdigest()


class SourceAssessmentContinuation:
    def __init__(self,workflow_root):
        self.workflow=evidence_workflow.EvidenceWorkflow(workflow_root);self.root=self.workflow.root
        self.sidecar=self.root/'continuation-v1';self.disposition=self.sidecar/'disposition.json'
        self.reservation=self.sidecar/'reservation.json';self.response=self.sidecar/'response.json';self.outcome=self.sidecar/'outcome.json';self.unknown=self.sidecar/'unknown.json'

    def _guard(self):
        for path in (self.sidecar,*self.sidecar.parents):
            require(not path.is_symlink() and not getattr(path,'is_junction',lambda:False)(),'UNSAFE_PATH','Continuation paths cannot redirect.')

    def _old_identities(self):
        loop=source_assessment.SourceAssessmentCloudLoop(self.workflow.child)
        paths={'workflow_config':self.workflow.config_path,'workflow_packet':self.root/'packet.json',
               'study':loop.study.db,'study_wal':Path(str(loop.study.db)+'-wal'),
               'controller':loop.db,'controller_wal':Path(str(loop.db)+'-wal'),'study_packet':loop.study.root/'packet.json'}
        return {key:_hash_path(path) for key,path in paths.items()}

    def _capture_old(self):
        before=self._old_identities();config=self.workflow._config();loop=source_assessment.SourceAssessmentCloudLoop(self.workflow.child)
        require(all(before[k] is not None for k in ('workflow_config','workflow_packet','study','controller','study_packet')),'EVIDENCE_CHANGED','Original workflow and ledgers are required.')
        with loop._connect() as con:
            project,spec,state=loop._state(con);rows=[dict(r) for r in con.execute('SELECT * FROM calls ORDER BY ordinal')]
        require(project['status']=='needs_review' and project['reason']=='UNKNOWN_NATIVE_REQUEST' and state['status']=='active','EVIDENCE_CHANGED','Original unknown hold is required.')
        require(config['max_requests']==spec['max_requests']==4 and len(rows)==3 and [r['status'] for r in rows]==['applied','invalid','sending'] and rows[-1]['response_json'] is None,'EVIDENCE_CHANGED','Expected three original reservations including one unknown.')
        require(state['source_snapshot_sha256'] and state['read_source_ids'] and state['read_aliases'],'EVIDENCE_CHANGED','Previously read source evidence is required.')
        bound,trace=_bind_native(loop,state,spec,rows,context_builder=source_assessment.project_context,scope_fields=('source_snapshot_sha256',))
        require(bound=={a['id'] for a in state['actions']},'EVIDENCE_CHANGED','Original action binding differs.')
        with loop.study._connect() as con:child_config,current,actions=loop.study._state(con)
        require(current==state and self._old_identities()==before,'EVIDENCE_CHANGED','Original ledger changed during capture.')
        packet=loop.study._source(child_config)
        records=[{'ordinal':r['ordinal'],'id':r['id'],'request_id':r['request_id'],'status':r['status'],
                  'request_sha256':r['request_sha256'],'response_sha256':r['response_sha256'],'error_code':r['error_code'],'action_id':r['action_id']} for r in rows]
        return {'identities':before,'workflow_configuration_sha256':config['configuration_sha256'],'study_configuration_sha256':state['configuration_sha256'],
                'controller_specification_sha256':fingerprint(spec),'source_snapshot_sha256':state['source_snapshot_sha256'],
                'observation_sha256':state['observation_sha256'],'actions_sha256':fingerprint(actions),
                'old_reservations':records,'native_trace':trace,'max_requests':spec['max_requests'],
                'model_identity':copy.deepcopy(spec['model_identity'])},state,packet,spec

    def dispose(self,*,actor,reason,reasoning_profile='low'):
        require(actor=='operator_assistant' and type(reason) is str and 1<=len(reason.strip())<=2000 and reasoning_profile=='low','INVALID_REQUEST','Explicit operator-assistant reason and low profile required.')
        with self.workflow._lock():
            self._guard();old,_,_,_=self._capture_old()
            require(not self.sidecar.exists(),'ALREADY_EXISTS','Disposition already exists or is partially initialized; no overwrite.')
            self.sidecar.mkdir(exist_ok=False)
            record={'schema_version':'p02-source-continuation-disposition-v1','actor':actor,'disposition':'abandon_waiting_outcome_unknown',
                    'reason':reason,'old':old,'code_sha256':code_identity(),
                    'profile':{'reasoning_effort':'low','max_output_tokens':4096,'context_tokens':32768,'model_identity':old['model_identity']},
                    'global_max_requests':old['max_requests'],'old_reserved':len(old['old_reservations']),'new_max_reservations':1,
                    'notice':'Unknown outcome remains reserved. This does not assert nonexecution or settled cost. The original request will never be resent.',
                    'scientific_validation':False}
            record['snapshot_sha256']=fingerprint(record);_write(self.disposition,record)
            return copy.deepcopy(record)

    def _validated(self):
        self._guard();require(self.sidecar.is_dir() and self.disposition.is_file(),'NOT_INITIALIZED','Explicit disposition is required.')
        disp=_read(self.disposition);require(disp.get('schema_version')=='p02-source-continuation-disposition-v1' and disp.get('snapshot_sha256')==fingerprint({k:v for k,v in disp.items() if k!='snapshot_sha256'}) and disp.get('code_sha256')==code_identity() and disp.get('actor')=='operator_assistant' and disp.get('disposition')=='abandon_waiting_outcome_unknown','EVIDENCE_CHANGED','Disposition identity changed.')
        old,state,packet,spec=self._capture_old();require(old==disp['old'] and disp['global_max_requests']==4 and disp['old_reserved']==3 and disp['new_max_reservations']==1 and disp['profile']=={'reasoning_effort':'low','max_output_tokens':4096,'context_tokens':32768,'model_identity':old['model_identity']},'EVIDENCE_CHANGED','Original ledger, declared profile or total budget changed.')
        expected={'disposition.json','reservation.json','response.json','outcome.json','unknown.json'}
        require(all(p.is_file() and not p.is_symlink() and p.name in expected for p in self.sidecar.iterdir()),'EVIDENCE_CHANGED','Unexpected continuation artifact.')
        require(not(self.response.exists() and self.unknown.exists()) and (not self.outcome.exists() or self.response.exists()) and (not(self.response.exists() or self.unknown.exists()) or self.reservation.exists()),'EVIDENCE_CHANGED','Continuation artifact sequence invalid.')
        return disp,state,packet,spec

    def _reservation(self,disp,state):
        if not self.reservation.exists():return None
        value=_read(self.reservation)
        require(value.get('schema_version')=='p02-source-continuation-reservation-v1' and value.get('snapshot_sha256')==fingerprint({k:v for k,v in value.items() if k!='snapshot_sha256'}) and value.get('disposition_sha256')==disp['snapshot_sha256'] and value.get('old_observation_sha256')==state['observation_sha256'] and value.get('global_ordinal')==4 and value.get('observation')==state and value.get('request_sha256')==fingerprint(value.get('request')),'EVIDENCE_CHANGED','Continuation reservation changed.')
        expected_errors=[r['error_code'] for r in disp['old']['old_reservations'] if r['error_code']][-2:]
        require(value['request_id']=='p02-sidecar-'+disp['snapshot_sha256'][:32] and value['previous_rejections']==expected_errors,'EVIDENCE_CHANGED','Continuation request identity or feedback changed.')
        expected=source_assessment._body(state,1,expected_errors,'low',32768,4096)
        require(value['request']==expected and len(canonical(expected).encode('utf-8'))<=65536,'EVIDENCE_CHANGED','Frozen final request or profile changed.')
        return value

    def _status_locked(self):
        disp,state,packet,spec=self._validated();reservation=self._reservation(disp,state)
        response=_read(self.response) if self.response.exists() else None;outcome=_read(self.outcome) if self.outcome.exists() else None;unknown=_read(self.unknown) if self.unknown.exists() else None
        if response is not None:
            require(response.get('schema_version')=='p02-source-continuation-response-v1' and response.get('reservation_sha256')==reservation['snapshot_sha256'] and response.get('response_sha256')==fingerprint(response.get('response')) and response.get('snapshot_sha256')==fingerprint({k:v for k,v in response.items() if k!='snapshot_sha256'}),'EVIDENCE_CHANGED','Stored response changed.')
        if unknown is not None:require(unknown.get('reservation_sha256')==reservation['snapshot_sha256'] and unknown.get('snapshot_sha256')==fingerprint({k:v for k,v in unknown.items() if k!='snapshot_sha256'}),'EVIDENCE_CHANGED','Unknown receipt changed.')
        if outcome is not None:
            require(outcome.get('reservation_sha256')==reservation['snapshot_sha256'] and outcome.get('response_sha256')==response['response_sha256'] and outcome.get('snapshot_sha256')==fingerprint({k:v for k,v in outcome.items() if k!='snapshot_sha256'}),'EVIDENCE_CHANGED','Stored outcome changed.')
            require(outcome==self._derive_outcome(reservation,response,state,packet,spec),'EVIDENCE_CHANGED','Outcome differs from actual native response.')
        state_name='completed' if outcome else 'needs_attention' if unknown or (reservation and not response) or (response and response.get('credit_hold')) else 'received' if response else 'ready'
        return {'schema_version':'p02-source-continuation-status-v1','status':state_name,'disposition_sha256':disp['snapshot_sha256'],
                'source_snapshot_sha256':state['source_snapshot_sha256'],'budget':{'max_requests':4,'old_reserved':3,'old_unknown_reserved':1,'new_reserved':1 if reservation else 0,'total_reserved':3+(1 if reservation else 0)},
                'profile':copy.deepcopy(disp['profile']),'original_study_status':state['status'],'new_outcome':outcome,
                'unknown_outcome_preserved':True,'automatic_retry':False,'actual_inference_cash_cny':None,
                'scientific_validation':False,'task_complete':False,'new_fits':0}

    def status(self):
        with self.workflow._lock():return self._status_locked()

    def _derive_outcome(self,reservation,response,state,packet,spec):
        reply=response['response'];request_id=reservation['request_id'];loop=source_assessment.SourceAssessmentCloudLoop(self.workflow.child)
        low_spec={**spec,'reasoning_effort':'low','max_output_tokens':4096,'context_tokens':32768}
        try:
            loop._validate_response(reply,low_spec)
            decision=source_assessment.parse_compact(reply,state,request_id,reservation['request'])
            require(decision['action'] in {'record_assessment','pause','stop'},'ACTION_NOT_AVAILABLE','Final slot permits assessment or control only.')
            result=source_assessment._result(decision['action'],decision['parameters'],decision['reason'],packet)
            action={**copy.deepcopy(decision),'id':'p02sidecar-'+fingerprint({'request_id':request_id,'request_sha256':fingerprint(decision)})[:32],
                    'ordinal':len(state['actions'])+1,'result':result,'result_sha256':fingerprint(result)}
            outcome={'schema_version':'p02-source-continuation-outcome-v1','reservation_sha256':reservation['snapshot_sha256'],
                     'response_sha256':response['response_sha256'],'status':'applied','action':action,'error_code':None,
                     'interpretation_status':'unreviewed_model_assessment' if decision['action']=='record_assessment' else 'no_assessment',
                     'task_complete':False,'scientific_validation':False}
        except ResearchError as error:
            if error.code in {'EVIDENCE_CHANGED','CODE_CHANGED','UNSAFE_PATH'}:raise
            outcome={'schema_version':'p02-source-continuation-outcome-v1','reservation_sha256':reservation['snapshot_sha256'],
                     'response_sha256':response['response_sha256'],'status':'invalid','action':None,'error_code':error.code,
                     'interpretation_status':'no_assessment','task_complete':False,'scientific_validation':False}
        except (TypeError,ValueError,OverflowError):
            outcome={'schema_version':'p02-source-continuation-outcome-v1','reservation_sha256':reservation['snapshot_sha256'],
                     'response_sha256':response['response_sha256'],'status':'invalid','action':None,'error_code':'INVALID_TOOL_DECISION',
                     'interpretation_status':'no_assessment','task_complete':False,'scientific_validation':False}
        outcome['snapshot_sha256']=fingerprint(outcome);return outcome

    def advance(self,client=None,*,max_new_requests=0):
        require(type(max_new_requests) is int and max_new_requests in (0,1),'INVALID_REQUEST','At most one new request is permitted.')
        with self.workflow._lock():
            current=self._status_locked();disp,state,packet,spec=self._validated();reservation=self._reservation(disp,state)
            if self.outcome.exists():return current
            if reservation is not None:
                if self.response.exists():
                    response=_read(self.response);require(not response.get('credit_hold'),'QUOTA_REVIEW_REQUIRED','Known response has unresolved account reconciliation; no automatic release.')
                    _write(self.outcome,self._derive_outcome(reservation,response,state,packet,spec));return self._status_locked()
                raise ResearchError('NEEDS_REVIEW','Continuation send outcome is unknown; preserve reservation and never resend.')
            if max_new_requests==0:return current
            from .source_continuation_transport import OwnedContinuationOllama
            require(isinstance(client,OwnedContinuationOllama),'LOCAL_SERVER_REQUIRED','The guarded low-reasoning continuation transport is required.')
            client.assert_owner();identity=client.acquire();require(c01_cloud_loop.cloud_identity(identity)==spec['model_identity'],'MODEL_CHANGED','Original model and account period must match.')
            prior_receipt=client._read_prior();require(prior_receipt.get('request_sha256')==disp['old']['old_reservations'][-1]['request_sha256'],'EVIDENCE_CHANGED','Transport unknown receipt must bind the exact original reserved request.')
            # One fresh call remains; the guarded transport reserves the old unknown charge separately.
            client.configure_budget(identity,1)
            old_errors=[r['error_code'] for r in disp['old']['old_reservations'] if r['error_code']][-2:]
            body=source_assessment._body(state,1,old_errors,'low',32768,4096)
            require(len(canonical(body).encode('utf-8'))<=65536,'PROMPT_TOO_LARGE','Final source context exceeds bound.')
            client.prepare(body)
            reservation={'schema_version':'p02-source-continuation-reservation-v1','disposition_sha256':disp['snapshot_sha256'],
                         'old_observation_sha256':state['observation_sha256'],'global_ordinal':4,'request_id':'p02-sidecar-'+disp['snapshot_sha256'][:32],
                         'observation':state,'request':body,'request_sha256':fingerprint(body),'previous_rejections':old_errors}
            reservation['snapshot_sha256']=fingerprint(reservation);_write(self.reservation,reservation)
            try:reply=client.http.request('/api/chat',body,timeout=spec['request_seconds'])
            except Exception as error:
                unknown={'schema_version':'p02-source-continuation-unknown-v1','reservation_sha256':reservation['snapshot_sha256'],
                         'error_code':getattr(error,'code','CLOUD_REQUEST_UNKNOWN'),'outcome_unknown':True}
                unknown['snapshot_sha256']=fingerprint(unknown);_write(self.unknown,unknown)
                raise ResearchError('NEEDS_REVIEW','Continuation outcome unknown; preserve reservation and never resend.') from None
            response={'schema_version':'p02-source-continuation-response-v1','reservation_sha256':reservation['snapshot_sha256'],
                      'response':reply,'response_sha256':fingerprint(reply),'credit_hold':copy.deepcopy(getattr(client,'credit_hold',None))}
            response['snapshot_sha256']=fingerprint(response);_write(self.response,response)
            require(not response['credit_hold'],'QUOTA_REVIEW_REQUIRED','Response received but account reconciliation is required.')
            _write(self.outcome,self._derive_outcome(reservation,response,state,packet,spec))
            return self._status_locked()
