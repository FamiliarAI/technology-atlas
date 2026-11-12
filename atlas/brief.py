"""Reader's version of breakthroughs: python3 -m atlas.brief ID [ID ...] [--workers N] [--no-commit].

One Codex Sol call per breakthrough, given the whole record and its sources with the opening of
each saved copy, writes a short plain-language version stored as `brief` in the record file.
Only `brief` and `models.brief` are added; every other byte of the file stays the same.
"""

import argparse
import hashlib
import json
import subprocess
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from ingestion.pipeline import passage_matches
from ingestion.providers import Models

from . import batch, core as records, store
from .copies import choose, known_copies
from .core import CORE
from .store import CONFIG, DB, ROOT, connect

CALLS = ROOT / 'atlas/data/brief'
MODEL = 'gpt-6.1-sol'
ENTRY = {'provider': 'codex', 'model': MODEL, 'effort': 'medium'}
SOURCE_LIMIT = 12000
TOTAL_LIMIT = 80000
# The prompt's stated limits in characters. An answer is rejected only past SLACK times a limit,
# so a model aiming at 400 is not rejected at 412.
SLACK = 1.1
LIMITS = {
    'title': 60,
    'paragraph': 400,
    'item': 160,
    'who': 80,
    'showed': 300,
    'sentence': 160,
    'label': 80,
    'explanation': 240,
}
LABEL_WORDS = 10
# A quote outside these lengths is stored as null and unchecked, never rejected.
QUOTE = (40, 300)
# Each list of text: the limit of its entries and how many entries it must have.
LISTS = {
    'possible': ('paragraph', 1, 2),
    'why': ('paragraph', 1, 2),
    'shown': ('paragraph', 1, 2),
    'missing': ('item', 2, 4),
    'uncertain': ('item', 1, 3),
}
SECTIONS = [
    ('concept', 'What it is'),
    ('significance', 'Why it matters'),
    ('current_state', 'Current state'),
    ('missing_breakthrough', 'What is still missing'),
]

TEXT = {'type': 'string'}
TEXTS = {'type': 'array', 'items': TEXT}
SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': [
        'title',
        'possible',
        'why',
        'sources',
        'shown',
        'missing',
        'milestones',
        'uncertain',
    ],
    'properties': {
        'title': TEXT,
        'possible': TEXTS,
        'why': TEXTS,
        'sources': {
            'type': 'array',
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'required': ['url', 'who', 'showed', 'quote', 'cited_for', 'not_established'],
                'properties': {
                    'url': TEXT,
                    'who': TEXT,
                    'showed': TEXT,
                    'quote': {'anyOf': [TEXT, {'type': 'null'}]},
                    'cited_for': TEXT,
                    'not_established': TEXT,
                },
            },
        },
        'shown': TEXTS,
        'missing': TEXTS,
        'milestones': {
            'type': 'array',
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'required': ['id', 'label', 'explanation'],
                'properties': {'id': TEXT, 'label': TEXT, 'explanation': TEXT},
            },
        },
        'uncertain': TEXTS,
    },
}

