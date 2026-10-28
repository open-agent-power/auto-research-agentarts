"""No-fit studio fixtures: saved zero coefficients and actual public validation y.

These are boundary tests, not new training or scientific results. PDF generation
is mocked; the root's separate real PDF run is the rendering acceptance evidence.
"""

from contextlib import contextmanager
import csv
import hashlib
from importlib.util import find_spec
from http.client import HTTPConnection
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

from autoresearch import datasets, training
from autoresearch.contracts import ResearchError, canonical
from autoresearch.engine import AGENT_POLICY, Engine
from autoresearch.studio import create_server
from autoresearch.studio_outputs import ProjectOutputs
from autoresearch.studio_project import ProjectStore, ReadOnlyEvidence, prepare_project


def zero_coefficient_fixture(candidate, dataset_id=datasets.fixture.DATASET_ID):
    """Construct numeric parameters without fitting; calculate their actual MSE."""
    descriptor = datasets.descriptor(dataset_id)
    x, y = datasets.split_data(dataset_id, "train")
    vx, vy = datasets.split_data(dataset_id, "validation")
    width = x.shape[1]
    artifact = {
        "format": "polynomial-ridge-json-v1", "dataset_id": dataset_id,
        "evidence_type": descriptor["evidence_type"], "candidate": candidate.to_dict(),
        "data_sha256": descriptor["data_sha256"], "split_protocol": descriptor["split_protocol"],
        "training_code_sha256": training.code_identity(), "powers": np.eye(width, dtype=int).tolist(),
        "mean": [0.] * width, "scale": [1.] * width, "coef": [0.] * width, "intercept": 0.,
        "training_rows": len(y), "training_data_sha256": hashlib.sha256(x.tobytes() + y.tobytes()).hexdigest(),
        "libraries": {"numpy": np.__version__, "fixture": "zero_coefficients_no_fit"},
    }
    return artifact, {
        "training_mse": float(np.mean(y ** 2)),
        "validation_mse": float(np.mean((training.predict(artifact, vx) - vy) ** 2)),
        "num_features": width, "training_seconds": 0.,
    }


def file_hashes(root):
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def dummy_paper(project, figures, path):
    path = Path(path)
    path.write_bytes(b"%PDF-1.4\n% unit-test fixture only; not a rendered paper\n")
    return {"path": str(path), "pages": 0, "fixture": True}


