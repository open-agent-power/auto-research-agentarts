"""Allowlisted build context, including only the pinned public data resource."""

import hashlib
import json
from pathlib import Path
import zipfile


def build_bundle(repo, destination):
    repo = Path(repo).resolve()
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = {"pyproject.toml": repo / "pyproject.toml",
             "requirements-runtime.lock": repo / "agentarts/requirements-runtime.lock",
             "Dockerfile": repo / "agentarts/runtime.Dockerfile"}
    for path in sorted((repo / "src/autoresearch").glob("*.py")):
        files[path.relative_to(repo).as_posix()] = path
    for relative in ("src/autoresearch/data/matbench_steels.json.gz", "src/autoresearch/data/README.md"):
        files[relative] = repo / relative
    manifest = {}
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, path in sorted(files.items()):
            if path.is_symlink() or not path.resolve().is_relative_to(repo):
                raise ValueError("bundle sources must be ordinary files inside the repository")
            data = path.read_bytes()
            manifest[relative] = hashlib.sha256(data).hexdigest()
            info = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
        info = zipfile.ZipInfo("source-manifest.json", date_time=(2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, json.dumps(manifest, indent=2, sort_keys=True))
    return {"path": str(destination), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "files": manifest, "image_built": False, "platform_deployed": False}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(build_bundle(root, root / ".agent/artifacts/runtime-context.zip"), indent=2))
