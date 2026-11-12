"""Find papers for breakthroughs: python3 -m atlas.find ID [ID ...] [--limit 4] [--no-commit].

One web-search model call per breakthrough returns up to --limit primary sources. Each URL then
goes through atlas.add (save, judge against the breakthrough's milestones, check quotes). A URL
that cannot be saved or has no text is reported and skipped.
"""

import argparse
import json
import subprocess
from datetime import datetime, timezone

from ingestion.providers import Models, ProviderExhausted
from ingestion.sources import MIN_TEXT

from . import add as adding, batch as batch_, core as records, store
from .core import CORE
from .store import CONFIG, DB, ROOT

CALLS = ROOT / 'atlas/data/find'
ENTRY = {'provider': 'codex', 'model': 'gpt-6.1-terra', 'effort': 'medium', 'search': True}
LIMIT = 4
SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['sources'],
    'properties': {
        'sources': {
            'type': 'array',
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'required': ['url', 'title', 'who', 'year', 'bears_on', 'finding'],
                'properties': {
                    'url': {'type': 'string'},
                    'title': {'type': 'string'},
                    'who': {'type': 'string'},
                    'year': {'type': 'integer'},
                    'bears_on': {'type': 'integer', 'minimum': 0},
                    'finding': {'type': 'string'},
                },
            },
        },
    },
}

PROMPT = (
    'You are finding published research for one entry in a public atlas of breakthroughs worth\n'
    'working towards. The entry is below: what the breakthrough is, what is still missing, and its\n'
    'milestones. It already cites the sources listed at the end.\n'
    '\n'
    'Search the web and find up to {limit} further primary sources that report a concrete result\n'
    'bearing on this breakthrough or on one of its milestones.\n'
    '\n'
    'What counts:\n'
    '- A paper, preprint or technical report by the people who did the work, reporting a result:\n'
    '  a measurement, a demonstration, a proof, a trial outcome, or a negative result.\n'
    '- Its full text or a detailed abstract is readable without logging in. Prefer arXiv, '
    'bioRxiv,\n'
    '  medRxiv, PubMed Central, open-access publisher pages and institutional repositories. Do '
    'not\n'
    '  return a pubmed.ncbi.nlm.nih.gov page when the paper also has a PubMed Central, publisher '
    'or\n'
    '  preprint page; return that page.\n'
    '- Prefer the strongest and most recent results, and the foundational result if the field '
    'has one.\n'
    '\n'
    'What does not count: news, press releases, blog posts, reviews and perspectives, grant or '
    'company\n'
    'announcements, papers about plans or roadmaps, and anything already listed.\n'
    '\n'
    'Open each page before you return it. Return it only if the page exists and reports the '
    'result you\n'
    'describe. Never return a URL you have not opened. Fewer good sources are better than more '
    'weak\n'
    'ones; an empty list is a valid answer.\n'
    '\n'
    'For each source return:\n'
    '- url: the page you opened (abstract or full text), not a search or DOI-resolver link if a '
    'direct\n'
    '  page exists.\n'
    "- title: the paper's title as printed.\n"
    '- who: the first author and "and colleagues", plus the lab, company or institution if '
    'stated.\n'
    '- year: publication year.\n'
    '- bears_on: the number of the milestone it most directly bears on, or 0 for the '
    'breakthrough as\n'
    '  a whole.\n'
    '- finding: one sentence stating the result it reports, with its key number if it has one.\n'
    '\n'
    'Breakthrough {id}: {title}\n'
    '\n'
    '{record}\n'
    '\n'
    'Already cited:\n'
    '{cited}\n'
)


def describe(item):
    """Concept, what is missing and the numbered milestones, as the search prompt shows them."""
    parts = [
        label + ': ' + ' '.join(paragraph['text'] for paragraph in item[key])
        for key, label in [
            ('concept', 'Concept'),
            ('missing_breakthrough', 'What is still missing'),
        ]
    ]
    parts += [
        f'Milestone {number}: {criterion["text"]}'
        for number, criterion in enumerate(item['completion_criteria'], 1)
    ]
    return '\n'.join(parts)


def cited(data, identifier):
    """URLs the breakthrough already cites: its sources, then URLs of its judged rows."""
    urls = list(data['breakthroughs'][identifier].get('sources', []))
    for row in data['progress']:
        if row['breakthrough'] == identifier and row['url'] not in urls:
            urls.append(row['url'])
    return urls


def prompt(data, identifier, limit=LIMIT):
    item = data['breakthroughs'][identifier]
    listing = []
    for url in cited(data, identifier):
        title = (data['sources'].get(url) or {}).get('title') or ''
        listing.append(f'- {title} ({url})' if title and title != url else f'- {url}')
    return PROMPT.format(
        limit=limit,
        id=identifier,
        title=item['title'],
        record=describe(item),
        cited='\n'.join(listing) or '(none)',
    )


