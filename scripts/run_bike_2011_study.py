#!/usr/bin/env python3
"""Fixed, operator-supervised Bike 2011 study. No source download.

Real execution requires a published detached pin, an active cooperating lease,
a prepared and reviewed source, and a unique claim. Each command makes at most
one native mutation. An intent without its completion receipt is a stop, never
an invitation to dispatch it again. This is a local coordination protocol, not
an OS security boundary or a scientific validation.
"""
import argparse
import csv
from contextlib import ExitStack, contextmanager
import hashlib
import io
import importlib.metadata
import tempfile
import unicodedata
import json
import math
import os
from pathlib import Path
import subprocess
import socket
from unittest.mock import patch
from urllib.parse import urlsplit
import sys
import time

# Never consume pre-existing bytecode from the source pin.
_PRIVATE_CACHE = tempfile.TemporaryDirectory(prefix='bike-2011-pycache-')
sys.pycache_prefix = _PRIVATE_CACHE.name
sys.dont_write_bytecode = True

from autoresearch import tabular_quality_adapter as tabular
from autoresearch.contracts import canonical, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController, code_identity as controller_identity
from autoresearch.research_project import ResearchProject, code_identity as project_identity

REPO = Path(__file__).resolve().parent.parent
STUDY = 'bike-sharing-2011-v1'
WORKSPACE = REPO / 'runs' / STUDY
CLAIM = REPO.parent / '.study-claims' / (STUDY + '.json')
LEASE = REPO.parent.parent / 'auto-research-agentarts/.agent/autonomy/lease.json'
PROTOCOL = REPO / 'docs/project/bike-sharing-2011-study-proposal.md'
IDS = {'cap':'bike-2011-evidence-zero', 'import':'bike-2011-import', 'select':'bike-2011-select',
       'plan1':'bike-2011-plan-v1', 'quality':'bike-2011-quality', 'feedback1':'bike-2011-quality-feedback',
       'plan2':'bike-2011-plan-v2', 'association':'bike-2011-association',
       'feedback2':'bike-2011-association-feedback', 'plan3':'bike-2011-plan-v3'}
GOAL = 'For all daily 2011 records, describe Pearson correlation of temp and cnt overall and separately for workingday 0 and 1.'
BUDGET = 'bike-sharing-2011-v1:independent-2-tools-zero-model-fit-evidence'
PURPOSE = 'operator_declared_descriptive_research'
STAGES = ('create', 'cap', 'import', 'select', 'plan1', 'quality', 'feedback1', 'plan2',
          'association', 'feedback2', 'plan3')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return canonical(value).encode('utf-8')


def save_once(path, data):
    # Exclusive file creation; partial files remain evidence after a failure.
    require(not path.is_symlink(), 'Refusing symlink.')
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save_json(path, value):
    save_once(path, encode(value))


def read_json(path):
    require(path.is_file() and not path.is_symlink(), 'Missing or unsafe original: ' + str(path))
    raw = path.read_bytes()
    obj = json.loads(raw)
    require(encode(obj) == raw, 'Noncanonical or changed JSON: ' + str(path))
    return obj


def git(*args):
    return subprocess.check_output(['git', '-C', str(REPO), *args], text=True).strip()


