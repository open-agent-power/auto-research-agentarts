"""Evidence reports from durable observations; no model-generated results."""

import hashlib
import html
from .contracts import ResearchError, canonical, fingerprint


def cell(value):
    return html.escape(str(value)).replace("|", "&#124;").replace("\n", " ")


def build_report(engine, campaign_id):
    state = engine.status(campaign_id)
    integrity = []
    for trial in state["trials"]:
        if not trial.get("model_artifact"):
            continue
        path = (engine.root / trial["model_artifact"]).resolve()
        if not path.is_relative_to(engine.root):
            raise ResearchError("INVALID_ARTIFACT", "artifact path escapes workspace")
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            raise ResearchError("ARTIFACT_CHANGED", "report artifact is missing") from None
        if actual != trial["model_sha256"]:
            raise ResearchError("ARTIFACT_CHANGED", "report artifact differs from the recorded model")
        integrity.append({"trial_id": trial["id"], "model_sha256": actual, "verified": True})
    data = state["dataset"]
    lines = ["# 证据驱动实验报告", "", f"目标：{cell(state['goal'])}", "",
             f"研究：`{state['campaign_id']}`；状态：`{state['status']}`。", "",
             f"数据：`{data['dataset_id']}`；证据类型：`{data['evidence_type']}`；研究状态：`{state['scientific_status']}`。",
             f"划分：`{data['split_protocol']}`；数据 SHA-256：`{data['data_sha256']}`。", "",
             "## 方法与边界", "",
             f"策略：`{state['policy_kind']}`。" +
             ("本策略约定由外部研究 Agent 提交结构化配方，控制器核对观察版本和引用后执行。"
              if state['policy_kind'] == 'external_agent_proposal_v1' else "固定工程策略生成候选，不作为研究 Agent 自主提案证据。"),
             "候选为多项式特征＋标准化＋Ridge；最终评价和数据划分不能由提案修改。",
             "这是本地预测基准；不代表新的科学发现、临床有效性、内置自主 LLM 或 AgentArts 云端贯通。",
             "数据划分、特征与来源以本报告数据描述为准；材料任务使用自定义组成分组 holdout，并非官方 Matbench 五折成绩。", "",
             "## 实际试验", "",
             "| 次数 | 候选 | 训练 MSE | 验证 MSE | 决定 | 假设 | 预期影响 |", "|---:|---|---:|---:|---|---|---|"]
    for trial in state["trials"]:
        proposal = trial.get("proposal", {})
        metric = trial.get("metrics", {}).get("validation_mse", "未取得")
        train_metric = trial.get("metrics", {}).get("training_mse", "历史记录未提供")
        lines.append(f"| {trial['ordinal']} | {cell(trial['candidate'])} | {train_metric} | {metric} | {trial['status']} | "
                     f"{cell(proposal.get('hypothesis', trial['reason']))} | {cell(proposal.get('expected_effect', '固定工程策略'))} |")
    lines += ["", "## 决策与复现证据", ""]
    for trial in state["trials"]:
        proposal = trial.get("proposal", {})
        lines += [f"- 试验 `{trial['id']}`／请求 `{trial['request_id']}`：{cell(trial.get('decision_reason',trial.get('error',{})))}。",
                  f"  观察指纹：`{proposal.get('observation_sha256','固定策略无提案')}`；引用试验：`{cell(proposal.get('evidence_trial_ids',[]))}`。",
                  f"  配方 SHA：`{trial.get('recipe_sha256','未取得')}`；训练代码 SHA：`{trial.get('training_code_sha256','未取得')}`；模型 SHA：`{trial.get('model_sha256','未取得')}`。"]
    lines += ["", "## 独立终测", ""]
    if state["final_evaluation"]:
        final = state["final_evaluation"]
        lines.append(f"最佳试验 `{final['best_trial_id']}`；测试 MSE：{final['test_mse']}；样本数：{final['test_rows']}。终测后本研究已锁定优化。")
    else:
        lines.append("尚未终测；测试指标不进入用于生成后续提案的观察。")
    lines += ["", "## 局限", "", "本报告从持久试验记录生成；提案的假设和预期影响是待检验主张，指标与决定来自实际执行。",
              "本轮没有验证跨领域科研增益、材料作用机制或研究 Agent 的权重更新。", ""]
    return {"report_version": "research-evidence-report-v1", "state": state,
            "state_sha256": fingerprint(state), "artifact_integrity": integrity,
            "cloud_calls_made_by_report": 0, "markdown": "\n".join(lines)}


def write_report(engine, campaign_id):
    report = build_report(engine, campaign_id)
    directory = engine.root / "exports"
    directory.mkdir(exist_ok=True)
    outputs = {}
    for suffix, payload in (("json", canonical(report)), ("md", report["markdown"])):
        path = directory / f"{campaign_id}.{suffix}"
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(path)
        outputs[suffix] = str(path)
    return outputs
