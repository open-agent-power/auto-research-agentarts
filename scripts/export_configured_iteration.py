"""Export configured results against a sealed baseline without original sources."""
import argparse
import json
from pathlib import Path

from autoresearch.chemotopo_experiment_evidence import _safe_file
from autoresearch.chemotopo_publication import read_artifacts
from autoresearch.configured_iteration_report import export_configured
from autoresearch.contracts import ResearchError, fingerprint


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True)
    parser.add_argument('--baseline-publication-directory',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--native-interface',choices=('legacy','compact-v1'),default='legacy')
    args=parser.parse_args();baseline=Path(args.baseline_publication_directory).absolute();out=Path(args.output).absolute()
    if out==baseline or out.is_relative_to(baseline) or baseline.is_relative_to(out):raise ResearchError('INVALID_OUTPUT','Output overlaps sealed baseline publication.')
    publication=json.loads(_safe_file(baseline/'research.json',3_000_000))
    if publication.get('snapshot_sha256')!=fingerprint({k:v for k,v in publication.items() if k!='snapshot_sha256'}):raise ResearchError('EVIDENCE_CHANGED','Sealed baseline snapshot identity differs.')
    read_artifacts(baseline,publication)
    manifest=export_configured(args.workspace,publication,args.output,native_interface=args.native_interface)
    print(json.dumps({'ok':True,'snapshot_sha256':manifest['snapshot_sha256'],'files':sorted(manifest['files']),
                      'new_fits':0,'model_calls':0},ensure_ascii=False))


if __name__=='__main__':main()
