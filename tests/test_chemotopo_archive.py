import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing

from autoresearch.chemotopo_archive import archive_evidence
from autoresearch.chemotopo_cloud import ChemoTopoCloudLoop
from autoresearch.chemotopo_study import ChemoTopoMemory, ChemoTopoStudy
from autoresearch.contracts import ResearchError
from test_chemotopo_cloud import IDENTITY, ServerFixture
from test_chemotopo_study import fixture_environment, request


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.base=Path(temp.name)
        env=fixture_environment();env.__enter__();self.addCleanup(env.__exit__,None,None,None)
        self.source=self.base/'study';self.loop=ChemoTopoCloudLoop(self.source)
        self.loop.study.create('fixture-source','Conditional source study')
        self.loop.configure(IDENTITY,max_requests=8)

    def run_actions(self,actions):
        return self.loop.run(ServerFixture(actions),max_new_requests=len(actions),verified_weights=IDENTITY)

    def test_postrun_reuse_idempotence_scope_and_source_unchanged(self):
        self.run_actions(['inspect_source','compare_policies','pause'])
        def source_files():return {str(p.relative_to(self.source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.rglob('*') if p.is_file()}
        before=source_files(); target=self.base/'shared'; first=self.base/'receipt1.json'; second=self.base/'receipt2.json'
        first_result=archive_evidence(self.source,target,first)
        self.assertEqual(first_result['status'],'completed');self.assertEqual(first_result['persistence_trigger'],'operator_postrun_workflow')
        self.assertFalse(first_result['model_selected_remember']);self.assertEqual(first_result['import_result']['inserted'],2)
        self.assertEqual({x['type'] for x in first_result['entries']},{'source_qualification','policy_sensitivity'})
        repeat=archive_evidence(self.source,target,second);self.assertEqual(repeat['import_result']['inserted'],0)
        self.assertEqual(source_files(),before)
        with self.assertRaises(FileExistsError):archive_evidence(self.source,target,first)
        self.assertEqual(source_files(),before)
        second_study=ChemoTopoStudy(self.base/'next')
        result=second_study.create('fixture-source','Continue later',memory_workspace=target)
        self.assertEqual(len(result['memory_context']['entries']),2)
        scope={**result['scope'],'inputs_sha256':'e'*64}
        self.assertEqual(ChemoTopoMemory(target).recall(scope)['entries'],[])

    def test_reject_active_and_overlapping_paths(self):
        with self.assertRaises(ResearchError):archive_evidence(self.source,self.base/'shared',self.base/'active.json')
        self.run_actions(['inspect_source','compare_policies','pause'])
        for target,receipt in ((self.source/'inside',self.base/'receipt.json'),(self.base/'shared',self.source/'receipt.json'),(self.base/'shared',self.base/'shared'/'receipt.json')):
            with self.subTest(target=target,receipt=receipt),self.assertRaises(ResearchError):archive_evidence(self.source,target,receipt)
        self.assertFalse((self.base/'shared').exists())

    def test_unbound_and_tampered_sources_fail_before_archive(self):
        self.loop.study.apply(request(self.loop.study,'inspect_source','manual'))
        self.run_actions(['compare_policies','pause'])
        target=self.base/'shared';receipt=self.base/'out.json'
        with self.assertRaises(ResearchError):archive_evidence(self.source,target,receipt)
        self.assertFalse(target.exists());self.assertFalse(receipt.exists())
        with closing(sqlite3.connect(self.loop.db)) as con:
            con.execute("UPDATE calls SET response_json='{}' WHERE ordinal=1");con.commit()
        with self.assertRaises(ResearchError):archive_evidence(self.source,target,receipt)
        self.assertFalse(target.exists());self.assertFalse(receipt.exists())


if __name__=='__main__':unittest.main()
