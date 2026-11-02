"""Add a paper or link as progress: python3 -m atlas.add <url> [--breakthrough ID].

Saves the source, ranks every milestone against its opening text in memory, and makes
one model call that returns a progress row for each milestone the source bears on.
"""
import argparse
import json
import math
import re
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from ingestion.pipeline import Models, passage_matches
from ingestion.sources import UA, Archive, request_url
from .store import CONFIG, DB, ROOT, connect, initialize

ADDED = ROOT / 'atlas/data/added'
CANDIDATES = 20
TEXT_LIMIT = 120000
STOP = set('that this with from have been which their there these those would could should about into over than more most also only such they them were will each other when where what using used between within without while being does through under after before because'.split())

SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': ['source_date', 'rows'],
    'properties': {
        'source_date': {'anyOf': [{'type': 'string', 'pattern': r'^\d{4}(-\d{2}(-\d{2})?)?$'}, {'type': 'null'}]},
        'rows': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False, 'required': ['breakthrough', 'criterion', 'verdict', 'quote'],
            'properties': {
                'breakthrough': {'type': 'string', 'pattern': r'^[A-Z]{2,8}-\d{2}$'},
                'criterion': {'type': 'integer', 'minimum': 1},
                'verdict': {'type': 'string', 'enum': ['advances', 'meets', 'contradicts']},
                'quote': {'type': 'string', 'minLength': 20, 'maxLength': 600}}}}}}

PROMPT = '''You are judging whether one source shows progress towards proposed breakthroughs.

Each candidate below is one milestone (a completion criterion) of an breakthrough. For every candidate this source genuinely bears on, return one row:
- verdict "meets": the source reports a result that satisfies the milestone as written.
- verdict "advances": the source reports a concrete result that moves measurably towards the milestone without satisfying it.
- verdict "contradicts": the source reports a result showing the milestone's approach fails or is further away than assumed.
- quote: a passage copied exactly from the source text (20-600 characters) that shows the result. Results only; not background, goals or plans.

Return no row for a candidate the source only mentions, motivates, or relates to in topic. Most candidates will have no row. An empty list is a valid answer.
source_date: the source's publication date as YYYY-MM-DD, YYYY-MM or YYYY if the text states it, else null.

Candidates:
{candidates}

Source ({url}):
<<<
{text}
>>>
'''


def words(text):
    return [w for w in re.findall(r'[a-z][a-z0-9-]{3,}', text.lower()) if w not in STOP]


def rank(db, opening, forced=None, limit=CANDIDATES):
    """Milestones ordered by IDF-weighted word overlap with the source's opening text."""
    milestones = []
    for r in db.execute('SELECT id, payload FROM breakthroughs'):
        item = json.loads(r['payload'])
        for n, c in enumerate(item['completion_criteria'], 1):
            milestones.append({'breakthrough': r['id'], 'title': item['title'], 'criterion': n, 'text': c['text']})
    docs = [set(words(m['title'] + ' ' + m['text'])) for m in milestones]
    df = Counter(w for d in docs for w in d)
    query = Counter(words(opening))
    for m, d in zip(milestones, docs):
        m['score'] = sum(math.log(len(docs) / df[w]) * min(k, 3) for w, k in query.items() if w in d)
    chosen = sorted(milestones, key=lambda m: -m['score'])[:limit]
    if forced:
        chosen += [m for m in milestones if m['breakthrough'] == forced and m not in chosen]
    return chosen


def save(url):
    """Saved copy for url: (sha256, path, text). Reuses an existing asset when the URL was already saved."""
    with connect(DB) as db:
        initialize(db)
        known = db.execute('SELECT a.id, a.path FROM progress p JOIN assets a ON a.id = p.asset WHERE p.url=? LIMIT 1', (url,)).fetchone()
    if known and Path(known['path']).is_file():
        from ingestion.sources import extract
        body = Path(known['path']).read_bytes()
        _, text, _, _ = extract(body, 'application/pdf' if body.startswith(b'%PDF-') else 'text/html')
        return known['id'], known['path'], text
    ADDED.mkdir(parents=True, exist_ok=True)
    archive = Archive(ADDED)
    archive.capture(url)
    items = archive.evidence(url)
    if not items:
        raise SystemExit('Could not save ' + url + '; see ' + str(ADDED / 'captures.json'))
    best = next((a for a in items if a['format'] == 'pdf' and a['text'].strip()), None) or next((a for a in items if a['text'].strip()), items[0])
    return best['sha256'], str((ADDED / best['path']).resolve()), best['text']


def request_wayback(url):
    # Best effort: the archive copy is found later at https://web.archive.org/web/<url>.
    try:
        urllib.request.urlopen(urllib.request.Request('https://web.archive.org/save/' + request_url(url), headers={'User-Agent': UA}), timeout=60).close()
        return True
    except OSError:
        return False


def judge(url, text, candidates, call):
    listing = '\n'.join(f"- {m['breakthrough']} milestone {m['criterion']} ({m['title']}): {m['text']}" for m in candidates)
    return call(PROMPT.format(candidates=listing, url=url, text=text[:TEXT_LIMIT]))


def add(url, forced=None, call=None, saver=save, path=DB):
    """Save url, judge it against ranked milestones, and store verified rows. Returns (stored, rejected)."""
    sha, file, text = saver(url)
    if not text.strip():
        raise SystemExit('Saved copy has no extractable text; attach a readable copy')
    with connect(path) as db:
        initialize(db)
        if forced and not db.execute('SELECT 1 FROM breakthroughs WHERE id=?', (forced,)).fetchone():
            raise SystemExit('Unknown breakthrough ' + forced)
        db.execute('INSERT OR IGNORE INTO assets VALUES (?,?,?)', (sha, file, sha))
        candidates = rank(db, text[:4000], forced)
        config = json.loads(CONFIG.read_text())
        model = config['format']['model']
        if call is None:
            calls = ADDED / 'calls' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            calls.mkdir(parents=True)
            call = lambda prompt: Models(config).call('format', prompt, SCHEMA, calls)
        result = judge(url, text, candidates, call)
        allowed = {(m['breakthrough'], m['criterion']) for m in candidates}
        stored, rejected = [], []
        for r in result['rows']:
            if (r['breakthrough'], r['criterion']) not in allowed:
                rejected.append((r, 'not a candidate milestone'))
            elif not passage_matches(r['quote'], text):
                rejected.append((r, 'quote not found in saved copy'))
            else:
                stored.append(r)
        added_at = datetime.now(timezone.utc).isoformat()
        with db:
            # Re-adding a source replaces its earlier judgement.
            db.execute("DELETE FROM progress WHERE id LIKE 'added:%' AND url=?", (url,))
            for r in stored:
                db.execute('INSERT OR REPLACE INTO progress VALUES (?,?,?,?,?,?,?,?,?,?)', (f"added:{sha}:{r['breakthrough']}:{r['criterion']}", r['breakthrough'], r['criterion'], url, sha, result['source_date'], r['verdict'], r['quote'], model, added_at))
    return stored, rejected


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('url')
    p.add_argument('--breakthrough', help='also judge every milestone of this breakthrough')
    a = p.parse_args()
    stored, rejected = add(a.url, a.breakthrough)
    print('Wayback save requested' if request_wayback(a.url) else 'Wayback save failed; retry later')
    for r in stored:
        print(f"stored  {r['breakthrough']} milestone {r['criterion']}: {r['verdict']}")
    for r, why in rejected:
        print(f"rejected {r['breakthrough']} milestone {r['criterion']}: {why}")
    if not stored:
        print('No progress rows stored.')


if __name__ == '__main__':
    main()
