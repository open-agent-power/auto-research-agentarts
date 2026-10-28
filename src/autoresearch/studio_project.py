"""Frozen experiment evidence and operator-authored follow-up questions.

Preparing a project reads existing experiment artifacts and recomputes predictions.
It never fits a model, calls a model provider or edits the source campaign.
"""

import csv
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import sqlite3
import sys
import uuid

import numpy as np

from .contracts import ResearchError, canonical, fingerprint, identifier
from .engine import Engine
from .reports import build_report
from . import datasets, training


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atomic_text(path, text):
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def csv_bytes(header, rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


class ReadOnlyEvidence(Engine):
    """Reuse status projection without running Engine's schema migrations."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.db = self.root / "research.sqlite3"

    @contextmanager
    def connection(self, write=False):
        if write:
            raise ResearchError("READ_ONLY", "source evidence is read-only")
        con = sqlite3.connect(self.db.as_uri() + "?mode=ro", uri=True, timeout=10, isolation_level=None)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA query_only=ON")
            con.execute("BEGIN")
            yield con
        finally:
            con.close()


def _models(engine, state):
    result = {}
    for trial in state["trials"]:
        if not trial.get("model_artifact"):
            continue
        identifier(trial["id"], "trial_id")
        path = (engine.root / trial["model_artifact"]).resolve()
        if not path.is_relative_to(engine.root) or not path.is_file():
            raise ResearchError("INVALID_ARTIFACT", "model artifact must remain inside the source workspace")
        payload = path.read_bytes()
        if sha(payload) != trial["model_sha256"]:
            raise ResearchError("ARTIFACT_CHANGED", "source model differs from its recorded hash")
        artifact = json.loads(payload)
        if artifact["dataset_id"] != state["dataset_id"] or artifact["data_sha256"] != state["dataset"]["data_sha256"]:
            raise ResearchError("DATASET_CHANGED", "model and campaign dataset identities differ")
        result[trial["id"]] = (artifact, payload)
    if not result or state["best_trial_id"] not in result:
        raise ResearchError("NO_RESULTS", "a retained model with actual recorded results is required")
    return result


def prepare_project(source_workspace, campaign_id, output):
    source = Path(source_workspace).resolve()
    output = Path(output).resolve()
    if output == source or output.is_relative_to(source):
        raise ResearchError("INVALID_REQUEST", "studio output must be outside the source experiment workspace")
    if output.exists() and any(output.iterdir()):
        raise ResearchError("OUTPUT_EXISTS", "use an empty studio output directory; existing projects are not overwritten")
    if not (source / "research.sqlite3").is_file():
        raise ResearchError("NOT_FOUND", "source research database is missing")
    engine = ReadOnlyEvidence(source)
    report = build_report(engine, campaign_id)
    state = report["state"]
    if state["dataset_id"] != datasets.STEELS_ID:
        raise ResearchError("UNSUPPORTED_DATASET", "this paper template requires the public steels engineering case")
    if len(state["trials"]) > 5:
        raise ResearchError("TEMPLATE_LIMIT", "the five-page paper supports at most five recorded trials; extend the template for a larger study")
    if fingerprint(state["dataset"]) != fingerprint(datasets.descriptor(state["dataset_id"])):
        raise ResearchError("DATASET_CHANGED", "current public data differs from the experiment")
    models = _models(engine, state)
    x, y = datasets.split_data(state["dataset_id"], "validation")
    predictions = {}
    for trial in state["trials"]:
        if trial["id"] not in models:
            continue
        artifact = models[trial["id"]][0]
        predicted = training.predict(artifact, x)
        measured = float(np.mean((predicted-y)**2))
        if not np.all(np.isfinite(predicted)) or not math.isclose(measured, trial["metrics"]["validation_mse"], rel_tol=1e-9, abs_tol=1e-6):
            raise ResearchError("METRIC_MISMATCH", "recomputed validation metric differs from its original record")
        predictions[trial["id"]] = predicted
    with engine.connection() as con:
        exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='autonomy_project'").fetchone()
        origin = con.execute("SELECT fixture FROM autonomy_project WHERE campaign_id=?", (campaign_id,)).fetchone() if exists else None
    fixture = origin is not None and origin["fixture"] == 1
    recorded = [t for t in state["trials"] if t["id"] in models]
    baseline = recorded[0]
    best = next(t for t in recorded if t["id"] == state["best_trial_id"])
    best_mse = best["metrics"]["validation_mse"]
    low_mse = min(t["metrics"]["validation_mse"] for t in recorded)
    raw_gain = (baseline["metrics"]["validation_mse"]-low_mse) / baseline["metrics"]["validation_mse"] * 100
    decision_origin = "脚本决策响应 · 真实训练记录" if fixture else "提案来源需结合原始记录核对 · 真实参数工件"
    labels = {"dataset": state["dataset_id"], "decision_origin": decision_origin,
              "scientific_status": "公开基准 · 工程案例", "cloud": "模型与平台接入暂缓"}
    sources = [
        {"id": "S1", "title": "Matbench steels 数据与使用范围", "url": state["dataset"].get("source_url", "https://matbench.materialsproject.org/"),
         "description": "312条成分与实验屈服强度；固定数据版本及CC BY 4.0署名见附件。" if state["dataset_id"] == datasets.STEELS_ID else "固定工程数据，见数据描述。"},
        {"id": "S2", "title": "Dunn等 2020 Matbench 原始论文", "url": "https://www.nature.com/articles/s41524-020-00406-3",
         "description": "用于数据背景与官方协议对照；其五折协议及MAE不可与本报告holdout MSE直接横比。"},
        {"id": "S3", "title": "scikit-learn Ridge 方法文档", "url": "https://scikit-learn.org/1.9/modules/generated/sklearn.linear_model.Ridge.html",
         "description": "L2正则化回归的目标与alpha含义；工件内保留实际依赖版本。"},
    ]
    claims = [
        {"id": "C1", "statement": f"固定数据包含{sum(state['dataset']['split_counts'].values())}条记录；验证集{len(y)}条。", "evidence_ids": ["S1"], "status": "observed"},
        {"id": "C2", "statement": f"本报告汇总{len(recorded)}次已有参数训练结果，未新增训练。", "evidence_ids": [t["id"] for t in recorded], "status": "observed"},
        {"id": "C3", "statement": f"按原选择规则保留的模型验证MSE为{best_mse:.4f}，验证RMSE约{math.sqrt(best_mse):.2f}。", "evidence_ids": [best["id"]], "status": "observed"},
        {"id": "C4", "statement": f"与初始基线相比，记录中最低验证MSE的改善为{raw_gain:.3f}%；是否采用仍按固定{state['protocol']['min_relative_gain']*100:g}%门槛判断。", "evidence_ids": [t["id"] for t in recorded], "status": "observed"},
        {"id": "C5", "statement": "本研究未终测，不混入其他研究任务的测试成绩。" if state["final_evaluation"] is None else "终测结果与调参观察隔离；详见实验状态附件。", "evidence_ids": [campaign_id], "status": "limitation"},
        {"id": "C6", "statement": "这些记录支持工程流程与特定划分的比较，尚不支持跨域发现、临床有效性或LLM策略增益。", "evidence_ids": ["S1", "S2"], "status": "limitation"},
    ]
    question = "在固定公开数据和评价条件下，成分交互特征与正则化变化如何影响验证误差？"
    sections = [
        {"heading": "摘要", "paragraphs": [f"本研究对既有公开材料实验进行证据整合与独立复算，围绕模型复杂度、正则化与验证误差进行有限比较。共汇总{len(recorded)}个候选，按原固定门槛保留的模型验证MSE为{best_mse:.4f}。报告没有为得到改进而重设指标、筛选测试集或新训练模型。", f"决策来源标记为“{decision_origin}”；结果属于工程案例，模型及平台接入暂缓。本文组织可复核的研究论证与附件，不将脚本响应写成大模型研究能力。"], "claim_ids": ["C2", "C3", "C6"]},
        {"heading": "研究问题与依据", "paragraphs": [question, "Matbench原始论文提供公开材料性能预测任务与统一评价的背景。钢材成分并不能完整表示制备、热处理和微观结构条件，因此本案例限定为组成输入下的预测比较，不解释材料机制，也不据此推断医疗用途。", "官方Matbench采用统一的交叉验证基准。本项目使用独立记录的组成分组holdout和验证MSE，两者评价协议不同，不能直接引用排行榜差异作为本项目收益。"], "claim_ids": ["C1", "C6"]},
        {"heading": "研究假设", "paragraphs": ["先用低维线性配方建立参照，再检验成分交互特征是否降低验证误差。若训练误差下降而验证误差上升，应考虑复杂度与当前样本条件是否匹配；后续比较可回到线性配方或改变正则强度。", "每次具体假设和预期影响均保留在原提案中。它们是待检验主张；报告以实际指标与采用／拒绝记录判断，不把提案的预期写成实验结论。"], "claim_ids": ["C2", "C4"]},
        {"heading": "数据与评价设计", "paragraphs": [f"数据ID为{state['dataset_id']}。特征为归一化成分原子分数；划分规模为训练{state['dataset']['split_counts']['train']}、验证{len(y)}、保留测试{state['dataset']['split_counts']['test']}。组成分组规则、固定种子和数据哈希见附件。", f"选择标准固定为验证MSE，越低越好；相对当前保留模型改善必须严格超过{state['protocol']['min_relative_gain']*100:g}%才采用。候选不能更改数据划分或评分规则。验证集参与选择，故其误差不能作为未经选择偏差影响的泛化证明。", claims[4]["statement"]], "claim_ids": ["C1", "C4", "C5"]},
        {"heading": "模型与复算方法", "paragraphs": ["计算流程依次为无常数项的多项式特征、标准化与Ridge回归。alpha控制L2正则强度；更强正则不保证验证误差下降。候选阶数、alpha、实际软件版本和参数文件均以原工件为准。", "本轮不重新拟合，使用保存的变换与回归系数重建验证集预测，并按平方残差均值计算MSE。所有可用模型均与原记录指标核对；图表直接使用这些预测和原指标，未添加虚构误差条或重复实验。"], "claim_ids": ["C2", "C3"]},
        {"heading": "结果与比较", "paragraphs": [f"原规则保留模型的验证RMSE约为{math.sqrt(best_mse):.2f}，对应MSE为{best_mse:.4f}。模型选择结果与单纯取最小观察值不同，应保留预先确定的采用门槛。", claims[3]["statement"], "训练与验证误差的差异用于讨论复杂度和数据条件，不等于证实具体材料因果机制。结果表完整展示已有候选及拒绝记录，不只展示最优一次。"], "claim_ids": ["C3", "C4"]},
        {"heading": "局限与结论", "paragraphs": ["本案例受单次数据划分、成分信息缺失和有限候选影响，尚未进行多种子、匹配预算搜索基线或真实跨域外部验证。没有据此声称统计显著收益或材料新发现。", "当前可成立的结论是：既有结果能够在固定工件与数据版本下复算，原采用／拒绝规则可以追溯，并可据失败与无增益记录提出后续研究。完整产品的自主模型接入、平台编排及科学价值仍需独立验收。"], "claim_ids": ["C5", "C6"]},
        {"heading": "后续研究与复现", "paragraphs": ["后续可在另行确认的研究范围内检查缺失条件、合适的外部数据、多次重复与简单搜索对照。本页保存的后续问题是人工待执行记录，保存操作不发起训练或模型调用。", "复现附件提供原始模型、验证数据、指标和图表输入、来源及许可、计算源文件与独立验证脚本。运行verify_results.py可在不训练、不联网的条件下复算验证MSE并核对文件哈希。"], "claim_ids": ["C3", "C6"]},
    ]
    project = {"id": campaign_id, "title": "公开钢材数据上模型复杂度与正则化的比较研究", "question": question,
               "source_goal": state["goal"], "status": "evidence_ready", "labels": labels, "dataset": state["dataset"],
               "metrics": {"trials": len(recorded), "accepted": sum(t["status"] == "accepted" for t in recorded),
                           "rejected": sum(t["status"] == "rejected" for t in recorded), "best_validation_mse": best_mse,
                           "best_trial_id": state["best_trial_id"], "test_mse": state["final_evaluation"]["test_mse"] if state["final_evaluation"] else None},
               "trials": state["trials"], "sources": sources, "claims": claims,
               "figures": [{"id": "F1", "title": "模型复杂度与训练／验证误差", "url": "/api/figures/validation.svg", "caption": "来自已有试验的MSE，对数纵轴；没有重复试验误差条。"},
                           {"id": "F2", "title": "保留模型的验证集预测", "url": "/api/figures/prediction.svg", "caption": f"保存参数重建{len(y)}个验证样本预测；虚线为预测等于实测。验证参与选模，不作独立终测。"}],
               "report": {"title": "公开钢材数据上模型复杂度与正则化的比较研究", "sections": sections},
               "next_questions": [], "snapshot": {"sha256": report["state_sha256"], "source_campaign_id": campaign_id,
                                                 "created_at": datetime.now(timezone.utc).isoformat(), "mode": "frozen_existing_evidence"},
               "exports": {"pdf": "/api/export/paper.pdf", "reproduction": "/api/export/reproduction.zip"}}
    output.mkdir(parents=True, exist_ok=True)
    evidence = output / "evidence"
    (evidence / "models").mkdir(parents=True)
    (evidence / "source").mkdir()
    files = {}
    def write(relative, payload):
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        files[relative] = sha(payload)
    write("project.json", canonical(project).encode("utf-8"))
    write("evidence/experiment.json", canonical(report).encode("utf-8"))
    write("evidence/validation.csv", csv_bytes([*state["dataset"]["feature_names"], "target"], [list(row)+[float(target)] for row, target in zip(x, y)]))
    best_pred = predictions[state["best_trial_id"]]
    write("evidence/predictions.csv", csv_bytes(["observed", "predicted"], zip(y.tolist(), best_pred.tolist())))
    for trial_id, (_, payload) in models.items():
        write(f"evidence/models/{trial_id}.json", payload)
    for name in ("contracts.py", "datasets.py", "fixture.py", "training.py"):
        write("evidence/source/"+name, Path(__file__).with_name(name).read_bytes())
    write("evidence/data-attribution.md", Path(__file__).with_name("data").joinpath("README.md").read_bytes())
    write("evidence/environment.json", canonical({"export_python": sys.version, "model_libraries": {key: value[0].get("libraries", {}) for key, value in models.items()},
                                                  "original_training_code_sha256": {key: value[0].get("training_code_sha256") for key, value in models.items()},
                                                  "available_computation_source_sha256": training.code_identity()}).encode("utf-8"))
    atomic_text(output / "evidence-manifest.json", canonical({"version": "studio-evidence-v1", "files": files, "state_sha256": report["state_sha256"]}))
    ProjectStore(output)  # Establish a separate operator-notes database, never the source DB.
    return ProjectStore(output).project()


class ProjectStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        if not (self.root / "evidence-manifest.json").is_file():
            raise ResearchError("NOT_INITIALIZED", "prepare a studio project snapshot first")
        self.db = self.root / "studio.sqlite3"
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute("CREATE TABLE IF NOT EXISTS questions(id TEXT PRIMARY KEY,text TEXT NOT NULL,created_at TEXT NOT NULL,status TEXT NOT NULL)")

    def verify(self):
        manifest = json.loads((self.root / "evidence-manifest.json").read_text(encoding="utf-8"))
        if manifest.get("version") != "studio-evidence-v1":
            raise ResearchError("INVALID_ARTIFACT", "unsupported evidence manifest")
        required = {"project.json", "evidence/experiment.json", "evidence/validation.csv", "evidence/predictions.csv",
                    "evidence/data-attribution.md", "evidence/environment.json"}
        required.update("evidence/source/"+name for name in ("contracts.py","datasets.py","fixture.py","training.py"))
        if not isinstance(manifest.get("files"), dict) or not required.issubset(manifest["files"]):
            raise ResearchError("INVALID_ARTIFACT", "required frozen evidence is missing from the manifest")
        for relative, expected in manifest["files"].items():
            path = (self.root / relative).resolve()
            if not path.is_relative_to(self.root) or not path.is_file() or sha(path.read_bytes()) != expected:
                raise ResearchError("ARTIFACT_CHANGED", "frozen evidence or computation input changed")
        project = json.loads((self.root / "project.json").read_text(encoding="utf-8"))
        for trial in project["trials"]:
            if trial.get("model_artifact"):
                identifier(trial["id"], "trial_id")
                required.add("evidence/models/"+trial["id"]+".json")
        if set(manifest["files"]) != required:
            raise ResearchError("INVALID_ARTIFACT", "model manifest differs from the frozen trial list")
        return manifest

    def project(self):
        self.verify()
        value = json.loads((self.root / "project.json").read_text(encoding="utf-8"))
        with closing(sqlite3.connect(self.db)) as con:
            con.row_factory = sqlite3.Row
            value["next_questions"] = [dict(row) for row in con.execute("SELECT * FROM questions ORDER BY created_at,id")]
        return value

    def add_question(self, text):
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1500 or "\x00" in text:
            raise ResearchError("INVALID_REQUEST", "后续研究问题需为1至1500字，不能包含空字符。")
        self.verify()
        item = {"id": uuid.uuid4().hex, "text": text.strip(), "created_at": datetime.now(timezone.utc).isoformat(), "status": "saved_pending_execution"}
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT count(*) FROM questions").fetchone()[0] >= 50:
                raise ResearchError("QUESTION_LIMIT", "当前项目最多保存50条后续问题。")
            con.execute("INSERT INTO questions VALUES(:id,:text,:created_at,:status)", item)
        return item
