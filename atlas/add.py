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
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from ingestion.pipeline import Models, passage_matches
from ingestion.sources import UA, Archive, request_url
from . import core as records, store
from .core import CORE
from .store import CONFIG, DB, ROOT, connect

ADDED = ROOT / 'atlas/data/added'
CANDIDATES = 20
TEXT_LIMIT = 120000
STOP = set(
    (
        'that this with from have been which their there these those would could should '
        'about into over than more most also only such they them were will each other when '
        'where what using used between within without while being does through under after '
        'before because'
    ).split()
)

SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['source_date', 'rows'],
    'properties': {
        'source_date': {
            'anyOf': [{'type': 'string', 'pattern': r'^\d{4}(-\d{2}(-\d{2})?)?$'}, {'type': 'null'}]
        },
        'rows': {
            'type': 'array',
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'required': ['breakthrough', 'criterion', 'verdict', 'quote'],
                'properties': {
                    'breakthrough': {'type': 'string', 'pattern': r'^[A-Z]{2,8}-\d{2}$'},
                    'criterion': {'type': 'integer', 'minimum': 1},
                    'verdict': {'type': 'string', 'enum': ['advances', 'meets', 'contradicts']},
                    'quote': {'type': 'string', 'minLength': 20, 'maxLength': 600},
                },
            },
        },
    },
}

PROMPT = (
    'You are judging whether one source shows progress towards proposed breakthroughs.\n'
    '\n'
    'Each candidate below is one milestone (a completion criterion) of an breakthrough. '
    'For every candidate this source genuinely bears on, return one row:\n'
    '- verdict "meets": the source reports a result that satisfies the milestone as '
    'written.\n'
    '- verdict "advances": the source reports a concrete result that moves measurably '
    'towards the milestone without satisfying it.\n'
    '- verdict "contradicts": the source reports a result showing the milestone\'s '
    'approach fails or is further away than assumed.\n'
    '- quote: a passage copied exactly from the source text (20-600 characters) that shows '
    'the result. Results only; not background, goals or plans.\n'
    '\n'
    'Return no row for a candidate the source only mentions, motivates, or relates to in '
    'topic. Most candidates will have no row. An empty list is a valid answer.\n'
    "source_date: the source's publication date as YYYY-MM-DD, YYYY-MM or YYYY if the text "
    'states it, else null.\n'
    '\n'
    'Candidates:\n'
    '{candidates}\n'
    '\n'
    'Source ({url}):\n'
    '<<<\n'
    '{text}\n'
    '>>>\n'
)


def words(text):
    return [word for word in re.findall(r'[a-z][a-z0-9-]{3,}', text.lower()) if word not in STOP]


def rank(db, opening, forced=None, limit=CANDIDATES):
    """Milestones ordered by IDF-weighted word overlap with the source's opening text."""
    milestones = []
    for row in db.execute('SELECT id, payload FROM breakthroughs'):
        item = json.loads(row['payload'])
        for criterion_number, criterion in enumerate(item['completion_criteria'], 1):
            milestones.append(
                {
                    'breakthrough': row['id'],
                    'title': item['title'],
                    'criterion': criterion_number,
                    'text': criterion['text'],
                }
            )
    documents = [
        set(words(milestone['title'] + ' ' + milestone['text'])) for milestone in milestones
    ]
    document_frequency = Counter(word for document in documents for word in document)
    query = Counter(words(opening))
    for milestone, document in zip(milestones, documents):
        milestone['score'] = sum(
            math.log(len(documents) / document_frequency[word]) * min(count, 3)
            for word, count in query.items()
            if word in document
        )
    chosen = sorted(milestones, key=lambda milestone: -milestone['score'])[:limit]
    if forced:
        chosen += [
            milestone
            for milestone in milestones
            if milestone['breakthrough'] == forced and milestone not in chosen
        ]
    return chosen


def save(url, path=DB):
    (
        """Saved copy for url: (sha256, path, text). Reuses an existing asset when """
        """the URL was already saved."""
    )
    with closing(connect(path)) as db:
        known = db.execute(
            (
                'SELECT a.id, a.path FROM progress p JOIN assets a ON a.id = p.asset WHERE '
                'p.url=? LIMIT 1'
            ),
            (url,),
        ).fetchone()
    if known and Path(known['path']).is_file():
        from ingestion.sources import extract

        body = Path(known['path']).read_bytes()
        _, text, _, _ = extract(
            body, 'application/pdf' if body.startswith(b'%PDF-') else 'text/html'
        )
        return known['id'], known['path'], text
    ADDED.mkdir(parents=True, exist_ok=True)
    archive = Archive(ADDED)
    archive.capture(url)
    items = archive.evidence(url)
    if not items:
        raise SystemExit('Could not save ' + url + '; see ' + str(ADDED / 'captures.json'))
    best = next(
        (
            artifact
            for artifact in items
            if artifact['format'] == 'pdf' and artifact['text'].strip()
        ),
        None,
    ) or next((artifact for artifact in items if artifact['text'].strip()), items[0])
    return best['sha256'], str((ADDED / best['path']).resolve()), best['text']


