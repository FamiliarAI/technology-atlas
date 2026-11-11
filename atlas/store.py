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
    return {
        field['prefix']: Path(field['root'])
        for field in fields
        if field.get('status') == 'complete'
    }


def connect(path=DB):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    return db


def initialize(db):
    db.executescript(
        (
            '\n'
            '    CREATE TABLE IF NOT EXISTS fields (id TEXT PRIMARY KEY, name TEXT NOT '
            'NULL, color TEXT NOT NULL);\n'
            '    CREATE TABLE IF NOT EXISTS breakthroughs (id TEXT PRIMARY KEY, field TEXT '
            'NOT NULL REFERENCES fields(id), payload TEXT NOT NULL);\n'
            '    CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY, path TEXT NOT '
            'NULL, hash TEXT NOT NULL);\n'
            '    CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, path TEXT NOT '
            'NULL, hash TEXT NOT NULL);\n'
            '    -- One row per source per milestone it bears on. criterion and verdict '
            'stay NULL until judged.\n'
            '    CREATE TABLE IF NOT EXISTS progress (id TEXT PRIMARY KEY, breakthrough '
            'TEXT NOT NULL, criterion INTEGER, url TEXT NOT NULL, asset TEXT, source_date '
            "TEXT, verdict TEXT CHECK (verdict IN ('advances','meets','contradicts')), "
            'quote TEXT NOT NULL, model TEXT NOT NULL, added_at TEXT NOT NULL);\n'
            '    CREATE INDEX IF NOT EXISTS progress_breakthrough ON '
            'progress(breakthrough);\n'
            '    '
        )
    )
    db.execute('PRAGMA foreign_keys = ON')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rewrite_model(config=CONFIG):
    # Final records are written by the review model's post-review rewrite.
    try:
        return json.loads(Path(config).read_text())['review']['model']
    except (OSError, KeyError, ValueError):
        return 'unknown'


def backfill_progress(db, value, model):
    (
        """Copy each current-state paragraph's cited sources into progress, with no """
        """criterion or verdict."""
    )
    for item in value['innovations']:
        saved = {}
        for source in item.get('sources', []):
            artifacts = source.get('artifacts', [])
            source_hash = next(
                (artifact['sha256'] for artifact in artifacts if artifact.get('kind') == 'source'),
                None,
            )
            if not source_hash:
                source_hash = next((artifact['sha256'] for artifact in artifacts), None)
            saved[source['url']] = source_hash
        for paragraph_index, paragraph in enumerate(item['current_state']):
            for url in paragraph.get('source_urls', []):
                db.execute(
                    'INSERT OR REPLACE INTO progress VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (
                        f'research:{item["id"]}:{paragraph_index}:{url}',
                        item['id'],
                        None,
                        url,
                        saved.get(url),
                        None,
                        None,
                        paragraph['text'],
                        model,
                        value.get('created_at') or datetime.now(timezone.utc).isoformat(),
                    ),
                )


def resolver(roots=SOURCES):
    """sha256 -> saved copy, for files named <sha256>.<ext> in any sources/ folder under roots."""
    found = {}
    for root in roots:
        for path in sorted(Path(root).glob('**/sources/*')):
            if path.is_file():
                found.setdefault(path.stem, path.resolve())
    return found


def rebuild(core=CORE, path=DB, roots=SOURCES):
    (
        """Build the database afresh from atlas/core/ and swap it in. Returns row """
        """counts and missing copies."""
    )
    from . import core as records  # core imports this module

    data = records.load(core)
    problems = records.check(data)
    if problems:
        raise ValueError('atlas/core check failed:\n' + '\n'.join(problems))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.rebuild')
    temp.unlink(missing_ok=True)
    files = resolver(roots)
    model = rewrite_model()
    missing = 0
    criteria = {}
    db = connect(temp)
    try:
        with db:
            initialize(db)
            for prefix, field in sorted(data['fields'].items()):
                db.execute(
                    'INSERT INTO fields VALUES (?,?,?)',
                    (prefix, field['name'], field['color']),
                )
                items = []
                for identifier, item in sorted(data['breakthroughs'].items()):
                    if item['field'] != prefix or item.get('status') == 'retired':
                        continue
                    sources = []
                    for source in map(data['sources'].get, item.get('sources', [])):
                        summary = {key: source[key] for key in ('url', 'title', 'status')}
                        sources.append(summary | {'artifacts': source['copies']})
                    item = dict(item, sources=sources)
                    db.execute(
                        'INSERT INTO breakthroughs VALUES (?,?,?)',
                        (identifier, prefix, json.dumps(item)),
                    )
                    items.append(item)
                    criteria[identifier] = {
                        criterion['id']: criterion_number
                        for criterion_number, criterion in enumerate(item['completion_criteria'], 1)
                    }
                    for kind, location in item.get('provenance', {}).items():
                        document_path = (ROOT / location).resolve()
                        if document_path.is_relative_to(ROOT) and document_path.is_file():
                            db.execute(
                                'INSERT OR REPLACE INTO documents VALUES (?,?,?)',
                                (
                                    identifier + ':' + kind,
                                    str(document_path),
                                    sha(document_path.read_bytes()),
                                ),
                            )
                backfill_progress(
                    db, {'innovations': items, 'created_at': field.get('created_at')}, model
                )
            for source in data['sources'].values():
                for copy in source['copies']:
                    document_path = files.get(copy['sha256'])
                    if document_path is None:
                        missing += 1
                        continue
                    if sha(document_path.read_bytes()) != copy['sha256']:
                        raise ValueError('Saved copy changed: ' + str(document_path))
                    db.execute(
                        'INSERT OR IGNORE INTO assets VALUES (?,?,?)',
                        (copy['sha256'], str(document_path), copy['sha256']),
                    )
            for row in data['progress']:
                if row['breakthrough'] not in criteria:
                    continue  # retired
                criterion_number = criteria[row['breakthrough']][row['milestone']]
                db.execute(
                    'INSERT OR REPLACE INTO progress VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (
                        f'added:{row.get("copy")}:{row["breakthrough"]}:{criterion_number}',
                        row['breakthrough'],
                        criterion_number,
                        row['url'],
                        row.get('copy'),
                        row.get('source_date'),
                        row['verdict'],
                        row['quote'],
                        row['by'],
                        row['added_at'],
                    ),
                )
            counts = {
                table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                for table in ['fields', 'breakthroughs', 'assets', 'documents', 'progress']
            }
        db.close()
        temp.replace(path)
    except BaseException:
        db.close()
        temp.unlink(missing_ok=True)
        raise
    return counts | {'missing': missing}


