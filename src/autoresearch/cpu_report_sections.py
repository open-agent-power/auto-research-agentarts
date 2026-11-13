"""Pure saved-evidence projections for native retrieval/scheduling reports.

No ranking, scoring against labels, scheduling, fitting, network or project
mutation. JSON action results remain complete; presentation samples are explicit.
"""
import base64
import binascii
import copy
import hashlib
import math

from .contracts import ResearchError, canonical, fingerprint

PRIMARY = {"retrieval": "research.retrieval-fixed-pair", "scheduling": "research.weighted-interval-fixed-pair",
           "relevance": "research.relevance-fixed-pair"}
AUDITS = {"retrieval": "research.retrieval-saved-error-audit", "scheduling": "research.weighted-interval-saved-audit",
          "relevance": "research.relevance-saved-error-audit"}
FILES = {"retrieval": {"corpus":"corpus.jsonl", "queries":"queries.jsonl", "train_qrels":"qrels-train.tsv", "test_qrels":"qrels-test.tsv", "license":"license.md"},
         "relevance": {"corpus":"corpus.jsonl", "queries":"queries.jsonl", "train_qrels":"qrels-train.tsv", "test_qrels":"qrels-test.tsv", "license":"license.md"},
         "scheduling": {"jobs":"jobs.json", "license":"license.md"}}
TITLES = {"retrieval":"引用文档检索对照与保存错误诊断报告", "scheduling":"合成加权区间调度对照与保存结果审计报告",
          "relevance":"文档相关性检索对照与保存错误诊断报告"}


def _require(value, message):
    if not value:
        raise ResearchError("EVIDENCE_CHANGED", message)


def _number(value):
    return format(value,".8g") if type(value) in (int,float) and math.isfinite(value) else "未知"


