import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np

from autoresearch import chemotopo_interaction as module


def rows():
    return [{'topography':t,'chemistry':c,'geometry':[float(t*(j+1)) for j in range(10)],
             'target':float(t*.3+c),'fold':t-1,'chemistry_prediction':1.0,'additive_prediction':1.1}
            for t in (2,3,4,5) for c in (0,1)]


class InteractionTests(unittest.TestCase):
    def test_holdout_target_and_geometry_preprocessing_are_train_only(self):
        original=rows(); altered=copy.deepcopy(original)
        for r in altered:
            if r['topography']==5:r['target']+=9999
        first=module.grouped_interactions(original);other=module.grouped_interactions(altered)
        select=lambda result:[r['interaction_prediction'] for r in result['records'] if r['topography']==5]
        np.testing.assert_allclose(select(first),select(other),rtol=0,atol=0)
        f=first['folds'][-1]
        self.assertTrue(set(f['train_topographies']).isdisjoint(f['test_topographies']))
        self.assertEqual(f['test_topographies'],[5]);self.assertEqual(f['chemistry_categories'],[0,1])
        train=[r['geometry'] for r in original if r['topography']!=5]
        np.testing.assert_allclose(f['geometry_scaler']['mean'],np.mean(train,axis=0))
        self.assertEqual(f['feature_counts'],{'chemistry_main':2,'geometry_main':10,'interactions':20,'total':32})
        self.assertEqual(len(first['paired_fold_mae']),4)

    def test_reject_unknown_chemistry_and_inconsistent_baseline_fold(self):
        unknown=rows();unknown[-1]['chemistry']=9
        with self.assertRaisesRegex(ValueError,'chemistry absent'):module.grouped_interactions(unknown)
        bad=rows();bad[-1]['fold']=2
        with self.assertRaisesRegex(ValueError,'baseline fold'):module.grouped_interactions(bad)
        checked={'verified_predictions':[{'policy':'p','recipe':'chemistry_ridge','topography':'2','chemistry':'0','fold':'1','target':'2','prediction':'1'},
                    {'policy':'p','recipe':'chemistry_geometry_ridge','topography':'2','chemistry':'0','fold':'2','target':'2','prediction':'1'}]}
        with self.assertRaisesRegex(ValueError,'baseline key, fold or target mismatch'):module._baseline_rows(checked,{2:[1.]*10},'p')

    def test_frozen_protocol_mismatch_and_existing_output_never_fit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'out'
            with patch.object(module,'_prepare',return_value=({'fixture':'fixed'},None,None)),patch.object(module,'grouped_interactions') as fit:
                with self.assertRaisesRegex(ValueError,'protocol differs'):module.run_interaction(root/'source',root/'baseline',target,'0'*64)
                self.assertFalse(target.exists());fit.assert_not_called()
                target.mkdir()
                with self.assertRaises(FileExistsError):module.run_interaction(root/'source',root/'baseline',target)
                fit.assert_not_called()


if __name__=='__main__':unittest.main()
