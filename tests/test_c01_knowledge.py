"""Synthetic source-contract tests, not real paper/scientific evaluations."""
import hashlib
import json
from pathlib import Path
import unittest

from autoresearch.c01_knowledge import PAGES, collect_case_sources, build_case_index
from autoresearch.contracts import ResearchError
from autoresearch.knowledge import KnowledgeIndex
import test_c01_source_audit as source_fixture


class CaseKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.base=source_fixture.C01SourceAuditTests('test_offline_comparison_keeps_formula_text_and_original_bytes')
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.snapshot=self.base.snapshot
        self.manifest=self.base.manifest
        self.manifest['pages']=[]
        for name, spec in PAGES.items():
            payload=('SYNTHETIC source, not an author fact.\n'+name+'\nMC3T3 passage13 ALP normalised DNA\n'
                     '## Conclusions\nSynthetic body only.\n## References\nFOREIGN_RECOMMENDATION_ONLY\n').encode()
            (self.snapshot/name).write_bytes(payload)
            self.manifest['pages'].append({'name':name,'url':spec['url'],'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()})
        self.base.save()

    def test_verbatim_sources_keep_roles_urls_and_original_line_coordinates(self):
        docs,audit=collect_case_sources(self.base.base.archive,self.snapshot)
        self.assertEqual(len(docs),3)
        self.assertTrue(audit['all_five_attachments_byte_equal'])
        output=self.base.base.root/'new-index'
        manifest=build_case_index(self.base.base.archive,self.snapshot,output)
        self.assertEqual(manifest['documents'],3)
        hits=KnowledgeIndex(output/'knowledge.sqlite').search('normalised',limit=4)['evidence']
        self.assertEqual(len(hits),3)
        for doc in docs:
            name=Path(doc['path']).name
            self.assertTrue((self.snapshot/name).read_bytes().startswith(doc['text'].encode()))
            self.assertEqual(doc['sha256'],hashlib.sha256((self.snapshot/name).read_bytes()).hexdigest())
            self.assertEqual(doc['source_url'],PAGES[name]['url'])
            self.assertFalse(doc['metadata']['manual_protocol_review_included'])
        for hit in hits:
            lines=(self.snapshot/Path(hit['source']['path']).name).read_text('utf-8').splitlines()
            location=hit['location']
            self.assertIn(hit['quote'].strip(),'\n'.join(lines[location['line_start']-1:location['line_end']]))
        self.assertFalse(manifest['scientific_validation'])
        related=next(d for d in docs if 'paper-2021' in d['id'])
        self.assertIn('not_c01_holdout',related['metadata']['source_role'])
        self.assertEqual(related['metadata']['paper_license'],'not inferred from dataset license')
        paper_hits=KnowledgeIndex(output/'knowledge.sqlite').search('FOREIGN_RECOMMENDATION_ONLY',kinds=['research_paper'])['evidence']
        self.assertEqual(paper_hits,[])

    def test_unknown_article_boundary_does_not_guess_or_relabel_foreign_text(self):
        page=next(p for p in self.manifest['pages'] if p['name']=='paper-2023.md')
        payload=b'Synthetic changed page without an article boundary.\n'
        (self.snapshot/page['name']).write_bytes(payload)
        page.update(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest())
        self.base.save()
        with self.assertRaises(ResearchError) as error: collect_case_sources(self.base.base.archive,self.snapshot)
        self.assertEqual(error.exception.code,'SOURCE_STRUCTURE_CHANGED')

    def test_changed_page_missing_primary_or_wrong_publisher_url_refuses_build(self):
        archive=self.base.base.archive
        original=(self.snapshot/'paper-2023.md').read_bytes()
        (self.snapshot/'paper-2023.md').write_text('changed',encoding='utf-8')
        with self.assertRaises(ResearchError): collect_case_sources(archive,self.snapshot)
        (self.snapshot/'paper-2023.md').write_bytes(original)
        self.manifest['pages']=[p for p in self.manifest['pages'] if p['name']!='paper-2021.md']
        self.base.save()
        with self.assertRaises(ResearchError): collect_case_sources(self.base.base.archive,self.snapshot)

    def test_resealed_wrong_url_and_attachment_mismatch_are_not_accepted(self):
        self.manifest['pages'][1]['url']='https://example.invalid/other-paper'
        self.base.save()
        with self.assertRaises(ResearchError): collect_case_sources(self.base.base.archive,self.snapshot)
        self.manifest['pages'][1]['url']=PAGES['paper-2023.md']['url']
        record=next(row for row in self.manifest['files'] if row['name'].endswith('.csv'))
        changed=b'different author attachment'
        (self.snapshot/record['name']).write_bytes(changed)
        record.update(bytes=len(changed),sha256=hashlib.sha256(changed).hexdigest())
        self.base.save()
        with self.assertRaises(ResearchError): collect_case_sources(self.base.base.archive,self.snapshot)

    def test_existing_index_is_preserved(self):
        output=self.base.base.root/'new-index'
        build_case_index(self.base.base.archive,self.snapshot,output)
        before=(output/'knowledge.sqlite').read_bytes()
        with self.assertRaises(ResearchError): build_case_index(self.base.base.archive,self.snapshot,output)
        self.assertEqual((output/'knowledge.sqlite').read_bytes(),before)
