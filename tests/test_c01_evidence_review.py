"""Source-bound qualitative assertions, never scientific approval."""
import copy
import json
from pathlib import Path
import unittest
import zipfile

from autoresearch.c01_model_loop import build_context
from autoresearch.c01_research_outputs import public_record,export_study
from autoresearch.c01_research_verifier import validate_record,verify_package,PACKAGE_FILES
from autoresearch.contracts import ResearchError
import test_c01_research as fixture

PARAMS={'field':'alp_norm_d21','question':'Does this retrieved source establish the normalization method?',
        'finding':'This synthetic source establishes exploratory aggregates only; the assay method remains unestablished here.',
        'status':'unresolved','next_check':'Locate the original ALP assay methods and distinguish normalization from the reported-value conversion.'}


class EvidenceReviewTests(unittest.TestCase):
    def setUp(self):
        self.base=fixture.C01ResearchTests('test_terminal_decision_is_durable_and_stops_new_dispatch')
        self.base.setUp();self.addCleanup(self.base.doCleanups);self.study=self.base.study
        self.base.search()

    def review(self,**changes):
        return self.base.request('review_evidence',copy.deepcopy(PARAMS),**changes)

    def test_review_copies_exact_retrieved_evidence_without_changing_audit_or_samples(self):
        before=self.study.export();request=self.review();result=self.study.apply(request)
        review=result['action']['result'];after=self.study.export()
        self.assertEqual(review['evidence'],[{k:hit[k] for k in ('citation_id','source','location','quote')}
                                            for hit in before['state']['citations']])
        self.assertTrue(review['source_linkage_verified']);self.assertFalse(review['interpretation_verified'])
        self.assertFalse(review['scientific_approval']);self.assertEqual(after['reproduction'],before['reproduction'])
        self.assertEqual(after['state']['data']['audit'],before['state']['data']['audit'])
        self.assertEqual(after['state']['budget']['fits_used'],0);self.assertEqual(after['state']['status'],'active')
        self.assertIn('下一项核验',after['markdown'])

    def test_unknown_field_missing_next_check_and_approval_injection_rejected(self):
        for replacement in ({'field':'arbitrary_path'},{'next_check':''},{'status':'scientifically_approved'},
                            {'finding':' '},{'approval':True}):
            with self.subTest(replacement=replacement):
                value=self.review();value['parameters'].update(replacement)
                self.base.assert_error('INVALID_REVIEW_STATUS' if 'status' in replacement else 'INVALID_REVIEW',value)

    def test_unknown_or_missing_source_rejected_without_literature_fallback(self):
        for ids in ([],['not-retrieved']):
            self.base.assert_error('INVALID_EVIDENCE',self.review(source_citation_ids=ids))

    def test_raw_text_caps_cannot_be_bypassed_by_whitespace(self):
        for field,maximum in (('question',500),('finding',1000),('next_check',500)):
            with self.subTest(field=field):
                request=self.review();request['parameters'][field]=' '*(maximum+1)+'X'
                self.base.assert_error('INVALID_REVIEW',request)
        self.study.apply(self.review());self.base.fit();exported=self.study.export()
        for field,maximum in (('question',500),('finding',1000),('next_check',500)):
            record=copy.deepcopy(public_record(exported['state']));record['decisions'][1]['parameters'][field]=' '*(maximum+1)+'X'
            with self.assertRaises(ValueError):validate_record(record,exported['reproduction'])

    def test_idempotency_and_duplicate_interpretation_after_reopen(self):
        from autoresearch.c01_research import C01Research
        request=self.review();first=self.study.apply(request)
        replay=C01Research(self.study.root).apply(request)
        self.assertTrue(replay['replayed']);self.assertEqual(first['action'],replay['action'])
        duplicate=self.review(reason='A new reason cannot make the same interpretation new evidence.')
        self.base.assert_error('DUPLICATE_REVIEW',duplicate)

    def test_context_preserves_claim_and_specific_next_check_as_unapproved(self):
        self.study.apply(self.review());obs=self.study.observe()
        ctx=build_context(obs,remaining_requests=5,text_limit=1400)
        item=ctx['actions'][-1]
        self.assertEqual(item['finding'],PARAMS['finding']);self.assertEqual(item['next_check'],PARAMS['next_check'])
        self.assertFalse(item['scientific_approval']);self.assertFalse(item['interpretation_verified'])
        self.assertEqual(item['reviewed_citation_ids'],[obs['citations'][0]['citation_id']])

    def test_public_projection_omits_source_quotes_and_verifies_numbers_without_approving_claim(self):
        self.study.apply(self.review());self.base.fit()
        exported=self.study.export();record=public_record(exported['state'])
        self.assertEqual(record['decisions'][1]['parameters'],PARAMS)
        self.assertNotIn('"quote"',json.dumps(record));self.assertNotIn('source_linkage_verified',json.dumps(record))
        result=validate_record(record,exported['reproduction'])
        self.assertFalse(result['scientific_validation'])
        broken=copy.deepcopy(record);broken['decisions'][1]['parameters']['field']='forged'
        with self.assertRaises(ValueError):validate_record(broken,exported['reproduction'])

    def test_review_report_keeps_existing_package_allowlist_and_independent_recomputation(self):
        self.study.apply(self.review());self.base.fit();self.study.apply(self.base.request('stop'))
        output=self.base.root/'paper';export_study(self.study.root,output)
        target=self.base.root/'unpacked';target.mkdir()
        with zipfile.ZipFile(output/'reproduction.zip') as z:
            self.assertEqual(set(z.namelist()),set(PACKAGE_FILES)|{'package-manifest.json'})
            self.assertNotIn('没有产品后端模型',z.read('README.md').decode('utf-8'))
            for name in z.namelist():
                path=target/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(name))
        result=verify_package(target)
        self.assertFalse(result['scientific_validation'])
        self.assertEqual(result['recipes_checked'],1)


if __name__=='__main__':unittest.main()
