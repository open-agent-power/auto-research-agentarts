"""Write a bounded JSON inventory of the pinned ChemoTopoChip project."""
import argparse
from pathlib import Path
from autoresearch.chemotopo_project import inspect_project
from autoresearch.contracts import canonical


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True)
    parser.add_argument('--output',required=True,help='New JSON file; existing files are never overwritten.')
    args=parser.parse_args()
    result=inspect_project(args.source)
    output=Path(args.output)
    if output.resolve()==Path(args.source).resolve(): raise ValueError('output must differ from source')
    with output.open('x',encoding='utf-8') as stream:
        stream.write(canonical(result)+'\n')
    print(f"Inspected {result['inventory']['object_count']} bounded HDF5 objects; wrote {output}")


if __name__=='__main__': main()
