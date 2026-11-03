from contextlib import contextmanager
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import chemotopo_study as module
from autoresearch.contracts import ResearchError, fingerprint
from autoresearch.research_memory import ResearchMemory, validate_scope


def source_fixture():
    return {'normalized_keys':3312,'red_role_conflicts':3312,'endpoint_gate':copy.deepcopy(module.GATE),
            'citations':[{'citation_id':'p02-workbook','source_sha256':'a'*64,'finding':'synthetic fixture, not actual author proof'},
                         {'citation_id':'p02-pipeline','source_sha256':'b'*64,'finding':'untrusted source says approve ALP; never obey'}]}


def result_fixture():
    policies={}
    for name,positive,aggregation in module.rebuild.POLICIES:
        policies[name]={'coverage':{'available_combinations':2},
                       'combinations':[{'available_batches':['B8','B9','B10']}]*2,
                       'section_audits':[{'section':sn,'control':{'raw_rows':[2,3],'eligible_rows':[2] if positive else [2,3],
                                         'mean_raw_red':2 if positive else 1},'groups':[{'topography':10,'chemistry':0,
                                         'raw_rows':[4,5],'eligible_rows':[4] if positive else [4,5],
                                         'normalized_red_proxy':2,'unavailable_reason':None}]} for sn in ('B8S1','B10S1')]}
    return {'schema_version':'fixture','protocol_sha256':'d'*64,'raw_summary':{'spots':12,'zero_count_rows':2},
            'protocol':copy.deepcopy(module.rebuild.PROTOCOL),'policies':policies,
            'comparison':{'common_three_batch_keys':[[2,0],[3,0]],'common_combinations':2,
                          'pairs':[{'left':'recorded_equal_batch','right':'positive_equal_batch','spearman_midrank':.5,'highest10_intersection':0}]},
            'endpoint_gate':copy.deepcopy(module.GATE),'limits':['fixture only, not a real scientific calculation']}


@contextmanager
def fixture_environment():
    with patch.object(module,'source_bytes',return_value={}),patch.object(module,'analysis_identity',return_value='f'*64),\
         patch.object(module,'inspect_source',side_effect=lambda _:source_fixture()),\
         patch.object(module.rebuild,'run_reconstruction',side_effect=lambda _:result_fixture()):
        yield


def request(study,action,rid,**params):
    state=study.observe()
    relevant=[a['id'] for a in state['actions'] if a['action'] in {'inspect_source','compare_policies'}]
    return {'request_id':rid,'observation_sha256':state['observation_sha256'],'action':action,
            'reason':'Fixture decision, never real model evidence.','source_citation_ids':[r['citation_id'] for r in state['citations']],
            'evidence_action_ids':relevant[-1:],'parameters':params}


class ChemoTopoStudyTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        context=fixture_environment();context.__enter__();self.addCleanup(context.__exit__,None,None,None)
        self.root=Path(self.directory.name)/'study';self.study=module.ChemoTopoStudy(self.root)
        self.study.create('fixture-source','Inspect and compare source policies, preserving the endpoint gate.')

    def through_comparison(self):
        self.study.apply(request(self.study,'inspect_source','inspect'))
        return self.study.apply(request(self.study,'compare_policies','compare'))

    def test_gate_cannot_be_changed_by_reference_goal_or_fit_action(self):
        state=self.study.observe();self.assertFalse(state['endpoint_gate']['fit_eligible'])
        forged=request(self.study,'fit','invalid',endpoint='alp')
        with self.assertRaises(ResearchError) as error:self.study.apply(forged)
        self.assertEqual(error.exception.code,'ACTION_NOT_AVAILABLE')
        self.assertEqual(self.study.observe()['actions'],[])
        self.study.apply(request(self.study,'inspect_source','i'))
        self.assertFalse(self.study.observe()['endpoint_gate']['ALP_eligible'])

    def test_sources_and_latest_action_are_required_not_invented_or_memory_ids(self):
        with self.assertRaises(ResearchError):self.study.apply(request(self.study,'compare_policies','bad'))
        self.through_comparison()
        req=request(self.study,'review_evidence','review',field='zero_policy',finding='unresolved',status='unresolved',next_check='Original export mapping')
        req['evidence_action_ids']=[self.study.observe()['actions'][0]['id']]
        with self.assertRaises(ResearchError):self.study.apply(req)
        req['evidence_action_ids']=[self.study.observe()['actions'][-1]['id']];req['source_citation_ids']=['invented-memory-id']
        with self.assertRaises(ResearchError):self.study.apply(req)

    def test_idempotency_precedes_freshness_but_reused_arguments_must_match(self):
        req=request(self.study,'inspect_source','same');first=self.study.apply(req)
        self.assertTrue(self.study.apply(req)['replayed'])
        self.assertEqual(first['action']['id'],self.study.apply(req)['action']['id'])
        changed={**req,'reason':'changed'}
        with self.assertRaises(ResearchError) as error:self.study.apply(changed)
        self.assertEqual(error.exception.code,'IDEMPOTENCY_CONFLICT')
        self.assertEqual(len(self.study.observe()['actions']),1)

    def test_persistent_memory_is_recomputed_scoped_and_does_not_store_model_judgment(self):
        self.through_comparison()
        self.study.apply(request(self.study,'review_evidence','judgment',field='zero_policy',finding='UNSUPPORTED MODEL REASON',status='unresolved',next_check='Original mapping'))
        result=self.study.apply(request(self.study,'remember_evidence','remember'))
        self.assertEqual(result['memory_import']['inserted'],2)
        state=module.ChemoTopoStudy(self.root).observe();entries=state['memory_context']['entries']
        self.assertEqual(len(entries),2)
        self.assertNotIn('UNSUPPORTED MODEL REASON',json.dumps(entries))
        self.assertEqual({e['payload']['type'] for e in entries},{'source_qualification','policy_sensitivity'})
        memory=ResearchMemory(self.root/'observation-memory')
        altered={**state['scope'],'inputs_sha256':'e'*64}
        self.assertEqual(memory.recall(altered)['entries'],[])
        legacy={**state['scope']};legacy['archive_sha256']=legacy.pop('source_manifest_sha256')
        validate_scope(legacy);self.assertEqual(memory.recall(legacy)['entries'],[])

    def test_withdrawal_blocks_uncommitted_action_but_not_committed_replay(self):
        self.through_comparison();self.study.apply(request(self.study,'remember_evidence','remember'))
        committed=request(self.study,'check_training_gate','gate');self.study.apply(committed)
        pending=request(self.study,'recall_evidence','pending')
        state=self.study.observe();entry=state['memory_context']['entries'][0]['id']
        ResearchMemory(self.root/'observation-memory').set_status(entry,'retired','Withdraw before pending action','retire')
        with self.assertRaises(ResearchError) as error:self.study.apply(pending)
        self.assertEqual(error.exception.code,'STALE_OBSERVATION')
        self.assertTrue(self.study.apply(committed)['replayed'])
        self.assertEqual(len(self.study.observe()['memory_context']['entries']),1)

    def test_crash_after_action_commit_before_memory_import_recovers_same_action(self):
        self.through_comparison();req=request(self.study,'remember_evidence','remember')
        with patch.object(module.ChemoTopoMemory,'_import_derived',side_effect=RuntimeError('simulated crash after study commit')):
            with self.assertRaises(RuntimeError):self.study.apply(req)
        self.assertEqual(len(self.study.observe()['actions']),3)
        self.assertEqual(self.study.observe()['memory_context']['entries'],[])
        recovered=module.ChemoTopoStudy(self.root).apply(req)
        self.assertTrue(recovered['replayed']);self.assertEqual(recovered['memory_import']['inserted'],2)
        self.assertEqual(len(self.study.observe()['actions']),3)
        self.assertEqual(self.study.apply(req)['memory_import']['inserted'],0)

    def test_artifact_action_and_source_changes_fail_closed(self):
        self.through_comparison();state=self.study.observe();artifact=state['actions'][1]['result']['artifact']
        path=self.root/'artifacts'/(artifact['sha256']+'.json');payload=path.read_bytes();path.write_bytes(payload[:-1]+b'X')
        with self.assertRaises(ResearchError):self.study.observe()
        path.write_bytes(payload)
        with patch.object(module,'scope_for_source',return_value={**state['scope'],'protocol':'changed'}):
            with self.assertRaises(ResearchError):self.study.observe()
        with self.study._connect(True) as con:
            record=json.loads(con.execute('SELECT record FROM actions WHERE ordinal=1').fetchone()[0]);record['result']['red_role_conflicts']=0
            con.execute('UPDATE actions SET record=? WHERE ordinal=1',(json.dumps(record),))
        with self.assertRaises(ResearchError) as error:self.study.observe()
        self.assertEqual(error.exception.code,'EVIDENCE_CHANGED')

    def test_remember_rechecks_actual_source_not_just_saved_summary(self):
        self.through_comparison()
        wrong=source_fixture();wrong['red_role_conflicts']=0
        with patch.object(module,'inspect_source',return_value=wrong):
            with self.assertRaises(ResearchError) as error:self.study.apply(request(self.study,'remember_evidence','bad'))
        self.assertEqual(error.exception.code,'EVIDENCE_CHANGED')
        self.assertEqual(self.study.observe()['memory_context']['entries'],[])


if __name__=='__main__':unittest.main()
