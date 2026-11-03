"""Operator-triggered archival of a terminal native P02 study into separate memory."""
import json
import os
from pathlib import Path

from .chemotopo_cloud import ChemoTopoCloudLoop
from .chemotopo_delivery import load_delivery
from .chemotopo_study import ChemoTopoMemory
from .contracts import ResearchError, canonical, fingerprint


def _path(value):
    path=Path(os.path.abspath(value))
    for part in (path,*path.parents):
        if part.is_symlink() or getattr(part,'is_junction',lambda:False)():
            raise ResearchError('UNSAFE_PATH','Archive paths cannot traverse redirected paths.')
    if os.path.normcase(str(path.resolve())) != os.path.normcase(str(path)):
        raise ResearchError('UNSAFE_PATH','Archive paths must not redirect.')
    return path


def _overlaps(left,right):
    return left==right or left.is_relative_to(right) or right.is_relative_to(left)


def archive_evidence(workspace,memory_workspace,receipt):
    source=_path(workspace); target=_path(memory_workspace); output=_path(receipt)
    loop=ChemoTopoCloudLoop(source)
    snapshot=load_delivery(source)
    if snapshot['status'] not in {'paused','stopped'} or not snapshot['actions'] or snapshot['actions'][-1]['action'] not in {'pause','stop'}:
        raise ResearchError('NOT_TERMINAL','Archive requires a terminal study and committed pause or stop.')
    if any(not action['model_selected'] for action in snapshot['actions']):
        raise ResearchError('EVIDENCE_CHANGED','Every source action must bind to an applied native call.')
    with loop.study._connect() as con:
        config,state,actions=loop.study._state(con)
    protected=[source,_path(config['memory_workspace']),_path(config['source_directory'])]
    if config.get('prediction_directory'):protected.append(_path(config['prediction_directory']))
    if any(_overlaps(target,p) or _overlaps(output,p) for p in protected) or _overlaps(target,output):
        raise ResearchError('UNSAFE_PATH','Archive memory and receipt must be separate from protected sources and each other.')
    if not output.parent.is_dir(): raise ResearchError('INVALID_REQUEST','Receipt parent directory must exist.')
    memory=ChemoTopoMemory(target);memory._guard()
    derived=memory.derive_actions(config,actions)
    if derived['scope']!=state['scope'] or any(entry['kind']!='diagnostic_observation' or entry['payload'].get('type') not in {'source_qualification','prediction_diagnostic','policy_sensitivity'} for entry in derived['entries']):
        raise ResearchError('INVALID_SCOPE','Only derived numerical observations in the exact source scope may be archived.')
    check=load_delivery(source)
    if check['snapshot_sha256']!=snapshot['snapshot_sha256'] or loop.study.observe()['observation_sha256']!=state['observation_sha256']:
        raise ResearchError('EVIDENCE_CHANGED','Source changed during archival validation.')
    result={'schema_version':'p02-operator-archive-v1','status':'pending',
            'persistence_trigger':'operator_postrun_workflow',
            'model_selected_remember':any(a['action']=='remember_evidence' and a['model_selected'] for a in snapshot['actions']),
            'source_observation_sha256':state['observation_sha256'],'source_snapshot_sha256':snapshot['snapshot_sha256'],
            'scope':state['scope'],'source_actions':[{'id':a['id'],'action':a['action'],'result_sha256':a['result_sha256']} for a in actions],
            'artifact_ids':[{'action_id':a['id'],**a['result']['artifact']} for a in actions if 'artifact' in a['result']],
            'entries':[{'id':entry['id'],'record_sha256':fingerprint(entry),'type':entry['payload']['type']} for entry in derived['entries']],
            'scientific_validation':False}
    # Reserve an exclusive, explicit receipt before the only archive write. A
    # crash leaves a pending receipt; replay to a new receipt is idempotent.
    with output.open('x',encoding='utf-8') as stream:
        stream.write(canonical(result)+'\n');stream.flush();os.fsync(stream.fileno())
        try:
            imported=memory._import_derived(derived)
            with memory._connect() as con:
                statuses={}
                for entry in derived['entries']:
                    row=con.execute('SELECT * FROM entries WHERE id=?',(entry['id'],)).fetchone()
                    if row is None: raise ResearchError('EVIDENCE_CHANGED','Archived entry is missing after import.')
                    verified=memory._verify(con,row)
                    if verified['scope']!=state['scope']: raise ResearchError('EVIDENCE_CHANGED','Archived entry has unexpected scope.')
                    statuses[entry['id']]=row['status']
            result['entries']=[{**entry,'inclusion_status':statuses[entry['id']]} for entry in result['entries']]
            result.update(status='completed',import_result=imported)
        except Exception as error:
            result.update(status='failed',error_code=getattr(error,'code','ARCHIVE_FAILED'))
            stream.seek(0);stream.truncate();stream.write(canonical(result)+'\n');stream.flush();os.fsync(stream.fileno())
            raise
        stream.seek(0);stream.truncate();stream.write(canonical(result)+'\n');stream.flush();os.fsync(stream.fileno())
    return result
