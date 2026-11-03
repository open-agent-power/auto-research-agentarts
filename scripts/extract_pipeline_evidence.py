"""Export inert text and structured module excerpts from the pinned project."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from autoresearch.pipeline_source import export_pipeline_evidence


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--source-url',required=True)
    parser.add_argument('--license-note',required=True)
    args=parser.parse_args()
    print(json.dumps(export_pipeline_evidence(args.project,args.output,source_url=args.source_url,license_note=args.license_note),ensure_ascii=False))


if __name__=='__main__': main()