def published_identity():
    commit = git('rev-parse', 'HEAD')
    require(len(commit) == 40 and all(c in '0123456789abcdef' for c in commit), 'Invalid full commit.')
    require(REPO.parent.name == 'source-pins' and REPO.name == commit[:7], 'Use the unique detached published source pin.')
    require(not git('status', '--porcelain', '--untracked-files=normal'), 'Dirty pin.')
    require(subprocess.run(['git', '-C', str(REPO), 'symbolic-ref', '-q', 'HEAD'], capture_output=True).returncode != 0,
            'Pin must be detached.')
    require(subprocess.run(['git', '-C', str(REPO), 'merge-base', '--is-ancestor', commit, 'refs/remotes/origin/main']).returncode == 0,
            'Commit is not contained in the observed origin/main ref.')
    require(Path(tabular.__file__).resolve().is_relative_to(REPO / 'src'), 'Adapter is not from this pin.')
    for module in ('autoresearch.research_project', 'autoresearch.project_controller', 'autoresearch.local_workbench'):
        require(Path(sys.modules[module].__file__).resolve().is_relative_to(REPO / 'src'), 'Core module is not from pin: ' + module)
    require(git('ls-files', '--error-unmatch', 'scripts/run_bike_2011_study.py') == 'scripts/run_bike_2011_study.py', 'Driver not tracked.')
    return {'commit':commit, 'project_core':project_identity(), 'controller_core':controller_identity(),
            'driver_sha256':sha(Path(__file__).read_bytes()),
            'preparation_sha256':sha((REPO/'scripts/prepare_bike_2011_source.py').read_bytes()),
            'protocol_sha256':sha(PROTOCOL.read_bytes()), 'python':sys.version,
            'executable':str(Path(sys.executable).resolve()), 'unicode':unicodedata.unidata_version,
            'dependencies':{name:importlib.metadata.version(name) for name in ('numpy','scipy','scikit-learn')}}


def active_owner():
    lease = json.loads(LEASE.read_bytes())
    require(lease.get('schema_version') == 'project-autonomy-lease-v1' and lease.get('status') == 'active'
            and type(lease.get('owner')) is str and lease['owner'] and type(lease.get('expires')) in (float, int)
            and lease['expires'] > time.time(), 'An active cooperating lease is required.')
    return lease['owner']


def init():
    identity, owner = published_identity(), active_owner()
    require(not CLAIM.exists() and not WORKSPACE.exists(), 'Claim or workspace exists; inspect original and stop.')
    require(CLAIM.parent.is_dir() and not CLAIM.parent.is_symlink(), 'Claim directory missing or unsafe.')
    claim = {'schema_version':'bike-2011-claim-v1', 'study':STUDY, 'workspace':str(WORKSPACE),
             'identity':identity, 'created_by_owner':owner, 'budget_ref':BUDGET, 'request_ids':IDS}
    save_json(CLAIM, claim)
    WORKSPACE.mkdir(mode=0o700, parents=True, exist_ok=False)
    (WORKSPACE/'requests').mkdir(mode=0o700)
    save_json(WORKSPACE/'claim-copy.json', claim)
    return {'status':'claimed', 'claim':str(CLAIM), 'workspace':str(WORKSPACE), 'identity':identity}


def checked_claim():
    identity, owner = published_identity(), active_owner()
    claim = read_json(CLAIM)
    require(claim == read_json(WORKSPACE/'claim-copy.json'), 'Claim copy differs or incomplete initialization.')
    require(claim['study'] == STUDY and claim['workspace'] == str(WORKSPACE) and claim['identity'] == identity
            and claim['budget_ref'] == BUDGET and claim['request_ids'] == IDS, 'Claim or runtime identity changed.')
    return claim, owner