PROMPT = (
    "You are writing the reader's version of one entry in a public atlas of breakthroughs worth\n"
    'working towards. The entry was researched and written by AI models for accuracy, and it is long,\n'
    'technical and full of caveats. Your version is what a curious, intelligent reader who is not a\n'
    'specialist reads first, on a phone, in about two minutes. The full entry stays available beneath\n'
    'yours, so you do not need to carry everything: choose what matters most and leave the rest out.\n'
    '\n'
    "You are given the entry and its sources, with the opening of each source's saved text where one\n"
    'exists.\n'
    '\n'
    'What you may say:\n'
    "- Only what the entry or a source's text supports. Add no fact, number, name or claim of your\n"
    '  own, and use no outside knowledge.\n'
    '- Do not change what the breakthrough is. Do not add, drop, merge, split or reorder milestones.\n'
    '  You explain them; you do not redefine them.\n'
    '- Keep a qualification only when it changes what a reader should believe about the science: a\n'
    '  preprint, a single group, a small sample, a result not yet reproduced.\n'
    '\n'
    'What you must leave out:\n'
    '- Anything about how the entry was produced or checked: what was saved, captured, supplied,\n'
    '  retrieved, extracted, inspected or verified, on what date, or by whom. A reader does not care\n'
    '  that a page could not be downloaded. Never write "the entry", "the record", "the innovation",\n'
    '  "the supplied research", "the evidence available here", "unverified here" or anything like\n'
    '  them.\n'
    '- Praise. Do not write "revolutionary", "groundbreaking" or "game-changing".\n'
    '- Strings of figures. Give at most one number in any item: the one a reader would remember.\n'
    '\n'
    'How to write:\n'
    '- Plain English, short sentences, active verbs, whole sentences. No fragments and no commands.\n'
    '- Explain each technical term in a few words the first time it appears, then use it freely.\n'
    '- Say each thing once.\n'
    '\n'
    'What to write, with hard limits. An answer over a limit is rejected.\n'
    '- title: the capability in everyday words, as a noun phrase, with no jargon. At most 60\n'
    '  characters.\n'
    '- possible: 1 or 2 paragraphs, each at most 400 characters. What people could do once this\n'
    "  exists that they cannot do today. Start from the reader's world, not from the technology.\n"
    '- why: 1 or 2 paragraphs, each at most 400 characters. What would change, and for whom, as the\n'
    '  entry argues it. State it plainly. Caveats and limits do not belong here; they go in missing,\n'
    '  uncertain and not_established.\n'
    '- sources: one item for every source that has saved text, in the order given. A source with no\n'
    '  saved text gets an item only if the entry says what it reports; otherwise leave it out.\n'
    '  - who: the people or organisation that did the work, at most 80 characters, for example\n'
    '    "Google Quantum AI and collaborators". Take it from the paper itself. Never name the website\n'
    '    that hosts the copy, such as GitHub, arXiv or PubMed.\n'
    '  - showed: at most 300 characters. What they showed, in one or two sentences. For a source with\n'
    "    no saved text, say in one sentence what kind of work it is, from the entry's description,\n"
    '    and nothing more.\n'
    "  - quote: one sentence or passage copied exactly, character for character, from that source's\n"
    '    saved text, 40 to 300 characters, in which the authors state a concrete finding: what they\n'
    '    measured, observed, proved or built. Not a title, a heading, a method, an aim, or a sentence\n'
    '    about what the results suggest or make possible. null if the source has no saved text or no\n'
    '    such passage.\n'
    '  - cited_for: one sentence, at most 160 characters: the part of the case this source supports.\n'
    '  - not_established: one sentence, at most 160 characters: the gap between what they showed and\n'
    '    the breakthrough. This is about the science, never about access to the paper.\n'
    '  - If two sources are versions of the same work, describe the work under the first. For the\n'
    '    other, showed is "An earlier version of the same work." or "A later version of the same\n'
    '    work.", quote is null, and the two sentences are each "See the other version."\n'
    '- shown: 1 or 2 paragraphs, each at most 400 characters. The furthest anyone has got, and who.\n'
    '- missing: 2 to 4 items, each at most 160 characters. The specific things nobody has yet done.\n'
    '- milestones: one item for each milestone, same ids, same order.\n'
    '  - label: at most 10 words and 80 characters, naming the result that would have to be seen.\n'
    '  - explanation: at most 240 characters. One sentence on what would have to be shown, then one\n'
    '    on why it matters for the breakthrough. Statements, never instructions: write "A trial would\n'
    '    have to show X", not "Show X".\n'
    '- uncertain: 1 to 3 items, each at most 160 characters. Open questions about the science, or\n'
    '  about how the milestones should be judged. Nothing about documents, dates or citations.\n'
    '\n'
    'Entry {id}: {title}\n'
    '\n'
    '{record}\n'
    '\n'
    'Sources:\n'
    '{sources}\n'
)

# Identifies the prompt a stored brief was written from (brief.prompt); --missing rewrites
# briefs whose hash differs.
PROMPT_HASH = hashlib.sha256(PROMPT.encode()).hexdigest()[:12]

RETRY = (
    '\nYour previous answer was rejected:\n'
    '{problems}\n'
    'Write the whole answer again within the limits stated above, fixing this.\n'
)


def describe(item):
    """The whole record as the prompt shows it."""
    parts = []
    for key, heading in SECTIONS:
        parts.append(heading + ':\n' + '\n\n'.join(p['text'] for p in item.get(key, [])))
    parts.append(
        'Milestones:\n'
        + '\n\n'.join(
            f'{criterion["id"]} ({criterion.get("label", "")}): {criterion["text"]}'
            for criterion in item['completion_criteria']
        )
    )
    issues = item.get('unresolved_issues', [])
    parts.append('Unresolved issues:\n' + ('\n'.join('- ' + issue for issue in issues) or '(none)'))
    return '\n\n'.join(parts)


