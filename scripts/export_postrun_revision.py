"""Export a revision against its original sealed iteration without new execution."""
import argparse
import json
from pathlib import Path

from autoresearch.chemotopo_experiment_evidence import _safe_file
from autoresearch.chemotopo_iteration_report import read_iteration_artifacts
from autoresearch.postrun_revision_view import export_revision


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True);parser.add_argument('--iteration-directory',required=True)
    parser.add_argument('--assessment');parser.add_argument('--output',required=True)
    args=parser.parse_args();directory=Path(args.iteration_directory)
    iteration=json.loads(_safe_file(directory/'iteration.json',3_000_000))
    read_iteration_artifacts(directory,iteration)
    annotation=json.loads(_safe_file(Path(args.assessment),20_000)) if args.assessment else None
    manifest=export_revision(args.workspace,iteration,args.output,annotation)
    print(json.dumps({'ok':True,'snapshot_sha256':manifest['snapshot_sha256'],
                      'iteration_snapshot_sha256':manifest['iteration_snapshot_sha256'],'model_calls':0,'new_fits':0},ensure_ascii=False))


if __name__=='__main__':main()
