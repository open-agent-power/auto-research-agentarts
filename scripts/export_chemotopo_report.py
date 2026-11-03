"""Export a checked Chinese P02 report and bounded reproduction package."""
import argparse
import json
from autoresearch.chemotopo_report import export_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--archive-receipt');parser.add_argument('--memory-workspace')
    args=parser.parse_args()
    manifest=export_report(args.workspace,args.output,archive_receipt=args.archive_receipt,memory_workspace=args.memory_workspace)
    print(json.dumps({'ok':True,'schema_version':manifest['schema_version'],'snapshot_sha256':manifest['snapshot_sha256'],
                      'files':sorted(manifest['files']),'new_fits':0,'model_calls':0},ensure_ascii=False))


if __name__=='__main__':main()
