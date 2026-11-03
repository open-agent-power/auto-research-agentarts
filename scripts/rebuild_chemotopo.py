"""Reconstruct source-table proxy sensitivity offline, with an explicit ALP gate."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from autoresearch.chemotopo_rebuild import run_reconstruction, report_markdown
from autoresearch.contracts import ResearchError


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--endpoint',choices=['raw_red_proxy','alp'],default='raw_red_proxy')
    args=parser.parse_args()
    try:
        result=run_reconstruction(args.directory,endpoint=args.endpoint)
        output=Path(args.output);output.mkdir(parents=True,exist_ok=False)
        summary={key:result[key] for key in ['schema_version','protocol','protocol_sha256','source','raw_summary','endpoint_gate','model_fits','model_calls','limits']}
        summary['policy_coverage']={name:value['coverage'] for name,value in result['policies'].items()}
        summary['comparison']={key:value for key,value in result['comparison'].items() if key!='common_three_batch_keys'}
        for name,value in [('sensitivity.json',result),('summary.json',summary),('protocol.json',result['protocol'])]:
            (output/name).write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
        (output/'report.md').write_text(report_markdown(result),encoding='utf-8')
        files=[p for p in output.iterdir() if p.is_file()]
        receipt={'complete':True,'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                 'protocol_sha256':result['protocol_sha256'],'model_calls':0,'fits':0}
        (output/'complete.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        print(json.dumps({'ok':True,'output':str(output.absolute()),'common_combinations':result['comparison']['common_combinations'],
                          'endpoint_gate':result['endpoint_gate'],'model_calls':0,'fits':0},ensure_ascii=False,indent=2))
        return 0
    except (ResearchError,OSError,ValueError) as error:
        print(json.dumps({'ok':False,'error':{'code':getattr(error,'code','RECONSTRUCTION_UNAVAILABLE'),
                         'message':str(error) if isinstance(error,ResearchError) else 'Source or fresh output unavailable.'}},ensure_ascii=False))
        return 1


if __name__=='__main__':raise SystemExit(main())
