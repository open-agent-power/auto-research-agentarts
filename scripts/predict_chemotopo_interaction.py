"""Freeze or execute one offline grouped interaction diagnostic."""
import argparse
from pathlib import Path
from autoresearch.chemotopo_interaction import build_protocol,run_interaction,_protected_output
from autoresearch.contracts import canonical,fingerprint


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True);parser.add_argument('--baseline',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--protocol-only',action='store_true');parser.add_argument('--expected-protocol-sha256')
    args=parser.parse_args()
    if args.protocol_only:
        if args.expected_protocol_sha256:parser.error('--expected-protocol-sha256 applies to execution')
        out=_protected_output(args.output,args.source,args.baseline)
        if out.exists():raise FileExistsError('protocol output already exists')
        protocol=build_protocol(args.source,args.baseline)
        with out.open('x',encoding='utf-8') as stream:stream.write(canonical(protocol)+'\n')
        print('protocol_sha256='+fingerprint(protocol)+' fits=0')
    else:
        print(run_interaction(args.source,args.baseline,args.output,args.expected_protocol_sha256))


if __name__=='__main__':main()