def request_wayback(url):
    # Best effort: the archive copy is found later at https://web.archive.org/web/<url>.
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                'https://web.archive.org/save/' + request_url(url), headers={'User-Agent': UA}
            ),
            timeout=60,
        ).close()
        return True
    except OSError:
        return False


def judge(url, text, candidates, call):
    listing = '\n'.join(
        f'- {milestone["breakthrough"]} milestone {milestone["criterion"]} '
        f'({milestone["title"]}): {milestone["text"]}'
        for milestone in candidates
    )
    return call(PROMPT.format(candidates=listing, url=url, text=text[:TEXT_LIMIT]))


def _call(config):
    calls = ADDED / 'calls' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    calls.mkdir(parents=True)
    return calls, lambda prompt: Models(config).call('format', prompt, SCHEMA, calls)


def add(url, forced=None, call=None, saver=None, path=DB, core=CORE):
    (
        """Save url, judge it against ranked milestones, and store verified rows. """
        """Returns (stored, rejected)."""
    )
    sha, file, text = saver(url) if saver else save(url, path)
    if not text.strip():
        raise SystemExit('Saved copy has no extractable text; attach a readable copy')
    with closing(connect(path)) as db:
        if (
            forced
            and not db.execute('SELECT 1 FROM breakthroughs WHERE id=?', (forced,)).fetchone()
        ):
            raise SystemExit('Unknown breakthrough ' + forced)
        candidates = rank(db, text[:4000], forced)
        config = json.loads(CONFIG.read_text())
        model = config['format']['model']
        if call is None:
            _, call = _call(config)
        result = judge(url, text, candidates, call)
        allowed = {(milestone['breakthrough'], milestone['criterion']) for milestone in candidates}
        stored, rejected = [], []
        for row in result['rows']:
            if (row['breakthrough'], row['criterion']) not in allowed:
                rejected.append((row, 'not a candidate milestone'))
            elif not passage_matches(row['quote'], text):
                rejected.append((row, 'quote not found in saved copy'))
            else:
                stored.append(row)
        added_at = datetime.now(timezone.utc).isoformat()
    data = records.load(core)
    source = data['sources'].setdefault(
        url, {'url': url, 'title': url, 'status': 'saved', 'copies': []}
    )
    if sha not in {copy['sha256'] for copy in source['copies']}:
        source['copies'].append(
            {'sha256': sha, 'format': Path(file).suffix.lstrip('.').lower(), 'kind': 'source'}
        )
    records.write_sources(data['sources'], core)
    # Re-adding a source replaces its earlier judgement; milestone IDs stay stable.
    rows = [row for row in data['progress'] if row['url'] != url]
    for row in stored:
        milestone = data['breakthroughs'][row['breakthrough']]['completion_criteria'][
            row['criterion'] - 1
        ]['id']
        rows.append(
            {
                'breakthrough': row['breakthrough'],
                'milestone': milestone,
                'url': url,
                'copy': sha,
                'source_date': result['source_date'],
                'verdict': row['verdict'],
                'quote': row['quote'],
                'by': model,
                'added_at': added_at,
            }
        )
    records.write_progress(rows, core)
    store.rebuild(core=core, path=path)
    return stored, rejected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--breakthrough', help='also judge every milestone of this breakthrough')
    parser.add_argument(
        '--no-commit', action='store_true', help='write core and rebuild without committing'
    )
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text())
    calls, call = _call(config)
    stored, rejected = add(args.url, args.breakthrough, call=call)
    print(
        'Wayback save requested'
        if request_wayback(args.url)
        else 'Wayback save failed; retry later'
    )
    for row in stored:
        print(f'stored  {row["breakthrough"]} milestone {row["criterion"]}: {row["verdict"]}')
    for row, why in rejected:
        print(f'rejected {row["breakthrough"]} milestone {row["criterion"]}: {why}')
    if not stored:
        print('No progress rows stored.')
    if not args.no_commit:
        call_path = calls.relative_to(ROOT) if calls.is_relative_to(ROOT) else calls
        message = (
            f'Add source {args.url} ({len(stored)} progress rows)\n\n'
            f'Model: {config["format"]["model"]}\n'
            f'Call: {call_path}'
        )
        records.commit(message)


if __name__ == '__main__':
    main()
