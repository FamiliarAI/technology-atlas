import copy
import io
import json
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from atlas import core, store


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.folder=self.root/'SWE';self.folder.mkdir();self.core=self.root/'core';self.db=self.root/'atlas.sqlite3'
        self.source=self.folder/'paper.html';self.source.write_text('actual source');self.hash=store.sha(self.source.read_bytes())
        self.record={'id':'SWE-01','title':'First breakthrough — café','change_log':[],'unresolved_issues':['Partial evidence'],'provenance':{'research':str(self.folder/'research.md')},'sources':[{'url':'https://example.org','title':'Paper','status':'saved','artifacts':[{'path':'paper.html','absolute_path':str(self.source),'sha256':self.hash,'format':'html','kind':'source'}]}]}
        for section in ['concept','significance','missing_breakthrough','current_state','completion_criteria','related_concepts']:self.record[section]=[{'text':'A proposed capability, discussed with SWE-02.','source_urls':['https://example.org']}]
        other=copy.deepcopy(self.record);other.update(id='SWE-02',title='Second breakthrough')
        self.value={'field':{'prefix':'SWE','field':'Software Engineering','as_of':'2026-11-01','boundaries':'Software'},'created_at':'2026-11-01','innovations':[self.record,other],'original_dispositions':[{'original_id':'old-1','decision':'covered'}],'reconciliation_change_log':['Kept']};self.write()

    def tearDown(self): self.tmp.cleanup()
    def write(self): (self.folder/'final-innovations.json').write_text(json.dumps(self.value))
    def imported(self):
        core.import_field(self.folder,self.core)
        return core.load(self.core)
    def progress(self):
        return {'breakthrough':'SWE-01','milestone':'m1','url':'https://example.org','copy':self.hash,'source_date':'2024-08-27','verdict':'advances','quote':'actual source','by':'test-model','added_at':'2026-11-02'}
    def snapshot(self): return {str(p.relative_to(self.core)):p.read_bytes() for p in self.core.rglob('*') if p.is_file()}

    def test_import_writes_field_and_breakthroughs_and_refuses_reimport(self):
        data=self.imported();field=data['fields']['SWE'];item=data['breakthroughs']['SWE-01']
        self.assertEqual(set(self.snapshot()),{'SWE/field.json','SWE/SWE-01.json','SWE/SWE-02.json','sources.jsonl','progress.jsonl'})
        self.assertEqual(field['id'],'SWE');self.assertEqual(field['name'],'Software Engineering');self.assertEqual(field['color'],store.color('SWE',0))
        for key in ['as_of','boundaries']:self.assertEqual(field[key],self.value['field'][key])
        for key in ['created_at','original_dispositions','reconciliation_change_log']:self.assertEqual(field[key],self.value[key])
        self.assertEqual(field['imported_from']['run_hash'],store.sha((self.folder/'final-innovations.json').read_bytes()))
        self.assertTrue(field['imported_from']['imported_at'])
        for key in ['title','concept','significance','missing_breakthrough','current_state','related_concepts','change_log','unresolved_issues']:self.assertEqual(item[key],self.record[key])
        self.assertEqual((item['field'],item['status'],item['sources']),('SWE','active',['https://example.org']))
        before=self.snapshot()
        with self.assertRaises((ValueError,FileExistsError)):core.import_field(self.folder,self.core)
        self.assertEqual(self.snapshot(),before);self.assertEqual(core.check(data),[])

    def test_import_checks_prefix_unique_ids_and_six_nonempty_sections_before_writing(self):
        variants=[]
        bad=copy.deepcopy(self.value);bad['field']['prefix']='CSC';variants.append(bad)
        bad=copy.deepcopy(self.value);bad['innovations'][1]['id']='SWE-01';variants.append(bad)
        bad=copy.deepcopy(self.value);bad['innovations'][0]['id']='CSC-01';variants.append(bad)
        bad=copy.deepcopy(self.value);bad['innovations']=[];variants.append(bad)
        for section in ['concept','significance','missing_breakthrough','current_state','completion_criteria','related_concepts']:
            for value in [[],None,'text']:
                bad=copy.deepcopy(self.value);bad['innovations'][0][section]=value;variants.append(bad)
        for value in variants:
            with self.subTest(value=value):
                self.value=value;self.write()
                with self.assertRaises(ValueError):core.import_field(self.folder,self.core)
                self.assertFalse((self.core/'SWE').exists());self.assertFalse((self.core/'CSC').exists())

    def test_milestone_ids_and_labels_follow_the_criterion_text(self):
        texts=['Demonstration: measured capability','x'*80+': details','one two three four five six seven eight nine ten '+ 'x'*81+': details','A short criterion without a colon','x'*81]
        self.record['completion_criteria']=[{'text':t,'source_urls':[]} for t in texts];self.write()
        data=self.imported();criteria=data['breakthroughs']['SWE-01']['completion_criteria']
        self.assertEqual([c['id'] for c in criteria],['m1','m2','m3','m4','m5'])
        self.assertEqual([c['label'] for c in criteria],['Demonstration','x'*80,'one two three four five six seven eight','A short criterion without a colon','x'*81])
        self.assertEqual([c['text'] for c in criteria],texts)

    def test_sources_merge_by_url_and_copy_hash_with_first_metadata_winning(self):
        second=self.value['innovations'][1]['sources'][0];second.update(title='Different title',status='failed')
        second['artifacts'].append({'sha256':'b'*64,'format':'pdf','path':'other.pdf','absolute_path':'/private/other.pdf','kind':'source'})
        self.write();data=self.imported();source=data['sources']['https://example.org']
        self.assertEqual((source['title'],source['status']),('Paper','saved'))
        self.assertEqual([a['sha256'] for a in source['copies']],[self.hash,'b'*64])
        self.assertTrue(all('path' not in a and 'absolute_path' not in a for a in source['copies']))
        other=self.root/'CSC';other.mkdir();value=copy.deepcopy(self.value);value['field'].update(prefix='CSC',field='Computer Science')
        for n,item in enumerate(value['innovations'],1):item['id']=f'CSC-0{n}';item['sources'][0]['title']='Later import'
        (other/'final-innovations.json').write_text(json.dumps(value));core.import_field(other,self.core,color='#123456')
        data=core.load(self.core);self.assertEqual(data['sources']['https://example.org'],source)
        self.assertEqual(data['fields']['CSC']['color'],'#123456')

    def test_provenance_is_repo_relative_and_no_absolute_paths_are_written(self):
        data=self.imported();location=data['breakthroughs']['SWE-01']['provenance']['research']
        self.assertFalse(Path(location).is_absolute());self.assertEqual((store.ROOT/location).resolve(),(self.folder/'research.md').resolve())
        for raw in self.snapshot().values():
            self.assertNotIn(b'/Users/',raw);self.assertNotIn(b'"/private/',raw)

    def test_load_and_writers_round_trip_bytes_and_preserve_milestone_ids(self):
        data=self.imported();sources=data['sources'];sources['https://a.example']={'url':'https://a.example','title':'é','status':'saved','copies':[]}
        rows=[self.progress(),dict(self.progress(),verdict='meets')]
        core.write_sources(sources,self.core);core.write_progress(rows,self.core)
        item=data['breakthroughs']['SWE-01'];item['completion_criteria'][0]['id']='m9';core.write_breakthrough(item,self.core)
        before=self.snapshot();data=core.load(self.core)
        for item in data['breakthroughs'].values():core.write_breakthrough(item,self.core)
        core.write_sources(data['sources'],self.core);core.write_progress(data['progress'],self.core)
        self.assertEqual(self.snapshot(),before);self.assertEqual(data['progress'],rows)
        self.assertEqual(data['breakthroughs']['SWE-01']['completion_criteria'][0]['id'],'m9')
        lines=(self.core/'sources.jsonl').read_text().splitlines();self.assertEqual([json.loads(s)['url'] for s in lines],sorted(sources))
        self.assertEqual(len((self.core/'progress.jsonl').read_text().splitlines()),2)
        self.assertIn('\n "id": "SWE-01",\n',(self.core/'SWE/SWE-01.json').read_text())
        self.assertIn('café',(self.core/'SWE/SWE-01.json').read_text())
        self.assertTrue(all(raw.endswith(b'\n') for raw in before.values() if raw))

    def test_check_reports_each_reference_identity_cycle_verdict_and_path_problem(self):
        data=self.imported();data['progress']=[self.progress()]
        self.assertEqual(core.check(data),[])
        cases=[
            ('breakthrough ID',lambda d:d['breakthroughs']['SWE-01'].update(id='SWE-99')),
            ('field',lambda d:d['breakthroughs']['SWE-01'].update(field='CSC')),
            ('field ID',lambda d:d['fields']['SWE'].update(id='CSC')),
            ('milestone',lambda d:d['breakthroughs']['SWE-01']['completion_criteria'].append(copy.deepcopy(d['breakthroughs']['SWE-01']['completion_criteria'][0]))),
            ('milestone',lambda d:d['breakthroughs']['SWE-01']['completion_criteria'][0].pop('id')),
            ('prerequisite',lambda d:d['breakthroughs']['SWE-01'].update(prerequisites=[{'id':'SWE-99'}])),
            ('loop',lambda d:[d['breakthroughs'][a].update(prerequisites=[{'id':b}]) for a,b in [('SWE-01','SWE-02'),('SWE-02','SWE-01')]]),
            ('merged_into',lambda d:d['breakthroughs']['SWE-01'].update(status='retired',merged_into='SWE-99')),
            ('source',lambda d:d['breakthroughs']['SWE-01']['sources'].append('https://unknown')),
            ('breakthrough',lambda d:d['progress'][0].update(breakthrough='SWE-99')),
            ('milestone',lambda d:d['progress'][0].update(milestone='m99')),
            ('source',lambda d:d['progress'][0].update(url='https://unknown')),
            ('verdict',lambda d:d['progress'][0].update(verdict='maybe')),
            ('absolute path',lambda d:d['breakthroughs']['SWE-01']['concept'][0].update(text='/Users/someone/file')),
            ('absolute path',lambda d:d['sources']['https://example.org']['copies'][0].update(note='/private/file')),
        ]
        for expected,break_it in cases:
            with self.subTest(expected=expected):
                broken=copy.deepcopy(data);break_it(broken);problems=core.check(broken)
                self.assertTrue(any(expected.lower() in p.lower() for p in problems),problems)

    def test_check_detects_wrong_file_and_folder_and_duplicate_files_do_not_disappear(self):
        self.imported();page=self.core/'SWE/SWE-01.json';page.rename(self.core/'SWE/SWE-09.json')
        self.assertTrue(any('ID' in p for p in core.check(core.load(self.core))))
        (self.core/'SWE/SWE-09.json').rename(page);other=self.core/'CSC';other.mkdir();page.rename(other/page.name)
        self.assertTrue(any('field' in p.lower() for p in core.check(core.load(self.core))))
        page.write_bytes((other/page.name).read_bytes())
        with self.assertRaises(ValueError):core.load(self.core)

    def test_cli_import_carries_database_links_and_judgements_once_without_changing_database(self):
        with closing(store.connect(self.db)) as db, db:
            # A database as the old ingestion import left it.
            store.initialize(db);db.execute("INSERT INTO runs VALUES ('r','SWE','2026-11-01','{}')");db.execute("INSERT INTO fields VALUES ('SWE','Software Engineering','#fff','r')")
            record=copy.deepcopy(self.record);record['prerequisites']=[{'id':'SWE-02','reason':'Needed','model':'test-model','field':'SWE'}]
            db.execute('INSERT INTO breakthroughs VALUES (?,?,?)',('SWE-01','SWE',json.dumps(record)))
            db.execute('INSERT INTO assets VALUES (?,?,?)',('b'*64,str(self.folder/'added.pdf'),'b'*64))
            for n,verdict in enumerate(['advances','meets'],1):db.execute('INSERT INTO progress VALUES (?,?,?,?,?,?,?,?,?,?)',(f'added:{n}','SWE-01',1,'https://new.example','b'*64,'2024-08-27',verdict,'Exact quote','test-model',f'2026-11-0{n}'))
        before=self.db.read_bytes()
        with patch.object(store,'completed_fields',return_value={'SWE':self.folder}),redirect_stdout(io.StringIO()):
            core.main(['import'],core=self.core,path=self.db)
            first=self.snapshot();core.main(['import'],core=self.core,path=self.db)
        data=core.load(self.core);self.assertEqual(self.snapshot(),first);self.assertEqual(self.db.read_bytes(),before)
        self.assertEqual(data['breakthroughs']['SWE-01']['prerequisites'],record['prerequisites'])
        self.assertEqual(len(data['progress']),2);row=data['progress'][0]
        self.assertEqual((row['milestone'],row['by'],row['copy']),('m1','test-model','b'*64));self.assertEqual(row['quote'],'Exact quote')
        self.assertEqual(data['sources']['https://new.example']['copies'][0]['sha256'],'b'*64)
        self.assertEqual(core.check(data),[])
        out=io.StringIO()
        with redirect_stdout(out):self.assertEqual(core.main(['check'],core=self.core,path=self.db),0)
        self.assertEqual(out.getvalue(),'')
        row['verdict']='maybe';core.write_progress(data['progress'],self.core)
        with redirect_stdout(out):self.assertNotEqual(core.main(['check'],core=self.core,path=self.db),0)
        self.assertIn('verdict',out.getvalue())

    def test_cli_import_works_without_database(self):
        with patch.object(store,'completed_fields',return_value={'SWE':self.folder}),redirect_stdout(io.StringIO()):core.main(['import'],core=self.core,path=self.db)
        self.assertFalse(self.db.exists());self.assertEqual(core.check(core.load(self.core)),[])


if __name__=='__main__':unittest.main()
