"""Archive a terminal P02 native study to separate exact-scope memory."""
import argparse
import json
from autoresearch.chemotopo_archive import archive_evidence


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True)
    parser.add_argument('--memory-workspace',required=True)
    parser.add_argument('--receipt',required=True)
    args=parser.parse_args()
    result=archive_evidence(args.workspace,args.memory_workspace,args.receipt)
    print(json.dumps({'status':result['status'],'persistence_trigger':result['persistence_trigger'],
                      'model_selected_remember':result['model_selected_remember'],'inserted':result['import_result']['inserted']},ensure_ascii=False))


if __name__=='__main__':main()