def checked_source():
    root = WORKSPACE/'source'
    receipt_path = root/'receipt.json'
    require(receipt_path.is_file() and not receipt_path.is_symlink(), 'Missing source receipt.')
    receipt = tabular._parse(receipt_path.read_bytes())
    require(receipt.get('schema_version') == 'bike-2011-source-preparation-v1', 'Wrong source preparation.')
    identity = read_json(CLAIM)['identity']
    require(receipt.get('preparation_identity') == {'commit':identity['commit'],
            'script_sha256':identity['preparation_sha256'], 'python':identity['python'],
            'executable':identity['executable']}, 'Preparation code or runtime differs from claim.')
    acquisition_marker_path = WORKSPACE/'source-acquisition-started.json'
    acquisition_receipt_path = WORKSPACE/'acquisition/receipt.json'
    acquisition_original_path = WORKSPACE/'acquisition/original.zip'
    for path in (acquisition_marker_path, acquisition_receipt_path, acquisition_original_path):
        require(path.is_file() and not path.is_symlink(), 'Missing original acquisition evidence.')
    acquisition_marker = tabular._parse(acquisition_marker_path.read_bytes())
    acquisition = tabular._parse(acquisition_receipt_path.read_bytes())
    official_zip = 'https://archive.ics.uci.edu/static/public/275/bike+sharing+dataset.zip'
    require(acquisition_marker == {'schema_version':'bike-2011-source-acquisition-started-v1',
            'source_url':official_zip, 'commit':identity['commit'], 'script_sha256':identity['preparation_sha256'],
            'output':str(acquisition_original_path)}, 'Acquisition marker differs from claim.')
    require(set(acquisition) == {'schema_version','requested_url','final_url','acquired_at_utc','bytes','sha256',
            'commit','script_sha256','path','clock_status','started_sha256'} and acquisition['schema_version'] == 'bike-2011-source-acquisition-v1'
            and acquisition['requested_url'] == official_zip and acquisition['path'] == 'acquisition/original.zip'
            and acquisition['commit'] == identity['commit'] and acquisition['script_sha256'] == identity['preparation_sha256']
            and acquisition['clock_status'] == 'local_clock_not_independently_verified'
            and acquisition['started_sha256'] == sha(acquisition_marker_path.read_bytes())
            and acquisition['acquired_at_utc'] == receipt['acquired_at_utc']
            and receipt['acquisition_receipt_sha256'] == sha(acquisition_receipt_path.read_bytes()),
            'Acquisition receipt differs from claim or prepared source.')
    parts = urlsplit(acquisition['final_url'])
    require(parts.scheme == 'https' and parts.hostname == 'archive.ics.uci.edu' and parts.port in (None,443)
            and parts.username is None and parts.password is None and not parts.fragment, 'Acquisition final URL differs.')
    acquired_bytes = acquisition_original_path.read_bytes()
    require(type(acquisition['bytes']) is int and 0 < acquisition['bytes'] <= 4*1024*1024
            and len(acquired_bytes) == acquisition['bytes'] and sha(acquired_bytes) == acquisition['sha256'],
            'Acquired original differs from receipt.')
    marker_path = WORKSPACE/'source-preparation-started.json'
    require(marker_path.is_file() and not marker_path.is_symlink(), 'Missing preparation start marker.')
    marker = tabular._parse(marker_path.read_bytes())
    require(set(marker) == {'schema_version','commit','script_sha256','expected_zip_sha256','acquired_at_utc','output'}
            and marker['schema_version'] == 'bike-2011-source-preparation-started-v1'
            and marker['commit'] == identity['commit'] and marker['script_sha256'] == identity['preparation_sha256']
            and marker['output'] == str(root) and marker['acquired_at_utc'] == receipt['acquired_at_utc']
            and receipt['source_url'] == 'https://archive.ics.uci.edu/static/public/275/bike+sharing+dataset.zip',
            'Preparation marker differs from source receipt or claim.')
    files = receipt['files']
    require(files['original_zip']['sha256'] == marker['expected_zip_sha256'] == acquisition['sha256']
            and files['original_zip']['bytes'] == acquisition['bytes'], 'Original ZIP differs from acquisition or start marker.')
    paths = {'original_zip':'original.zip', 'original_day':'day.csv', 'original_readme':'README.txt',
             'projection':'development/bike-2011.csv', 'spec':'development/spec.json', 'packet':'source.json'}
    require(set(files) == set(paths), 'Unexpected source inventory.')
    for name, relative in paths.items():
        entry = files[name]
        require(set(entry) == {'path','bytes','sha256'} and entry['path'] == relative, 'Unexpected inventory path.')
        path = root/relative
        require(path.is_file() and not path.is_symlink(), 'Missing source original.')
        raw = path.read_bytes()
        require(len(raw) == entry['bytes'] and sha(raw) == entry['sha256'], 'Source changed: ' + name)
    packet_raw = (root/'source.json').read_bytes()
    packet = tabular.load_source(packet_raw)
    require(packet['snapshot_sha256'] == receipt['source_snapshot_sha256'], 'Packet snapshot mismatch.')
    require(packet['source']['sha256'] == files['projection']['sha256']
            and packet['spec_source']['sha256'] == files['spec']['sha256'], 'Packet input mismatch.')
    spec = packet['spec']
    require(spec['key_columns'] == ['dteday'] and spec['group_columns'] == ['workingday']
            and spec['numeric_columns'] == ['temp','cnt'] and spec['target_column'] == 'cnt'
            and spec['target_unit'] == 'rentals per day' and spec['delimiter'] == ',' and spec['missing_tokens'] == ['']
            and spec['provenance']['origin_sha256'] == files['original_day']['sha256'], 'Spec differs from protocol.')
    rows = list(csv.DictReader(io.StringIO((root/'development/bike-2011.csv').read_text(encoding='utf-8'), newline='')))
    import datetime
    require(len(rows) == 365 and all(list(row) == ['dteday','workingday','temp','cnt'] for row in rows), 'Projection shape differs.')
    expected = [(datetime.date(2011,1,1)+datetime.timedelta(days=i)).isoformat() for i in range(365)]
    require([r['dteday'] for r in rows] == expected, 'Dates differ from fixed sample.')
    groups = [r['workingday'] for r in rows]
    require(set(groups) == {'0','1'} and min(groups.count('0'), groups.count('1')) >= 3, 'Groups differ from fixed sample.')
    review = read_json(WORKSPACE/'source-review.json')
    require(set(review) == {'schema_version','receipt_sha256','reviewer','reviewed_at_utc','source_verified',
                            'license_verified','fields_verified','notes','official_evidence','preparation_marker_sha256'}
            and review['schema_version'] == 'bike-2011-source-review-v1'
            and review['receipt_sha256'] == sha((root/'receipt.json').read_bytes())
            and review['preparation_marker_sha256'] == sha(marker_path.read_bytes())
            and all(review[k] is True for k in ('source_verified','license_verified','fields_verified'))
            and all(type(review[k]) is str and review[k].strip() for k in ('reviewer','reviewed_at_utc','notes')),
            'Missing or mismatched operator source and license review.')
    expected_evidence = {
        'uci_dataset':('evidence/uci-dataset.html','https://archive.ics.uci.edu/dataset/275/bike+sharing+dataset'),
        'uci_metadata':('evidence/uci-metadata.json','https://archive.ics.uci.edu/api/dataset?id=275'),
        'license':('evidence/cc-by-4.0.html','https://creativecommons.org/licenses/by/4.0/')}
    evidence = review['official_evidence']
    require(type(evidence) is dict and set(evidence) == set(expected_evidence), 'Missing official evidence inventory.')
    for name, (relative, url) in expected_evidence.items():
        item = evidence[name]
        require(type(item) is dict and set(item) == {'path','url','bytes','sha256'}
                and item['path'] == relative and item['url'] == url, 'Official evidence identity differs.')
        path = WORKSPACE/relative
        require(path.is_file() and not path.is_symlink(), 'Missing official evidence original.')
        raw = path.read_bytes()
        require(len(raw) == item['bytes'] and sha(raw) == item['sha256'], 'Official evidence bytes changed.')
    return packet, rows, {'receipt_sha256':sha((root/'receipt.json').read_bytes()),
                          'review_sha256':sha((WORKSPACE/'source-review.json').read_bytes()),
                          'preparation_marker_sha256':sha(marker_path.read_bytes()),
                          'acquisition_marker_sha256':sha(acquisition_marker_path.read_bytes()),
                          'acquisition_receipt_sha256':sha(acquisition_receipt_path.read_bytes()),
                          'packet_sha256':sha(packet_raw), 'snapshot_sha256':packet['snapshot_sha256']}


