import csv
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from autoresearch import chemotopo_experiment_evidence as module
from autoresearch.contracts import ResearchError, canonical


class ExperimentEvidenceTests(unittest.TestCase):
    def test_manifest_and_source_target_tamper_rejected_without_fitting(self):
        base=Path(__file__).resolve().parents[1]
        source=base.parent.parent/'references/auto-research/10-chemotopochip/2026-10-31'
        if not (base/'runs/r54-grouped-proxy-prediction/manifest.json').is_file() or not (source/'Modelling_Descriptors.xlsx').is_file():
            self.skipTest('R54 experiment or pinned original sources are unavailable in this checkout')
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'experiment'; shutil.copytree(base/'runs/r54-grouped-proxy-prediction',dest)
            original=module.attachment(dest,source)['manifest_sha256']
            csvpath=dest/'results.csv'
            with csvpath.open(encoding='utf-8',newline='') as stream:
                reader=csv.DictReader(stream); fields=reader.fieldnames; rows=list(reader)
            rows[0]['target']=str(float(rows[0]['target'])+1)
            with csvpath.open('w',encoding='utf-8',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader();writer.writerows(rows)
            with self.assertRaises(ResearchError):module.attachment(dest,source,original)
            manifest_path=dest/'manifest.json'; manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
            manifest['files']['results.csv']={'sha256':hashlib.sha256(csvpath.read_bytes()).hexdigest(),'bytes':csvpath.stat().st_size}
            manifest_path.write_text(canonical(manifest)+'\n',encoding='utf-8')
            forged=hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            with self.assertRaises(ResearchError):module.inspect_experiment(dest,source,forged)


    def test_changed_train_mean_is_rejected_even_when_manifest_is_rehashed(self):
        base=Path(__file__).resolve().parents[1]
        source=base.parent.parent/'references/auto-research/10-chemotopochip/2026-10-31'
        if not (base/'runs/r54-grouped-proxy-prediction/manifest.json').is_file() or not (source/'Modelling_Descriptors.xlsx').is_file():
            self.skipTest('R54 experiment or pinned original sources are unavailable in this checkout')
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'experiment'; shutil.copytree(base/'runs/r54-grouped-proxy-prediction',dest)
            path=dest/'results.csv'
            with path.open(encoding='utf-8',newline='') as stream:
                reader=csv.DictReader(stream); fields=reader.fieldnames; rows=list(reader)
            first=next(row for row in rows if row['recipe']=='train_mean'); first['prediction']=str(float(first['prediction'])+1)
            with path.open('w',encoding='utf-8',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
            mp=dest/'manifest.json'; manifest=json.loads(mp.read_text(encoding='utf-8'))
            manifest['files']['results.csv']={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
            mp.write_text(canonical(manifest)+'\n',encoding='utf-8')
            with self.assertRaisesRegex(ResearchError,'train-mean'):
                module.inspect_experiment(dest,source,hashlib.sha256(mp.read_bytes()).hexdigest())


if __name__=='__main__':unittest.main()
