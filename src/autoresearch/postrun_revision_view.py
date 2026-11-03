"""Read-only revision projection with explicit original source and retired memory."""
import copy
import hashlib
import json
from pathlib import Path

from .chemotopo_delivery import _safe
from .chemotopo_iteration_view import _bind_native, _require
from .contracts import ResearchError, canonical, fingerprint
from .postrun_revision import RevisionCloudLoop, project_context
from .postrun_view import _assessment, _identities
from .research_memory import ResearchMemory


def capture_revision(workspace,iteration,annotation=None):
    _require(iteration.get('schema_version')=='p02-iteration-view-v1'
             and iteration.get('snapshot_sha256')==fingerprint({k:v for k,v in iteration.items() if k!='snapshot_sha256'}),
             'An intact original sealed iteration is required.')
    loop=RevisionCloudLoop(workspace)
    with loop.study._connect() as con:
        config=json.loads(con.execute('SELECT * FROM meta').fetchone()['config'])
    paths=[loop.db,loop.study.db,Path(config['memory_workspace'])/'memory.sqlite']
    before=_identities(paths)
    with loop._connect() as con:
        project,spec,state=loop._state(con)
        calls=[dict(row) for row in con.execute('SELECT * FROM calls ORDER BY ordinal')]
    payload=loop.study._source(config)
    _require(payload['source']['view']==iteration,'Revision must bind its exact original source iteration.')
    _require(payload['snapshot_sha256']==state['source_snapshot_sha256'] and payload['scope']==state['scope'],
             'Revision payload and observed scope differ.')
    bound,trace=_bind_native(loop,state,spec,calls,context_builder=project_context,
                              scope_fields=('source_snapshot_sha256','scope'))
    actions=[_safe({**{k:a[k] for k in ('id','ordinal','action','parameters','reason','result_sha256',
                                       'source_citation_ids','evidence_action_ids')},
                    'result':copy.deepcopy(a['result']),'model_selected':a['id'] in bound}) for a in state['actions']]
    memory=ResearchMemory(config['memory_workspace']).recall(state['scope'],limit=8,include_retired=True)
    unapplied=[];recalled_in_later=set()
    recalls={a['id']:a for a in state['actions'] if a['action']=='recall_observations'}
    for row in calls:
        body=json.loads(row['request_json']);context=json.loads(body['messages'][1]['content'])
        for item in context['actions']:
            if item['id'] in recalls:
                _require(item['result']==recalls[item['id']]['result'],'Recalled values differ in later native request.')
                recalled_in_later.update(e['record']['id'] for e in item['result']['entries'])
        if row['status']!='applied':
            entry={'ordinal':row['ordinal'],'error_code':row['error_code'],'tool_name':None,'reason_excerpt':None}
            response=json.loads(row['response_json']) if row['response_json'] else {}
            tools=response.get('message',{}).get('tool_calls',[])
            if type(tools) is list and len(tools)==1 and type(tools[0]) is dict:
                function=tools[0].get('function',{});entry['tool_name']=str(function.get('name',''))[:80]
                args=function.get('arguments');reason=args.get('reason') if type(args) is dict else None
                entry['reason_excerpt']=reason[:700] if type(reason) is str else None
            unapplied.append(_safe(entry))
    view=_safe({'schema_version':'p02-postrun-view-v1','iteration_snapshot_sha256':iteration['snapshot_sha256'],
        'source_snapshot_sha256':payload['snapshot_sha256'],'study_configuration_sha256':state['configuration_sha256'],
        'controller_configuration_sha256':fingerprint(spec),'goal':state['goal'],
        'study_status':state['status'],'controller_status':project['status'],'controller_reason':project['reason'],
        'actions':actions,'native_trace':trace,'unapplied_requests':unapplied,'memory_context':memory,
        'assessment':_assessment(annotation,state,payload),
        'revision':{'seed_proposal':copy.deepcopy(payload['seed_proposal']),
                    'prior_postrun_snapshot_sha256':payload['postrun']['snapshot_sha256'],
                    'original_source_snapshot_sha256':payload['source']['snapshot_sha256'],
                    'superseded_memory_id':payload['superseded_memory_id'],
                    'proposal_version_count':1+sum(a['action']=='revise_proposal' for a in actions)},
        'execution':{'model':spec['model_identity']['model'],'requests_reserved':len(calls),'max_requests':spec['max_requests'],
                     'applied_calls':len(bound),'invalid_calls':sum(c['status']=='invalid' for c in calls),
                     'unknown_requests':sum(c['status'] in {'sending','received'} for c in calls),
                     'explicit_remembers':sum(a['action']=='remember_revision' and a['id'] in bound for a in actions),
                     'explicit_recalls':sum(a['action']=='recall_observations' and a['id'] in bound for a in actions),
                     'recalled_entries_in_later_request':len(recalled_in_later),
                     'native_terminal_control_applied':any(a['action'] in {'pause','stop'} and a['id'] in bound for a in actions),
                     'new_fits':0},
        'limits':['Original failed proposal and invalid requests remain historical evidence; revisions do not rewrite them.',
                  'Memory includes actual active and retired records; inclusion is not scientific approval.',
                  'No explicit recall is inferred from memory availability or from writing a replacement decision.',
                  'Proposals do not execute experiments. Model prose and operator-assistant assessment are not scientific validation.'],
        'scientific_validation':False,'llm_weight_training':False})
    _require(_identities(paths)==before,'Revision study or shared memory changed during capture.')
    view['snapshot_sha256']=fingerprint(view)
    return view


def export_revision(workspace,iteration,output,annotation=None):
    target=Path(output).absolute()
    for part in (target,*target.parents):
        _require(not part.is_symlink() and not getattr(part,'is_junction',lambda:False)(),'Redirected output forbidden.')
    study=RevisionCloudLoop(workspace).study
    with study._connect() as con:
        config=json.loads(con.execute('SELECT * FROM meta').fetchone()['config'])
    locations=[study.root,Path(config['memory_workspace']),*(Path(v) for v in config['private_sources'].values())]
    for path in locations:
        _require(not(target==path or target.is_relative_to(path) or path.is_relative_to(target)),'Output overlaps frozen source or memory.')
    if target.exists():raise ResearchError('ALREADY_EXISTS','Use a fresh revision publication directory.')
    view=capture_revision(workspace,iteration,annotation);raw=(canonical(view)+'\n').encode('utf-8')
    _require(len(raw)<=3_000_000,'Revision view exceeds public bound.')
    manifest={'schema_version':'p02-postrun-artifacts-v1','snapshot_sha256':view['snapshot_sha256'],
              'iteration_snapshot_sha256':view['iteration_snapshot_sha256'],
              'files':{'postrun.json':{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}}}
    target.mkdir(parents=True,exist_ok=False)
    (target/'postrun.json').write_bytes(raw);(target/'manifest.json').write_text(canonical(manifest)+'\n',encoding='utf-8')
    return manifest
