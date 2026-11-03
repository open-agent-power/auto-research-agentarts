"""Build a new C01 primary-source index, preserving the global technology library."""
import argparse
import json
import sys
from autoresearch.c01_knowledge import build_case_index


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',required=True)
    parser.add_argument('--snapshot',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    manifest=build_case_index(args.archive,args.snapshot,args.output)
    print(json.dumps({key:manifest[key] for key in ('documents','chunks','by_kind','corpus_sha256','database_sha256')},ensure_ascii=False,indent=2))


if __name__=='__main__': main()
