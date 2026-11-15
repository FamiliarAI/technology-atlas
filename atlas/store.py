"""The SQLite view, rebuilt from atlas/core/: python3 -m atlas.store."""

import hashlib
import json
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
            'NULL, color TEXT NOT NULL, boundaries TEXT, withheld TEXT);\n'
            '    CREATE TABLE IF NOT EXISTS breakthroughs (id TEXT PRIMARY KEY, field TEXT '
            'NOT NULL REFERENCES fields(id), payload TEXT NOT NULL);\n'
            '    CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY, path TEXT NOT '
            'NULL, hash TEXT NOT NULL);\n'
            '    CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, path TEXT NOT '
            'NULL, hash TEXT NOT NULL);\n'
            '    -- One row per source per milestone it bears on. criterion and verdict '
            'stay NULL until judged.\n'
            '    -- A judged row with criterion NULL bears on the breakthrough as a whole.\n'
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
                    'INSERT INTO fields VALUES (?,?,?,?,?)',
                    (
                        prefix,
                        field['name'],
                        field['color'],
                        field.get('boundaries'),
                        json.dumps(field.get('withheld') or []),
                    ),
                )
                items = []
                for identifier, item in sorted(data['breakthroughs'].items()):
                    if item['field'] != prefix or item.get('status') == 'retired':
                        continue
                    sources = []
                    for source in map(data['sources'].get, item.get('sources', [])):
                        summary = {key: source[key] for key in ('url', 'title', 'status')}
                        sources.append(summary | {'artifacts': source['copies']})
                    # Papers that only have judged rows: listed apart so source counts keep
                    # meaning the record's citations.
                    cited = set(item.get('sources', []))
                    judged = []
                    for url in dict.fromkeys(
                        row['url'] for row in data['progress'] if row['breakthrough'] == identifier
                    ):
                        if url not in cited:
                            source = data['sources'][url]
                            judged.append({key: source[key] for key in ('url', 'title', 'status')})
                    item = dict(item, sources=sources, judged_sources=judged)
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
                # A row with no milestone bears on the breakthrough as a whole: criterion NULL,
                # and 0 in its ID.
                criterion_number = None
                if row['milestone'] is not None:
                    criterion_number = criteria[row['breakthrough']][row['milestone']]
                db.execute(
                    'INSERT OR REPLACE INTO progress VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (
                        f'added:{row.get("copy")}:{row["breakthrough"]}:{criterion_number or 0}',
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
    """A breakthrough's rows: milestone rows in milestone order, then whole-breakthrough
    judgements, then research citations. Also the status of each of its criteria milestones."""
    rows = [
        dict(row)
        for row in db.execute(
            (
                'SELECT * FROM progress WHERE breakthrough=? ORDER BY criterion IS NULL, '
                'criterion, verdict IS NULL, added_at, id'
            ),
            (identifier,),
        )
    ]
    status = []
    for criterion_number in range(1, criteria + 1):
        verdicts = {row['verdict'] for row in rows if row['criterion'] == criterion_number}
        status.append(status_of(verdicts))
    return rows, status


def overall(rows):
    """Steps toward the breakthrough as a whole: `advances` rows with no milestone."""
    return sum(1 for row in rows if row['criterion'] is None and row['verdict'] == 'advances')


def progress_summary(db):
    """Per breakthrough: milestone status list, whole-breakthrough steps and row count."""
    out = {}
    for row in db.execute('SELECT id, payload FROM breakthroughs'):
        rows, status = progress(
            db, row['id'], len(json.loads(row['payload'])['completion_criteria'])
        )
        out[row['id']] = {'status': status, 'overall': overall(rows), 'count': len(rows)}
    return out


# The site's data contract (docs/plans/2026-11-11-site-design.md, Technical): the same files are
# served by atlas.server under /data/ and written to disk by atlas.export.
AS_OF = '2026-11-01'

# Eight regions of neighbouring disciplines, in sky order. A constant, not core data.
REGIONS = {
    'Computing and Information': ['CSC', 'SWE', 'CPE', 'MLC', 'HCI', 'CRY', 'QUA'],
    'Mathematics and Physics': ['MAT', 'PHY', 'OPT', 'THR'],
    'Chemistry and Materials': ['CHM', 'CHE', 'CRX', 'CRM', 'MAS', 'MET', 'RHE'],
    'Engineering and Energy': [
        'AER',
        'BME',
        'CIV',
        'ELE',
        'IND',
        'MEC',
        'MNE',
        'NUC',
        'PET',
        'PWR',
        'ROB',
        'STR',
    ],
    'Earth and Space': ['AST', 'GEO', 'OCE', 'ROC', 'AGR'],
    'Life Sciences': ['BIO', 'BCH', 'BIF', 'BOT', 'GEN', 'IMM', 'LON', 'MIC', 'NEU', 'VIR', 'ZOO'],
    'Medicine': [
        'ANS',
        'CAR',
        'CLM',
        'DER',
        'EMR',
        'END',
        'INF',
        'NEP',
        'NRL',
        'OBG',
        'ONC',
        'OPH',
        'ORT',
        'PED',
        'PHA',
        'SUR',
    ],
    'Mind and Society': ['ACT', 'ECO', 'FIN', 'PSY'],
}
REGION = {field: region for region, fields in REGIONS.items() for field in fields}
DEFAULT_REGION = 'Engineering and Energy'
STATUSES = ['none', 'in_progress', 'met']
SUMMARY_CUT = 160
# The research prompt's instruction, stored as most fields' `boundaries` after "<Name>". It is
# not a scope a reader needs, so the field file carries an empty string instead.
RESEARCH_SCOPE = (
    ': fundamental discoveries and enabling technologies within this field. Include '
    'cross-field consequences where the central advance belongs to this field; exclude '
    'routine incremental optimization. Use the historical breakthroughs in the prompt to '
    'calibrate revolutionary impact.'
)


def region(field):
    return REGION.get(field, DEFAULT_REGION)


def cut(text, limit=SUMMARY_CUT):
    """Text shortened at a word boundary to about limit characters."""
    text = ' '.join(text.split())
    if len(text) <= limit:
        return text
    head = text[: limit + 1].rsplit(' ', 1)[0].rstrip(' ,;:.-–—')
    return head + '…'


def status_of(verdicts):
    if 'meets' in verdicts:
        return 'met'
    if 'advances' in verdicts:
        return 'in_progress'
    return 'none'


def page_milestones(page):
    """A page's active milestones with a status each, by the rule of Page.jsx progress():
    every result counts, a claim too (owner, November 15, 2026); met if any is met, in
    progress if any is partial."""
    order = page.get('milestone_order') or [m['id'] for m in page['milestones']]
    known = {m['id']: m for m in page['milestones'] if m.get('status', 'active') == 'active'}
    out = []
    for identifier in order:
        if identifier not in known:
            continue
        verdicts = {
            row['verdict'] for row in page.get('results', []) if row['milestone'] == identifier
        }
        status = 'met' if 'met' in verdicts else 'in_progress' if verdicts else 'none'
        out.append({'id': identifier, 'label': known[identifier]['title'], 'status': status})
    return out


def published(item):
    """The owner published this breakthrough's page (atlas.review)."""
    return bool(item.get('page')) and (item.get('review') or {}).get('state') == 'published'


def site_view(db, public=False):
    """Everything the data files are built from, read once. public: only published
    breakthroughs, and only the fields that have one (the public export)."""
    view = _site_view(db)
    if public:
        view['items'] = {key: item for key, item in view['items'].items() if published(item)}
        fields = {item['field'] for item in view['items'].values()}
        view['fields'] = {key: field for key, field in view['fields'].items() if key in fields}
        view['judged'] = [row for row in view['judged'] if row['breakthrough'] in view['items']]
    return view


def _site_view(db):
    fields = {row['id']: dict(row) for row in db.execute('SELECT * FROM fields ORDER BY id')}
    for field in fields.values():
        # Concepts a provider refused to review: {id, title, stage, reason}. A database built
        # before the column existed has none recorded.
        field['withheld'] = json.loads(field.get('withheld') or '[]')
    counts = dict(
        db.execute('SELECT breakthrough, COUNT(*) FROM progress GROUP BY breakthrough').fetchall()
    )
    # Judged rows only: they give milestone status, the latest movement and recent changes.
    judged = [
        dict(row)
        for row in db.execute(
            'SELECT breakthrough, criterion, verdict, url, source_date, quote, added_at '
            'FROM progress WHERE verdict IS NOT NULL ORDER BY added_at DESC, id'
        )
    ]
    mine = {}
    for row in judged:
        mine.setdefault(row['breakthrough'], []).append(row)
    items = {}
    for row in db.execute('SELECT id, field, payload FROM breakthroughs ORDER BY id'):
        item = json.loads(row['payload'])
        if published(item):
            # The published page names the breakthrough everywhere: lists, search, the chart.
            item['title'] = item['page']['title']
        rows = mine.get(row['id'], [])
        milestones = []
        for number, criterion in enumerate(item['completion_criteria'], 1):
            verdicts = {entry['verdict'] for entry in rows if entry['criterion'] == number}
            milestones.append(
                {
                    'id': criterion['id'],
                    'label': criterion.get('label'),
                    'status': status_of(verdicts),
                }
            )
        item['field'] = row['field']
        item['milestones'] = milestones
        item['overall'] = overall(rows)
        if published(item):
            # Lists and the chart describe a published breakthrough by its page: its
            # definition, its active milestones, and marks from its confirmed results only.
            page = item['page']
            item['concept'] = [{'text': page['definition'], 'source_urls': []}]
            item['milestones'] = page_milestones(page)
            item['overall'] = 0
            # Its completion test met (a claim counts, as on the page): the star reads complete.
            item['complete'] = any(
                row['milestone'] == 'completion' and row['verdict'] == 'met'
                for row in page.get('results', [])
            )
            if item['complete'] and page.get('completed'):
                done = page['completed']
                item['completed_on'] = {'date': done['date'], 'precision': done['precision']}
        # Any judged row counts as movement, including one about the breakthrough as a whole.
        item['moved_at'] = max((entry['added_at'] for entry in rows), default=None)
        item['progress_count'] = counts.get(row['id'], 0)
        items[row['id']] = item
    return {'fields': fields, 'items': items, 'judged': judged}


def milestone_id(item, criterion):
    """The stable milestone ID at a 1-based criterion position, or None for the whole."""
    if criterion and criterion <= len(item.get('milestones', [])):
        return item['milestones'][criterion - 1]['id']
    return None


def catalog(db, view=None):
    """data/catalog.json: what every page and the chart need, and no more."""
    view = view or site_view(db)
    items = view['items']
    fields = []
    for prefix, field in sorted(view['fields'].items(), key=lambda pair: pair[1]['name']):
        mine = [item for item in items.values() if item['field'] == prefix]
        statuses = [milestone['status'] for item in mine for milestone in item['milestones']]
        fields.append(
            {
                'id': prefix,
                'name': field['name'],
                'region': region(prefix),
                'breakthroughs': len(mine),
                'milestones': {status: statuses.count(status) for status in STATUSES},
            }
        )
    breakthroughs = [
        {
            'id': identifier,
            'field': item['field'],
            'title': item['title'],
            'milestones': [milestone['status'] for milestone in item['milestones']],
            'overall': item['overall'],
            'moved_at': item['moved_at'],
            # Only when true, to keep the catalog small: its completion test is met, and when.
            **({'complete': True} if item.get('complete') else {}),
            **({'completed': item['completed_on']} if item.get('completed_on') else {}),
        }
        for identifier, item in sorted(items.items())
    ]
    recent = []
    for row in view['judged'][:12]:
        item = items.get(row['breakthrough'], {})
        milestones = item.get('milestones', [])
        label = None
        if row['criterion'] and row['criterion'] <= len(milestones):
            label = milestones[row['criterion'] - 1]['label']
        recent.append(row | {'milestone': milestone_id(item, row['criterion']), 'label': label})
    withheld = [
        {'id': entry['id'], 'title': entry['title'], 'field': prefix}
        for prefix, field in sorted(view['fields'].items())
        for entry in field['withheld']
    ]
    return {
        'as_of': AS_OF,
        'regions': list(REGIONS),
        'fields': fields,
        'breakthroughs': breakthroughs,
        'recent': recent,
        'withheld': withheld,
    }


def scope(boundaries):
    """A field's reader-facing scope: empty when it is only the research prompt's instruction."""
    text = boundaries or ''
    return '' if text.endswith(RESEARCH_SCOPE) else text


def field_data(db, prefix, view=None):
    """data/field/<ID>.json: one field's scope and its breakthroughs, or None."""
    view = view or site_view(db)
    field = view['fields'].get(prefix)
    if field is None:
        return None
    breakthroughs = [
        {
            'id': identifier,
            'title': item['title'],
            'summary': item['concept'][0]['text'] if item['concept'] else '',
            'milestones': item['milestones'],
            'source_count': len(item.get('sources', [])),
            'progress_count': item['progress_count'],
            'issue_count': len(item.get('unresolved_issues', [])),
            'moved_at': item['moved_at'],
        }
        for identifier, item in sorted(view['items'].items())
        if item['field'] == prefix
    ]
    return {
        'id': prefix,
        'name': field['name'],
        'region': region(prefix),
        'boundaries': scope(field.get('boundaries')),
        'as_of': AS_OF,
        'breakthroughs': breakthroughs,
        'withheld': [
            {key: entry.get(key) for key in ('id', 'title', 'stage', 'reason')}
            for entry in field['withheld']
        ],
    }


def breakthrough_data(db, identifier, view=None):
    """data/b/<ID>.json: one breakthrough's record, sources as links, and its evidence."""
    view = view or site_view(db)
    item = view['items'].get(identifier)
    if item is None:
        return None
    sections = [
        'concept',
        'significance',
        'missing_breakthrough',
        'current_state',
        'completion_criteria',
        'related_concepts',
        'unresolved_issues',
        'change_log',
    ]
    rows, _ = progress(db, identifier, len(item['completion_criteria']))
    # Saved-copy hashes stay out: the site links to originals only. milestone is the stable ID,
    # or None for a judgement about the breakthrough as a whole (and for research citations).
    keys = ['url', 'source_date', 'verdict', 'quote', 'model', 'added_at']
    evidence = [
        {
            'criterion': row['criterion'],
            'milestone': milestone_id(item, row['criterion']),
            **{key: row[key] for key in keys},
        }
        for row in rows
    ]
    field = view['fields'][item['field']]
    sources = [
        {'url': source['url'], 'title': source.get('title'), 'status': source.get('status')}
        for source in item.get('sources', []) + item.get('judged_sources', [])
    ]
    out = {
        'id': identifier,
        'field': item['field'],
        'field_name': field['name'],
        'region': region(item['field']),
        'title': item['title'],
        'status': item.get('status'),
        'models': item.get('models', {}),
        **{key: item.get(key, []) for key in sections},
        'milestones': item['milestones'],
        'moved_at': item['moved_at'],
        # Links to the originals only: no saved copies, no local paths. Papers that only have
        # judged rows follow the record's own sources.
        'sources': sources,
        'progress': evidence,
    }
    if item.get('brief'):
        # The reader's version; each source carries the title and status of its listed source.
        known = {source['url']: source for source in sources}
        brief = dict(item['brief'])
        brief['sources'] = [
            entry
            | {
                'title': known.get(entry['url'], {}).get('title'),
                'status': known.get(entry['url'], {}).get('status'),
            }
            for entry in brief['sources']
        ]
        out['brief'] = brief
    if item.get('page'):
        # The breakthrough page entry (atlas.page). The judged list is bookkeeping for the
        # results pass and stays out.
        out['page'] = {key: value for key, value in item['page'].items() if key != 'judged'}
        # A published page is the breakthrough's page at /b/<ID>. The owner's review notes
        # stay out of the data.
        out['published'] = published(item)
    return out


def search_index(db, view=None):
    """data/search.json: titles and short summaries, loaded when search is first used."""
    view = view or site_view(db)
    return [
        {
            'id': identifier,
            'field': item['field'],
            'title': item['title'],
            'summary': cut(item['concept'][0]['text']) if item['concept'] else '',
        }
        for identifier, item in sorted(view['items'].items())
    ]


def site_files(db, public=False):
    """Every data file of the contract: (path under data/, value). public: published only."""
    view = site_view(db, public)
    yield 'catalog.json', catalog(db, view)
    yield 'search.json', search_index(db, view)
    for prefix in view['fields']:
        yield f'field/{prefix}.json', field_data(db, prefix, view)
    for identifier in view['items']:
        yield f'b/{identifier}.json', breakthrough_data(db, identifier, view)


def encode(value):
    """Compact UTF-8 JSON, as served and exported."""
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


if __name__ == '__main__':
    counts = rebuild()
    print(
        ', '.join(f'{count} {table}' for table, count in counts.items() if table != 'missing')
        + f'; {counts["missing"]} saved copies missing (skipped)'
    )
