"""The SQLite view, rebuilt from atlas/core/: python3 -m atlas.store."""
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'atlas/data/atlas.sqlite3'
MANIFEST = ROOT / 'ingestion/runs/all-fields/batch.json'
CONFIG = ROOT / 'ingestion/config.json'
CORE = ROOT / 'atlas/core'
SOURCES = [ROOT / 'ingestion/runs', ROOT / 'atlas/data/added']
FIELDS = ['SWE', 'CSC', 'CPE', 'ROB']
COLORS = dict(zip(FIELDS, ['#c5ed91', '#97b9ff', '#e8b77d', '#d8a6e4']))

def color(prefix, n):
    # Prototype colors stay fixed; other fields step round the hue circle.
    return COLORS.get(prefix) or f'hsl({(n * 137.5) % 360:.0f} 60% 74%)'

def completed_fields(manifest=MANIFEST):
    """Prefix -> field folder for every field the ingestion batch marks complete."""
    fields = json.loads(Path(manifest).read_text())['fields']
    return {f['prefix']: Path(f['root']) for f in fields if f.get('status') == 'complete'}

def connect(path=DB):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    return db

def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS runs (hash TEXT PRIMARY KEY, field TEXT NOT NULL, imported_at TEXT NOT NULL, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS fields (id TEXT PRIMARY KEY, name TEXT NOT NULL, color TEXT NOT NULL, run_hash TEXT NOT NULL REFERENCES runs(hash));
    CREATE TABLE IF NOT EXISTS breakthroughs (id TEXT PRIMARY KEY, field TEXT NOT NULL REFERENCES fields(id), payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY, path TEXT NOT NULL, hash TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, path TEXT NOT NULL, hash TEXT NOT NULL);
    -- One row per source per milestone it bears on. criterion and verdict stay NULL until judged.
    CREATE TABLE IF NOT EXISTS progress (id TEXT PRIMARY KEY, breakthrough TEXT NOT NULL, criterion INTEGER, url TEXT NOT NULL, asset TEXT, source_date TEXT, verdict TEXT CHECK (verdict IN ('advances','meets','contradicts')), quote TEXT NOT NULL, model TEXT NOT NULL, added_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS progress_breakthrough ON progress(breakthrough);
    ''')
    db.execute('PRAGMA foreign_keys = ON')

def sha(data):
    return hashlib.sha256(data).hexdigest()

def rewrite_model(config=CONFIG):
    # Final records are written by the review model's post-review rewrite.
    try: return json.loads(Path(config).read_text())['review']['model']
    except (OSError, KeyError, ValueError): return 'unknown'

def backfill_progress(db, value, model):
    """Copy each current-state paragraph's cited sources into progress, with no criterion or verdict."""
    for item in value['innovations']:
        saved = {s['url']: next((a['sha256'] for a in s.get('artifacts', []) if a.get('kind') == 'source'), None) or next((a['sha256'] for a in s.get('artifacts', [])), None) for s in item.get('sources', [])}
        for n, paragraph in enumerate(item['current_state']):
            for url in paragraph.get('source_urls', []):
                db.execute('INSERT OR REPLACE INTO progress VALUES (?,?,?,?,?,?,?,?,?,?)', (f"research:{item['id']}:{n}:{url}", item['id'], None, url, saved.get(url), None, None, paragraph['text'], model, value.get('created_at') or datetime.now(timezone.utc).isoformat()))

def resolver(roots=SOURCES):
    """sha256 -> saved copy, for files named <sha256>.<ext> in any sources/ folder under roots."""
    found = {}
    for root in roots:
        for p in sorted(Path(root).glob('**/sources/*')):
            if p.is_file(): found.setdefault(p.stem, p.resolve())
    return found

def rebuild(core=CORE, path=DB, roots=SOURCES):
    """Build the database afresh from atlas/core/ and swap it in. Returns row counts and missing copies."""
    from . import core as records  # core imports this module
    data = records.load(core); problems = records.check(data)
    if problems:
        raise ValueError('atlas/core check failed:\n' + '\n'.join(problems))
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.rebuild'); temp.unlink(missing_ok=True)
    files = resolver(roots); model = rewrite_model(); missing = 0; criteria = {}
    db = connect(temp)
    try:
        with db:
            initialize(db)
            for prefix, field in sorted(data['fields'].items()):
                run = field['imported_from']
                db.execute('INSERT INTO runs VALUES (?,?,?,?)', (run['run_hash'], prefix, run['imported_at'], (Path(core) / prefix / 'field.json').read_text(encoding='utf-8')))
                db.execute('INSERT INTO fields VALUES (?,?,?,?)', (prefix, field['name'], field['color'], run['run_hash']))
                items = []
                for identifier, item in sorted(data['breakthroughs'].items()):
                    if item['field'] != prefix or item.get('status') == 'retired': continue
                    item = dict(item, sources=[{k: s[k] for k in ('url', 'title', 'status')} | {'artifacts': s['copies']} for s in map(data['sources'].get, item.get('sources', []))])
                    db.execute('INSERT INTO breakthroughs VALUES (?,?,?)', (identifier, prefix, json.dumps(item)))
                    items.append(item); criteria[identifier] = {c['id']: n for n, c in enumerate(item['completion_criteria'], 1)}
                    for kind, loc in item.get('provenance', {}).items():
                        p = (ROOT / loc).resolve()
                        if p.is_relative_to(ROOT) and p.is_file():
                            db.execute('INSERT OR REPLACE INTO documents VALUES (?,?,?)', (identifier + ':' + kind, str(p), sha(p.read_bytes())))
                backfill_progress(db, {'innovations': items, 'created_at': field.get('created_at') or run['imported_at']}, model)
            for source in data['sources'].values():
                for copy in source['copies']:
                    p = files.get(copy['sha256'])
                    if p is None:
                        missing += 1; continue
                    if sha(p.read_bytes()) != copy['sha256']:
                        raise ValueError('Saved copy changed: ' + str(p))
                    db.execute('INSERT OR IGNORE INTO assets VALUES (?,?,?)', (copy['sha256'], str(p), copy['sha256']))
            for row in data['progress']:
                if row['breakthrough'] not in criteria: continue  # retired
                n = criteria[row['breakthrough']][row['milestone']]
                db.execute('INSERT OR REPLACE INTO progress VALUES (?,?,?,?,?,?,?,?,?,?)', (f"added:{row.get('copy')}:{row['breakthrough']}:{n}", row['breakthrough'], n, row['url'], row.get('copy'), row.get('source_date'), row['verdict'], row['quote'], row['by'], row['added_at']))
            counts = {t: db.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ['runs', 'fields', 'breakthroughs', 'assets', 'documents', 'progress']}
        db.close()
        temp.replace(path)
    except BaseException:
        db.close(); temp.unlink(missing_ok=True)
        raise
    return counts | {'missing': missing}

def progress(db, identifier, criteria):
    rows = [dict(r) for r in db.execute('SELECT * FROM progress WHERE breakthrough=? ORDER BY criterion IS NULL, criterion, added_at, id', (identifier,))]
    status = []
    for n in range(1, criteria + 1):
        verdicts = {r['verdict'] for r in rows if r['criterion'] == n}
        status.append('met' if 'meets' in verdicts else 'in_progress' if 'advances' in verdicts else 'none')
    return rows, status

def progress_summary(db):
    """Per breakthrough: milestone status list and progress row count, for the tree."""
    out = {}
    for r in db.execute('SELECT id, payload FROM breakthroughs'):
        rows, status = progress(db, r['id'], len(json.loads(r['payload'])['completion_criteria']))
        out[r['id']] = {'status': status, 'count': len(rows)}
    return out

def catalog(db):
    counts = dict(db.execute('SELECT breakthrough, COUNT(*) FROM progress GROUP BY breakthrough').fetchall())
    fields = [dict(r) for r in db.execute('SELECT * FROM fields ORDER BY name')]
    items = []
    for r in db.execute('SELECT * FROM breakthroughs ORDER BY id'):
        i = json.loads(r['payload'])
        items.append({'id': i['id'], 'field': r['field'], 'title': i['title'], 'summary': i['concept'][0]['text'], 'source_count': len(i.get('sources', [])), 'milestone_count': len(i['completion_criteria']), 'progress_count': counts.get(i['id'], 0), 'issue_count': len(i.get('unresolved_issues', [])), 'prerequisites': [l['id'] for l in i.get('prerequisites', [])], 'search_text': ' '.join(p['text'] for key in ['concept','significance','missing_breakthrough','current_state','completion_criteria'] for p in i[key])})
    known = {i['id'] for i in items}; edges = {}
    for r in db.execute('SELECT id,payload FROM breakthroughs'):
        for p in json.loads(r['payload'])['related_concepts']:
            for target in set(re.findall(r'\b[A-Z]{2,6}-\d{2}\b', p['text'])) & known - {r['id']}:
                key = tuple(sorted((r['id'], target)))
                edges.setdefault(key, []).append({'from': r['id'], 'text': p['text'], 'source_urls': p.get('source_urls', [])})
    return {'fields': fields, 'breakthroughs': items, 'connections': [{'source': a, 'target': b, 'kind': 'discussed together', 'explanations': notes} for (a,b), notes in edges.items()], 'as_of': '2026-11-01'}

if __name__ == '__main__':
    counts = rebuild()
    print(', '.join(f'{v} {k}' for k, v in counts.items() if k != 'missing') + f"; {counts['missing']} saved copies missing (skipped)")
