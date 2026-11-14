"""Bounded stored project facts, read without project runtime or write access.

The immutable SQLite reads require that no other process is writing either DB.
File/sidecar checks detect changes but do not provide operating-system isolation.
"""
from contextlib import contextmanager
import json
import math
from pathlib import Path
import re
import sqlite3
import stat

from .contracts import ResearchError
from .research_project import safe_path

_MAX_RECORD = 4 * 1024 * 1024
_MAX_ACTIONS = 2048
_MAX_TOTAL_ACTION_BYTES = 32 * 1024 * 1024
_SCHEMA = 'stored-current-project-summary-v1'


class _Unavailable(Exception):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status = status


def _need(condition, status, reason):
    if not condition:
        raise _Unavailable(status, reason)


def _identity(path):
    try:
        safe_path(path)
        info = path.stat()
    except ResearchError:
        raise _Unavailable('integrity_error', 'A stored database path redirects through a link.') from None
    except FileNotFoundError:
        raise _Unavailable('unavailable', 'A required stored database is missing.') from None
    except OSError:
        raise _Unavailable('unknown', 'A stored database cannot be inspected.') from None
    _need(stat.S_ISREG(info.st_mode), 'integrity_error', 'A stored database is not a regular file.')
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _sidecars_clear(path):
    for suffix in ('-wal', '-shm', '-journal'):
        sidecar = Path(str(path) + suffix)
        try:
            # A dangling symlink must count as a sidecar as well.
            sidecar.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            raise _Unavailable('unknown', 'A database sidecar could not be inspected.') from None
        raise _Unavailable('unknown', 'A database sidecar exists; the stored state is not safely readable.')


@contextmanager
def _database(path):
    before = _identity(path)
    _sidecars_clear(path)
    try:
        connection = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True, timeout=5)
        try:
            connection.execute('BEGIN')
            yield connection
            _need(_identity(path) == before, 'unknown', 'A stored database changed during reading.')
            _sidecars_clear(path)
        finally:
            connection.close()
    except sqlite3.OperationalError:
        raise _Unavailable('unknown', 'A stored database could not be read consistently.') from None
    except sqlite3.DatabaseError:
        raise _Unavailable('integrity_error', 'A stored database is invalid.') from None


