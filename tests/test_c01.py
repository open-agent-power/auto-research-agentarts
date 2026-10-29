"""Synthetic C01-format fixtures test this protocol, not scientific validity."""
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

from autoresearch import c01


def workbook(cells, *, external=False):
    ns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    root=ET.Element("worksheet",xmlns=ns);data=ET.SubElement(root,"sheetData")
    for ref,value in cells.items():
        row=ET.SubElement(data,"row");cell=ET.SubElement(row,"c",r=ref)
        if isinstance(value,tuple):
            ET.SubElement(cell,"f").text=value[0];ET.SubElement(cell,"v").text=str(value[1])
        elif isinstance(value,str):
            cell.set("t","inlineStr");ET.SubElement(ET.SubElement(cell,"is"),"t").text=value
        else:ET.SubElement(cell,"v").text=str(value)
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml",'<workbook xmlns="'+ns+'" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Fixture" sheetId="1" r:id="r1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels",'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Target="worksheets/sheet1.xml"'+(' TargetMode="External"' if external else '')+'/></Relationships>')
        archive.writestr("xl/worksheets/sheet1.xml",ET.tostring(root,encoding="utf-8"))
    return out.getvalue()


def fixture_archive():
    main,bio={},{}
    target_values={target["id"]:[] for target in c01.TARGETS}
    for i in range(8):
        row,br=i+5,i+7
        main["A"+str(row)]="Alloy "+str(i+1);bio["B"+str(br)]="B"+str(i+24)+( "*" if i in (1,2,4) else "")
        for column,value in {"P":80-i*2,"R":900-i*20,"W":70+(i%3),"AN":48+i*.3,"AT":10000+i*1000,"BP":.0001+i*.00001}.items():main[column+str(row)]=value
        main["P"+str(row)]=("do_not_execute_this_formula()",80-i*2)
        main["N"+str(row)]="<0.1"
        for j,target in enumerate(c01.TARGETS):
            value=80+i if j==0 else (200000+i*12000 if j==1 else (1.2+(i%2)*3 if j==2 else 250+i*6))
            main[target["column"]+str(row)]=value;bio[target["bio_column"]+str(br)]=value
            target_values[target["id"]].append(value)
        bio["H"+str(br)]=main["AT"+str(row)];bio["G"+str(br)]=main["BP"+str(row)]
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as archive:
        for name in c01.ATTACHMENTS:
            payload=workbook(main) if name==c01.MAIN else workbook(bio) if name==c01.BIO else b"raw evidence unit fixture; not executed"
            archive.writestr("case/attachments/"+name,payload)
        buf=io.StringIO();writer=csv.DictWriter(buf,fieldnames=["target","mean_baseline_mae"]);writer.writeheader()
        for name,values in target_values.items():
            y=np.asarray(values);writer.writerow({"target":name,"mean_baseline_mae":float(np.mean(np.abs(y-y.mean())))})
        archive.writestr("case/loo_ridge_summary.csv",buf.getvalue())
    return out.getvalue()


