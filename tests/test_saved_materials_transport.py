"""Saved-material entrypoint wiring and replay; no fitting or provider execution."""
from contextlib import redirect_stderr, redirect_stdout
import copy
import http.client
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from test_saved_materials import saved_project
from autoresearch import recipe_change_proposal as recipe_protocol
from autoresearch import recipe_improvement_adapter as adapter
from autoresearch import research_plan_proposal as plan_protocol
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.project_workbench import create_project_server


class Output(io.StringIO):
    def reconfigure(self, **kwargs):
        pass


class SavedMaterialsTransportTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.manager, self.project, request = saved_project(self.root)
        self.journal = HostModelSelection(self.project.root)
        self.selectors = [request]
        self.base = plan_protocol.build_context(self.project)
        self.prompt = plan_protocol.build_prompt(self.base)
        self.supplied = plan_protocol.build_context(self.project, saved_materials=self.selectors)
        self.cli = runpy.run_path(str(Path(__file__).parents[1] / "scripts/run_host_selection.py"))
        self.enterContext(patch("sklearn.linear_model.Ridge.fit", side_effect=AssertionError("No fit in transport tests")))
        self.enterContext(patch("sklearn.preprocessing.StandardScaler.fit", side_effect=AssertionError("No fit in transport tests")))
        self.dispatch = self.enterContext(patch("autoresearch.host_model_selection.run_claude_selection",
                                                side_effect=AssertionError("No provider execution in transport tests")))

    @staticmethod
    def files(root):
        return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def specification(self, **overrides):
        return {"request_id": "saved-plan", "provider": "delegated", "purpose": "plan",
                "expected_state_version": self.project.status()["state_version"], "decision_limit": 1,
                "cli_budget_usd": 0.1, "reason": "Constructed zero-fit transport validation", **overrides}

    def assert_code(self, code, callback, *args, **kwargs):
        with self.assertRaises(ResearchError) as caught:
            callback(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def invoke(self, args):
        output = Output()
        with patch.object(sys, "argv", ["run_host_selection.py", *map(str, args)]), redirect_stdout(output):
            result = self.cli["main"]()
        return result, json.loads(output.getvalue())

    def test_default_and_empty_keep_original_context_prompt_and_specification_bytes(self):
        with patch("autoresearch.saved_materials.materialize", side_effect=AssertionError("No implicit material reads")):
            record = self.journal.prepare(**self.specification())
            self.assertEqual(self.journal.prepare(**self.specification(saved_materials=[])), record)
        self.assertNotIn("saved_materials", record["prepare_specification"])
        self.assertEqual(canonical(record["context"]), canonical(self.base))
        self.assertEqual(canonical(record["prompt"]), canonical(self.prompt))
        folder = self.journal.directory / record["directory"]
        self.assertEqual((folder / "context.json").read_bytes(), canonical(self.base).encode("utf-8"))
        self.assertEqual((folder / "prompt.json").read_bytes(), canonical(self.prompt).encode("utf-8"))

    def test_same_id_replays_before_builder_after_project_changes_and_selectors_conflict(self):
        specification = self.specification(saved_materials=copy.deepcopy(self.selectors))
        with patch.object(plan_protocol, "build_context", wraps=plan_protocol.build_context) as builder:
            record = self.journal.prepare(**specification)
            builder.assert_called_once_with(self.journal.project, saved_materials=self.selectors)
        self.assertEqual(record["context"], self.supplied)
        self.assertIn(canonical(self.supplied), record["prompt"]["prompt"])
        specification["saved_materials"][0]["fields"].append("folds")
        self.assertEqual(record["prepare_specification"]["saved_materials"], self.selectors)
        specification["saved_materials"] = copy.deepcopy(self.selectors)
        response = self.root / "invalid-fixture-response.json"
        response.write_bytes(b"{}")
        record = self.journal.import_response(request_id=record["request_id"], response_file=response)
        self.project.save_plan(request_id="later-plan", expected_state_version=self.project.status()["state_version"],
            plan={"question": "Later fixture question", "basis": "Constructed feedback", "steps": "Wait for source details.",
                  "expected_feedback": "Source definitions"}, reason="A changed project must not rebuild the original Host input.")
        with self.project._connect() as con:
            current = self.project._project(con)
            binding = copy.deepcopy(current["design_revisions"][-1])
            binding["version"] = 2
            binding["resource"].update(version=2, parent_version=1)
            current["design_revisions"].append(binding)
            current["state_version"] += 1
            self.project._save(con, current)
        with patch.object(plan_protocol, "build_context", side_effect=AssertionError("Replay must not rebuild")), \
                patch.object(self.journal.project, "_artifact", side_effect=AssertionError("Replay must not read artifacts")):
            self.assertEqual(self.journal.prepare(**specification), record)
            for replacement in ({**self.selectors[0], "fields": ["folds"]},
                                {**self.selectors[0], "result_sha256": "b" * 64}):
                self.assert_code("IDEMPOTENCY_CONFLICT", self.journal.prepare,
                                 **{**specification, "saved_materials": [replacement]})
        self.dispatch.assert_not_called()

    def test_freshness_uses_frozen_selectors_for_plan_and_recipe(self):
        for purpose in ("plan", "recipe"):
            specification = {"saved_materials": copy.deepcopy(self.selectors)}
            context, protocol = self.supplied, plan_protocol
            if purpose == "recipe":
                specification.update(current_recipe={"id": "frozen-recipe"}, improvement_goal="Frozen goal")
                context, protocol = {"research_context": self.supplied}, recipe_protocol
            record = {"purpose": purpose, "prepare_specification": specification, "context": context}
            with patch.object(protocol, "build_context", return_value=context) as builder:
                self.journal._fresh(record)
                self.assertEqual(builder.call_args.kwargs, {"saved_materials": self.selectors})
                if purpose == "recipe":
                    self.assertEqual(builder.call_args.args[1:], (specification["current_recipe"], "Frozen goal"))

    def test_invalid_identity_and_complete_oversize_create_no_grant_request_or_dispatch(self):
        for outcome in ("identity", "oversize", "selector"):
            with self.subTest(outcome=outcome):
                before = self.project.status()
                selectors = copy.deepcopy(self.selectors)
                if outcome == "selector":
                    selectors[0]["fields"] = ["arbitrary.path"]
                kwargs = ({"side_effect": ResearchError("EVIDENCE_CHANGED", "Wrong saved producer identity")}
                          if outcome == "identity" else {"return_value": [{"complete": "x" * 70000}]})
                with patch("autoresearch.saved_materials.materialize", **kwargs):
                    self.assert_code("EVIDENCE_CHANGED" if outcome == "identity" else "INVALID_PLAN_CONTEXT"
                                     if outcome == "oversize" else "INVALID_SAVED_MATERIALS", self.journal.prepare,
                                     **self.specification(provider="claude_cli", executable=__file__, saved_materials=selectors))
                self.assertEqual(self.project.status(), before)
                self.assertEqual(self.journal._load()["requests"], {})
                self.assertIsNone(self.journal._load()["grant"])
                self.assertFalse(self.journal.state_file.exists())
                self.assertEqual(list(self.journal.directory.glob("requests/**/*")), [])
        self.dispatch.assert_not_called()

    def test_exhausted_host_limit_does_not_build_material_or_expand_grant(self):
        self.journal.prepare(**self.specification())
        before = self.files(self.journal.directory)
        with patch.object(plan_protocol, "build_context", side_effect=AssertionError("No read after exhausted quota")):
            self.assert_code("HOST_DECISION_LIMIT", self.journal.prepare,
                             **self.specification(request_id="new-plan", saved_materials=self.selectors))
            self.assert_code("HOST_GRANT_CHANGED", self.journal.prepare,
                             **self.specification(request_id="new-plan", decision_limit=2, saved_materials=self.selectors))
        self.assertEqual(self.files(self.journal.directory), before)

    def test_cli_prepare_and_advance_forward_strict_selector_file(self):
        path = self.root / "selectors.json"
        path.write_text(canonical(self.selectors), encoding="utf-8")
        arguments = ["--workspace", self.project.root, "--request-id", "cli-plan", "--purpose", "plan",
                     "--expected-state-version", 0, "--decision-limit", 1, "--cli-budget-usd", 0.1,
                     "--reason", "Constructed CLI transport test", "--saved-materials", path]
        for command in ("prepare", "advance"):
            with patch.object(HostModelSelection, "prepare", return_value={"status": "prepared"}) as prepare, \
                    patch.object(HostModelSelection, "request", return_value={"status": "prepared"}) as request:
                options = (["--provider", "delegated"] if command == "prepare" else ["--claude-executable", __file__])
                self.assertEqual(self.invoke([command, *arguments, *options])[0], 0)
                self.assertEqual(prepare.call_args.kwargs["saved_materials"], self.selectors)
                self.assertEqual(request.call_count, command == "advance")
        path.write_text('[{"action_id":"x","action_id":"y"}]', encoding="utf-8")
        with patch.object(HostModelSelection, "prepare") as prepare:
            self.assertEqual(self.invoke(["prepare", *arguments, "--provider", "delegated"])[0], 2)
            prepare.assert_not_called()

    def test_cli_preview_exports_original_bytes_and_refuses_overwrite_without_host_preparation(self):
        before, output = self.files(self.project.root), self.root / "preview"
        args = ["preview", "--workspace", self.project.root, "--purpose", "plan", "--output", output]
        with patch.object(HostModelSelection, "prepare", side_effect=AssertionError("Preview must not prepare")), \
                patch.object(HostModelSelection, "_writer", side_effect=AssertionError("Preview must not lock/write Host")):
            code, manifest = self.invoke(args)
            self.assertEqual(code, 0)
            self.assertFalse(manifest["host_request_prepared"])
            self.assertEqual((output / "context.json").read_bytes(), canonical(self.base).encode("utf-8"))
            self.assertEqual((output / "prompt.json").read_bytes(), canonical(self.prompt).encode("utf-8"))
            original = self.files(output)
            self.assertEqual(self.invoke(args)[0], 2)
            self.assertEqual(self.files(output), original)
            selectors = self.root / "preview-selectors.json"
            selectors.write_text(canonical(self.selectors), encoding="utf-8")
            selected_output = self.root / "selected-preview"
            self.assertEqual(self.invoke([*args[:-1], selected_output, "--saved-materials", selectors])[0], 0)
            self.assertEqual((selected_output / "context.json").read_bytes(), canonical(self.supplied).encode("utf-8"))
            self.assertEqual((selected_output / "prompt.json").read_bytes(), canonical(plan_protocol.build_prompt(self.supplied)).encode("utf-8"))
        self.assertEqual(self.files(self.project.root), before)
        self.assertFalse(self.journal.directory.exists())

    def test_cli_rejects_injected_wrapper_members_before_prepare_or_builder(self):
        path = self.root / "non-json-selectors.json"
        path.write_text('[],"ignored":true', encoding="utf-8")
        before = self.files(self.project.root)
        with patch.object(HostModelSelection, "prepare") as prepare, \
                patch.object(plan_protocol, "build_context") as builder:
            code, result = self.invoke(["prepare", "--workspace", self.project.root, "--request-id", "bad-json",
                "--provider", "delegated", "--purpose", "plan", "--expected-state-version", 3,
                "--decision-limit", 1, "--cli-budget-usd", 0.1, "--reason", "Reject invalid JSON before preparation",
                "--saved-materials", path])
            self.assertEqual((code, result["code"]), (2, "INVALID_REQUEST"))
            prepare.assert_not_called()
            builder.assert_not_called()
        self.assertEqual(self.files(self.project.root), before)
        self.assertFalse(self.journal.directory.exists())

    def test_cli_recipe_preview_and_selection_exclusions(self):
        recipe_path = Path(__file__).parents[1] / "examples/research-recipes/tabular-group-first.json"
        selectors = self.root / "recipe-selectors.json"
        selectors.write_text(canonical(self.selectors), encoding="utf-8")
        output, goal = self.root / "recipe-preview", "Review complete saved group errors"
        before = self.files(self.project.root)
        self.assertEqual(self.invoke(["preview", "--workspace", self.project.root, "--purpose", "recipe",
            "--current-recipe", recipe_path, "--improvement-goal", goal, "--saved-materials", selectors,
            "--output", output])[0], 0)
        context = json.loads((output / "context.json").read_bytes())
        self.assertEqual(context["research_context"], self.supplied)
        self.assertEqual(context["improvement_goal"], goal)
        self.assertEqual((output / "prompt.json").read_bytes(), canonical(recipe_protocol.build_prompt(context)).encode("utf-8"))
        args = ["--workspace", self.project.root, "--request-id", "selection", "--expected-state-version", 3,
                "--decision-limit", 1, "--cli-budget-usd", 0.1, "--reason", "Scope exclusion test",
                "--saved-materials", selectors]
        with patch.object(HostModelSelection, "prepare") as prepare:
            self.assertEqual(self.invoke(["prepare", "--provider", "delegated", *args])[0], 2)
            prepare.assert_not_called()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            self.invoke(["advance-batch", "--max-decisions", 1, *args])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(self.files(self.project.root), before)

    def test_plan_body_forwards_selectors_and_other_commands_reject_them(self):
        body = {"request_id": "http-plan", "project_id": self.project.status()["id"],
                "expected_state_version": self.project.status()["state_version"], "decision_limit": 1, "cli_budget_usd": 0.1,
                "reason": "Constructed plan body transport", "saved_materials": self.selectors}
        with patch.object(HostModelSelection, "request", side_effect=lambda *, request_id: self.journal.status(request_id=request_id)) as request:
            result = self.manager.model_plan_advance(body, executable=__file__)
            self.assertEqual(result["command"], "model-plan-advance")
            self.assertEqual(result["model_record"]["prepare_specification"]["saved_materials"], self.selectors)
            self.assertEqual(result["model_record"]["context"], self.supplied)
            request.assert_called_once_with(request_id="http-plan")
        self.assert_code("INVALID_REQUEST", self.manager.model_advance, body, executable=__file__)
        self.assert_code("INVALID_REQUEST", self.manager.model_resume,
                         {"request_id": "http-plan", "project_id": body["project_id"], "saved_materials": []}, executable=__file__)

    def serve(self):
        server = create_project_server(local_workspace=self.manager, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def close():
            server.shutdown()
            server.server_close()
            thread.join(2)
        self.addCleanup(close)
        return server

    def get(self, server, query=""):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        self.addCleanup(connection.close)
        connection.request("GET", "/api/project/plan-context.json" + ("?" + query if query else ""))
        response = connection.getresponse()
        return response.status, json.loads(response.read())

    def test_get_preview_is_readonly_returns_context_and_checks_exact_snapshot_query(self):
        server, before = self.serve(), self.files(self.project.root)
        self.assertEqual(self.get(server), (200, self.base))
        query = urlencode({"saved_materials": canonical(self.selectors), "snapshot_ref": self.project.status()["snapshot_ref"]})
        with patch("autoresearch.project_workbench.build_plan_context", wraps=plan_protocol.build_context) as builder, \
                patch.object(HostModelSelection, "prepare", side_effect=AssertionError("GET must not prepare")), \
                patch.object(HostModelSelection, "_writer", side_effect=AssertionError("GET must not write Host")):
            self.assertEqual(self.get(server, query), (200, self.supplied))
            self.assertEqual(builder.call_args.kwargs, {"saved_materials": self.selectors})
            for invalid in ("saved_materials=", "saved_materials=%5B%5D&saved_materials=%5B%5D", "unexpected=x", "snapshot_ref=bad"):
                self.assertEqual(self.get(server, invalid)[0], 400)
            self.assertEqual(self.get(server, "snapshot_ref=" + "0" * 64)[0], 409)
        for code, status in (("EVIDENCE_CHANGED", 409), ("INVALID_PLAN_CONTEXT", 400)):
            with patch("autoresearch.project_workbench.build_plan_context", side_effect=ResearchError(code, "Complete context rejected")):
                self.assertEqual(self.get(server, query)[0], status)
        self.assertEqual(self.files(self.project.root), before)
        self.assertFalse(self.journal.directory.exists())

    def test_recipe_adapter_new_request_and_old_id_keep_same_selectors(self):
        recipe = json.loads((Path(__file__).parents[1] / "examples/research-recipes/tabular-group-first.json").read_text(encoding="utf-8"))
        context = recipe_protocol.build_context(self.project, recipe, "Use the explicitly supplied complete saved groups",
                                                saved_materials=self.selectors)
        options = {"workspace": self.project.root, "request_id": "recipe-materials", "decision_limit": 1,
                   "cli_budget_usd": 0.1, "reason": "Constructed recipe adapter wiring"}
        with patch.object(recipe_protocol, "build_context", wraps=recipe_protocol.build_context) as builder:
            prepared = adapter.propose_recipe_change(recipe, self.supplied, context["improvement_goal"],
                                                    saved_materials=self.selectors, **options)
            self.assertEqual(prepared["status"], "prepared")
            self.assertEqual(builder.call_count, 2)
            self.assertTrue(all(call.kwargs == {"saved_materials": self.selectors} for call in builder.call_args_list))
        with patch.object(recipe_protocol, "build_context", side_effect=AssertionError("Old adapter request must not rebuild")):
            self.assertEqual(adapter.propose_recipe_change(recipe, self.supplied, context["improvement_goal"], **options), prepared)
            self.assert_code("IDEMPOTENCY_CONFLICT", adapter.propose_recipe_change, recipe, self.supplied,
                             context["improvement_goal"], saved_materials=[], **options)
        self.assertEqual(self.journal.status(request_id="recipe-materials")["prepare_specification"]["saved_materials"], self.selectors)

    def test_get_rejects_injected_wrapper_members_before_builder_without_writes(self):
        server, before = self.serve(), self.files(self.project.root)
        query = urlencode({"saved_materials": '[],"ignored":true'})
        with patch("autoresearch.project_workbench.build_plan_context") as builder, \
                patch.object(HostModelSelection, "prepare") as prepare:
            status, result = self.get(server, query)
            self.assertEqual((status, result["code"]), (400, "INVALID_QUERY"))
            builder.assert_not_called()
            prepare.assert_not_called()
        self.assertEqual(self.files(self.project.root), before)
        self.assertFalse(self.journal.directory.exists())


if __name__ == "__main__":
    unittest.main()
