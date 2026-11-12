"""从明确的已完成 raw Ridge 行动导出只读 OOF 诊断。"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from autoresearch.contracts import ResearchError
from autoresearch.saved_oof_diagnostics import inspect_saved_oof


def _cell(value):
    if value is None:
        return "null"
    if isinstance(value, float):
        return format(value, ".12g")
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(headers, rows):
    return ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |",
            *("| " + " | ".join(_cell(value) for value in row) + " |" for row in rows), ""]


def _fold_coverage(bucket, total):
    counts = ", ".join(f"{item['fold']}:{item['n']}" for item in bucket["fold_counts"])
    return f"{bucket['fold_count']}/{total}" + (f" ({counts})" if counts else "")


def _within_group_markdown(within):
    summary = within["summary"]
    lines = [f"## 组内相邻输入对照：{within['column']}", "",
             f"声明分组：{_cell(within['group_columns'])}；原尺度输入。",
             f"完整保留 {summary['group_count']} 组 / {summary['row_count']} 行 / {summary['level_count']} 个组内输入水平；"
             f"可比较 {summary['comparable_group_count']} 组 / {summary['comparable_row_count']} 行，"
             f"不可比较 {summary['noncomparable_group_count']} 组 / {summary['noncomparable_row_count']} 行。",
             f"可比较组共 {summary['adjacent_pair_count']} 个相邻对，分为 {summary['pair_type_count']} 种精确低值/高值组合。",
             "变化统一为高值水平均值 − 低值水平均值；平均残差变化 = 预测变化 − 观察变化。", "",
             "### 完整相邻输入对类型", ""]
    lines += _table(["低值", "高值", "组数", "低值行", "高值行", "平均观察变化", "平均预测变化", "平均残差变化", "观察增加组", "观察减少组", "观察持平组"], [
        [pair[key] for key in ("low_value", "high_value", "group_count", "low_n", "high_n", "mean_observed_change",
                               "mean_predicted_change", "mean_error_change", "observed_increase_groups",
                               "observed_decrease_groups", "observed_tie_groups")] for pair in within["pair_summaries"]])
    if summary["reason_counts"]:
        labels = {"singleton": "单行组", "single_input_level": "只有一个输入水平", "mixed_evaluation_folds": "跨保存评价折",
                  "varying_other_features": "其他训练输入变化"}
        lines += ["不可比较原因（同一组可能有多项）：" + "；".join(
            f"{labels[item['reason_code']]} {item['group_count']} 组 / {item['row_count']} 行"
            for item in summary["reason_counts"]) + "。", ""]
    lines += ["各组状态、原因、变化的其他输入、完整水平/相邻对与逻辑行成员保留在 diagnostic.json 的 within_group。", ""]
    return lines


def diagnostic_markdown(result):
    origin, row, group = result["provenance"], result["row_weighted"], result["group_weighted"]
    lines = ["# 保存 OOF 只读诊断", "", f"项目：`{origin['project_id']}`；state_version：{origin['state_version']}。",
             f"行动：`{origin['action']['id']}`；检查：`{result['check']}`；目标：`{result['target_column']}`（{result['target_unit']}）。",
             f"来源 snapshot：`{origin['source_snapshot_sha256']}`。", f"结果 artifact：`{origin['artifact_sha256']}`。", "",
             f"原始 {result['input_n']} 行，评价 {row['n']} 行，排除 {result['excluded']} 行；声明组 {group['group_count']} 个。",
             "残差统一为 predicted − observed；参考为各训练折目标均值。以下数值使用目标原单位。", "",
             "## 汇总", ""]
    lines += _table(["加权", "行数 / 组数", "candidate MAE", "reference MAE", "平均残差", "负预测数"], [
        ["逐行", row["n"], row["candidate_mae"], row["reference_mae"], row["mean_error"], row["negative_predictions"]],
        ["逐组等权", group["group_count"], group["candidate_mae"], group["reference_mae"], None, None]])
    lines += ["## 完整折表", ""]
    lines += _table(["fold", "训练行", "测试行", "训练组", "测试组", "candidate MAE", "reference MAE", "平均残差", "负预测数"], [
        [fold[key] for key in ("fold", "train_n", "test_n", "train_group_count", "test_group_count", "candidate_mae",
                              "reference_mae", "mean_error", "negative_predictions")] for fold in result["folds"]])
    lines += ["## 声明组规模", ""]
    lines += _table(["组类型", "行数", "组数", "逐行 candidate MAE", "逐行 reference MAE", "等权组 candidate MAE", "等权组 reference MAE"], [
        [item["stratum"], item["row_weighted"]["n"], item["group_weighted"]["group_count"], item["row_weighted"]["candidate_mae"],
         item["row_weighted"]["reference_mae"], item["group_weighted"]["candidate_mae"], item["group_weighted"]["reference_mae"]]
        for item in result["group_strata"]])
    lines += ["完整逐组 MAE、参考 MAE、平均残差、负预测数与逻辑行成员保留在 diagnostic.json 的 groups。", "", "## 完整输入表", ""]
    if not result["input_profiles"]:
        lines += ["本次未请求输入列。", ""]
    for profile in result["input_profiles"]:
        lines += [f"### {profile['column']}（{profile['grouping']}，原尺度输入）", ""]
        lines += _table(["值 / 区间", "行数", "组数", "折覆盖（fold:行数）", "candidate MAE", "reference MAE", "平均残差", "负预测数"], [
            [bucket["label"], bucket["n"], bucket["group_count"], _fold_coverage(bucket, len(result["folds"])),
             *[bucket[key] for key in ("candidate_mae", "reference_mae", "mean_error", "negative_predictions")]]
            for bucket in profile["buckets"]])
    if "within_group" in result:
        lines += _within_group_markdown(result["within_group"])
    limitations = result["limitations"] + (result["within_group"]["limitations"] if "within_group" in result else [])
    lines += ["## Limitations", "", *("- " + value for value in limitations), "",
              "scientific_validation=false；新增 model / fit / source dispatch 均为 0。", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("workspace", "action-id", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--column", action="append", default=[])
    parser.add_argument("--within-group-column", help="比较声明组内相邻原始训练输入水平（可选）")
    args = parser.parse_args(argv)
    try:
        workspace, output = Path(args.workspace).resolve(), Path(args.output).resolve()
        if output == workspace or output.is_relative_to(workspace) or workspace.is_relative_to(output):
            raise ResearchError("INVALID_DIAGNOSTIC_OUTPUT", "Output must be separate from the original project.")
        if output.exists():
            raise ResearchError("EVIDENCE_CONFLICT", "Use a fresh output directory; existing evidence is preserved.")
        result = inspect_saved_oof(workspace, args.action_id, args.column, within_group_column=args.within_group_column)
        raw = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        markdown = diagnostic_markdown(result)
        output.mkdir(parents=True, exist_ok=False)
        (output / "diagnostic.json").write_text(raw, encoding="utf-8")
        (output / "diagnostic.md").write_text(markdown, encoding="utf-8")
        print(json.dumps({"ok": True, "output": str(output), "action_id": args.action_id,
                          "n": result["row_weighted"]["n"], "scientific_validation": False}, ensure_ascii=False))
        return 0
    except (ResearchError, ValueError, OSError) as error:
        print(json.dumps({"ok": False, "code": getattr(error, "code", "INVALID_SAVED_OOF_DIAGNOSTIC"),
                          "message": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
