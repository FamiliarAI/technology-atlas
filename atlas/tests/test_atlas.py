import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from atlas.store import import_fields, completed_fields, connect, catalog, progress, progress_summary, sha
from atlas.server import Handler
from atlas.add import add

class AtlasTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.folder=self.root/'SWE';self.folder.mkdir();self.db=self.root/'atlas.sqlite3'
        self.source=self.folder/'paper.html';self.source.write_text('<script>bad()</script>actual source');self.hash=sha(self.source.read_bytes())
        self.record={'id':'SWE-01','title':'First breakthrough','change_log':[],'unresolved_issues':['Partial evidence'],'provenance':{},'sources':[{'url':'https://example.org','title':'Paper','status':'saved','artifacts':[{'path':'paper.html','sha256':self.hash,'format':'html'}]}]}
        for section in ['concept','significance','missing_breakthrough','current_state','completion_criteria','related_concepts']:self.record[section]=[{'text':'A proposed capability, discussed with SWE-02.','source_urls':['https://example.org']}]
        other=copy.deepcopy(self.record);other.update(id='SWE-02',title='Second breakthrough')
        self.value={'field':{'prefix':'SWE','field':'Software Engineering'},'innovations':[self.record,other],'original_dispositions':[{'original_id':'old-1','decision':'covered'}]};self.write()
    def tearDown(self): self.tmp.cleanup()
    def write(self): (self.folder/'final-innovations.json').write_text(json.dumps(self.value))
    def load(self):return import_fields(self.root,self.db,['SWE'])
    def test_repeat_import_preserves_full_payload_without_duplicates(self):
        self.assertEqual(self.load(),['SWE']);self.assertEqual(self.load(),[])
        with connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM runs').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM breakthroughs').fetchone()[0],2)
            self.assertEqual(json.loads(db.execute('SELECT payload FROM breakthroughs WHERE id=?', ('SWE-01',)).fetchone()[0]),self.record)
            self.assertEqual(json.loads(db.execute('SELECT payload FROM runs').fetchone()[0]),self.value)
    def test_new_revision_keeps_prior_snapshot(self):
        self.load();self.value['innovations'][0]['title']='Revised title';self.write();self.load()
        with connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM runs').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT count(*) FROM breakthroughs').fetchone()[0],2)
    def test_tampered_artifact_rolls_back_revision(self):
        self.load();self.value['innovations'][0]['title']='Bad revision';self.write();self.source.write_text('changed')
        with self.assertRaises(ValueError):self.load()
        with connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM runs').fetchone()[0],1)
            self.assertEqual(json.loads(db.execute('SELECT payload FROM breakthroughs WHERE id=?', ('SWE-01',)).fetchone()[0])['title'],'First breakthrough')
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
        self.assertEqual(import_fields(self.root,self.db,sorted(roots),roots),['SWE'])
        with connect(self.db) as db:self.assertEqual(catalog(db)['breakthroughs'][0]['milestone_count'],1)

    def test_current_state_sources_backfill_progress_without_status(self):
        self.load()
        with connect(self.db) as db:
            rows,status=progress(db,'SWE-01',1)
            self.assertEqual(len(rows),1);self.assertEqual((rows[0]['url'],rows[0]['asset'],rows[0]['criterion'],rows[0]['verdict']),('https://example.org',self.hash,None,None))
            self.assertEqual(status,['none'])
            db.execute("INSERT INTO progress VALUES ('added:1','SWE-01',1,'https://example.org/new',NULL,'2026-12-01','meets','quote','model','2026-12-02')");db.commit()
        self.record['title']='Revised';self.write();self.load()
        with connect(self.db) as db:
            rows,status=progress(db,'SWE-01',1)
            self.assertEqual(len(rows),2);self.assertEqual(status,['met'])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM progress WHERE id LIKE 'research:%'").fetchone()[0],2)

    def test_added_source_stores_only_verified_candidate_rows_and_replaces_on_readd(self):
        self.load()
        text='Results: we demonstrate a proposed capability at full scale in a working system.'
        reply={'source_date':'2026-11','rows':[
            {'breakthrough':'SWE-01','criterion':1,'verdict':'advances','quote':'we demonstrate a proposed capability at full scale'},
            {'breakthrough':'SWE-02','criterion':1,'verdict':'meets','quote':'a sentence the source never contains anywhere'},
            {'breakthrough':'SWE-09','criterion':1,'verdict':'meets','quote':'we demonstrate a proposed capability at full scale'}]}
        saver=lambda url:('f'*64,str(self.source),text)
        stored,rejected=add('https://arxiv.org/abs/1',call=lambda prompt:reply,saver=saver,path=self.db)
        self.assertEqual([(r['breakthrough'],r['criterion']) for r in stored],[('SWE-01',1)])
        self.assertEqual(sorted(why for _,why in rejected),['not a candidate milestone','quote not found in saved copy'])
        with connect(self.db) as db:
            rows,status=progress(db,'SWE-01',1)
            added=[r for r in rows if r['id'].startswith('added:')]
            self.assertEqual((added[0]['verdict'],added[0]['source_date'],added[0]['asset']),('advances','2026-11','f'*64));self.assertEqual(status,['in_progress'])
        reply['rows']=[]
        add('https://arxiv.org/abs/1',call=lambda prompt:reply,saver=saver,path=self.db)
        with connect(self.db) as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM progress WHERE id LIKE 'added:%'").fetchone()[0],0)

    def test_progress_summary_lists_every_breakthrough(self):
        self.load()
        with connect(self.db) as db:
            self.assertEqual(progress_summary(db),{'SWE-01':{'status':['none'],'count':1},'SWE-02':{'status':['none'],'count':1}})

if __name__=='__main__':unittest.main()
