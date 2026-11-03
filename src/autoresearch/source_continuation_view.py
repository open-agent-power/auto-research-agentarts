"""Read-only, source-bound projection of one bounded continuation response."""
import copy
import hashlib
import json
from pathlib import Path

from .chemotopo_experiment_evidence import _safe_file
from .contracts import ResearchError, canonical, fingerprint
from .handoff_view import _public_text
from .source_assessment import QUESTIONS
from .source_assessment_continuation import SourceAssessmentContinuation
from .source_assessment_view import read_source_progress_artifacts

LIMITS={'continuation.json':3_000_000,'continuation.md':250_000}


def _require(condition,message):
    if not condition:raise ResearchError('EVIDENCE_CHANGED',message)


def _schema_errors(value,schema,path='$'):
    """Report structural schema failures; never repair native arguments."""
    errors=[];kind=schema.get('type')
    if kind=='object':
        if type(value) is not dict:return [{'path':path,'code':'expected_object'}]
        props=schema.get('properties',{});required=schema.get('required',[])
        for key in required:
            if key not in value:errors.append({'path':path+'.'+key,'code':'missing_required'})
        if schema.get('additionalProperties') is False:
            for key in value:
                if key not in props:errors.append({'path':path+'.'+key,'code':'unexpected_field'})
        for key in sorted(value.keys() & props.keys()):errors.extend(_schema_errors(value[key],props[key],path+'.'+key))
    elif kind=='array':
        if type(value) is not list:return [{'path':path,'code':'expected_array'}]
        if len(value)<schema.get('minItems',0):errors.append({'path':path,'code':'too_few_items','minimum':schema['minItems'],'actual':len(value)})
        if len(value)>schema.get('maxItems',float('inf')):errors.append({'path':path,'code':'too_many_items','maximum':schema['maxItems'],'actual':len(value)})
        if schema.get('uniqueItems') and len({canonical(v) for v in value})!=len(value):errors.append({'path':path,'code':'duplicate_items'})
        for i,element in enumerate(value):errors.extend(_schema_errors(element,schema.get('items',{}),f'{path}[{i}]'))
    elif kind=='string':
        if type(value) is not str:return [{'path':path,'code':'expected_string'}]
        if len(value)<schema.get('minLength',0):errors.append({'path':path,'code':'too_short'})
        if len(value)>schema.get('maxLength',float('inf')):errors.append({'path':path,'code':'too_long'})
    if 'enum' in schema and value not in schema['enum']:errors.append({'path':path,'code':'not_offered'})
    return errors


