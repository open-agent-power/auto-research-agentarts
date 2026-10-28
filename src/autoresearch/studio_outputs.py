"""Figures, paper and an allowlisted validation-reproduction attachment."""
import csv
import io
import json
from pathlib import Path
import threading
import zipfile

from .contracts import ResearchError, canonical, fingerprint
from .studio_project import ProjectStore, atomic_text, csv_bytes, sha


class ProjectOutputs:
    def __init__(self, store):
        self.store = store if isinstance(store, ProjectStore) else ProjectStore(store)
        self.lock = threading.RLock()
        self.figures = self.store.root / "figures"
        self.exports = self.store.root / "exports"
        self._export_key = None

    def render_figures(self, project):
        try:
            import matplotlib
            matplotlib.use("Agg")
            from matplotlib import pyplot as plt
        except ImportError:
            raise ResearchError("REPORT_DEPENDENCY_REQUIRED", "install .[reports] to generate figures and paper") from None
        self.figures.mkdir(exist_ok=True)
        trials = [t for t in project["trials"] if t.get("model_artifact")]
        with plt.rc_context({"svg.hashsalt": "autoresearch-frozen-v1", "font.family": "DejaVu Sans", "font.size": 10}):
            fig, ax = plt.subplots(figsize=(8, 3.7), layout="constrained")
            positions = list(range(len(trials)))
            for offset, key, label, color in ((-.18, "training_mse", "Training MSE", "#648777"),
                                               (.18, "validation_mse", "Validation MSE", "#b87759")):
                values = [t["metrics"][key] for t in trials]
                bars = ax.bar([p + offset for p in positions], values, width=.34, label=label, color=color)
                ax.bar_label(bars, labels=[f"{v:,.0f}" for v in values], fontsize=8, padding=4)
            ax.set_xticks(positions, [f"T{i+1}: degree {t['candidate']['degree']}, alpha {t['candidate']['alpha']:g}" for i,t in enumerate(trials)])
            ax.set_ylabel("MSE (MPa squared; log scale)")
            ax.set_yscale("log")
            ax.margins(y=.25)
            ax.legend(frameon=False, loc="upper left")
            ax.grid(axis="y", alpha=.15)
            for suffix in ("png", "svg"):
                fig.savefig(self.figures / ("validation."+suffix), dpi=180, metadata={"Date": None} if suffix == "svg" else {})
            plt.close(fig)
            with (self.store.root / "evidence/predictions.csv").open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            observed = [float(row["observed"]) for row in rows]
            predicted = [float(row["predicted"]) for row in rows]
            fig, ax = plt.subplots(figsize=(7.6, 4.2), layout="constrained")
            ax.scatter(observed, predicted, color="#35624f", alpha=.75, s=26, edgecolors="white", linewidths=.4)
            lower, upper = min(observed+predicted), max(observed+predicted)
            ax.plot([lower, upper], [lower, upper], "--", color="#9b725d", label="Predicted = observed")
            ax.set(xlabel="Observed yield strength (MPa)", ylabel="Predicted yield strength (MPa)")
            ax.legend(frameon=False)
            ax.grid(alpha=.15)
            for suffix in ("png", "svg"):
                fig.savefig(self.figures / ("prediction."+suffix), dpi=180, metadata={"Date": None} if suffix == "svg" else {})
            plt.close(fig)
        table = csv_bytes(["trial", "degree", "alpha", "training_mse", "validation_mse", "decision"],
                          [[t["id"],t["candidate"]["degree"],t["candidate"]["alpha"],t["metrics"]["training_mse"],t["metrics"]["validation_mse"],t["status"]] for t in trials])
        (self.figures / "comparison.csv").write_bytes(table)
        hashes = {name: sha((self.figures/name).read_bytes()) for name in
                  ("validation.png", "validation.svg", "prediction.png", "prediction.svg", "comparison.csv")}
        atomic_text(self.figures / "figure-manifest.json", canonical({"files": hashes, "snapshot": project["snapshot"]["sha256"]}))

    def figure(self, name):
        if name not in {"validation.svg", "prediction.svg"}:
            raise ResearchError("NOT_FOUND", "figure not available")
        with self.lock:
            project = self.store.project()
            # Regenerate from checked evidence; never serve an unverified substituted SVG.
            self.render_figures(project)
            return (self.figures / name).read_bytes()

    def export(self):
        with self.lock:
            project = self.store.project()
            key = fingerprint(project)
            if key == self._export_key and all((self.exports/name).is_file() and
                    sha((self.exports/name).read_bytes()) == digest for name,digest in self._export_hashes.items()):
                return self._export_result
            self.render_figures(project)
            self.exports.mkdir(exist_ok=True)
            from .paper_export import render_paper
            result = render_paper(project, self.figures, self.exports / "research-paper.pdf")
            files = {"project.json": canonical(project).encode("utf-8")}
            manifest = self.store.verify()
            # Explicit payload names: never recurse over the experiment or operator workspace.
            allowed = {"evidence/experiment.json", "evidence/validation.csv", "evidence/predictions.csv",
                       "evidence/data-attribution.md", "evidence/environment.json"}
            allowed.update("evidence/source/"+n for n in ("contracts.py","datasets.py","fixture.py","training.py"))
            allowed.update("evidence/models/"+t["id"]+".json" for t in project["trials"] if t.get("model_artifact"))
            for name in sorted(allowed):
                if name not in manifest["files"]:
                    raise ResearchError("INVALID_ARTIFACT", "a required reproduction input is missing")
                files[name] = (self.store.root/name).read_bytes()
            for name in ("validation.png","validation.svg","prediction.png","prediction.svg","comparison.csv","figure-manifest.json"):
                files["figures/"+name] = (self.figures/name).read_bytes()
            files["research-paper.pdf"] = Path(result["path"]).read_bytes()
            files["verify_results.py"] = Path(__file__).with_name("reproduction_verifier.py").read_bytes()
            files["README.md"] = ("# 冻结研究证据与验证复算\n\n"
                "运行 `python verify_results.py`（Python 3.11+，仅标准库）。它核对附件哈希，使用保存参数和62条验证数据复算每个候选的验证MSE，并核对保留模型图表输入；不训练、不联网、不读取密钥。\n\n"
                "本附件用于已有验证结果的独立复算；不是从头重新训练的完整环境。原始训练数据不在附件中，数据来源、固定版本、划分及计算源文件见evidence。指标仍受验证选模偏差影响，不能替代独立终测。\n\n"
                "package-manifest.json是传输完整性校验，不是作者签名或科学正确性认证；请从可信来源取得整包。project.json保存完整主张、引用和人工后续问题；后续问题尚未执行。\n\n"
                "材料数据许可与署名见evidence/data-attribution.md；第三方文献仅列引用链接，未将论文全文重新分发。当前模型与平台接入暂缓。\n").encode("utf-8")
            files["package-manifest.json"] = canonical({"version":"validation-reproduction-v1", "files":{name:sha(data) for name,data in files.items()}}).encode("utf-8")
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name,data in sorted(files.items()):
                    archive.writestr(name,data)
            archive_path = self.exports / "reproduction.zip"
            temporary = archive_path.with_suffix(".zip.tmp")
            temporary.write_bytes(buffer.getvalue())
            temporary.replace(archive_path)
            self._export_key = key
            self._export_hashes = {"research-paper.pdf":sha(Path(result["path"]).read_bytes()), "reproduction.zip":sha(archive_path.read_bytes())}
            self._export_result = {"pdf":result, "reproduction":{"path":str(archive_path), "sha256":self._export_hashes["reproduction.zip"], "files":len(files)}, "new_training_runs":0, "cloud_calls":0}
            return self._export_result
