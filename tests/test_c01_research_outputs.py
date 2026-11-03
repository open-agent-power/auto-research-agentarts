"""Standalone verifier tests; all numeric fixtures are small synthetic C01 rows."""
import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import c01, c01_loop, c01_research, c01_research_outputs as outputs, c01_research_verifier as verifier, knowledge
from autoresearch.contracts import ResearchError, fingerprint


class C01ResearchOutputsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        samples = []
        for index in range(8):
            row = {"sample_id": "Alloy " + str(index + 1)}
            row.update({name: float((index + 1) ** (column % 2 + 1)) for column, name in enumerate(c01.FEATURES)})
            row.update({target["id"]: float((index + 2) * (column + 1) + index % 3)
                        for column, target in enumerate(c01.TARGETS)})
            samples.append(row)
        inputs = {"samples": samples, "source": {"archive_sha256": "a" * 64},
                  "audit": [], "provenance": [], "bio_mapping": []}
        cls.reproduction = {"inputs": inputs, "inputs_sha256": fingerprint(inputs),
                            "analysis_code_sha256": c01_research.code_identity(),
                            "protocol": "existing C01 fold-fitted scaler/Ridge_svd; all eight alloy groups held out once",
                            "model_weight_training": "32 actual Ridge fits per recipe; no LLM weight training"}
        cls.record = {"schema_version": "c01-public-research-v1", "goal": "Synthetic record verification only",
                      "status": "stopped", "origin_observation_sha256": "b" * 64, "archive_sha256": "a" * 64,
                      "corpus_sha256": "c" * 64, "scientific_status": verifier.SCIENTIFIC_STATUS,
                      "decision_origin": verifier.DECISION_ORIGIN, "fits": [], "diagnostics": [], "decisions": [],
                      "references": [{"citation_id": "citation-test", "source": {"path": "profiles/test.md", "sha256": "d" * 64,
                                                                                 "title": "Synthetic source", "page": None},
                                      "location": {"line_start": 1, "line_end": 2}}]}
        def decision(identifier, action, params, result, previous):
            record = {"id": identifier, "ordinal": len(cls.record["decisions"]) + 1, "action": action,
                      "request_id": "request-" + identifier, "observation_sha256": "e" * 64,
                      "reason": "Synthetic protocol test; no scientific claim.", "parameters": params,
                      "source_citation_ids": ["citation-test"], "evidence_action_ids": previous,
                      "result_sha256": fingerprint(result)}
            cls.record["decisions"].append(record)
            return record
        decision("search-1", "search", {"query": "synthetic"}, {"evidence": "not exported"}, [])
        cls.fit_results = {}
        latest = []
        for ordinal, (alpha, features) in enumerate(((1.0, list(c01.FEATURES)), (100.0, list(c01.FEATURES[:2]))), 1):
            identifier = "fit-" + str(ordinal)
            summary, predictions = c01._round(samples, 1, alpha, features)
            summary.update(id=identifier, title="受控Ridge留一比较")
            result = {"recipe": {"alpha": alpha, "features": features}, "summary": summary, "predictions": predictions,
                      "fold_fits": 32, "promotion": verifier.FIT_PROMOTION, "model_type": verifier.MODEL_TYPE}
            params = {"alpha": alpha, "features": features, "hypothesis": "Regularization changes held-out errors.",
                      "expected_effect": "Compare all targets to their fold-mean baseline."}
            submitted = decision(identifier, "fit", params, result, latest)
            cls.record["fits"].append({"id": identifier, "recipe": result["recipe"], "summary": summary,
                                       "predictions": predictions, **{key: submitted[key] for key in
                                           ("reason", "source_citation_ids", "evidence_action_ids")}})
            cls.fit_results[identifier] = result
            latest = [identifier]
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(cls.fit_results["fit-2"]["predictions"][0]))
        writer.writeheader()
        writer.writerows(cls.fit_results["fit-2"]["predictions"])
        residuals = {"fit_action_id": "fit-2", **c01_loop.residual_influence(stream.getvalue().encode())}
        submitted = decision("residual-1", "residuals", {"fit_action_id": "fit-2"}, residuals, latest)
        cls.record["diagnostics"].append({**{key: submitted[key] for key in
            ("id", "action", "parameters", "reason", "result_sha256", "source_citation_ids", "evidence_action_ids")}, "result": residuals})
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(samples[0]))
        writer.writeheader()
        writer.writerows(samples)
        correlation = c01_loop.correlation_influence(stream.getvalue().encode())
        submitted = decision("correlation-1", "correlation", {}, correlation, ["residual-1"])
        cls.record["diagnostics"].append({**{key: submitted[key] for key in
            ("id", "action", "parameters", "reason", "result_sha256", "source_citation_ids", "evidence_action_ids")}, "result": correlation})
        decision("stop-1", "stop", {}, {"decision": "stop"}, ["correlation-1"])

    def records(self):
        return copy.deepcopy(self.record), copy.deepcopy(self.reproduction)

    def assert_invalid(self, change):
        research, reproduction = self.records()
        change(research, reproduction)
        with self.assertRaises(ValueError):
            verifier.validate_record(research, reproduction)

    def reseal_fit(self, research, fit):
        result = {"recipe": fit["recipe"], "summary": fit["summary"], "predictions": fit["predictions"],
                  "fold_fits": 32, "promotion": verifier.FIT_PROMOTION, "model_type": verifier.MODEL_TYPE}
        next(row for row in research["decisions"] if row["id"] == fit["id"])["result_sha256"] = fingerprint(result)

    def package(self, root):
        research, reproduction = self.records()
        for name in verifier.PACKAGE_FILES:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"test artifact: " + name.encode())
        for module in (c01, c01_loop, knowledge, c01_research):
            (root / "source" / (module.__name__.rsplit(".", 1)[-1] + ".py")).write_bytes(Path(module.__file__).read_bytes())
        # If any bundled source is imported, the subprocess test would fail.
        (root / "source/contracts.py").write_text("raise RuntimeError('package source must never execute')\n", encoding="utf-8")
        (root / "verify_results.py").write_bytes(Path(verifier.__file__).read_bytes())
        (root / "research.json").write_text(json.dumps(research, ensure_ascii=False), encoding="utf-8")
        (root / "reproduction.json").write_text(json.dumps(reproduction, ensure_ascii=False), encoding="utf-8")
        (root / "environment.json").write_text("{}", encoding="utf-8")
        self.seal_package(root)

    def seal_package(self, root):
        manifest = {"schema_version": "c01-reproduction-package-v1", "files": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sorted(verifier.PACKAGE_FILES)}}
        (root / "package-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_independent_recompute_all_recipes_metrics_and_diagnostics(self):
        research, reproduction = self.records()
        with patch("autoresearch.c01._round", side_effect=AssertionError("must not use production evaluator")):
            report = verifier.validate_record(research, reproduction)
        self.assertTrue(report["ok"])
        self.assertEqual(report["recipes_checked"], 2)
        self.assertEqual(report["fold_fits_performed"], 64)
        self.assertEqual(report["diagnostics_checked"], 2)
        self.assertLess(report["max_abs_prediction_error"], 1e-10)
        for field in ("network_used", "package_source_executed", "scientific_validation", "llm_identity_verified",
                      "origin_observation_reconstructed", "raw_archive_independently_verified"):
            self.assertFalse(report[field])

    def test_saved_predictions_and_metrics_fail_even_with_resealed_hash(self):
        for kind in ("prediction", "metric", "baseline", "training_fold", "duplicate_prediction", "summary_id"):
            with self.subTest(kind=kind):
                def change(research, reproduction):
                    fit = research["fits"][0]
                    if kind == "prediction": fit["predictions"][0]["predicted"] += 1
                    elif kind == "metric": fit["summary"]["metrics"][0]["mae"] += 1
                    elif kind == "baseline": fit["predictions"][0]["baseline_predicted"] += 1
                    elif kind == "training_fold": fit["predictions"][0]["training_sample_ids"] += ";Alloy 1"
                    elif kind == "duplicate_prediction": fit["predictions"][1] = copy.deepcopy(fit["predictions"][0])
                    else: fit["summary"]["id"] = "different-fit"
                    self.reseal_fit(research, fit)
                self.assert_invalid(change)

    def test_hash_and_archive_binding(self):
        self.assert_invalid(lambda r, p: p["inputs"]["samples"][0].update(ecm_gpa=123))
        self.assert_invalid(lambda r, p: r.update(archive_sha256="f" * 64))
        self.assert_invalid(lambda r, p: r["decisions"][1].update(result_sha256="f" * 64))
        self.assert_invalid(lambda r, p: p.update(inputs_sha256="not-a-sha"))

    def test_finite_exact_sample_dimensions_and_nonconstant_targets(self):
        def with_reseal(research, reproduction, mutate):
            mutate(reproduction["inputs"]["samples"])
            reproduction["inputs_sha256"] = fingerprint(reproduction["inputs"])
        for mutate in (lambda rows: rows.pop(), lambda rows: rows[0].update(sample_id=rows[1]["sample_id"]),
                       lambda rows: rows[0].update(ecm_gpa=True), lambda rows: rows[0].update(secret_label=3),
                       lambda rows: rows[0].pop("yield_mpa"),
                       lambda rows: [row.update(alp_norm_d21=1.0) for row in rows]):
            with self.subTest(mutate=mutate):
                self.assert_invalid(lambda r, p: with_reseal(r, p, mutate))
        self.assert_invalid(lambda r, p: p["inputs"]["samples"][0].update(ecm_gpa=float("nan")))
        self.assert_invalid(lambda r, p: p["inputs"]["samples"][0].update(ecm_gpa=float("inf")))

    def test_bounded_recipes_and_boolean_metrics(self):
        for alpha in (True, 0, 10001, float("inf"), 10 ** 400):
            self.assert_invalid(lambda r, p: r["fits"][0]["recipe"].update(alpha=alpha))
        for features in (["hidden_target"], [], ["ecm_gpa", "ecm_gpa"]):
            self.assert_invalid(lambda r, p: r["fits"][0]["recipe"].update(features=features))
        self.assert_invalid(lambda r, p: r["fits"][0]["summary"]["metrics"][0].update(mae=True))

    def test_submitted_feature_order_can_differ_but_recipe_alpha_is_exact(self):
        research, reproduction = self.records()
        research["decisions"][1]["parameters"]["features"] = list(reversed(c01.FEATURES))
        self.assertTrue(verifier.validate_record(research, reproduction)["ok"])
        self.assert_invalid(lambda r, p: r["decisions"][1]["parameters"].update(alpha=1.000000001))

    def test_decision_order_references_status_and_projection_binding(self):
        changes = (lambda r, p: r["fits"].append(copy.deepcopy(r["fits"][0])),
                   lambda r, p: r["decisions"][2].update(id=r["decisions"][1]["id"]),
                   lambda r, p: r["decisions"][1].update(evidence_action_ids=["stop-1"]),
                   lambda r, p: r["fits"][0].update(reason="detached explanation"),
                   lambda r, p: r.update(status="active"),
                   lambda r, p: r["references"].clear(),
                   lambda r, p: r["references"].append(copy.deepcopy(r["references"][0])),
                   lambda r, p: r["fits"].pop(),
                   lambda r, p: r["diagnostics"].pop())
        for change in changes:
            with self.subTest(change=change): self.assert_invalid(change)

    def test_resealed_diagnostic_values_do_not_pass(self):
        for which in (0, 1):
            def change(research, reproduction):
                diagnostic = research["diagnostics"][which]
                if which == 0: diagnostic["result"]["targets"][0]["share_of_absolute_error"] += .1
                else: diagnostic["result"]["leave_one_out"][0]["pearson_r"] -= .1
                diagnostic["result_sha256"] = fingerprint(diagnostic["result"])
                next(d for d in research["decisions"] if d["id"] == diagnostic["id"])["result_sha256"] = diagnostic["result_sha256"]
            self.assert_invalid(change)

    def test_untrusted_empty_record_is_not_a_scientific_or_llm_pass(self):
        research, reproduction = self.records()
        research.update(fits=[], diagnostics=[], decisions=[], references=[], status="active")
        report = verifier.validate_record(research, reproduction)
        self.assertEqual(report["recipes_checked"], 0)
        self.assertFalse(report["numerical_results_present"])
        self.assert_invalid(lambda r, p: r.update(scientific_status="scientifically_validated"))
        self.assert_invalid(lambda r, p: r.update(decision_origin="authenticated_LLM"))

    def test_complete_package_and_isolated_standalone_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.package(root)
            report = verifier.verify_package(root)
            self.assertEqual(report["package_files_checked"], 14)
            self.assertFalse(report["presentation_content_independently_verified"])
            completed = subprocess.run([sys.executable, "-I", "-B", str(root / "verify_results.py")],
                                       cwd=root.parent, capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            self.assertEqual(json.loads(completed.stdout)["fold_fits_performed"], 64)

    def test_package_checksum_extra_missing_and_code_identity(self):
        for case in ("checksum", "extra", "missing", "code_identity"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.package(root)
                if case == "checksum": (root / "paper.pdf").write_bytes(b"changed")
                elif case == "extra": (root / "secret.txt").write_bytes(b"extra")
                elif case == "missing": (root / "figures/comparison.svg").unlink()
                else:
                    (root / "source/c01.py").write_bytes(b"raise AssertionError('never execute')\n")
                    self.seal_package(root)
                with self.assertRaises(ValueError): verifier.verify_package(root)

    def test_manifest_escape_duplicate_keys_and_nonfinite_json(self):
        for manifest in (b'{"schema_version":"c01-reproduction-package-v1","files":{"../outside":"abc"}}',
                         b'{"schema_version":"c01-reproduction-package-v1","files":{},"files":{}}',
                         b'{"schema_version":"c01-reproduction-package-v1","files":{},"bad":1e999}'):
            with self.subTest(manifest=manifest), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "package-manifest.json").write_bytes(manifest)
                with self.assertRaises(ValueError): verifier.verify_package(root)

    def test_package_hardlinks_and_redirects_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "package"
            root.mkdir()
            self.package(root)
            target = root.parent / "evidence.pdf"
            target.write_bytes((root / "paper.pdf").read_bytes())
            (root / "paper.pdf").unlink()
            os.link(target, root / "paper.pdf")
            with self.assertRaises(ValueError): verifier.verify_package(root)
            self.assertEqual(target.read_bytes(), b"test artifact: paper.pdf")
            (root / "paper.pdf").unlink()
            try:
                (root / "paper.pdf").symlink_to(target)
            except OSError:
                return  # Windows may not grant symlink creation; hard-link test already ran.
            with self.assertRaises(ValueError): verifier.verify_package(root)

    def test_abstract_only_describes_research_actions_actually_executed(self):
        research, _ = self.records()
        research.update(fits=research["fits"][:1], diagnostics=[])
        abstract = outputs._abstract(research)
        self.assertIn("配方执行", abstract)
        for unsupported in ("误差诊断", "关联稳定性", "收缩", "特征组", "消融", "POPPER"):
            self.assertNotIn(unsupported, abstract)
        research, _ = self.records()
        abstract = outputs._abstract(research)
        for performed in ("误差诊断", "关联稳定性", "特征组"):
            self.assertIn(performed, abstract)
        self.assertNotIn("收缩", abstract)  # These two synthetic recipes also change features.
        research["fits"][1]["recipe"]["features"] = list(research["fits"][0]["recipe"]["features"])
        self.assertIn("收缩", outputs._abstract(research))

    def test_inspection_projection_rejects_parameters_without_claiming_payload_or_science_verification(self):
        research,reproduction=self.records()
        inspection=copy.deepcopy(research['decisions'][0])
        inspection.update(id='inspection-1',request_id='request-inspection-1',action='inspect_dataset',
                          source_citation_ids=[],parameters={})
        research['decisions'].insert(0,inspection)
        for ordinal,decision in enumerate(research['decisions'],1):decision['ordinal']=ordinal
        self.assertTrue(verifier.validate_record(research,reproduction)['ok'])
        self.assertIn('冻结数值与来源检查',outputs._abstract(research))
        self.assertNotIn('samples',inspection)
        inspection['parameters']['path']='../not-allowed'
        with self.assertRaises(ValueError):verifier.validate_record(research,reproduction)

    def test_control_projection_binds_current_proposal_and_experiment_without_approving_rationale(self):
        research,reproduction=self.records()
        latest=next(d for d in reversed(research['decisions']) if d['action'] in {'fit','residuals','correlation'})
        template=copy.deepcopy(research['decisions'][-1])
        proposal={**template,'id':'control-proposal','request_id':'control-proposal-request','action':'propose_control',
                  'parameters':{'decision':'pause'},'evidence_action_ids':[latest['id']]}
        review={**template,'id':'control-review','request_id':'control-review-request','action':'review_evidence',
                'parameters':{'field':'control_rationale','question':'Is the rationale supported by the actual evidence?',
                              'finding':'Synthetic unapproved assertion only.','status':'unresolved','next_check':'Choose a justified action.'},
                'evidence_action_ids':['control-proposal',latest['id']]}
        research['decisions'][-1:-1]=[proposal,review]
        for ordinal,decision in enumerate(research['decisions'],1):decision['ordinal']=ordinal
        self.assertTrue(verifier.validate_record(research,reproduction)['ok'])
        self.assertIn('控制理由评议',outputs._abstract(research))
        for kind in ('missing_proposal','missing_experiment','bad_decision','extra_path','duplicate_proposal','duplicate_review'):
            altered=copy.deepcopy(research)
            if kind=='missing_proposal':altered['decisions'][-2]['evidence_action_ids']=[latest['id']]
            elif kind=='missing_experiment':altered['decisions'][-2]['evidence_action_ids']=['control-proposal']
            elif kind=='bad_decision':altered['decisions'][-3]['parameters']['decision']='continue'
            elif kind=='extra_path':altered['decisions'][-3]['parameters']['path']='../not-allowed'
            else:
                item=copy.deepcopy(altered['decisions'][-3 if kind=='duplicate_proposal' else -2])
                item.update(id='duplicate-control',request_id='duplicate-control-request')
                altered['decisions'].insert(-1,item)
                for ordinal,decision in enumerate(altered['decisions'],1):decision['ordinal']=ordinal
            with self.subTest(kind=kind),self.assertRaises(ValueError):verifier.validate_record(altered,reproduction)

    def test_read_projection_binds_source_and_range_without_claiming_original_text_coverage(self):
        research,reproduction=self.records()
        research['references'][0]['source']['id']='synthetic-document'
        read=copy.deepcopy(research['decisions'][0])
        read.update(id='read-1',request_id='request-read-1',action='read_source',source_citation_ids=[],
                    parameters={'document_id':'synthetic-document','source_sha256':'d'*64,'start_chunk':0,'count':1})
        research['decisions'].insert(1,read)
        for ordinal,decision in enumerate(research['decisions'],1):decision['ordinal']=ordinal
        self.assertTrue(verifier.validate_record(research,reproduction)['ok'])
        self.assertIn('固定来源分段阅读',outputs._abstract(research))
        self.assertNotIn('quote',read);self.assertNotIn('outline',read)
        for changes in ({'source_sha256':'f'*64},{'document_id':'different-document'},
                        {'start_chunk':-1},{'count':True},{'count':3},{'path':'../not-allowed'}):
            altered=copy.deepcopy(research)
            altered['decisions'][1]['parameters'].update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                verifier.validate_record(altered,reproduction)

    def test_export_checks_source_identity_and_uses_one_snapshot_before_rendering(self):
        research, reproduction = self.records()
        names = ("c01.py", "c01_loop.py", "knowledge.py", "c01_research.py", "contracts.py")
        paths = {Path(outputs.__file__).with_name(name).resolve(): name for name in names}
        original_read = Path.read_bytes
        expected = {name: original_read(path) for path, name in paths.items()}
        figures = {"figures/comparison.png": b"mock PNG", "figures/comparison.svg": b"mock SVG"}
        # A mismatch must fail before rendering or creating any output directory.
        def already_changed(path):
            payload = original_read(path)
            return payload + b"\n# changed\n" if path.resolve() in paths and paths[path.resolve()] == "c01.py" else payload
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "rejected"
            with patch.object(outputs.C01Research, "export", return_value={"state": {}, "reproduction": reproduction}), \
                 patch.object(outputs, "public_record", return_value=research), \
                 patch.object(verifier, "validate_record", return_value={"ok": True}), \
                 patch.object(outputs, "_figures", return_value=figures) as render_figures, \
                 patch.object(outputs, "_paper", return_value=b"mock PDF") as render_paper, \
                 patch.object(Path, "read_bytes", already_changed):
                with self.assertRaises(ResearchError) as error:
                    outputs.export_study("unused synthetic workspace", destination)
                self.assertEqual(error.exception.code, "CODE_CHANGED")
                render_figures.assert_not_called()
                render_paper.assert_not_called()
            self.assertFalse(destination.exists())
        # Later source changes cannot leak into an already identity-checked package.
        reads, rendering_started = {}, False
        def versioned_read(path):
            name = paths.get(path.resolve())
            if name is None:
                return original_read(path)
            reads[name] = reads.get(name, 0) + 1
            return expected[name] + (b"\n# changed during rendering\n" if rendering_started else b"")
        def start_rendering(_):
            nonlocal rendering_started
            rendering_started = True
            return figures
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "snapshot"
            with patch.object(outputs.C01Research, "export", return_value={"state": {}, "reproduction": reproduction}), \
                 patch.object(outputs, "public_record", return_value=research), \
                 patch.object(verifier, "validate_record", return_value={"ok": True}), \
                 patch.object(outputs, "_figures", side_effect=start_rendering), \
                 patch.object(outputs, "_paper", return_value=b"mock PDF"), \
                 patch.object(Path, "read_bytes", versioned_read):
                outputs.export_study("unused synthetic workspace", destination)
            self.assertEqual(reads, {name: 1 for name in names})
            for name in names:
                self.assertEqual((destination / "source" / name).read_bytes(), expected[name])


if __name__ == "__main__":
    unittest.main()