@contextmanager
def local_server(workspace):
    server = create_server(workspace, port=0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def request(server, method, path, body=None, headers=None, raw_headers=None):
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        if raw_headers is None:
            connection.request(method, path, body=body, headers=headers or {})
        else:
            connection.putrequest(method, path, skip_host=True)
            for name, value in raw_headers:
                connection.putheader(name, value)
            connection.endheaders(body)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.output = self.root / "studio"
        self.trainer = patch("autoresearch.training.train", side_effect=zero_coefficient_fixture)
        self.train_mock = self.trainer.start()
        self.addCleanup(self.trainer.stop)
        self.engine = Engine(self.source)
        self.cid = self.engine.create("studio-case", "No-fit studio boundary fixture", 3,
                                      datasets.STEELS_ID, AGENT_POLICY)["campaign_id"]
        for number, alpha in enumerate((.01, 1.0), start=1):
            observation = self.engine.observe(self.cid)
            self.engine.submit(self.cid, "trial-" + str(number), {
                "observation_sha256": observation["observation_sha256"],
                "hypothesis": "Unit-test numeric artifact; no training or discovery.",
                "expected_effect": "Zero coefficients yield reproducible validation MSE.",
                "candidate": {"degree": 1, "alpha": alpha},
                "evidence_trial_ids": [trial["id"] for trial in observation["trials"]],
            })
        self.assertEqual(self.train_mock.call_count, 2)
        self.train_mock.reset_mock()
        self.source_before = file_hashes(self.source)
        self.project = prepare_project(self.source, self.cid, self.output)
        self.store = ProjectStore(self.output)

    def tearDown(self):
        self.train_mock.assert_not_called()

    def assert_research_error(self, code, call):
        with self.assertRaises(ResearchError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)

    def test_snapshot_recomputes_saved_parameters_without_fitting_or_source_writes(self):
        self.assertEqual(file_hashes(self.source), self.source_before)
        self.assertEqual(self.project["snapshot"]["mode"], "frozen_existing_evidence")
        self.assertEqual(self.project["metrics"]["trials"], 2)
        self.assertEqual(self.project["metrics"]["accepted"], 1)
        self.assertEqual(self.project["metrics"]["rejected"], 1)
        _, y = datasets.split_data(datasets.STEELS_ID, "validation")
        self.assertAlmostEqual(self.project["metrics"]["best_validation_mse"], float(np.mean(y ** 2)))
        self.assertIsNone(self.project["metrics"]["test_mse"])
        self.assertEqual(self.project["next_questions"], [])
        with self.assertRaises(ResearchError) as caught:
            with ReadOnlyEvidence(self.source).connection(write=True):
                self.fail("source writes must not be available")
        self.assertEqual(caught.exception.code, "READ_ONLY")
        self.assertEqual(file_hashes(self.source), self.source_before)

    def test_snapshot_rejects_changed_evidence_and_incomplete_manifest(self):
        (self.output / "evidence/predictions.csv").write_text("tampered\n", encoding="utf-8")
        self.assert_research_error("ARTIFACT_CHANGED", self.store.project)
        manifest_path = self.output / "evidence-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        del manifest["files"]["evidence/predictions.csv"]
        manifest_path.write_text(canonical(manifest), encoding="utf-8")
        with self.assertRaises(ResearchError):
            self.store.project()

    def test_snapshot_rejects_changed_source_model_and_changed_recorded_metric(self):
        trial = self.engine.status(self.cid)["trials"][0]
        model_path = self.source / trial["model_artifact"]
        original = model_path.read_bytes()
        model_path.write_bytes(original + b"\n")
        self.assert_research_error("ARTIFACT_CHANGED",
                                   lambda: prepare_project(self.source, self.cid, self.root / "changed-source"))
        model_path.write_bytes(original)
        with self.engine.connection(write=True) as con:
            row = con.execute("SELECT result_json FROM trials WHERE id=?", (trial["id"],)).fetchone()
            result = json.loads(row["result_json"])
            result["metrics"]["validation_mse"] += 100
            con.execute("UPDATE trials SET result_json=? WHERE id=?", (canonical(result), trial["id"]))
        self.assert_research_error("METRIC_MISMATCH",
                                   lambda: prepare_project(self.source, self.cid, self.root / "wrong-metric"))

    def test_preparation_never_overwrites_source_or_existing_project(self):
        self.assert_research_error("INVALID_REQUEST",
                                   lambda: prepare_project(self.source, self.cid, self.source / "nested"))
        self.assert_research_error("OUTPUT_EXISTS",
                                   lambda: prepare_project(self.source, self.cid, self.output))
        self.assertEqual(file_hashes(self.source), self.source_before)

    def test_question_restart_persistence_is_separate_from_frozen_evidence(self):
        before = json.loads((self.output / "evidence-manifest.json").read_text(encoding="utf-8"))
        question = self.store.add_question("  检查缺失加工条件如何限制解释。  ")
        fresh = ProjectStore(self.output).project()
        self.assertEqual(fresh["next_questions"], [question])
        self.assertEqual(question["status"], "saved_pending_execution")
        self.assertEqual(question["text"], "检查缺失加工条件如何限制解释。")
        self.assertEqual(before, self.store.verify())
        self.assertEqual(file_hashes(self.source), self.source_before)
        for invalid in ("", " ", "\0", "问" * 1501, None, {}, 1):
            self.assert_research_error("INVALID_REQUEST", lambda value=invalid: self.store.add_question(value))

    def test_http_host_origin_csrf_and_restart_persistence(self):
        with local_server(self.output) as server:
            self.assertEqual(server.server_address[0], "127.0.0.1")
            status, headers, raw = request(server, "GET", "/api/project")
            self.assertEqual(status, 200)
            self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
            self.assertNotIn("Access-Control-Allow-Origin", headers)
            token = json.loads(raw)["csrf_token"]
            host = "127.0.0.1:" + str(server.server_port)
            origin = "http://" + host
            payload = canonical({"text": "保存后待人工核查，不执行模型。"}).encode("utf-8")
            valid = {"Content-Type": "application/json", "X-Research-CSRF": token, "Origin": origin}
            for bad_host in ("evil.example", "127.0.0.1:1"):
                self.assertEqual(request(server, "GET", "/api/project", headers={"Host": bad_host})[0], 403)
            self.assertEqual(request(server, "GET", "/api/project",
                                     raw_headers=[("Host", host), ("Host", host)])[0], 403)
            for bad_origin in ("https://evil.example", "null", "http://127.0.0.1:1"):
                self.assertEqual(request(server, "POST", "/api/questions", payload,
                                         {**valid, "Origin": bad_origin})[0], 403)
            for bad_token in ("", "incorrect", "\u00e9"):
                self.assertEqual(request(server, "POST", "/api/questions", payload,
                                         {**valid, "X-Research-CSRF": bad_token})[0], 403)
            self.assertEqual(request(server, "POST", "/api/questions", payload,
                                     {"Content-Type": "application/json", "Origin": origin})[0], 403)
            status, _, saved = request(server, "POST", "/api/questions", payload, valid)
            self.assertEqual(status, 201)
            item = json.loads(saved)["question"]
            self.assertEqual(item["status"], "saved_pending_execution")
        with local_server(self.output) as fresh:
            status, _, raw = request(fresh, "GET", "/api/project")
            self.assertEqual(status, 200)
            current = json.loads(raw)
            self.assertEqual(current["next_questions"], [item])
            self.assertNotEqual(current["csrf_token"], token)
            self.assertEqual(request(fresh, "POST", "/api/questions", payload,
                                     {"Content-Type": "application/json", "X-Research-CSRF": token})[0], 403)
        self.assertEqual(file_hashes(self.source), self.source_before)

    def test_http_paths_static_assets_and_question_body_are_allowlisted(self):
        with local_server(self.output) as server:
            _, _, raw = request(server, "GET", "/api/project")
            token = json.loads(raw)["csrf_token"]
            host = "127.0.0.1:" + str(server.server_port)
            valid = {"Content-Type": "application/json", "X-Research-CSRF": token}
            for path in ("/", "/app.css", "/app.js"):
                status, headers, body = request(server, "GET", path)
                self.assertEqual(status, 200)
                self.assertTrue(body)
                self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
            for path in ("/../studio.sqlite3", "/%2e%2e/project.json", "/project.json", "/.env",
                         "/evidence/experiment.json", "/api/project?path=secret", "/api/run_trial",
                         "/api/figures/../../project.json"):
                self.assertEqual(request(server, "GET", path)[0], 404)
            self.assertEqual(request(server, "POST", "/api/run_trial", b'{"text":"x"}', valid)[0], 404)
            for body in (b'{"text":"x","text":"y"}', b'{"text":"x","workspace":"elsewhere"}',
                         b'{"text":NaN}', b'{"text":1e999}', b"\xff", b'{"text":""}'):
                self.assertEqual(request(server, "POST", "/api/questions", body, valid)[0], 400)
            self.assertEqual(request(server, "POST", "/api/questions", b"x" * 8193, valid)[0], 413)
            self.assertEqual(request(server, "POST", "/api/questions", b'{"text":"x"}',
                                     {**valid, "Content-Type": "text/plain"})[0], 415)
            for size in ("9" * 5000, "\u00b2", "0"):
                status, _, _ = request(server, "POST", "/api/questions", raw_headers=[
                    ("Host", host), ("Content-Type", "application/json"),
                    ("X-Research-CSRF", token), ("Content-Length", size)])
                self.assertEqual(status, 413)
            self.assertEqual(request(server, "POST", "/api/questions", raw_headers=[
                ("Host", host), ("Content-Type", "application/json"), ("X-Research-CSRF", token),
                ("Content-Length", "12"), ("Content-Length", "12")])[0], 413)

    def test_http_downloads_use_only_fixed_names_without_real_pdf_generation(self):
        with local_server(self.output) as server:
            outputs = server.project_outputs

            def export_fixture():
                outputs.exports.mkdir(exist_ok=True)
                (outputs.exports / "research-paper.pdf").write_bytes(b"%PDF-1.4 fixture, not rendered")
                (outputs.exports / "reproduction.zip").write_bytes(b"PK fixture, not an exported archive")

            with patch.object(outputs, "export", side_effect=export_fixture) as export_mock:
                for path, mime, filename in (("/api/export/paper.pdf", "application/pdf", "research-paper.pdf"),
                                             ("/api/export/reproduction.zip", "application/zip", "reproduction.zip")):
                    status, headers, body = request(server, "GET", path)
                    self.assertEqual(status, 200)
                    self.assertEqual(headers["Content-Type"], mime)
                    self.assertIn(filename, headers["Content-Disposition"])
                    self.assertTrue(body)
                self.assertEqual(export_mock.call_count, 2)

    @unittest.skipUnless(find_spec("matplotlib") is not None, "install the reports extra for figure/export tests")
    def test_reproduction_zip_excludes_secrets_and_verifies_without_numpy_or_fitting(self):
        for name in (".env", "private-key.pem", "studio-private.sqlite3", "evidence/private.csv",
                     "evidence/source/secret.py", "figures/auth-token.txt", "exports/private.json"):
            target = self.output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("PRIVATE_STUDIO_SECRET_DO_NOT_EXPORT", encoding="utf-8")
        outputs = ProjectOutputs(self.store)
        with patch("autoresearch.paper_export.render_paper", side_effect=dummy_paper) as paper:
            exported = outputs.export()
            self.assertEqual(outputs.export(), exported)
            self.assertEqual(paper.call_count, 1)
        self.assertEqual(exported["new_training_runs"], 0)
        self.assertEqual(exported["cloud_calls"], 0)
        expected = {
            "project.json", "evidence/experiment.json", "evidence/validation.csv", "evidence/predictions.csv",
            "evidence/data-attribution.md", "evidence/environment.json",
            "evidence/source/contracts.py", "evidence/source/datasets.py", "evidence/source/fixture.py",
            "evidence/source/training.py", "figures/validation.png", "figures/validation.svg",
            "figures/prediction.png", "figures/prediction.svg", "figures/comparison.csv",
            "figures/figure-manifest.json", "research-paper.pdf", "verify_results.py", "README.md",
            "package-manifest.json",
        }
        expected.update("evidence/models/" + trial["id"] + ".json" for trial in self.project["trials"])
        extracted = self.root / "extracted"
        with zipfile.ZipFile(exported["reproduction"]["path"]) as archive:
            self.assertEqual(set(archive.namelist()), expected)
            self.assertNotIn(b"PRIVATE_STUDIO_SECRET_DO_NOT_EXPORT", b"".join(archive.read(n) for n in archive.namelist()))
            manifest = json.loads(archive.read("package-manifest.json"))
            self.assertEqual(set(manifest["files"]), expected - {"package-manifest.json"})
            for name, digest in manifest["files"].items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)
            archive.extractall(extracted)
        checked = subprocess.run([sys.executable, "-I", "-S", str(extracted / "verify_results.py")],
                                 cwd=extracted, capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        verified = json.loads(checked.stdout)
        self.assertTrue(verified["ok"])
        self.assertFalse(verified["training_performed"])
        self.assertFalse(verified["network_used"])
        self.assertEqual([trial["rows"] for trial in verified["trials"]], [62, 62])
        # Rehash a changed table to bypass transport hashes; semantic MSE verification must still fail.
        table = extracted / "evidence/validation.csv"
        with table.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        rows[0]["target"] = str(float(rows[0]["target"]) + 100)
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        table.write_text(output.getvalue(), encoding="utf-8")
        manifest["files"]["evidence/validation.csv"] = hashlib.sha256(table.read_bytes()).hexdigest()
        (extracted / "package-manifest.json").write_text(canonical(manifest), encoding="utf-8")
        corrupted = subprocess.run([sys.executable, "-I", "-S", str(extracted / "verify_results.py")],
                                   cwd=extracted, capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertNotEqual(corrupted.returncode, 0)
        self.assertIn("recomputed validation MSE differs", corrupted.stderr)
        self.assertEqual(file_hashes(self.source), self.source_before)


if __name__ == "__main__":
    unittest.main()

