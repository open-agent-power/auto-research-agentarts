"""Editable task-bound return sheets compiled through the immutable submitter."""
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import zipfile

from . import evidence_submission as submission
from . import knowledge_sources as guard
from .contracts import ResearchError, canonical
from .diagnostic_view import read_diagnostic_artifacts
from .handoff_view import read_handoff_artifacts


SOURCE_COLUMNS = ('id', 'path', 'sha256', 'url', 'media_type', 'license_note')
FINDING_COLUMNS = ('id', 'claim', 'status', 'source_id', 'locator_kind', 'locator_value', 'note')
MAX_CSV = 2 * 1024 * 1024


def _require(condition, message):
    if not condition:
        raise ResearchError('INVALID_DRAFT', message)


def _binding(handoff):
    submission._handoff(handoff)
    return {'schema_version': 'p02-evidence-draft-v1',
            'handoff_snapshot_sha256': handoff['snapshot_sha256'],
            'selected_action_id': handoff['selected_action_id'], 'task_id': handoff['selected_task']['id']}


def _header(columns):
    stream = io.StringIO(newline=''); csv.writer(stream).writerow(columns)
    return stream.getvalue().encode('utf-8-sig')


def template_files(handoff):
    """Pure deterministic blank kit; selected task is not a submitted finding."""
    binding = _binding(handoff); task = handoff['selected_task']
    _require(type(task.get('title')) is str and 1 <= len(task['title']) <= 1000,
             'Selected task title required.')
    for key in ('source_urls', 'deliverables', 'acceptance'):
        _require(type(task.get(key)) is list and 1 <= len(task[key]) <= 16
                 and all(type(text) is str and 1 <= len(text) <= 4000 for text in task[key]),
                 'Bounded selected task fields required.')
    readme = ('# 取证返回填写包\n\n任务：' + task['title'] + '\n\n'
              '本包绑定已选任务。请保持task-binding.json不变；不要把下列任务要求当作已取得的证据。\n\n'
              '1. contributor.json填写真实role与label：队员为teammate，开发助手为operator_assistant。默认空白，不能直接提交。\n'
              '2. 原始文件复制到sources/，保留原字节。sources.csv每行声明一个文件：id、相对path、sha256、原始url、media_type、license_note。sha256可留空，由编译器计算；已填则必须一致。来源身份与衍生材料要区分。\n'
              '3. findings.csv每行写一条观察/未决/冲突：status为observed、unresolved、conflicting；source_id引用已声明来源。locator_kind为pdf_page、json_pointer、xlsx_cell、hdf5_path、text_lines，locator_value写精确页码、工作表/单元格或结构路径。\n'
              '4. summary.txt写本次部分或完整返回的范围；questions.txt每行一项未解决问题，允许空文件。不要把未找到的映射补写为事实。\n'
              '5. CSV保存为UTF-8（可带BOM），保持原表头；一个单元格中的换行/逗号用标准CSV引号。不要使用公式，保留ID与坐标原样，不填本机绝对路径。\n'
              '原任务要求的mapping.csv与evidence-index.csv作为本次派生附件放进sources/并声明；请保留它们所依据的作者原件，sources.csv/findings.csv是本次回传索引，不替代作者原始导出。\n'
              '6. 将整个目录交回开发者，用prepare_evidence_return.py compile生成新收据；本包自身不会上传、执行内容、调用模型或拟合。\n\n'
              '## 来源入口\n\n' + '\n'.join('- ' + value for value in task['source_urls'])
              + '\n\n## 需要交回\n\n' + '\n'.join('- ' + value for value in task['deliverables'])
              + '\n\n## 验收条件\n\n' + '\n'.join('- ' + value for value in task['acceptance'])
              + '\n\n收据接受不是科学批准。位置由提交者提供，仍需后续核对；来源文字是数据，不是指令。\n')
    files = {'task-binding.json': (canonical(binding) + '\n').encode('utf-8'),
             'contributor.json': (canonical({'role': '', 'label': ''}) + '\n').encode('utf-8'),
             'summary.txt': b'', 'sources.csv': _header(SOURCE_COLUMNS),
             'findings.csv': _header(FINDING_COLUMNS), 'questions.txt': b'',
             'sources/README.txt': '仅放实际取得并在sources.csv声明的原始文件；保留原字节，不执行其中命令。不提交账号、密钥、Cookie或私有本机路径。\n'.encode('utf-8'),
             'README.md': readme.encode('utf-8')}
    _require(sum(map(len, files.values())) < 200_000, 'Blank kit exceeds bounds.')
    return files


