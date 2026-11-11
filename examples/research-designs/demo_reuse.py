"""Run two independent engineering fixtures through the normal local workbench."""
import argparse
import base64
import hashlib
import json
from pathlib import Path

from autoresearch.contracts import canonical
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.prediction_checks import evaluate_prediction
from autoresearch.project_controller import ProjectController


FIXTURES = {
    "a": {"observed": [0, 1, 2, 3, 20, 21], "predicted": [3, 4, 5, 6, 20, 21],
          "groups": ["a", "a", "b", "b", "c", "c"]},
    "b": {"observed": [2, 4, 16, 18, 30, 34], "predicted": [2.5, 3.5, 16.5, 17.5, 30.5, 33.5],
          "groups": ["x", "x", "y", "y", "z", "z"]},
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def create_body(name):
    fixture = FIXTURES[name]
    lines = ["batch,observed,predicted"]
    lines.extend(f"{group},{observed},{predicted}" for group, observed, predicted
                 in zip(fixture["groups"], fixture["observed"], fixture["predicted"]))
    raw = ("\n".join(lines) + "\n").encode("utf-8")
    spec = {"schema_version": "tabular-quality-spec-v1", "file": "predictions.csv",
            "dataset_label": f"Independent constructed prediction fixture {name.upper()}",
            "source_url": "urn:autoresearch:engineering-design-reuse:" + name,
            "license_note": "Project-authored synthetic engineering fixture; no external dataset.",
            "sample_unit": "constructed_record", "group_columns": ["batch"], "key_columns": [],
            "numeric_columns": ["observed", "predicted"], "target_column": "observed",
            "target_unit": "fixture_unit", "missing_tokens": ["", "NA"], "delimiter": ",",
            "provenance": {"origin_sha256": hashlib.sha256(raw).hexdigest(),
                           "description": "Authored observed and prediction values; no trained model or held-out protocol."}}
    return {"request_id": name + "-create", "goal": "Review saved constructed predictions for fixture " + name.upper(),
            "budget_ref": "isolated-design-reuse-fixture:" + name, "max_tool_calls": 8,
            "input": {"file_name": spec["file"], "csv_base64": base64.b64encode(raw).decode("ascii"),
                      "spec_base64": base64.b64encode(canonical(spec).encode("utf-8")).decode("ascii")}}


def command(manager, request_id, **values):
    project, _ = manager.binding()
    state = project.status()
    return {"request_id": request_id, "project_id": state["id"],
            "expected_state_version": state["state_version"], **values}


def invoke(manager, requests, method, body):
    result = getattr(manager, method)(body)
    require(result["status"] in {"created", "completed"}, f"Unexpected {method} outcome: {result['status']}")
    requests.append((method, body))
    return result


def bind(manager, requests, name, version):
    body = command(manager, f"{name}-bind-v{version}", resource_id="saved-prediction-review", resource_version=version,
                   prediction_column="predicted", reason="Bind the resource to the authored saved-prediction column.")
    return invoke(manager, requests, "bind_design", body)


def step(manager, requests, request_id, method):
    project, _ = manager.binding()
    context = ProjectController(project.root).selection_context()
    candidate = next((item for item in context["candidates"] if item["method_id"] == method), None)
    require(candidate is not None, f"No qualified {method} candidate for {request_id}.")
    proposal = {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                "provider": {"kind": "operator_assistant", "label": "Explicit engineering-fixture script"},
                "choice": {"kind": "execute", "candidate_id": candidate["id"]},
                "rationale": "Execute only this check from the current sealed candidate context.", "evidence_citation_ids": []}
    return invoke(manager, requests, "advance", command(manager, request_id, proposal=proposal))


def snapshot(manager):
    project, _ = manager.binding()
    state, catalog = project.status(), manager.designs()
    return {"project_id": state["id"], "state_version": state["state_version"],
            "source_snapshot_sha256": state["source_snapshot_sha256"],
            "design": catalog["binding"], "assessment": catalog["assessment"], "checks": catalog["checks"],
            "budget": state["budget"], "host_decisions": HostModelSelection(project.root).status()["usage"]["decision_slots_used"],
            "action_ids": [item["id"] for item in state["actions"]], "workspace": str(project.root)}


def replay(manager, project_id, name, requests):
    manager.select({"request_id": name + "-select-for-replay", "project_id": project_id})
    project, _ = manager.binding()
    before = project.status()
    receipts = []
    reopened = LocalWorkbench(manager.root)
    for method, body in requests:
        result = getattr(reopened, method)(body)
        require(result.get("replayed") is True, "Original request did not return its replay receipt.")
        receipts.append({"request_id": body["request_id"], "method": method, "replayed": True})
    after = project.status()
    require(after == before, "Replay changed the original project state or cumulative usage.")
    return {"project_id": project_id, "requests": receipts, "project_state_unchanged": True,
            "budget_unchanged": after["budget"] == before["budget"], "additional_tool_calls": 0}


def fixture_checks():
    adverse = evaluate_prediction(**FIXTURES["a"], check="sensitivity")
    require(adverse["summary"]["improvement"] > 0 and adverse["details"]["conclusion_reversed"],
            "Fixture A must retain a genuine adverse group-exclusion result.")
    removal = adverse["details"]["most_influential"]
    require(removal["unit"] == "c" and abs(removal["improvement"] + 0.5) < 1e-10,
            "Fixture A's group-c exclusion must produce the hand-checked -50% improvement.")
    stable = evaluate_prediction(**FIXTURES["b"], check="sensitivity")
    require(stable["summary"]["improvement"] > 0 and stable["details"]["conclusion_reversed"] is False,
            "Fixture B must retain its distinct stable result.")
    grouped = evaluate_prediction(**FIXTURES["b"], check="grouped")
    require(all(group["improvement"] > 0 for group in grouped["details"]["groups"]),
            "Fixture B must improve on the reference in every declared group.")


def report_text(result):
    lines = ["# 研究设计跨项目复用工程记录", "", "输入为独立构造的验证用例，预测值由示例作者直接给出。", "",
             "| 项目阶段 | 设计版本 | claim_supported | 本地工具用量 | 模型调用 | 拟合 |", "|---|---|---|---|---|---|"]
    for label, stage in result["stages"].items():
        budget = stage["budget"]
        lines.append(f"| {label} | {stage['design']['resource']['version']} | {stage['assessment']['claim_supported']} | "
                     f"{budget['local_tool_calls_used']}/{budget['local_tool_call_limit']} | {budget['new_model_requests']} | {budget['new_fits']} |")
    lines.extend(["", "A的v1仅核对总体误差。v2增加分组及删除单位检查，c组删除后改善比例为-50%，完整优势主张为False。",
                  "B从目录引用同一v2，并在独立输入上完成三个检查，工程误差比较主张为True。", "",
                  "原请求在重新打开manager后重放，两个项目的完整状态和累计用量保持一致。", "",
                  "计算工件、各组指标、删除单位结果、原始输入和预算位于demo-result.json及manager目录。", "",
                  "## Limitations", "", "该记录验证资源修订、跨项目执行及不利反馈保留。真人使用、真实预测产生协议和科研收益需各自取得证据。",
                  "均值参考仅排除评价对象或整组后用剩余目标计算。使用真实数据时须确认预测来源、划分、单位和样本关系。", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New output directory; existing paths are rejected.")
    arguments = parser.parse_args()
    output = arguments.output.absolute()
    if output.exists():
        parser.error("--output must name a new directory.")
    fixture_checks()
    output.mkdir(parents=True, exist_ok=False)
    manager, requests_a, requests_b = LocalWorkbench(output / "manager"), [], []
    created_a = invoke(manager, requests_a, "create", create_body("a"))
    bind(manager, requests_a, "a", 1)
    step(manager, requests_a, "a-quality", "data.tabular-quality-audit")
    step(manager, requests_a, "a-baseline-v1", "data.prediction-baseline")
    first = snapshot(manager)
    require(first["assessment"]["claim_supported"] is True, "A's v1 overall comparison must be supported.")
    improvement = command(manager, "a-improve-v2", reason="实际总体误差下降，但六行分为三个组，原设计尚缺分组及删除单位的反证检查。")
    invoke(manager, requests_a, "improve_design", improvement)
    bind(manager, requests_a, "a", 2)
    for check in ("baseline", "grouped", "sensitivity"):
        step(manager, requests_a, "a-v2-" + check, "data.prediction-" + check)
    revised = snapshot(manager)
    require(revised["assessment"]["claim_supported"] is False, "A's adverse feedback must weaken the full claim.")
    sensitivity = next(item for item in revised["checks"] if item["check"] == "sensitivity")["details"]
    require(sensitivity["conclusion_reversed"] and abs(sensitivity["most_influential"]["improvement"] + 0.5) < 1e-10,
            "The saved A result must retain its actual -50% adverse group-exclusion result.")
    created_b = invoke(manager, requests_b, "create", create_body("b"))
    bind(manager, requests_b, "b", 2)
    step(manager, requests_b, "b-quality", "data.tabular-quality-audit")
    for check in ("baseline", "grouped", "sensitivity"):
        step(manager, requests_b, "b-v2-" + check, "data.prediction-" + check)
    reused = snapshot(manager)
    require(reused["assessment"]["claim_supported"] is True, "B must retain its independently supported fixture comparison.")
    require(reused["design"]["resource"] == revised["design"]["resource"], "B must reuse A's exact immutable v2 resource.")
    require(first["project_id"] != reused["project_id"] and first["source_snapshot_sha256"] != reused["source_snapshot_sha256"],
            "Cross-project reuse must retain distinct project and source identities.")
    stages = {"A-v1": first, "A-v2": revised, "B-v2": reused}
    require(all(stage["budget"]["new_model_requests"] == stage["budget"]["new_fits"] == stage["host_decisions"] == 0
                for stage in stages.values()), "The fixture must preserve zero model calls and zero fits.")
    replays = [replay(manager, created_a["project_id"], "a", requests_a),
               replay(manager, created_b["project_id"], "b", requests_b)]
    result = {"schema_version": "research-design-reuse-demo-v1", "evidence_kind": "synthetic_engineering_fixture",
              "stages": stages, "resources": manager.designs()["resources"], "replay": replays,
              "boundary_cases": {"constant_target": evaluate_prediction([4, 4, 4], [4, 5, 3]),
                                 "single_group": evaluate_prediction([0, 1, 2], [0, 1, 2], groups=["one"] * 3, check="grouped")},
              "model_calls": 0, "new_fits": 0, "human_use_evidence": False, "scientific_validation": False}
    with (output / "demo-result.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
    with (output / "demo-report.md").open("x", encoding="utf-8") as stream:
        stream.write(report_text(result))
    print(json.dumps({"output": str(output), "claims": {key: value["assessment"]["claim_supported"] for key, value in stages.items()},
                      "model_calls": 0, "new_fits": 0, "replayed_projects": len(replays)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
