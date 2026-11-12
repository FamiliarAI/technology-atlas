"""Add a paper or link as progress: python3 -m atlas.add <url> [--breakthrough ID].

Saves the source, ranks every milestone against its opening text in memory, and makes
one model call that returns a progress row for each milestone the source bears on, or with
criterion 0 for a step toward a candidate breakthrough as a whole.
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
from .batch import ARCHIVE_LOCK
from .copies import ADDED, Copy, choose, known_copies
from .core import CORE
from .store import CONFIG, DB, ROOT, connect

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
                    'criterion': {'type': 'integer', 'minimum': 0},
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
    'criterion is the milestone number shown in the candidate. Use criterion 0 for a concrete '
    'result that is a step toward one of the listed breakthroughs as a whole but bears on no '
    'single listed milestone of it. Prefer a specific milestone whenever one fits; use 0 only '
    'when none does. A row with criterion 0 may have verdict "advances" or "contradicts", '
    'never "meets".\n'
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


def captured(url):
    """Copies of url in the atlas/data/added archive: {sha256, format, kind} each."""
    if not (ADDED / 'captures.json').is_file():
        return []
    with ARCHIVE_LOCK:
        artifacts = Archive(ADDED).source(url)['artifacts']
    return [
        {key: artifact[key] for key in ('sha256', 'format', 'kind')}
        for artifact in artifacts
        if (ADDED / artifact['path']).is_file()
    ]


def save(url, path=DB, core=CORE, title=None):
    (
        """The copy of url to read, as a Copy: the trusted copy with the most text """
        """(atlas.copies). Captures only when no trusted copy has MIN_TEXT characters; a """
        """PubMed page then also gets its E-utilities abstract and PMC page. When still none """
        """has, the trusted copy with the most text is returned for the caller to judge."""
    )
    source = dict(records.load(core)['sources'].get(url) or {'url': url, 'title': title or ''})
    with closing(connect(path)) as db:
        found = known_copies(source, db)
    chosen = choose(source, found)
    if chosen:
        return chosen
    ADDED.mkdir(parents=True, exist_ok=True)
    with ARCHIVE_LOCK:
        archive = Archive(ADDED)
        archive.capture(url)
        archive.pubmed(url)
        items = archive.evidence(url)
    known = {copy.sha256 for copy in found}
    for item in items:
        if item['sha256'] not in known:
            path_ = str((ADDED / item['path']).resolve())
            found.append(
                Copy(item['sha256'], path_, item['text'], item['kind'], item.get('resolved_url'))
            )
    chosen = choose(source, found) or choose(source, found, minimum=1)
    if chosen is None:
        raise SystemExit('Could not save ' + url + '; see ' + str(ADDED / 'captures.json'))
    return chosen


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


def assess(url, copy, forced=None, call=None, path=DB, only=None):
    """Judge a saved copy against ranked milestones without writing anything. Returns a dict:
    stored and rejected rows, source_date, model, added_at."""
    text = copy[2]
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
    if call is None:
        _, call = _call(config)
    result = judge(url, text, candidates, call)
    allowed = {(milestone['breakthrough'], milestone['criterion']) for milestone in candidates}
    # Criterion 0: a step toward a candidate breakthrough as a whole.
    allowed |= {(milestone['breakthrough'], 0) for milestone in candidates}
    stored, rejected = [], []
    for row in result['rows']:
        if only and row['breakthrough'] != only:
            rejected.append((row, 'other breakthrough, not stored'))
        elif (row['breakthrough'], row['criterion']) not in allowed:
            rejected.append((row, 'not a candidate milestone'))
        elif row['criterion'] == 0 and row['verdict'] == 'meets':
            rejected.append((row, 'meets needs a milestone'))
        elif not passage_matches(row['quote'], text):
            rejected.append((row, 'quote not found in saved copy'))
        else:
            stored.append(row)
    return {
        'stored': stored,
        'rejected': rejected,
        'source_date': result['source_date'],
        'model': config['format']['model'],
        'added_at': datetime.now(timezone.utc).isoformat(),
    }


def record(url, copy, judged, core=CORE, title=None, only=None, record_captured=True):
    """Write a judged source to atlas/core: the source line and copies, and its progress rows
    (replacing earlier rows for url, or only only's earlier rows). Does not rebuild."""
    sha, file = copy[0], copy[1]
    kind = copy[3] if len(copy) > 3 else 'source'
    data = records.load(core)
    source = data['sources'].setdefault(
        url, {'url': url, 'title': title or url, 'status': 'saved', 'copies': []}
    )
    chosen = {'sha256': sha, 'format': Path(file).suffix.lstrip('.').lower(), 'kind': kind}
    # Every copy captured for url is recorded, so later readers can choose among them.
    for entry in [chosen] + (captured(url) if record_captured else []):
        if entry['sha256'] not in {known['sha256'] for known in source['copies']}:
            source['copies'].append(entry)
    source['status'] = 'saved'
    records.write_sources(data['sources'], core)
    # Re-adding a source replaces its earlier judgement; milestone IDs stay stable.
    rows = [
        row
        for row in data['progress']
        if row['url'] != url or (only and row['breakthrough'] != only)
    ]
    for row in judged['stored']:
        milestone = None  # criterion 0: the breakthrough as a whole
        if row['criterion']:
            milestone = data['breakthroughs'][row['breakthrough']]['completion_criteria'][
                row['criterion'] - 1
            ]['id']
        rows.append(
            {
                'breakthrough': row['breakthrough'],
                'milestone': milestone,
                'url': url,
                'copy': sha,
                'source_date': judged['source_date'],
                'verdict': row['verdict'],
                'quote': row['quote'],
                'by': judged['model'],
                'added_at': judged['added_at'],
            }
        )
    records.write_progress(rows, core)


def add(url, forced=None, call=None, saver=None, path=DB, core=CORE, title=None, only=None):
    (
        """Save url, judge it against ranked milestones, store verified rows and rebuild. """
        """A new source gets title, or its URL when none is given. With only, rows for """
        """other breakthroughs are not stored, and only that breakthrough's earlier rows """
        """for url are replaced. Every copy captured for url is recorded unless a stub """
        """saver is given. Returns (stored, rejected)."""
    )
    copy = saver(url) if saver else save(url, path, core, title)
    judged = assess(url, copy, forced, call, path, only)
    record(url, copy, judged, core, title, only, record_captured=saver is None)
    store.rebuild(core=core, path=path)
    return judged['stored'], judged['rejected']


def target(row):
    """What a returned row bears on, for printing."""
    if row['criterion'] == 0:
        return 'whole breakthrough'
    return f'milestone {row["criterion"]}'


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
        print(f'stored  {row["breakthrough"]} {target(row)}: {row["verdict"]}')
    for row, why in rejected:
        print(f'rejected {row["breakthrough"]} {target(row)}: {why}')
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