class C01Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.archive=self.root/"input.zip";self.payload=fixture_archive();self.archive.write_bytes(self.payload)
        self.patcher=patch.object(c01,"EXPECTED_ARCHIVE_SHA256",hashlib.sha256(self.payload).hexdigest());self.patcher.start();self.addCleanup(self.patcher.stop)

    def error(self,code,call):
        with self.assertRaises(c01.C01Error) as caught:call()
        self.assertEqual(caught.exception.code,code)

    def test_loads_raw_workbook_caches_and_preserves_provenance(self):
        with patch("socket.create_connection",side_effect=AssertionError("network forbidden")):
            bundle=c01.load_archive(self.archive)
        self.assertEqual(len(bundle["samples"]),8)
        self.assertEqual(bundle["samples"][0]["ecm_gpa"],80.)
        self.assertEqual(bundle["provenance"][0]["formula"],"do_not_execute_this_formula()")
        self.assertTrue(all(item["consistent_with_row_mapping"] for item in bundle["bio_mapping"]))
        self.assertEqual(bundle["source"]["doi"],"10.17632/tt7gwkpck8.1")
        self.assertEqual(self.archive.read_bytes(),self.payload)

    def test_censoring_is_upper_bound_not_measurement(self):
        result=c01.parse_measurement("<0.02")
        self.assertIsNone(result["value"]);self.assertEqual(result["upper_bound"],.02)
        self.assertEqual(result["status"],"left_censored_upper_bound")
        for value in ("see other file","", "NaN", "1e999"):
            self.assertIsNone(c01.parse_measurement(value)["value"])

    def test_archive_identity_is_pinned(self):
        with patch.object(c01,"EXPECTED_ARCHIVE_SHA256","0"*64):
            self.error("ARCHIVE_CHANGED",lambda:c01.load_archive(self.archive))

    def test_unsafe_zip_paths_and_resource_bombs_are_rejected(self):
        for name in ("../escape.csv","/absolute","C:/drive","root\\escape"):
            buf=io.BytesIO()
            info=zipfile.ZipInfo("placeholder")
            info.filename=name  # Preserve the unsafe raw separator on Windows too.
            with zipfile.ZipFile(buf,"w") as archive:archive.writestr(info,b"test")
            self.error("UNSAFE_ARCHIVE",lambda:c01._safe_zip(buf.getvalue()))
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as archive:archive.writestr("compressed.txt",b"x"*1_000_000)
        self.error("ARCHIVE_LIMIT",lambda:c01._safe_zip(buf.getvalue()))

    def test_external_workbook_relationship_is_not_followed(self):
        self.error("INVALID_WORKBOOK",lambda:c01._workbook(workbook({"A1":1},external=True)))
        self.error("UNSAFE_XML",lambda:c01._xml(b'<!DOCTYPE x [<!ENTITY bad "boom">]><x/>'))

    def test_each_baseline_and_prediction_excludes_held_out_label(self):
        x=np.arange(32,dtype=float).reshape(8,4);y=np.asarray([2,5,8,12,16,18,21,27],dtype=float)
        predicted,baseline=c01.loo_predictions(x,y,1.)
        for index in range(8):self.assertAlmostEqual(baseline[index],float(np.mean(np.delete(y,index))))
        changed=y.copy();changed[0]+=9999
        other,other_baseline=c01.loo_predictions(x,changed,1.)
        self.assertAlmostEqual(predicted[0],other[0]);self.assertAlmostEqual(baseline[0],other_baseline[0])
        self.assertNotAlmostEqual(baseline[0],float(y.mean()))

    def test_standardization_fits_only_seven_training_rows(self):
        x=np.arange(32,dtype=float).reshape(8,4);y=np.arange(8,dtype=float)**2
        seen=[];original=c01.StandardScaler.fit
        def fit(scaler,values,*args,**kwargs):seen.append(np.asarray(values).copy());return original(scaler,values,*args,**kwargs)
        with patch.object(c01.StandardScaler,"fit",fit):c01.loo_predictions(x,y,1.)
        self.assertEqual(len(seen),8)
        for index,values in enumerate(seen):np.testing.assert_equal(values,np.delete(x,index,axis=0))

    def test_outputs_and_feedback_rule_are_stable_and_bounded(self):
        before=hashlib.sha256(self.archive.read_bytes()).hexdigest()
        with patch.object(c01,"render_figures",return_value=([],"optional_matplotlib_unavailable",None)),patch("socket.create_connection",side_effect=AssertionError("network forbidden")):
            first=c01.analyze_archive(self.archive,self.root/"one")
            second=c01.analyze_archive(self.archive,self.root/"two")
        self.assertEqual(first,second)
        self.assertEqual(first["data"]["sample_count"],8)
        self.assertEqual(len(first["rounds"]),2)
        expect=100. if any(not value["better_than_baseline"] for value in first["rounds"][0]["metrics"]) else 1.
        self.assertEqual(first["rounds"][1]["alpha"],expect)
        self.assertEqual(first["cloud_calls"]+first["model_calls"],0)
        self.assertEqual(hashlib.sha256(self.archive.read_bytes()).hexdigest(),before)
        self.assertEqual((self.root/"one/evidence/input.zip").read_bytes(),self.payload)
        self.assertEqual(json.loads((self.root/"one/summary.json").read_text(encoding="utf-8")),first)
        with (self.root/"one/loo_predictions.csv").open(encoding="utf-8-sig",newline="") as stream:rows=list(csv.DictReader(stream))
        self.assertEqual(len(rows),64)
        for row in rows:
            self.assertEqual(row["training_n"],"7")
            self.assertNotIn(row["sample_id"],row["training_sample_ids"].split(";"))
        self.assertTrue(any("全8样本均值" in row["issue"] for row in first["audit"]))
        self.assertEqual(first["data"]["feature_names"],list(c01.FEATURES))
        self.assertEqual(first["audit"][0]["origin"],"manual_pre_review")
        self.assertTrue(any(row["origin"]=="program_check" for row in first["audit"]))

    def test_domain_warnings_keep_unclipped_values_and_sample_ids(self):
        bundle=c01.load_archive(self.archive)
        calls=iter((np.array([110.,-5.,80.,81.,82.,83.,84.,85.]),
                    np.arange(8,dtype=float)+250000,
                    np.array([1.,2.,3.,-2.,1.,2.,3.,4.]),np.arange(8,dtype=float)+300))
        def values(x,y,alpha):
            return next(calls),np.asarray([np.mean(np.delete(y,i)) for i in range(8)])
        with patch.object(c01,"loo_predictions",side_effect=values):
            result,predictions=c01._round(bundle["samples"],1,1.,c01.FEATURES)
        self.assertEqual(len(result["domain_violations"]),3)
        self.assertEqual(result["domain_violations"][0]["sample_id"],"Alloy 1")
        self.assertEqual(result["domain_violations"][0]["predicted"],110.)
        self.assertEqual(predictions[0]["predicted"],110.)
        self.assertEqual(result["domain_violations"][-1]["predicted"],-2.)
        self.assertIn("未裁剪",result["feedback"])
        self.assertIn("Alloy 1",result["feedback"])
        self.assertIn("不代表有效生物预测",result["feedback"])

    def make_output(self,name="verified",with_figures=False):
        def figures(directory,rounds,predictions):
            directory.mkdir()
            records=[]
            for index,relative in enumerate(c01.OUTPUT_FIGURES,1):
                (directory/Path(relative).name).write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>unit fixture</text></svg>',encoding="utf-8")
                records.append({"id":"F-C01-"+str(index),"path":relative,"title":"test","caption":"synthetic fixture"})
            return records,"generated","test-fixture"
        output=self.root/name
        with patch.object(c01,"render_figures",side_effect=figures if with_figures else lambda *args:([],"optional_matplotlib_unavailable",None)):
            result=c01.analyze_archive(self.archive,output)
        return output,result

    def test_complete_output_manifest_and_readonly_verification(self):
        output,result=self.make_output()
        manifest=json.loads((output/c01.OUTPUT_MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(set(manifest),{"schema_version","files"})
        self.assertEqual(manifest["schema_version"],"c01-output-manifest-v1")
        self.assertEqual(set(manifest["files"]),c01.OUTPUT_BASE_FILES)
        self.assertEqual(len(manifest["files"]),12)
        self.assertNotIn(c01.OUTPUT_MANIFEST,manifest["files"])
        before={p.relative_to(output).as_posix():p.read_bytes() for p in output.rglob("*") if p.is_file()}
        for name,digest in manifest["files"].items():
            self.assertEqual(hashlib.sha256((output/name).read_bytes()).hexdigest(),digest)
        self.assertEqual(c01.verify_output(output),result)
        self.assertEqual({p.relative_to(output).as_posix():p.read_bytes() for p in output.rglob("*") if p.is_file()},before)

    def test_each_fixed_artifact_tamper_is_rejected(self):
        output,_=self.make_output()
        for index,relative in enumerate(sorted(c01.OUTPUT_BASE_FILES)):
            with self.subTest(relative=relative):
                changed=self.root/("tamper-"+str(index));shutil.copytree(output,changed)
                target=changed/relative;target.write_bytes(target.read_bytes()+b"tampered")
                self.error("OUTPUT_INTEGRITY_FAILED",lambda:c01.verify_output(changed))

    def test_output_manifest_rejects_missing_extra_and_unsafe_entries(self):
        output,_=self.make_output()
        manifest_path=output/c01.OUTPUT_MANIFEST
        original=json.loads(manifest_path.read_text(encoding="utf-8"))
        for label,mutate in (
            ("missing",lambda files:files.pop("rounds.csv")),
            ("escape",lambda files:files.update({"../outside.txt":"0"*64})),
            ("external",lambda files:files.update({"https://external.invalid/result":"0"*64})),
            ("wronghash",lambda files:files.update({"summary.json":"0"*64})),
        ):
            with self.subTest(label=label):
                manifest=json.loads(json.dumps(original));mutate(manifest["files"])
                manifest_path.write_text(json.dumps(manifest),encoding="utf-8")
                self.error("OUTPUT_INTEGRITY_FAILED",lambda:c01.verify_output(output))
        manifest_path.write_text(json.dumps(original),encoding="utf-8")
        (output/"unexpected.csv").write_text("not an approved result")
        self.error("OUTPUT_INTEGRITY_FAILED",lambda:c01.verify_output(output))

    def test_optional_svg_manifest_set_must_match_summary(self):
        output,result=self.make_output(with_figures=True)
        manifest_path=output/c01.OUTPUT_MANIFEST
        manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["files"]),14)
        self.assertEqual(set(manifest["files"]),c01.OUTPUT_BASE_FILES|set(c01.OUTPUT_FIGURES))
        self.assertEqual(c01.verify_output(output),result)
        result["artifacts"]["figures"][0]["path"]="https://external.invalid/chart.svg"
        summary_path=output/"summary.json";summary_path.write_text(c01._json(result),encoding="utf-8")
        manifest["files"]["summary.json"]=hashlib.sha256(summary_path.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest),encoding="utf-8")
        self.error("OUTPUT_INTEGRITY_FAILED",lambda:c01.verify_output(output))

    def test_existing_output_and_bad_rounds_are_rejected_without_writes(self):
        output=self.root/"existing";output.mkdir();(output/"original.txt").write_text("keep")
        self.error("OUTPUT_EXISTS",lambda:c01.analyze_archive(self.archive,output))
        self.assertEqual((output/"original.txt").read_text(),"keep")
        for rounds in (0,3,True,"2"):
            self.error("INVALID_REQUEST",lambda:c01.analyze_archive(self.archive,self.root/"unused",rounds=rounds))
        self.assertFalse((self.root/"unused").exists())

    def test_copied_script_has_standalone_cli(self):
        target=self.root/"standalone.py";shutil.copyfile(c01.__file__,target)
        result=subprocess.run([sys.executable,"-I",str(target),"--help"],capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors="replace"))
        self.assertIn(b"--archive",result.stdout)


if __name__=="__main__":unittest.main()