def saved_text(source, db):
    """Full extracted text of the copy atlas.copies.choose picks: a trusted copy of the work
    itself with at least MIN_TEXT characters. Empty when there is none (no copy on this
    computer, a cookie wall or error page, or only PDFs that are other works)."""
    chosen = choose(source, known_copies(source, db))
    return chosen.text if chosen else ''


def gather(data, identifier, db):
    """Every source of a breakthrough: its record sources, then URLs of its judged rows.
    Each: {url, title, text (full saved text or ''), passages, quotes}."""
    item = data['breakthroughs'][identifier]
    urls = list(item.get('sources', []))
    rows = [row for row in data['progress'] if row['breakthrough'] == identifier]
    for row in rows:
        if row['url'] not in urls:
            urls.append(row['url'])
    headings = dict(SECTIONS) | {
        'completion_criteria': 'Milestone',
        'related_concepts': 'Related concepts',
    }
    sources = []
    for url in urls:
        source = data['sources'].get(url, {'url': url})
        passages = [
            (headings[key], paragraph.get('id'), paragraph['text'])
            for key in headings
            for paragraph in item.get(key, [])
            if url in paragraph.get('source_urls', [])
        ]
        title = source.get('title') or ''
        text = saved_text(source, db)
        sources.append(
            {
                'url': url,
                'title': '' if title == url else title,
                'text': text,
                'passages': passages,
                'quotes': [row for row in rows if row['url'] == url],
            }
        )
    return sources


def show_sources(sources):
    """The sources block of the prompt, each saved text cut to its share of the budget."""
    share = min(SOURCE_LIMIT, TOTAL_LIMIT // max(len(sources), 1))
    blocks = []
    for number, source in enumerate(sources, 1):
        lines = [
            f'Source {number}',
            f'url: {source["url"]}',
            f'title: {source["title"] or "(none recorded)"}',
            f'saved copy: {"yes" if source["text"] else "no"}',
        ]
        if source['passages']:
            lines.append('Passages of the entry that cite it:')
            for heading, milestone, text in source['passages']:
                where = f'{heading} {milestone}' if milestone else heading
                lines.append(f'- {where}: {text}')
        if source['quotes']:
            lines.append('Passages judged to show progress:')
            for row in source['quotes']:
                where = f'milestone {row["milestone"]}' if row['milestone'] else 'the whole'
                lines.append(f'- {where}, {row["verdict"]}: "{row["quote"]}"')
        if source['text']:
            lines += ['Saved text (opening):', '<<<', source['text'][:share], '>>>']
        else:
            lines.append('Saved text: none')
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks)


def prompt(data, identifier, sources):
    item = data['breakthroughs'][identifier]
    return PROMPT.format(
        id=identifier, title=item['title'], record=describe(item), sources=show_sources(sources)
    )


