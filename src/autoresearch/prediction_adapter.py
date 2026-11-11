"""Check explicitly declared saved predictions against bounded numeric references."""

import copy
import hashlib
from pathlib import Path

from . import grouped_quality_adapter as grouped, numeric_association_adapter as numeric, tabular_quality_adapter as tabular, prediction_controls


ADAPTER_VERSION = "1"
MAX_RECORDS = 512


class PredictionAdapter:
    ADAPTER_VERSION = ADAPTER_VERSION

    def __init__(self, check):
        self.check = check
        self.TOOL_ID = "data.prediction-" + check

    def code_identity(self):
        from . import prediction_checks, project_design
        raw = (Path(__file__).read_bytes() + Path(prediction_checks.__file__).read_bytes()
               + Path(prediction_controls.__file__).read_bytes() + Path(project_design.__file__).read_bytes())
        return hashlib.sha256(raw + tabular.code_identity().encode("ascii")).hexdigest()

    def execute(self, payload, parameters):
        from .prediction_checks import evaluate_prediction

        predecessor = grouped._parameters(parameters)
        original = {key: value for key, value in payload.items() if key != "design_binding"}
        spec, _, (header, records, physical_end) = tabular._checked(original)
        tabular._require(len(records) <= MAX_RECORDS, "UNSUPPORTED_SCOPE", "Saved-prediction checks support at most 512 captured records.")
        binding = payload.get("design_binding")
        tabular._require(type(binding) is dict and binding["source_snapshot_sha256"] == payload["snapshot_sha256"]
                         and binding["target_column"] == spec["target_column"]
                         and binding["prediction_column"] in spec["numeric_columns"]
                         and binding["prediction_column"] != spec["target_column"]
                         and self.check in binding["resource"]["checks"],
                         "EVIDENCE_CHANGED", "The frozen prediction design differs from the captured input.")
        positions, missing = {name: index for index, name in enumerate(header)}, set(spec["missing_tokens"])
        observed = [numeric._finite(row[positions[spec["target_column"]]], missing) for row, _ in records]
        predicted = [numeric._finite(row[positions[binding["prediction_column"]]], missing) for row, _ in records]
        groups = None
        if self.check != "baseline" and spec["group_columns"]:
            groups = [tuple(None if row[positions[name]] in missing else row[positions[name]]
                            for name in spec["group_columns"]) for row, _ in records]
        analysis = evaluate_prediction(observed, predicted, groups=groups, check=self.check)
        scope = copy.deepcopy(payload["scope"])
        scope.update(contract="prediction-check-" + self.check + "-v1", input_contract=payload["scope"]["contract"])
        reference = {"source_snapshot_sha256": payload["snapshot_sha256"], "source_sha256": payload["source"]["sha256"],
                     "file_name": spec["file"], "url": spec["source_url"], "license_note": spec["license_note"],
                     "predecessor": copy.deepcopy(predecessor),
                     "locator": {"kind": "csv_logical_records", "first": 1 if records else None,
                                 "last": len(records) or None, "physical_line_end": physical_end}}
        analysis_record = {**analysis, "schema_version": "prediction-check-v1", "scope": scope,
                           "source_snapshot_sha256": payload["snapshot_sha256"], "design_binding": copy.deepcopy(binding),
                           "predecessor": predecessor, "target_column": spec["target_column"],
                           "prediction_column": binding["prediction_column"], "group_columns": copy.deepcopy(spec["group_columns"]),
                           "scientific_validation": False}
        result = {"analysis": analysis_record, "scope": scope, "predecessor": copy.deepcopy(predecessor),
                  "source_snapshot_sha256": payload["snapshot_sha256"]}
        observation = {"producer": self.TOOL_ID, "kind": "prediction_check", "check": self.check,
                       "summary": copy.deepcopy(analysis["summary"]), "findings": copy.deepcopy(analysis["findings"]),
                       "limitations": copy.deepcopy(analysis["limitations"]), "design_binding": copy.deepcopy(binding),
                       "target_column": spec["target_column"], "prediction_column": binding["prediction_column"],
                       "scope": scope, "predecessor": copy.deepcopy(predecessor), "evidence_refs": [copy.deepcopy(reference)],
                       "interpretation_status": "saved_prediction_comparison_not_independent_validation", "scientific_validation": False}
        return {"schema_version": "prediction-check-result-v1", "tool_id": self.TOOL_ID, "adapter_version": ADAPTER_VERSION,
                "status": "completed", "observations": [observation], "metrics": [
                    {"name": name, "value": analysis["summary"][name], "unit": spec["target_unit"]}
                    for name in ("candidate_mae", "reference_mae")], "evidence_refs": [reference], "result": result,
                "failure": None, "scientific_validation": False, "new_fits": 0, "model_calls": 0}

    def next_decision(self, result):
        tabular._require(result.get("tool_id") == self.TOOL_ID and result.get("status") == "completed"
                         and result.get("new_fits") == 0 and result.get("model_calls") == 0,
                         "INVALID_RESULT", "A saved prediction check result is required.")
        return {"policy_ref": {"id": self.TOOL_ID, "version": ADAPTER_VERSION}, "project_status": "waiting",
                "next_action": {"kind": "evidence_task", "method_id": "research.source-selection", "execution_status": "not_executed",
                                "required_evidence": ["Confirm saved-prediction training and holdout provenance, target units and sampling-group definitions.",
                                                      "Use the saved comparison and sensitivity findings before deciding on reuse."]},
                "reason": "The saved predictions were compared with the fixed reference; conditional follow-up checks remain available.",
                "source_snapshot_sha256": result["result"]["source_snapshot_sha256"],
                "predecessor": copy.deepcopy(result["result"]["predecessor"]),
                "evidence_refs": copy.deepcopy(result["evidence_refs"]), "scientific_validation": False, "new_fits": 0, "model_calls": 0}