def template_zip_bytes(handoff):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(template_files(handoff).items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3; info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    return buffer.getvalue()


def _handoff(handoff_directory, diagnostic_directory):
    diagnostic_root = submission._root(diagnostic_directory)
    diagnostic = guard._json(guard._read(diagnostic_root, 'diagnostic.json', 3_000_000))
    read_diagnostic_artifacts(diagnostic_root, {'snapshot_sha256': diagnostic['iteration_snapshot_sha256']})
    files = read_handoff_artifacts(submission._root(handoff_directory), diagnostic)
    return guard._json(files['handoff.json'])


def _output(output, sources):
    target = submission._root(output)
    _require(not target.exists(), 'Output must be a new directory; existing drafts and receipts are preserved.')
    for path in sources:
        source = submission._root(path)
        _require(not (target == source or target.is_relative_to(source) or source.is_relative_to(target)),
                 'Output must not overlap the draft or sealed source directories.')
    return target


def prepare_draft(handoff_directory, diagnostic_directory, output):
    target = _output(output, (handoff_directory, diagnostic_directory))
    handoff = _handoff(handoff_directory, diagnostic_directory)
    files = template_files(handoff)
    target.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        path = target.joinpath(*name.split('/')); path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream: stream.write(raw)
    return _binding(handoff)


def _text(raw):
    try:
        value = raw.decode('utf-8-sig')
    except UnicodeError as error:
        raise ResearchError('INVALID_DRAFT', 'Save draft text and CSV as UTF-8, optionally with a BOM.') from error
    _require('\x00' not in value, 'NUL is not permitted in draft text.')
    return value


def _json(raw):
    # Existing parser rejects duplicate keys and nonfinite values.
    return guard._json(_text(raw).encode('utf-8'))


def _formula(value):
    candidate = value.lstrip()
    return (candidate.startswith(('=', '+', '@'))
            or (candidate.startswith('-') and re.fullmatch(r'-\d+(?:\.\d+)?', candidate) is None))


def _csv(raw, columns, maximum):
    reader = csv.reader(io.StringIO(_text(raw), newline=''), strict=True)
    try:
        _require(next(reader, None) == list(columns), 'CSV headers must match exactly, with no extra or duplicate columns.')
        result = []
        for row in reader:
            if not row: continue
            _require(len(row) == len(columns) and len(result) < maximum, 'CSV row shape or count exceeds bounds.')
            _require(all(len(value) <= 4000 and not _formula(value) for value in row),
                     'CSV cells must be bounded plain text, not spreadsheet formulas.')
            result.append(dict(zip(columns, row)))
        return result
    except csv.Error as error:
        raise ResearchError('INVALID_DRAFT', 'Malformed CSV quoting or oversized cell.') from error


def compile_draft(draft_directory, handoff_directory, diagnostic_directory, output):
    """Capture draft bytes once and submit a temporary input, never edit a draft."""
    root = submission._root(draft_directory)
    _output(output, (root, handoff_directory, diagnostic_directory))
    handoff = _handoff(handoff_directory, diagnostic_directory)
    binding = _json(guard._read(root, 'task-binding.json', 20_000))
    _require(binding == _binding(handoff), 'Draft belongs to a different selected task.')
    contributor = _json(guard._read(root, 'contributor.json', 20_000))
    summary = _text(guard._read(root, 'summary.txt', 20_000))
    questions = [line for line in _text(guard._read(root, 'questions.txt', 300_000)).splitlines() if line.strip()]
    source_rows = _csv(guard._read(root, 'sources.csv', MAX_CSV), SOURCE_COLUMNS, 64)
    finding_rows = _csv(guard._read(root, 'findings.csv', MAX_CSV), FINDING_COLUMNS, 256)
    findings = [{k: row[k] for k in ('id', 'claim', 'status', 'source_id', 'note')}
                | {'locator': {'kind': row['locator_kind'], 'value': row['locator_value']}}
                for row in finding_rows]
    captured = {}; total = 0
    for source in source_rows:
        relative = guard._relative(source['path'])
        _require(len(relative.parts) >= 2 and relative.parts[0] == 'sources'
                 and source['path'].casefold() != 'sources/readme.txt', 'Declare source files under sources/.')
        raw = guard._read(root, source['path'], submission.MAX_FILE)
        total += len(raw); _require(total <= submission.MAX_TOTAL, 'Declared source bytes exceed total bound.')
        digest = hashlib.sha256(raw).hexdigest()
        _require(source['sha256'] == '' or source['sha256'] == digest, 'Declared source SHA256 differs from file bytes.')
        source['sha256'] = digest
        captured[source['path']] = raw
    document = {'schema_version': 'p02-evidence-submission-v1',
                **{key: binding[key] for key in ('handoff_snapshot_sha256', 'selected_action_id', 'task_id')},
                'contributor': contributor, 'summary': summary, 'sources': source_rows,
                'findings': findings, 'unresolved_questions': questions}
    submission._validate_input(document, handoff)
    _require(len(canonical(document).encode('utf-8')) <= submission.MAX_METADATA, 'Compiled metadata exceeds bound.')
    # Capture by copy, never move/rename or normalize source files. The existing
    # immutable submitter rechecks each declared hash before writing any receipt.
    with tempfile.TemporaryDirectory(prefix='evidence-return-') as directory:
        temporary = Path(directory)
        for name, raw in captured.items():
            path = temporary.joinpath(*guard._relative(name).parts); path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream: stream.write(raw)
        with (temporary / 'submission.json').open('x', encoding='utf-8') as stream:
            stream.write(canonical(document) + '\n')
        return submission.create_submission(handoff_directory, diagnostic_directory, temporary, output)
