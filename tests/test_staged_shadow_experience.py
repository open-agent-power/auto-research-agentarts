"""Synthetic tests for S069 work-in-progress comparison arithmetic."""
import copy
import unittest
from unittest.mock import patch
from autoresearch.contracts import fingerprint
from autoresearch.research_memory import observation_id
from autoresearch import staged_project_experience as experience
from autoresearch.contracts import ResearchError


class ShadowComparisonTests(unittest.TestCase):
    def feedback(self,value,outcome):
        return {'condition':copy.deepcopy(experience._SHADOW_A_CONDITION),'value':value,'outcome':outcome}

    def value(self,recall,mrr,minimum,maximum):
        return {'means':[recall,mrr],'leave_one_out':{'minimum':minimum,'maximum':maximum,'queries':200}}

    def final(self,baseline_mrr=.8,selected_mrr=.7,baseline_recall=.9,selected_recall=.9):
        return {'selected_method':'tfidf_cosine','baseline_method':'bm25',
                'comparison_status':'distinct_selected_and_baseline',
                'summary':{'baseline':{'recall@5':.5,'recall@10':.8,'recall@20':baseline_recall,
                                       'mrr@10':baseline_mrr,'ndcg@10':.6},
                           'selected':{'recall@5':.5,'recall@10':.8,'recall@20':selected_recall,
                                       'mrr@10':selected_mrr,'ndcg@10':.6}}}

    def test_same_arm_preserves_unknown_and_zero(self):
        value=self.value(0.0,-.02,-.01,.01)
        result=experience._shadow_comparison(self.feedback(0.0,'condition_not_met'),experience._SHADOW_B_CONDITION,value,self.final())
        self.assertEqual(result,{'A_method':'bm25','B_method':'bm25','outcome':'unknown','reason':'same_arm','B_minus_A':None})

    def test_distinct_arms_strict_target_and_unmeasured(self):
        value=self.value(.1,-.02,0,.2);fb=self.feedback(.1,'condition_met')
        result=experience._shadow_comparison(fb,experience._SHADOW_B_CONDITION,value,self.final())
        self.assertEqual((result['A_method'],result['B_method'],result['outcome']),('tfidf_cosine','bm25','condition_met'))
        self.assertEqual(result['B_minus_A']['recall@20'],0)
        result=experience._shadow_comparison(fb,experience._SHADOW_B_CONDITION,value,self.final(selected_mrr=.8))
        self.assertEqual(result['outcome'],'condition_not_met')
        result=experience._shadow_comparison(fb,experience._SHADOW_B_CONDITION,value,None)
        self.assertEqual((result['outcome'],result['reason'],result['B_minus_A']),('unknown','final_unmeasured',None))

    def test_missing_unknown_does_not_short_circuit_to_false(self):
        result=experience._shadow_comparison(self.feedback(0,'condition_not_met'),experience._SHADOW_B_CONDITION,None,None)
        self.assertEqual((result['outcome'],result['reason']),('unknown','policy_unknown'))
        result=experience._shadow_comparison(self.feedback(None,'unknown'),experience._SHADOW_B_CONDITION,self.value(0,0,0,0),None)
        self.assertEqual(result['outcome'],'unknown')

    def test_wrong_rule_bool_nan_and_mismatched_values_rejected(self):
        value=self.value(.1,-.02,0,.2);fb=self.feedback(.1,'condition_met')
        bad=copy.deepcopy(experience._SHADOW_B_CONDITION);bad['all'][0]['threshold']=False
        with self.assertRaises(ResearchError):experience._shadow_comparison(fb,bad,value,None)
        for x in (True,float('nan')):
            invalid=copy.deepcopy(fb);invalid['value']=x
            with self.assertRaises(ResearchError):experience._shadow_comparison(invalid,experience._SHADOW_B_CONDITION,value,None)
        invalid=copy.deepcopy(value);invalid['means'][0]=.2
        with self.assertRaises(ResearchError):experience._shadow_comparison(fb,experience._SHADOW_B_CONDITION,invalid,None)

    def test_unmeasured_or_damaged_final_is_not_treated_as_two_arms(self):
        value=self.value(.1,-.02,0,.2);fb=self.feedback(.1,'condition_met')
        bad=self.final();bad['selected_method']='bm25'
        with self.assertRaises(ResearchError):experience._shadow_comparison(fb,experience._SHADOW_B_CONDITION,value,bad)
        bad=self.final();bad['summary']['baseline']['mrr@10']=True
        with self.assertRaises(ResearchError):experience._shadow_comparison(fb,experience._SHADOW_B_CONDITION,value,bad)


