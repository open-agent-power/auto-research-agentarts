"""Evaluate retrieval of named sources, not answer correctness or scientific validity."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

from autoresearch.knowledge import KnowledgeIndex


def evaluate(database, tasks):
    if type(tasks) is not list or not tasks or len(tasks) > 1000:
        raise ValueError('require 1..1000 fixed evaluation tasks')
    ids = set()
    for task in tasks:
        expected = task.get('expected_paths', [])
        if (not isinstance(task.get('id'), str) or task['id'] in ids or
                type(expected) is not list or any(type(path) is not str or not path for path in expected) or
                len(expected) != len(set(expected)) or
                (bool(expected) == (task.get('expect_empty') is True))):
            raise ValueError('each distinct task requires nonempty expected paths OR expect_empty=true')
        ids.add(task['id'])
    index = KnowledgeIndex(database)
    connection = sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    results = []
    try:
        for task in tasks:
            if task.get('requires_kind') and not index.manifest['by_kind'].get(task['requires_kind']):
                results.append({'id': task['id'], 'query': task['query'], 'passed': False,
                                'skipped': 'required source kind not indexed', 'missing_expected': task['expected_paths']})
                continue
            response = index.search(task['query'], kinds=task.get('kinds'), limit=task.get('limit', 8))
            paths = {hit['source']['path'] for hit in response['evidence']}
            expected = task.get('expected_paths', [])
            matched = [path for path in expected if path in paths]
            citations_valid = True
            for hit in response['evidence']:
                row = connection.execute('SELECT excerpt,line_start,line_end,document_id FROM chunks WHERE id=?',
                                         (hit['citation_id'],)).fetchone()
                citations_valid &= bool(row and row[0] == hit['quote'])
                citations_valid &= len(hit['source']['sha256']) == 64
                source = connection.execute('SELECT record FROM documents WHERE id=?', (row[3],)).fetchone() if row else None
                citations_valid &= bool(source and json.loads(source[0]) == hit['source'])
                location = hit['location']
                if hit['source']['page']:
                    citations_valid &= location == {'page': hit['source']['page']}
                else:
                    citations_valid &= bool(row and location == {'line_start': row[1], 'line_end': row[2]})
            passed = citations_valid and len(matched) == len(expected)
            if task.get('expect_empty'):
                passed &= not response['evidence']
            results.append({'id': task['id'], 'query': task['query'], 'passed': bool(passed),
                            'matched_expected': matched, 'missing_expected': sorted(set(expected)-paths),
                            'citations_valid': bool(citations_valid), 'response': response})
    finally:
        connection.close()
    return {'schema_version': 'research-retrieval-evaluation-v1',
            'database_sha256': hashlib.sha256(Path(database).read_bytes()).hexdigest(),
            'tasks': len(results), 'passed': sum(result['passed'] for result in results),
            'skipped': sum('skipped' in result for result in results),
            'answer_correctness_evaluated': False, 'scientific_validation': False,
            'method': 'Fixed queries; required-source inclusion at bounded k; exact indexed excerpts checked',
            'results': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--tasks', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output must be new')
    tasks = json.loads(args.tasks.read_text(encoding='utf-8'))['tasks']
    report = evaluate(args.database, tasks)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'results'}, ensure_ascii=False))
    for result in report['results']:
        print(json.dumps({key: result[key] for key in ('id', 'passed', 'missing_expected')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
