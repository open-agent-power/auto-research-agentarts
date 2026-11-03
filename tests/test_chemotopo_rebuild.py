import json
import unittest
from unittest.mock import patch

from autoresearch import chemotopo_rebuild as module
from autoresearch.contracts import ResearchError


def spot(row,count,red):return {'row':row,'count':count,'red':red,'green':0}


def sections():
    return {
        'B8S1':{(1,0):[spot(2,1,2),spot(3,1,6)],(2,0):[spot(4,5,8),spot(5,0,0)]},
        'B8S2':{(1,0):[spot(2,1,4)],(2,0):[spot(3,1,12)]},
        'B9S1':{(1,0):[spot(2,1,1)],(2,0):[spot(3,1,3)]},
        'B10S1':{(1,0):[spot(2,1,1)],(2,0):[spot(3,1,4)]},
    }


def row(policy,key=(2,0)):
    return next(r for r in policy['combinations'] if (r['topography'],r['chemistry'])==key)


class ChemoTopoRebuildTests(unittest.TestCase):
    def test_unresolved_alp_fails_before_io_even_if_caller_requests_it(self):
        with patch.object(module,'_captured',side_effect=AssertionError('must not read')):
            with self.assertRaises(ResearchError) as error:module.run_reconstruction('absent',endpoint='alp')
        self.assertEqual(error.exception.code,'ENDPOINT_UNRESOLVED')
        with self.assertRaises(ResearchError):module.run_reconstruction('absent',endpoint='unknown')

    def test_equal_batch_is_not_equal_section_and_zero_policy_changes_estimand(self):
        source=sections()
        recorded_batch=module.reconstruct(source,positive_only=False,aggregation='equal_batch')
        recorded_section=module.reconstruct(source,positive_only=False,aggregation='equal_section')
        positive_batch=module.reconstruct(source,positive_only=True,aggregation='equal_batch')
        positive_section=module.reconstruct(source,positive_only=True,aggregation='equal_section')
        self.assertEqual(row(recorded_batch)['value'],3)
        self.assertEqual(row(recorded_section)['value'],2.75)
        self.assertAlmostEqual(row(positive_batch)['value'],19/6)
        self.assertEqual(row(positive_section)['value'],3)
        self.assertEqual(row(recorded_batch)['section_counts_by_batch'],{'B8':2,'B9':1,'B10':1})
        self.assertTrue(row(recorded_batch)['complete_three_batch_coverage'])
        self.assertEqual(positive_batch['section_audits'][0]['groups'][1]['excluded_zero_count_rows'],[5])

    def test_denominator_uses_same_zero_policy_and_exact_control_rows(self):
        source={'B8S1':{(1,0):[spot(2,1,4),spot(3,0,0)],(2,0):[spot(4,1,8)]}}
        a=module.reconstruct(source,positive_only=False,aggregation='equal_batch')
        b=module.reconstruct(source,positive_only=True,aggregation='equal_batch')
        self.assertEqual(row(a)['value'],4)
        self.assertEqual(row(b)['value'],2)
        self.assertEqual(a['section_audits'][0]['control']['eligible_rows'],[2,3])
        self.assertEqual(b['section_audits'][0]['control']['eligible_rows'],[2])

    def test_all_zero_spots_recorded_vs_missing_are_explicit_not_biological_approval(self):
        source={'B8S1':{(1,0):[spot(2,1,4)],(2,0):[spot(3,0,0)]}}
        a=module.reconstruct(source,positive_only=False,aggregation='equal_batch')
        b=module.reconstruct(source,positive_only=True,aggregation='equal_batch')
        self.assertEqual(row(a)['value'],0)
        self.assertEqual(b['combinations'],[])
        self.assertEqual(b['section_audits'][0]['groups'][1]['unavailable_reason'],'no_eligible_spots')
        self.assertFalse(row(a)['complete_three_batch_coverage'])

    def test_zero_control_never_becomes_zero_imputation_or_infinity(self):
        source={'B8S1':{(1,0):[spot(2,0,0)],(2,0):[spot(3,1,8)]}}
        for positive in (False,True):
            result=module.reconstruct(source,positive_only=positive,aggregation='equal_batch')
            self.assertFalse(result['section_audits'][0]['control']['usable_positive_mean'])
            self.assertEqual(result['combinations'],[])
            self.assertIsNone(result['section_audits'][0]['groups'][1]['normalized_red_proxy'])
            json.dumps(result,allow_nan=False)

    def test_records_are_not_weighted_by_cell_count_or_divided_by_count(self):
        source={'B8S1':{(1,0):[spot(2,1,1)],(2,0):[spot(3,1,2),spot(4,100,4)]}}
        result=module.reconstruct(source,positive_only=True,aggregation='equal_batch')
        self.assertEqual(row(result)['value'],3)
        self.assertEqual(row(result)['section_values'][0]['raw_rows'],[3,4])

    def test_material_order_does_not_pair_values_by_position(self):
        source={'B8S1':{(3,0):[spot(4,1,12)],(1,0):[spot(2,1,4)],(2,0):[spot(3,1,8)]}}
        result=module.reconstruct(source,positive_only=False,aggregation='equal_batch')
        self.assertEqual(row(result,(2,0))['value'],2)
        self.assertEqual(row(result,(3,0))['value'],3)
        with self.assertRaises(ResearchError):module.reconstruct({'B8S1':{(2,0):[spot(3,1,8)]}},positive_only=False,aggregation='equal_batch')

    def test_midranks_and_ties_at_top10_are_retained(self):
        self.assertEqual(module._ranks([1,1,3,4]),[1.5,1.5,3,4])
        def policy(values):return {'combinations':[{'topography':i+2,'chemistry':0,'value':v,'complete_three_batch_coverage':True} for i,v in enumerate(values)]}
        a=[12,11,10,9,8,7,6,5,4,1,1,1]
        b=[1]*12
        result=module.compare_policies({'a':policy(a),'b':policy(b)})
        self.assertEqual(len(result['highest10_keys_including_exact_ties']['a']),12)
        self.assertEqual(result['pairs'][0]['highest10_left_including_exact_ties'],12)
        self.assertIsNone(result['pairs'][0]['spearman_midrank'])
        json.dumps(result,allow_nan=False)

    def test_compare_requires_common_batch_coverage_and_explicit_keys(self):
        a=[{'topography':t,'chemistry':0,'value':float(t),'complete_three_batch_coverage':True} for t in (2,3,4)]
        b=[{'topography':t,'chemistry':0,'value':float(5-t),'complete_three_batch_coverage':True} for t in (4,2,3)]
        b[0]['complete_three_batch_coverage']=False
        result=module.compare_policies({'a':{'combinations':a},'b':{'combinations':b}})
        self.assertEqual(result['common_three_batch_keys'],[[2,0],[3,0]])
        self.assertAlmostEqual(result['pairs'][0]['spearman_midrank'],-1)
        b[1]['complete_three_batch_coverage']=False
        with self.assertRaises(ResearchError):module.compare_policies({'a':{'combinations':a},'b':{'combinations':b}})

    def test_comparison_does_not_silently_overwrite_duplicate_keys_or_nonfinite_values(self):
        rows=[{'topography':2,'chemistry':0,'value':1,'complete_three_batch_coverage':True}]*2
        with self.assertRaises(ResearchError) as error:module.compare_policies({'a':{'combinations':rows},'b':{'combinations':rows}})
        self.assertEqual(error.exception.code,'DUPLICATE_KEY')
        for value in (float('inf'),float('nan')):
            with self.assertRaises(ResearchError):module.compare_policies({'a':{'combinations':[{'topography':2,'chemistry':0,'value':value}]},'b':{'combinations':[]}})
        with self.assertRaises(ResearchError):module.compare_policies({})

    def test_static_project_is_never_deserialized_or_executed(self):
        pipeline=b'CellProfiler Pipeline: example\\nNamesAndTypes:[enabled:True]\\n    Name to assign these images:OrigRed\\n'
        data=b'\x89HDF\r\n\x1a\n\x00'+pipeline+b'\x00'+pipeline+b'\x00'
        with patch('pickle.loads',side_effect=AssertionError('no deserialization')):
            evidence=module.static_pipeline(data)
        self.assertEqual(len(evidence['copies']),2)
        self.assertFalse(evidence['biological_ALP_channel_and_export_mapping_confirmed'])
        self.assertFalse(evidence['author_project_executed'])
        with self.assertRaises(ResearchError):module.static_pipeline(data+pipeline.replace(b'OrigRed',b'ALPRed'))
        with self.assertRaises(ResearchError):module.static_pipeline(b'invalid')


if __name__=='__main__':unittest.main()