def _folder(identifier):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = (CALLS / f'{identifier}-{stamp}').resolve()
    folder.mkdir(parents=True)
    return folder


def _search(folder):
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    return lambda text: Models(config).call('format', text, SCHEMA, folder, entry=ENTRY)


def _judge(folder):
    """atlas.add's judge call, with its records kept beside the search call."""
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    count = [0]

    def call(text):
        count[0] += 1
        directory = folder / f'add-{count[0]}'
        directory.mkdir()
        return Models(config).call('format', text, adding.SCHEMA, directory)

    return call


def done_before(identifier):
    """True when a finder call for identifier completed (its reports.json was written)."""
    return any((folder / 'reports.json').is_file() for folder in CALLS.glob(f'{identifier}-*'))


def thin(data, most=1):
    """Active breakthroughs whose record cites at most `most` sources, in ID order."""
    return sorted(
        identifier
        for identifier, item in data['breakthroughs'].items()
        if item.get('status') == 'active' and len(item.get('sources', [])) <= most
    )


def find(
    identifier,
    limit=LIMIT,
    search=None,
    judge=None,
    saver=None,
    path=DB,
    core=CORE,
    urls=None,
    writer=None,
    stop=None,
):
    """Search for papers for one breakthrough and add each through atlas.add, storing rows for
    this breakthrough only. Given urls, skip the search. Saving and judging run here; the core
    writes and one rebuild run through writer (atlas.batch.Writer), so parallel calls do not
    interleave writes. Returns (call folder, one report per URL: {url, title, bears_on, saved,
    stored, rejected, skipped})."""
    data = records.load(core)
    if identifier not in data['breakthroughs']:
        raise ValueError(f'{identifier}: unknown breakthrough')
    folder = None
    if (search is None and urls is None) or judge is None:
        folder = _folder(identifier)
    judge = judge or _judge(folder)
    save = saver or (lambda url, title: adding.save(url, path, core, title))

    def readable(url, title):
        copy = save(url, title) if saver is None else saver(url)
        if len(copy[2].strip()) < MIN_TEXT:
            raise SystemExit(
                f'Saved copy has {len(copy[2].strip())} characters of text; not a readable paper'
            )
        return copy

    if urls is None:
        answer = (search or _search(folder))(prompt(data, identifier, limit))
    else:
        limit = len(urls)
        answer = {
            'sources': [
                {
                    'url': url,
                    'title': (data['sources'].get(url) or {}).get('title') or url,
                    'bears_on': None,
                }
                for url in urls
            ]
        }
    known = set(cited(data, identifier))
    reports, judged = [], []
    seen = set()
    for source in answer['sources'][:limit]:
        url = source['url'].strip()
        report = {
            'url': url,
            'title': source['title'],
            'bears_on': source['bears_on'],
            'saved': False,
            'stored': [],
            'rejected': [],
            'skipped': None,
        }
        reports.append(report)
        if not url.startswith(('http://', 'https://')):
            report['skipped'] = 'not a web URL'
            continue
        if url in known or url in seen:
            report['skipped'] = 'already cited'
            continue
        seen.add(url)
        if stop is not None and stop.is_set():
            report['skipped'] = 'run stopping'
            continue
        try:
            copy = readable(url, source['title'])
            result = adding.assess(url, copy, identifier, judge, path, only=identifier)
        except ProviderExhausted:
            raise
        except SystemExit as error:
            # The URL cannot be saved, or its saved copy has no readable text.
            report['skipped'] = str(error)
            continue
        except (OSError, ValueError, RuntimeError) as error:
            report['skipped'] = f'{type(error).__name__}: {error}'
            continue
        report.update(saved=True, stored=result['stored'], rejected=result['rejected'])
        judged.append((url, copy, result, source['title']))

    def write():
        for url, copy, result, title in judged:
            adding.record(
                url, copy, result, core, title, only=identifier, record_captured=saver is None
            )
        if judged:
            store.rebuild(core=core, path=path)

    if writer is None:
        write()
    else:
        writer.write(identifier, write)
    if any(report['skipped'] == 'run stopping' for report in reports):
        # Judged papers are kept; with no reports.json the breakthrough is redone next run.
        raise batch_.Stopped()
    if folder is not None:
        (folder / 'reports.json').write_text(
            json.dumps(reports, indent=1, ensure_ascii=False) + '\n', encoding='utf-8'
        )
    return folder, reports


