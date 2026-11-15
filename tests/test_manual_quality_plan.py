"""Direct delegated quality plan: synthetic only, no model, fit or dispatch."""
import base64, copy, hashlib, json, unittest
from pathlib import Path
from unittest.mock import patch
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject
import test_quality_plan_workbench as fixtures

class ManualQualityPlanTests(unittest.TestCase):
    def stage(self):
        helper=fixtures.QualityPlanWorkbenchTests('runTest'); f,m,_=helper.stage(); self.addCleanup(helper.doCleanups)
        s=f.project.status(); reg=s['tabular_quality_registrations'][0]
        selector={'kind':'tabular_quality_feedback','registration_request_id':'reg','registration_sha256':reg['registration_sha256']}
        body={'request_id':'local-manual-plan-synthetic','project_id':s['id'],'expected_state_version':s['state_version'],
              'expected_snapshot_ref':s['snapshot_ref'],'decision_limit':2,'cli_budget_usd':0.1,'reason':'Synthetic manual review','saved_materials':[selector]}
        args={'plan':{'question':'Synthetic','basis':'Quality observation','steps':'Inspect','expected_feedback':'Preserve uncertainty'},
              'reason':'Synthetic','expected_improvement':'Review','feedback_action_ids':[s['actions'][0]['id']]}
        raw=canonical(args).encode(); imp={'request_id':body['request_id'],'project_id':s['id'],'response_base64':base64.b64encode(raw).decode()}
        return f,m,body,imp,raw

    def test_complete_and_original_response_replay(self):
        f,m,body,imp,raw=self.stage();before=copy.deepcopy(f.project.status()['budget'])
        with patch.object(ResearchProject,'step',side_effect=AssertionError('step')),patch.object(ProjectController,'_dispatch',side_effect=AssertionError('dispatch')),patch('autoresearch.host_model_selection.run_claude_selection',side_effect=AssertionError('model')):
            prepared=m.prepare_manual_quality_plan(body); self.assertEqual(prepared['status'],'prepared')
            self.assertEqual(prepared['model_record']['manual_plan_intent']['schema_version'],'host-manual-quality-plan-intent-v1')
            self.assertEqual(prepared['model_record']['prepare_specification']['saved_materials'],body['saved_materials'])
            result=m.import_manual_quality_plan(imp); replay=m.import_manual_quality_plan(imp)
        self.assertEqual((result['status'],replay['status']),('proposed','proposed'))
        self.assertFalse(result['model_record']['execution_declaration']['execution_verified'])
        self.assertEqual(result['model_record']['execution_declaration']['cost'],'unknown')
        self.assertEqual(f.project.status()['budget'],before)
        with self.assertRaises(ResearchError) as e: m.import_manual_quality_plan({**imp,'response_base64':base64.b64encode(raw+b' ').decode()})
        self.assertEqual(e.exception.code,'IDEMPOTENCY_CONFLICT')

    def test_orphans_and_missing_input_stop_without_adoption(self):
        for mode in ('prepared_response','prepared_proposal','received_proposal','missing_context'):
            with self.subTest(mode=mode):
                f,m,body,imp,raw=self.stage(); result=m.prepare_manual_quality_plan(body);host=HostModelSelection(f.project.root);rec=result['model_record'];folder=host.directory/rec['directory']
                if mode=='prepared_response': (folder/'delegated.bin').write_bytes(raw)
                elif mode=='prepared_proposal': (folder/'proposal.json').write_text('{}')
                elif mode=='missing_context': (folder/'context.json').unlink()
                else:
                    source=f.root/'answer.bin';source.write_bytes(raw);host.import_response(request_id=body['request_id'],response_file=source,strict_manual_plan=True)
                    (folder/'proposal.json').write_text('{}')
                before=f.project.db.read_bytes()
                with self.assertRaises(ResearchError) as e: m.import_manual_quality_plan(imp)
                self.assertEqual(e.exception.code,'EVIDENCE_CHANGED' if mode=='missing_context' else 'OPERATION_INCOMPLETE')
                self.assertEqual(before,f.project.db.read_bytes());self.assertNotEqual(host.status(request_id=body['request_id'])['status'],'proposed')
                if mode=='missing_context': self.assertFalse((folder/'context.json').exists())

    def test_old_no_marker_and_fresh_collision_are_refused(self):
        f,m,body,imp,_=self.stage(); host=HostModelSelection(f.project.root)
        spec={k:body[k] for k in ('request_id','expected_state_version','decision_limit','cli_budget_usd','reason','saved_materials')}
        host.prepare(provider='delegated',purpose='plan',**spec)
        before=host.state_file.read_bytes()
        with self.assertRaises(ResearchError):m.import_manual_quality_plan(imp)
        self.assertEqual(before,host.state_file.read_bytes())
        with self.assertRaises(ResearchError) as e:m.prepare_manual_quality_plan(body)
        self.assertEqual(e.exception.code,'IDEMPOTENCY_CONFLICT');self.assertEqual(before,host.state_file.read_bytes())

    def test_marked_pending_blocks_new_id_and_bad_selector_does_not_write(self):
        f,m,body,_,_=self.stage(); host=HostModelSelection(f.project.root)
        with self.assertRaises(ResearchError):m.prepare_manual_quality_plan({**body,'saved_materials':[]})
        self.assertFalse(host.state_file.exists())
        with self.assertRaises(ResearchError):host.prepare(request_id='unmarked',provider='delegated',purpose='plan',expected_state_version=body['expected_state_version'],decision_limit=2,cli_budget_usd=.1,reason='Synthetic',saved_materials=body['saved_materials'],require_new=True)
        self.assertFalse(host.state_file.exists());m.prepare_manual_quality_plan(body); before=host.state_file.read_bytes()
        with self.assertRaises(ResearchError) as e:m.prepare_manual_quality_plan({**body,'request_id':'local-manual-plan-other'})
        self.assertEqual(e.exception.code,'OPERATION_INCOMPLETE');self.assertEqual(before,host.state_file.read_bytes())

    def test_marked_pending_blocks_other_host_entry_until_rejected(self):
        f,m,body,imp,raw=self.stage(); m.prepare_manual_quality_plan(body); host=HostModelSelection(f.project.root)
        spec={k:body[k] for k in ('expected_state_version','decision_limit','cli_budget_usd','reason','saved_materials')}
        for phase in ('prepared','proposed'):
            if phase == 'proposed': self.assertEqual(m.import_manual_quality_plan(imp)['status'],'proposed')
            before=host.state_file.read_bytes()
            with self.assertRaises(ResearchError) as e:
                host.prepare(request_id='other-host',provider='delegated',purpose='plan',**spec)
            self.assertEqual(e.exception.code,'OPERATION_INCOMPLETE');self.assertEqual(before,host.state_file.read_bytes())
        host.reject_plan(request_id=body['request_id'],reason='Synthetic explicit rejection')
        self.assertEqual(host.prepare(request_id='other-host',provider='delegated',purpose='plan',**spec)['status'],'prepared')

    def test_manual_plan_cannot_use_legacy_adoption_or_reject_missing_original(self):
        f,m,body,imp,_=self.stage();m.prepare_manual_quality_plan(body);m.import_manual_quality_plan(imp)
        host=HostModelSelection(f.project.root);before=f.project.db.read_bytes()
        for method,kwargs in ((host.adopt_plan,{}),(host.adopt_quality_plan,{'registration_request_id':'reg'})):
            with self.assertRaises(ResearchError) as error:method(request_id=body['request_id'],**kwargs)
            self.assertEqual(error.exception.code,'OPERATION_INCOMPLETE')
        record=host.status(request_id=body['request_id']);(host.directory/record['directory']/'proposal.json').unlink()
        with self.assertRaises(ResearchError) as error:host.reject_plan(request_id=body['request_id'],reason='Synthetic')
        self.assertEqual(error.exception.code,'EVIDENCE_CHANGED')
        with self.assertRaises(ResearchError) as error:host.adopt_supplied_quality_plan(request_id=body['request_id'],registration_request_id='reg')
        self.assertEqual(error.exception.code,'EVIDENCE_CHANGED');self.assertEqual(before,f.project.db.read_bytes())

    def test_resealed_forged_provider_label_is_rejected(self):
        f,m,body,imp,_=self.stage();m.prepare_manual_quality_plan(body);m.import_manual_quality_plan(imp)
        host=HostModelSelection(f.project.root);state=json.loads(host.state_file.read_text());record=state['requests'][body['request_id']]
        record['proposal']['provider']['label']='Invented verified model'; folder=host.directory/record['directory']
        (folder/'proposal.json').write_text(canonical(record['proposal']));host.state_file.write_text(canonical(state))
        with self.assertRaises(ResearchError) as error:host.reject_plan(request_id=body['request_id'],reason='Synthetic')
        self.assertEqual(error.exception.code,'EVIDENCE_CHANGED')

    def test_applied_replay_checks_original_marker_after_project_changes(self):
        for change in ('none','removed','resealed'):
            with self.subTest(change=change):
                f,m,body,imp,_=self.stage();m.prepare_manual_quality_plan(body);m.import_manual_quality_plan(imp)
                adoption={'request_id':'manual-adopt','project_id':body['project_id'],'expected_state_version':body['expected_state_version'],
                          'host_request_id':body['request_id'],'registration_request_id':'reg'}
                m.model_supplied_quality_plan_adopt(adoption)
                state=f.project.status()
                f.project.save_plan(request_id='later-plan',expected_state_version=state['state_version'],
                    plan={'question':'Later','basis':'Synthetic','steps':'Inspect','expected_feedback':'Review'},reason='Later synthetic plan')
                host=HostModelSelection(f.project.root)
                if change != 'none':
                    ledger=json.loads(host.state_file.read_text());record=ledger['requests'][body['request_id']]
                    if change == 'removed': record.pop('manual_plan_intent')
                    else:
                        marker=record['manual_plan_intent'];marker['nonce']='0'*64
                        marker['intent_sha256']=fingerprint({k:v for k,v in marker.items() if k!='intent_sha256'})
                    host.state_file.write_text(canonical(ledger))
                if change == 'none': self.assertTrue(m.resume_supplied_quality_plan_adopt(adoption)['replayed'])
                else:
                    before=f.project.db.read_bytes()
                    with self.assertRaises(ResearchError) as error:m.resume_supplied_quality_plan_adopt(adoption)
                    self.assertEqual(error.exception.code,'EVIDENCE_CHANGED');self.assertEqual(before,f.project.db.read_bytes())

    def test_rejected_replay_checks_original_marker(self):
        f,m,body,imp,_=self.stage();m.prepare_manual_quality_plan(body);m.import_manual_quality_plan(imp)
        host=HostModelSelection(f.project.root);host.reject_plan(request_id=body['request_id'],reason='Synthetic')
        ledger=json.loads(host.state_file.read_text());ledger['requests'][body['request_id']].pop('manual_plan_intent');host.state_file.write_text(canonical(ledger))
        with self.assertRaises(ResearchError) as error:host.reject_plan(request_id=body['request_id'],reason='Synthetic')
        self.assertEqual(error.exception.code,'EVIDENCE_CHANGED')

    def test_manual_version_and_marker_single_field_drift_blocks_all_host_entries(self):
        for kind in ('marker_removed', 'mode_removed', 'mode_changed', 'marker_changed'):
            with self.subTest(kind=kind):
                f,m,body,_,raw=self.stage();m.prepare_manual_quality_plan(body)
                host=HostModelSelection(f.project.root);ledger=json.loads(host.state_file.read_text());record=ledger['requests'][body['request_id']]
                if kind=='marker_removed': record.pop('manual_plan_intent')
                elif kind=='mode_removed': record['prepare_specification'].pop('manual_plan_mode')
                elif kind=='mode_changed': record['prepare_specification']['manual_plan_mode']='other'
                else: record['manual_plan_intent']['intent_sha256']='0'*64
                host.state_file.write_text(canonical(ledger));source=f.root/'manual-answer.bin';source.write_bytes(raw)
                before=(host.state_file.read_bytes(),f.project.db.read_bytes(),m.db.read_bytes())
                common={'request_id':body['request_id']}
                actions=(lambda:host.import_response(**common,response_file=source),lambda:host.consume(**common),
                         lambda:host.adopt_plan(**common),lambda:host.adopt_quality_plan(**common,registration_request_id='reg'),
                         lambda:host.reject_plan(**common,reason='Synthetic'),
                         lambda:host.prepare(request_id='other-host',provider='delegated',purpose='plan',
                             expected_state_version=body['expected_state_version'],decision_limit=body['decision_limit'],
                             cli_budget_usd=body['cli_budget_usd'],reason=body['reason'],saved_materials=body['saved_materials']))
                for action in actions:
                    with self.assertRaises(ResearchError) as error:action()
                    self.assertEqual(error.exception.code,'EVIDENCE_CHANGED')
                self.assertEqual(before,(host.state_file.read_bytes(),f.project.db.read_bytes(),m.db.read_bytes()))

    def test_legacy_unmarked_host_plan_import_consume_and_adopt_still_work(self):
        f,_,body,_,raw=self.stage();host=HostModelSelection(f.project.root)
        host.prepare(request_id='legacy-host',provider='delegated',purpose='plan',expected_state_version=body['expected_state_version'],
                     decision_limit=body['decision_limit'],cli_budget_usd=body['cli_budget_usd'],reason=body['reason'],saved_materials=body['saved_materials'])
        record=host.status(request_id='legacy-host');self.assertNotIn('manual_plan_mode',record['prepare_specification']);self.assertNotIn('manual_plan_intent',record)
        source=f.root/'legacy-answer.bin';source.write_bytes(raw)
        self.assertEqual(host.import_response(request_id='legacy-host',response_file=source)['status'],'received')
        self.assertEqual(host.consume(request_id='legacy-host')['status'],'proposed')
        self.assertEqual(host.adopt_plan(request_id='legacy-host')['status'],'applied')

if __name__=='__main__': unittest.main()
