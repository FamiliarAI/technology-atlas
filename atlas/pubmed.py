"""Re-capture PubMed cookie walls: python3 -m atlas.pubmed [ID ...] [--list] [--no-commit].

A PubMed page often reaches the capture code as a short "Cookies must be enabled" page. For each
PubMed source of the named breakthroughs whose fullest saved copy has under 1,000 characters of
text, this fetches the abstract from NCBI E-utilities and, when it names one, the PMC article,
and records them as `alternative` copies of the same source, rebuilds and commits atlas/core
unless --no-commit. No model calls.

--list counts, without fetching, the PubMed sources that would be re-captured: those of the named
breakthroughs, or of the whole atlas when none is named.
"""

import argparse
from contextlib import closing

from ingestion.sources import MIN_TEXT, Archive, pubmed_id

from . import add as adding, core as records, store
from .core import CORE
from .store import DB, connect


def sources_of(data, identifier):
    """A breakthrough's sources: its record's, then URLs of its judged rows."""
    urls = list(data['breakthroughs'][identifier].get('sources', []))
    for row in data['progress']:
        if row['breakthrough'] == identifier and row['url'] not in urls:
            urls.append(row['url'])
    return urls


def short(data, urls, db):
    """The PubMed URLs among urls whose fullest saved copy has under MIN_TEXT characters."""
    found = []
    for url in dict.fromkeys(urls):
        if pubmed_id(url) is None or url not in data['sources']:
            continue
        chosen = adding.best(adding.known_copies(data['sources'][url], db))
        if chosen is None or len(chosen[2].strip()) < MIN_TEXT:
            found.append(url)
    return found


def recapture(urls, core=CORE, path=DB, archive=None):
    """Fetch the abstract and PMC copies for urls and record them. Returns {url: characters of
    the fullest copy afterwards}."""
    archive = archive or Archive(adding.ADDED)
    data = records.load(core)
    result = {}
    for url in urls:
        archive.pubmed(url)
        source = data['sources'][url]
        known = {copy['sha256'] for copy in source['copies']}
        for copy in adding.captured(url):
            if copy['sha256'] not in known and copy['kind'] == 'alternative':
                source['copies'].append(copy)
        texts = [len(item['text'].strip()) for item in archive.evidence(url)]
        result[url] = max(texts, default=0)
        if result[url] >= MIN_TEXT:
            source['status'] = 'saved'
    records.write_sources(data['sources'], core)
    store.rebuild(core=core, path=path)
    return result


def main(argv=None, core=CORE, path=DB):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('identifiers', nargs='*', metavar='ID')
    parser.add_argument('--list', action='store_true', help='count only; fetch nothing')
    parser.add_argument('--no-commit', action='store_true')
    args = parser.parse_args(argv)
    if not args.identifiers and not args.list:
        parser.error('name breakthroughs, or pass --list')
    data = records.load(core)
    for identifier in args.identifiers:
        if identifier not in data['breakthroughs']:
            parser.error(f'{identifier}: unknown breakthrough')
    if args.identifiers:
        urls = [url for identifier in args.identifiers for url in sources_of(data, identifier)]
    else:
        urls = list(data['sources'])
    with closing(connect(path)) as db:
        found = short(data, urls, db)
    total = sum(1 for url in dict.fromkeys(urls) if pubmed_id(url))
    print(f'{len(found)} of {total} PubMed sources have under {MIN_TEXT} characters of saved text')
    if args.list:
        for url in found:
            print('  ' + url)
        return 0
    result = recapture(found, core, path)
    for url, characters in result.items():
        print(f'  {url}: {characters} characters')
    if not args.no_commit and result:
        records.commit(
            f'Re-capture {len(result)} PubMed sources for {", ".join(args.identifiers)}\n\n'
            'Abstracts from NCBI E-utilities and PMC pages, recorded as alternative copies.'
        )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