def quality_gate(profile):
    try:
        cols = profile['numeric_columns']
        by_name = {c['name']:c['counts'] for c in cols}
        return (type(profile['rows']) is int and profile['rows'] == 365 and profile['columns'] == 4
                and profile['exact_duplicate_rows'] == 0 and profile['key_columns']['incomplete_rows'] == 0
                and profile['key_columns']['duplicate_rows'] == 0 and profile['key_columns']['conflict_groups'] == 0
                and profile['group_columns']['incomplete_group_rows'] == 0
                and profile['group_columns']['group_count'] == 2
                and type(profile['group_columns']['min_group_size']) is int and profile['group_columns']['min_group_size'] >= 3
                and profile['flags'] == [] and len(cols) == 2 and set(by_name) == {'temp','cnt'}
                and all(c['finite'] == 365 and all(c[k] == 0 for k in ('empty','declared_missing','invalid_numeric','nonfinite'))
                        for c in by_name.values()))
    except (KeyError, TypeError, ValueError):
        return False


def association_outcome(result, rows):
    try:
        require(result['summary']['rows'] == 365 and result['summary']['group_count'] == 2
                and result['summary']['incomplete_group_rows'] == 0 and len(result['groups']) == 2, 'Association group identity differs.')
        require(len(result['overall']) == 1 and result['overall'][0]['predictor'] == 'temp', 'Unexpected overall association.')
        groups = {}
        for group in result['groups']:
            index = group['first_coordinate']['logical_record']
            require(type(index) is int and 1 <= index <= len(rows), 'Invalid group coordinate.')
            key = rows[index-1]['workingday']
            require(key in ('0','1') and key not in groups and len(group['associations']) == 1, 'Group coordinate mismatch.')
            require(group['associations'][0]['predictor'] == 'temp' and group['rows'] == sum(r['workingday'] == key for r in rows),
                    'Group rows or predictor mismatch.')
            groups[key] = group['associations'][0]
        require(set(groups) == {'0','1'}, 'Missing encoded group.')
        items = [result['overall'][0], groups['0'], groups['1']]
        for item, n in zip(items, (365, sum(r['workingday']=='0' for r in rows), sum(r['workingday']=='1' for r in rows))):
            r = item['pearson_r']
            if (type(item['n']) is not int or type(item['excluded']) is not int or item['n'] < 3
                or item['n'] != n or item['excluded'] != 0 or item['reason'] is not None or type(r) not in (int,float)
                or not math.isfinite(r) or not -1 <= r <= 1):
                return {'outcome':'unknown','overall':items[0], 'groups':groups}
        return {'outcome':'condition_met' if all(v['pearson_r'] > 0 for v in items) else 'condition_not_met',
                'overall':items[0], 'groups':groups}
    except (KeyError, TypeError, ValueError, RuntimeError):
        return {'outcome':'unknown', 'reason':'Association result or group identity is incomplete or inconsistent.'}


