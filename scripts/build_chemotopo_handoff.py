"""Build a new portable workbench from sealed P02 publication directories."""
import argparse
import json
from autoresearch.chemotopo_bundle import build_handoff


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-directory', required=True)
    parser.add_argument('--iteration-directory')
    parser.add_argument('--postrun-directory')
    parser.add_argument('--diagnostic-directory')
    parser.add_argument('--handoff-directory')
    parser.add_argument('--source-progress-directory')
    parser.add_argument('--prepared-input-directory')
    parser.add_argument('--source-continuation-directory')
    parser.add_argument('--pipeline-input-directory')
    parser.add_argument('--pipeline-research-directory')
    parser.add_argument('--tabular-research-directory')
    parser.add_argument('--dossier-directory')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = build_handoff(args.baseline_directory, args.iteration_directory, args.output,postrun_directory=args.postrun_directory,diagnostic_directory=args.diagnostic_directory,handoff_directory=args.handoff_directory,source_progress_directory=args.source_progress_directory,prepared_input_directory=args.prepared_input_directory,source_continuation_directory=args.source_continuation_directory,pipeline_input_directory=args.pipeline_input_directory,pipeline_research_directory=args.pipeline_research_directory,tabular_research_directory=args.tabular_research_directory,dossier_directory=args.dossier_directory)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