def show(identifier, reports):
    print(f'{identifier}: {len(reports)} papers')
    for report in reports:
        print(f'  {report["url"]}')
        print(f'    {report["title"]}')
        if report['skipped']:
            print(f'    not saved: {report["skipped"]}')
            continue
        print(f'    saved; {len(report["stored"])} rows stored, {len(report["rejected"])} rejected')
        for row in report['stored']:
            print(f'    stored  {row["breakthrough"]} {adding.target(row)}: {row["verdict"]}')
        for row, why in report['rejected']:
            if why == 'other breakthrough, not stored':
                print(f'    {row["breakthrough"]} {adding.target(row)}: {why}')
            else:
                print(f'    rejected {row["breakthrough"]} {adding.target(row)}: {why}')


def line(identifier, reports):
    """One line for a batch run."""
    saved = sum(1 for report in reports if report['saved'])
    rows = sum(len(report['stored']) for report in reports)
    return f'{identifier}: {len(reports)} found, {saved} saved, {rows} rows stored'


def main(argv=None, core=CORE, path=DB):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('identifiers', nargs='*', metavar='ID')
    parser.add_argument(
        '--thin', action='store_true', help='every active breakthrough citing at most one source'
    )
    parser.add_argument('--limit', type=int, default=LIMIT, help='papers per breakthrough')
    parser.add_argument(
        '--url',
        action='append',
        dest='urls',
        help='add this URL for the one breakthrough named, without the search call (repeatable)',
    )
    parser.add_argument('--workers', type=int, default=1, help='breakthroughs at once')
    parser.add_argument(
        '--force', action='store_true', help='also redo breakthroughs with a finder call record'
    )
    parser.add_argument('--no-commit', action='store_true')
    args = parser.parse_args(argv)
    if args.limit < 1 or args.workers < 1:
        parser.error('--limit and --workers must be at least 1')
    if args.urls and (len(args.identifiers) != 1 or args.thin):
        parser.error('--url needs exactly one breakthrough')
    if not args.identifiers and not args.thin:
        parser.error('name breakthroughs, or pass --thin')
    data = records.load(core)
    identifiers = list(dict.fromkeys(args.identifiers + (thin(data) if args.thin else [])))
    unknown = [identifier for identifier in identifiers if identifier not in data['breakthroughs']]
    if unknown:
        parser.error('unknown breakthrough: ' + ', '.join(unknown))
    skipped = []
    if not args.force and not args.urls:
        skipped = [identifier for identifier in identifiers if done_before(identifier)]
        identifiers = [identifier for identifier in identifiers if identifier not in skipped]
    batch = len(identifiers) > 1 or args.thin
    config = json.loads(CONFIG.read_text(encoding='utf-8'))

    def message(done):
        return (
            f'Find papers for {len(done)} breakthroughs ({done[0]} to {done[-1]})\n\n'
            f'Search model: {"none (--url)" if args.urls else ENTRY["model"]}\n'
            f'Judge model: {config["format"]["model"]}\nBreakthroughs: {", ".join(done)}'
        )

    writer = batch_.Writer(25, not args.no_commit, message, core)

    def work(identifier, stop):
        return find(
            identifier, args.limit, core=core, path=path, urls=args.urls, writer=writer, stop=stop
        )

    def report(identifier, outcome):
        status, value = outcome
        if status == 'done' and batch:
            print(line(identifier, value[1]), flush=True)
        elif status == 'done':
            show(identifier, value[1])
        elif status == 'failed':
            print(f'{identifier}: failed: {value}', flush=True)

    for identifier in skipped:
        print(f'{identifier}: skipped, already has a finder call record (--force to redo)')
    outcomes, exhausted = batch_.run(identifiers, work, args.workers, report)
    if not batch:
        for status, value in outcomes.values():
            for entry in value[1] if status == 'done' else []:
                if entry['saved'] and adding.request_wayback(entry['url']) is False:
                    print(f'  Wayback save failed for {entry["url"]}; retry later')
    try:
        writer.flush()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(error)
        return 1
    done = [value for status, value in outcomes.values() if status == 'done']
    failed = sum(1 for status, _ in outcomes.values() if status == 'failed')
    stopped = sum(1 for status, _ in outcomes.values() if status == 'stopped')
    reports = [report for _, entries in done for report in entries]
    print(
        f'Done: {len(done)} breakthroughs, {len(skipped)} skipped, {failed} failed, '
        f'{stopped} not started; {len(reports)} papers found, '
        f'{sum(1 for entry in reports if entry["saved"])} saved, '
        f'{sum(len(entry["stored"]) for entry in reports)} rows stored'
        + ('. Stopped: a provider reported exhaustion.' if exhausted else '')
    )
    return int(bool(failed) or exhausted)


if __name__ == '__main__':
    raise SystemExit(main())
