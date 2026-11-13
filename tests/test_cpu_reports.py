"""Pure saved-report dictionaries; no native cases, ranking, solving, fit or API."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import cpu_report_sections as cpu, project_report
from autoresearch import retrieval_lexical, scheduling_kernel
from autoresearch.contracts import ResearchError, canonical, fingerprint


def asset(name, raw):
    return {"file_name":name,"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw),"bytes_base64":base64.b64encode(raw).decode()}


def packet(kind):
    # Presentation-only originals, not an accepted research-adapter dataset.
    spec={"files":cpu.FILES[kind],"source_url":"urn:report:fixture","attribution":"Fixture author",
        "license_notes":{"claims_and_qrels":"CC BY 4.0 citation annotations","abstracts":"ODC-By 1.0 abstracts"} if kind=="retrieval" else "Author-created synthetic input",
        "source_provenance":{"fixture":True},"comparison":{"fixed_fixture":True}}
    assets={role:asset(name,("synthetic saved original "+role).encode()) for role,name in cpu.FILES[kind].items()}
    value={"schema_version":"cpu-research-source-v1","task_kind":"citation_retrieval" if kind=="retrieval" else "weighted_interval",
        "spec_source":asset("spec.json",canonical(spec).encode()),"spec":spec,"assets":assets,
        "scope":{"input_identities":{role:{key:a[key] for key in ("sha256","bytes")} for role,a in assets.items()}}}
    value["snapshot_sha256"]=fingerprint(value)
    return value


def retrieval_body():
    metric_names=("recall@5","recall@10","recall@20","mrr@10","ndcg@10")
    before={name:.6 for name in metric_names}
    after={name:(.4 if name.startswith("recall") else .8) for name in metric_names}
    summary={"splits":{split:{"arms":{"tfidf_cosine":{"queries":13,"metrics":before},"bm25":{"queries":13,"metrics":after}},
        "paired_candidate_minus_baseline":{name:{"mean":after[name]-before[name],"wins":0 if name.startswith("recall") else 13,
            "ties":0,"losses":13 if name.startswith("recall") else 0} for name in metric_names}} for split in ("dev","validation","test")}}
    adverse=[{"split":"test","query_id":"q"+str(index),"loss_metrics":["recall@5"],"baseline":before,"candidate":after} for index in range(13)]
    rankings=[{"query_id":"q"+str(i),"method":m,"ranking":["doc-"+str(i)],"query_line":i+1,"ranked_doc_lines":[i+1]}
              for i in range(13) for m in ("tfidf_cosine","bm25")]
    return {"paired_summary":summary,"adverse_queries":adverse,"rankings":rankings,"rankings_before_scoring_sha256":fingerprint(rankings),
            "per_query_metrics":[{"query_id":row["query_id"]} for row in rankings]}


def scheduling_body():
    cases=[]
    summaries=[]
    for case_id,outcome in (("faster-case","faster"),("tie-case","tie")):
        runs=[]
        for method in ("quadratic_scan_dp","binary_search_dp"):
            runs.append({"method":method,"repeat":0,"seconds":.003 if method=="quadratic_scan_dp" or outcome=="tie" else .001,
                "objective":7,"schedule":[5,1],"operations":{"dp_steps":3,"full_scan_comparisons":3 if method=="quadratic_scan_dp" else 0,
                    "bisect_calls":0 if method=="quadratic_scan_dp" else 3,"bisect_internal_comparisons":None,"reconstruction_steps":2}})
        cases.append({"case_id":case_id,"jobs":[{"id":5},{"id":1},{"id":9}],"runs":runs,
                      "correctness":{"paired_objective_and_schedule_equal":True,"bruteforce_performed":True}})
        summaries.append({"case_id":case_id,"split":"test","jobs":3,"objective":7,
            "median_seconds":{"quadratic_scan_dp":.003,"binary_search_dp":runs[1]["seconds"]},
            "speedup_baseline_over_candidate":1 if outcome=="tie" else 3,"candidate_timing":outcome})
    return {"cases":cases,"paired_summary":{"per_case":summaries,"adverse_cases":["tie-case"]},"usage":{"solver_calls":4}}


def report(kind):
    body=retrieval_body() if kind=="retrieval" else scheduling_body()
    entry={"action_id":"fixture-action","command":cpu.PRIMARY[kind],"status":"completed","failure":None,"tool_result":{"result":body}}
    state={"registration":{"method_id":cpu.PRIMARY[kind],"goal":"Fixture saved-evidence reporting"},"execution_status":"completed",
        "research_status":"waiting","code_identity":"c"*64,"source_scope":{"domain":"retrieval" if kind=="retrieval" else "algorithm"},
        "budget":{"lineage_ref":"fixture-not-real","new_fits":0,"new_model_requests":0},"next_decision":{"reason":"Wait for interpretation"}}
    source=packet(kind)
    source_rows,provenance=cpu.source_manifest(source,kind)
    usage={"decision_slots_used":0,"cli_launch_attempts":0,"known_cli_reported_cost_usd":0,"cli_cost_unknown":False,
           "delegated_outputs_received":0,"unlinked_external_selection_count":0,"prior_external_usage":"unknown_not_zero","cash_settlement":"unknown"}
    value={"kind":kind,"title":cpu.TITLES[kind],"project":state,"project_id":"fixture-project","project_snapshot_ref":"snapshot-fixture",
        "action_results":[entry],"source_selections":[],"source_manifest":source_rows,"cpu_source_provenance":provenance,
        "host_models":{"snapshot_sha256":"h"*64,"status":{"usage":usage},"records":[]},"plan_reviews":[],"execution_conditions":{},
        "registered_inputs":[],"selection_history":{"records":[]},"feature_comparisons":[],"design_assessment":None,
        "input":{"source_packet":source,"source_file_identity":{"sha256":"s"*64}},"exporter_code_identity":"e"*64}
    value["summary"]=project_report._summary(kind,state,[entry])
    value["cpu_sections"]=cpu.sections(value)
    return value


class CPUReportTests(unittest.TestCase):
    def test_new_kinds_titles_and_original_empty_summaries_preserved(self):
        for kind in ("retrieval","scheduling"):
            self.assertEqual(project_report.KINDS[cpu.PRIMARY[kind]],kind)
            self.assertEqual(project_report._report_title(kind,[]),cpu.TITLES[kind])
        for kind,method in (("p02","p02.saved-oof-residuals"),("tabular","data.tabular-quality-audit")):
            old=project_report._summary(kind,{"registration":{"method_id":method}},[])
            self.assertFalse(old["has_completed_primary_result"])
            self.assertEqual(old["rows"],[])
            self.assertNotIn("cpu_sections",old)
        self.assertEqual(cpu.sections({"kind":"p02"}),[])

    def test_retrieval_macro_metrics_retain_recall_losses_and_citation_boundary(self):
        value=report("retrieval")
        rows=value["summary"]["rows"]
        self.assertEqual(len(rows),15)
        recall=next(row for row in rows if row[:2]==["test","recall@5"])
        self.assertEqual(recall[2:],["0.6","0.4","-0.2","0/0/13"])
        self.assertIn("不是SUPPORT",value["summary"]["result_notice"])
        self.assertIn("metadata",value["summary"]["result_notice"])

    def test_asset_manifest_verifies_all_five_assets_spec_and_dual_licences(self):
        source=packet("retrieval")
        rows,provenance=cpu.source_manifest(source,"retrieval")
        self.assertEqual(len(rows),6)
        self.assertEqual({row["asset_role"] for row in rows if "asset_role" in row},set(cpu.FILES["retrieval"]))
        corpus=next(row for row in rows if row.get("asset_role")=="corpus")
        queries=next(row for row in rows if row.get("asset_role")=="queries")
        self.assertIn("ODC-By",corpus["license_note"])
        self.assertIn("CC BY",queries["license_note"])
        self.assertEqual(provenance["verification"],"embedded_bytes_checked_declarations_unverified")

    def test_source_manifest_rejects_changed_originals_scope_and_extra_assets(self):
        for mode in ("bytes","scope","extra","filename"):
            source=packet("retrieval")
            if mode=="bytes":source["assets"]["corpus"]["sha256"]="0"*64
            elif mode=="scope":source["scope"]["input_identities"]["corpus"]["bytes"]+=1
            elif mode=="extra":source["assets"]["unrecognized"]=source["assets"]["corpus"]
            else:source["assets"]["corpus"]["file_name"]="../corpus.jsonl"
            source["snapshot_sha256"]=fingerprint({k:v for k,v in source.items() if k!="snapshot_sha256"})
            with self.subTest(mode=mode),self.assertRaises(ResearchError):cpu.source_manifest(source,"retrieval")

    def test_readable_sample_is_explicit_and_complete_evidence_remains_in_json(self):
        value=report("retrieval")
        before=deepcopy(value["action_results"])
        section=next(s for s in value["cpu_sections"] if s["title"]=="检索覆盖损失与完整排名")
        self.assertEqual(len(section["rows"]),12)
        self.assertTrue(any("12/13" in line for line in section["paragraphs"]))
        self.assertTrue(any("action_results[0].tool_result.result.rankings" in line for line in section["paragraphs"]))
        self.assertEqual(len(value["action_results"][0]["tool_result"]["result"]["adverse_queries"]),13)
        self.assertEqual(value["action_results"],before)

    def test_scheduling_summary_synthetic_scope_operations_and_complete_schedules(self):
        value=report("scheduling")
        self.assertEqual(len(value["source_manifest"]),3)
        self.assertEqual(len(value["summary"]["rows"]),2)
        self.assertIn("合成",value["summary"]["result_notice"])
        section=next(s for s in value["cpu_sections"] if s["title"]=="调度可行性、操作数与完整schedule")
        self.assertEqual(len(section["rows"]),4)
        self.assertTrue(any(row[-2]=="未计量" for row in section["rows"]))
        self.assertTrue(any("tie-case" in line for line in section["paragraphs"]))
        self.assertEqual(value["action_results"][0]["tool_result"]["result"]["cases"][0]["runs"][0]["schedule"],[5,1])

    def test_saved_audit_sections_show_original_predecessor_and_no_reexecution(self):
        value=report("retrieval")
        value["action_results"].append({"action_id":"audit","command":cpu.AUDITS["retrieval"],"status":"completed",
            "tool_result":{"result":{"predecessor":{"based_on_action_id":"fixture-action","based_on_result_sha256":"a"*64}}}})
        sections=cpu.sections(value)
        self.assertTrue(any("不重新排名" in line for section in sections for line in section["paragraphs"]))

    def test_markdown_and_pdf_use_saved_projection_without_research_execution(self):
        for kind in ("retrieval","scheduling"):
            value=report(kind)
            with self.subTest(kind=kind),patch.object(retrieval_lexical,"retrieve",side_effect=AssertionError("No ranking")), \
                 patch.object(retrieval_lexical,"metrics",side_effect=AssertionError("No scoring")), \
                 patch.object(scheduling_kernel,"schedule",side_effect=AssertionError("No solving")):
                markdown=project_report._markdown(value)
                pdf=project_report._pdf(value)
            self.assertIn(value["title"],markdown)
            self.assertIn("report.json.action_results[0]",markdown)
            self.assertTrue(pdf.startswith(b"%PDF"))

    def test_existing_four_file_export_keeps_complete_cpu_json_and_hashes(self):
        value=report("retrieval")
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);project=root/"native-project";project.mkdir()
            target=root/"report"
            with patch.object(project_report,"collect_report",return_value=value), \
                 patch.object(project_report,"ResearchProject") as core, \
                 patch.object(project_report.host_model_report,"host_model_snapshot_sha256",return_value="h"*64):
                core.return_value.status.return_value={"snapshot_ref":"snapshot-fixture"}
                manifest=project_report.export_report(workspace=project,output=target)
            self.assertEqual(set(manifest["files"]),{"report.json","report.md","report.pdf","input.json"})
            for name,identity in manifest["files"].items():
                raw=(target/name).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(),identity["sha256"])
                self.assertEqual(len(raw),identity["bytes"])
            saved=json.loads((target/"report.json").read_text())
            self.assertEqual(len(saved["action_results"][0]["tool_result"]["result"]["rankings"]),26)
            self.assertEqual(len(saved["action_results"][0]["tool_result"]["result"]["adverse_queries"]),13)
            self.assertEqual(json.loads((target/"input.json").read_text())["source_packet"],value["input"]["source_packet"])


if __name__=="__main__":unittest.main()
