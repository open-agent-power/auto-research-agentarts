#!/usr/bin/env python3
"""Plot saved G3-L grouped-validation OOF only; never fits or opens a manager."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import statistics

os.environ["MPLBACKEND"] = "Agg"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "runs/g3-local-transfer-20261113-01"
CONCRETE = ROOT / "runs/cloud-concrete-local-20261113-01"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory(root):
    return {str(p.relative_to(ROOT)): sha(p) for p in root.rglob("*") if p.is_file()}


def read_case(name):
    root = CASE / name
    data = list((root / "manager/inputs").rglob(name + ".csv"))
    assert len(data) == 1
    with data[0].open() as f:
        rows = list(csv.DictReader(f))
    arms, sources = {}, {str(data[0].relative_to(ROOT)): sha(data[0])}
    for path in (root / "manager/projects").rglob("artifacts/action-*.json"):
        envelope = json.loads(path.read_text())
        analysis = envelope.get("tool_result", {}).get("result", {}).get("analysis", {})
        if "oof" not in analysis:
            continue
        arm = "log1p_age" if analysis["protocol"].get("input_basis") else "raw"
        assert arm not in arms
        predictions = {r["logical_record"]: r for r in analysis["oof"]}
        assert len(predictions) == len(rows)
        assert set(predictions) == set(range(1, len(rows) + 1))
        for index, row in enumerate(rows, 1):
            assert int(row["source_row"]) == index
            assert float(row[analysis["target_column"]]) == predictions[index]["observed"]
        arms[arm] = {"action_id": envelope["action_id"], "analysis": analysis, "predictions": predictions}
        sources[str(path.relative_to(ROOT))] = sha(path)
    assert set(arms) == ({"raw", "log1p_age"} if name == "real-estate" else {"raw"})
    return rows, arms, sources


def errors(arm):
    return [abs(p["predicted"] - p["observed"]) for _, p in sorted(arm["predictions"].items())]


def reference_errors(arm):
    return [abs(p["reference_prediction"] - p["observed"]) for _, p in sorted(arm["predictions"].items())]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "runs/g3-local-figures")
    args = parser.parse_args()
    output = args.output.resolve()
    assert output.is_relative_to(ROOT / "runs") and output not in (CASE, CONCRETE)
    assert not output.is_relative_to(CASE) and not output.is_relative_to(CONCRETE)
    assert not output.exists(), "refusing existing output directory"
    protected = {**inventory(CASE), **inventory(CONCRETE)}
    output.mkdir(parents=True)
    re_rows, re_arms, re_sources = read_case("real-estate")
    sl_rows, sl_arms, sl_sources = read_case("slump")
    raw, candidate = re_arms["raw"], re_arms["log1p_age"]
    for key in raw["predictions"]:
        a, b = raw["predictions"][key], candidate["predictions"][key]
        assert all(a[f] == b[f] for f in ("observed", "fold", "groups", "reference_prediction", "physical_line_end"))
    raw_err, candidate_err = errors(raw), errors(candidate)
    delta = [b - a for a, b in zip(raw_err, candidate_err)]
    assert sum(d > 0 for d in delta) == 179 and sum(d < 0 for d in delta) == 235
    ages = [float(r["house_age"]) for r in re_rows]
    slump = sl_arms["raw"]
    sl_err, sl_ref = errors(slump), reference_errors(slump)
    assert sum(a > b for a, b in zip(sl_err, sl_ref)) == 20
    means = {"real_estate": {"raw": statistics.mean(raw_err), "candidate_log1p_age": statistics.mean(candidate_err),
                              "training_fold_mean_reference": statistics.mean(reference_errors(raw))},
             "slump": {"raw": statistics.mean(sl_err), "training_fold_mean_reference": statistics.mean(sl_ref)}}
    for arm in (raw, candidate, slump):
        assert math.isclose(statistics.mean(errors(arm)), arm["analysis"]["summary"]["candidate_mae"], rel_tol=1e-12)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titleweight": "bold", "svg.fonttype": "none"})
    blue, green, gray, red = "#2563eb", "#0f766e", "#94a3b8", "#c2410c"
    fig, axes = plt.subplots(2, 2, figsize=(14, 9.5))
    fig.subplots_adjust(left=.09, right=.97, bottom=.12, top=.84, hspace=.57, wspace=.33)
    fig.suptitle("Method transfer: saved grouped-validation results", x=.09, y=.965, ha="left", fontsize=21, fontweight="bold")
    fig.text(.09, .91, "UCI Real Estate (414 rows / 259 coordinate groups)  |  UCI Slump (103 rows / 103 ingredient groups)", fontsize=11, color="#334155")
    fig.text(.09, .875, "Five-fold GroupKFold, training-fold scaling and Ridge. Figures read stored predictions only; no new fits.", fontsize=11, color="#334155")

    ax = axes[0, 0]
    values = list(means["real_estate"].values())
    bars = ax.bar(["Raw Ridge", "log1p(age) Ridge", "Fold-mean\nreference"], values, color=[blue, green, gray], width=.62)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + .15, f"{value:.3f}", ha="center", fontsize=12)
    ax.set_ylim(0, max(values) * 1.2)
    ax.set_ylabel("Mean absolute error\n(10,000 NTD / Ping)")
    ax.set_title("A  Real Estate: modest aggregate improvement", loc="left", pad=13, fontsize=12)
    ax.text(.03, .94, "Raw to candidate: -2.14% MAE", transform=ax.transAxes, va="top", fontsize=10, color="#334155")
    ax.yaxis.grid(True, alpha=.2)
    ax.set_axisbelow(True)

    ax = axes[0, 1]
    for adverse, color, label in ((False, blue, "235 improved rows"), (True, red, "179 worsened rows")):
        indices = [i for i, d in enumerate(delta) if (d > 0) == adverse]
        ax.scatter([ages[i] for i in indices], [delta[i] for i in indices], s=18, alpha=.6,
                   color=color, edgecolors="none", label=label, rasterized=False)
    ax.axhline(0, color="#475569", linewidth=1)
    ax.set_xlabel("House age (years)")
    ax.set_ylabel("Candidate minus raw absolute error\n(10,000 NTD / Ping)")
    ax.set_title("B  Real Estate: paired row changes", loc="left", pad=13, fontsize=12)
    ax.legend(loc="lower right", frameon=True, fontsize=9)
    ax.text(.02, .97, "Above zero = worse after log1p(age)", transform=ax.transAxes, va="top", fontsize=9, color=red)
    ax.grid(alpha=.15)

    ax = axes[1, 0]
    values = list(means["slump"].values())
    bars = ax.bar(["Raw Ridge", "Fold-mean reference"], values, color=[blue, gray], width=.5)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + .1, f"{value:.3f}", ha="center", fontsize=12)
    ax.set_ylim(0, max(values) * 1.28)
    ax.set_ylabel("Mean absolute error (MPa)")
    ax.set_title("C  Slump: baseline comparison only", loc="left", pad=13, fontsize=12)
    ax.text(.03, .96, "No varying-age input; no candidate was run", transform=ax.transAxes, va="top", fontsize=10, color="#334155")
    ax.yaxis.grid(True, alpha=.2)
    ax.set_axisbelow(True)

    ax = axes[1, 1]
    predictions = [r for _, r in sorted(slump["predictions"].items())]
    observed = [r["observed"] for r in predictions]
    predicted = [r["predicted"] for r in predictions]
    ax.scatter(observed, [r["reference_prediction"] for r in predictions], color=gray, s=14, alpha=.4, label="Fold-mean reference")
    for adverse, color, label in ((False, blue, "83 no worse than reference"), (True, red, "20 worse than reference")):
        indices = [i for i, (a, b) in enumerate(zip(sl_err, sl_ref)) if (a > b) == adverse]
        ax.scatter([observed[i] for i in indices], [predicted[i] for i in indices], s=23, alpha=.75, color=color,
                   edgecolors="white", linewidths=.2, label=label)
    maximum = max(observed + predicted) * 1.05
    ax.plot([0, maximum], [0, maximum], color="#475569", linestyle="--", linewidth=1, label="Prediction = observed")
    ax.set_xlim(0, maximum)
    ax.set_ylim(0, maximum)
    ax.set_xlabel("Observed 28-day strength (MPa)")
    ax.set_ylabel("Saved out-of-fold prediction (MPa)")
    ax.set_title("D  Slump: individual predictions and errors", loc="left", pad=13, fontsize=12)
    ax.legend(loc="upper left", fontsize=8, frameon=True)
    ax.grid(alpha=.15)

    fig.text(.09, .055, "Scope: grouped interpolation on selected public data; coordinate/ingredient equality are declared grouping proxies.", fontsize=10, color="#475569")
    fig.text(.09, .03, "No causal memory benefit, new-region validation, automatic promotion or cross-domain scientific validity is established.", fontsize=10, color="#475569")
    png, svg = output / "tabular-transfer.png", output / "tabular-transfer.svg"
    fig.savefig(png, dpi=180, facecolor="white")
    fig.savefig(svg, facecolor="white", metadata={"Description": "Saved G3-L grouped-validation OOF; no new fits; units separated by dataset."})
    plt.close(fig)
    assert protected == {**inventory(CASE), **inventory(CONCRETE)}, "original case files changed"
    summary = {"source_case": str(CASE.relative_to(ROOT)), "source_files": {**re_sources, **sl_sources},
               "means": means, "real_estate_paired": {"improved": 235, "worsened": 179, "rows": 414},
               "slump_worse_than_reference": 20, "slump_rows": 103, "slump_candidate": "not_applicable_not_run",
               "protected_files_unchanged": len(protected), "new_fits": 0, "model_api_calls": 0,
               "script_sha256": sha(Path(__file__)), "outputs": {png.name: sha(png), svg.name: sha(svg)},
               "limits": "Descriptive saved grouped-validation only; no causal or domain-validity inference"}
    (output / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"outputs": summary["outputs"], "means": means, "protected_files_unchanged": len(protected)}))


if __name__ == "__main__":
    main()
