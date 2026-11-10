import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from atlas import core
from atlas.store import rebuild, resolver, completed_fields, connect, catalog, progress, progress_summary, sha
from atlas.server import Handler
from atlas.add import add
from atlas.add import main as add_main
from atlas.prerequisites import run as prerequisites
from atlas.prerequisites import main as prerequisites_main

TABLES=['runs','fields','breakthroughs','assets','documents','progress']

class AtlasTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.folder=self.root/'SWE';(self.folder/'sources').mkdir(parents=True);self.db=self.root/'atlas.sqlite3';self.core=self.root/'core'
        body=b'<script>bad()</script>actual source';self.hash=sha(body);self.source=self.folder/'sources'/(self.hash+'.html');self.source.write_bytes(body)
        self.record={'id':'SWE-01','title':'First breakthrough','change_log':[],'unresolved_issues':['Partial evidence'],'provenance':{},'sources':[{'url':'https://example.org','title':'Paper','status':'saved','artifacts':[{'path':'sources/'+self.source.name,'sha256':self.hash,'format':'html','kind':'source'}]}]}
        for section in ['concept','significance','missing_breakthrough','current_state','completion_criteria','related_concepts']:self.record[section]=[{'text':'A proposed capability, discussed with SWE-02.','source_urls':['https://example.org']}]
        other=copy.deepcopy(self.record);other.update(id='SWE-02',title='Second breakthrough')
        self.value={'field':{'prefix':'SWE','field':'Software Engineering'},'created_at':'2026-11-01T00:00:00+00:00','innovations':[self.record,other],'original_dispositions':[{'original_id':'old-1','decision':'covered'}]};self.write()
    def tearDown(self): self.tmp.cleanup()
    def write(self): (self.folder/'final-innovations.json').write_text(json.dumps(self.value))
    def load(self,folder=None):
        folder=folder or self.folder
        if not (self.core/folder.name).exists():core.import_field(folder,self.core)
        return rebuild(self.core,self.db,roots=[self.root])
    def tables(self):
        with connect(self.db) as db:return {t:[tuple(r) for r in db.execute(f'SELECT * FROM {t} ORDER BY 1')] for t in TABLES}
    def judged(self,verdict='meets'):
        data=core.load(self.core);data['sources']['https://example.org/new']={'url':'https://example.org/new','title':'New','status':'saved','copies':[{'sha256':self.hash,'format':'html','kind':'source'}]}
        core.write_sources(data['sources'],self.core)
        core.write_progress([{'breakthrough':'SWE-01','milestone':'m1','url':'https://example.org/new','copy':self.hash,'source_date':'2026-12-01','verdict':verdict,'quote':'quote','by':'model','added_at':'2026-12-02'}],self.core)

    def test_rebuild_loads_core_records_with_sources_expanded(self):
        counts=self.load();self.assertEqual((counts['breakthroughs'],counts['assets'],counts['missing']),(2,1,0))
        field=(self.core/'SWE/field.json').read_text()
        with connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM runs').fetchone()[0],1)
            run=db.execute('SELECT * FROM runs').fetchone();self.assertEqual((run['hash'],run['payload']),(json.loads(field)['imported_from']['run_hash'],field))
            self.assertEqual(tuple(db.execute('SELECT id,name,run_hash FROM fields').fetchone()),('SWE','Software Engineering',run['hash']))
            item=json.loads(db.execute('SELECT payload FROM breakthroughs WHERE id=?',('SWE-01',)).fetchone()[0])
            self.assertEqual(db.execute('SELECT path FROM assets').fetchone()[0],str(self.source.resolve()))
        for key in ['title','concept','current_state','unresolved_issues','change_log']:self.assertEqual(item[key],self.record[key])
        self.assertEqual(item['sources'],[{'url':'https://example.org','title':'Paper','status':'saved','artifacts':[{'sha256':self.hash,'format':'html','kind':'source'}]}])
        self.assertEqual((item['field'],item['status'],item['completion_criteria'][0]['id']),('SWE','active','m1'))

    def test_retired_breakthroughs_are_not_loaded(self):
        core.import_field(self.folder,self.core);data=core.load(self.core);item=data['breakthroughs']['SWE-02'];item.update(status='retired',merged_into='SWE-01');core.write_breakthrough(item,self.core)
        self.load()
        with connect(self.db) as db:self.assertEqual([r[0] for r in db.execute('SELECT id FROM breakthroughs')],['SWE-01'])

    def test_deleting_and_rebuilding_gives_identical_tables(self):
        core.import_field(self.folder,self.core);self.judged();self.load();before=self.tables()
        self.db.unlink();self.load();self.assertEqual(self.tables(),before)
        self.assertEqual(len(before['progress']),3)

    def test_check_problem_stops_rebuild_and_keeps_old_database(self):
        self.load();before=self.db.read_bytes()
        item=core.load(self.core)['breakthroughs']['SWE-01'];item['prerequisites']=[{'id':'SWE-99','reason':'x','model':'m','field':'SWE'}];core.write_breakthrough(item,self.core)
        with self.assertRaises(ValueError) as error:self.load()
        self.assertIn('SWE-99',str(error.exception));self.assertEqual(self.db.read_bytes(),before)
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if p.name.startswith('atlas.sqlite3')),['atlas.sqlite3'])

    def test_changed_copy_stops_rebuild_and_missing_copy_is_skipped(self):
        self.load();before=self.db.read_bytes();self.source.write_text('changed')
        with self.assertRaises(ValueError):self.load()
        self.assertEqual(self.db.read_bytes(),before)
        self.source.unlink();counts=self.load();self.assertEqual((counts['assets'],counts['missing']),(0,1))

    def test_connections_are_explicit_mentions_with_preserved_explanation(self):
        self.load()
        with connect(self.db) as db:d=catalog(db)
        self.assertEqual(len(d['connections']),1);edge=d['connections'][0]
        self.assertEqual(edge['kind'],'discussed together');self.assertEqual((edge['source'],edge['target']),('SWE-01','SWE-02'))
        self.assertEqual(edge['explanations'][0]['text'],self.record['related_concepts'][0]['text'])

    def test_http_source_downloads_are_allowlisted_and_integrity_checked(self):
        self.load();server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.db_path=self.db
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base+'/api/assets/'+self.hash) as res:
                self.assertIn('attachment',res.headers['Content-Disposition']);self.assertEqual(res.read(),self.source.read_bytes())
            with self.assertRaises(HTTPError) as error:urlopen(base+'/api/assets/../../etc/passwd')
            self.assertEqual(error.exception.code,404)
            self.source.write_text('tampered')
            with self.assertRaises(HTTPError) as error:urlopen(base+'/api/assets/'+self.hash)
            self.assertEqual(error.exception.code,409)
            with urlopen(base+'/api/breakthroughs/SWE-01') as res:
                item=json.load(res);self.assertNotIn('provenance',item);self.assertNotIn('path',item['sources'][0]['artifacts'][0])
        finally:server.shutdown();server.server_close();thread.join()

    def test_manifest_selects_completed_fields_from_their_roots(self):
        moved=self.root/'elsewhere'/'SWE';moved.parent.mkdir();self.folder.rename(moved)
        manifest=self.root/'batch.json';manifest.write_text(json.dumps({'fields':[{'prefix':'SWE','root':str(moved),'status':'complete'},{'prefix':'CSC','root':str(self.root/'CSC'),'status':'pending'}]}))
        roots=completed_fields(manifest);self.assertEqual(roots,{'SWE':moved})
        self.load(roots['SWE'])
        with connect(self.db) as db:self.assertEqual(catalog(db)['breakthroughs'][0]['milestone_count'],1)

    def test_current_state_sources_backfill_progress_without_status(self):
        self.load()
        with connect(self.db) as db:
            rows,status=progress(db,'SWE-01',1)
            self.assertEqual(len(rows),1);self.assertEqual((rows[0]['url'],rows[0]['asset'],rows[0]['criterion'],rows[0]['verdict']),('https://example.org',self.hash,None,None))
            self.assertEqual(status,['none'])
        self.judged();self.load()
        with connect(self.db) as db:
            rows,status=progress(db,'SWE-01',1)
            self.assertEqual(len(rows),2);self.assertEqual(status,['met'])
            self.assertEqual(rows[0]['id'],f'added:{self.hash}:SWE-01:1')
            self.assertEqual(db.execute("SELECT COUNT(*) FROM progress WHERE id LIKE 'research:%'").fetchone()[0],2)

    def test_added_source_stores_only_verified_candidate_rows_and_replaces_on_readd(self):
        self.load();self.judged()
        data=core.load(self.core);item=data['breakthroughs']['SWE-01'];item['completion_criteria'][0]['id']='m7';core.write_breakthrough(item,self.core)
        data['progress'][0]['breakthrough']='SWE-02';core.write_progress(data['progress'],self.core);self.load()
        text='Results: we demonstrate a proposed capability at full scale in a working system.'
        added=self.root/'added/sources';added.mkdir(parents=True);digest=sha(text.encode());saved=added/(digest+'.html');saved.write_text(text)
        capture=patch('atlas.store.resolver',side_effect=lambda roots:resolver([self.root]));capture.start();self.addCleanup(capture.stop)
        reply={'source_date':'2026-11','rows':[
            {'breakthrough':'SWE-01','criterion':1,'verdict':'advances','quote':'we demonstrate a proposed capability at full scale'},
            {'breakthrough':'SWE-02','criterion':1,'verdict':'meets','quote':'a sentence the source never contains anywhere'},
            {'breakthrough':'SWE-09','criterion':1,'verdict':'meets','quote':'we demonstrate a proposed capability at full scale'}]}
        saver=lambda url:(digest,str(saved),text)
        stored,rejected=add('https://arxiv.org/abs/1',call=lambda prompt:reply,saver=saver,core=self.core,path=self.db)
        self.assertEqual([(r['breakthrough'],r['criterion']) for r in stored],[('SWE-01',1)])
        self.assertEqual(sorted(why for _,why in rejected),['not a candidate milestone','quote not found in saved copy'])
        data=core.load(self.core);source=data['sources']['https://arxiv.org/abs/1'];judgement=data['progress'][-1]
        self.assertEqual((source['status'],source['copies']),('saved',[{'sha256':digest,'format':'html','kind':'source'}]))
        self.assertEqual((judgement['breakthrough'],judgement['milestone'],judgement['url'],judgement['copy']),('SWE-01','m7','https://arxiv.org/abs/1',digest))
        self.assertEqual((judgement['verdict'],judgement['source_date'],judgement['quote']),('advances','2026-11',reply['rows'][0]['quote']))
        self.assertTrue(judgement['by']);self.assertTrue(judgement['added_at']);self.assertEqual(core.check(data),[])
        with connect(self.db) as db:
            rows,status=progress(db,'SWE-01',1)
            rows=[r for r in rows if r['url']=='https://arxiv.org/abs/1']
            self.assertEqual((rows[0]['verdict'],rows[0]['source_date'],rows[0]['asset']),('advances','2026-11',digest));self.assertEqual(status,['in_progress'])
            self.assertEqual(db.execute('SELECT path FROM assets WHERE id=?',(digest,)).fetchone()[0],str(saved.resolve()))
        add('https://arxiv.org/abs/1',call=lambda prompt:reply,saver=saver,core=self.core,path=self.db)
        data=core.load(self.core);self.assertEqual(len(data['progress']),2);self.assertEqual(len(data['sources']['https://arxiv.org/abs/1']['copies']),1)
        self.db.unlink();self.load()
        with connect(self.db) as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM progress WHERE url='https://arxiv.org/abs/1'").fetchone()[0],1)
        reply['rows']=[]
        add('https://arxiv.org/abs/1',call=lambda prompt:reply,saver=saver,core=self.core,path=self.db)
        self.assertEqual([r['url'] for r in core.load(self.core)['progress']],['https://example.org/new'])
        with connect(self.db) as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM progress WHERE url='https://arxiv.org/abs/1'").fetchone()[0],0)
        add('https://example.org',call=lambda prompt:reply,saver=lambda url:(self.hash,str(self.source),text),core=self.core,path=self.db)
        self.assertEqual(len(core.load(self.core)['sources']['https://example.org']['copies']),1)
        add('https://example.org',call=lambda prompt:reply,saver=saver,core=self.core,path=self.db)
        source=core.load(self.core)['sources']['https://example.org'];self.assertEqual(source['title'],'Paper');self.assertEqual(len(source['copies']),2)

    def test_progress_summary_lists_every_breakthrough(self):
        self.load()
        with connect(self.db) as db:
            self.assertEqual(progress_summary(db),{'SWE-01':{'status':['none'],'count':1},'SWE-02':{'status':['none'],'count':1}})

    def test_prerequisites_keep_checked_links_on_the_dependent_record(self):
        other=self.root/'CSC';(other/'sources').mkdir(parents=True);(other/'sources'/self.source.name).write_bytes(self.source.read_bytes())
        value=copy.deepcopy(self.value);value['field']={'prefix':'CSC','field':'Computer Science'}
        for n,i in enumerate(value['innovations'],1):i['id']=f'CSC-0{n}'
        (other/'final-innovations.json').write_text(json.dumps(value));core.import_field(self.folder,self.core);self.load(other)
        reply={'breakthroughs':[
            {'breakthrough':'SWE-01','needs':[{'id':'SWE-09','reason':'SWE-09 does not exist in the catalog at all.'}],'needed_by':[{'id':'SWE-02','reason':'SWE-02 builds directly on the SWE-01 capability.'}]},
            {'breakthrough':'SWE-02','needs':[{'id':'SWE-01','reason':'Repeated from the other side of the same link.'}],'needed_by':[{'id':'CSC-01','reason':'CSC-01 needs the SWE-02 system to exist first.'},{'id':'SWE-01','reason':'This link would close a loop with SWE-02.'}]},
            {'breakthrough':'CSC-02','needs':[{'id':'CSC-01','reason':'Neither side of this link is in this field.'}],'needed_by':[]}]}
        capture=patch('atlas.store.resolver',side_effect=lambda roots:resolver([self.root]));capture.start();self.addCleanup(capture.stop)
        before=core.load(self.core)['breakthroughs']
        stored,rejected=prerequisites('SWE',call=lambda prompt:reply,core=self.core,path=self.db)
        self.assertEqual(len(stored),2);self.assertEqual(sorted(why for _,why in rejected),['closes a loop','neither side in this field','unknown ID'])
        data=core.load(self.core);self.assertEqual(core.check(data),[])
        for identifier,item in data['breakthroughs'].items():
            self.assertEqual({k:v for k,v in item.items() if k!='prerequisites'},before[identifier])
        self.assertEqual(data['breakthroughs']['SWE-02']['prerequisites'][0]['id'],'SWE-01')
        self.assertEqual(data['breakthroughs']['CSC-01']['prerequisites'][0]['field'],'SWE')
        self.db.unlink();self.load()
        with connect(self.db) as db:
            items={i['id']:i['prerequisites'] for i in catalog(db)['breakthroughs']}
            self.assertEqual(items,{'SWE-01':[],'SWE-02':['SWE-01'],'CSC-01':['SWE-02'],'CSC-02':[]})
            self.assertEqual(json.loads(db.execute("SELECT payload FROM breakthroughs WHERE id='CSC-01'").fetchone()[0])['prerequisites'][0]['field'],'SWE')
        prerequisites('CSC',call=lambda prompt:{'breakthroughs':[{'breakthrough':'CSC-02','needs':[{'id':'CSC-01','reason':'CSC-02 extends the CSC-01 result directly.'}],'needed_by':[]}]},core=self.core,path=self.db)
        prerequisites('SWE',call=lambda prompt:{'breakthroughs':[]},core=self.core,path=self.db)
        data=core.load(self.core)
        self.assertEqual(data['breakthroughs']['SWE-02']['prerequisites'],[]);self.assertEqual(data['breakthroughs']['CSC-01']['prerequisites'],[])
        self.assertEqual(data['breakthroughs']['CSC-02']['prerequisites'][0]['id'],'CSC-01')
        with connect(self.db) as db:
            self.assertEqual({i['id']:i['prerequisites'] for i in catalog(db)['breakthroughs']},{'SWE-01':[],'SWE-02':[],'CSC-01':[],'CSC-02':['CSC-01']})

    def test_writer_commands_commit_core_unless_no_commit(self):
        self.load();calls=self.root/'calls'
        for module,main,args,writer in [('atlas.add',add_main,['https://example.org'],'add'),('atlas.prerequisites',prerequisites_main,['SWE'],'run')]:
            for flag in [[],['--no-commit']]:
                with self.subTest(module=module,flag=flag),patch('sys.argv',[module]+args+flag),patch(module+'.DB',self.db),patch(module+'._call',return_value=(calls,lambda prompt:{})),patch(module+'.'+writer,return_value=([],[])),patch('subprocess.run') as git,patch('atlas.add.request_wayback',return_value=True),patch('builtins.print'):
                    main()
                    if flag:git.assert_not_called()
                    else:
                        self.assertEqual(git.call_count,3)
                        self.assertEqual(git.call_args_list[0].args[0],['git','add','atlas/core'])
                        command=git.call_args_list[2].args[0];self.assertEqual(command[:3],['git','commit','-m']);self.assertEqual(command[4:],['--','atlas/core'])
                        self.assertIn(args[0],command[3]);self.assertIn('\nModel: ',command[3]);self.assertIn(str(calls),command[3])

if __name__=='__main__':unittest.main()
