"""Standalone C01 archive audit and bounded, reproducible local analysis.

This reads cached XLSX values with stdlib XML, never executes formulas or code,
never downloads data, and does not reproduce the unknown original ML pipeline.
Dependencies: numpy/scikit-learn; matplotlib is optional for static figures.
"""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import sys
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import sklearn
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

EXPECTED_ARCHIVE_SHA256 = "f6687161b0014e4ac6d904fb4920b45456451eebdc1bf9d9dce57140eaa80653"
SCHEMA_VERSION = "c01-analysis-v1"
DOI = "10.17632/tt7gwkpck8.1"
MAIN = "TNZST_Summary table.xlsx"
BIO = "TNZST_Summary table_bio.xlsx"
ATTACHMENTS = (MAIN, BIO, "TNZST_SFE calculation ver 3.xlsx", "TNZST_XRD.xlsx", "TNZST_Eng_Stress_vs_Eng_Strain.csv")
FEATURES = ("ecm_gpa", "yield_mpa", "water_contact_angle_deg", "sfe_owrk_total_mn_m")
FEATURE_COLUMNS = {"ecm_gpa": "P", "yield_mpa": "R", "water_contact_angle_deg": "W", "sfe_owrk_total_mn_m": "AN"}
TARGETS = (
    {"id": "cell_seeding_efficiency_24h_pct", "label": "24小时细胞接种效率", "unit": "%", "column": "AP", "bio_column": "C"},
    {"id": "dna_cell_count_d21", "label": "d21 DNA值（原表约细胞计数）", "unit": "as-reported approximate cell count", "column": "BJ", "bio_column": "R"},
    {"id": "alp_norm_d21", "label": "d21 ALP原表数值（单位及归一化待核）", "unit": "as-reported; unit/normalization unconfirmed", "column": "BV", "bio_column": "U"},
    {"id": "calcium_deposition_d21_ug_ml", "label": "d21钙沉积原表数值", "unit": "ug/mL", "column": "BX", "bio_column": "V"},
)
OUTPUT_MANIFEST = "output-manifest.json"
OUTPUT_MANIFEST_VERSION = "c01-output-manifest-v1"
OUTPUT_BASE_FILES = frozenset({"summary.json", "source-manifest.json", "audit.csv", "cleaned_samples.csv",
                               "loo_predictions.csv", "rounds.csv", "evidence/input.zip", *(
                                   "evidence/attachments/"+name for name in ATTACHMENTS)})
OUTPUT_FIGURES = ("figures/loo_mae.svg", "figures/loo_predictions.svg")
N = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
LIMITATIONS = [
    "只有8个合金聚合样本；SD和不同日期没有扩成独立样本。",
    "留一法重复使用同一组8个样本，不是独立外部验证；第二轮还受第一轮反馈影响。",
    "材料特征与体外终点的数值关系仅作描述和小样本探索，不支持因果、临床有效性、长期安全性或最佳材料结论。",
    "没有原始分析源码，不能宣称复现原作者或队员的训练流程；这里只复算本文件定义的协议。",
    "ALP单位及归一化、B标签星号和实验重复结构尚未确认。",
    "预测未裁剪；超出接种率0–100%或ALP非负数值域的预测不能解释为有效生物预测。",
]


