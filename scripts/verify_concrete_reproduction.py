"""Read-only independent Concrete evaluator; reconstruct saved predictions, never fit.

No autoresearch modules are imported. Input SQLite is opened mode=ro. Output must
be a fresh directory outside the project/manager. Results retain every failed
check and full row/group/fold diagnostics; historical report metrics are unused.
"""
import argparse
import base64
from contextlib import ExitStack
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import traceback
from unittest.mock import patch

import numpy as np

COLUMNS = ["cement", "blast_furnace_slag", "fly_ash", "water", "superplasticizer",
           "coarse_aggregate", "fine_aggregate", "age", "strength"]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def fingerprint(value):
    return digest(canonical(value).encode())


def read_json(path):
    return json.loads(path.read_bytes())


def read_database(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError("Existing unlinked regular database required: " + str(path))
    con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


def snapshot(root):
    return {str(p.relative_to(root)): digest(p.read_bytes())
            for p in sorted(root.rglob("*")) if p.is_file()}


class Audit:
    def __init__(self):
        self.checks = []
        self.results = {"schema_version": "concrete-independent-reproduction-v1",
                        "new_fits": 0, "model_calls": 0, "scientific_validation": False}

    def check(self, name, passed, detail=None):
        item = {"name": name, "passed": bool(passed)}
        if detail is not None:
            item["detail"] = detail
        self.checks.append(item)
        return item["passed"]

    def near(self, name, left, right, rtol=1e-9, atol=1e-10):
        left, right = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
        valid = left.shape == right.shape and bool(np.isfinite(left).all() and np.isfinite(right).all())
        valid = valid and bool(np.allclose(left, right, rtol=rtol, atol=atol))
        difference = np.abs(left-right) if left.shape == right.shape else np.asarray([])
        error = float(np.max(difference)) if difference.size and np.isfinite(difference).all() else None
        return self.check(name, valid, {"max_abs_error": error, "rtol": rtol, "atol": atol})

    def asset(self, label, asset):
        raw = base64.b64decode(asset["bytes_base64"], validate=True)
        self.check(label + "_sha", digest(raw) == asset["sha256"])
        self.check(label + "_size", len(raw) == asset["bytes"])
        return raw


def parse_csv(raw, delimiter=","):
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), delimiter=delimiter, strict=True)
    header = next(reader)
    rows = []
    for number, tokens in enumerate(reader, 1):
        if len(tokens) != len(header):
            raise ValueError("CSV width mismatch at record " + str(number))
        rows.append({"logical_record": number, "physical_line_end": reader.line_num,
                     "values": dict(zip(header, tokens)), "tokens": tokens})
    return header, rows


