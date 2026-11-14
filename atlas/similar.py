"""Near-duplicate search over breakthroughs: python3 -m atlas.similar ID [--among published|all].

Each breakthrough is turned into one text (its page's title, definition, completion test and
milestone titles; the record's title and first concept paragraph when it has no page) and each
text into a vector. The closest vectors by cosine similarity are the likely duplicates.

The vectors come from an Embedder. The one used now, Tfidf, is computed locally from the texts
themselves: no model, no download, no key. It finds texts that share wording, not synonyms.
An embedding model (for example Cloudflare Workers AI, with the vectors kept in Vectorize) can
replace it by providing the same two methods; nothing else changes.

A match never blocks anything: the review shows the closest pages and the owner decides.
"""

import argparse
import math
import re
from collections import Counter

from . import core as records

WORD = re.compile(r'[a-z0-9][a-z0-9\-]*[a-z0-9]|[a-z0-9]')
# Words that say nothing about which breakthrough a text is about.
COMMON = frozenset(
    """a an and are as at be by can for from has have in into is it its of on or that the
    their this to under using via when where which while with within without one two each
    any all more than per not no breakthrough atlas milestone completion criterion""".split()
)
# At or above this score a match is flagged. Set from the first look (November 14): CSC-01 and
# MAT-01, both P versus NP, scored 0.31; unrelated pages in one field score under 0.1.
LIKELY = 0.25


def text_of(item):
    """The text that stands for one breakthrough."""
    page = item.get('page')
    if page:
        parts = [page.get('title') or '', page.get('definition') or '']
        completion = page.get('completion') or {}
        parts += [completion.get('title') or '', completion.get('criterion') or '']
        parts += [
            milestone.get('title') or ''
            for milestone in page.get('milestones', [])
            if milestone.get('status', 'active') == 'active'
        ]
    else:
        concept = item.get('concept') or []
        parts = [item.get('title') or '', concept[0]['text'] if concept else '']
    return '\n'.join(part for part in parts if part)


def terms(text):
    words = [word for word in WORD.findall(text.lower()) if word not in COMMON]
    return words + [f'{a} {b}' for a, b in zip(words, words[1:])]


class Tfidf:
    """Sparse TF-IDF vectors (words and word pairs, sublinear counts), unit length."""

    name = 'tfidf'

    def fit(self, texts):
        counts = [Counter(terms(text)) for text in texts]
        documents = Counter(term for count in counts for term in count)
        total = len(texts)
        self.weight = {term: math.log((1 + total) / (1 + n)) + 1 for term, n in documents.items()}
        return self

    def embed(self, text):
        vector = {
            term: (1 + math.log(n)) * self.weight.get(term, 0)
            for term, n in Counter(terms(text)).items()
        }
        length = math.sqrt(sum(value * value for value in vector.values())) or 1
        return {term: value / length for term, value in vector.items() if value}


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(value * b.get(term, 0) for term, value in a.items())


class Index:
    """Vectors for the active breakthroughs, built from atlas/core."""

    def __init__(self, data, embedder=None):
        self.items = {
            identifier: item
            for identifier, item in data['breakthroughs'].items()
            if item.get('status') != 'retired'
        }
        texts = {identifier: text_of(item) for identifier, item in self.items.items()}
        self.embedder = embedder or Tfidf().fit(list(texts.values()))
        self.vectors = {identifier: self.embedder.embed(text) for identifier, text in texts.items()}

    def nearest(self, identifier, among='published', k=5):
        """[{id, title, score, state}] closest first; among is 'published' or 'all'."""
        query = self.vectors[identifier]
        rows = []
        for other, vector in self.vectors.items():
            if other == identifier:
                continue
            item = self.items[other]
            state = (item.get('review') or {}).get('state')
            if among == 'published' and state != 'published':
                continue
            score = cosine(query, vector)
            if score > 0:
                title = (item.get('page') or {}).get('title') or item['title']
                rows.append({'id': other, 'title': title, 'score': round(score, 3), 'state': state})
        rows.sort(key=lambda row: -row['score'])
        return rows[:k]


def report(rows):
    if not rows:
        return ['  no published page shares its wording']
    return [
        f'  {row["score"]:.2f} {row["id"]:<12} {row["title"]}'
        + ('   <- likely duplicate' if row['score'] >= LIKELY else '')
        for row in rows
    ]


def main(argv=None, core=records.CORE):
    parser = argparse.ArgumentParser(description='Find near-duplicate breakthroughs.')
    parser.add_argument('ids', nargs='+', metavar='ID')
    parser.add_argument('--among', choices=('published', 'all'), default='all')
    parser.add_argument('-k', type=int, default=5)
    args = parser.parse_args(argv)
    index = Index(records.load(core))
    for identifier in args.ids:
        if identifier not in index.vectors:
            print(f'{identifier}: not an active breakthrough')
            continue
        print(f'{identifier}: closest {args.among}')
        print('\n'.join(report(index.nearest(identifier, args.among, args.k))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