class NegativeControlAdapter(PredictionAdapter):
    def __init__(self):
        super().__init__("negative_control")
        self.TOOL_ID = "data.prediction-negative-control"

    def execute(self, payload, parameters):
        from .prediction_controls import evaluate_negative_control

        predecessor = grouped._parameters(parameters)
        original = {key: value for key, value in payload.items() if key not in ("design_binding", "generated_prediction")}
        spec, _, _ = tabular._checked(original)
        binding, generated = payload["design_binding"], payload["generated_prediction"]
        producer = generated["analysis"]
        tabular._require(producer["schema_version"] == "ridge-validation-v1"
                         and producer["source_snapshot_sha256"] == payload["snapshot_sha256"]
                         and binding["prediction_column"] is None and "negative_control" in binding["resource"]["checks"],
                         "EVIDENCE_CHANGED", "Negative control requires OOF predictions from the bound raw design.")
        rows = producer["oof"]
        analysis = evaluate_negative_control([row["observed"] for row in rows], [row["predicted"] for row in rows],
                                             groups=[row["fold"] for row in rows])
        analysis["protocol"]["grouping"] = "within_oof_folds"
        scope = {**copy.deepcopy(payload["scope"]), "contract": "prediction-check-negative_control-v1",
                 "input_contract": payload["scope"]["contract"]}
        reference = {"source_snapshot_sha256": payload["snapshot_sha256"], "source_sha256": payload["source"]["sha256"],
                     "file_name": spec["file"], "url": spec["source_url"], "license_note": spec["license_note"],
                     "predecessor": copy.deepcopy(predecessor),
                     "generated_prediction_ref": {key: generated[key] for key in ("action_id", "result_sha256")}}
        analysis.update(check="negative_control", design_binding=copy.deepcopy(binding), scope=scope,
                        source_snapshot_sha256=payload["snapshot_sha256"], predecessor=predecessor,
                        target_column=spec["target_column"], prediction_column=None,
                        generated_prediction_ref=reference["generated_prediction_ref"],
                        declared_groups=[row["groups"] for row in rows])
        observation = {"producer": self.TOOL_ID, "kind": "prediction_check", "check": "negative_control",
                       "summary": copy.deepcopy(analysis["summary"]), "design_binding": copy.deepcopy(binding),
                       "scope": scope, "predecessor": copy.deepcopy(predecessor), "evidence_refs": [reference],
                       "interpretation_status": "within_fold_pairing_control_not_independent_validation", "scientific_validation": False}
        return {"schema_version": "prediction-check-result-v1", "tool_id": self.TOOL_ID, "adapter_version": ADAPTER_VERSION,
                "status": "completed", "observations": [observation], "metrics": [], "evidence_refs": [reference],
                "result": {"analysis": analysis, "scope": scope, "predecessor": predecessor,
                           "source_snapshot_sha256": payload["snapshot_sha256"]},
                "failure": None, "scientific_validation": False, "new_fits": 0, "model_calls": 0}


BASELINE = PredictionAdapter("baseline")
GROUPED = PredictionAdapter("grouped")
SENSITIVITY = PredictionAdapter("sensitivity")
NEGATIVE_CONTROL = NegativeControlAdapter()
ADAPTERS = (BASELINE, GROUPED, SENSITIVITY, NEGATIVE_CONTROL)