def audit_mapping(audit, packet, original_csv):
    spec_raw = audit.asset("spec", packet["spec_source"])
    spec = json.loads(spec_raw)
    audit.check("packet_spec_equals_original_spec", spec == packet["spec"])
    audit.check("packet_snapshot", fingerprint({k:v for k,v in packet.items() if k != "snapshot_sha256"}) == packet["snapshot_sha256"])
    derived_raw = audit.asset("derived_csv", packet["source"])
    header, rows = parse_csv(derived_raw, spec["delimiter"])
    original_raw = original_csv.read_bytes()
    original_header, original = parse_csv(original_raw)
    audit.check("original_nine_fields", len(original_header) == 9)
    audit.check("original_provenance_sha", digest(original_raw) == spec["provenance"]["origin_sha256"])
    audit.check("field_dictionary_binding", spec["numeric_columns"] == COLUMNS and spec["target_column"] == "strength" and spec["target_unit"] == "MPa" and spec["group_columns"] == ["mixture_signature"] and spec["key_columns"] == ["source_row"])
    audit.check("full_original_row_coverage", len(original) == len(rows) and len(rows) == 1030)
    audit.check("mapped_required_columns", set(COLUMNS + ["source_row", "mixture_signature"]) <= set(header))
    token_errors, row_errors, group_errors = [], [], []
    signatures, reverse = {}, {}
    for row, origin in zip(rows, original):
        values, index = row["values"], row["logical_record"]
        if [values[c] for c in COLUMNS] != origin["tokens"]:
            token_errors.append(index)
        if values["source_row"] != str(index):
            row_errors.append(index)
        signature = tuple(Decimal(values[c]) for c in COLUMNS[:7])
        group = values["mixture_signature"]
        if signature in signatures and signatures[signature] != group or group in reverse and reverse[group] != signature:
            group_errors.append(index)
        signatures.setdefault(signature, group)
        if group != "mixture-" + str(list(signatures).index(signature)+1).zfill(4):
            group_errors.append(index)
        reverse.setdefault(group, signature)
    audit.check("all_nine_original_numeric_tokens_preserved_in_order", not token_errors, token_errors)
    audit.check("source_row_identity", not row_errors, row_errors)
    audit.check("exact_decimal_seven_ingredient_group_bijection", not group_errors, group_errors)
    audit.results["mapping"] = {"rows": len(rows), "groups": len(signatures), "original_header": original_header,
                                "project_header": header, "original_csv_sha256": digest(original_raw),
                                "derived_csv_sha256": digest(derived_raw), "source_snapshot_sha256": packet["snapshot_sha256"]}
    return spec, rows


def group_folds(groups, count):
    # Independently spell out greedy size-balanced GroupKFold with first-seen IDs.
    labels = list(dict.fromkeys(groups))
    indices = np.asarray([labels.index(g) for g in groups], dtype=int)
    sizes = np.bincount(indices)
    weights, assignments = np.zeros(count, dtype=int), np.empty(len(labels), dtype=int)
    for group in np.argsort(sizes)[::-1]:
        fold = int(np.argmin(weights))
        assignments[group] = fold + 1
        weights[fold] += sizes[group]
    return assignments[indices]