def _parse(value):
    _need(type(value) is str and len(value.encode('utf-8')) <= _MAX_RECORD,
          'integrity_error', 'A stored JSON record is missing or exceeds its bound.')
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError('duplicate field')
            result[key] = item
        return result
    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError('nonfinite number')
        return number
    try:
        return json.loads(value, object_pairs_hook=unique, parse_float=finite_float,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
    except (ValueError, TypeError, RecursionError):
        raise _Unavailable('integrity_error', 'A stored JSON record is malformed.') from None


def _manager_selection(con):
    version = con.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchall()
    _need(version == [('local-research-workbench-v1',)], 'integrity_error', 'The manager schema is not supported.')
    active = con.execute("SELECT value FROM metadata WHERE key='active_project_id'").fetchall()
    if not active:
        return None
    _need(len(active) == 1 and type(active[0][0]) is str and 0 < len(active[0][0]) <= 256,
          'integrity_error', 'The active project identity is invalid.')
    project_id = active[0][0]
    projects = con.execute('SELECT id, slot FROM projects WHERE id=?', (project_id,)).fetchall()
    _need(len(projects) == 1 and projects[0][0] == project_id, 'integrity_error', 'The active project binding is missing or ambiguous.')
    slot = projects[0][1]
    _need(type(slot) is str and re.fullmatch(r'[a-f0-9]{64}', slot) is not None,
          'integrity_error', 'The stored project slot is unsafe.')
    return project_id, slot


def read_stored_project_summary(root):
    """Read active manager/project records; no recovery, execution or calculation."""
    try:
        root = Path(root).absolute()
        with _database(root / 'workbench.sqlite') as manager:
            selection = _manager_selection(manager)
            if selection is None:
                return {'schema_version': _SCHEMA, 'status': 'no_active', 'reason': 'No active project is recorded.'}
            project_id, slot = selection
            with _database(root / 'projects' / slot / 'project.sqlite') as project_db:
                rows = project_db.execute('SELECT id, length(CAST(record AS BLOB)) FROM project LIMIT 2').fetchall()
                _need(len(rows) == 1 and rows[0][0] == 1 and type(rows[0][1]) is int and rows[0][1] <= _MAX_RECORD,
                      'integrity_error', 'The stored project record is missing, ambiguous or too large.')
                project = _parse(project_db.execute('SELECT record FROM project WHERE id=1').fetchone()[0])
                _need(type(project) is dict and project.get('schema_version') == 'local-research-project-v3',
                      'integrity_error', 'The stored project schema is not supported.')
                _need(project.get('id') == project_id and type(project.get('run_id')) is str and project['run_id'],
                      'integrity_error', 'The stored project identity does not match the manager.')
                _need(type(project.get('state_version')) is int and project['state_version'] >= 0
                      and type(project.get('budget')) is dict,
                      'partial', 'The stored project version or budget is missing.')
                rows = project_db.execute('SELECT request_id, length(CAST(record AS BLOB)) FROM actions ORDER BY rowid LIMIT ?', (_MAX_ACTIONS + 1,)).fetchall()
                _need(len(rows) <= _MAX_ACTIONS and all(type(row[1]) is int and 0 <= row[1] <= _MAX_RECORD for row in rows)
                      and sum(row[1] for row in rows) <= _MAX_TOTAL_ACTION_BYTES,
                      'partial', 'The stored actions exceed the reading bounds.')
                actions = []
                seen = set()
                for request_id, _ in rows:
                    raw = project_db.execute('SELECT record FROM actions WHERE request_id=?', (request_id,)).fetchone()[0]
                    action = _parse(raw)
                    _need(type(action) is dict and type(request_id) is str and action.get('request_id') == request_id
                          and type(action.get('id')) is str and bool(action['id']) and action['id'] not in seen
                          and (action.get('command') is None or type(action['command']) is str)
                          and type(action.get('status')) is str and bool(action['status'])
                          and action.get('project_id') == project_id
                          and action.get('run_id') == project['run_id'],
                          'integrity_error', 'A stored action identity or project binding is invalid.')
                    seen.add(action['id'])
                    method = action.get('method_instance')
                    definition = method.get('definition_ref') if type(method) is dict else None
                    actions.append({'id': action['id'], 'request_id': request_id, 'status': action['status'],
                                    'command': action.get('command'), 'producer_code_identity': action.get('code_identity'),
                                    'method': {key: definition.get(key) for key in ('id', 'version')}
                                    if type(definition) is dict else None})
                _need(_manager_selection(manager) == selection, 'unknown', 'The active project changed during reading.')
                producer = {'code_identity': project.get('code_identity'), 'runtime_dependencies': project.get('runtime_dependencies')}
                partial = not isinstance(producer['code_identity'], str) or producer['runtime_dependencies'] is None
                return {'schema_version': _SCHEMA, 'status': 'partial' if partial else 'available',
                        'reason': 'Stored producer identity is incomplete.' if partial else None,
                        'project_id': project_id, 'run_id': project['run_id'], 'state_version': project['state_version'],
                        'producer': producer, 'stored_budget': project['budget'], 'stored_actions': actions,
                        'budget_scope': 'stored_project_record_not_computed_usage',
                        'notice': 'Stored facts only; no usage, reservations, costs or tokens were independently computed. Requires no concurrent writer.'}
    except _Unavailable as error:
        return {'schema_version': _SCHEMA, 'status': error.status, 'reason': str(error)}
    except (OSError, UnicodeError):
        return {'schema_version': _SCHEMA, 'status': 'unknown', 'reason': 'The stored project could not be read.'}
