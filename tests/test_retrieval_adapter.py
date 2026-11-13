"""Small engineering fixtures for native retrieval; no SciFact run, fit or API."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import retrieval_adapter as adapter, retrieval_lexical as lexical
from autoresearch.contracts import ResearchError, canonical, fingerprint


def fixture_spec():
    return {"schema_version": "citation-retrieval-spec-v1", "dataset_label": "Engineering fixture, not research evidence",
        "source_url": "https://example.invalid/fixture", "attribution": "Synthetic engineering records",
        "license_notes": {"claims_and_qrels": "Synthetic fixture", "abstracts": "Synthetic fixture"},
        "source_provenance": {"beir_archive_sha256": "a"*64, "original_archive_sha256": "b"*64,
            "original_source_commit": "c"*40, "mapping_receipt_sha256": "d"*64, "qrels_semantics": adapter.SEMANTICS},
        "files": deepcopy(adapter.FILES), "query_splits": {"dev": ["qd"], "validation": ["qv"], "test": ["qt"]},
        "comparison": deepcopy(adapter.COMPARISON), "limits": deepcopy(adapter.LIMITS)}


def reseal(payload):
    payload["snapshot_sha256"] = fingerprint({k:v for k,v in payload.items() if k != "snapshot_sha256"})
    return payload


class RetrievalAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.spec = fixture_spec()
        self.write_json("spec.json", self.spec)
        docs = [{"_id":"a","title":"cat","text":"cat dog","metadata":{}},
                {"_id":"b","title":"dog","text":"dog","metadata":{}},
                {"_id":"c","title":"cat","text":"cat cat fish","metadata":{}}]
        queries = [{"_id":name,"text":text,"metadata":{}} for name,text in (("qd","cat"),("qv","unknown token"),("qt","fish"))]
        (self.root/"corpus.jsonl").write_text("\n".join(canonical(row) for row in docs)+"\n")
        (self.root/"queries.jsonl").write_text("\n".join(canonical(row) for row in queries)+"\n")
        (self.root/"qrels-train.tsv").write_text("query-id\tcorpus-id\tscore\nqd\ta\t1\nqv\tb\t1\n")
        (self.root/"qrels-test.tsv").write_text("query-id\tcorpus-id\tscore\nqt\tc\t1\n")
        (self.root/"license.md").write_text("Synthetic fixture license notice, no external-source verification.\n")

    def write_json(self, name, value):
        (self.root/name).write_text(canonical(value))

    def captured(self):
        return adapter.capture_source(self.root)

    def assert_rejected(self, call, *args, **kwargs):
        with self.assertRaises(ResearchError):
            call(*args, **kwargs)

    def test_source_roundtrip_original_bytes_and_derived_scope(self):
        before = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir()}
        packet = self.captured()
        self.assertEqual(adapter.load_source(canonical(packet).encode()),packet)
        self.assertEqual(packet["scope"]["document_count"],3)
        self.assertEqual(packet["scope"]["query_count"],3)
        self.assertEqual(packet["scope"]["qrels_semantics"],adapter.SEMANTICS)
        self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir()})

    def test_hand_calculable_metrics_no_relevance_and_no_hit(self):
        metrics = lexical.metrics(["a","b","c"],{"b","c"})
        self.assertEqual(metrics["recall@5"],1)
        self.assertEqual(metrics["mrr@10"],.5)
        self.assertAlmostEqual(metrics["ndcg@10"],(1/math.log2(3)+.5)/(1+1/math.log2(3)))
        self.assertTrue(all(value==0 for value in lexical.metrics(["x"],set()).values()))
        self.assertTrue(all(value==0 for value in lexical.metrics(["x"],{"z"}).values()))

    def test_fixed_lexical_tie_order_and_empty_query(self):
        docs = {name:{"title":"same", "text":"cat"} for name in ("z","a")}
        index = lexical.build_index(docs)
        for method in lexical.METHODS:
            self.assertEqual(lexical.retrieve("cat",index,method),["a","z"])
            self.assertEqual(lexical.retrieve("unknown",index,method),[])
        with self.assertRaises(ValueError):
            lexical.retrieve("cat",index,"arbitrary method")

    def test_all_rankings_finish_before_first_score_and_adverse_no_hit_is_retained(self):
        packet = self.captured()
        original_rank, original_metrics = lexical.retrieve, lexical.metrics
        calls = []
        def rank(*args):
            calls.append(args[2])
            return original_rank(*args)
        def metrics(*args):
            self.assertEqual(len(calls),6)
            return original_metrics(*args)
        with patch.object(lexical,"retrieve",side_effect=rank),patch.object(lexical,"metrics",side_effect=metrics):
            tool = adapter.execute(packet)
        result = tool["result"]
        self.assertEqual(len(result["rankings"]),6)
        self.assertEqual(len(result["per_query_metrics"]),6)
        self.assertEqual(result["rankings_before_scoring_sha256"],fingerprint(result["rankings"]))
        self.assertTrue(any(row["query_id"]=="qv" for row in result["adverse_queries"]))
        self.assertEqual(tool["new_fits"],0)
        self.assertEqual(tool["model_calls"],0)
        self.assertFalse(tool["scientific_validation"])
        for row in result["rankings"]:
            self.assertEqual(len(row["ranking"]),len(row["ranked_doc_lines"]))
            self.assertGreater(row["query_line"],0)
        self.assertEqual(adapter.next_decision(tool)["next_action"]["method_id"],adapter.AUDIT_TOOL_ID)

    def test_saved_audit_does_not_index_rank_or_score_gold(self):
        tool = adapter.execute(self.captured())
        original = deepcopy(tool)
        parameters = {"based_on_action_id":"action-original","based_on_result_sha256":"f"*64}
        with patch.object(lexical,"build_index",side_effect=AssertionError("No index")), \
             patch.object(lexical,"retrieve",side_effect=AssertionError("No rerank")), \
             patch.object(lexical,"metrics",side_effect=AssertionError("No qrels scoring")):
            self.assertTrue(adapter.AUDIT.eligible(tool))
            audit = adapter.AUDIT.execute_saved(tool,parameters)
        self.assertEqual(tool,original)
        self.assertEqual(audit["result"]["summary"],tool["result"]["paired_summary"])
        self.assertEqual(audit["result"]["usage"]["ranking_calls"],0)
        self.assertEqual(audit["result"]["usage"]["scoring_calls"],0)
        self.assertEqual(audit["result"]["predecessor"],parameters)
        self.assertEqual(adapter.AUDIT.next_decision(audit)["project_status"],"waiting")

    def test_saved_audit_rejects_incomplete_changed_and_unpaired_results(self):
        tool = adapter.execute(self.captured())
        self.assertFalse(adapter.AUDIT.eligible({}))
        cases = [deepcopy(tool) for _ in range(5)]
        cases[0]["result"]["rankings"][0]["ranking"].append("changed")
        cases[1]["result"]["per_query_metrics"].pop()
        cases[2]["result"]["per_query_metrics"][0]["metrics"]["mrr@10"] = float("nan")
        cases[3]["model_calls"] = 1
        cases[4]["result"]["per_query_metrics"][0]["metrics"] = list(lexical.METRICS)
        for candidate in cases:
            with self.subTest(candidate=list(candidate)):
                self.assertFalse(adapter.AUDIT.eligible(candidate))
        changed = deepcopy(tool)
        changed["result"]["paired_summary"]["splits"]["dev"]["arms"]["bm25"]["queries"] = 999
        self.assert_rejected(adapter.AUDIT.execute_saved,changed,{"based_on_action_id":"a","based_on_result_sha256":"f"*64})

    def test_json_duplicate_nonfinite_invalid_utf8_and_unknown_packet_keys_reject(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'\xff',b'{"x":Infinity}'):
            with self.subTest(raw=raw):self.assert_rejected(adapter.load_source,raw)
        packet = self.captured()
        packet["extra"] = "unrecognized"
        self.assert_rejected(adapter.load_source,canonical(reseal(packet)).encode())

    def test_asset_hash_base64_name_scope_and_packet_caps_reject(self):
        original = self.captured()
        variants = []
        for key,value in (("sha256","0"*64),("bytes",True),("bytes_base64","!!"),("file_name","../corpus.jsonl")):
            packet=deepcopy(original);packet["assets"]["corpus"][key]=value;variants.append(packet)
        packet=deepcopy(original);packet["scope"]["document_count"]=999;variants.append(packet)
        for packet in variants:
            self.assert_rejected(adapter.load_source,canonical(reseal(packet)).encode())
        with patch.dict(adapter.LIMITS,{"packet_bytes":10}):
            self.assert_rejected(adapter.load_source,canonical(original).encode())

    def test_source_echoes_reject_numerically_equal_but_different_json_types(self):
        packet=self.captured()
        packet["spec"]["comparison"]["top_k"]=20.0
        self.assert_rejected(adapter.load_source,canonical(reseal(packet)).encode())
        one={"_id":"a","title":"one document","text":"cat dog fish","metadata":{}}
        (self.root/"corpus.jsonl").write_text(canonical(one)+"\n")
        (self.root/"qrels-train.tsv").write_text("query-id\tcorpus-id\tscore\nqd\ta\t1\nqv\ta\t1\n")
        (self.root/"qrels-test.tsv").write_text("query-id\tcorpus-id\tscore\nqt\ta\t1\n")
        packet=self.captured()
        self.assertEqual(packet["scope"]["document_count"],1)
        packet["scope"]["document_count"]=True
        self.assert_rejected(adapter.load_source,canonical(reseal(packet)).encode())

    def test_split_overlap_missing_labels_foreign_keys_and_qrel_duplicates_reject(self):
        self.spec["query_splits"]["test"]=["qd"]
        self.write_json("spec.json",self.spec)
        self.assert_rejected(self.captured)
        self.spec=fixture_spec();self.write_json("spec.json",self.spec)
        for content in ("query-id\tcorpus-id\tscore\nqt\tmissing\t1\n", "query-id\tcorpus-id\tscore\nqt\tc\t0\n",
                        "query-id\tcorpus-id\tscore\nqt\tc\t1\nqt\tc\t1\n", "query-id\tcorpus-id\tscore\nqd\ta\t1\n"):
            (self.root/"qrels-test.tsv").write_text(content)
            self.assert_rejected(self.captured)

    def test_duplicate_jsonl_ids_metadata_and_lone_surrogate_reject(self):
        original=(self.root/"corpus.jsonl").read_bytes()
        (self.root/"corpus.jsonl").write_bytes(original+original.splitlines(keepends=True)[0])
        self.assert_rejected(self.captured)
        row={"_id":"a","title":"a","text":"a","metadata":["not an object"]}
        (self.root/"corpus.jsonl").write_text(canonical(row))
        self.assert_rejected(self.captured)
        (self.root/"corpus.jsonl").write_bytes(b'{"_id":"a","title":"\\ud800","text":"a","metadata":{}}')
        self.assert_rejected(self.captured)

    def test_protocol_types_caps_methods_and_paths_reject(self):
        for section,key,value in (("comparison","top_k",20.0),("comparison","candidate","arbitrary"),("limits","packet_bytes",99999999),
                                  ("files","corpus","elsewhere/corpus.jsonl"),("source_provenance","qrels_semantics","support_refute")):
            changed=fixture_spec();changed[section][key]=value
            self.write_json("spec.json",changed)
            self.assert_rejected(self.captured)

    def test_c04_safe_reader_rejects_symlink_and_preserves_original(self):
        original=(self.root/"corpus.jsonl").read_bytes()
        elsewhere=self.root/"original-corpus"
        elsewhere.write_bytes(original)
        (self.root/"corpus.jsonl").unlink()
        (self.root/"corpus.jsonl").symlink_to(elsewhere)
        self.assert_rejected(self.captured)
        self.assertEqual(elsewhere.read_bytes(),original)

    def test_source_bytes_change_during_capture_is_rejected(self):
        real=adapter.reader._read_file
        counts={}
        def read(path,maximum):
            counts[path.name]=counts.get(path.name,0)+1
            data=real(path,maximum)
            return data+b' ' if path.name=='license.md' and counts[path.name]==2 else data
        with patch.object(adapter.reader,"_read_file",side_effect=read):
            self.assert_rejected(self.captured)

    def test_jsonl_physical_lines_preserve_unicode_separators(self):
        records=[{"_id":"a","title":"First\u2028title","text":"x\u0085y","metadata":{}},
                 {"_id":"b","title":"Second","text":"text","metadata":{}}]
        raw=(canonical(records[0])+"\r\n"+canonical(records[1])+"\n").encode("utf-8")
        docs,lines=adapter._jsonl(raw,True)
        self.assertEqual(lines,{"a":1,"b":2})
        self.assertEqual(docs["a"]["title"],"First\u2028title")
        self.assertEqual(docs["a"]["text"],"x\u0085y")

    def test_bounded_opaque_annotations_preserve_bytes_and_do_not_affect_ranking(self):
        first=adapter.execute(self.captured())
        path=self.root/"queries.jsonl"
        rows=[json.loads(line) for line in path.read_text().split("\n") if line.strip()]
        rows[0]["metadata"]={"a":[{"sentences":[0,1],"label":"CONTRADICT"}]}
        raw=("\n".join(canonical(row) for row in rows)+"\n").encode()
        path.write_bytes(raw)
        packet=self.captured()
        self.assertEqual(path.read_bytes(),raw)
        self.assertEqual(packet["assets"]["queries"]["sha256"],hashlib.sha256(raw).hexdigest())
        with patch.object(lexical,"retrieve",wraps=lexical.retrieve) as ranking,patch.object(lexical,"metrics",wraps=lexical.metrics) as scoring:
            second=adapter.execute(packet)
        self.assertTrue(all(type(call.args[0]) is str for call in ranking.call_args_list))
        self.assertTrue(all(type(call.args[0]) is list and type(call.args[1]) is dict for call in scoring.call_args_list))
        self.assertEqual([row["ranking"] for row in first["result"]["rankings"]],[row["ranking"] for row in second["result"]["rankings"]])
        self.assertEqual(first["result"]["paired_summary"],second["result"]["paired_summary"])

    def test_opaque_metadata_object_depth_nodes_size_and_primitives_are_bounded(self):
        depth={"leaf":None}
        for _ in range(8):depth={"nested":depth}
        invalid=[[],depth,{"too_many":list(range(513))},{"long_key"*20:None},{"value":"x"*4097},
                 {"nan":float("nan")},{"surrogate":"\ud800"},{str(n):"x"*4096 for n in range(5)}]
        for value in invalid:
            with self.subTest(kind=type(value).__name__):
                self.assert_rejected(adapter._metadata,value)
        row={"_id":"qd","text":"cat","metadata":{"bad":"\ud800"}}
        (self.root/"queries.jsonl").write_text(json.dumps(row,ensure_ascii=True))
        self.assert_rejected(self.captured)
        adapter._metadata({"empty":"","nullable":None,"flag":True,"finite":1.5,"nested":[1,{"value":"α"}]})

    def test_free_execution_parameters_rejected(self):
        self.assert_rejected(adapter.execute,self.captured(),{"command":"arbitrary"})
        self.assert_rejected(adapter.AUDIT.execute_saved,{}, {"based_on_action_id":"a","based_on_result_sha256":"f"*64,"parameters":{}})


if __name__ == "__main__":
    unittest.main()