def validate(item, sources, result):
    """The answer as stored, with quotes checked. ValueError lists every problem, one per line."""
    if not isinstance(result, dict) or set(result) != set(SCHEMA['required']):
        raise ValueError('- the answer does not match the schema')
    problems = []

    def reject(reason):
        problems.append('- ' + reason)

    def check(text, limit, where):
        stated = LIMITS[limit]
        if not isinstance(text, str) or not text.strip():
            reject(f'{where} must be non-empty text')
        elif len(text) > int(stated * SLACK):
            reject(f'{where} is {len(text)} characters; the limit is {stated}')

    check(result['title'], 'title', 'title')
    for key, (size, low, high) in LISTS.items():
        if not low <= len(result[key]) <= high:
            reject(f'{key} has {len(result[key])} entries; it must have {low} to {high}')
        for number, text in enumerate(result[key], 1):
            check(text, size, f'{key} entry {number}')
    ids = [criterion['id'] for criterion in item['completion_criteria']]
    returned = [milestone.get('id') for milestone in result['milestones']]
    if returned != ids:
        reject(f'milestones must be exactly {", ".join(ids)} in this order, got {returned}')
    for milestone in result['milestones']:
        where = f'milestone {milestone.get("id")}'
        check(milestone['label'], 'label', where + ' label')
        words = len(str(milestone['label']).split())
        if words > int(LABEL_WORDS * SLACK):
            reject(f'{where} label has {words} words; the limit is {LABEL_WORDS}')
        check(milestone['explanation'], 'explanation', where + ' explanation')
    given = [source['url'] for source in sources]
    urls = [entry['url'] for entry in result['sources']]
    for url in urls:
        if url not in given:
            reject(f'source url {url} is not one of the given URLs')
    if len(urls) != len(set(urls)):
        reject('a source url appears twice')
    if len(urls) == len(set(urls)) and set(urls) <= set(given):
        missing = [
            source['url'] for source in sources if source['text'] and source['url'] not in urls
        ]
        if missing:
            reject(f'every source with saved text must appear; missing: {missing}')
        elif urls != [url for url in given if url in urls]:
            reject('sources must be in the order given')
    for entry in result['sources']:
        where = f'source {entry["url"]}'
        check(entry['who'], 'who', where + ' who')
        check(entry['showed'], 'showed', where + ' showed')
        check(entry['cited_for'], 'sentence', where + ' cited_for')
        check(entry['not_established'], 'sentence', where + ' not_established')
    if problems:
        raise ValueError('\n'.join(problems))
    texts = {source['url']: source['text'] for source in sources}
    out = []
    for entry in result['sources']:
        quote = entry['quote']
        text = texts[entry['url']]
        checked = (
            isinstance(quote, str)
            and QUOTE[0] <= len(quote) <= QUOTE[1]
            and bool(text)
            and passage_matches(quote, text)
        )
        out.append(
            {
                'url': entry['url'],
                'who': entry['who'],
                'showed': entry['showed'],
                'quote': quote if checked else None,
                'cited_for': entry['cited_for'],
                'not_established': entry['not_established'],
                'checked': checked,
            }
        )
    return {
        'title': result['title'],
        'possible': result['possible'],
        'why': result['why'],
        'sources': out,
        'shown': result['shown'],
        'missing': result['missing'],
        'milestones': [
            {key: milestone[key] for key in ('id', 'label', 'explanation')}
            for milestone in result['milestones']
        ],
        'uncertain': result['uncertain'],
        'prompt': PROMPT_HASH,
    }


def write(identifier, brief, model=MODEL, core=CORE):
    """Add brief and models.brief to the record file; every other byte stays the same."""
    paths = [p for p in Path(core).glob(f'*/{identifier}.json')]
    if len(paths) != 1:
        raise ValueError(f'{identifier}: expected exactly one breakthrough file')
    path = paths[0]
    source = path.read_text(encoding='utf-8')
    item = json.loads(source)

    def dump(value):
        return json.dumps(value, indent=1, ensure_ascii=False) + '\n'

    # Record files are written by atlas.core in this exact form. Adding keys at the end of an
    # object then leaves every other key's bytes as they were.
    if dump(item) != source:
        raise ValueError(f'{identifier}: record file is not in the written format; not changed')
    item['brief'] = brief
    item.setdefault('models', {})['brief'] = model
    updated = dump(item)
    records.replace_text(path, updated)


def _call(identifier):
    """A call(prompt) that keeps each attempt's records in its own folder."""
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = (CALLS / f'{identifier}-{stamp}').resolve()
    folder.mkdir(parents=True)
    attempts = [0]

    def call(text):
        attempts[0] += 1
        directory = folder / f'attempt-{attempts[0]}'
        directory.mkdir()
        return Models(config).call('format', text, SCHEMA, directory, entry=ENTRY)

    return folder, call


def answer(item, sources, text, call):
    """Call, validate, and retry once with the problem stated. Returns (brief, attempts)."""
    try:
        return validate(item, sources, call(text)), 1
    except ValueError as error:
        problem = str(error)
    return validate(item, sources, call(text + RETRY.format(problems=problem))), 2


def prepare(identifier, core=CORE, path=DB):
    data = records.load(core)
    if identifier not in data['breakthroughs']:
        raise ValueError(f'{identifier}: unknown breakthrough')
    with closing(connect(path)) as db:
        sources = gather(data, identifier, db)
    item = data['breakthroughs'][identifier]
    return item, sources, prompt(data, identifier, sources)


