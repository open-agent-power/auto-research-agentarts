"""Three bounded continuation checks; constructed providers, original core actions and HTTP."""

import copy
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import test_local_evidence as evidence_fixtures
import test_local_workbench as fixtures
import test_local_workbench_http as http_fixtures
import test_host_model_batch as host_fixtures
import test_recipe_improvement_adapter as recipe_fixtures
from autoresearch import recipe_improvement_adapter as adapter, tabular_quality_adapter as tabular, grouped_quality_adapter as grouped
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_plan_proposal import build_context


class SimulatedCrash(BaseException):
    pass


class LocalWorkbenchContinuationTests(unittest.TestCase):
    serve = http_fixtures.LocalWorkbenchHTTPTests.serve
    request = http_fixtures.LocalWorkbenchHTTPTests.request
    session = http_fixtures.LocalWorkbenchHTTPTests.session
    transport = host_fixtures.HostModelBatchTests.transport

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.number = 0
        self.contexts = []

    def fresh(self):
        self.number += 1
        self.manager = LocalWorkbench(self.root / ("workbench-" + str(self.number)))
        self.manager.create(fixtures.LocalWorkbenchTests.create_body(self))
        self.project, _ = self.manager.binding()
        return self.project

    @staticmethod
    def plan():
        return {"question": "What do the saved constructed readings support?", "basis": "Tiny engineering fixture only.",
                "steps": "Check recorded quality, then the declared groups and source; keep interpretation unverified.",
                "expected_feedback": "Obtain the original quality and grouped observations."}

    def body(self, request_id, *, plan_mode="reuse", execution_mode="rules", maximum=2, methods=None, receipts=None):
        state = self.project.status()
        return {"request_id": request_id, "project_id": state["id"], "expected_state_version": state["state_version"],
                "plan_mode": plan_mode, "execution_mode": execution_mode, "max_actions": maximum,
                "allowed_methods": methods if methods is not None else [tabular.TOOL_ID, grouped.TOOL_ID],
                "source_receipt_sha256s": receipts or [], "reason": "Explicit constructed-fixture continuation, without expanding any grant."}

    def answer(self, journal, request_id):
        feedback = build_context(self.project)["feedback"]
        arguments = {"plan": self.plan(), "reason": "Use the saved fixture feedback before interpreting the next result.",
                     "feedback_action_ids": [feedback[0]["action_id"]] if feedback else [],
                     "expected_improvement": "Keep this engineering sequence tied to actual saved observations."}
        response = self.root / (request_id + ".json")
        response.write_bytes(canonical(arguments).encode("utf-8"))
        journal.import_response(request_id=request_id, response_file=response)

    def seed_grant(self, limit=3):
        journal = HostModelSelection(self.project.root)
        journal.prepare(request_id="seed-plan", provider="delegated", purpose="plan",
            expected_state_version=self.project.status()["state_version"], decision_limit=limit, cli_budget_usd=.1,
            reason="Original prospective fixture grant; continuation cannot replace it.")
        self.answer(journal, "seed-plan")
        journal.consume(request_id="seed-plan")
        journal.adopt_plan(request_id="seed-plan")
        return journal

    def assert_code(self, code, callback, *args):
        with self.assertRaises(ResearchError) as caught:
            callback(*args)
        self.assertEqual(caught.exception.code, code)

    def adopted_recipe(self):
        fixture = recipe_fixtures.RecipeImprovementAdapterTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        self.manager, self.project = fixture.manager, fixture.project
        receipt = self.manager.register_evidence(evidence_fixtures.LocalEvidenceTests.body(self))["registration"]["receipt_snapshot_sha256"]
        trace = build_context(self.project)
        candidate = copy.deepcopy(fixture.original)
        candidate["version"] += 1
        candidate["ordered_methods"] = [{key: item[key] for key in ("method_id", "evaluation_ref")}
            for method in ("research.source-selection", grouped.TOOL_ID)
            for item in trace["selection_context"]["conditions"] if item["method_id"] == method]
        options = {**fixture.options, "decision_limit": 2}
        adapter.propose_recipe_change(fixture.original, trace, fixture.goal, **options)
        arguments = {"candidate": candidate, "reason": "Read the declared source before the remaining group profile.",
            "feedback_action_ids": [self.project.status()["actions"][0]["id"]],
            "expected_improvement": "Keep the available group profile after source reading.",
            "validation_plan": "Check the exact saved source receipt and original predecessor."}
        response = self.root / "recipe-response.json"
        response.write_bytes(canonical(arguments).encode("utf-8"))
        proposed = adapter.propose_recipe_change(fixture.original, trace, fixture.goal, response_file=response, **options)
        validation = adapter.validate_recipe_change(proposed["candidate"], fixture.original, fixture.goal,
            workspace=self.project.root, request_id=options["request_id"], allowed_methods=["research.source-selection"], allowed_receipts=[receipt])
        round_input = {"schema_version": "recipe-improvement-input-v1", "round_id": "fixture-adopted-round",
            "request_id": options["request_id"], "evidence_kind": "saved_host_validation", "current_recipe": fixture.original,
            "trace": trace, "goal": fixture.goal,
            "issue": {"summary": "Keep the follow-up after checking the actual source.", "feedback_action_ids": arguments["feedback_action_ids"]},
            "acceptance": candidate["ordered_methods"][0], "proposal_result": proposed, "validation_result": validation,
            "previous_round": None, "next_question": "Use the effective version for the remaining grouped observation."}
        revision = self.project.apply_recipe_round(request_id="fixture-effective-recipe",
            expected_state_version=self.project.status()["state_version"], round_input=round_input, reason="Explicitly keep this constructed v2.")
        self.assertEqual((revision["decision"], revision["recipe"]["version"]), ("keep", 2))

    def test_linked_plan_adoption_then_original_batch_uses_effective_recipe(self):
        self.adopted_recipe()
        before = self.project.status()
        body = self.body("continue-adopted-v2", plan_mode="suggest", maximum=1, methods=[grouped.TOOL_ID])
        journal = HostModelSelection(self.project.root)
        with patch("autoresearch.host_model_selection.run_claude_selection") as model:
            prepared = self.manager.continue_research(body)
            self.assertEqual((prepared["phase"], prepared["status"], prepared["record_status"]), ("plan", "waiting", "incomplete"))
            plan_id = prepared["plan_ref"]["request_id"]
            self.assertEqual(journal.status(request_id=plan_id)["provider"], "delegated")
            self.assertEqual(self.project.status(), before)
            self.assert_code("OPERATION_INCOMPLETE", self.manager.save_plan,
                {"request_id": "unrelated-plan", "project_id": before["id"], "expected_state_version": before["state_version"],
                 "plan": self.plan(), "reason": "Must not bypass the linked plan gate."})
            self.answer(journal, plan_id)
            resumed = self.manager.model_resume({"project_id": before["id"], "request_id": plan_id}, executable=None)
            self.assertEqual(resumed["status"], "proposed")
            awaiting = self.manager.continue_research(body)
            self.assertEqual((awaiting["phase"], awaiting["stop"]["code"]), ("awaiting_adoption", "PLAN_ADOPTION_REQUIRED"))
            self.assert_code("OPERATION_INCOMPLETE", self.manager.model_plan_adopt,
                             {"project_id": before["id"], "request_id": "unrelated-model"})
            snapshot = os.environ.get("AUTORESEARCH_CONTINUATION_FIXTURE")
            if snapshot:
                shutil.copytree(self.manager.root, Path(snapshot))
            adopted = self.manager.model_plan_adopt({"project_id": before["id"], "request_id": plan_id})
            self.assertEqual(adopted["status"], "applied")
            with patch.object(grouped, "execute", wraps=grouped.execute) as followup:
                result = self.manager.continue_research(body)
                final = self.project.status()
                self.assertEqual((result["phase"], result["record_status"], result["batch_ref"]["kind"]), ("stopped", "completed", "local"))
                self.assertEqual((len(final["actions"]), final["budget"]["local_tool_calls_used"]), (2, 2))
                parent = final["controller_requests"][-1]
                self.assertEqual((parent["effective_recipe_revision"], parent["request"]["recipe_decision"]["recipe_version"]), (1, 2))
                self.assertEqual(parent["request"]["command"], "controller.advance_recipe")
                self.assertEqual(result["steps"][-1]["controller_request_id"], parent["request_id"])
                self.assertEqual(result["steps"][-1]["child_request_id"], parent["child_request_id"])
                self.assertEqual(result["plan_ref"]["plan_version"], final["plan_revisions"][-1]["version"])
                db_bytes = self.project.db.read_bytes()
                self.assertEqual(self.manager.continue_research(body), result)
                self.assertEqual(self.manager.continuation_record(body["request_id"]), result)
                self.assertEqual(self.manager.describe()["continuations"][0], result)
                self.assertEqual(self.project.db.read_bytes(), db_bytes)
                followup.assert_called_once()
            self.assertEqual(journal.status()["usage"]["decision_slots_used"], 2)
            self.assertEqual(final["budget"]["local_tool_call_limit"], before["budget"]["local_tool_call_limit"])
            self.assertEqual((final["budget"]["new_model_requests"], final["budget"]["new_fits"]), (0, 0))
            model.assert_not_called()

    def test_committed_child_and_unknown_recover_only_original_request(self):
        self.fresh()
        self.project.save_plan(request_id="initial-plan", expected_state_version=0, plan=self.plan(), reason="Original fixture route.")
        body = self.body("continue-committed")
        advance = ProjectController.advance

        def interrupt_after_core(controller, **kwargs):
            advance(controller, **kwargs)
            raise SimulatedCrash()

        with patch.object(tabular, "execute", wraps=tabular.execute) as primary:
            with patch.object(ProjectController, "advance", interrupt_after_core), self.assertRaises(SimulatedCrash):
                self.manager.continue_research(body)
            committed = self.project.status()
            original = committed["controller_requests"][0]["request_id"]
            self.assert_code("OPERATION_INCOMPLETE", self.manager.continue_research, {**body, "request_id": "replacement-not-allowed"})
            recovered = LocalWorkbench(self.manager.root).continue_research(body)
            self.assertEqual((recovered["record_status"], recovered["steps"][1]["controller_request_id"]), ("completed", original))
            self.assertEqual(len(self.project.status()["actions"]), 2)
            primary.assert_called_once()
            self.assert_code("IDEMPOTENCY_CONFLICT", self.manager.continue_research, {**body, "reason": "Changed original authorization"})

        self.fresh()
        self.project.save_plan(request_id="initial-plan", expected_state_version=0, plan=self.plan(), reason="Original fixture route.")
        body = self.body("continue-unknown")
        with patch.object(tabular, "execute", wraps=tabular.execute) as primary:
            with patch("autoresearch.research_project.write_once", side_effect=OSError("Constructed missing result artifact")):
                unknown = self.manager.continue_research(body)
            self.assertEqual((unknown["status"], unknown["record_status"], unknown["stop"]["code"]), ("needs_review", "incomplete", "BATCH_INTERRUPTED"))
            child_id = unknown["steps"][-1]["child_request_id"]
            self.project.resume(request_id=child_id)
            before = self.project.status()
            with patch.object(ProjectController, "advance", side_effect=AssertionError("Unknown cannot dispatch again")):
                repeated = self.manager.continue_research(body)
            self.assertEqual(repeated["steps"][-1]["child_request_id"], child_id)
            self.assertEqual(repeated["stop"]["code"], "EXECUTION_UNKNOWN")
            self.assertTrue(repeated["stop"]["resume_allowed"])
            self.assertEqual(self.project.status(), before)
            self.assertEqual(before["budget"]["local_tool_calls_reserved"], 1)
            primary.assert_called_once()

    def test_http_scopes_original_host_grant_and_fixed_model_batch(self):
        self.fresh()
        self.project.save_plan(request_id="operator-plan", expected_state_version=0, plan=self.plan(), reason="Saved route.")
        server = self.serve(local_workspace=self.manager, allow_local_actions=True)
        headers = self.session(server)
        body = self.body("no-existing-grant", plan_mode="suggest")
        before = self.project.status()
        self.assertEqual(self.request(server, "/api/local-workbench/continue", "POST", body, {**headers, "Origin": "http://external.invalid"})[0], 403)
        status, stopped = self.request(server, "/api/local-workbench/continue", "POST", body, headers)
        self.assertEqual((status, stopped["stop"]["code"]), (200, "HOST_GRANT_REQUIRED"))
        self.assertEqual(self.project.status(), before)
        self.assertIsNone(HostModelSelection(self.project.root).status()["grant"])
        manager_bytes = self.manager.db.read_bytes()
        self.assertEqual(self.request(server, "/api/local-workbench/continue/no-existing-grant.json"), (200, stopped))
        self.assertEqual(self.request(server, "/api/local-workbench/continue/no-existing-grant.json?replace=1")[0], 400)
        self.assertEqual(self.manager.db.read_bytes(), manager_bytes)
        disabled = self.serve(local_workspace=self.manager)
        self.assertEqual(self.request(disabled, "/api/local-workbench/continue", "POST", body, self.session(disabled))[0], 405)
        journal = self.seed_grant(2)
        disabled_model = self.manager.continue_research(self.body("model-disabled", execution_mode="model", maximum=1))
        self.assertEqual(disabled_model["stop"]["code"], "MODEL_DISABLED")
        self.assertEqual(journal.status()["usage"]["decision_slots_used"], 1)

        self.fresh()
        ProjectController(self.project.root).advance(request_id="fixture-quality")
        receipt = self.manager.register_evidence(evidence_fixtures.LocalEvidenceTests.body(self))["registration"]["receipt_snapshot_sha256"]
        journal = self.seed_grant(3)
        original_grant = journal.status()["grant"]
        methods = [item["method_id"] for item in ProjectController(self.project.root).selection_context()["conditions"]]
        server = self.serve(local_workspace=self.manager, allow_local_actions=True, claude_executable=Path(__file__).absolute())
        headers = self.session(server)
        with patch("autoresearch.host_model_selection.run_claude_selection", side_effect=self.transport) as model:
            denied_body = self.body("outside-method", execution_mode="model", maximum=1, methods=[grouped.TOOL_ID])
            denied = self.request(server, "/api/local-workbench/continue", "POST", denied_body, headers)[1]
            self.assertEqual(denied["stop"]["code"], "NOT_AUTHORIZED")
            no_receipt = self.body("outside-receipt", execution_mode="model", maximum=1, methods=methods)
            denied = self.request(server, "/api/local-workbench/continue", "POST", no_receipt, headers)[1]
            self.assertEqual(denied["stop"]["code"], "NOT_AUTHORIZED")
            model.assert_not_called()
            self.assertEqual(journal.status()["usage"]["decision_slots_used"], 1)
            body = self.body("original-host-batch", execution_mode="model", maximum=2, methods=methods, receipts=[receipt])
            status, result = self.request(server, "/api/local-workbench/continue", "POST", body, headers)
            self.assertEqual((status, result["batch_ref"]["kind"], result["record_status"]), (200, "host", "completed"))
            self.assertEqual(len(result["steps"]), 3)
            self.assertEqual(model.call_count, 2)
            self.assertEqual(self.request(server, "/api/local-workbench/continue", "POST", body, headers), (200, result))
            self.assertEqual(model.call_count, 2)
            self.assertEqual(self.request(server, "/api/local-workbench/continue/original-host-batch.json"), (200, result))
            exhausted = self.request(server, "/api/local-workbench/continue", "POST", self.body("spent-grant", plan_mode="suggest"), headers)[1]
            self.assertEqual(exhausted["stop"]["code"], "HOST_DECISION_LIMIT")
            self.assertEqual(journal.status()["grant"], original_grant)
            self.assertEqual(journal.status()["usage"]["decision_slots_used"], 3)
            self.assertEqual(model.call_count, 2)
        state = self.project.status()
        self.assertEqual((state["budget"]["local_tool_calls_used"], state["budget"]["evidence_reads_used"]), (2, 1))
        self.assertEqual((state["budget"]["new_model_requests"], state["budget"]["new_fits"]), (0, 0))


if __name__ == "__main__":
    unittest.main()
