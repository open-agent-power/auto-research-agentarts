"""Export a source-continuation review snapshot without calls or fitting."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from autoresearch.source_continuation_view import export_source_continuation


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workflow-root',required=True);parser.add_argument('--progress-directory',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();result=export_source_continuation(args.workflow_root,args.progress_directory,args.output)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