def _capture(workflow_root,progress):
    _require(type(progress) is dict and progress.get('schema_version')=='p02-source-assessment-progress-v1' and progress.get('snapshot_sha256')==fingerprint({k:v for k,v in progress.items() if k!='snapshot_sha256'}) and progress.get('publication_eligible') is False and progress.get('progress_only') is True,'Exact original progress snapshot required.')
    continuation=SourceAssessmentContinuation(workflow_root)
    with continuation.workflow._lock():
        status=continuation._status_locked();disp,state,packet,spec=continuation._validated();reservation=continuation._reservation(disp,state)
        _require(status['status']=='completed' and status['new_outcome']['status']=='invalid' and reservation is not None,'Expected a received, invalid continuation outcome.')
        response_record=json.loads(_safe_file(continuation.response,20_000_000));reply=response_record['response'];outcome=status['new_outcome']
        _require(progress['source_snapshot_sha256']==packet['snapshot_sha256']==state['source_snapshot_sha256'] and progress['handoff_snapshot_sha256']==packet['handoff_snapshot_sha256'] and progress['read_aliases']==state['read_aliases'] and progress['read_source_ids']==state['read_source_ids'] and progress['alias_map']==state['alias_map'],'Progress packet, aliases or handoff differ from original study.')
        _require([(a['id'],a['result_sha256']) for a in progress['actions']]==[(a['id'],a['result_sha256']) for a in state['actions']],'Progress actions differ from original ledger.')
        trace=disp['old']['native_trace'];old=progress['native_trace'];keys=('ordinal','status','action_id','request_sha256','response_sha256','feedback_action_ids')
        _require(len(trace)==len(old) and all(all(a[k]==b[k] for k in keys) for a,b in zip(trace,old)),'Progress native trace differs from original reservations.')
        message=reply.get('message',{});calls=message.get('tool_calls',[]) if type(message) is dict else []
        _require(type(calls) is list and len(calls)==1 and type(calls[0]) is dict and type(calls[0].get('function')) is dict,'One original native call required for this projection.')
        function=calls[0]['function'];name=function.get('name');arguments=copy.deepcopy(function.get('arguments'))
        offered=[t['function'] for t in reservation['request']['tools'] if t.get('function',{}).get('name')==name]
        _require(name=='record_assessment' and len(offered)==1 and type(arguments) is dict,'Original assessment tool and arguments required.')
        errors=_schema_errors(arguments,offered[0]['parameters']);_require(bool(errors),'No structural failures found for invalid response.')
        content=message.get('content');_require(content is None or type(content) is str,'Unexpected native content.')
        _public_text({'reason':disp['reason'],'content':content,'arguments':arguments})
        view={'schema_version':'p02-source-continuation-view-v1','source_progress_snapshot_sha256':progress['snapshot_sha256'],
              'source_snapshot_sha256':packet['snapshot_sha256'],'handoff_snapshot_sha256':packet['handoff_snapshot_sha256'],
              'status':'回复已收到，评议未通过','disposition':{k:copy.deepcopy(disp[k]) for k in ('actor','disposition','reason','notice')},
              'budget':copy.deepcopy(status['budget']),'profile':{k:disp['profile'][k] for k in ('reasoning_effort','max_output_tokens','context_tokens')},
              'prior':{'read_source_ids':list(progress['read_source_ids']),'read_aliases':list(progress['read_aliases']),
                       'alias_map':copy.deepcopy(progress['alias_map']),'native_trace':copy.deepcopy(progress['native_trace']),'old_unknown_preserved':True},
              'response':{'ordinal':reservation['global_ordinal'],'status':outcome['status'],'error_code':outcome['error_code'],
                          'content':content,'tool_calls':[{'name':name,'arguments':arguments}],
                          'metadata':{k:reply[k] for k in ('model','done','done_reason','prompt_eval_count','eval_count') if k in reply}},
              'schema_diagnostics':{'origin':'host_schema_validation','errors':errors,'notice':'Host reports structural constraints only; original arguments are unchanged.'},
              'accepted_assessment':None,'needed_questions':copy.deepcopy(QUESTIONS),'scientific_validation':False,
              'biological_endpoint_eligible':False,'task_complete':False,'automatic_retry':False,'new_fits':0,
              'evidence':{'disposition_sha256':disp['snapshot_sha256'],'reservation_sha256':reservation['snapshot_sha256'],
                          'response_sha256':response_record['response_sha256'],'response_record_sha256':response_record['snapshot_sha256'],
                          'outcome_sha256':outcome['snapshot_sha256']},
              'notice':'The earlier unknown request remains reserved; its outcome and cash settlement remain unknown. No new fit or accepted assessment.'}
        view['snapshot_sha256']=fingerprint(view);return view


def _markdown(view):
    lines=['# 原文评议续行记录','','原请求未知结果继续占用预算；不能据此推断是否执行或费用结算。','',
           '状态：'+view['status'],'预算：'+str(view['budget']['total_reserved'])+' / '+str(view['budget']['max_requests']),
           '新请求：'+view['profile']['reasoning_effort']+'；返回已收到但未通过结构校验。','',
           '## 宿主结构核对（未修复原参数）','']
    for error in view['schema_diagnostics']['errors']:lines.append('- `'+error['path']+'`：'+error['code'])
    lines+=['','## 模型原始工具参数（未应用）','','```json',json.dumps(view['response']['tool_calls'][0]['arguments'],ensure_ascii=False,indent=2),'```','',
            '没有有效评议；原文读取不等于科学批准、ALP 身份确认或外部任务完成。','']
    return '\n'.join(lines).encode('utf-8')


