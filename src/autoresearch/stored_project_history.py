"""Bounded saved plans and report references, never execution or recovery."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat

from .research_project import safe_path
from .contracts import ResearchError, canonical, fingerprint

_MAX_RECORD = 4 * 1024 * 1024
_MAX_HISTORY = 256 * 1024
_MAX_ITEMS = 256
_REPORT_FILES = {'report.json', 'report.md', 'report.pdf', 'input.json'}


class _Failure(Exception):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status = status


def _need(condition, status, reason):
    if not condition:
        raise _Failure(status, reason)


def _parse(raw):
    _need(type(raw) is str and len(raw.encode('utf-8')) <= _MAX_RECORD, 'partial', 'A saved record is missing or too large.')
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError('duplicate field')
            out[key] = value
        return out
    def finite(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError('nonfinite')
        return number
    try:
        return json.loads(raw, object_pairs_hook=unique, parse_float=finite,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
    except (ValueError, UnicodeError, RecursionError):
        raise _Failure('integrity_error', 'A saved record is malformed.') from None


def _receipt(manager, request_id, command, project_id, *, expected_plan=None):
    if not isinstance(request_id, str) or not request_id or len(request_id) > 256:
        return {'view_status': 'not_recorded'}
    row = manager.execute('SELECT command,length(CAST(record AS BLOB)) FROM requests WHERE id=?', (request_id,)).fetchone()
    if row is None:
        return {'view_status': 'unavailable', 'request_id': request_id}
    if row[0] != command or type(row[1]) is not int or row[1] > _MAX_RECORD:
        return {'view_status': 'integrity_error', 'request_id': request_id}
    record = _parse(manager.execute('SELECT record FROM requests WHERE id=?', (request_id,)).fetchone()[0])
    if type(record) is not dict or type(record.get('intent')) is not dict or record['intent'].get('project_id') is None:
        return {'view_status': 'partial', 'request_id': request_id}
    if record['intent']['project_id'] != project_id:
        return {'view_status': 'integrity_error', 'request_id': request_id}
    result = record.get('result')
    if result is not None and (type(result) is not dict or result.get('project_id') not in (None, project_id)
                               or result.get('request_id') not in (None, request_id)):
        return {'view_status': 'integrity_error', 'request_id': request_id}
    complete = type(record.get('status')) is str and 'result' in record
    if result is not None:
        complete = complete and result.get('project_id') == project_id and result.get('request_id') == request_id
    view = {'view_status': 'available' if complete else 'partial', 'request_id': request_id, 'command': command,
            'record_status': record.get('status'), 'result_status': result.get('status') if result is not None else None,
            'result_recorded': 'result' in record, 'result_present': result is not None,
            'intent': {k: record['intent'].get(k) for k in ('project_id', 'report_slot', 'snapshot_ref', 'state_version') if k in record['intent']}}
    if command == 'save_plan':
        saved = result.get('research_plan') if type(result) is dict else None
        view['plan_binding_status'] = 'not_recorded' if saved is None else 'matched' if saved == expected_plan else 'mismatch'
        if view['plan_binding_status'] != 'matched':
            view['view_status'] = 'integrity_error' if view['plan_binding_status'] == 'mismatch' else 'partial'
    return view


def _request_handoff(controller, manager, project_id):
    """Prove a canonical semantic manager body from two saved request identities."""
    view = {'schema_version': 'stored-original-request-handoff-v1',
            'scope': 'canonical_semantic_body_only_not_execution_authorization', 'status': 'partial'}
    try:
        request_id, request = controller.get('request_id'), controller.get('request')
        _need(type(request_id) is str and bool(request_id) and type(request) is dict,
              'partial', 'The original controller request or identity is not recorded.')
        _need(controller.get('project_id') is not None, 'partial', 'The controller project identity is not recorded.')
        _need(controller['project_id'] == project_id, 'integrity_error', 'The controller project identity differs.')
        core_sha = controller.get('request_sha256')
        _need(type(core_sha) is str and re.fullmatch(r'[a-f0-9]{64}', core_sha),
              'partial', 'The original controller request digest is not recorded.')
        _need(fingerprint(request) == core_sha, 'integrity_error', 'The original controller request digest differs.')
        _need(request.get('project_id') is not None, 'partial', 'The original request project identity is not recorded.')
        _need(request['project_id'] == project_id, 'integrity_error', 'The original request project identity differs.')
        producers = (controller.get('code_identity'), controller.get('controller_code_identity'), controller.get('source_snapshot_sha256'))
        _need(all(type(value) is str and re.fullmatch(r'[a-f0-9]{64}', value) for value in producers),
              'partial', 'The original producer or source identity is not recorded.')
        row = manager.execute('SELECT command,digest,length(CAST(record AS BLOB)) FROM requests WHERE id=?', (request_id,)).fetchone()
        _need(row is not None, 'unavailable', 'The original manager request is missing.')
        command, manager_sha, size = row
        _need(type(size) is int and 0 <= size <= _MAX_RECORD, 'partial', 'The original manager record exceeds its bound.')
        record = _parse(manager.execute('SELECT record FROM requests WHERE id=?', (request_id,)).fetchone()[0])
        _need(type(record) is dict and type(record.get('intent')) is dict, 'partial', 'The original manager intent is not recorded.')
        intent = record['intent']
        _need(intent.get('project_id') is not None, 'partial', 'The original manager project identity is not recorded.')
        _need(intent['project_id'] == project_id, 'integrity_error', 'The original manager project identity differs.')
        intent_sha = intent.get('request_sha256')
        _need(all(type(value) is str and re.fullmatch(r'[a-f0-9]{64}', value) for value in (manager_sha, intent_sha)),
              'partial', 'The original manager digests are not recorded.')
        _need(request.get('need') == 'next_check' and type(request.get('expected_state_version')) is int
              and request['expected_state_version'] >= 0,
              'partial', 'The original need or expected version cannot be reconstructed without a default.')
        common = {'request_id': request_id, 'project_id': project_id, 'expected_state_version': request['expected_state_version']}
        if command == 'advance' and request.get('command') == 'controller.advance_selection':
            _need(set(request) == {'project_id', 'command', 'need', 'expected_state_version', 'proposal'}
                  and type(request.get('proposal')) is dict, 'partial', 'The saved selection request cannot be reconstructed losslessly.')
            body = {**common, 'proposal': request['proposal']}
        elif command == 'advance_recipe' and request.get('command') == 'controller.advance_recipe':
            decision = request.get('recipe_decision')
            _need(set(request) == {'project_id', 'command', 'need', 'expected_state_version', 'proposal', 'recipe_decision'}
                  and type(decision) is dict and type(decision.get('recipe')) is dict and type(request.get('proposal')) is dict,
                  'partial', 'The saved recipe request cannot be reconstructed losslessly.')
            _need(decision.get('proposal') == request['proposal'], 'integrity_error', 'The saved recipe proposal differs from the controller request.')
            body = {**common, 'recipe': decision['recipe']}
        elif request.get('command') in ('controller.advance_selection', 'controller.advance_recipe'):
            raise _Failure('integrity_error', 'The original manager and controller command identities differ.')
        else:
            raise _Failure('partial', 'The saved command cannot be reconstructed without assumptions.')
        _need(fingerprint(body) == manager_sha == intent_sha,
              'integrity_error', 'The reconstructed request does not match both original manager digests.')
        view.update(status='available', original_request_id=request_id, manager_command=command,
                    canonical_semantic_body=body, canonical_semantic_json=canonical(body),
                    manager_body_sha256=manager_sha, manager_intent_sha256=intent_sha,
                    controller_request_sha256=core_sha, project_producer_code_identity=producers[0],
                    controller_producer_code_identity=producers[1], source_snapshot_sha256=producers[2],
                    notice='Canonical semantic reconstruction only; original wire bytes and key order are not established. Not authorization to execute.')
        return view
    except _Failure as error:
        return {**view, 'status': error.status, 'reason': str(error)}
    except (sqlite3.Error, OSError, TypeError, ValueError, UnicodeError, RecursionError):
        return {**view, 'status': 'unknown', 'reason': 'The original request could not be checked.'}


def _controller(controller, actions, manager, project_id):
    request_id = controller.get('request_id')
    child = controller.get('child_request_id')
    matches = [a for a in actions if isinstance(child, str) and a['request_id'] == child]
    child_status = ('not_recorded' if 'child_request_id' not in controller else 'explicit_null' if child is None
                    else 'invalid' if type(child) is not str or not child else 'matched' if len(matches) == 1
                    else 'unavailable' if not matches else 'ambiguous')
    decision = controller.get('decision')
    next_action = decision.get('next_action') if type(decision) is dict else None
    original_command = (controller.get('request') or {}).get('command') if type(controller.get('request')) is dict else None
    manager_command = 'advance_recipe' if original_command == 'controller.advance_recipe' else 'advance'
    return {'request_id': request_id, 'status': controller.get('status'), 'child_request_id': child,
            'decision_next_action': next_action, 'child_binding_status': child_status,
            'matched_action': matches[0] if len(matches) == 1 else None,
            'manager_receipt': _receipt(manager, request_id, manager_command, project_id),
            'request_handoff': _request_handoff(controller, manager, project_id)}


def read_history(manager, project, actions):
    result = {'schema_version': 'stored-project-plan-history-v1', 'scope': 'stored_records_not_execution_or_recovery',
              'status': 'available', 'plans': None, 'unmatched_controllers': None}
    try:
        plans, controllers = project.get('plan_revisions'), project.get('controller_requests')
        if plans is None and controllers is None:
            result.update(status='not_recorded', reason='Saved plans and controller records are not present.')
            return result
        plans_missing, controllers_missing = plans is None, controllers is None
        _need((plans_missing or type(plans) is list) and (controllers_missing or type(controllers) is list),
              'integrity_error', 'Saved plans or controller records are malformed.')
        plans, controllers = plans if plans is not None else [], controllers if controllers is not None else []
        _need(len(plans) <= _MAX_ITEMS and len(controllers) <= _MAX_ITEMS,
              'partial', 'Saved plans or controller records are missing or exceed their bounds.')
        _need(all(type(item) is dict for item in plans + controllers), 'integrity_error', 'A saved plan or controller record is malformed.')
        project_id = project['id']
        _need(all(item.get('project_id') == project_id for item in controllers), 'integrity_error', 'A controller belongs to another project.')
        ids = [item.get('request_id') for item in plans]
        _need(all(type(value) is str and value for value in ids) and len(set(ids)) == len(ids),
              'partial', 'A saved plan request identity is missing or duplicated.')
        controller_ids = [item.get('request_id') for item in controllers]
        _need(all(type(value) is str and value for value in controller_ids) and len(set(controller_ids)) == len(controller_ids),
              'partial', 'A controller request identity is missing or duplicated.')
        linked = set()
        output = []
        for plan in plans:
            bindings = []
            for parent in controllers:
                context = parent.get('selection_context')
                if type(context) is dict and context.get('research_plan') == plan:
                    bindings.append(_controller(parent, actions, manager, project_id)); linked.add(parent['request_id'])
            output.append({'revision': plan, 'manager_receipt': _receipt(manager, plan['request_id'], 'save_plan', project_id, expected_plan=plan),
                           'controllers': None if controllers_missing else bindings})
        unmatched = [_controller(parent, actions, manager, project_id) for parent in controllers if parent['request_id'] not in linked]
        result.update(plans=None if plans_missing else output, unmatched_controllers=None if controllers_missing else unmatched)
        if plans_missing or controllers_missing or unmatched or any(item['manager_receipt']['view_status'] != 'available' or any(
                parent['manager_receipt']['view_status'] != 'available' or parent['child_binding_status'] in ('not_recorded', 'invalid', 'unavailable', 'ambiguous')
                for parent in (item['controllers'] or [])) for item in output):
            result.update(status='partial', reason='Some saved bindings or manager receipts could not be matched.')
        _need(len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode()) <= _MAX_HISTORY,
              'partial', 'Saved history exceeds the display bound.')
        return result
    except _Failure as error:
        return {**result, 'status': error.status, 'reason': str(error), 'plans': None, 'unmatched_controllers': None}
    except (sqlite3.Error, OSError, TypeError, ValueError, UnicodeError, RecursionError):
        return {**result, 'status': 'unknown', 'reason': 'Saved history could not be read.', 'plans': None, 'unmatched_controllers': None}


def _file(path, maximum):
    try:
        safe_path(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            _need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= maximum,
                  'integrity_error', 'A saved report metadata file is not a bounded regular file.')
            raw = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
        safe_path(path)
        current = path.stat(follow_symlinks=False)
        identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        _need(identity(before) == identity(after) == identity(current) and len(raw) == before.st_size,
              'unknown', 'Saved report metadata changed during reading.')
        return raw, identity(current)
    except _Failure:
        raise
    except ResearchError:
        raise _Failure('integrity_error', 'A saved report path redirects through a link.') from None
    except FileNotFoundError:
        raise _Failure('unavailable', 'Saved report metadata is missing.') from None
    except OSError:
        raise _Failure('unknown', 'Saved report metadata could not be inspected.') from None


def read_report(manager, root, project_id, slot):
    safe_slot = slot if type(slot) is str and re.fullmatch(r'[a-f0-9]{64}', slot) else None
    view = {'schema_version': 'stored-project-report-reference-v1', 'scope': 'saved_report_metadata_only',
            'currentness': 'unknown', 'status': 'not_recorded', 'slot': slot}
    if slot is None:
        return view
    try:
        _need(type(slot) is str and re.fullmatch(r'[a-f0-9]{64}', slot) is not None,
              'integrity_error', 'The saved report slot is unsafe.')
        export_rows = manager.execute("SELECT id,length(CAST(record AS BLOB)) FROM requests WHERE command='export' ORDER BY rowid LIMIT ?", (_MAX_ITEMS + 1,)).fetchall()
        _need(len(export_rows) <= _MAX_ITEMS, 'partial', 'Saved export requests exceed the display bound.')
        receipts = []
        for request_id, size in export_rows:
            _need(type(size) is int and size <= _MAX_RECORD, 'partial', 'A saved export request exceeds the bound.')
            record = _parse(manager.execute('SELECT record FROM requests WHERE id=?', (request_id,)).fetchone()[0])
            intent = record.get('intent') if type(record) is dict else None
            if type(intent) is dict and intent.get('project_id') == project_id and intent.get('report_slot') == slot:
                receipts.append(_receipt(manager, request_id, 'export', project_id))
        _need(len(receipts) <= 1, 'partial', 'Saved report export binding is ambiguous.')
        directory = root / 'reports' / slot
        manifest_path, report_path = directory / 'manifest.json', directory / 'report.json'
        manifest_raw, manifest_identity = _file(manifest_path, 1024 * 1024)
        report_raw, report_identity = _file(report_path, _MAX_RECORD)
        manifest, report = _parse(manifest_raw.decode('utf-8')), _parse(report_raw.decode('utf-8'))
        _need(type(manifest) is dict and manifest.get('schema_version') == 'project-report-export-v1'
              and manifest.get('project_id') == project_id and type(manifest.get('files')) is dict
              and set(manifest['files']) == _REPORT_FILES, 'integrity_error', 'Saved report manifest identity differs.')
        files = manifest['files']
        _need(all(type(ref) is dict and type(ref.get('bytes')) is int and 0 < ref['bytes'] <= 64 * 1024 * 1024
                  and type(ref.get('sha256')) is str and re.fullmatch(r'[a-f0-9]{64}', ref['sha256']) is not None
                  for ref in files.values()), 'integrity_error', 'Saved report file declarations are invalid.')
        _need(type(report) is dict and report.get('schema_version') == 'research-project-report-v1'
              and report.get('project_id') == project_id and type(manifest.get('project_snapshot_ref')) is str
              and bool(manifest['project_snapshot_ref']) and report.get('project_snapshot_ref') == manifest.get('project_snapshot_ref')
              and len(report_raw) == files['report.json']['bytes'] and hashlib.sha256(report_raw).hexdigest() == files['report.json']['sha256'],
              'integrity_error', 'Saved report metadata does not match its manifest.')
        if receipts:
            intent = receipts[0].get('intent', {})
            if intent.get('snapshot_ref') is not None:
                _need(intent['snapshot_ref'] == manifest.get('project_snapshot_ref'), 'integrity_error', 'Saved export snapshot binding differs.')
        _need(_file(manifest_path, 1024 * 1024)[1] == manifest_identity and _file(report_path, _MAX_RECORD)[1] == report_identity,
              'unknown', 'Saved report metadata changed during reading.')
        embedded = report.get('project') if type(report.get('project')) is dict else {}
        complete_receipt = bool(receipts and receipts[0].get('view_status') == 'available'
                                and receipts[0].get('record_status') == 'completed' and receipts[0].get('result_status') == 'exported'
                                and receipts[0].get('intent', {}).get('snapshot_ref') == manifest.get('project_snapshot_ref')
                                and type(receipts[0].get('intent', {}).get('state_version')) is int
                                and receipts[0]['intent']['state_version'] == embedded.get('state_version'))
        view.update(status='available' if complete_receipt else 'partial', export_receipt=receipts[0] if receipts else None,
                    metadata={'schema_version': report.get('schema_version'), 'project_id': report.get('project_id'),
                              'title': report.get('title'), 'kind': report.get('kind'), 'project_snapshot_ref': report.get('project_snapshot_ref'),
                              'snapshot_sha256': report.get('snapshot_sha256'),
                              'saved_project_state_version': embedded.get('state_version'), 'exporter_code_identity': report.get('exporter_code_identity'),
                              'scientific_validation': report.get('scientific_validation')},
                    declared_files=files, declaration_scope='manifest_declarations_only_report_json_checked',
                    notice='Only report.json and manifest.json were read. Other file bytes and report currentness were not checked.')
        _need(len(json.dumps(view, ensure_ascii=False, allow_nan=False).encode()) <= _MAX_HISTORY,
              'partial', 'Saved report metadata exceeds the display bound.')
        return view
    except _Failure as error:
        return {'schema_version': view['schema_version'], 'scope': view['scope'], 'currentness': 'unknown',
                'status': error.status, 'reason': str(error), 'slot': safe_slot}
    except (sqlite3.Error, OSError, UnicodeError, TypeError, ValueError, RecursionError):
        return {'schema_version': view['schema_version'], 'scope': view['scope'], 'currentness': 'unknown',
                'status': 'unknown', 'reason': 'Saved report metadata could not be read.', 'slot': safe_slot}
