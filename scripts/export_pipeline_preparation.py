"""Seal a source-bound pipeline preparation view without model calls."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from autoresearch.pipeline_preparation_view import export_pipeline_preparation


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('pipeline-directory','intake-directory','handoff-directory','diagnostic-directory','output'):
        parser.add_argument('--'+flag,required=True)
    a=parser.parse_args()
    print(json.dumps(export_pipeline_preparation(a.pipeline_directory,a.intake_directory,a.handoff_directory,a.diagnostic_directory,a.output),ensure_ascii=False))

if __name__=='__main__':main()
