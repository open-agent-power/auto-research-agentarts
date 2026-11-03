import argparse
import json
import sys

from autoresearch.c01_research_outputs import export_study


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='Export a frozen C01 study as paper and numerical reproduction ZIP')
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(export_study(args.workspace, args.output), ensure_ascii=False, indent=2))
