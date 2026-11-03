"""Frozen, evidence-bound public projection of a P02 study; no dispatch or writes."""
import copy
import json
import re

from .chemotopo_cloud import ChemoTopoCloudLoop
from .chemotopo_study import ChemoTopoMemory
from .c01_research import ACTION_FIELDS
from .contracts import ResearchError, fingerprint


def _safe(value):
    if isinstance(value, dict):
        return {k: _safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe(v) for v in value]
    if isinstance(value, str):
        # Remove local absolute paths, keeping published URLs and simple source names.
        return re.sub(r'(?i)\b[a-z]:[\\/][^\s"<>]+|(?<![\w:/])/(?:[^\s/]+/)+[^\s,;"<>]*', '[local path]', value)
    return value


def load_delivery(workspace):
    loop = ChemoTopoCloudLoop(workspace)
    # status/observe use guarded read-only connections and enforce current identities.
    status = loop.status()
    state = status['study']
    actions = {a['id']: a for a in state['actions']}
    bound = set()
    with loop._connect() as con:
        project, spec, current = loop._state(con)
        if current['observation_sha256'] != state['observation_sha256']:
            raise ResearchError('EVIDENCE_CHANGED', 'study changed while building snapshot')
        rows = [dict(row) for row in con.execute('SELECT * FROM calls ORDER BY ordinal')]
        for index, row in enumerate(rows, 1):
            if row['ordinal'] != index:
                raise ResearchError('EVIDENCE_CHANGED', 'controller call sequence changed')
            observation = json.loads(row['observation_json'])
            body = json.loads(row['request_json'])
            if fingerprint(body) != row['request_sha256'] or fingerprint({k:v for k,v in observation.items() if k != 'observation_sha256'}) != observation['observation_sha256']:
                raise ResearchError('EVIDENCE_CHANGED', 'controller request or observation changed')
            context = json.loads(body['messages'][1]['content'])
            if (context.get('observation_sha256') != observation['observation_sha256']
                    or context.get('memory_context') != observation['memory_context']):
                raise ResearchError('EVIDENCE_CHANGED', 'native request context differs from captured observation')
            if row['response_json'] is not None:
                response = json.loads(row['response_json'])
                if fingerprint(response) != row['response_sha256']:
                    raise ResearchError('EVIDENCE_CHANGED', 'controller response changed')
            if row['status'] != 'applied':
                continue
            action = actions.get(row['action_id'])
            if action is None or row['action_id'] in bound or row['response_json'] is None:
                raise ResearchError('EVIDENCE_CHANGED', 'applied call lacks its unique action')
            loop._validate_response(response, spec)
            decision = loop._parse_decision(response, observation, row['request_id'], body)
            if json.loads(row['decision_json']) != decision or decision != {k:action[k] for k in ACTION_FIELDS}:
                raise ResearchError('EVIDENCE_CHANGED', 'native response and committed action differ')
            bound.add(action['id'])
    # Include original memory records and all verified provenance versions.
    with loop.study._connect() as con:
        config, rechecked, _ = loop.study._state(con)
    if rechecked['observation_sha256'] != state['observation_sha256']:
        raise ResearchError('EVIDENCE_CHANGED', 'memory or study changed while building snapshot')
    memory = ChemoTopoMemory(config['memory_workspace'])
    entries = []
    with memory._connect() as con:
        if con is not None:
            for row in con.execute('SELECT * FROM entries WHERE scope_sha256=? ORDER BY id', (fingerprint(state['scope']),)):
                record = memory._verify(con, row)
                versions = memory._versions(con, row['id'])
                if (record['scope'] != state['scope'] or _safe(record) != record or _safe(versions) != versions):
                    raise ResearchError('EVIDENCE_CHANGED', 'memory provenance cannot be safely projected')
                entries.append({'record': record, 'record_sha256': row['record_sha256'],
                                'inclusion_status': row['status'], 'source_versions': versions})
    active = {(entry['record']['id'], entry['record_sha256']) for entry in entries if entry['inclusion_status'] == 'active'}
    observed = {(entry['id'], entry['record_sha256']) for entry in state['memory_context']['entries']}
    if active != observed:
        raise ResearchError('EVIDENCE_CHANGED', 'memory changed while building snapshot')
    projected=[]
    for action in state['actions']:
        result=action['result']
        summary=result.get('summary', result) if isinstance(result, dict) else result
        projected.append(_safe({**{k:action[k] for k in ('id','ordinal','action','reason','parameters','source_citation_ids','evidence_action_ids','result_sha256')},
                                'summary':summary,'model_selected':action['id'] in bound}))
    comparison=next((a['result']['summary'] for a in state['actions'] if a['action']=='compare_policies'),None)
    payload=_safe({'schema_version':'p02-workbench-v1','case_id':'P02-ChemoTopoChip',
        'goal':state['goal'],'status':state['status'],'scope':state['scope'],'endpoint_gate':state['endpoint_gate'],
        'scientific_validation':False,'source_manifest':state['source_manifest']['files'],'citations':state['citations'],
        'actions':projected,'comparison':comparison,'memory':{'entries':entries,'scope':state['scope']},
        'execution':{'model':status['model_identity']['model'],'requests_reserved':len(rows),'max_requests':status['budget']['max_requests'],
                     'applied_calls':sum(r['status']=='applied' for r in rows),'invalid_calls':sum(r['status']=='invalid' for r in rows),
                     'explicit_recalls':sum(a['action']=='recall_evidence' and a['id'] in bound for a in state['actions'])}})
    payload['snapshot_sha256']=fingerprint(payload)
    return payload
