"""Native zero-fit diagnostics of an explicitly bound completed Ridge result."""
import copy
import hashlib
from pathlib import Path

from .contracts import ResearchError

ADAPTER_VERSION = "1"


def _counts(pairs, names):
    changes = [left - right for left, right in pairs]
    return {names[0]: len(changes), names[1]: sum(value < 0 for value in changes),
            names[2]: sum(value > 0 for value in changes), names[3]: sum(value == 0 for value in changes)}


class SavedOOFDiagnosticAdapter:
    ADAPTER_VERSION = ADAPTER_VERSION

    def __init__(self, check):
        self.check = check
        self.TOOL_ID = "data.saved-oof-" + ("random" if check == "random_cv" else "group") + "-diagnostics"

    @staticmethod
    def code_identity():
        path = Path(__file__)
        return hashlib.sha256(path.read_bytes() + path.with_name("saved_oof_diagnostics.py").read_bytes()
                              + path.with_name("prediction_summary.py").read_bytes()).hexdigest()

    def execute(self, workspace, parameters):
        # Lazy import: the standalone reader imports ResearchProject itself.
        from .saved_oof_diagnostics import inspect_saved_oof
        diagnostic = inspect_saved_oof(workspace, parameters["based_on_action_id"])
        origin = diagnostic["provenance"]
        action, binding = origin["action"], origin["design_binding"]
        if diagnostic["check"] != self.check or action["result_sha256"] != parameters["based_on_result_sha256"]:
            raise ResearchError("EVIDENCE_CHANGED", "The diagnostic source differs from its accepted CV result.")
        source_ref = {"action_id": action["id"], "request_id": action["request_id"], "method_id": action["command"],
                      "result_sha256": action["result_sha256"], "producer_code_identity": action["code_identity"],
                      "design_version": binding["version"], "resource_id": binding["resource"]["id"],
                      "resource_version": binding["resource"]["version"], "target_column": diagnostic["target_column"],
                      "target_unit": diagnostic["target_unit"]}
        rows, groups = diagnostic["rows"], diagnostic["groups"]
        row_pairs = [(abs(row["predicted"] - row["observed"]),
                      abs(row["reference_prediction"] - row["observed"])) for row in rows]
        group_pairs = [(group["candidate_mae"], group["reference_mae"]) for group in groups]
        metrics = ("n", "candidate_mae", "reference_mae", "mean_error", "reference_mean_error", "negative_predictions")
        observation = {"producer": self.TOOL_ID, "kind": "saved_oof_diagnostic", "source_check": self.check,
            "source_ref": source_ref, "input_n": diagnostic["input_n"], "excluded": diagnostic["excluded"],
            "group_columns": copy.deepcopy(diagnostic["group_columns"]),
            "row_weighted": copy.deepcopy(diagnostic["row_weighted"]),
            "row_error_counts": _counts(row_pairs, ("n", "improved_rows", "worsened_rows", "tied_rows")),
            "group_weighted": copy.deepcopy(diagnostic["group_weighted"]),
            "group_error_counts": _counts(group_pairs, ("group_count", "improved_groups", "worsened_groups", "tied_groups")),
            "prediction_ranges": copy.deepcopy(diagnostic["prediction_ranges"]),
            "fold_errors": [{key: copy.deepcopy(fold[key]) for key in
                ("fold", "train_n", "test_n", "train_group_count", "test_group_count", *metrics)} for fold in diagnostic["folds"]],
            "group_errors": [{key: copy.deepcopy(group[key]) for key in ("groups", "folds", *metrics)} for group in groups],
            "interpretation_status": "saved_arithmetic_not_refitting_or_scientific_review", "scientific_validation": False}
        reference = {"source_snapshot_sha256": origin["source_snapshot_sha256"],
                     "source_sha256": origin["source_sha256"], "producer": copy.deepcopy(source_ref),
                     "locator": {"kind": "saved_oof_action", "action_id": action["id"], "result_sha256": action["result_sha256"]}}
        return {"schema_version": "saved-oof-diagnostic-result-v1", "tool_id": self.TOOL_ID,
            "adapter_version": self.ADAPTER_VERSION, "status": "completed", "observations": [observation],
            "metrics": [{"name": "diagnosed_rows", "value": len(rows), "unit": "count"},
                        {"name": "diagnosed_groups", "value": len(groups), "unit": "count"}],
            "evidence_refs": [reference], "result": {"diagnostic": diagnostic}, "failure": None,
            "scientific_validation": False, "new_fits": 0, "model_calls": 0}

    def next_decision(self, result):
        if (result.get("tool_id") != self.TOOL_ID or result.get("status") != "completed"
                or result.get("scientific_validation") is not False or result.get("new_fits") != 0
                or result.get("model_calls") != 0):
            raise ResearchError("INVALID_RESULT", "A completed unchanged saved-OOF diagnostic is required.")
        return {"policy_ref": {"id": self.TOOL_ID, "version": self.ADAPTER_VERSION}, "project_status": "waiting",
            "next_action": {"kind": "review_saved_evidence", "execution_status": "not_executed",
                "required_evidence": ["Interpret all retained local errors against the original target, sampling and input definitions; no new fit or scientific approval is implied."]},
            "reason": "Saved row, fold and group errors are supplied with the original producer identity; retain adverse outcomes and unresolved scientific conditions.",
            "source_snapshot_sha256": result["result"]["diagnostic"]["provenance"]["source_snapshot_sha256"],
            "evidence_refs": copy.deepcopy(result["evidence_refs"]), "scientific_validation": False,
            "new_fits": 0, "model_calls": 0}


ADAPTERS = (SavedOOFDiagnosticAdapter("random_cv"), SavedOOFDiagnosticAdapter("group_cv"))