def brief(identifier, call=None, core=CORE, path=DB):
    """Write one breakthrough's brief. Returns (brief, attempts). Does not rebuild or commit."""
    item, sources, text = prepare(identifier, core, path)
    folder = None
    if call is None:
        folder, call = _call(identifier)
    result, attempts = answer(item, sources, text, call)
    write(identifier, result, core=core)
    if folder is not None:
        _success(folder, attempts)
    return result, attempts


def _success(folder, attempts):
    (folder / 'success.json').write_text(
        json.dumps({'model': MODEL, 'attempts': attempts}) + '\n', encoding='utf-8'
    )


def show(identifier, result, attempts):
    checked = sum(1 for source in result['sources'] if source['checked'])
    print(
        f'{identifier}: {result["title"]} ({len(result["sources"])} sources, {checked} quotes '
        f'checked, {attempts} attempt{"s" if attempts > 1 else ""})'
    )
    for source in result['sources']:
        print(f'  {"checked  " if source["checked"] else "unchecked"} {source["url"]}')


def wanted(data, missing):
    """Active breakthroughs, in ID order; with missing, only those with no brief or a brief
    written from another prompt."""
    return sorted(
        identifier
        for identifier, item in data['breakthroughs'].items()
        if item.get('status') == 'active'
        and (not missing or (item.get('brief') or {}).get('prompt') != PROMPT_HASH)
    )


def main(argv=None, core=CORE, path=DB):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('identifiers', nargs='*', metavar='ID')
    parser.add_argument('--all', action='store_true', help='every active breakthrough')
    parser.add_argument(
        '--missing',
        action='store_true',
        help='only breakthroughs with no brief, or one written from another prompt',
    )
    parser.add_argument('--workers', type=int, default=3, help='parallel model calls (default: 3)')
    parser.add_argument('--no-commit', action='store_true')
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error('--workers must be at least 1')
    if not args.identifiers and not args.all and not args.missing:
        parser.error('name breakthroughs, or pass --all or --missing')
    try:
        data = records.load(core)
    except (OSError, ValueError) as error:
        print(error)
        return 1
    unknown = [
        identifier for identifier in args.identifiers if identifier not in data['breakthroughs']
    ]
    if unknown:
        parser.error('unknown breakthrough: ' + ', '.join(unknown))
    identifiers = list(args.identifiers)
    if args.all or args.missing:
        everything = wanted(data, args.missing)
        if identifiers and args.missing:
            identifiers = [identifier for identifier in identifiers if identifier in everything]
        elif not identifiers:
            identifiers = everything
    identifiers = list(dict.fromkeys(identifiers))
    folders = {}

    def message(done):
        return (
            f"Write reader's version for {len(done)} breakthroughs ({done[0]} to {done[-1]})"
            f'\n\nModel: {MODEL}\nPrompt: {PROMPT_HASH}\nCalls:\n'
            + '\n'.join(folders[identifier] for identifier in done)
        )

    writer = batch.Writer(50, not args.no_commit, message, core)

    def work(identifier, stop):
        item, sources, text = prepare(identifier, core, path)
        folder, call = _call(identifier)
        folders[identifier] = str(
            folder.relative_to(ROOT) if folder.is_relative_to(ROOT) else folder
        )

        def guarded(prompt_text):
            if stop.is_set():
                raise batch.Stopped()
            return call(prompt_text)

        result, attempts = answer(item, sources, text, guarded)
        writer.write(identifier, lambda: write(identifier, result, core=core))
        _success(folder, attempts)
        return result, attempts

    def report(identifier, outcome):
        status, value = outcome
        if status == 'done':
            show(identifier, *value)
        elif status == 'failed':
            print(f'{identifier}: failed: {value}')

    outcomes, exhausted = batch.run(identifiers, work, args.workers, report)
    failed = sum(1 for status, _ in outcomes.values() if status == 'failed')
    stopped = sum(1 for status, _ in outcomes.values() if status == 'stopped')
    done = [value for status, value in outcomes.values() if status == 'done']
    try:
        if done:
            store.rebuild(core=core, path=path)
        writer.flush()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(error)
        return 1
    print(
        f'Done: {len(done)} briefs written, {failed} failed, {stopped} not started; '
        f'{sum(1 for _, attempts in done if attempts > 1)} needed the retry'
        + ('. Stopped: a provider reported exhaustion.' if exhausted else '')
    )
    return int(bool(failed) or exhausted)


if __name__ == '__main__':
    raise SystemExit(main())
