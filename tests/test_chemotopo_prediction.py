import copy
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np
from autoresearch import chemotopo_prediction as module
from autoresearch.contracts import ResearchError


def sample():
    return [{'topography':t,'chemistry':c,'geometry':[float(t*(j+1)) for j in range(10)],
             'target':float(t*.4+c)} for t in (2,3,4,5) for c in (0,1)]


class PredictionTests(unittest.TestCase):
    def test_heldout_target_change_cannot_change_its_predictions(self):
        rows=sample(); changed=copy.deepcopy(rows)
        for r in changed:
            if r['topography']==5:r['target']+=9999
        first=module.grouped_predictions(rows); second=module.grouped_predictions(changed)
        def heldout(result): return {(r['chemistry'],r['recipe']):r['prediction'] for r in result['records'] if r['topography']==5}
        self.assertEqual(heldout(first),heldout(second))
        for fold in first['folds']:
            self.assertTrue({key[0] for key in fold['train_keys']}.isdisjoint({key[0] for key in fold['test_keys']}))
            self.assertEqual({key[0] for key in fold['test_keys']},{fold['held_out_topography']})

    def test_training_only_scaler_and_encoder(self):
        rows=sample(); result=module.grouped_predictions(rows)
        fold=next(f for f in result['folds'] if f['held_out_topography']==5)
        train=[r for r in rows if r['topography']!=5]
        self.assertEqual(fold['chemistry_categories'],[0,1])
        np.testing.assert_allclose(fold['geometry_scaler']['mean'],np.mean([r['geometry'] for r in train],axis=0))
        self.assertEqual(fold['training_geometry_bounds'][0]['max'],4)
        unseen=sample(); unseen[-1]['chemistry']=9
        with self.assertRaisesRegex(ValueError,'chemistry absent'): module.grouped_predictions(unseen)
        self.assertEqual(len(result['records']),len(rows)*3)
        self.assertAlmostEqual(result['metrics']['train_mean']['skill_vs_oof_train_mean_mae'],0)

    def test_existing_output_rejected_before_any_fit_or_reconstruction(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(module,'build_protocol',return_value={'fixture':True}), \
                 patch.object(module.rebuild,'run_reconstruction') as reconstruction, \
                 patch.object(module,'grouped_predictions') as fits:
                with self.assertRaises(FileExistsError): module.run_diagnostic('unused',directory)
                reconstruction.assert_not_called(); fits.assert_not_called()

    def test_reject_invalid_sources_and_nonfinite_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises((ResearchError,OSError)):module.build_protocol(Path(directory))
        rows=sample(); rows[0]['geometry'][0]=float('nan')
        with self.assertRaises(ValueError):module.grouped_predictions(rows)


if __name__=='__main__': unittest.main()