def audit_action(audit, action, envelope, spec, source_rows, source_snapshot):
    label = action["id"]
    analysis = envelope["tool_result"]["result"]["analysis"]
    binding, protocol = analysis["design_binding"], analysis["protocol"]
    training = binding["training"]
    features, group_columns = training["feature_columns"], training["split_group_columns"]
    audit.check(label + ":eight_declared_features", features == COLUMNS[:8])
    audit.check(label + ":original_target_groups", group_columns == ["mixture_signature"] and analysis["target_column"] == "strength")
    audit.check(label + ":source_binding", analysis["source_snapshot_sha256"] == source_snapshot == action["source_snapshot_sha256"] == binding["source_snapshot_sha256"])
    audit.check(label + ":binding_saved_in_action", binding == action["design_binding"])
    audit.check(label + ":fixed_group_protocol", analysis["check"] == "group_cv" and protocol["splitter"] == "GroupKFold" and protocol["shuffle"] is False and protocol["random_state"] is None and protocol["ridge_alpha"] == 1.0)
    missing = set(spec["missing_tokens"])
    complete, exclusions = [], []
    for row in source_rows:
        values = row["values"]
        reasons = []
        def finite(name):
            try:
                token = values[name]
                value = float(token)
                return value if token not in missing and np.isfinite(value) else None
            except (ValueError, OverflowError):
                return None
        y = finite(spec["target_column"])
        x = [finite(c) for c in features]
        groups = tuple(values[c] for c in group_columns)
        if y is None: reasons.append("target_missing_or_nonfinite")
        if any(v is None for v in x): reasons.append("feature_missing_or_nonfinite")
        if any(v in missing for v in groups): reasons.append("split_group_missing")
        if reasons:
            exclusions.append({"logical_record":row["logical_record"],"physical_line_end":row["physical_line_end"],"reasons":reasons})
        else:
            complete.append({**row, "x":x,"y":y,"groups":groups})
    audit.check(label + ":exact_exclusions", exclusions == analysis["exclusions"])
    audit.check(label + ":complete_summary_counts", analysis["summary"]["input_n"] == len(source_rows) and analysis["summary"]["n"] == len(complete) and analysis["summary"]["excluded"] == len(exclusions) and analysis["summary"]["group_count"] == len({r["groups"] for r in complete}))
    audit.check(label + ":no_silent_exclusions", not exclusions)
    x, y = np.asarray([r["x"] for r in complete]), np.asarray([r["y"] for r in complete])
    transforms = training.get("input_transforms", {})
    expected_additions = ({"input_basis":{"kind":"log1p","source_columns":features,"transformed_columns":[name for name in features if name in transforms],"order":"raw_log1p_then_fold_standardization"},"model_input_terms":["log1p("+name+")" if name in transforms else name for name in features]} if transforms else {})
    audit.check(label + ":exact_mapping_metadata", all(protocol.get(k) == v for k,v in expected_additions.items()) and (bool(transforms) or not any(k in protocol for k in ["input_basis","model_input_terms"])))
    audit.check(label + ":fixed_transform_only", not training.get("input_basis") and transforms in ({}, {"age":"log1p"}))
    for column, transform in transforms.items():
        if transform != "log1p" or column not in features:
            raise ValueError("Unsupported transform in frozen case")
        column_index = features.index(column)
        if not np.all(x[:,column_index] > -1): raise ValueError("Invalid log1p domain")
        x[:,column_index] = np.log1p(x[:,column_index])
    rows_by_id = {r["logical_record"]:i for i,r in enumerate(complete)}
    oof = analysis["oof"]
    audit.check(label + ":unique_complete_oof_ids", len(oof) == len(complete) and len({r["logical_record"] for r in oof}) == len(oof) and {r["logical_record"] for r in oof} == set(rows_by_id))
    oof_by_id = {r["logical_record"]:r for r in oof}
    count = min(5, len({r["groups"] for r in complete}))
    audit.check(label + ":five_folds", count == 5 and protocol["n_splits"] == count and len(analysis["folds"]) == count)
    expected_membership = group_folds([r["groups"] for r in complete], count)
    reconstructed, reference, membership = np.full(len(complete), np.nan), np.full(len(complete), np.nan), np.zeros(len(complete),dtype=int)
    seen_test, fold_results = [], []
    for fold in analysis["folds"]:
        number = fold["fold"]
        train_ids, test_ids = fold["train_records"], fold["test_records"]
        train, test = [rows_by_id[k] for k in train_ids], [rows_by_id[k] for k in test_ids]
        seen_test.extend(test_ids)
        audit.check(label + ":fold_partition:" + str(number), len(set(train_ids)) == len(train_ids) and len(set(test_ids)) == len(test_ids) and not set(train_ids)&set(test_ids) and set(train_ids)|set(test_ids) == set(rows_by_id))
        audit.check(label + ":independent_groupfold:" + str(number), set(test) == set(np.flatnonzero(expected_membership == number)))
        audit.check(label + ":no_group_leakage:" + str(number), not {complete[i]["groups"] for i in train}&{complete[i]["groups"] for i in test})
        mean, variance = np.mean(x[train],axis=0), np.var(x[train],axis=0)
        scale = np.sqrt(variance)
        scale[scale == 0] = 1
        audit.near(label + ":train_scaler_mean:" + str(number), mean, fold["scaler_mean"])
        audit.near(label + ":train_scaler_scale:" + str(number), scale, fold["scaler_scale"])
        audit.near(label + ":training_target_mean:" + str(number), np.mean(y[train]), fold["reference_prediction"])
        coef, intercept = np.asarray(fold["ridge_coefficients"]), fold["ridge_intercept"]
        saved_mean, saved_scale = np.asarray(fold["scaler_mean"]), np.asarray(fold["scaler_scale"])
        reconstructed[test] = ((x[test]-saved_mean)/saved_scale) @ coef + intercept
        reference[test], membership[test] = np.mean(y[train]), number
        z = (x[train]-saved_mean)/saved_scale
        # Check saved solution's normal-equation residual; never solve or fit a model.
        residual = z @ coef + intercept - y[train]
        audit.near(label + ":ridge_stationarity:" + str(number), z.T @ residual + coef, np.zeros(len(features)),rtol=0,atol=1e-6)
        audit.near(label + ":intercept_stationarity:" + str(number), np.mean(residual), 0,atol=1e-8)
        audit.check(label + ":ridge_params:" + str(number), fold["model_params"]["alpha"] == 1.0 and fold["model_params"]["fit_intercept"] is True)
        fold_results.append({"fold":number,"train_rows":len(train),"test_rows":len(test),"candidate_mae":float(np.mean(np.abs(reconstructed[test]-y[test]))),"reference_mae":float(np.mean(np.abs(reference[test]-y[test])))})
    audit.check(label + ":test_once_only", len(seen_test) == len(complete) and len(set(seen_test)) == len(complete))
    row_results = []
    for i,row in enumerate(complete):
        saved = oof_by_id[row["logical_record"]]
        audit.check(label + ":row_identity:" + str(row["logical_record"]), saved["physical_line_end"] == row["physical_line_end"] and saved["observed"] == row["y"] and saved["groups"] == list(row["groups"]) and saved["fold"] == int(membership[i]))
        row_results.append({"logical_record":row["logical_record"],"physical_line_end":row["physical_line_end"],"groups":list(row["groups"]),"fold":int(membership[i]),"observed":row["y"],"predicted":float(reconstructed[i]),"reference_prediction":float(reference[i]),"age":float(row["values"]["age"]),"absolute_error":float(abs(reconstructed[i]-y[i]))})
    audit.near(label + ":all_oof_predictions", reconstructed,[oof_by_id[r["logical_record"]]["predicted"] for r in complete])
    audit.near(label + ":all_oof_references", reference,[oof_by_id[r["logical_record"]]["reference_prediction"] for r in complete])
    mae, ref_mae = float(np.mean(np.abs(reconstructed-y))),float(np.mean(np.abs(reference-y)))
    audit.near(label + ":reported_mae", mae,analysis["summary"]["candidate_mae"])
    audit.near(label + ":reported_reference_mae", ref_mae,analysis["summary"]["reference_mae"])
    audit.check(label + ":all_fit_events_completed", all(event.get("status") == "completed" for event in action.get("fit_events",[])))
    audit.check(label + ":usage", analysis["usage"] == {"fit_attempts":2*count,"ridge_fit_attempts":count,"preprocessing_fit_attempts":count} and len(action.get("fit_events",[])) == 2*count)
    groups = []
    for key in dict.fromkeys(r["groups"] for r in complete):
        selected = [i for i,r in enumerate(complete) if r["groups"] == key]
        local, base = float(np.mean(np.abs(reconstructed[selected]-y[selected]))),float(np.mean(np.abs(reference[selected]-y[selected])))
        groups.append({"groups":list(key),"n":len(selected),"mae":local,"reference_mae":base,"worse_than_reference":local>base})
    return {"action_id":label,"analysis":analysis,"rows":row_results,"folds":fold_results,"groups":groups,"metrics":{"mae":mae,"reference_mae":ref_mae,"negative_predictions":int(np.sum(reconstructed<0)),"bad_groups_vs_reference":sum(g["worse_than_reference"] for g in groups)}}


