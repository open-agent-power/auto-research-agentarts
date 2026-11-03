"""Inspect or build an explicitly pinned local workbench recipe."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from autoresearch.contracts import ResearchError
from autoresearch.workbench_recipe import inspect_recipe, publish_recipe


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('inspect','build'))
    p.add_argument('--recipe',default='config/workbench-p02.json');p.add_argument('--output');p.add_argument('--select',action='store_true');a=p.parse_args()
    try:
        if a.action=='inspect':
            if a.output or a.select:raise ResearchError('INVALID_REQUEST','Inspect does not build or select.')
            result=inspect_recipe(a.recipe)[0]
        else:
            if not a.output:raise ResearchError('INVALID_REQUEST','Build requires a fresh output.')
            result=publish_recipe(a.recipe,a.output,select=a.select)
        print(json.dumps(result,ensure_ascii=False));return 0
    except (ResearchError,OSError,ValueError,KeyError,TypeError) as error:
        print(json.dumps({'ok':False,'code':getattr(error,'code','RECIPE_FAILED'),'model_calls':0,'new_fits':0}));return 1
if __name__=='__main__':raise SystemExit(main())
