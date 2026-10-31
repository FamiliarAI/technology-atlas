"""Local SQLite persistence. Standard library only; seed once, never refresh over edits."""
from pathlib import Path
from contextlib import contextmanager,closing
from datetime import datetime, timezone
import sqlite3, json, hashlib, uuid

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_DB=ROOT/'data/techtree.sqlite3'
SEEDS=ROOT/'web/data'
def encode(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def now(): return datetime.now(timezone.utc).isoformat()
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
class APIError(Exception):
    def __init__(self,status,message,code='invalid_request',details=None):
        super().__init__(message);self.status=status;self.code=code;self.details=details

SCHEMA='''
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents(name TEXT PRIMARY KEY,metadata TEXT NOT NULL CHECK(json_valid(metadata)));
CREATE TABLE IF NOT EXISTS fields(name TEXT PRIMARY KEY,position INTEGER NOT NULL,payload TEXT NOT NULL CHECK(json_valid(payload)));
CREATE TABLE IF NOT EXISTS milestones(id TEXT PRIMARY KEY,field TEXT NOT NULL REFERENCES fields(name),duplicate_of TEXT REFERENCES milestones(id) DEFERRABLE INITIALLY DEFERRED,position INTEGER NOT NULL,payload TEXT NOT NULL CHECK(json_valid(payload)));
CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY,position INTEGER NOT NULL,payload TEXT NOT NULL CHECK(json_valid(payload)));
CREATE TABLE IF NOT EXISTS associations(id TEXT PRIMARY KEY,milestone_id TEXT NOT NULL REFERENCES milestones(id),result_id TEXT NOT NULL REFERENCES evidence(id),position INTEGER NOT NULL,payload TEXT NOT NULL CHECK(json_valid(payload)));
CREATE TABLE IF NOT EXISTS relationships(id TEXT NOT NULL,layer TEXT NOT NULL CHECK(layer IN ('tree','collection')),from_id TEXT NOT NULL REFERENCES milestones(id),to_id TEXT NOT NULL REFERENCES milestones(id),kind TEXT NOT NULL,position INTEGER NOT NULL,payload TEXT NOT NULL CHECK(json_valid(payload)),PRIMARY KEY(layer,id),CHECK(from_id<>to_id));
CREATE TABLE IF NOT EXISTS relationship_evidence(layer TEXT NOT NULL,relationship_id TEXT NOT NULL,result_id TEXT NOT NULL REFERENCES evidence(id),position INTEGER NOT NULL,PRIMARY KEY(layer,relationship_id,result_id),FOREIGN KEY(layer,relationship_id) REFERENCES relationships(layer,id));
CREATE TABLE IF NOT EXISTS branches(id TEXT PRIMARY KEY,position INTEGER NOT NULL,payload TEXT NOT NULL CHECK(json_valid(payload)));
CREATE TABLE IF NOT EXISTS branch_nodes(branch_id TEXT NOT NULL REFERENCES branches(id),milestone_id TEXT NOT NULL REFERENCES milestones(id),position INTEGER NOT NULL,PRIMARY KEY(branch_id,milestone_id));
CREATE TABLE IF NOT EXISTS submissions(id TEXT PRIMARY KEY,milestone_id TEXT REFERENCES milestones(id),state TEXT NOT NULL CHECK(state IN ('pending-source-review','dismissed')),version INTEGER NOT NULL DEFAULT 1,payload TEXT NOT NULL CHECK(json_valid(payload)),content_hash TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS review_activity(seq INTEGER PRIMARY KEY AUTOINCREMENT,submission_id TEXT REFERENCES submissions(id),action TEXT NOT NULL,payload TEXT NOT NULL CHECK(json_valid(payload)),created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS revisions(seq INTEGER PRIMARY KEY AUTOINCREMENT,scope TEXT NOT NULL,original_id TEXT NOT NULL,position INTEGER NOT NULL,payload TEXT NOT NULL CHECK(json_valid(payload)),created_at TEXT NOT NULL,UNIQUE(scope,original_id));
CREATE TABLE IF NOT EXISTS migration_snapshots(id TEXT PRIMARY KEY,storage_key TEXT NOT NULL,raw TEXT NOT NULL,report TEXT NOT NULL CHECK(json_valid(report)),created_at TEXT NOT NULL,UNIQUE(storage_key,id));
CREATE TABLE IF NOT EXISTS migration_conflicts(id TEXT PRIMARY KEY,snapshot_id TEXT NOT NULL REFERENCES migration_snapshots(id),record_id TEXT,payload TEXT NOT NULL CHECK(json_valid(payload)),reason TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS legacy_records(id TEXT PRIMARY KEY,snapshot_id TEXT NOT NULL REFERENCES migration_snapshots(id),kind TEXT NOT NULL,original_id TEXT,payload TEXT NOT NULL CHECK(json_valid(payload)),UNIQUE(kind,original_id,payload));
CREATE TABLE IF NOT EXISTS connection_reviews(milestone_id TEXT PRIMARY KEY REFERENCES milestones(id),revision_id TEXT NOT NULL,position INTEGER NOT NULL,payload TEXT NOT NULL CHECK(json_valid(payload)));
CREATE INDEX IF NOT EXISTS milestone_field ON milestones(field);
CREATE INDEX IF NOT EXISTS relationship_from ON relationships(from_id);
CREATE INDEX IF NOT EXISTS relationship_to ON relationships(to_id);
'''

class Database:
    def __init__(self,path=DEFAULT_DB,seed_dir=SEEDS):
        self.path=Path(path);self.seed_dir=Path(seed_dir);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL');db.executescript(SCHEMA)
            row=db.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()
            if row and row[0]!='1': raise RuntimeError('Unsupported database schema; restore a compatible backup')
        self.initialize()
        self.import_existing_tree_history()
    @contextmanager
    def connection(self,write=False):
        db=sqlite3.connect(self.path,timeout=10,isolation_level=None);db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA busy_timeout=10000')
        try:
            if write: db.execute('BEGIN IMMEDIATE')
            yield db
            if write: db.commit()
        except BaseException:
            if write: db.rollback()
            raise
        finally: db.close()
    def initialize(self):
        with self.connection(write=True) as db:
            if db.execute("SELECT 1 FROM settings WHERE key='initialized'").fetchone():return
            if db.execute('SELECT COUNT(*) FROM milestones').fetchone()[0]:raise RuntimeError('Uninitialized nonempty DB; refusing to seed over data')
            c,e,t=[json.loads((self.seed_dir/f'{name}.json').read_text()) for name in ['milestones','evidence','tree']]
            for name,doc,arrays in [('collection',c,['milestones','fields','evidenceAssociations','relationships','history']),('evidence',e,['results']),('tree',t,['edges','branches','connectionReviews'])]:
                db.execute('INSERT INTO documents VALUES (?,?)',(name,encode({k:v for k,v in doc.items() if k not in arrays})))
            for i,f in enumerate(c['fields']):db.execute('INSERT INTO fields VALUES (?,?,?)',(f['name'],i,encode(f)))
            for i,m in enumerate(c['milestones']):db.execute('INSERT INTO milestones VALUES (?,?,?,?,?)',(m['id'],m['field'],m['duplicateOf'],i,encode(m)))
            for i,r in enumerate(e['results']):db.execute('INSERT INTO evidence VALUES (?,?,?)',(r['id'],i,encode(r)))
            for i,a in enumerate(c['evidenceAssociations']):db.execute('INSERT INTO associations VALUES (?,?,?,?,?)',(a['id'],a['milestoneId'],a['resultId'],i,encode(a)))
            for layer,items in [('tree',t['edges']),('collection',c['relationships'])]:
                for i,r in enumerate(items):
                    db.execute('INSERT INTO relationships VALUES (?,?,?,?,?,?,?)',(r['id'],layer,r['fromId'],r['toId'],r['kind'],i,encode(r)))
                    for j,result in enumerate(r['resultIds']):db.execute('INSERT INTO relationship_evidence VALUES (?,?,?,?)',(layer,r['id'],result,j))
            for i,b in enumerate(t['branches']):
                db.execute('INSERT INTO branches VALUES (?,?,?)',(b['id'],i,encode({k:v for k,v in b.items() if k!='nodeIds'})))
                for j,id in enumerate(b['nodeIds']):db.execute('INSERT INTO branch_nodes VALUES (?,?,?)',(b['id'],id,j))
            for i,r in enumerate(t.get('connectionReviews',[])):db.execute('INSERT INTO connection_reviews VALUES (?,?,?,?)',(r['milestoneId'],t['version'],i,encode(r)))
            for i,h in enumerate(c['history']):db.execute('INSERT INTO revisions(scope,original_id,position,payload,created_at) VALUES (?,?,?,?,?)',('collection',h['id'],i,encode(h),h['date']))
            db.execute('INSERT INTO revisions(scope,original_id,position,payload,created_at) VALUES (?,?,?,?,?)',('database','sqlite-initialization',0,encode({'id':'sqlite-initialization','title':'Local SQLite storage initialized','description':'Imported original milestone collection, tree, branches, evidence and source history. Scientific content unchanged.','date':now()[:10]}),now()))
            for key,value in [('schema_version','1'),('initialized',now()),('seed_hash',digest(encode([c,e,t])))]:db.execute('INSERT INTO settings VALUES (?,?)',(key,value))
    def _items(self,db,table,where='',params=()):return [json.loads(r['payload']) for r in db.execute(f'SELECT payload FROM {table} {where} ORDER BY position',params)]
    def _submission(self,row):return {**json.loads(row['payload']),'state':row['state'],'version':row['version']}
    def _desk(self,db):return {'schemaVersion':2,'submissions':[self._submission(r) for r in db.execute('SELECT * FROM submissions ORDER BY created_at,id')]}
    def desk(self):
        with self.connection() as db:return self._desk(db)
    def bootstrap(self):
        with self.connection() as db:
            db.execute('BEGIN')
            return self._bootstrap(db)
    def _bootstrap(self,db):
        docs={r['name']:json.loads(r['metadata']) for r in db.execute('SELECT * FROM documents')}
        c,e,t=[docs[k] for k in ['collection','evidence','tree']]
        c.update(fields=self._items(db,'fields'),milestones=self._items(db,'milestones'),evidenceAssociations=self._items(db,'associations'),relationships=self._items(db,'relationships','WHERE layer=?',('collection',)),history=self._items(db,'revisions',"WHERE scope='collection'"))
        e['results']=self._items(db,'evidence');t['edges']=self._items(db,'relationships','WHERE layer=?',('tree',))
        t['branches']=self._items(db,'branches')
        if t.get('reviewSummary'):t['connectionReviews']=self._items(db,'connection_reviews')
        for b in t['branches']:b['nodeIds']=[r[0] for r in db.execute('SELECT milestone_id FROM branch_nodes WHERE branch_id=? ORDER BY position',(b['id'],))]
        from source_audit import snapshot
        return {'sourceAudit':snapshot(self,db),'collection':c,'evidence':e,'tree':t,'desk':self._desk(db),'storage':{'engine':'SQLite','schemaVersion':1},'activity':self._activity(db)}
    def _activity(self,db):return {'reviews':[dict(r)|{'payload':json.loads(r['payload'])} for r in db.execute('SELECT * FROM review_activity ORDER BY seq')],'revisions':[dict(r)|{'payload':json.loads(r['payload'])} for r in db.execute('SELECT * FROM revisions ORDER BY seq')]}
    def activity(self):
        with self.connection() as db:return self._activity(db)
    def counts(self):
        with self.connection() as db:
            counts={table:db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ['milestones','fields','evidence','associations','branches','submissions','review_activity','revisions','migration_snapshots','migration_conflicts','legacy_records','connection_reviews']}
            counts['tree_relationships']=db.execute("SELECT COUNT(*) FROM relationships WHERE layer='tree'").fetchone()[0];counts['collection_relationships']=db.execute("SELECT COUNT(*) FROM relationships WHERE layer='collection'").fetchone()[0]
            return counts
    def normalize_submission(self,value):
        from urllib.parse import urlsplit
        if not isinstance(value,dict):raise APIError(400,'Submission must be an object')
        out={}
        for key,limit in [('title',180),('url',2000),('summary',12000),('limits',12000)]:
            v=value.get(key)
            if not isinstance(v,str) or not v.strip() or len(v)>limit:raise APIError(400,f'Invalid {key}')
            out[key]=v.strip()
        try:
            url=urlsplit(out['url'])
            if url.scheme!='https' or not url.hostname or url.username or url.password or any(c.isspace() or ord(c)<32 for c in out['url']):raise ValueError()
        except ValueError:raise APIError(400,'A valid HTTPS source without credentials is required')
        id=value.get('id') or str(uuid.uuid4())
        if not isinstance(id,str) or len(id)>120 or any(ord(c)<32 for c in id):raise APIError(400,'Invalid submission ID')
        out['id']=id;created=value.get('createdAt') or now()
        if not isinstance(created,str) or len(created)>100:raise APIError(400,'Invalid submission date')
        try:datetime.fromisoformat(created.replace('Z','+00:00'))
        except (TypeError,ValueError):raise APIError(400,'Invalid submission date')
        out['createdAt']=created
        milestone=value.get('milestoneId')
        if milestone:
            if not isinstance(milestone,str):raise APIError(400,'Invalid milestone')
            out['milestoneId']=milestone
        return out
    def _create(self,db,value,state='pending-source-review',action='created'):
        item=self.normalize_submission(value)
        if item.get('milestoneId') and not db.execute('SELECT 1 FROM milestones WHERE id=?',(item['milestoneId'],)).fetchone():raise APIError(400,'Unknown original milestone')
        fingerprint=digest(encode(item));existing=db.execute('SELECT * FROM submissions WHERE id=?',(item['id'],)).fetchone()
        if existing:
            if existing['content_hash']!=fingerprint:raise APIError(409,'Submission ID already exists with different content','submission_conflict',{'existing':self._submission(existing)})
            return self._submission(existing),False
        stamp=now();db.execute('INSERT INTO submissions VALUES (?,?,?,?,?,?,?,?)',(item['id'],item.get('milestoneId'),state,1,encode(item),fingerprint,stamp,stamp))
        db.execute('INSERT INTO review_activity(submission_id,action,payload,created_at) VALUES (?,?,?,?)',(item['id'],action,encode({'state':state,'version':1,'scientificallyVerified':False}),stamp))
        return dict(item,state=state,version=1),True
    def create_submission(self,value):
        if not isinstance(value,dict) or set(value)-{'id','title','url','summary','limits','milestoneId','createdAt'}:raise APIError(400,'Unsupported submission fields; verified status cannot be supplied')
        with self.connection(write=True) as db:return self._create(db,value)[0]
    def dismiss(self,id,value):
        if not isinstance(value,dict) or set(value)!={'version','state'} or value.get('state')!='dismissed' or type(value.get('version')) is not int:raise APIError(400,'Dismissal requires the current version and dismissed state')
        with self.connection(write=True) as db:
            row=db.execute('SELECT * FROM submissions WHERE id=?',(id,)).fetchone()
            if not row:raise APIError(404,'Submission not found')
            if row['version']!=value['version']:raise APIError(409,'This suggestion changed elsewhere. Reload the latest state.','stale_version',{'current':self._submission(row)})
            if row['state']=='dismissed':return self._submission(row)
            db.execute('UPDATE submissions SET state=?,version=version+1,updated_at=? WHERE id=? AND version=?',('dismissed',now(),id,value['version']))
            db.execute('INSERT INTO review_activity(submission_id,action,payload,created_at) VALUES (?,?,?,?)',(id,'dismissed',encode({'previousVersion':value['version'],'version':value['version']+1}),now()))
            return self._submission(db.execute('SELECT * FROM submissions WHERE id=?',(id,)).fetchone())
    def backup(self,destination):
        destination=Path(destination)
        if destination.resolve()==self.path.resolve():raise ValueError('Backup must have a different path')
        destination.parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as source,closing(sqlite3.connect(destination)) as target:source.backup(target)
        return destination
    def migrate_browser(self,value):
        allowed={'techtree-evidence-desk-v2','techtree-state-v1'}
        if not isinstance(value,dict) or not isinstance(value.get('snapshots'),list) or len(value['snapshots'])>2:raise APIError(400,'Expected at most two browser storage snapshots')
        reports=[]
        with self.connection(write=True) as db:
            for snapshot in value['snapshots']:
                if not isinstance(snapshot,dict) or snapshot.get('key') not in allowed or not isinstance(snapshot.get('raw'),str) or len(snapshot['raw'])>4000000:raise APIError(400,'Invalid browser snapshot')
                key,raw=snapshot['key'],snapshot['raw'];sid=digest(key+'\n'+raw)
                existing=db.execute('SELECT report FROM migration_snapshots WHERE id=?',(sid,)).fetchone()
                if existing:
                    reports.append(dict(json.loads(existing[0]),alreadyImported=True));continue
                report={'key':key,'snapshotId':sid,'added':0,'existing':0,'legacyRecords':0,'conflicts':0,'issues':[]}
                db.execute('INSERT INTO migration_snapshots VALUES (?,?,?,?,?)',(sid,key,raw,encode(report),now()))
                def conflict(record,reason):
                    record_id=record.get('id') if isinstance(record,dict) else None
                    cid=digest(sid+encode(record)+reason)
                    db.execute('INSERT OR IGNORE INTO migration_conflicts VALUES (?,?,?,?,?,?)',(cid,sid,record_id,encode(record),reason,now()))
                    report['conflicts']+=1
                try:parsed=json.loads(raw)
                except (ValueError,TypeError):
                    report['issues'].append('Stored text is not valid JSON. Raw text retained verbatim.');parsed=None
                if parsed is not None:
                    if key=='techtree-evidence-desk-v2':
                        if not isinstance(parsed,dict) or parsed.get('schemaVersion')!=2 or not isinstance(parsed.get('submissions'),list):report['issues'].append('Unrecognized research desk structure; raw snapshot retained.')
                        else:
                            for item in parsed['submissions']:
                                try:
                                    if not isinstance(item,dict) or not item.get('id') or item.get('state') not in ['pending-source-review','dismissed']:raise APIError(400,'Invalid saved submission identity or state')
                                    saved=self.normalize_submission(item);row=db.execute('SELECT * FROM submissions WHERE id=?',(saved['id'],)).fetchone()
                                    if row:
                                        if row['content_hash']!=digest(encode(saved)) or row['state']!=item['state']:raise APIError(409,'Saved browser record conflicts with the database; neither copy was overwritten')
                                        report['existing']+=1
                                    else:
                                        self._create(db,saved,state=item['state'],action='browser-import');report['added']+=1
                                except APIError as error:conflict(item,str(error))
                    else:
                        if not isinstance(parsed,dict) or parsed.get('schemaVersion')!=1 or not isinstance(parsed.get('proposals'),list) or not isinstance(parsed.get('revisions'),list):report['issues'].append('Unrecognized earlier prototype structure; raw snapshot retained.')
                        else:
                            for kind in ['proposals','revisions']:
                                for item in parsed[kind]:
                                    if not isinstance(item,dict):conflict(item,'Legacy record must be an object; raw preserved');continue
                                    event=item.get('event');event_id=event.get('id') if isinstance(event,dict) else None
                                    original=str(item.get('id') or item.get('number') or event_id or digest(encode(item)))
                                    content=encode(item);rid=digest(kind+'\n'+original+'\n'+content)
                                    prior=db.execute('SELECT payload FROM legacy_records WHERE kind=? AND original_id=?',(kind,original)).fetchall()
                                    if any(r[0]!=content for r in prior):conflict(item,'A different historical version with this legacy identity is also retained')
                                    added=db.execute('INSERT OR IGNORE INTO legacy_records VALUES (?,?,?,?,?)',(rid,sid,kind,original,content)).rowcount
                                    report['legacyRecords']+=added
                                    if kind=='revisions' and added:
                                        db.execute('INSERT INTO revisions(scope,original_id,position,payload,created_at) VALUES (?,?,?,?,?)',('legacy-unverified',rid,int(item.get('number',0)) if isinstance(item.get('number',0),int) else 0,content,now()))
                                    if kind=='proposals' and added:
                                        db.execute('INSERT INTO review_activity(submission_id,action,payload,created_at) VALUES (NULL,?,?,?)',('legacy-unverified-import',encode({'recordId':rid,'originalState':item.get('state'),'scientificallyVerified':False}),now()))
                db.execute('UPDATE migration_snapshots SET report=? WHERE id=?',(encode(report),sid));reports.append(report)
            return {'reports':reports,'desk':self._desk(db),'conflicts':db.execute('SELECT COUNT(*) FROM migration_conflicts').fetchone()[0]}
    def migrations(self):
        with self.connection() as db:return {'snapshots':[{'id':r['id'],'key':r['storage_key'],'createdAt':r['created_at'],'report':json.loads(r['report'])} for r in db.execute('SELECT * FROM migration_snapshots ORDER BY created_at')],'conflicts':[dict(r)|{'payload':json.loads(r['payload'])} for r in db.execute('SELECT * FROM migration_conflicts ORDER BY created_at')]}
    def export(self):
        with self.connection() as db:
            db.execute('BEGIN')
            out=self._bootstrap(db)
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='source_audit_batches'").fetchone():
                out['sourceAuditBatches']=[json.loads(r['payload']) for r in db.execute('SELECT payload FROM source_audit_batches ORDER BY id')]
                out['sourceAuditHistory']=[dict(r)|{'payload':json.loads(r['payload'])} for r in db.execute('SELECT * FROM source_audit_history ORDER BY seq')]
            from source_roles import assignments
            out['sourceRoleAssignments']=assignments(db)
            out['browserSnapshots']=[dict(r) for r in db.execute('SELECT * FROM migration_snapshots ORDER BY created_at')]
            out['migrationConflicts']=[dict(r) for r in db.execute('SELECT * FROM migration_conflicts ORDER BY created_at')]
            out['legacyRecords']=[dict(r) for r in db.execute('SELECT * FROM legacy_records ORDER BY kind,original_id')]
            return out
    def import_existing_tree_history(self):
        # This record already existed in the UI before SQLite; import once, not on every seed/restart.
        with self.connection(write=True) as db:
            if db.execute("SELECT 1 FROM settings WHERE key='tree_history_imported'").fetchone():return
            record={'id':'first-directed-tree','date':'2026-10-30','title':'The technology tree becomes the landing view','description':'Connected 114 original milestones across 24 fields with 103 proposed mechanisms: 55 enabling components, 40 accelerators and eight alternative research approaches. Added directed layering, branch and field views, ancestor/descendant focus, arrow reasoning and pan/zoom/fit. All arrows are editorial hypotheses; no established required dependency is asserted.'}
            db.execute('INSERT OR IGNORE INTO revisions(scope,original_id,position,payload,created_at) VALUES (?,?,?,?,?)',('collection',record['id'],-1,encode(record),record['date']))
            db.execute("INSERT INTO settings VALUES ('tree_history_imported',?)",(now(),))
