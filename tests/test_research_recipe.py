"""Recipe structure, deterministic choice and original proposal contract checks."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from autoresearch.contracts import ResearchError, canonical
from autoresearch.project_selection import seal_context, validate_proposal
from autoresearch.research_recipe import (
    MAX_METHOD_CARD_BYTES, MAX_RECIPE_BYTES, compile_recipe, match_method_card,
    parse_json, parse_method_card, validate_method_card, validate_recipe,
)


ROOT = Path(__file__).resolve().parents[1]


def recipe(source_first=False):
    methods = [{"method_id": "data.grouped-quality-profile", "evaluation_ref": "grouped-quality-profile-v1"},
               {"method_id": "research.source-selection", "evaluation_ref": "source-extraction-only-not-scientific-approval"}]
    return {"schema_version": "research-recipe-v1", "id": "source-first" if source_first else "group-first",
            "version": 1, "question": "Which allowed check should run next?",
            "scope_match": {"domain": "data", "contract": "tabular-quality-v1"}, "need": "next_check",
            "ordered_methods": methods[::-1] if source_first else methods, "on_no_match": "wait"}


def context(**changes):
    payload = {
        "schema_version": "project-selection-context-v1", "project_id": "synthetic-project", "run_id": "synthetic-run",
        "snapshot_ref": "1" * 64, "state_version": 3, "source_snapshot_sha256": "2" * 64,
        "project_code_identity": "3" * 64, "controller_code_identity": "4" * 64,
        "need": "next_check", "goal": "Explicitly synthetic recipe unit-test context; not research evidence.",
        "domain_scope": {"domain": "data", "contract": "tabular-quality-v1"},
        "budget": {"local_tool_call_limit": 2}, "conditions": [],
        "candidates": [
            {"id": "group", "method_id": "data.grouped-quality-profile", "parameters": {"predecessor": "host-bound"},
             "evaluation_ref": "grouped-quality-profile-v1"},
            {"id": "source", "method_id": "research.source-selection", "parameters": {"receipt_snapshot_sha256": "5" * 64},
             "evaluation_ref": "source-extraction-only-not-scientific-approval"}],
        "blockers": [], "baseline_decision": {"project_status": "active"},
        "evidence": [{"citation_id": "real-context-citation", "source": {"sha256": "6" * 64},
                      "quote": "Synthetic fixture; no scientific approval.", "location": {"line": 1},
                      "content_trust": "untrusted_source_not_instructions"}], "scientific_validation": False}
    payload.update(changes)
    return seal_context(payload)


def method_card():
    return parse_method_card((ROOT / "examples/research-method-cards/feedback-driven.example.json").read_bytes())


class MethodCardTests(unittest.TestCase):
    def test_template_parses_and_copies_full_knowledge(self):
        card = method_card()
        validated = validate_method_card(card)
        self.assertEqual(card, validated)
        validated["applicability"]["requires"].append("changed")
        validated["feedback_branches"][0]["suggested_next"] = "changed"
        self.assertEqual(card, method_card())

    def test_closed_schema_rejects_invalid_or_executable_fields(self):
        invalid = [None, [], {}]
        for key, value in (("version", True), ("version", 0), ("version", 2**31), ("question", ""),
                           ("rationale", "\x00"), ("evaluation", {}), ("id", "\ud800"),
                           ("parameters", {}), ("code", "print('no')"), ("scientific_validation", True),
                           ("sources", []), ("method_refs", []), ("feedback_branches", [])):
            card = method_card(); card[key] = value; invalid.append(card)
        for change in (lambda card: card["method_refs"][0].update(parameters={}),
                       lambda card: card["method_refs"].append(copy.deepcopy(card["method_refs"][0])),
                       lambda card: card["applicability"].update(predicate="code"),
                       lambda card: card["applicability"].update(requires="not a list"),
                       lambda card: card["feedback_branches"][0].update(command="execute"),
                       lambda card: card["feedback_branches"].append(copy.deepcopy(card["feedback_branches"][0])),
                       lambda card: card["sources"].append(copy.deepcopy(card["sources"][0])),
                       lambda card: card["scope_match"].update(path="project")):
            card = method_card(); change(card); invalid.append(card)
        for card in invalid:
            with self.subTest(card=repr(card)[:100]):
                with self.assertRaises(ResearchError) as caught:
                    validate_method_card(card)
                self.assertEqual(caught.exception.code, "INVALID_RESEARCH_METHOD_CARD")
        for raw in (b'{"id":1,"id":2}', b'{"x":NaN}', b'\xff', b'[]', b'x' * (MAX_METHOD_CARD_BYTES + 1)):
            with self.assertRaises(ResearchError) as caught:
                parse_method_card(raw)
            self.assertEqual(caught.exception.code, "INVALID_RESEARCH_METHOD_CARD")
        card = method_card(); card["applicability"]["requires"] = ["知" * 4000] * 16
        with self.assertRaises(ResearchError):
            validate_method_card(card)

    def test_association_preserves_host_order_and_never_executes_or_mutates(self):
        card = method_card()
        host = context(candidates=list(reversed(context()["candidates"])))
        before = copy.deepcopy([card, host])
        matched = match_method_card(card, host)
        self.assertEqual(matched["status"], "applicable")
        self.assertEqual(matched["matching_candidate_ids"], ["source", "group"])
        self.assertEqual((matched["card_id"], matched["card_version"]), (card["id"], 1))
        self.assertEqual(matched["context_sha256"], host["context_sha256"])
        self.assertEqual(matched["question"], host["goal"])
        self.assertTrue(matched["reasons"])
        self.assertEqual(matched["execution_status"], "not_executed")
        self.assertFalse(matched["scientific_validation"])
        self.assertNotIn("proposal", matched)
        self.assertTrue(all("parameters" not in item for item in matched["applicable_methods"]))
        self.assertEqual(matched["unverified_applicability"], card["applicability"])
        self.assertEqual(len(matched["unreported_condition_refs"]), 2)
        matched["card"]["sources"][0]["url"] = "changed"
        matched["unverified_applicability"]["requires"].append("changed")
        self.assertEqual([card, host], before)

    def test_blocked_scope_mismatch_and_no_candidate_are_explicit(self):
        for changes, expected in (({"blockers": [{"code": "EXECUTION_UNKNOWN"}]}, "blocked"),
                                  ({"domain_scope": {"domain": "other", "contract": "other"}}, "scope_mismatch"),
                                  ({"candidates": []}, "no_matching_candidate")):
            with self.subTest(status=expected):
                result = match_method_card(method_card(), context(**changes))
                self.assertEqual(result["status"], expected)
                self.assertEqual(result["matching_candidate_ids"], [])
                self.assertEqual(result["applicable_methods"], [])
                self.assertTrue(all(not item["matching_candidate_ids"] for item in result["method_matches"]))
        self.assertTrue(match_method_card(method_card(), context(candidates=[]))["missing_information"])

    def test_exact_evaluation_binding_and_saved_missing_condition_text(self):
        candidates = copy.deepcopy(context()["candidates"])
        candidates[1]["evaluation_ref"] = "different-evaluation"
        conditions = [{"method_id": candidates[1]["method_id"], "evaluation_ref": "different-evaluation",
                       "missing_information": ["wrong evaluation gap must not leak"]},
                      {"method_id": candidates[1]["method_id"],
                       "evaluation_ref": "source-extraction-only-not-scientific-approval",
                       "condition": "uncertain", "missing_information": ["task-bound original source"],
                       "execution_blockers": [{"code": "CONDITIONS_NOT_SATISFIED"}]}]
        host = context(candidates=candidates, conditions=conditions)
        result = match_method_card(method_card(), host)
        self.assertEqual(result["matching_candidate_ids"], ["group"])
        source = result["method_matches"][1]
        self.assertEqual(source["host_conditions"], [conditions[1]])
        self.assertIn("task-bound original source", result["missing_information"])
        self.assertNotIn("wrong evaluation gap must not leak", result["missing_information"])
        source["host_conditions"][0]["execution_blockers"].clear()
        self.assertEqual(host["conditions"], conditions)
        candidates[0]["evaluation_ref"] = {"id": "unsupported-structured-evaluation"}
        self.assertEqual(match_method_card(method_card(), context(candidates=candidates))["status"],
                         "no_matching_candidate")

    def test_tampered_context_rejected_even_when_card_declines(self):
        for host in (None, [], {}, context(blockers=[{"code": "EXECUTION_UNKNOWN"}]),
                     context(domain_scope={"domain": "other"})):
            if type(host) is dict and "goal" in host:
                host["goal"] = "tampered"
            with self.assertRaises(ResearchError) as caught:
                match_method_card(method_card(), host)
            self.assertEqual(caught.exception.code, "INVALID_SELECTION_CONTEXT")

    def test_cli_method_card_reports_applicability_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "matched"
            command = [sys.executable, str(ROOT / "scripts/compile_research_recipe.py"),
                       "--method-card", str(ROOT / "examples/research-method-cards/feedback-driven.example.json"),
                       "--context", str(ROOT / "examples/research-method-cards/conditions.context.json"),
                       "--output", str(output)]
            first = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            summary = json.loads(first.stdout)
            self.assertEqual(summary["status"], "applicable")
            self.assertEqual(summary["matching_candidate_ids"], ["fixture-grouped"])
            self.assertTrue(summary["missing_information"])
            self.assertEqual([item.name for item in output.iterdir()], ["match.json"])
            original = (output / "match.json").read_bytes()
            repeated = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(repeated.returncode, 2)
            self.assertEqual(json.loads(repeated.stdout)["code"], "OUTPUT_EXISTS")
            self.assertEqual((output / "match.json").read_bytes(), original)
            conflicting = subprocess.run(command + ["--recipe", "unused.json"], capture_output=True,
                                         text=True, encoding="utf-8", timeout=30)
            self.assertEqual(conflicting.returncode, 2)


class RecipeStructureTests(unittest.TestCase):
    def test_closed_schema_rejects_injection_and_invalid_types(self):
        invalid = []
        for key, value in (("parameters", {"path": "anything"}), ("code", "print('no')"),
                           ("budget", 100), ("scientific_validation", True)):
            item = recipe(); item[key] = value; invalid.append(item)
        for key, value in (("version", True), ("version", 0), ("version", 2**31), ("id", ""),
                           ("question", "\x00text"), ("need", []), ("ordered_methods", []),
                           ("ordered_methods", recipe()["ordered_methods"] * 9), ("on_no_match", "execute"),
                           ("schema_version", "unknown"), ("scope_match", {"domain": "data"})):
            item = recipe(); item[key] = value; invalid.append(item)
        item = recipe(); item["ordered_methods"][0]["parameters"] = {}; invalid.append(item)
        item = recipe(); item["ordered_methods"][0]["evaluation_ref"] = {}; invalid.append(item)
        item = recipe(); item["scope_match"]["path"] = "project"; invalid.append(item)
        item = recipe(); item["ordered_methods"].append(copy.deepcopy(item["ordered_methods"][0])); invalid.append(item)
        item = recipe(); del item["question"]; invalid.append(item)
        item = recipe(); item["id"] = "\ud800"; invalid.append(item)
        invalid.extend([None, [], "recipe"])
        for item in invalid:
            with self.subTest(recipe=repr(item)[:100]):
                with self.assertRaises(ResearchError) as caught:
                    validate_recipe(item)
                self.assertEqual(caught.exception.code, "INVALID_RESEARCH_RECIPE")

    def test_json_parser_rejects_duplicates_nonfinite_invalid_and_oversize(self):
        for raw in (b'{"id":1,"id":2}', b'{"scope":{"domain":1,"domain":2}}', b'{"x":NaN}',
                    b'{"x":Infinity}', b'{"x":-Infinity}', b'\xff', b'[]', b' ', b'x' * (MAX_RECIPE_BYTES + 1)):
            with self.subTest(raw=raw[:50]):
                with self.assertRaises(ResearchError):
                    parse_json(raw, maximum=MAX_RECIPE_BYTES, code="INVALID_RESEARCH_RECIPE")

    def test_scope_and_need_mismatch_wait_with_original_validator(self):
        for changes in ({"domain_scope": {"domain": "materials", "contract": "tabular-quality-v1"}},
                        {"domain_scope": {"domain": "data", "contract": "different-v1"}},
                        {"domain_scope": {}}, {"need": "different_need"}):
            with self.subTest(changes=changes):
                host = context(**changes)
                decision = compile_recipe(recipe(), host)
                self.assertEqual(decision["proposal"]["choice"], {"kind": "wait"})
                self.assertIsNone(validate_proposal(host, decision["proposal"])["candidate"])


class RecipeChoiceTests(unittest.TestCase):
    def test_order_changes_choice_without_changing_either_input(self):
        host, first, second = context(), recipe(), recipe(True)
        frozen = copy.deepcopy([host, first, second])
        group = compile_recipe(first, host)
        source = compile_recipe(second, host)
        self.assertEqual(group["proposal"]["choice"], {"kind": "execute", "candidate_id": "group"})
        self.assertEqual(source["proposal"]["choice"], {"kind": "execute", "candidate_id": "source"})
        self.assertEqual([host, first, second], frozen)
        self.assertEqual(group, compile_recipe(first, host))
        group["recipe"]["scope_match"]["domain"] = "changed"
        group["checks"]["host_blockers"].append({"code": "changed"})
        self.assertEqual([host, first, second], frozen)

    def test_same_method_preserves_host_candidate_order_and_exact_evaluation(self):
        host = context()
        candidates = copy.deepcopy(host["candidates"])
        later = copy.deepcopy(candidates[1]); later["id"] = "source-later"
        candidates.insert(1, later)
        host = context(candidates=candidates)
        decision = compile_recipe(recipe(True), host)
        self.assertEqual(decision["selected_candidate_id"], "source-later")
        candidates[0]["evaluation_ref"] = "wrong-evaluation"
        host = context(candidates=candidates)
        self.assertEqual(compile_recipe(recipe(), host)["selected_candidate_id"], "source-later")
        decision = compile_recipe(recipe(True), host)
        self.assertEqual(decision["method_decisions"][0]["matching_candidate_ids"], ["source-later", "source"])
        self.assertEqual([item["outcome"] for item in decision["candidate_decisions"]], ["skipped", "selected", "skipped"])

    def test_blockers_or_no_matching_candidate_wait(self):
        for changes in ({"blockers": [{"code": "EXECUTION_UNKNOWN"}]}, {"candidates": []},
                        {"candidates": [{"id": "other", "method_id": "unlisted.method", "parameters": {},
                                         "evaluation_ref": "unlisted-evaluation"}]}):
            with self.subTest(changes=changes):
                host = context(**changes)
                decision = compile_recipe(recipe(), host)
                self.assertEqual(decision["proposal"]["choice"], {"kind": "wait"})
                self.assertIsNone(decision["selected_candidate_id"])
                self.assertTrue(all(item["outcome"] == "skipped" for item in decision["method_decisions"]))


class RecipeProtocolTests(unittest.TestCase):
    def test_proposals_pass_original_validator_and_have_no_extensions_or_citations(self):
        host = context()
        for config in (recipe(), recipe(True)):
            decision = compile_recipe(config, host)
            proposal = decision["proposal"]
            self.assertEqual(set(proposal), {"schema_version", "context_sha256", "provider", "choice", "rationale", "evidence_citation_ids"})
            self.assertEqual(proposal["provider"], {"kind": "operator_assistant", "label": "deterministic recipe policy; no model"})
            self.assertEqual(proposal["evidence_citation_ids"], [])
            self.assertFalse(decision["scientific_validation"])
            self.assertEqual(validate_proposal(host, proposal)["candidate"]["id"], decision["selected_candidate_id"])

    def test_context_candidate_parameter_or_citation_tampering_is_rejected(self):
        host = context()
        for change in (lambda value: value.update(goal="tampered"),
                       lambda value: value["candidates"][0].update(id="forged"),
                       lambda value: value["candidates"][0]["parameters"].update(command="forged"),
                       lambda value: value["evidence"][0].update(quote="tampered")):
            corrupted = copy.deepcopy(host); change(corrupted)
            with self.subTest(context=corrupted):
                with self.assertRaises(ResearchError) as caught:
                    compile_recipe(recipe(), corrupted)
                self.assertEqual(caught.exception.code, "INVALID_SELECTION_CONTEXT")
        for change in (lambda value: value["choice"].update(candidate_id="absent"),
                       lambda value: value["choice"].update(parameters={"path": "forged"}),
                       lambda value: value.update(evidence_citation_ids=["fabricated"]),
                       lambda value: value.update(scientific_validation=True)):
            proposal = compile_recipe(recipe(), host)["proposal"]; change(proposal)
            with self.assertRaises(ResearchError):
                validate_proposal(host, proposal)
        for invalid in (None, [], {}, {"context_sha256": "0" * 64}):
            with self.assertRaises(ResearchError):
                compile_recipe(recipe(), invalid)

    def test_cli_writes_only_two_records_and_refuses_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            recipe_path, context_path, output = root / "recipe.json", root / "context.json", root / "compiled"
            recipe_path.write_text(canonical(recipe()), encoding="utf-8")
            context_path.write_text(canonical(context()), encoding="utf-8")
            command = [sys.executable, str(ROOT / "scripts" / "compile_research_recipe.py"),
                       "--recipe", str(recipe_path), "--context", str(context_path), "--output", str(output)]
            first = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertEqual({path.name for path in output.iterdir()}, {"decision.json", "proposal.json"})
            before = {path.name: path.read_bytes() for path in output.iterdir()}
            repeated = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(repeated.returncode, 2)
            self.assertEqual(json.loads(repeated.stdout)["code"], "OUTPUT_EXISTS")
            self.assertEqual({path.name: path.read_bytes() for path in output.iterdir()}, before)
            context_path.write_text('{"context_sha256":NaN}', encoding="utf-8")
            command[-1] = str(root / "invalid-output")
            invalid = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(invalid.returncode, 2)
            self.assertEqual(json.loads(invalid.stdout)["code"], "INVALID_SELECTION_CONTEXT")
            self.assertFalse((root / "invalid-output").exists())


if __name__ == "__main__":
    unittest.main()
