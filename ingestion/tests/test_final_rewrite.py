import copy
import tempfile
from pathlib import Path
import unittest
from ingestion.final_rewrite import SECTIONS, validate_record, merge_records, make_input, normalize_source_aliases
from ingestion.sources import write_json


class FinalRewriteTests(unittest.TestCase):
    def test_rejects_invented_citations_and_changed_identity(self):
        payload={'candidate':{'id':'X-01'},'source_index':[{'url':'https://example.org'}]}
        record={'id':'X-01','title':'Concept',**{k:[{'text':'Explanation','source_urls':['https://example.org']}] for k in SECTIONS},'change_log':[],'unresolved_issues':[]}
        validate_record(record,payload)
        invalid=copy.deepcopy(record);invalid['concept'][0]['source_urls']=['https://invented.org']
        with self.assertRaises(ValueError):validate_record(invalid,payload)
        invalid=copy.deepcopy(record);invalid['id']='X-02'
        with self.assertRaises(ValueError):validate_record(invalid,payload)

    def test_merge_requires_every_concept_exactly_once(self):
        rows=[{'id':'X-02'},{'id':'X-01'}]
        self.assertEqual([r['id'] for r in merge_records(rows,['X-01','X-02'])],['X-01','X-02'])
        for bad in [rows[:1],rows+[rows[0]],rows+[{'id':'X-03'}]]:
            with self.assertRaises(ValueError):merge_records(bad,['X-01','X-02'])

    def test_input_excludes_source_bodies_and_other_research(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);review={'evidence_review':{'claims':[]}}
            write_json(root/'validated.json',review)
            write_json(root/'input.json',{'sources':[{'text':'HUGE DOCUMENT MUST NOT BE LOADED'}]})
            candidate={'id':'X-01','claims':[]}
            reviews={'X-01':{'status':'complete','path':str(root),'review':review}}
            research='**X-01. First**\nFirst details\n**X-02. Second**\nOther details\n**Change log**\nChanges'
            value=make_input(root,candidate,[],research,reviews,[])
            self.assertIn('First details',value['research'])
            self.assertNotIn('Other details',str(value))
            self.assertNotIn('HUGE DOCUMENT',str(value))
            reviews['X-01']['status']='failed'
            with self.assertRaises(ValueError):make_input(root,candidate,[],research,reviews,[])

    def test_saved_artifact_alias_is_normalized_but_unknown_url_is_not(self):
        payload={'source_index':[{'url':'https://paper.org','artifacts':[{'resolved_url':'https://repository.org/paper.pdf'}]}]}
        record={section:[{'text':'Text','source_urls':['https://repository.org/paper.pdf','https://unknown.org']}] for section in SECTIONS}
        normalized=normalize_source_aliases(record,payload)
        self.assertEqual(normalized['concept'][0]['source_urls'],['https://paper.org','https://unknown.org'])
        self.assertEqual(record['concept'][0]['source_urls'][0],'https://repository.org/paper.pdf')

    def rewrite_fixture(self, root, raw):
        from ingestion.final_rewrite import FINAL_SCHEMA, fingerprint, prompt
        from ingestion.sources import read_json
        import ingestion.final_rewrite as module
        url='https://paper.org'
        record={'id':'X-01','title':'Concept',**{k:[{'text':'Explanation','source_urls':[url]}] for k in SECTIONS},'change_log':[],'unresolved_issues':[]}
        payload={'candidate':{'id':'X-01'},'research':'Research','validated_review':{},
                 'source_index':[{'url':url,'title':'Paper','status':'saved','artifacts':[{'resolved_url':'https://repository.org/paper.pdf','format':'pdf','absolute_path':'/saved/paper.pdf','sha256':'example'}]}],
                 'provenance':{'review':'/review.json','research':'/research.md'}}
        (root/'attempts').mkdir()
        prior=root/'attempts/final-rewrite-prior/X-01';prior.mkdir(parents=True)
        import json
        text=prompt('final_rewrite',INPUT=json.dumps(payload,ensure_ascii=False))
        config=read_json(Path(module.__file__).parent/'config.json')
        key=fingerprint({'prompt':text,'schema':FINAL_SCHEMA,'model':config['review']})
        write_json(prior/'receipt.json',{'status':'failed','input_hash':key})
        write_json(prior/'result.json',raw or record)
        (root/'reconciled-research.md').write_text('Research')
        write_json(root/'reconciled-candidates.json',{'problems':[{'id':'X-01','title':'Concept'}]})
        write_json(root/'reconciled-reviews.json',{})
        write_json(root/'source-file-index.json',[])
        write_json(root/'field.json',{'field':'Test'})
        write_json(root/'reconciled-structured.json',{'original_dispositions':[],'change_log':[]})
        return payload,record,prior,key

    def test_invalid_prior_output_triggers_one_fresh_call_with_error(self):
        from unittest.mock import patch
        from ingestion.final_rewrite import run
        from ingestion.sources import read_json
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            payload,valid,prior,key=self.rewrite_fixture(root,{'bad':'schema'})
            original=(prior/'result.json').read_bytes()
            with patch('ingestion.final_rewrite.validate_candidates',side_effect=lambda x:x), \
                 patch('ingestion.final_rewrite.make_input',return_value=payload), \
                 patch('ingestion.final_rewrite.Models.call',return_value=valid) as call:
                run(root,workers=1)
            call.assert_called_once()
            self.assertIn('prior attempt failed output validation',call.call_args.args[1])
            self.assertEqual((prior/'result.json').read_bytes(),original)
            self.assertEqual(read_json(root/'final-innovations.json')['innovations'][0]['id'],'X-01')
            # Successful-cache corruption stays fail closed; it must not call the model.
            cache=root/'final-rewrite-cache'/(key+'.json');cached=read_json(cache)
            cached['record']['title']='Changed without hash update';write_json(cache,cached)
            with patch('ingestion.final_rewrite.validate_candidates',side_effect=lambda x:x), \
                 patch('ingestion.final_rewrite.make_input',return_value=payload), \
                 patch('ingestion.final_rewrite.Models.call') as call:
                with self.assertRaisesRegex(ValueError,'Cached rewrite changed'):run(root,workers=1)
                call.assert_not_called()

    def test_alias_repair_recovers_prior_without_new_call(self):
        from unittest.mock import patch
        from ingestion.final_rewrite import run
        from ingestion.sources import read_json
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            payload,valid,prior,key=self.rewrite_fixture(root,None)
            valid['concept'][0]['source_urls']=['https://repository.org/paper.pdf']
            write_json(prior/'result.json',valid)
            original=(prior/'result.json').read_bytes()
            with patch('ingestion.final_rewrite.validate_candidates',side_effect=lambda x:x), \
                 patch('ingestion.final_rewrite.make_input',return_value=payload), \
                 patch('ingestion.final_rewrite.Models.call') as call:
                run(root,workers=1)
                call.assert_not_called()
            result=read_json(root/'final-innovations.json')['innovations'][0]
            self.assertEqual(result['concept'][0]['source_urls'],['https://paper.org'])
            self.assertEqual((prior/'result.json').read_bytes(),original)

    def test_atx_and_bold_research_extract_same_concept_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);review={'evidence_review':{'claims':[]}}
            write_json(root/'validated.json',review)
            candidate={'id':'CSC-01','claims':[]}
            reviews={'CSC-01':{'status':'complete','path':str(root),'review':review}}
            body='\nFirst details\n## CSC-01-current_state. This is a claim, not a concept boundary\nMore first details\n'
            values=[]
            for first,second,change in [('**CSC-01. One**','**CSC-02. Two**','**Change log**'),
                                        ('## CSC-01. One','### CSC-02. Two','## Change log')]:
                text=first+body+second+'\nSecond details\n'+change+'\nAudit notes'
                value=make_input(root,candidate,[],text,reviews,[])['research']
                values.append(value.split('\n',1)[1])
                self.assertNotIn('Second details',value)
                self.assertNotIn('Audit notes',value)
            self.assertEqual(values,[body[1:],body[1:]])
            last=make_input(root,{'id':'CSC-02','claims':[]},[],
                '## CSC-02. Two\nSecond details\n## Change log\nAudit notes',
                {'CSC-02':reviews['CSC-01']},[])['research']
            self.assertNotIn('Audit notes',last)