class C01Error(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def _safe_zip(data, *, nested=False):
    limit = 12_000_000 if nested else 20_000_000
    if len(data) > (8_000_000 if not nested else 2_000_000):
        raise C01Error("ARCHIVE_LIMIT", "输入压缩包超过大小限制。")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        items = archive.infolist()
        if not items or len(items) > (128 if nested else 64) or sum(i.file_size for i in items) > limit:
            raise C01Error("ARCHIVE_LIMIT", "压缩包成员数量或解压总量超过限制。")
        names = set()
        for item in items:
            name = item.filename
            raw_name = item.orig_filename
            path = PurePosixPath(raw_name)
            mode = item.external_attr >> 16
            if (not name or "\x00" in raw_name or "\\" in raw_name or ":" in raw_name or path.is_absolute() or ".." in path.parts
                    or name in names or stat.S_ISLNK(mode) or item.flag_bits & 1):
                raise C01Error("UNSAFE_ARCHIVE", "压缩包存在重复、加密或不安全的成员路径。")
            if item.file_size > 8_000_000 or item.file_size > max(1, item.compress_size) * 500:
                raise C01Error("ARCHIVE_LIMIT", "压缩包成员大小或压缩比超过限制。")
            names.add(name)
        return archive
    except (zipfile.BadZipFile, OSError):
        raise C01Error("INVALID_ARCHIVE", "输入不是有效ZIP文件。") from None


def _xml(data):
    if len(data) > 4_000_000 or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise C01Error("UNSAFE_XML", "工作簿XML超过限制或包含实体声明。")
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        raise C01Error("INVALID_WORKBOOK", "工作簿XML无法读取。") from None


def _workbook(data):
    with _safe_zip(data, nested=True) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = ["".join(t.text or "" for t in item.findall(".//s:t", N))
                      for item in _xml(archive.read("xl/sharedStrings.xml")).findall("s:si", N)]
        book = _xml(archive.read("xl/workbook.xml"))
        sheet = book.find("s:sheets/s:sheet", N)
        if sheet is None:
            raise C01Error("INVALID_WORKBOOK", "工作簿没有数据表。")
        relationship = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        rels = _xml(archive.read("xl/_rels/workbook.xml.rels"))
        match = next((r for r in rels if r.get("Id") == relationship), None)
        if match is None or match.get("TargetMode") == "External":
            raise C01Error("INVALID_WORKBOOK", "工作簿的数据表关系无效。")
        target = match.get("Target", "")
        member = target.lstrip("/") if target.startswith("/xl/") else "xl/" + target
        if ".." in PurePosixPath(member).parts or "\\" in member or member not in archive.namelist():
            raise C01Error("INVALID_WORKBOOK", "工作簿数据表路径无效。")
        cells = {}
        for cell in _xml(archive.read(member)).findall("s:sheetData/s:row/s:c", N):
            ref = cell.get("r", "")
            if not ref or ref in cells or len(cells) >= 50_000:
                raise C01Error("INVALID_WORKBOOK", "工作簿单元格重复或超过限制。")
            value, formula = cell.find("s:v", N), cell.find("s:f", N)
            raw = value.text or "" if value is not None else ""
            if cell.get("t") == "s":
                try:
                    raw = shared[int(raw)]
                except (ValueError, IndexError):
                    raise C01Error("INVALID_WORKBOOK", "工作簿共享文本索引无效。") from None
            elif cell.get("t") == "inlineStr":
                raw = "".join(t.text or "" for t in cell.findall("s:is//s:t", N))
            cells[ref] = {"raw": raw, "formula": formula.text if formula is not None else None}
        return {"sheet": sheet.get("name", ""), "cells": cells}


def parse_measurement(value):
    raw = str(value).strip()
    if raw.startswith("<"):
        try:
            upper = float(raw[1:].strip())
        except ValueError:
            upper = None
        if upper is not None and not math.isfinite(upper):
            upper = None
        return {"value": None, "raw": raw, "status": "left_censored_upper_bound", "upper_bound": upper}
    try:
        number = float(raw)
        if not math.isfinite(number):
            raise ValueError
        return {"value": number, "raw": raw, "status": "numeric", "upper_bound": None}
    except ValueError:
        return {"value": None, "raw": raw, "status": "missing_or_non_numeric", "upper_bound": None}


def _numeric(book, cell):
    parsed = parse_measurement(book["cells"].get(cell, {}).get("raw", ""))
    if parsed["status"] != "numeric":
        raise C01Error("INVALID_DATA", "分析所需的确认字段缺失、删失或不是有限数值：" + cell)
    return parsed["value"]


def _audit(field, issue, handling, *, source="case-package", cell="", raw="", severity="limitation", origin="manual_pre_review"):
    return {"field": field, "issue": issue, "handling": handling, "source": source,
            "cell": cell, "raw": raw, "severity": severity, "origin": origin}


def load_archive(archive_path):
    path = Path(archive_path)
    if not path.is_file() or path.stat().st_size > 8_000_000:
        raise C01Error("INVALID_ARCHIVE", "需要本地C01原始ZIP文件，且大小不超过8MB。")
    data = path.read_bytes()
    # Validate paths and resource bounds even when identity is wrong.
    with _safe_zip(data) as archive:
        files = {}
        manifest = []
        for item in archive.infolist():
            if item.is_dir():
                continue
            payload = archive.read(item)
            manifest.append({"member": item.filename, "bytes": len(payload), "sha256": _sha(payload),
                             "role": "raw_attachment" if "/attachments/" in item.filename else "team_supplied_derived_or_note"})
            basename = PurePosixPath(item.filename).name
            if basename in files:
                raise C01Error("UNSAFE_ARCHIVE", "压缩包包含同名输入文件。")
            files[basename] = payload
    if _sha(data) != EXPECTED_ARCHIVE_SHA256:
        raise C01Error("ARCHIVE_CHANGED", "C01原始包SHA与已核对版本不同，需人工核查。")
    if any(name not in files for name in ATTACHMENTS):
        raise C01Error("MISSING_EVIDENCE", "C01包缺少必需原始附件。")
    main, bio = _workbook(files[MAIN]), _workbook(files[BIO])
    audit = [
        _audit("source_doi", "包内摘要DOI少了末尾字符8。", "按本轮人工核对使用 " + DOI + "；本程序不联网复核。"),
        _audit("proliferation_rate_*", "两表同名异义：主表为相对增长百分比，bio表为绝对细胞增量/天。", "全部排除，不合并为同一指标；不作为输入特征。", source=MAIN+" / "+BIO),
        _audit("edx_o_1_pct", "清洗表把主表L列氧误标为EDX；L列属于ICP OES。", "识别为ICP-OES氧含量；不作为本次特征。", source=MAIN, cell="L3:L4"),
        _audit("yield_to_modulus_ratio", "原数值直接用MPa/GPa相除，不能称无量纲。", "不作为特征。无量纲比值须用yield_MPa/(Ecm_GPa*1000)。", source=MAIN, cell="V5:V12"),
        _audit("eym_pct;ra_mm;rsm_mm", "应变百分数及粗糙度单位需要方法学复核。", "本次不使用这些特征。", source=MAIN),
        _audit("bio_label", "B标签与Alloy无显式主键，部分B标签有未定义星号。", "按行顺序核对共享数值，仅记录一致性；不当成已证实的批次或重复标识。", source=BIO),
        _audit("ml_pipeline", "未提供原分析源码与完整训练协议。", "只声明本文件协议可复算，不声明复现原训练流程。"),
        _audit("license", "包内声明CC BY 4.0，本次未联网独立核定许可。", "保留原包、来源声明与DOI，分发前由操作者核查许可。"),
        _audit("xlsx_cached_values", "数值来自原工作簿缓存，未重新求值Excel公式。", "记录单元格出处及公式文本，不执行工作簿公式。", source=MAIN+" / "+BIO),
        _audit("alp_norm_d21", "归一化方法和单位未充分说明。", "仅称d21 ALP原表数值；不作成骨能力或临床等级标签。", source=MAIN, cell="BV4"),
        _audit("stress_strain;XRD;SFE_workbook", "应力单位和原始专业计算流程未核定。", "保留原附件，不拟合应力单位、识峰或重算SFE公式。"),
    ]
    samples, provenance, mapping = [], [], []
    fields = {**FEATURE_COLUMNS, **{target["id"]: target["column"] for target in TARGETS}}
    for index in range(8):
        row, bio_row = index + 5, index + 7
        alloy = main["cells"].get("A"+str(row), {}).get("raw")
        if alloy != "Alloy " + str(index+1):
            raise C01Error("INVALID_DATA", "主表8个合金的标识或行顺序不符合已核对版本。")
        sample = {"sample_id": alloy}
        for name, column in fields.items():
            cell = column + str(row)
            sample[name] = _numeric(main, cell)
            provenance.append({"sample_id": alloy, "field": name, "source": MAIN,
                               "sheet": main["sheet"], "cell": cell, **main["cells"][cell]})
        samples.append(sample)
        pairs = [(target["column"], target["bio_column"]) for target in TARGETS] + [("AT", "H"), ("BP", "G")]
        differences = [abs(_numeric(main, a+str(row))-_numeric(bio, b+str(bio_row))) for a,b in pairs]
        mapping.append({"sample_id": alloy, "bio_label": bio["cells"].get("B"+str(bio_row), {}).get("raw", ""),
                        "shared_fields_compared": 6, "max_abs_difference": max(differences),
                        "consistent_with_row_mapping": max(differences) <= 1e-6})
    for cell, record in main["cells"].items():
        parsed = parse_measurement(record["raw"])
        if parsed["status"] == "left_censored_upper_bound":
            audit.append(_audit("censored_measurement", "<x 是左删失上界，不能作为实测x或0。",
                                "本次不使用；原值保留，上界="+str(parsed["upper_bound"]),
                                source=MAIN, cell=cell, raw=record["raw"], severity="excluded",origin="program_check"))
        elif "see other file" in record["raw"].lower():
            audit.append(_audit("unresolved_measurement", "单元格指向其他文件而非数值。", "保留为缺失，不填0。",
                                source=MAIN, cell=cell, raw=record["raw"], severity="excluded",origin="program_check"))
    return {"archive": data, "files": files, "source": {"archive_sha256": _sha(data), "archive_bytes": len(data),
        "doi": DOI, "doi_url": "https://doi.org/"+DOI, "license_statement": "CC BY 4.0 (claimed in input package)",
        "license_verification": "not_independently_verified_in_this_run", "files": manifest},
        "samples": samples, "provenance": provenance, "bio_mapping": mapping, "audit": audit}


def loo_predictions(x, y, alpha):
    """Both standardization and Ridge fit only the seven training rows per fold."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if x.ndim != 2 or len(x) != 8 or y.shape != (8,) or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)) or np.ptp(y) == 0:
        raise C01Error("INVALID_DATA", "留一分析要求8行有限数值且目标不为常数。")
    predicted, baseline = [], []
    for held_out in range(8):
        train = np.arange(8) != held_out
        pipeline = make_pipeline(StandardScaler(), Ridge(alpha=alpha, solver="svd"))
        pipeline.fit(x[train], y[train])
        predicted.append(float(pipeline.predict(x[held_out:held_out+1])[0]))
        baseline.append(float(np.mean(y[train])))
    return np.asarray(predicted), np.asarray(baseline)


def _metrics(y, predicted, baseline):
    denominator = float(np.sum((y-np.mean(y))**2))
    def score(values):
        error = values-y
        return float(np.mean(np.abs(error))), float(np.sqrt(np.mean(error**2))), 1-float(np.sum(error**2))/denominator
    mae, rmse, r2 = score(predicted)
    bmae, brmse, br2 = score(baseline)
    return {"mae": mae, "rmse": rmse, "r2": r2, "baseline_mae": bmae, "baseline_rmse": brmse,
            "baseline_r2": br2, "mae_relative_change_vs_baseline": (mae-bmae)/bmae,
            "better_than_baseline": mae < bmae}


def _round(samples, ordinal, alpha, features):
    x = np.asarray([[sample[name] for name in features] for sample in samples])
    scores, predictions, violations = [], [], []
    for target in TARGETS:
        y = np.asarray([sample[target["id"]] for sample in samples])
        predicted, baseline = loo_predictions(x, y, alpha)
        scores.append({"target": target["id"], "target_label": target["label"], "target_unit": target["unit"],
                       "n": 8, "alpha": alpha, "feature_names": list(features), **_metrics(y, predicted, baseline)})
        for index, sample in enumerate(samples):
            rule=""
            if target["id"]=="cell_seeding_efficiency_24h_pct" and not 0<=predicted[index]<=100:
                rule="cell_seeding_efficiency_outside_0_100_percent"
            elif target["id"]=="alp_norm_d21" and predicted[index]<0:
                rule="alp_reported_value_below_zero"
            if rule:
                violations.append({"target":target["id"],"target_label":target["label"],"sample_id":sample["sample_id"],
                                   "predicted":float(predicted[index]),"rule":rule,"handling":"not_clipped_not_valid_biological_prediction"})
            predictions.append({"round_id": "R"+str(ordinal), "target": target["id"], "sample_id": sample["sample_id"],
                "observed": float(y[index]), "predicted": float(predicted[index]), "baseline_predicted": float(baseline[index]),
                "training_n": 7, "training_sample_ids": ";".join(row["sample_id"] for i,row in enumerate(samples) if i!=index),"domain_flag":rule})
    worse = sum(not score["better_than_baseline"] for score in scores)
    feedback=f"4个目标中有{worse}个目标的MAE不低于逐折7样本均值基线。"
    if violations:
        feedback+=" 数值域警告（预测未裁剪，不代表有效生物预测）："+"；".join(
            f"{item['sample_id']} / {item['target_label']}={item['predicted']:.6g}" for item in violations)+"。"
    return {"id": "R"+str(ordinal), "title": "固定四特征留一比较" if ordinal==1 else "反馈后的敏感性比较",
            "method": "leave_one_alloy_out / fold_fitted_StandardScaler_Ridge_svd",
            "alpha": alpha, "feature_names": list(features), "status": "executed",
            "feedback": feedback,"domain_violations":violations,
            "metrics": scores, "limitations": LIMITATIONS,
            "next_action": "先核对重复结构与单位，并增加独立样本；不据此选出最佳材料。"}, predictions


def render_figures(directory, rounds, predictions):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return [], "optional_matplotlib_unavailable", None
    directory.mkdir()
    figures = []
    with plt.rc_context({"svg.hashsalt": "c01-analysis-v1", "font.family": "DejaVu Sans"}):
        fig, axis = plt.subplots(figsize=(9,4.8))
        positions = np.arange(len(TARGETS))
        width = .32
        for index, result in enumerate(rounds):
            ratios = [metric["mae"]/metric["baseline_mae"] for metric in result["metrics"]]
            axis.bar(positions+(index-(len(rounds)-1)/2)*width, ratios, width, label=result["id"], color=("#668876","#aa9680")[index])
        axis.axhline(1,color="#686868",ls="--",lw=1,label="7-row training mean baseline")
        axis.set_xticks(positions,["24h seeding", "d21 DNA (reported)", "d21 ALP (reported)", "d21 calcium"])
        axis.set_ylabel("LOO MAE / LOO mean-baseline MAE")
        axis.set_title("C01: 8 alloys; exploratory reused-sample comparison")
        axis.legend(fontsize=8);fig.tight_layout()
        file = directory/"loo_mae.svg";fig.savefig(file,metadata={"Date":None,"Creator":"AutoResearch C01"});plt.close(fig)
        figures.append({"id":"F-C01-1","title":"留一MAE与逐折均值基线比较","path":"figures/loo_mae.svg",
                        "caption":"同8个合金的探索性复算；1为逐折7样本均值基线，非独立验证。"})
        fig, axes = plt.subplots(2,2,figsize=(9,7))
        for axis,target in zip(axes.flat,TARGETS):
            for index,result in enumerate(rounds):
                values=[row for row in predictions if row["target"]==target["id"] and row["round_id"]==result["id"]]
                axis.scatter([row["observed"] for row in values],[row["predicted"] for row in values],label=result["id"],color=("#668876","#aa9680")[index],s=25)
            values=[row for row in predictions if row["target"]==target["id"] and row["round_id"]=="R1"]
            low=min([row["observed"] for row in values]+[row["predicted"] for row in predictions if row["target"]==target["id"]])
            high=max([row["observed"] for row in values]+[row["predicted"] for row in predictions if row["target"]==target["id"]])
            axis.plot([low,high],[low,high],ls="--",color="#9b9b9b",lw=1)
            axis.set_title(target["id"],fontsize=9);axis.set_xlabel("Observed (as reported)",fontsize=8);axis.set_ylabel("LOO prediction",fontsize=8);axis.legend(fontsize=8)
        fig.suptitle("C01 exploratory LOO; no independent validation",fontsize=11);fig.tight_layout()
        file=directory/"loo_predictions.svg";fig.savefig(file,metadata={"Date":None,"Creator":"AutoResearch C01"});plt.close(fig)
        figures.append({"id":"F-C01-2","title":"原表终点与留一预测","path":"figures/loo_predictions.svg",
                        "caption":"每点为一个合金聚合样本；ALP单位及归一化待核，虚线仅为数值相等参考线。"})
    return figures, "generated", matplotlib.__version__


def _write_csv(path, rows, columns):
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=columns,extrasaction="ignore")
        writer.writeheader();writer.writerows(rows)


def _output_error():
    return C01Error("OUTPUT_INTEGRITY_FAILED", "C01固定产物或SHA清单校验失败；不接受缺项、额外路径或变更结果。")


def _output_root(output_dir):
    requested=Path(output_dir)
    if requested.is_symlink() or getattr(requested,"is_junction",lambda:False)():
        raise _output_error()
    root=requested.resolve(strict=True)
    if not root.is_dir():
        raise _output_error()
    return root


def _read_output(root, relative):
    # Callers supply only names from the constant whitelist, never a manifest path.
    path=root
    for part in PurePosixPath(relative).parts:
        path=path/part
        if path.is_symlink() or getattr(path,"is_junction",lambda:False)():
            raise _output_error()
    metadata=path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink>1 or metadata.st_size>8_000_000:
        raise _output_error()
    return path.read_bytes()


def _strict_output_json(payload):
    if len(payload)>1_000_000:
        raise _output_error()
    def unique(pairs):
        value={}
        for key,item in pairs:
            if key in value:
                raise _output_error()
            value[key]=item
        return value
    def invalid(_):
        raise _output_error()
    return json.loads(payload.decode("utf-8"),object_pairs_hook=unique,parse_constant=invalid)


def _expected_output_files(summary):
    if not isinstance(summary,dict) or summary.get("schema_version")!=SCHEMA_VERSION or summary.get("case_id")!="C01-TNZST":
        raise _output_error()
    artifacts=summary.get("artifacts")
    fixed={"summary":"summary.json","source_manifest":"source-manifest.json","audit":"audit.csv",
           "cleaned_samples":"cleaned_samples.csv","predictions":"loo_predictions.csv","round_metrics":"rounds.csv",
           "original_archive":"evidence/input.zip","output_manifest":OUTPUT_MANIFEST}
    if not isinstance(artifacts,dict) or any(artifacts.get(key)!=value for key,value in fixed.items()):
        raise _output_error()
    if artifacts.get("raw_attachments")!=["evidence/attachments/"+name for name in ATTACHMENTS]:
        raise _output_error()
    figures=artifacts.get("figures")
    if summary.get("figure_status")=="generated":
        if (not isinstance(figures,list) or len(figures)!=2 or any(not isinstance(item,dict) for item in figures)
                or [item.get("path") for item in figures]!=list(OUTPUT_FIGURES)
                or [item.get("id") for item in figures]!=["F-C01-1","F-C01-2"]):
            raise _output_error()
        return OUTPUT_BASE_FILES|set(OUTPUT_FIGURES)
    if summary.get("figure_status")!="optional_matplotlib_unavailable" or figures!=[]:
        raise _output_error()
    return OUTPUT_BASE_FILES


def _check_output_tree(root, expected):
    allowed_directories={"evidence","evidence/attachments"}
    if any(name.startswith("figures/") for name in expected):
        allowed_directories.add("figures")
    seen=set()
    def visit(directory, prefix=""):
        children=list(directory.iterdir())
        if len(children)>32:
            raise _output_error()
        for path in children:
            relative=prefix+path.name
            if path.is_symlink() or getattr(path,"is_junction",lambda:False)():
                raise _output_error()
            if path.is_dir():
                if relative not in allowed_directories:
                    raise _output_error()
                visit(path,relative+"/")
            else:
                if relative not in expected|{OUTPUT_MANIFEST}:
                    raise _output_error()
                seen.add(relative)
    visit(root)
    if seen!=expected|{OUTPUT_MANIFEST}:
        raise _output_error()


def verify_output(output_dir):
    """Read-only, fail-closed artifact validation; return the verified summary.

    The manifest is an integrity record, not a signature. Its own hash is omitted
    to avoid self-reference. No path from the manifest is opened until the exact
    constant file set has been checked; unknown files/directories are rejected.
    """
    try:
        root=_output_root(output_dir)
        manifest=_strict_output_json(_read_output(root,OUTPUT_MANIFEST))
        if not isinstance(manifest,dict) or set(manifest)!={"schema_version","files"} or manifest.get("schema_version")!=OUTPUT_MANIFEST_VERSION:
            raise _output_error()
        files=manifest.get("files")
        if not isinstance(files,dict) or set(files) not in (OUTPUT_BASE_FILES,OUTPUT_BASE_FILES|set(OUTPUT_FIGURES)):
            raise _output_error()
        if any(not isinstance(value,str) or not re.fullmatch(r"[0-9a-f]{64}",value) for value in files.values()):
            raise _output_error()
        payloads={name:_read_output(root,name) for name in sorted(files)}
        if any(_sha(payload)!=files[name] for name,payload in payloads.items()):
            raise _output_error()
        summary=_strict_output_json(payloads["summary.json"])
        expected=_expected_output_files(summary)
        if set(files)!=expected:
            raise _output_error()
        _check_output_tree(root,expected)
        source=summary.get("source")
        if not isinstance(source,dict) or source.get("archive_sha256")!=_sha(payloads["evidence/input.zip"]):
            raise _output_error()
        return summary
    except C01Error:
        raise
    except (OSError,ValueError,TypeError,KeyError,RecursionError):
        raise _output_error() from None


def _write_output_manifest(output, summary):
    expected=_expected_output_files(summary)
    manifest={"schema_version":OUTPUT_MANIFEST_VERSION,
              "files":{name:_sha(_read_output(output,name)) for name in sorted(expected)}}
    with (output/OUTPUT_MANIFEST).open("x",encoding="utf-8",newline="\n") as stream:
        stream.write(_json(manifest))


def analyze_archive(archive_path, output_dir, *, rounds=2):
    if type(rounds) is not int or rounds not in (1,2):
        raise C01Error("INVALID_REQUEST", "仅允许1或2轮本地分析。")
    requested=Path(output_dir)
    if requested.is_symlink() or getattr(requested,"is_junction",lambda:False)():
        raise C01Error("UNSAFE_OUTPUT", "输出目录不能是链接。")
    output=requested.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise C01Error("OUTPUT_EXISTS", "输出目录必须不存在或为空；不会覆盖既有结果。")
    bundle=load_archive(archive_path)
    first,predictions=_round(bundle["samples"],1,1.0,FEATURES)
    results=[first]
    if rounds==2:
        stronger=any(not metric["better_than_baseline"] for metric in first["metrics"])
        features=FEATURES if stronger else ("ecm_gpa","water_contact_angle_deg")
        second,more=_round(bundle["samples"],2,100.0 if stronger else 1.0,features)
        second["selection_rule"]="any_R1_MAE_not_better_then_alpha100_else_two_features"
        second["based_on_round"]="R1"
        second["selection_warning"]="规则在本分析版本中固定，但数据与包内探索结果已经可见；同一8样本被重复使用，不构成无偏选模证据。"
        results.append(second);predictions.extend(more)
    if "loo_ridge_summary.csv" in bundle["files"]:
        rows=list(csv.DictReader(io.StringIO(bundle["files"]["loo_ridge_summary.csv"].decode("utf-8-sig"))))
        for row in rows:
            match=next((metric for metric in first["metrics"] if metric["target"]==row.get("target")),None)
            if not match:
                continue
            try:
                provided=float(row["mean_baseline_mae"])
            except (KeyError,ValueError):
                continue
            y=np.asarray([sample[row["target"]] for sample in bundle["samples"]])
            global_mae=float(np.mean(np.abs(y-y.mean())))
            if math.isclose(provided,global_mae,rel_tol=1e-9,abs_tol=1e-9) and not math.isclose(provided,match["baseline_mae"],rel_tol=1e-9):
                bundle["audit"].append(_audit(row["target"],"包内基线数值等于全8样本均值基线，不等于逐折7样本均值基线。",
                    "本次基线每折只取训练7行均值；不据无源码结果推断原训练实现。",source="loo_ridge_summary.csv",raw=str(provided),origin="program_check"))
    output.mkdir(parents=True,exist_ok=True)
    # Recheck immediately before writing; every named data file uses exclusive create.
    if any(output.iterdir()):
        raise C01Error("OUTPUT_EXISTS", "输出目录已非空，不会覆盖既有结果。")
    evidence=output/"evidence";attachments=evidence/"attachments";attachments.mkdir(parents=True)
    with (evidence/"input.zip").open("xb") as stream:
        stream.write(bundle["archive"])
    for name in ATTACHMENTS:
        with (attachments/name).open("xb") as stream:
            stream.write(bundle["files"][name])
    figures,figure_status,matplotlib_version=render_figures(output/"figures",results,predictions)
    _write_csv(output/"cleaned_samples.csv",bundle["samples"],["sample_id",*FEATURES,*[target["id"] for target in TARGETS]])
    _write_csv(output/"audit.csv",bundle["audit"],["field","issue","handling","source","cell","raw","severity","origin"])
    _write_csv(output/"loo_predictions.csv",predictions,["round_id","target","sample_id","observed","predicted","baseline_predicted","training_n","training_sample_ids","domain_flag"])
    flat=[]
    for result in results:
        flat.extend({"round_id":result["id"],**metric,"feature_names":";".join(metric["feature_names"])} for metric in result["metrics"])
    _write_csv(output/"rounds.csv",flat,["round_id","target","target_label","target_unit","n","alpha","feature_names","mae","rmse","r2","baseline_mae","baseline_rmse","baseline_r2","mae_relative_change_vs_baseline","better_than_baseline"])
    source_manifest={**bundle["source"],"provenance":bundle["provenance"],"bio_mapping":bundle["bio_mapping"]}
    with (output/"source-manifest.json").open("x",encoding="utf-8",newline="\n") as stream:
        stream.write(_json(source_manifest))
    summary={"schema_version":SCHEMA_VERSION,"case_id":"C01-TNZST","origin":"local_recomputable_analysis_not_llm",
        "scientific_status":"small_sample_descriptive_exploration","source":bundle["source"],
        "data":{"sample_count":8,"sample_unit":"alloy_aggregate","feature_names":list(FEATURES),
                "targets":[{"id":target["id"],"label":target["label"],"unit":target["unit"]} for target in TARGETS],
                "excluded_fields":["proliferation_rate_*","edx_o_1_pct","yield_to_modulus_ratio","eym_pct","ra_mm","rsm_mm","censored_*","all_biological_predictors","all_SD_predictors"],
                "split_protocol":"leave_one_alloy_out_8_folds_each_training7","baseline":"training_fold_mean_only",
                "formula_handling":"cached_values_only_no_formula_execution"},
        "rounds":results,"audit":bundle["audit"],"audit_policy":"manual_pre_review entries come from human package review; program_check entries are deterministic checks, not autonomous scientific discoveries",
        "limitations":LIMITATIONS,"figure_status":figure_status,
        "environment":{"python":platform.python_version(),"numpy":np.__version__,"scikit_learn":sklearn.__version__,"matplotlib":matplotlib_version},
        "analysis_code_sha256":_sha(Path(__file__).read_bytes()),
        "artifacts":{"summary":"summary.json","source_manifest":"source-manifest.json","audit":"audit.csv",
                     "cleaned_samples":"cleaned_samples.csv","predictions":"loo_predictions.csv","round_metrics":"rounds.csv",
                     "original_archive":"evidence/input.zip","raw_attachments":["evidence/attachments/"+name for name in ATTACHMENTS],"figures":figures,
                     "output_manifest":OUTPUT_MANIFEST},
        "cloud_calls":0,"model_calls":0}
    with (output/"summary.json").open("x",encoding="utf-8",newline="\n") as stream:
        stream.write(_json(summary))
    _write_output_manifest(output,summary)
    return verify_output(output)


def main(argv=None):
    if hasattr(sys.stdout,"reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description="C01 bounded local audit and exploratory LOO analysis; no network/model calls")
    parser.add_argument("--archive",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--rounds",type=int,choices=(1,2),default=2)
    args=parser.parse_args(argv)
    try:
        result=analyze_archive(args.archive,args.output,rounds=args.rounds)
        print(_json(result));return 0
    except C01Error as exc:
        print(_json({"ok":False,"error":{"code":exc.code,"message":str(exc)}}));return 2


if __name__=="__main__":
    raise SystemExit(main())
