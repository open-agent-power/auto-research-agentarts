import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autoresearch import evidence_catalog as catalog
from autoresearch.contracts import ResearchError, canonical, fingerprint


def sealed(schema, **fields):
    value = {'schema_version': schema, 'scientific_validation': False, **fields}
    value['snapshot_sha256'] = fingerprint(value)
    return value


class EvidenceCatalogTests(unittest.TestCase):
    def test_sealed_chain_pointer_recomputation_tasks_and_exact_readback(self):
        source = {'file': 'captured.cpproj', 'bytes': 17, 'sha256': 'a' * 64}
        baseline = sealed('p02-workbench-v1', source_manifest=[source],
                          endpoint_gate={'ALP_eligible': False, 'fit_eligible': False,
                                         'scope': 'old source-policy only'})
        iteration = sealed('p02-iteration-view-v1', baseline_publication_sha256=baseline['snapshot_sha256'],
                           endpoint_gate={'biological_fit_eligible': False, 'numerical_fit_eligible': True})
        policies = [{'policy': p, 'candidate_mae': .3, 'chemistry_mae': .2,
                     'delta_mae': .1, 'comparison': 'worse'} for p in catalog.POLICIES]
        diagnostic = sealed('p02-diagnostic-view-v1', iteration_snapshot_sha256=iteration['snapshot_sha256'],
                            candidate_facts={'policies': policies},
                            topography={'summary': {'policies': {p: {'methods': {'current_candidate': {
                                'worse_groups': 24, 'better_groups': 11, 'tied_groups': 0, 'group_count': 35}}}
                                for p in catalog.POLICIES}}},
                            prior_diagnostics=[{'id': 'chem', 'action': 'inspect_residuals'}],
                            actions=[{'id': 'topo', 'action': 'inspect_topography'},
                                     {'id': 'judgment', 'action': 'investigate_data_mapping',
                                      'reason': 'Unverified p < .001 is not a performed test'}])
        inventory = {'schema_version': 'chemotopo-project-inventory-v1', 'source': source,
                     'inventory': {'measurements': [{'groups': ['Experiment', 'Image'],
                                                     'features': {'Image': ['ImageNumber']}}]},
                     'ome_filelist': [{'filename': 'POS' + str(i), 'channels': [{'Name': 'DAPI'}]}
                                      for i in range(4)]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for sub in ('diag', 'iteration', 'baseline'):
                (root / sub).mkdir()
            raw = {key: (canonical(value) + '\n').encode('utf-8') for key, value in
                   [('diagnostic', diagnostic), ('iteration', iteration), ('baseline', baseline), ('inventory', inventory)]}
            (root / 'iteration' / 'iteration.json').write_bytes(raw['iteration'])
            (root / 'baseline' / 'research.json').write_bytes(raw['baseline'])
            (root / 'inventory.json').write_bytes(raw['inventory'])
            with patch('autoresearch.chemotopo_publication.read_artifacts', return_value={'research.json': raw['baseline']}) as b, \
                 patch('autoresearch.chemotopo_iteration_report.read_iteration_artifacts', return_value={'iteration.json': raw['iteration']}) as i, \
                 patch('autoresearch.diagnostic_view.read_diagnostic_artifacts', return_value={'diagnostic.json': raw['diagnostic']}) as d:
                result = catalog.build_catalog(root / 'diag', root / 'iteration', root / 'baseline', root / 'inventory.json')
                b.assert_called_once(); i.assert_called_once(); d.assert_called_once()
            catalog.validate_catalog(result)
            selected = catalog.read_facts(result, ['source_gate', 'candidate_vs_chem.positive_equal_batch',
                                                    'diagnostic_statistics_scope'])
            self.assertFalse(selected[0]['value']['fit_eligible'])
            self.assertEqual(selected[1]['value']['comparison'], 'worse')
            self.assertEqual(selected[2]['value']['statistical_tests_in_these_tools'], [])
            self.assertEqual(len(selected[2]['value']['analyses']), 2)
            self.assertEqual(result['source_payloads']['diagnostic'], raw['diagnostic'].decode())
            for task in result['tasks']:
                self.assertTrue(1 <= len(task['required_fact_ids']) <= 8)
                self.assertTrue(task['requires_external_data'])
                self.assertEqual(task['origin'], 'host_curated_template')
                catalog.read_facts(result, task['required_fact_ids'])
            for change in ('fact', 'task', 'source_hash', 'source_text'):
                altered = copy.deepcopy(result)
                if change == 'fact': altered['facts'][0]['value']['comparison'] = 'better'
                elif change == 'task': altered['tasks'][0]['requires_external_data'] = False
                elif change == 'source_hash': altered['source_snapshots']['inventory']['file_sha256'] = 'b' * 64
                else: altered['source_payloads']['diagnostic'] = altered['source_payloads']['diagnostic'].replace('"candidate_mae":0.3', '"candidate_mae":0.1')
                altered['snapshot_sha256'] = fingerprint({k: v for k, v in altered.items() if k != 'snapshot_sha256'})
                with self.assertRaises(ResearchError): catalog.validate_catalog(altered)
            with self.assertRaises(ResearchError): catalog.read_facts(result, ['source_gate', 'source_gate'])
            with self.assertRaises(ResearchError): catalog.read_facts(result, ['invented'])
            selected[0]['value']['fit_eligible'] = True
            self.assertFalse(catalog.read_facts(result, ['source_gate'])[0]['value']['fit_eligible'])


if __name__ == '__main__':
    unittest.main()
