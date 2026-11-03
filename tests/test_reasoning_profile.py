import copy
import json
import socket
import unittest

from autoresearch import ollama_cloud
from autoresearch.contracts import ResearchError, fingerprint
from autoresearch.reasoning_profile import OwnedHighReasoningOllama, REASONING, MAX_OUTPUT_TOKENS
import test_ollama_cloud as fixture_tools
from test_ollama_cloud import FakeOpener, ACCOUNT, BODY


class ReasoningProfileTests(unittest.TestCase):
    def test_high_exact_send_medium_rejected_unknown_not_retried_and_free_guard_inherited(self):
        fixture=fixture_tools.OllamaCloudTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        def make(**kwargs):
            fixture.counter+=1
            with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
            server=OwnedHighReasoningOllama(fixture.exe,fixture.root/f'high-cache-{fixture.counter}',
                                           fixture.root/f'high-output-{fixture.counter}',port=port,model_store=fixture.store)
            server.opener=FakeOpener(**kwargs);return server
        self.assertIs(OwnedHighReasoningOllama.prepare,ollama_cloud.OwnedCloudOllama.prepare)
        self.assertIs(OwnedHighReasoningOllama._check_account,ollama_cloud.OwnedCloudOllama._check_account)
        request=copy.deepcopy(BODY);request['think']=REASONING;request['options']['num_predict']=MAX_OUTPUT_TOKENS
        original=copy.deepcopy(request);server=make()
        with server:
            identity=server.acquire();self.assertEqual(server.acquire(),identity)
            self.assertIn('high',server.reasoning_capabilities['thinking']['values'])
            self.assertEqual(sum(path=='/api/show' for path,_,_ in server.opener.requests),1)
            server.configure_budget(identity,2)
            medium=copy.deepcopy(request);medium['think']='medium'
            with self.assertRaises(ResearchError) as error:server.http.request('/api/chat',medium)
            self.assertEqual(error.exception.code,'INVALID_REQUEST');self.assertEqual(server.opener.chat_count,0)
            server.http.request('/api/chat',request)
            self.assertEqual(request,original)
            sent=[body for path,body,_ in server.opener.requests if path=='/api/chat'][0]
            self.assertEqual(sent,original)
            receipt=json.loads((server.output/'cloud-001-sending.json').read_text(encoding='utf-8'))
            self.assertEqual(receipt['request'],original);self.assertEqual(receipt['request_sha256'],fingerprint(original))
            server.opener.chat_error=OSError('unknown send fixture')
            with self.assertRaises(ResearchError) as unknown:server.http.request('/api/chat',request)
            self.assertEqual(unknown.exception.code,'CLOUD_REQUEST_UNKNOWN')
            self.assertEqual(server._used,2)
            with self.assertRaises(ResearchError) as retry:server.http.request('/api/chat',request)
            self.assertEqual(retry.exception.code,'NEEDS_REVIEW');self.assertEqual(server.opener.chat_count,2)
        self.assertTrue(server.stopped);self.assertTrue(server.key_metadata_unchanged)
        low=make(states=[{**ACCOUNT,'balance':1.05}])
        with low:
            identity=low.acquire();low.configure_budget(identity,1)
            with self.assertRaises(ResearchError) as quota:low.http.request('/api/chat',request)
            self.assertEqual(quota.exception.code,'FREE_QUOTA_REQUIRED');self.assertEqual(low.opener.chat_count,0)
        self.assertEqual(ollama_cloud.THINKING,'medium')


if __name__=='__main__':unittest.main()