def _asset(value, name, maximum):
    _require(type(value) is dict and set(value)=={"file_name","sha256","bytes","bytes_base64"}
             and value["file_name"]==name and type(value["bytes"]) is int and 0<value["bytes"]<=maximum
             and type(value["bytes_base64"]) is str and len(value["bytes_base64"])<=4*((maximum+2)//3), "CPU原始资产结构或大小改变。")
    try:
        raw=base64.b64decode(value["bytes_base64"],validate=True)
    except (ValueError,binascii.Error):
        raise ResearchError("EVIDENCE_CHANGED","CPU原始资产Base64无效。") from None
    _require(len(raw)==value["bytes"] and hashlib.sha256(raw).hexdigest()==value["sha256"], "CPU原始资产字节或SHA改变。")
    return raw


def source_manifest(packet, kind):
    """Verify embedded byte identities; never attest domain/provenance declarations."""
    from .snapshot_viewer import _json
    try:
        expected=FILES[kind]
        _require(set(packet)=={"schema_version","task_kind","spec_source","assets","spec","scope","snapshot_sha256"}
            and packet["schema_version"]=="cpu-research-source-v1"
            and packet["task_kind"]=={"retrieval":"citation_retrieval", "relevance":"relevance_retrieval", "scheduling":"weighted_interval"}[kind]
            and packet["snapshot_sha256"]==fingerprint({k:v for k,v in packet.items() if k!="snapshot_sha256"})
            and type(packet["assets"]) is dict and set(packet["assets"])==set(expected), "CPU输入结构或快照身份改变。")
        spec_raw=_asset(packet["spec_source"],"spec.json",65536)
        _require(_json(spec_raw)==packet["spec"] and packet["spec"]["files"]==expected, "CPU声明不匹配原spec字节。")
        spec=packet["spec"]
        if kind=="relevance":
            _require(spec["schema_version"]=="relevance-retrieval-spec-v1"
                and packet["scope"]["contract"]=="relevance-retrieval-fixed-pair-v1"
                and packet["scope"]["qrels_semantics"]==spec["source_provenance"]["qrels_semantics"]=="positive_relevance_binary_projection"
                and set(spec["license_notes"])=={"corpus","queries_and_qrels"}, "相关性输入合同、标签语义或许可对象改变。")
        rows=[{"name":"embedded:spec.json","role":"embedded_cpu_spec","sha256":hashlib.sha256(spec_raw).hexdigest(),"bytes":len(spec_raw)}]
        for role,name in expected.items():
            maximum=(8912896 if role=="corpus" else 524288 if role=="queries" else 4194304 if role=="jobs" else 65536)
            if kind=="relevance":
                maximum=12*1024*1024 if role=="corpus" else 3*1024*1024 if role=="queries" else 1024*1024 if role.endswith("qrels") else 65536
            asset=packet["assets"][role]
            raw=_asset(asset,name,maximum)
            _require(packet["scope"]["input_identities"][role]=={"sha256":asset["sha256"],"bytes":len(raw)}, "CPU范围中的输入身份改变。")
            license_note=spec["license_notes"]["abstracts" if role=="corpus" else "claims_and_qrels"] if kind=="retrieval" else spec["license_notes"]
            if kind=="relevance":
                license_note=spec["license_notes"]["corpus" if role=="corpus" else "queries_and_qrels"]
            rows.append({"name":"embedded:"+name,"role":"embedded_cpu_original","asset_role":role,"sha256":asset["sha256"],"bytes":len(raw),
                "url":spec["source_url"],"license_note":license_note,"attribution":spec["attribution"],
                "provenance_claim":copy.deepcopy(spec["source_provenance"]),"notice":"Verified embedded bytes only; licence/provenance declarations are not independently established by report export."})
        provenance={"source_url":spec["source_url"],"attribution":spec["attribution"],"license_notes":copy.deepcopy(spec["license_notes"]),
            "source_provenance":copy.deepcopy(spec["source_provenance"]),"verification":"embedded_bytes_checked_declarations_unverified"}
        return rows,provenance
    except ResearchError:
        raise
    except (KeyError,TypeError,ValueError,UnicodeError,OverflowError,RecursionError):
        raise ResearchError("EVIDENCE_CHANGED","Malformed CPU input or source manifest.") from None


def _primary(kind, entries):
    return next((entry for entry in reversed(entries) if entry["command"]==PRIMARY[kind]
                 and entry["status"]=="completed" and entry.get("tool_result") is not None),None)


def summary(kind, state, entries):
    entry=_primary(kind,entries)
    rows=[]
    if kind in ("retrieval","relevance"):
        relevance=kind=="relevance"
        method="在冻结语料和查询上比较固定TF-IDF余弦与BM25，完整排名先冻结，再按引用文档qrels计算Recall/MRR/nDCG；不生成答案、不拟合、不调用模型。"
        headers=["划分","指标","TF-IDF","BM25","候选−基线","胜/平/负"]
        baseline,candidate="tfidf_cosine","bm25"
        if relevance:
            method="在冻结语料和查询上比较固定BM25基线与TF-IDF余弦候选；相同query/doc ID在top20截断前排除。完整排名先在内存计算内容身份，再按正相关性标签的二元投影计算Recall/MRR/nDCG，排名随最终原生工件保存；不生成答案、不拟合、不调用模型。"
            headers=["划分","指标","BM25 基线","TF-IDF 候选","候选−基线","胜/平/负"]
            baseline,candidate="bm25","tfidf_cosine"
        if entry:
            for split,value in entry["tool_result"]["result"]["paired_summary"]["splits"].items():
                for metric,change in value["paired_candidate_minus_baseline"].items():
                    rows.append([split,metric,_number(value["arms"][baseline]["metrics"][metric]),_number(value["arms"][candidate]["metrics"][metric]),
                        _number(change["mean"]),f"{change['wins']}/{change['ties']}/{change['losses']}"])
        notice="qrels表示cited_doc_ids，不是SUPPORT/CONTRADICT或事实核验。原query metadata可能含句级注释，仅原样保留且不参与检索或评分；不是封存盲测。早排指标改善可伴随Recall下降，不自动采用候选。"
        if relevance:
            notice="原始正相关性grade保留，当前指标按grade>0二元投影，不是canonical graded BEIR nDCG。语料中缺失的正例仍计入召回分母，不补造文档或静默丢标签；划分以原spec清单为准，不自动成为官方或封存盲测。固定算法对照本身不能证明记忆的因果收益；保留所有下降与未召回结果，不自动采用候选。"
    else:
        method="在显式合成工程任务上比较相同精确动态规划的全扫描与二分前驱查找；保留每次实际时延、完整schedule、目标值和生产核验，不训练模型。"
        headers=["任务/划分","jobs","目标值","扫描 ms","二分 ms","倍率/状态"]
        if entry:
            for case in entry["tool_result"]["result"]["paired_summary"]["per_case"]:
                timing=case["median_seconds"]
                rows.append([case["case_id"]+" / "+case["split"],case["jobs"],case["objective"],_number(timing["quadratic_scan_dp"]*1000),
                    _number(timing["binary_search_dp"]*1000),_number(case["speedup_baseline_over_candidate"])+" / "+case["candidate_timing"]])
        notice="这是合成加权区间调度、已知精确DP的代码/复杂度对照，不是新算法发现或科学样本。倍率为这些保存任务的本地时延；完整可行性、目标及坏例须一并阅读，零全扫描计数不等于零CPU工作。"
    return {"method":method,"headers":headers,"rows":rows,"result_notice":notice,"has_completed_primary_result":entry is not None,
            "scope":copy.deepcopy(state.get("source_scope",{}))}


def sections(report):
    """Bounded readable tables plus exact pointers to every complete JSON array."""
    kind=report["kind"]
    if kind not in PRIMARY:
        return []
    result=[]
    source=report.get("cpu_source_provenance")
    if source:
        license_rows=[[name,value] for name,value in source["license_notes"].items()] if type(source["license_notes"]) is dict else [["工程输入声明",source["license_notes"]]]
        result.append({"title":"CPU输入原件、许可与来源声明","paragraphs":["来源："+source["source_url"],"署名："+source["attribution"],
            "以下许可/来源为原spec声明；本导出仅核对字节身份，不把声明、检索命中或opaque注释变成已验证事实。",
            "原件/许可/完整spec在input.json.source_packet；source_manifest保留每资产SHA。",
            "来源身份："+canonical(source["source_provenance"])],"headers":["许可对象","原声明"],"rows":license_rows})
    for index,entry in enumerate(report["action_results"]):
        if entry["status"]!="completed" or entry.get("tool_result") is None or entry["command"] not in (PRIMARY[kind],AUDITS[kind]):
            continue
        body=entry["tool_result"]["result"]
        pointer=f"report.json.action_results[{index}].tool_result.result"
        if entry["command"]==AUDITS[kind]:
            result.append({"title":"保存结果的后续诊断","paragraphs":["行动："+entry["action_id"],
                "前序绑定："+canonical(body["predecessor"]),"仅复用保存算术，不重新排名、对gold评分、求解、计时或拟合。完整诊断："+pointer],"headers":[],"rows":[]})
        elif kind in ("retrieval","relevance"):
            adverse=body["adverse_queries"]
            shown=adverse[:12]
            result.append({"title":"检索覆盖损失与完整排名","paragraphs":["行动："+entry["action_id"],
                f"已保存{len(body['rankings'])}条arm/query完整排名、{len(body['per_query_metrics'])}条逐query指标；不以摘要替换原证据。",
                f"以下为原顺序前{len(shown)}/{len(adverse)}条差异/覆盖坏例；全部坏例、亏损与持平详见{pointer}.adverse_queries及per_query_metrics。",
                "完整rankings JSON附件定位："+pointer+".rankings；原query行、ranked_doc_lines及qrel SHA/定位随原记录保留。",
                "排名在首次评分前的内容身份："+body["rankings_before_scoring_sha256"]],
                "headers":["划分/query","下降指标","R@5 父/候选","R@20 父/候选"],
                "rows":[[row["split"]+" / "+row["query_id"],", ".join(row["loss_metrics"]) or "共有漏检/持平",
                    _number(row["baseline"]["recall@5"])+" / "+_number(row["candidate"]["recall@5"]),
                    _number(row["baseline"]["recall@20"])+" / "+_number(row["candidate"]["recall@20"])] for row in shown]})
        else:
            operations=[]
            for case in body["cases"]:
                for method in ("quadratic_scan_dp","binary_search_dp"):
                    run=next(row for row in case["runs"] if row["method"]==method)
                    ops=run["operations"]
                    operations.append([case["case_id"],method,ops["dp_steps"],ops["full_scan_comparisons"],
                        ops["bisect_calls"],"未计量" if ops["bisect_internal_comparisons"] is None else ops["bisect_internal_comparisons"],ops["reconstruction_steps"]])
            result.append({"title":"调度可行性、操作数与完整schedule","paragraphs":["行动："+entry["action_id"],
                f"保留{len(body['cases'])}个任务、{body['usage']['solver_calls']}次实际求解及每个完整schedule；report导出未调用求解器。",
                "原生产回执检查每次schedule可行性、两法目标/schedule一致；小任务穷举核验与大任务未穷举范围均在cases[].correctness，导出不另行声称独立最优证明。",
                "下面每任务/方法显示首个已保存run的操作数；所有repeats/seconds/objectives/schedules/operations完整JSON："+pointer+".cases。",
                "候选较慢或持平任务（完整列表）："+canonical(body["paired_summary"]["adverse_cases"]),
                "二分内部比较次数未计量；full_scan_comparisons=0仅表示没有二次全扫描。"],
                "headers":["任务","方法","DP步","全扫描","二分调用","内部比较","回溯步"],"rows":operations})
    return result
