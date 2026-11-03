"""Build a new, local evidence index; no network, embeddings or source execution."""
import argparse
import json
from pathlib import Path

from autoresearch.knowledge import build_index
from autoresearch.knowledge_sources import collect_documents


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--references', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--no-papers', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output must be a new directory; preserve previous evidence')
    documents, audit = collect_documents(args.references, include_papers=not args.no_papers)
    args.output.mkdir(parents=True)
    manifest = build_index(documents, args.output / 'knowledge.sqlite', audit=audit)
    print(json.dumps({'output': str(args.output.resolve()), 'documents': manifest['documents'],
                      'chunks': manifest['chunks'], 'by_kind': manifest['by_kind'],
                      'corpus_sha256': manifest['corpus_sha256'], 'issues': len(audit['issues'])},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
