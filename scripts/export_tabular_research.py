"""Export a read-only source-bound tabular assessment."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from autoresearch.tabular_research_view import export_tabular_research

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','prepared-input-directory','handoff-directory','diagnostic-directory','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();print(json.dumps(export_tabular_research(a.workspace,a.prepared_input_directory,a.handoff_directory,a.diagnostic_directory,a.output),ensure_ascii=False))
if __name__=='__main__':main()
