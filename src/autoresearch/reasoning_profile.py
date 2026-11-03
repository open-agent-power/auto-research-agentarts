"""Isolated high-reasoning transport for the unchanged pinned GPT-OSS alias.

Only request reasoning/output limits differ. Ownership, account observation,
preflight and unknown-send policy remain the existing transport's contract.
"""
import copy
from decimal import Decimal
import hashlib
from pathlib import Path
import re
import time

from . import ollama_cloud
from .contracts import ResearchError, canonical, fingerprint
from .local_ollama import file_info, parse_json, require

REASONING='high'
MAX_OUTPUT_TOKENS=4096
MAX_CONTEXT_TOKENS=32768


def code_identity():
    return hashlib.sha256(Path(__file__).read_bytes()+Path(ollama_cloud.__file__).read_bytes()).hexdigest()


class OwnedHighReasoningOllama(ollama_cloud.OwnedCloudOllama):
    def acquire(self):
        with self._lock:
            identity=super().acquire()
            if not getattr(self,'_high_reasoning_verified',False):
                digest,_,raw=file_info(self.output/'model-show.json',2*1024*1024)
                shown=parse_json(raw);thinking=shown.get('thinking')
                require(type(thinking) is dict and type(thinking.get('values')) is list
                        and REASONING in thinking['values'],'THINKING_UNVERIFIED','Acquired model must advertise high reasoning.')
                self._reasoning_capabilities={'model':identity['model'],'remote_model':identity['remote_model'],
                    'remote_host':identity['remote_host'],'thinking':copy.deepcopy(thinking),
                    'selected_reasoning':REASONING,'max_output_tokens':MAX_OUTPUT_TOKENS,
                    'max_context_tokens':MAX_CONTEXT_TOKENS,'model_show_sha256':digest,
                    'source':'actual_cached_api_show','model_calls':0}
                self._high_reasoning_verified=True
            return identity

    @property
    def reasoning_capabilities(self):
        require(getattr(self,'_high_reasoning_verified',False),'THINKING_UNVERIFIED','Acquire and verify metadata first.')
        return copy.deepcopy(self._reasoning_capabilities)

    def _chat(self,route,body=None,*,timeout=90):
        with self._lock:
            require(route=='/api/chat' and type(timeout) in (int,float) and 0<timeout<=90,'INVALID_REQUEST','Only bounded native chat is public.')
            require(type(body) is dict and set(body)<={'model','messages','stream','think','keep_alive','options','tools'}
                    and body.get('model')==ollama_cloud.MODEL and body.get('stream') is False and body.get('think')==REASONING,
                    'INVALID_REQUEST','Unchanged model and high reasoning required.')
            options=body.get('options')
            require(type(options) is dict and set(options)<={'temperature','num_ctx','num_predict'}
                    and type(options.get('num_predict')) is int and 1<=options['num_predict']<=MAX_OUTPUT_TOKENS
                    and type(options.get('num_ctx')) is int and 1<=options['num_ctx']<=MAX_CONTEXT_TOKENS
                    and type(options.get('temperature',0)) in (int,float) and options.get('temperature',0)==0
                    and type(body.get('keep_alive',0)) is int and body.get('keep_alive',0)==0,
                    'INVALID_REQUEST','Bounded output and context required.')
            if 'tools' in body:
                tools,names=body['tools'],set()
                require(type(tools) is list and 1<=len(tools)<=16,'INVALID_REQUEST','Bounded native tools required.')
                for tool in tools:
                    function=tool.get('function') if type(tool) is dict else None
                    require(type(function) is dict and set(tool)=={'type','function'} and tool['type']=='function'
                            and set(function)=={'name','description','parameters'}
                            and type(function['name']) is str and re.fullmatch('[a-z][a-z0-9_]{0,63}',function['name']) is not None
                            and function['name'] not in names and type(function['description']) is str
                            and 1<=len(function['description'])<=2000 and type(function['parameters']) is dict
                            and function['parameters'].get('type')=='object','INVALID_REQUEST','Valid distinct function definitions required.')
                    names.add(function['name'])
            messages=body.get('messages')
            require(type(messages) is list and 1<=len(messages)<=16 and all(type(m) is dict and set(m)=={'role','content'}
                    and type(m['role']) is str and m['role'] in {'system','user','assistant'} and type(m['content']) is str for m in messages)
                    and len(canonical(body).encode('utf-8'))<=65536,'INVALID_REQUEST','Bounded textual prompt required.')
            require(getattr(self,'_high_reasoning_verified',False),'THINKING_UNVERIFIED','Actual high capability must be verified before inference.')
            require(not self._uncertain,'NEEDS_REVIEW','Previous cloud outcome requires review; no resend.')
            require(self.credit_hold is None,'QUOTA_REVIEW_REQUIRED','Received response requires credit reconciliation.')
            require(self._budget is not None and self._used<self._budget,'BUDGET_EXHAUSTED','Configure remaining cumulative budget before chat.')
            self.assert_owner()
            if self._prepared is None:self.prepare(body)
            require(self._prepared['request_sha256']==fingerprint(body) and self._prepared['used']==self._used
                    and time.monotonic()-self._prepared['at']<=10,'PREFLIGHT_CHANGED','Request approval changed or expired; never dispatch.')
            ordinal,before=self._used+1,self._prepared['account']
            self._write(f'cloud-{ordinal:03}-sending.json',{'status':'sending','request':body,'request_sha256':fingerprint(body),
                'reserved_usd':'.10','account':before,'preflight_receipt':self._prepared['receipt']})
            self._used+=1;self._prepared=None;self._uncertain=True
            response=self._wire('/api/chat',body,timeout=timeout,capture=f'cloud-{ordinal:03}-response.raw.json')
            self._uncertain=False
            try:
                after=self._account();self._write(f'cloud-{ordinal:03}-account-after.json',after);self._check_account(after)
                require(Decimal('0')<=Decimal(str(before['included_balance_usd']))-Decimal(str(after['included_balance_usd']))<=Decimal('.10'),
                        'QUOTA_CHANGED','Unexpected credit movement; stop.')
            except (ResearchError,OSError) as error:
                code=error.code if isinstance(error,ResearchError) else 'QUOTA_RECEIPT_FAILED'
                self.credit_hold={'code':code,'ordinal':ordinal,'response_received':True}
                try:self._write(f'cloud-{ordinal:03}-credit-hold.json',self.credit_hold)
                except OSError:self.credit_hold['receipt_write_failed']=True
            return response
