"""Export the current P02 research evidence without running models or experiments."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from autoresearch.contracts import ResearchError
from autoresearch.research_dossier_render import export_dossier


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    try:
        result=export_dossier(args.bundle,args.output)
        print(json.dumps(result,ensure_ascii=False));return 0
    except (ResearchError,ValueError,OSError,KeyError,TypeError) as error:
        print(json.dumps({'ok':False,'code':getattr(error,'code','DOSSIER_EXPORT_FAILED'),'model_calls':0,'new_fits':0}));return 1
if __name__=='__main__':raise SystemExit(main())
