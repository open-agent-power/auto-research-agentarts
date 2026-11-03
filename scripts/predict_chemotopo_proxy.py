"""Run the predeclared offline grouped raw-red proxy diagnostic."""
import argparse
from autoresearch.chemotopo_prediction import run_diagnostic


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True); parser.add_argument('--output',required=True)
    args=parser.parse_args(); print(run_diagnostic(args.source,args.output))


if __name__=='__main__': main()
