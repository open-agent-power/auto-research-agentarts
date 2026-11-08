"""Run a bounded saved-evidence queue using constructed inputs, never research tools."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from demo_saved_rounds import ROOT, SOURCE, fixture_inputs
from autoresearch.contracts import canonical
from autoresearch.research_project import safe_path, write_bytes_once


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = safe_path(Path(args.output).absolute())
    root.mkdir(parents=True, exist_ok=True)
    first = fixture_inputs()
    second = fixture_inputs(first["proposal_result"]["candidate"]["candidate"],
                            request_id="synthetic-rsi-2", target=SOURCE, failed=True)
    for number, value in enumerate((first, second), 1):
        write_bytes_once(root / f"fixture-input-{number}.json", canonical(value).encode("utf-8"))
    manifest = json.loads((ROOT / "examples/recipe-improvement/sequence.fixture.example.json").read_text("utf-8"))
    manifest_path = root / "sequence.fixture.json"
    write_bytes_once(manifest_path, canonical(manifest).encode("utf-8"))
    command = [sys.executable, "-B", str(ROOT / "scripts/run_recipe_improvement.py"), "sequence",
               "--manifest", str(manifest_path), "--output", str(root / "queue"), "--max-rounds", "1"]
    for _ in range(2):
        subprocess.run(command, check=True)
    subprocess.run([sys.executable, "-B", str(ROOT / "scripts/run_recipe_improvement.py"), "next-input",
                    "--output", str(root / "queue/rounds"), "--round-id", "round-2"], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
