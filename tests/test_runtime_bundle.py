import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

module_path = Path(__file__).resolve().parents[1] / "scripts/build_runtime_bundle.py"
spec = importlib.util.spec_from_file_location("runtime_bundle", module_path)
bundler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundler)


class RuntimeBundleTests(unittest.TestCase):
    def test_reproducible_context_excludes_private_and_runtime_data(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            for name, data in {
                "pyproject.toml": "[project]",
                "agentarts/requirements-runtime.lock": "agentarts-sdk==0.1.8",
                "agentarts/runtime.Dockerfile": "FROM python:3.12-slim",
                "src/autoresearch/runtime.py": "# public source",
                "src/autoresearch/data/matbench_steels.json.gz": "pinned public resource fixture",
                "src/autoresearch/data/README.md": "public source and attribution",
                "src/autoresearch/data/private-secret.json": "PRIVATE_TOKEN=do-not-package",
                ".env": "PRIVATE_TOKEN=do-not-package",
                "runs/private-dataset.json": "sensitive-data",
                ".venv/lib/credentials.py": "private",
            }.items():
                target = repo / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(data, encoding="utf-8")
            first = bundler.build_bundle(repo, repo / "one.zip")
            second = bundler.build_bundle(repo, repo / "two.zip")
            self.assertEqual(first["sha256"], second["sha256"])
            with zipfile.ZipFile(first["path"]) as archive:
                self.assertEqual(set(archive.namelist()), {
                    "Dockerfile", "pyproject.toml", "requirements-runtime.lock",
                    "src/autoresearch/runtime.py", "src/autoresearch/data/matbench_steels.json.gz",
                    "src/autoresearch/data/README.md", "source-manifest.json"})
                manifest = json.loads(archive.read("source-manifest.json"))
                for name, digest in manifest.items():
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)
                self.assertNotIn(b"PRIVATE_TOKEN", b"".join(archive.read(n) for n in archive.namelist()))
            self.assertFalse(first["image_built"])
            self.assertFalse(first["platform_deployed"])
