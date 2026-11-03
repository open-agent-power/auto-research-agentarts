"""Export an iteration report bound to the explicitly selected old publication."""
import argparse
import json
from autoresearch.chemotopo_publication import load_publication
from autoresearch.chemotopo_iteration_report import export_iteration


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True,help='New iteration study workspace')
    parser.add_argument('--publication-workspace',required=True,help='Old source study for the baseline publication')
    parser.add_argument('--archive-receipt',required=True);parser.add_argument('--memory-workspace',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    publication=load_publication(args.publication_workspace,archive_receipt=args.archive_receipt,memory_workspace=args.memory_workspace)
    manifest=export_iteration(args.workspace,publication,args.output)
    print(json.dumps({'ok':True,'snapshot_sha256':manifest['snapshot_sha256'],'files':sorted(manifest['files']),
                      'new_fits':0,'model_calls':0},ensure_ascii=False))


if __name__=='__main__':main()