def audit_pair(audit, left, right):
    a,b = left["analysis"],right["analysis"]
    ar,br = a["design_binding"]["resource"],b["design_binding"]["resource"]
    audit.check("strict_parent_lineage", ar["id"] == br["id"] and br["parent_version"] == ar["version"] and br.get("comparison_kind") == "fixed_input_basis")
    audit.check("strict_same_project_source_target", a["design_binding"]["project_id"] == b["design_binding"]["project_id"] and all(a[k] == b[k] for k in ["source_snapshot_sha256","target_column","target_unit","check"]))
    audit.check("strict_protocol_except_fixed_input_mapping", a["protocol"] == {k:v for k,v in b["protocol"].items() if k not in ("input_basis","model_input_terms")} and not a["design_binding"]["training"].get("input_transforms") and b["design_binding"]["training"].get("input_transforms") == {"age":"log1p"})
    lrows,rrows = {r["logical_record"]:r for r in left["rows"]},{r["logical_record"]:r for r in right["rows"]}
    audit.check("strict_complete_row_set", lrows.keys() == rrows.keys())
    changes=[]
    for index in sorted(lrows):
        l,r = lrows[index],rrows[index]
        audit.check("strict_row_group_fold_reference:"+str(index), all(l[k] == r[k] for k in ["logical_record","physical_line_end","groups","fold","observed","reference_prediction"]))
        changes.append({"logical_record":index,"groups":l["groups"],"fold":l["fold"],"age":l["age"],"baseline_absolute_error":l["absolute_error"],"candidate_absolute_error":r["absolute_error"],"worsened":r["absolute_error"]>l["absolute_error"],"baseline_negative":l["predicted"]<0,"candidate_negative":r["predicted"]<0})
    for l,r in zip(a["folds"],b["folds"]):
        audit.check("strict_fold_partition:"+str(l["fold"]), l["fold"] == r["fold"] and all(set(l[k]) == set(r[k]) for k in ["train_records","test_records"]) and l["model_params"] == r["model_params"])
    group_changes=[]
    for key in dict.fromkeys(tuple(r["groups"]) for r in changes):
        selected=[r for r in changes if tuple(r["groups"])==key]
        l=float(np.mean([r["baseline_absolute_error"] for r in selected]));r=float(np.mean([r["candidate_absolute_error"] for r in selected]))
        group_changes.append({"groups":list(key),"n":len(selected),"baseline_mae":l,"candidate_mae":r,"worsened":r>l})
    return {"baseline_action":left["action_id"],"candidate_action":right["action_id"],"rows":changes,"groups":group_changes,"worsened_rows":sum(r["worsened"] for r in changes),"worsened_groups":sum(r["worsened"] for r in group_changes),"baseline_mae":left["metrics"]["mae"],"candidate_mae":right["metrics"]["mae"],"relative_improvement":1-right["metrics"]["mae"]/left["metrics"]["mae"]}