def request_path(stage, suffix):
    return WORKSPACE/'requests'/(stage + suffix + '.json')


def last_completed():
    completed = []
    for stage in STAGES:
        intent, result = request_path(stage,''), request_path(stage,'.result')
        context = request_path(stage,'.context')
        require(intent.exists() == result.exists(), 'Incomplete original request: ' + stage)
        require(not context.exists() or (stage in ('quality','association') and intent.exists()),
                'Incomplete original context: ' + stage)
        if intent.exists():
            require(len(completed) == STAGES.index(stage), 'Noncontiguous request journal.')
            completed.append(stage)
    return completed


def check_budget(state, used, cap=True):
    b = state['budget']
    require(b['local_tool_call_limit'] == 2 and b['local_tool_calls_used'] == used
            and b['local_tool_calls_reserved'] == 0 and b['model_requests_allowed'] == 0
            and b['model_requests_reserved'] == b['new_model_requests'] == b['new_fits'] == b['fit_attempts_used'] == 0
            and b['fits_reserved'] == b['evidence_reads_used'] == b['evidence_reads_reserved'] == 0
            and b['evidence_read_limit'] == (0 if cap else 8), 'Budget differs or pending reservation.')


def run_stage(stage):
    checked_claim()
    packet, rows, source_identity = checked_source()
    done = last_completed()
    require(stage == STAGES[len(done)] if len(done) < len(STAGES) else False, 'Wrong stage or already completed; do not reissue.')
    if done:
        previous = read_json(request_path(done[-1],'.result'))
        require(previous['source_identity'] == source_identity, 'Source review or identity drift.')
        if done[-1] == 'create' or done[-1] == 'cap':
            project = ResearchProject(WORKSPACE/'project-before-import')
        else:
            project = ResearchProject(previous['project_root'])
        state = project.status()
        require(state == previous['state'], 'Project state differs from original completed stage.')
    else:
        project, state = None, None
    if stage == 'create':
        require(not (WORKSPACE/'project-before-import').exists() and not (WORKSPACE/'manager').exists(), 'Partial project or manager exists.')
        body = {'source':str(WORKSPACE/'source/source.json'), 'goal':GOAL, 'budget_ref':BUDGET, 'max_tool_calls':2,
                'method_id':tabular.TOOL_ID, 'evidence_purpose':PURPOSE}
        project = ResearchProject(WORKSPACE/'project-before-import')
    elif stage == 'cap':
        check_budget(state,0,False)
        body = {'request_id':IDS[stage], 'expected_limit':8, 'new_limit':0, 'expected_state_version':state['state_version'],
                'reason':'The approved Bike 2011 study excludes native evidence reads.'}
    elif stage == 'import':
        check_budget(state,0)
        require(not (WORKSPACE/'manager').exists(), 'Manager already exists or partial.')
        body = {'request_id':IDS[stage], 'workspace':str(project.root)}
    elif stage == 'select':
        check_budget(state,0)
        body = {'request_id':IDS[stage], 'project_id':state['id']}
    elif stage in ('plan1','plan2','plan3','feedback1','feedback2','quality','association'):
        used = 0 if stage in ('plan1','quality') else 1 if stage in ('feedback1','plan2','association') else 2
        check_budget(state, used)
        if stage == 'plan1':
            plan = {'question':GOAL, 'basis':'Reviewed UCI 2011 daily projection and original source identities.',
                    'steps':'Check quality first; use the bound association only if the fixed quality gate passes.',
                    'expected_feedback':'Three valid positive correlations mean condition_met; any invalid result means unknown.'}
            body = {'request_id':IDS[stage], 'expected_state_version':state['state_version'], 'plan':plan,
                    'reason':'Fix the descriptive question and stopping conditions before the first action.'}
        elif stage in ('quality','association'):
            if stage == 'association':
                require(read_json(request_path('feedback1','.result'))['quality_passed'] is True, 'Quality gate did not pass.')
                predecessor = saved_action(project, state, 'quality', tabular.TOOL_ID)
            ctx = ProjectController(project.root).selection_context()
            method = tabular.TOOL_ID if stage == 'quality' else 'data.numeric-association'
            evaluation = 'tabular-quality-v1' if stage == 'quality' else 'numeric-association-v1'
            candidates = [v for v in ctx['candidates'] if v['method_id'] == method]
            conditions = [v for v in ctx['conditions'] if v['method_id'] == method]
            require(not ctx['blockers'] and len(candidates) == len(conditions) == 1
                    and candidates[0]['evaluation_ref'] == evaluation
                    and conditions[0]['budget_cost'] == {'local_tool_calls':1,'evidence_reads':0,'estimator_fits':0}, 'Candidate unavailable or blocked.')
            if stage == 'association':
                require(candidates[0]['parameters'] == {'based_on_action_id':predecessor['id'],
                        'based_on_result_sha256':predecessor['result_sha256']}, 'Candidate predecessor differs.')
            else:
                require(candidates[0]['parameters'] == {}, 'Quality parameters differ.')
            proposal = {'schema_version':'project-selection-proposal-v1', 'context_sha256':ctx['context_sha256'],
                        'provider':{'kind':'human','label':'operator'}, 'choice':{'kind':'execute','candidate_id':candidates[0]['id']},
                        'rationale':'Follow the fixed Bike 2011 descriptive protocol and saved observations.', 'evidence_citation_ids':[]}
            save_json(request_path(stage,'.context'), ctx)
            body = {'request_id':IDS[stage], 'proposal':proposal, 'expected_state_version':state['state_version']}
        else:
            quality = saved_action(project,state,'quality',tabular.TOOL_ID)
            qresult = artifact(project,quality)['tool_result']['result']['profile']
            passed = quality_gate(qresult)
            observation = 'Quality profile: ' + canonical(qresult)
            if stage == 'feedback1':
                body = {'request_id':IDS[stage], 'expected_state_version':state['state_version'], 'author':'operator',
                        'comment':observation, 'next_step':'Select bound numeric association.' if passed else 'Wait for source or quality review.',
                        'action_id':quality['id']}
            elif stage == 'plan2':
                plan = {'question':GOAL, 'basis':observation,
                        'steps':'Select original quality-bound numeric association.' if passed else 'Wait; do not execute association.',
                        'expected_feedback':'Unknown takes priority over a non-positive value.'}
                body = {'request_id':IDS[stage], 'expected_state_version':state['state_version'], 'plan':plan,
                        'reason':'Revise using the completed quality action and fixed gate.'}
            else:
                second = saved_action(project,state,'association','data.numeric-association')
                result = artifact(project,second)['tool_result']['result']
                expected_predecessor = {'based_on_action_id':quality['id'], 'based_on_result_sha256':quality['result_sha256']}
                if (result.get('predecessor') != expected_predecessor
                        or result.get('source_snapshot_sha256') != state['source_snapshot_sha256']):
                    details = {'outcome':'unknown','reason':'Association source or quality predecessor differs.'}
                else:
                    details = association_outcome(result, rows)
                if stage == 'feedback2':
                    body = {'request_id':IDS[stage], 'expected_state_version':state['state_version'], 'author':'operator',
                            'comment':'Observed association: '+canonical(details), 'next_step':'Wait; no further actions authorized.', 'action_id':second['id']}
                else:
                    plan = {'question':GOAL, 'basis':'Observed association: '+canonical(details),
                            'steps':'Wait; no further actions authorized.',
                            'expected_feedback':'Descriptive 2011 sample only; retain unknown and competing time/season explanations.'}
                    body = {'request_id':IDS[stage], 'expected_state_version':state['state_version'], 'plan':plan,
                            'reason':'Preserve the observed association and stop.'}
    save_json(request_path(stage,''), body)
    if stage == 'create': result = project.create(**body)
    elif stage == 'cap': result = project.limit_evidence_budget(**body)
    elif stage == 'import':
        manager = LocalWorkbench(WORKSPACE/'manager')
        result = manager.import_project(**body)
        with manager._connect(readonly=True) as connection: _, project = manager._project(connection, result['project_id'])
    elif stage == 'select': result = LocalWorkbench(WORKSPACE/'manager').select(body)
    elif stage.startswith('plan'): result = project.save_plan(**body)
    elif stage.startswith('feedback'): result = project.record_feedback(**body)
    else:
        result = ProjectController(project.root).advance_selection(**body)
        require(result['status'] == 'completed' and not result.get('replayed'), 'Nonterminal or unexpected replay: stop.')
    state = project.status()
    used = 0 if stage in ('create','cap','import','select','plan1') else 1 if stage in ('quality','feedback1','plan2') else 2
    check_budget(state,used,stage != 'create')
    require(state['source_snapshot_sha256'] == packet['snapshot_sha256'] and state['evidence_purpose'] == PURPOSE, 'Project source or purpose changed.')
    if stage in ('quality','association'):
        saved_action(project,state,stage,tabular.TOOL_ID if stage == 'quality' else 'data.numeric-association', result)
    receipt = {'result':result, 'state':state, 'project_root':str(project.root), 'source_identity':source_identity}
    if stage == 'feedback1': receipt['quality_passed'] = passed
    save_json(request_path(stage,'.result'),receipt)
    return {'stage':stage,'project_id':state['id'],'run_id':state['run_id'],'state_version':state['state_version'],
            'tool_calls_used':used,'quality_passed':receipt.get('quality_passed')}


