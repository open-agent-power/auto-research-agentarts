"""Export one sealed read-only diagnostic view without model or fit calls."""
import argparse
import json
from pathlib import Path

from autoresearch.chemotopo_experiment_evidence import _safe_file
from autoresearch.chemotopo_iteration_report import read_iteration_artifacts
from autoresearch.diagnostic_view import export_diagnostic


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True);parser.add_argument('--iteration-directory',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--assessment')
    args=parser.parse_args();directory=Path(args.iteration_directory).absolute();output=Path(args.output).absolute().resolve();iteration_dir=directory.resolve()
    if output==iteration_dir or output.is_relative_to(iteration_dir) or iteration_dir.is_relative_to(output):parser.error('Output must be separate from the sealed iteration directory.')
    iteration=json.loads(_safe_file(directory/'iteration.json',3_000_000));read_iteration_artifacts(directory,iteration)
    assessment=json.loads(_safe_file(Path(args.assessment).absolute(),100_000)) if args.assessment else None
    result=export_diagnostic(args.workspace,iteration,args.output,assessment)
    print(json.dumps({'ok':True,**result},ensure_ascii=False))


if __name__=='__main__':main()
