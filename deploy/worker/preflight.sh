#!/bin/sh
# Qualify an operator-provided host using the existing bounded Docker probe.
# Does not install packages, change cgroups, start daemons or deploy a service.
set -eu

case "${1-}" in
  -h|--help)
    printf '%s\n' 'Usage: sh deploy/worker/preflight.sh [fresh-output-directory]' \
      'Exit 0: all probe checks passed; 2: blocked; 64: invalid output/arguments.'
    exit 0 ;;
esac
if [ "$#" -gt 1 ]; then
  printf '%s\n' 'Pass at most one fresh evidence directory.' >&2
  exit 64
fi
worker_repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$worker_repo_root"
worker_evidence_dir=${1:-"runs/worker-qualification-$(date -u +%Y%m%dT%H%M%SZ)"}
if [ -e "$worker_evidence_dir" ] || [ -L "$worker_evidence_dir" ]; then
  printf '%s\n' 'Output already exists; preserve it and choose a new directory.' >&2
  exit 64
fi
exec python3 scripts/verify_cloud_resources.py --output "$worker_evidence_dir"
