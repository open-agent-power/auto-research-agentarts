"""Prepare submitted tabular coordinates as explicit derived JSON evidence."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile

from . import evidence_submission as submission, knowledge_sources as guard, tabular_source
from .contracts import ResearchError, canonical, fingerprint
from .diagnostic_view import read_diagnostic_artifacts
from .handoff_view import read_handoff_artifacts
from .returned_evidence import build_returned_evidence, validate_packet


def _require(condition, message):
    if not condition:
        raise ResearchError('INVALID_TABULAR_SUBMISSION', message)


def _bytes(value):
    return (canonical(value) + '\n').encode('utf-8')


def _write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def prepare_tabular_submission(handoff_directory, diagnostic_directory, submission_directory, output):
    """One fresh receipt/packet from an existing receipt; no study or inference."""
    handoff_root = submission._root(handoff_directory)
    diagnostic_root = submission._root(diagnostic_directory)
    original_root = submission._root(submission_directory)
    target = submission._root(output)
    _require(not target.exists(), 'Use a fresh preparation output directory.')
    for source in (handoff_root, diagnostic_root, original_root):
        _require(not (target == source or target.is_relative_to(source) or source.is_relative_to(target)),
                 'Preparation output must be separate from the original receipt and publications.')
    diagnostic = guard._json(guard._read(diagnostic_root, 'diagnostic.json', 3_000_000))
    read_diagnostic_artifacts(diagnostic_root, {'snapshot_sha256': diagnostic['iteration_snapshot_sha256']})
    handoff = guard._json(read_handoff_artifacts(handoff_root, diagnostic)['handoff.json'])
    receipt = submission.read_submission(original_root, handoff)
    original_raw = guard._read(original_root, 'receipt.json', submission.MAX_METADATA)
    _require(guard._json(original_raw) == receipt, 'Original receipt changed during preparation.')
    original_sha = hashlib.sha256(original_raw).hexdigest()
    selected = [f for f in receipt['findings'] if f['locator']['kind'] in {'xlsx_cell', 'text_lines'}]
    _require(bool(selected), 'No submitted XLSX cells or physical text lines; no duplicate receipt was created.')
    captured = {}; sources = []
    for item in receipt['sources']:
        raw = guard._read(original_root, item['path'], submission.MAX_FILE,
                          expected_sha=item['sha256'], expected_bytes=item['bytes'])
        captured[item['path']] = raw
        sources.append({k: copy.deepcopy(v) for k, v in item.items() if k != 'bytes'})
    source_index = {s['id']: s for s in receipt['sources']}
    identities = {s['id'].casefold() for s in receipt['sources']}
    adapter_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    extractor_sha = tabular_source.extraction_identity()
    derived = {}; selection_indices = {}; selections_count = 0
    for source_id in dict.fromkeys(f['source_id'] for f in selected):
        source = source_index[source_id]
        derived_id = 'derived-' + fingerprint({'id': source_id, 'sha256': source['sha256']})[:24]
        _require(derived_id.casefold() not in identities, 'Derived source ID collides with an original source.')
        identities.add(derived_id.casefold())
        selections = []
        for finding in selected:
            if finding['source_id'] != source_id: continue
            extraction = tabular_source.extract_selection(captured[source['path']], copy.deepcopy(finding['locator']))
            selection_indices[finding['id']] = (derived_id, len(selections))
            selections.append({'finding': copy.deepcopy(finding), 'locator': copy.deepcopy(finding['locator']),
                               'origin': {'original_source': {k: copy.deepcopy(source[k]) for k in ('id', 'sha256', 'url')},
                                          'original_receipt_snapshot_sha256': receipt['snapshot_sha256'],
                                          'original_contributor': copy.deepcopy(receipt['contributor']),
                                          'adapter_sha256': adapter_sha, 'extractor_sha256': extractor_sha},
                               'extraction': extraction})
        document = {'schema_version': 'p02-tabular-source-v1', 'origin': 'derived',
                    'original_source': {k: copy.deepcopy(source[k]) for k in ('id', 'sha256', 'url', 'bytes', 'media_type', 'license_note')},
                    'original_receipt_sha256': original_sha, 'original_receipt_snapshot_sha256': receipt['snapshot_sha256'],
                    'original_contributor': copy.deepcopy(receipt['contributor']),
                    'selections': selections,
                    'adapter': {'module': 'autoresearch.tabular_submission', 'sha256': adapter_sha},
                    'extractor': {'module': 'autoresearch.tabular_source', 'sha256': extractor_sha},
                    'interpretation_status': 'pending_scientific_interpretation',
                    'notice': 'Derived extraction of explicitly submitted coordinates; original claims and locators are preserved, not scientifically verified. No formula evaluation.',
                    'scientific_validation': False}
        raw = _bytes(document)
        _require(len(raw) <= submission.MAX_FILE, 'Derived evidence source exceeds file bound.')
        path = 'sources/' + derived_id + '/selection.json'
        captured[path] = raw
        license_note = ('Developer-derived selection; original source license statement: ' + source['license_note']
                        + ' Original URL identifies underlying source, not this derived JSON. No new author confirmation.')
        _require(len(license_note) <= 2000, 'Original license statement plus derived notice exceeds metadata bound.')
        sources.append({'id': derived_id, 'path': path, 'sha256': hashlib.sha256(raw).hexdigest(),
                        'url': source['url'], 'media_type': 'application/json', 'license_note': license_note})
        derived[derived_id] = {'original_source_id': source_id, 'sha256': hashlib.sha256(raw).hexdigest(),
                               'bytes': len(raw), 'selections': len(selections)}
        selections_count += len(selections)
    findings = []
    for finding in receipt['findings']:
        item = {k: copy.deepcopy(v) for k, v in finding.items() if k != 'locator_validation'}
        if finding['id'] in selection_indices:
            source_id, index = selection_indices[finding['id']]
            item['source_id'] = source_id
            item['locator'] = {'kind': 'json_pointer', 'value': '/selections/' + str(index)}
            # Original claim/note/coordinate remain inside the derived source;
            # the new claim status is still only the original contributor claim.
            item['note'] = ('Adapter-derived extraction, not new author evidence. Original contributor claim, note and locator '
                            'are retained in the selected derived JSON; interpretation is pending.')
        findings.append(item)
    document = {'schema_version': 'p02-evidence-submission-v1',
                **{k: receipt[k] for k in ('handoff_snapshot_sha256', 'selected_action_id', 'task_id')},
                'contributor': {'role': 'operator_assistant', 'label': 'Tabular evidence adapter'},
                'summary': 'Derived from an existing immutable receipt, not a new teammate or author return. Original source bytes and submitted coordinate claims remain separate from bounded extraction. No model assessment or new research budget.',
                'sources': sources, 'findings': findings,
                'unresolved_questions': copy.deepcopy(receipt['unresolved_questions'])}
    submission._validate_input(document, handoff)
    document_raw = _bytes(document)
    _require(len(document_raw) <= submission.MAX_METADATA and sum(map(len, captured.values())) <= submission.MAX_TOTAL,
             'Prepared metadata or source total exceeds existing submission bounds.')
    target.parent.mkdir(parents=True, exist_ok=True); submission._root(target.parent)
    # Build and validate everything under a temporary sibling. The final output
    # appears only after receipt and returned packet both passed their contracts.
    with tempfile.TemporaryDirectory(prefix='.tabular-evidence-', dir=target.parent) as temporary:
        container = Path(temporary); input_root = container / 'input'; result_root = container / 'result'
        input_root.mkdir(); result_root.mkdir()
        for name, raw in captured.items(): _write(input_root.joinpath(*guard._relative(name).parts), raw)
        _write(input_root / 'submission.json', document_raw)
        result = submission.create_submission(handoff_root, diagnostic_root, input_root, result_root / 'receipt')
        packet = build_returned_evidence(handoff_root, diagnostic_root, result_root / 'receipt')
        validate_packet(packet); packet_raw = _bytes(packet)
        _require(len(packet_raw) <= 4_000_000, 'Prepared returned-evidence packet exceeds source bound.')
        _write(result_root / 'packet.json', packet_raw)
        new_receipt_raw = (result_root / 'receipt' / 'receipt.json').read_bytes()
        preparation = {'schema_version': 'p02-tabular-preparation-v1', 'status': 'prepared',
                       'handoff_snapshot_sha256': receipt['handoff_snapshot_sha256'], 'task_id': receipt['task_id'],
                       'original_receipt_sha256': original_sha, 'original_receipt_snapshot_sha256': receipt['snapshot_sha256'],
                       'receipt_snapshot_sha256': result['snapshot_sha256'],
                       'receipt_sha256': hashlib.sha256(new_receipt_raw).hexdigest(),
                       'packet_snapshot_sha256': packet['snapshot_sha256'], 'packet_sha256': hashlib.sha256(packet_raw).hexdigest(),
                       'original_sources': len(receipt['sources']), 'derived_sources': derived,
                       'selected_coordinates': selections_count, 'chunks': len(packet['chunks']),
                       'exclusions': copy.deepcopy(packet['exclusions']),
                       'contributor': document['contributor'], 'adapter_sha256': adapter_sha, 'extractor_sha256': extractor_sha,
                       'model_calls': 0, 'new_fits': 0, 'model_read_performed': False,
                       'scientific_validation': False, 'biological_endpoint_eligible': False,
                       'interpretation_status': 'pending_scientific_interpretation'}
        _write(result_root / 'preparation.json', _bytes(preparation))
        _require(not target.exists(), 'Output appeared while preparing; existing output was preserved.')
        result_root.rename(target)
    return preparation