def verify(audit, project, manager, original_csv):
    before=snapshot(manager or project)
    with read_database(project/"project.sqlite") as con:
        state=json.loads(con.execute("SELECT record FROM project WHERE id=1").fetchone()[0])
        actions=[json.loads(row[0]) for row in con.execute("SELECT record FROM actions ORDER BY rowid")]
    packet_raw=(project/"source.json").read_bytes();packet=json.loads(packet_raw)
    audit.check("registered_original_packet_bytes",digest(packet_raw)==state["registration"]["source_sha256"])
    spec,rows=audit_mapping(audit,packet,original_csv)
    audit.results.update(project_id=state["id"],run_id=state["run_id"],project=str(project),manager=str(manager) if manager else None,evaluator_sha256=digest(Path(__file__).read_bytes()))
    saved=[]
    for action in actions:
        if action["status"] != "completed":
            audit.check("no_unresolved_or_failed_action:"+action["id"],False,action)
            continue
        path=project/action["artifact"]
        if not path.resolve().is_relative_to(project.resolve()):raise ValueError("Artifact path escaped project")
        envelope=read_json(path)
        audit.check("artifact_identity:"+action["id"],fingerprint({k:v for k,v in envelope.items() if k!="sha256"})==envelope["sha256"]==action["result_sha256"] and envelope["action_id"]==action["id"] and envelope["request_sha256"]==action["request_sha256"] and envelope["code_identity"]==action["code_identity"]==state["code_identity"] and envelope["source_snapshot_sha256"]==packet["snapshot_sha256"])
        if action["command"]=="data.ridge-group-validation":
            saved.append(audit_action(audit,action,envelope,spec,rows,packet["snapshot_sha256"]))
    audit.check("two_actual_grouped_fit_actions",len(saved)==2,{"count":len(saved)})
    saved.sort(key=lambda r:r["analysis"]["design_binding"]["resource"]["version"])
    audit.results["actions"]=[{k:v for k,v in item.items() if k!="analysis"} for item in saved]
    if len(saved)==2:audit.results["parent_child"]=audit_pair(audit,*saved)
    numerical=[a for a in actions if a["command"] not in ("research.source-selection","p02.source-mapping-check")]
    sources=[a for a in actions if a not in numerical]
    fits=sum(len(a.get("fit_events",[])) for a in numerical)
    audit.check("budget_ceiling",len(numerical)<=6 and fits<=20 and len(sources)<=1 and state["budget"]["local_tool_call_limit"]==6 and state["budget"]["evidence_read_limit"]==1 and state["budget"].get("fit_limit")==20)
    audit.check("zero_product_model_requests",all(state["budget"].get(k,0)==0 for k in ["model_requests_allowed","new_model_requests","model_requests_reserved"]) and not state.get("local_model_requests"))
    audit.results["usage"]={"local_actions":len(numerical),"fit_attempts":fits,"source_reads":len(sources),"native_model_requests":state["budget"].get("new_model_requests",0)}
    audit.check("input_tree_unchanged",snapshot(manager or project)==before)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--project",type=Path);source.add_argument("--manager",type=Path)
    parser.add_argument("--project-id",help="When a manager has multiple projects, select the original ID explicitly.")
    parser.add_argument("--original-csv",type=Path,required=True,help="Preserved original nine-column numeric CSV, in UCI source field order.")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();audit=Audit();project=args.project
    output=args.output.absolute()
    protected=(args.manager or args.project).absolute()
    if output.exists() or output.resolve().is_relative_to(protected.resolve()) or protected.resolve().is_relative_to(output.resolve()):
        parser.error("Output must be a fresh directory outside the input project/manager tree")
    output.mkdir(parents=True)
    try:
        if args.manager:
            with read_database(args.manager/"workbench.sqlite") as con:
                entries=list(con.execute("SELECT id,slot FROM projects"))
            selected=[r for r in entries if args.project_id is None or r["id"]==args.project_id]
            if len(selected)!=1:raise ValueError("Select exactly one existing managed project ID")
            slot=selected[0]["slot"]
            if len(slot)!=64 or any(c not in "0123456789abcdef" for c in slot):raise ValueError("Invalid manager project slot")
            project=args.manager/"projects"/slot
        from sklearn.linear_model import Ridge
        from sklearn.preprocessing import StandardScaler
        with ExitStack() as guards:
            for cls in (Ridge,StandardScaler):
                guards.enter_context(patch.object(cls,"fit",side_effect=AssertionError("Independent evaluator forbids fitting")))
            verify(audit,project.absolute(),args.manager.absolute() if args.manager else None,args.original_csv)
    except Exception as exc:
        audit.check("verification_exception",False,{"type":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc()})
    audit.results.update(checks=audit.checks,passed=all(c["passed"] for c in audit.checks),failures=[c for c in audit.checks if not c["passed"]])
    (output/"verification.json").write_text(json.dumps(audit.results,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"passed":audit.results["passed"],"checks":len(audit.checks),"failures":len(audit.results["failures"]),"output":str(output)}))
    return 0 if audit.results["passed"] else 1


if __name__=="__main__":
    raise SystemExit(main())