def artifact(project, action):
    raw = (project.root/action['artifact']).read_bytes()
    envelope = json.loads(raw)
    require(envelope['sha256'] == action['result_sha256'] == fingerprint({k:v for k,v in envelope.items() if k != 'sha256'}),
            'Action artifact identity differs.')
    state = project.status()
    require(envelope['action_id'] == action['id'] and envelope['request_sha256'] == action['request_sha256']
            and envelope['source_snapshot_sha256'] == action['source_snapshot_sha256'] == state['source_snapshot_sha256']
            and envelope['code_identity'] == action['code_identity'] == state['code_identity']
            and envelope['tool_result']['tool_id'] == action['command']
            and envelope['tool_result']['status'] == 'completed'
            and envelope['tool_result']['model_calls'] == 0 and envelope['tool_result']['new_fits'] == 0,
            'Action envelope binding differs.')
    return envelope


def saved_action(project, state, stage, method, response=None):
    parent = [p for p in state['controller_requests'] if p['request_id'] == IDS[stage]]
    actions = [a for a in state['actions'] if a['command'] == method]
    require(len(parent) == len(actions) == 1 and actions[0]['status'] == 'completed', 'Original action is absent, duplicate or nonterminal.')
    parent = parent[0]
    body = read_json(request_path(stage,''))
    context = read_json(request_path(stage,'.context'))
    require(parent['request_sha256'] == fingerprint(parent['request'])
            and parent['request']['proposal'] == body['proposal']
            and parent['request']['expected_state_version'] == body['expected_state_version']
            and parent['selection_context'] == context and context['context_sha256'] == body['proposal']['context_sha256']
            and parent['project_id'] == state['id'] and parent['source_snapshot_sha256'] == state['source_snapshot_sha256']
            and parent['code_identity'] == state['code_identity']
            and parent['controller_code_identity'] == controller_identity()
            and actions[0]['project_id'] == state['id'] and actions[0]['run_id'] == state['run_id'],
            'Original controller context, proposal or source identity differs.')
    child = parent['result']['child']
    require(parent['status'] == 'completed' and child['id'] == actions[0]['id']
            and child['result_sha256'] == actions[0]['result_sha256'] and child['status'] == 'completed', 'Parent/child mismatch.')
    if response is not None:
        require(response['result']['child'] == child, 'Receipt does not match original child.')
    artifact(project,actions[0])
    return actions[0]


@contextmanager
def selected_execution_guards():
    # Selected entry points only; this is not an OS/network sandbox.
    from autoresearch import host_model_selection as host
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    def forbidden(*args, **kwargs):
        raise RuntimeError('Model, selected fit, network or native evidence entry is forbidden.')
    with ExitStack() as stack:
        for obj, name in ((socket.socket,'connect'), (socket,'create_connection'),
                          (Ridge,'fit'), (StandardScaler,'fit'), (ResearchProject,'read_evidence'),
                          (host.HostModelSelection,'prepare'), (host.HostModelSelection,'request'),
                          (host,'run_claude_selection')):
            stack.enter_context(patch.object(obj,name,side_effect=forbidden))
        yield


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('init', *STAGES, 'inspect'))
    args = parser.parse_args()
    with selected_execution_guards():
        if args.stage == 'init': result = init()
        elif args.stage == 'inspect':
            checked_claim(); _, _, source_identity = checked_source()
            result = {'completed':last_completed(), 'source_identity':source_identity}
        else: result = run_stage(args.stage)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))


if __name__ == '__main__':
    main()
