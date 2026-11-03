"""Trace the archived six-column hiMSC B8S1 CSV to saved workbook cells offline."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from autoresearch.chemotopo_data import SOURCES, read_workbook
from autoresearch.contracts import ResearchError

HEADERS = ("Topo", "Chem", "Coordinate", "Count", "Mean_Red_Intensity", "Mean_Green_Intensity")
SHEET = "B8S1"
ARCHIVED_CSV_SHA256 = "880485da61b3d850dc53d03746b7f6068229bf2ec94d510a69fa0c45f049118b"
METADATA_SHA256 = "2600412f5ea578933a13c9d9051a82d69c6f5e55377951ae9a7ef39cdffe05fb"
METADATA_SHEET = "iMSC_B8S1"
METADATA_HEADERS = ("Series", "Topo", "Chem", "Row")
EMPTY_CELL = {"value": None, "raw": "", "status": "missing", "formula_present": False, "formula": None}


def _require(condition, message, code="SOURCE_LINKAGE_INVALID"):
    if not condition:
        raise ResearchError(code, message)


def _number(text):
    try:
        value = float(text)
        return value if math.isfinite(value) else None
    except ValueError:
        return None


def _compare(text, cell, ref, header):
    status = cell["status"]
    expected = cell["raw"] if status == "finite" else cell["value"] if status == "text" else "" if status == "missing" else None
    exact = expected is not None and text == expected
    number = _number(text)
    numeric_equal = number == cell["value"] if number is not None and status == "finite" else None
    kind = ("numeric_cache_text_exact" if exact and status == "finite" else "decoded_text_exact" if exact and status == "text"
            else "missing_exact" if exact else "numeric_value_equal_text_diff" if numeric_equal else "stored_value_mismatch")
    return {"column": header, "workbook_cell": SHEET + "!" + ref, "csv_text": text,
            "workbook_value": cell["value"], "workbook_raw": cell["raw"], "workbook_status": status,
            "formula_present": cell["formula_present"], "formula": cell["formula"],
            "projected_cache_text": expected, "exact_projection_match": exact,
            "numeric_value_match": numeric_equal, "comparison": kind}


def inspect_linkage(csv_raw, workbook_raw):
    """Compare decoded text and exact numeric cache strings; never infer row joins."""
    reader = csv.reader(io.StringIO(csv_raw.decode("utf-8-sig"), newline=""), strict=True)
    _require(tuple(next(reader, ())) == HEADERS, "CSV must contain exactly the six B8S1 headers.")
    book = read_workbook(workbook_raw)
    _require(SHEET in book, "Workbook is missing B8S1.")
    cells = book[SHEET]
    for index, header in enumerate(HEADERS):
        ref = chr(65 + index) + "1"
        _require(cells.get(ref, EMPTY_CELL)["value"] == header, "Workbook header differs at " + SHEET + "!" + ref)
    rows, zero_rows, mismatches = [], [], []
    comparisons, joint, zero_counts = Counter(), Counter(), Counter()
    formula_cells = 0
    for logical_record, values in enumerate(reader, 1):
        _require(len(values) == 6, "CSV row width differs at logical record " + str(logical_record))
        workbook_row = logical_record + 1
        points = [_compare(value, cells.get(chr(65 + index) + str(workbook_row), EMPTY_CELL),
                           chr(65 + index) + str(workbook_row), HEADERS[index]) for index, value in enumerate(values)]
        for point in points:
            comparisons[point["comparison"]] += 1
            formula_cells += point["formula_present"]
            if not point["exact_projection_match"]:
                mismatches.append({"logical_record": logical_record, "csv_physical_line_end": reader.line_num, **point})
        group = dict(zip(HEADERS[:3], values[:3]))
        numeric = [_number(value) for value in values[3:]]
        mask = "unknown" if None in numeric else "".join("1" if value == 0 else "0" for value in numeric)
        joint[mask] += 1
        zero_columns = [name for name, value in zip(HEADERS[3:], numeric) if value == 0]
        zero_counts.update(zero_columns)
        row = {"logical_record": logical_record, "csv_physical_line_end": reader.line_num,
               "workbook_row": workbook_row, "group": group, "zero_mask": mask,
               "all_six_cells_match": all(point["exact_projection_match"] for point in points), "cells": points}
        rows.append(row)
        if zero_columns:
            zero_rows.append({key: row[key] for key in ("logical_record", "csv_physical_line_end", "workbook_row", "group", "zero_mask", "all_six_cells_match")}
                             | {"zero_columns": zero_columns, "numeric_cells": points[3:]})
    workbook_rows = {int(match[1]) for ref, cell in cells.items()
                     if (match := re.fullmatch(r"[A-F]([0-9]+)", ref)) and int(match[1]) > 1 and cell["status"] != "missing"}
    expected_rows = set(range(2, len(rows) + 2))
    missing_rows, extra_rows = sorted(expected_rows - workbook_rows), sorted(workbook_rows - expected_rows)
    exact_count = sum(point["exact_projection_match"] for row in rows for point in row["cells"])
    return {"schema_version": "himsc-source-linkage-v1", "sheet": SHEET, "headers": list(HEADERS),
        "projection_rule": "CSV logical data record n maps to B8S1 workbook row n+1; finite numeric XML cache text is retained exactly; text cells are decoded; absent cells are empty. Formulas are never evaluated.",
        "comparison_rule": "Exact projection match is separate from numeric value equality. workbook_raw for a shared-string cell is its XML string index, not its decoded text.",
        "coverage": {"csv_records": len(rows), "workbook_data_rows": len(workbook_rows), "compared_cells": len(rows) * 6,
            "exact_projection_matches": exact_count, "all_six_cells_matched_rows": sum(row["all_six_cells_match"] for row in rows),
            "mismatch_cells": len(mismatches), "missing_workbook_rows": missing_rows, "extra_workbook_rows": extra_rows,
            "formula_present_cells": formula_cells, "comparison_counts": dict(comparisons),
            "complete_projection_match": bool(rows) and exact_count == len(rows) * 6 and not missing_rows and not extra_rows},
        "zero_cooccurrence": {"mask_order": list(HEADERS[3:]), "mask_legend": "1 means numeric zero in that column; 0 means finite nonzero; unknown means at least one numeric value could not be established.",
            "joint_masks": {format(mask, "03b"): joint[format(mask, "03b")] for mask in range(8)} | {"unknown": joint["unknown"]},
            "per_column_zero_counts": {name: zero_counts[name] for name in HEADERS[3:]}, "any_zero_rows": len(zero_rows),
            "all_three_zero_rows": joint["111"], "partial_zero_rows": sum(count for mask, count in joint.items() if mask not in ("000", "111", "unknown")),
            "inference_boundary": "Equal per-column zero totals do not establish co-occurrence; the joint masks are computed directly for every CSV row."},
        "unknowns": {"zero_cause": "unknown", "ALP_endpoint_identity": "unknown", "independent_experimental_unit": "unknown",
                     "image_metadata_join": "not_performed"},
        "rows": rows, "mismatches": mismatches, "zero_rows": zero_rows, "scientific_validation": False,
        "model_calls": 0, "new_fits": 0, "research_project_operations": 0}


def _metadata_records(raw):
    book = read_workbook(raw)
    _require(METADATA_SHEET in book, "Metadata workbook is missing iMSC_B8S1.")
    cells = book[METADATA_SHEET]
    for index, header in enumerate(METADATA_HEADERS):
        _require(cells.get(chr(65 + index) + "1", EMPTY_CELL)["value"] == header, "Unexpected metadata header: " + header)
    row_ids = sorted({int(match[1]) for ref, cell in cells.items()
                      if (match := re.fullmatch(r"[A-D]([0-9]+)", ref)) and int(match[1]) > 1 and cell["status"] != "missing"})
    rows = {row: {name: {"sheet": METADATA_SHEET, "cell": chr(65 + index) + str(row),
                                **cells.get(chr(65 + index) + str(row), EMPTY_CELL)}
                  for index, name in enumerate(METADATA_HEADERS)} for row in row_ids}
    _require(all(point["status"] == "finite" for values in rows.values() for point in values.values()),
             "The four current metadata fields must have finite saved numeric caches.")
    return rows, len(book)


def _key_profile(index, columns):
    return {"columns": columns, "unique_keys": len(index), "duplicate_keys": sum(len(rows) > 1 for rows in index.values()),
            "max_candidate_rows": max((len(rows) for rows in index.values()), default=0),
            "ambiguous_keys": [{"key": list(key), "metadata_rows": rows} for key, rows in index.items() if len(rows) > 1]}


def inspect_metadata(audit, raw):
    """Test saved layout keys and same-position correspondence; do not infer image IDs."""
    metadata, sheet_count = _metadata_records(raw)
    tc, tcr, series = defaultdict(list), defaultdict(list), defaultdict(list)
    for row, points in metadata.items():
        key = points["Topo"]["value"], points["Chem"]["value"]
        tc[key].append(row)
        tcr[key + (points["Row"]["value"],)].append(row)
        series[(points["Series"]["value"],)].append(row)
    records, mismatches = [], []
    zeros_by_row, totals_by_row = Counter(), Counter(points["Row"]["value"] for points in metadata.values())
    for source in audit["rows"]:
        row = source["workbook_row"]
        key = tuple(point["workbook_value"] for point in source["cells"][:2])
        points = metadata.get(row)
        matched = points is not None and key == (points["Topo"]["value"], points["Chem"]["value"])
        coordinate = source["cells"][2]["workbook_value"]
        expected_label = "_".join(str(int(value)) for value in key) if all(type(v) in (int, float) and float(v).is_integer() for v in key) else None
        ordered_series = points is not None and points["Series"]["value"] == source["logical_record"] - 1
        record = {"logical_record": source["logical_record"], "raw_workbook_row": row, "zero_mask": source["zero_mask"],
            "source_coordinate_cell": f"B8S1!C{row}", "source_Coordinate": coordinate,
            "coordinate_matches_Topo_Chem_label": expected_label is not None and coordinate == expected_label,
            "same_position_topo_chem_match": matched, "Series_equals_zero_based_data_position": ordered_series,
            "Topo_Chem_candidate_metadata_rows": tc.get(key, []),
            "same_position_metadata": points,
            "correspondence_status": "saved_layout_position_keys_verified" if matched else "not_established",
            "join_basis": ["same saved data row position", "saved Topo and Chem values equal"] if matched else [],
            "unique_image_or_observation_join": False,
            "limitation": "Raw source has no Series or Row field. A checked position or layout key is not proof of image/frame/object export identity or independent sampling."}
        if matched and ordered_series:
            record["join_basis"].append("metadata Series equals CSV record minus one; observed order relation only")
        records.append(record)
        if not matched or not ordered_series or not record["coordinate_matches_Topo_Chem_label"]:
            mismatches.append(record)
        if matched and source["zero_mask"] == "111":
            zeros_by_row[points["Row"]["value"]] += 1
    sample_ids = [row for row in (2, 3, 38, 326, 973) if row in metadata]
    return {"schema_version": "himsc-layout-correspondence-v1", "metadata_sheet": METADATA_SHEET, "workbook_sheet_count": sheet_count,
        "headers": list(METADATA_HEADERS), "checks": {"source_records": len(audit["rows"]), "metadata_records": len(metadata),
            "same_position_topo_chem_matches": sum(row["same_position_topo_chem_match"] for row in records),
            "Series_equals_zero_based_data_position": sum(row["Series_equals_zero_based_data_position"] for row in records),
            "Coordinate_equals_Topo_Chem_label": sum(row["coordinate_matches_Topo_Chem_label"] for row in records),
            "missing_metadata_rows": sorted({row["workbook_row"] for row in audit["rows"]} - metadata.keys()),
            "extra_metadata_rows": sorted(metadata.keys() - {row["workbook_row"] for row in audit["rows"]})},
        "keys": {"Topo_Chem": _key_profile(tc, ["Topo", "Chem"]), "Topo_Chem_Row": _key_profile(tcr, ["Topo", "Chem", "Row"]),
                 "Series": _key_profile(series, ["Series"])},
        "saved_Row_values": sorted(totals_by_row),
        "zero_counts_by_saved_row": [{"saved_Row_value": value, "total_metadata_records": count,
            "all_three_zero_rows_in_verified_same_position": zeros_by_row[value]} for value, count in sorted(totals_by_row.items())],
        "samples": [{"metadata_row": row, "cells": metadata[row]} for row in sample_ids],
        "layout_position_correspondence_complete": len(records) == len(metadata) and not mismatches,
        "rows": records, "mismatches": mismatches, "zero_rows": [row for row in records if row["zero_mask"] == "111"],
        "unknowns": {"Series_acquisition_or_frame_semantics": "unknown", "Row_physical_or_batch_semantics": "unknown",
                     "image_or_object_export_link": "unknown", "ALP_endpoint_identity": "unknown", "independence": "unknown"},
        "interpretation": "Only saved layout keys and row-order relations are checked. Coordinate encodes the Topo/Chem label when equal; repeated keys and all candidate metadata rows are retained. Row and Series are not assumed to be source CSV line numbers or acquisition identifiers."}


def _metadata_markdown(metadata):
    checks, keys = metadata["checks"], metadata["keys"]
    lines = ["", "## 作者metadata的可证对应", "",
        f"已读取作者工作簿的{METADATA_SHEET}。同序Topo/Chem相等{checks['same_position_topo_chem_matches']}/{checks['source_records']}条；Series等于CSV数据记录号减一{checks['Series_equals_zero_based_data_position']}条；原Coordinate等于Topo_Chem标签{checks['Coordinate_equals_Topo_Chem_label']}条。",
        f"Row实际保存值为{metadata['saved_Row_values']}。Series唯一键{keys['Series']['unique_keys']}个；Topo/Chem重复键{keys['Topo_Chem']['duplicate_keys']}个，最多{keys['Topo_Chem']['max_candidate_rows']}条候选；加上metadata的Row后仍有{keys['Topo_Chem_Row']['duplicate_keys']}个重复键，最多{keys['Topo_Chem_Row']['max_candidate_rows']}条候选。",
        "原始表没有Series或Row字段。相同行序加两键核对是一种有明确依据的layout对应，不是独立的图像/对象导出链；zero-metadata.csv保留所有同键候选，不能把重复键当作唯一连接。", "",
        "| 保存的Row值 | metadata记录数 | 同序核对通过的111零行数 |", "|---|---:|---:|"]
    lines.extend(f"| {row['saved_Row_value']} | {row['total_metadata_records']} | {row['all_three_zero_rows_in_verified_same_position']} |" for row in metadata["zero_counts_by_saved_row"])
    lines.extend(["", "该表是保存layout字段的描述性交叉计数，不赋予Row物理位置、采集批次或独立重复的含义。真实原单元格样例及全部差异/多解见audit.json的metadata。", "",
        "请作者补充：Series 0..971究竟对应哪种原始标识、如何从每个Series追到图像文件和对象级导出？Row 1..9的实际含义是什么？例如iMSC_B8S1!A38:D38保存Series36/Topo1/Chem24/Row1，不能把Row1解释为CSV第1行，也不能仅凭Series连续就称其采集frame。", ""])
    return lines


def _markdown(audit):
    cover, zero = audit["coverage"], audit["zero_cooccurrence"]
    first = audit["zero_rows"][0] if audit["zero_rows"] else None
    example = "B8S1!D" + str(first["workbook_row"]) + ":F" + str(first["workbook_row"]) if first else "B8S1!D2:F973"
    lines = ["# hiMSC B8S1：CSV与工作簿逐行取证", "",
        f"CSV共{cover['csv_records']}行、6列；核对{cover['compared_cells']}个数据单元格。严格投影匹配{cover['exact_projection_matches']}个，不匹配{cover['mismatch_cells']}个；整行6列均匹配{cover['all_six_cells_matched_rows']}行。",
        "CSV数据记录n对应工作簿第n+1行。数字比较保留原XML缓存文本，字符串比较解码后的内容；数值相同但文本不同另列，不算严格投影匹配。全部逐格定位见audit.json的rows和mismatches。", "",
        "## 原件身份", "", "| 原件 | 字节数 | SHA-256 |", "|---|---:|---|"]
    for label, identity in audit["sources"].items():
        lines.append(f"| {label} | {identity['bytes']} | `{identity['sha256']}` |")
    lines.extend(["", "原工作簿须与已归档版本完全一致才继续；CSV归档字节身份与逐格内容匹配分别报告。",
        f"CSV字节与归档投影一致：{audit['archived_csv_bytes_match']}。六列中含公式的单元格数：{cover['formula_present_cells']}；未执行公式。", "",
        "## 三列零值是否在同一行", "", "位顺序固定为Count、Mean_Red_Intensity、Mean_Green_Intensity；1表示该列为数值零，0表示有限非零。", "",
        "| 同行掩码 | 行数 |", "|---|---:|"])
    lines.extend(f"| {mask} | {count} |" for mask, count in zero["joint_masks"].items())
    lines.extend(["", f"三列各自零值数：{zero['per_column_zero_counts']}。至少一列为零{zero['any_zero_rows']}行，三列同时为零{zero['all_three_zero_rows']}行，仅部分列为零{zero['partial_zero_rows']}行。",
        "以上共现结论来自逐行掩码，不能由三个列总数恰好相同推出。每一零行的CSV记录号、原工作簿行号、Topo/Chem/Coordinate标签和D/E/F单元格见zero-rows.csv。", "",
        "## 请作者明确回答的问题", "",
        f"1. 请核对zero-rows.csv列出的{zero['any_zero_rows']}条记录（例如{example}）：Count及两通道的零分别表示什么？它们是有效测量、没有分割对象、缺失值替代、QC排除，还是其他情况？请给出采集/分析/导出中的具体赋值规则。",
        "2. 当Count=0时，计算两通道均值的程序是否直接写0？请提供对应软件版本、分割和汇总公式，说明零分母、无对象及缺失值分别如何导出。共现本身不能证明该规则存在。",
        "3. B8S1列E的Mean_Red_Intensity对应什么染色、探针或生物学终点？ALP身份仍未确认；请给出通道设置、信号定义、背景处理和单位，并标明来源文件及行/单元格。",
        "4. 相同Topo/Chem/Coordinate标签的每条原始行对应图像、视野、spot、chip还是独立生物实验？请提供工作簿行号到原始图像/样本ID、批次和重复单位的映射；已取得的layout对应也不替代这条运行来源证据。", "",
        "## Limitations", "",
        "已核对保存值的投影及同行零值分布。保存值一致不证明上游测量有效、零值原因、ALP终点或实验独立性；layout对应的范围单列，原始记录未更改。", ""])
    if "metadata" in audit:
        insertion = lines.index("## Limitations")
        lines[insertion:insertion] = _metadata_markdown(audit["metadata"])
    return "\n".join(lines)


def _write_outputs(output, audit):
    output.mkdir(parents=True, exist_ok=False)
    (output / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (output / "README.md").write_text(_markdown(audit), encoding="utf-8")
    fields = ["logical_record", "csv_physical_line_end", "workbook_row", "Topo", "Chem", "Coordinate", "zero_mask", "all_six_cells_match"]
    fields += [name + suffix for name in HEADERS[3:] for suffix in ("_cell", "_csv_text", "_workbook_raw", "_workbook_status")]
    with (output / "zero-rows.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for zero in audit["zero_rows"]:
            row = {key: zero[key] for key in fields[:3] + ["zero_mask", "all_six_cells_match"]} | zero["group"]
            for point in zero["numeric_cells"]:
                name = point["column"]
                row.update({name + "_cell": point["workbook_cell"], name + "_csv_text": point["csv_text"],
                            name + "_workbook_raw": point["workbook_raw"], name + "_workbook_status": point["workbook_status"]})
            writer.writerow(row)
    if "metadata" in audit:
        with (output / "zero-metadata.csv").open("x", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["logical_record", "raw_workbook_row", "zero_mask", "source_Coordinate", "metadata_Series", "metadata_Topo", "metadata_Chem", "metadata_Row", "same_position_topo_chem_match", "Topo_Chem_candidate_metadata_rows", "join_basis", "unique_image_or_observation_join"])
            for row in audit["metadata"]["zero_rows"]:
                points = row["same_position_metadata"]
                writer.writerow([row["logical_record"], row["raw_workbook_row"], row["zero_mask"], row["source_Coordinate"],
                    *[points[name]["value"] if points else "" for name in METADATA_HEADERS], row["same_position_topo_chem_match"],
                    ";".join(map(str, row["Topo_Chem_candidate_metadata_rows"])), "; ".join(row["join_basis"]), False])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--workbook", required=True)
    parser.add_argument("--metadata", help="Optional pinned author CTC_Image_Metadata.xlsx; inspect saved iMSC_B8S1 layout only.")
    parser.add_argument("--output", required=True, help="A new output directory; originals and prior output are never overwritten.")
    args = parser.parse_args()
    try:
        csv_path, workbook_path = Path(args.csv).absolute(), Path(args.workbook).absolute()
        csv_raw, workbook_raw = csv_path.read_bytes(), workbook_path.read_bytes()
        workbook_digest = hashlib.sha256(workbook_raw).hexdigest()
        expected_sha, expected_bytes = SOURCES["hiMSC_Raw_Data.xlsx"]
        _require((workbook_digest, len(workbook_raw)) == (expected_sha, expected_bytes),
                 "Workbook is not the pinned archived hiMSC original; do not apply B8S1 row linkage to another version.", "SOURCE_VERSION_MISMATCH")
        audit = inspect_linkage(csv_raw, workbook_raw)
        _require(audit["coverage"]["csv_records"] == 972, "This archived B8S1 projection must have 972 data records.")
        csv_digest = hashlib.sha256(csv_raw).hexdigest()
        audit.update(sources={"csv": {"path": str(csv_path), "bytes": len(csv_raw), "sha256": csv_digest},
                              "workbook": {"path": str(workbook_path), "bytes": len(workbook_raw), "sha256": workbook_digest}},
                     archived_csv_sha256=ARCHIVED_CSV_SHA256, archived_csv_bytes_match=csv_digest == ARCHIVED_CSV_SHA256)
        if args.metadata:
            metadata_path = Path(args.metadata).absolute()
            metadata_raw = metadata_path.read_bytes()
            metadata_digest = hashlib.sha256(metadata_raw).hexdigest()
            _require((metadata_digest, len(metadata_raw)) == (METADATA_SHA256, 440330),
                     "Metadata is not the pinned author original.", "SOURCE_VERSION_MISMATCH")
            audit["metadata"] = inspect_metadata(audit, metadata_raw)
            audit["sources"]["metadata"] = {"path": str(metadata_path), "bytes": len(metadata_raw), "sha256": metadata_digest}
            audit["unknowns"]["image_metadata_join"] = "saved_layout_position_and_keys_checked_only; image_or_object_export_identity_unknown"
        _write_outputs(Path(args.output).absolute(), audit)
        ok = (audit["coverage"]["complete_projection_match"] and audit["archived_csv_bytes_match"]
              and audit.get("metadata", {}).get("layout_position_correspondence_complete", True))
        print(json.dumps({"ok": ok, "coverage": audit["coverage"], "zero_cooccurrence": audit["zero_cooccurrence"],
                          "metadata_checks": audit.get("metadata", {}).get("checks"),
                          "output": str(Path(args.output).absolute()), "scientific_validation": False}, ensure_ascii=False))
        return 0 if ok else 2
    except (ResearchError, OSError, ValueError, csv.Error) as error:
        print(json.dumps({"ok": False, "code": getattr(error, "code", "SOURCE_LINKAGE_UNAVAILABLE"),
                          "message": str(error) if isinstance(error, ResearchError) else "Original inputs or a fresh output directory are unavailable."}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