def progress(db, identifier, criteria):
    rows = [
        dict(row)
        for row in db.execute(
            (
                'SELECT * FROM progress WHERE breakthrough=? ORDER BY criterion IS NULL, '
                'criterion, added_at, id'
            ),
            (identifier,),
        )
    ]
    status = []
    for criterion_number in range(1, criteria + 1):
        verdicts = {row['verdict'] for row in rows if row['criterion'] == criterion_number}
        status.append(
            'met' if 'meets' in verdicts else 'in_progress' if 'advances' in verdicts else 'none'
        )
    return rows, status


def progress_summary(db):
    """Per breakthrough: milestone status list and progress row count, for the tree."""
    out = {}
    for row in db.execute('SELECT id, payload FROM breakthroughs'):
        rows, status = progress(
            db, row['id'], len(json.loads(row['payload'])['completion_criteria'])
        )
        out[row['id']] = {'status': status, 'count': len(rows)}
    return out


def catalog(db):
    counts = dict(
        db.execute('SELECT breakthrough, COUNT(*) FROM progress GROUP BY breakthrough').fetchall()
    )
    fields = [dict(row) for row in db.execute('SELECT * FROM fields ORDER BY name')]
    # Judged rows only: they give milestone status, the latest movement and recent changes.
    judged = [
        dict(row)
        for row in db.execute(
            'SELECT breakthrough, criterion, verdict, url, source_date, quote, added_at '
            'FROM progress WHERE verdict IS NOT NULL ORDER BY added_at DESC, id'
        )
    ]
    items = []
    for row in db.execute('SELECT * FROM breakthroughs ORDER BY id'):
        item = json.loads(row['payload'])
        mine = [entry for entry in judged if entry['breakthrough'] == item['id']]
        milestones = []
        for criterion_number, criterion in enumerate(item['completion_criteria'], 1):
            verdicts = {
                entry['verdict'] for entry in mine if entry['criterion'] == criterion_number
            }
            status = (
                'met'
                if 'meets' in verdicts
                else 'in_progress'
                if 'advances' in verdicts
                else 'none'
            )
            milestones.append(
                {'id': criterion['id'], 'label': criterion.get('label'), 'status': status}
            )
        items.append(
            {
                'id': item['id'],
                'field': row['field'],
                'title': item['title'],
                'summary': item['concept'][0]['text'],
                'source_count': len(item.get('sources', [])),
                'milestone_count': len(item['completion_criteria']),
                'progress_count': counts.get(item['id'], 0),
                'issue_count': len(item.get('unresolved_issues', [])),
                'prerequisites': [link['id'] for link in item.get('prerequisites', [])],
                'milestones': milestones,
                'moved_at': max((entry['added_at'] for entry in mine), default=None),
                'search_text': ' '.join(
                    paragraph['text']
                    for key in [
                        'concept',
                        'significance',
                        'missing_breakthrough',
                        'current_state',
                        'completion_criteria',
                    ]
                    for paragraph in item[key]
                ),
            }
        )
    known = {item['id'] for item in items}
    edges = {}
    for row in db.execute('SELECT id,payload FROM breakthroughs'):
        for paragraph in json.loads(row['payload'])['related_concepts']:
            for target in set(re.findall(r'\b[A-Z]{2,6}-\d{2}\b', paragraph['text'])) & known - {
                row['id']
            }:
                key = tuple(sorted((row['id'], target)))
                edges.setdefault(key, []).append(
                    {
                        'from': row['id'],
                        'text': paragraph['text'],
                        'source_urls': paragraph.get('source_urls', []),
                    }
                )
    return {
        'fields': fields,
        'breakthroughs': items,
        'connections': [
            {
                'source': source_id,
                'target': target_id,
                'kind': 'discussed together',
                'explanations': notes,
            }
            for (source_id, target_id), notes in edges.items()
        ],
        'recent': judged[:12],
        'as_of': '2026-11-01',
    }


if __name__ == '__main__':
    counts = rebuild()
    print(
        ', '.join(f'{count} {table}' for table, count in counts.items() if table != 'missing')
        + f'; {counts["missing"]} saved copies missing (skipped)'
    )