def _manifest(view,files):
    return {'schema_version':'p02-source-continuation-artifacts-v1','snapshot_sha256':view['snapshot_sha256'],
            'source_progress_snapshot_sha256':view['source_progress_snapshot_sha256'],'source_snapshot_sha256':view['source_snapshot_sha256'],
            'handoff_snapshot_sha256':view['handoff_snapshot_sha256'],
            'files':{name:{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)} for name,raw in files.items()}}


def export_source_continuation(workflow_root,progress_directory,output):
    workflow=Path(workflow_root).absolute().resolve();progress_dir=Path(progress_directory).absolute().resolve();target=Path(output).absolute()
    for part in (target,*target.parents):_require(not part.is_symlink() and not getattr(part,'is_junction',lambda:False)(),'Output cannot redirect.')
    resolved=target.resolve()
    for source in (workflow,progress_dir):_require(not(resolved==source or resolved.is_relative_to(source) or source.is_relative_to(resolved)),'Output must be separate from original workflow and progress.')
    _require(not target.exists(),'Use a fresh exclusive output directory.')
    progress=json.loads(read_source_progress_artifacts(progress_dir)['progress.json']);view=_capture(workflow,progress)
    files={'continuation.json':(canonical(view)+'\n').encode('utf-8'),'continuation.md':_markdown(view)}
    _require(all(len(raw)<=LIMITS[name] for name,raw in files.items()),'Public continuation exceeds bounds.')
    target.mkdir(parents=True,exist_ok=False)
    for name,raw in files.items():
        with (target/name).open('xb') as stream:stream.write(raw)
    with (target/'manifest.json').open('xb') as stream:stream.write((canonical(_manifest(view,files))+'\n').encode('utf-8'))
    return _manifest(view,files)


def read_source_continuation_artifacts(directory,progress):
    root=Path(directory).absolute();manifest=json.loads(_safe_file(root/'manifest.json',100_000));files={name:_safe_file(root/name,limit) for name,limit in LIMITS.items()};view=json.loads(files['continuation.json'])
    _require(type(progress) is dict and progress.get('snapshot_sha256')==fingerprint({k:v for k,v in progress.items() if k!='snapshot_sha256'}) and view.get('schema_version')=='p02-source-continuation-view-v1' and view.get('snapshot_sha256')==fingerprint({k:v for k,v in view.items() if k!='snapshot_sha256'}) and view.get('source_progress_snapshot_sha256')==progress['snapshot_sha256'] and view.get('source_snapshot_sha256')==progress['source_snapshot_sha256'] and view.get('handoff_snapshot_sha256')==progress['handoff_snapshot_sha256'] and view.get('scientific_validation') is False and view.get('task_complete') is False,'Continuation identity or progress binding changed.')
    _public_text({'disposition':view['disposition'],'response':view['response']})
    expected_errors=[{'code':'missing_required','path':f'$.answers[{i}].status'} for i in range(4)]+[{'actual':0,'code':'too_few_items','minimum':1,'path':'$.answers[3].evidence_ids'}]
    evidence=view.get('evidence',{})
    _require(view.get('accepted_assessment') is None and view.get('biological_endpoint_eligible') is False and view.get('automatic_retry') is False and type(view.get('new_fits')) is int and view['new_fits']==0 and view.get('prior',{}).get('old_unknown_preserved') is True and view.get('budget')=={'max_requests':4,'old_reserved':3,'old_unknown_reserved':1,'new_reserved':1,'total_reserved':4} and view.get('response',{}).get('status')=='invalid' and view['response'].get('error_code')=='INVALID_REQUEST' and view.get('schema_diagnostics',{}).get('origin')=='host_schema_validation' and view['schema_diagnostics'].get('errors')==expected_errors and set(evidence)=={'disposition_sha256','reservation_sha256','response_sha256','response_record_sha256','outcome_sha256'} and all(type(v) is str and len(v)==64 and all(c in '0123456789abcdef' for c in v) for v in evidence.values()),'Continuation outcome, preserved reservation or evidence anchors changed.')
    _require(manifest==_manifest(view,files) and files['continuation.md']==_markdown(view),'Continuation artifacts changed.')
    return files