class ShadowOfflineProjectionTests(unittest.TestCase):
    """A fabricated v2 subset isolates the v3 checks, not source authentication."""
    def fixture(self):
        qids=['q-%03d'%i for i in range(200)];zero={k:0.0 for k in ('recall@5','recall@10','recall@20','mrr@10','ndcg@10')}
        rows=[{'split':'validation','query_id':qid,'method':method,'metrics':dict(zero)}
              for qid in qids for method in ('bm25','tfidf_cosine')]
        primary={'id':experience._S067_PRIMARY_ID,'result_sha256':'c'*64}
        parent={'primary':{'state_version_after':9},'audit':{'state_version_before':10,'request_id':'audit','context_sha256':'a'*64}}
        origin={'project_id':experience._S067_PROJECT_ID,'run_id':experience._S067_RUN_ID,
                'source_snapshot_sha256':experience._S067_SOURCE_SNAPSHOT}
        fb={'condition':copy.deepcopy(experience._SHADOW_A_CONDITION),'outcome':'condition_not_met','value':0.0}
        paired={k:{'mean':0.0,'wins':0,'losses':0,'ties':200} for k in ('recall@20','mrr@10')}
        base={'scope':{'source_manifest_sha256':'b'*64,'inputs_sha256':'d'*64,'analysis_code_sha256':'e'*64,
                       'protocol':experience.PROTOCOL_V2},
              'payload':{'paired_summary':{'splits':{'validation':{'paired_candidate_minus_baseline':paired}}},'final':None},
              'provenance':{'action_id':primary['id'],'actions':{'primary':primary},'parent_bindings':parent,'origin':origin,
                            'source':{'spec':{'query_splits':{'validation':qids}}},
                            'artifacts':{'primary':{'tool_result':{}}},'feedback_history':{'feedback':fb}}}
        projected_rows=[{'query_id':qid,'bm25':{'recall@20':0.0,'mrr@10':0.0},
                         'tfidf_cosine':{'recall@20':0.0,'mrr@10':0.0}} for qid in qids]
        inputs={'schema_version':'s067-shadow-validation-inputs-v1','rows':projected_rows,
                'case_sha256':experience._S067_CASE_SHA,'primary_action_id':primary['id'],
                'primary_result_sha256':primary['result_sha256']}
        value={'means':[0.0,0.0],'leave_one_out':{'minimum':0.0,'maximum':0.0,'queries':200}}
        shadow={'schema_version':'staged-shadow-comparison-v1','case_sha256':experience._S067_CASE_SHA,
                'source_commit':experience._S067_COMMIT,'protocol_sha256':experience._S067_PROTOCOL_SHA,
                'driver_sha256':experience._S067_DRIVER_SHA,'decision_sha256':experience._S067_DECISION_SHA,
                'validation_inputs_sha256':fingerprint(inputs),'start_sha256':'f'*64,'claim_sha256':'1'*64,
                'anchor_request_id':'s067-shadow-anchor','anchor_based_on_state_version':9,
                'anchor_content_trust':'unverified_researcher_statement','audit_parent_request_id':'audit',
                'audit_context_sha256':'a'*64,'condition':copy.deepcopy(experience._SHADOW_B_CONDITION),'value':value,
                'comparison':experience._shadow_comparison(fb,experience._SHADOW_B_CONDITION,value,None),
                'verification':experience._SHADOW_VERIFICATION}
        scope=dict(base['scope']);scope['protocol']=experience.PROTOCOL_V3
        scope['inputs_sha256']=fingerprint({'base_inputs_sha256':base['scope']['inputs_sha256'],
                                            'shadow_decision_sha256':shadow['decision_sha256']})
        record={'schema_version':'conditional-research-memory-v1','kind':'diagnostic_observation',
                'scope':scope,'provenance':{'action_id':primary['id']}}
        record['id']=observation_id(record)
        return base,shadow,record,{'per_query_metrics':rows}

    def check(self,base,shadow,record,saved):
        with patch.object(experience,'_base_from_shadow_record',return_value=(base,shadow)), \
             patch.object(experience.staged,'_saved',return_value=saved):
            return experience._validate_shadow_record(record)

    def test_fabricated_shadow_checks_full_coverage_and_zero(self):
        base,shadow,record,saved=self.fixture();self.assertEqual(self.check(base,shadow,record,saved),record)
        self.assertEqual(shadow['comparison']['outcome'],'unknown')

    def test_resealed_wrong_source_anchor_input_and_value_rejected(self):
        for key,bad in (('case_sha256','2'*64),('decision_sha256','3'*64),
                        ('validation_inputs_sha256','4'*64),('anchor_based_on_state_version',8)):
            with self.subTest(key=key):
                base,shadow,record,saved=self.fixture();shadow[key]=bad
                if key=='decision_sha256':
                    record['scope']['inputs_sha256']=fingerprint({'base_inputs_sha256':base['scope']['inputs_sha256'],
                                                                  'shadow_decision_sha256':bad});record['id']=observation_id(record)
                with self.assertRaises(ResearchError):self.check(base,shadow,record,saved)
        base,shadow,record,saved=self.fixture();shadow['value']['means'][0]=False
        with self.assertRaises(ResearchError):self.check(base,shadow,record,saved)

    def test_missing_validation_row_rejected(self):
        base,shadow,record,saved=self.fixture();saved['per_query_metrics'].pop()
        with self.assertRaises(ResearchError):self.check(base,shadow,record,saved)


if __name__=='__main__':unittest.main()
