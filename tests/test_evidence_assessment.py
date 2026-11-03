import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from autoresearch import evidence_assessment as assessment
from autoresearch.contracts import ResearchError, fingerprint


def response(name, args):
    return {'message': {'tool_calls': [{'type': 'function', 'function': {'name': name, 'arguments': args}}]}}


class EvidenceAssessmentTests(unittest.TestCase):
    def test_native_read_assess_pause_replay_and_unread_citation_rejected(self):
        chunks = [{'id': 'c' + str(i), 'label': 'Page ' + str(i), 'source_id': 'paper',
                   'locator': {'kind': 'pdf_page', 'value': str(i)},
                   'text': 'Distinct source text ' + str(i), 'complete_document': False} for i in (1, 2)]
        packet = {'chunks': chunks, 'contributor': {'role': 'operator_assistant', 'label': 'Partial collection'},
                  'submission_claims': [{'claim': 'ALP mapping not established', 'status': 'unresolved'}],
                  'unresolved_questions': ['Which original export column?']}
        packet['snapshot_sha256'] = fingerprint(packet)

        def read(packet, ids):
            return [copy.deepcopy(next(c for c in packet['chunks'] if c['id'] == identifier)) for identifier in ids]

        fake = SimpleNamespace(__file__=__file__, build_returned_evidence=lambda *args: copy.deepcopy(packet),
                               validate_packet=lambda value: None, read_chunks=read)
        with tempfile.TemporaryDirectory() as temp, patch.object(assessment, 'packet_module', return_value=fake):
            root = Path(temp); loop = assessment.EvidenceAssessmentCloudLoop(root / 'study')
            first = loop.study.create(root / 'handoff', root / 'diagnostic', root / 'submission', '评议原始来源与四项缺口', 4)
            self.assertEqual(assessment.available_actions(first, True), {'pause', 'stop'})
            spec = {'reasoning_effort': 'high', 'context_tokens': 32768, 'max_output_tokens': 4096, 'max_request_bytes': 65536}
            body = loop._request(first, 4, [], spec)
            self.assertEqual(body['think'], 'high'); self.assertEqual(body['options']['num_predict'], 4096)
            request = loop._parse_decision(response('read_evidence', {'chunk_ids': ['c1'], 'reason': 'Read methods'}), first, 'read', body)
            saved = loop.study.apply(request)['action']
            self.assertEqual(saved['result']['chunks'], chunks[:1])
            state = loop.study.observe(); context = assessment.project_context(state, 3, [])
            self.assertEqual(context['read_chunks'], chunks[:1])
            self.assertNotIn('result', context['actions'][0])
            self.assertNotIn('Distinct source text 2', json.dumps(context))
            self.assertEqual(context['submission_claims_unverified'], packet['submission_claims'])
            self.assertEqual(context['host_binding']['origin'], 'host_bound_execution_metadata')
            answers = [{'question_id': q['id'], 'status': 'unresolved', 'evidence_ids': ['c1'],
                        'answer': 'This partial method description does not establish the exact mapping.'} for q in assessment.QUESTIONS]
            final_body = loop._request(state, 1, [], spec)
            self.assertEqual({t['function']['name'] for t in final_body['tools']}, {'record_assessment', 'pause', 'stop'})
            bad = copy.deepcopy(answers); bad[0]['evidence_ids'] = ['c2']
            with self.assertRaises(ResearchError):
                loop._parse_decision(response('record_assessment', {'answers': bad, 'reason': 'Unseen source'}), state, 'bad', final_body)
            request = loop._parse_decision(response('record_assessment', {'answers': answers, 'reason': 'Keep unresolved gaps'}), state, 'assessment', final_body)
            result = loop.study.apply(request)['action']['result']
            self.assertEqual(result['answers'], answers)
            self.assertFalse(result['scientific_validation']); self.assertFalse(result['task_complete'])
            self.assertEqual(result['answer_status_origin'], 'model_claim_not_scientific_approval')
            self.assertEqual(loop.study.observe()['status'], 'paused')
            self.assertTrue(loop.study.apply(request)['replayed'])
            self.assertEqual(len(loop.study.observe()['actions']), 2)
            wrong = copy.deepcopy(request); wrong['reason'] = 'changed'
            with self.assertRaises(ResearchError): loop.study.apply(wrong)


if __name__ == '__main__':
    unittest.main()
