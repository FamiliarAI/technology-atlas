"""Lossless, repeatable import of every completed ingestion field."""
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

def import_fields(base=ROOT / 'ingestion/runs/all-fields', path=DB, prefixes=FIELDS, roots=None):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    db = connect(path); initialize(db)
    changed = []; model = rewrite_model()
    try:
        with db:
            for n, prefix in enumerate(prefixes):
                folder = Path((roots or {}).get(prefix) or Path(base) / prefix)
                raw = (folder / 'final-innovations.json').read_bytes()
                value = json.loads(raw); fingerprint = sha(raw)
                if value['field']['prefix'] != prefix:
                    raise ValueError('Field ID mismatch')
                items = value['innovations']; ids = [i['id'] for i in items]
                if not items or len(ids) != len(set(ids)) or any(not i.startswith(prefix + '-') for i in ids):
                    raise ValueError('Invalid breakthrough IDs')
                for item in items:
                    for key in ['concept', 'significance', 'missing_breakthrough', 'current_state', 'completion_criteria', 'related_concepts']:
                        if not isinstance(item[key], list) or not item[key]:
                            raise ValueError('Missing final section: ' + key)
                existing = db.execute('SELECT run_hash FROM fields WHERE id=?', (prefix,)).fetchone()
                if existing and existing['run_hash'] == fingerprint:
                    if not db.execute("SELECT 1 FROM progress WHERE id LIKE 'research:%' AND breakthrough IN (SELECT id FROM breakthroughs WHERE field=?) LIMIT 1", (prefix,)).fetchone():
                        backfill_progress(db, value, model)
                    continue
                db.execute('INSERT OR IGNORE INTO runs VALUES (?,?,?,?)', (fingerprint, prefix, datetime.now(timezone.utc).isoformat(), raw.decode()))
                db.execute('INSERT INTO fields VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,color=excluded.color,run_hash=excluded.run_hash', (prefix, value['field']['field'], color(prefix, n), fingerprint))
                # Research-derived progress follows the current run; progress added later is kept.
                db.execute("DELETE FROM progress WHERE id LIKE 'research:%' AND breakthrough IN (SELECT id FROM breakthroughs WHERE field=?)", (prefix,))
                db.execute('DELETE FROM breakthroughs WHERE field=?', (prefix,))
                for item in items:
                    db.execute('INSERT INTO breakthroughs VALUES (?,?,?)', (item['id'], prefix, json.dumps(item)))
                    for source in item.get('sources', []):
                        for a in source.get('artifacts', []):
                            p = Path(a.get('absolute_path') or folder / a['path']).resolve()
                            if not p.is_relative_to(folder.resolve()) or not p.is_file() or sha(p.read_bytes()) != a['sha256']:
                                raise ValueError('Source artifact is missing, outside field, or changed: ' + str(p))
                            db.execute('INSERT OR IGNORE INTO assets VALUES (?,?,?)', (a['sha256'], str(p), a['sha256']))
                    for kind, loc in item.get('provenance', {}).items():
                        p = Path(loc).resolve()
                        if p.is_relative_to(folder.resolve()) and p.is_file():
                            db.execute('INSERT OR REPLACE INTO documents VALUES (?,?,?)', (item['id'] + ':' + kind, str(p), sha(p.read_bytes())))
                backfill_progress(db, value, model)
                changed.append(prefix)
    finally:
        db.close()
    return changed

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
    roots = completed_fields()
    print('Imported:', ', '.join(import_fields(prefixes=sorted(roots), roots=roots)) or 'already current')
