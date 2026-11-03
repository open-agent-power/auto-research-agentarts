from io import BytesIO
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from autoresearch.configured_iteration_report import _package
from autoresearch.contracts import canonical, fingerprint


POLICIES=['recorded_equal_batch','positive_equal_batch','recorded_equal_section','positive_equal_section']


def fixture(candidate=False):
    keys=[(t,c) for t in range(2,37) for c in range(25)][:870]
    rows=[{'topography':t,'chemistry':c,'fold':t-1,'geometry':[0.]*10,'target':t*100+c,
           'chemistry_prediction':t*100+c+.5,'additive_prediction':t*100+c+1.,
           'interaction_prediction':t*100+c+2.} for t,c in keys]
    folds=[{'fold':t-1,'held_out_topography':t,'train_keys':[[a,b] for a,b in keys if a!=t],
            'test_keys':[[a,b] for a,b in keys if a==t]} for t in range(2,37)]
    def metric(error):return {'pooled_mae':error,'pooled_rmse':error,'pooled_spearman_midrank':1.,'macro_fold_mae':error}
    prior={'metrics':{p:{'chemistry':metric(.5),'additive':metric(1.),'interaction':metric(2.)} for p in POLICIES}}
    inputs={'schema_version':'p02-configured-inputs-v1','executor_id':'p02-interaction-ridge-v1','policies':POLICIES,
            'rows_by_policy':{p:rows for p in POLICIES},'folds_by_policy':{p:folds for p in POLICIES},'prior_evidence':prior}
    protocol={'schema_version':'configured-iteration-protocol-v1','executor_id':'p02-interaction-ridge-v1',
              'goal':'数值夹具','candidates':[{'id':'alpha3','alpha':3.}],'max_fits':140,'max_requests':2}
    raw=canonical(inputs).encode();inputsha=hashlib.sha256(raw).hexdigest()
    view={'schema_version':'p02-iteration-view-v1','inputs_sha256':inputsha,'protocol':protocol,
          'study_configuration_sha256':'b'*64,'prior_evidence':prior,'actions':[],'comparisons':[],
          'execution':{'completed_candidates':0,'completed_fits':0}}
    artifacts={}
    if candidate:
        summary={'candidate_id':'alpha3','alpha':3.,'fit_count':140,'metrics':{p:{**metric(1.5),
                 'r59_alpha1_mae':2.,'r54_additive_mae':1.,'r54_chemistry_mae':.5} for p in POLICIES}}
        result={'schema_version':'configured-candidate-result-v1','request_sha256':'c'*64,'configuration_sha256':'b'*64,
                'inputs_sha256':inputsha,'candidate_id':'alpha3','alpha':3.,'summary':summary,
                'predictions':[{'policy':p,'topography':t,'chemistry':c,'fold':t-1,'target':t*100+c,'prediction':t*100+c+1.5} for p in POLICIES for t,c in keys],
                'folds':{p:folds for p in POLICIES}}
        payload=canonical(result).encode();action={'id':'action3','action':'run_candidate','parameters':{'candidate_id':'alpha3'},
            'summary':summary,'result_sha256':fingerprint({'summary':summary,'artifact':{'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)}})}
        view['actions']=[action];view['execution']={'completed_candidates':1,'completed_fits':140}
        view['comparisons']=[{'action_id':'action3','alpha':3.,'policies':[{'policy':p,'mae':1.5,'spearman':1.,
                             'alpha1_mae':2.,'additive_mae':1.,'chemistry_mae':.5,
                             'delta_vs_alpha1':-.5,'delta_vs_additive':.5,'delta_vs_chemistry':1.} for p in POLICIES]}]
        artifacts={'action3':result}
    view['snapshot_sha256']=fingerprint(view)
    return view,{'inputs':inputs,'inputs_bytes':raw,'config':{'protocol':protocol},'candidate_artifacts':artifacts}


class ConfiguredPackageTests(unittest.TestCase):
    def unpack(self,candidate):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        view,private=fixture(candidate)
        with zipfile.ZipFile(BytesIO(_package(view,private))) as archive:archive.extractall(root)
        return root

    def verify(self,root):
        return subprocess.run([sys.executable,'-I','-S','-B',str(root/'verify.py')],cwd=root,capture_output=True,text=True)

    def test_zero_candidate_package_recomputes_baselines_without_invented_fits(self):
        result=self.verify(self.unpack(False))
        self.assertEqual(result.returncode,0,result.stderr)
        outcome=json.loads(result.stdout)
        self.assertEqual(outcome['input_rows'],3480);self.assertEqual(outcome['candidate_rows'],0)
        self.assertEqual(outcome['new_fits'],0);self.assertEqual(outcome['model_calls'],0)

    def test_rehashed_candidate_arithmetic_tamper_is_rejected(self):
        root=self.unpack(True)
        good=self.verify(root);self.assertEqual(good.returncode,0,good.stderr)
        name='candidates/alpha3.json';path=root/name;value=json.loads(path.read_text())
        value['predictions'][0]['prediction']+=1
        raw=(canonical(value)+'\n').encode();path.write_bytes(raw)
        manifest=json.loads((root/'package-manifest.json').read_text())
        manifest['files'][name]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
        view=json.loads((root/'iteration.json').read_text(encoding='utf-8'))
        payload=canonical(value).encode()
        view['actions'][0]['result_sha256']=fingerprint({'summary':value['summary'],'artifact':{
            'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)}})
        view.pop('snapshot_sha256');view['snapshot_sha256']=fingerprint(view)
        public=(canonical(view)+'\n').encode();(root/'iteration.json').write_bytes(public)
        manifest['snapshot_sha256']=view['snapshot_sha256']
        manifest['files']['iteration.json']={'sha256':hashlib.sha256(public).hexdigest(),'bytes':len(public)}
        (root/'package-manifest.json').write_text(json.dumps(manifest))
        bad=self.verify(root);self.assertNotEqual(bad.returncode,0)
        self.assertIn('metric arithmetic differs',bad.stderr)


if __name__=='__main__':unittest.main()
