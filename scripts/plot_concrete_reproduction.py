"""Plot saved observations only; does not create projects, fit or dispatch tools."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    case, output = Path(args.case), Path(args.output)
    if output.exists():
        raise ValueError("Use a fresh derived-output directory; retain previous evidence")
    records = [json.loads((case / (name + "-age-diagnostics.json")).read_text()) for name in ("baseline", "candidate")]
    if any(r["saved_summary"]["n"] != 1030 for r in records):
        raise ValueError("Require full case coverage")
    output.mkdir(parents=True)
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), sharex=True, sharey=True, layout="constrained")
    for ax, label, record, color in zip(axes, ("Raw age baseline", "Fixed log1p age"), records, ("#345d9d", "#087f6b")):
        rows = record["rows"]
        ax.scatter([r["observed"] for r in rows], [r["predicted"] for r in rows], s=12, alpha=.4, color=color, edgecolors="none")
        negative = [r for r in rows if r["predicted"] < 0]
        if negative:
            ax.scatter([r["observed"] for r in negative], [r["predicted"] for r in negative], s=70, facecolors="none", edgecolors="#b42318", linewidths=1.5, label=f"{len(negative)} negative prediction")
            ax.legend(loc="upper left", frameon=False, fontsize=9)
        ax.plot([-5, 85], [-5, 85], color="#777777", lw=1, ls="--")
        ax.set(xlim=(-5, 85), ylim=(-5, 85), xlabel="Observed strength (MPa)", title=f"{label}\nOOF MAE {record['saved_summary']['candidate_mae']:.3f} MPa")
        ax.grid(alpha=.15)
    axes[0].set_ylabel("Saved held-out prediction (MPa)")
    fig.suptitle("Same-data grouped evaluation: all 1,030 observations retained")
    fig.savefig(output / "oof-comparison.png", dpi=180)
    fig.savefig(output / "oof-comparison.svg")
    plt.close(fig)

    buckets = [r["input_profiles"][0]["buckets"] for r in records]
    ages = [b["value"] for b in buckets[0]]
    if ages != [b["value"] for b in buckets[1]]:
        raise ValueError("Exact observed age strata differ")
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True, layout="constrained")
    for label, series, color in zip(("Raw age baseline", "Fixed log1p age"), buckets, ("#345d9d", "#087f6b")):
        axes[0].plot(range(len(ages)), [b["mean_error"] for b in series], marker="o", lw=1.5, label=label, color=color)
        axes[1].plot(range(len(ages)), [b["candidate_mae"] for b in series], marker="o", lw=1.5, label=label, color=color)
    axes[0].axhline(0, color="#777777", ls="--", lw=1)
    axes[0].set_ylabel("Mean prediction − observation (MPa)")
    axes[0].legend(frameon=False)
    axes[1].set(ylabel="MAE (MPa)", xlabel="Exact age in days; n is observed row count")
    axes[1].set_xticks(range(len(ages)), [f"{int(a)}\nn={b['n']}" for a, b in zip(ages, buckets[0])], fontsize=8)
    for ax in axes:
        ax.grid(alpha=.15)
    fig.suptitle("Local errors and sparse coverage remain visible; no external validation")
    fig.savefig(output / "age-errors.png", dpi=180)
    fig.savefig(output / "age-errors.svg")
    plt.close(fig)
    receipt = {"kind": "derived_saved_arithmetic_visualization", "model_fits": 0, "tool_dispatches": 0, "matplotlib_version": matplotlib.__version__, "inputs": {name: hashlib.sha256((case / name).read_bytes()).hexdigest() for name in ["baseline-age-diagnostics.json", "candidate-age-diagnostics.json"]}, "outputs": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}}
    (output / "manifest.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
