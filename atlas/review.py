"""The owner's review of breakthrough pages: which are published, and what happens to the rest.

    python3 -m atlas.review list [--state STATE]
    python3 -m atlas.review publish ID [ID ...]
    python3 -m atlas.review hold ID --note "needs a regulator source"
    python3 -m atlas.review merge ID --into OTHER [--note ...]
    python3 -m atlas.review revise ID --note "split m3"
    python3 -m atlas.review retire ID --note "duplicate of OTHER"
    python3 -m atlas.review clear ID

A decision is stored on the breakthrough record as `review`: {state, note, into, at, log}.
Only `published` changes what the public export contains; the other states record what the
owner wants done (hold for more research, merge, revise, retire) and change nothing else. Each
decision appends a row to `review.log`. atlas/core is committed unless --no-commit. The local
server offers the same decisions as buttons (atlas.server, /api/review).
"""

import argparse
import os
from datetime import datetime, timezone

from . import core as records
from .similar import LIKELY, Index, cosine, report

STATES = ('published', 'hold', 'merge', 'revise', 'retire')
VERBS = {
    'publish': 'published',
    'hold': 'hold',
    'merge': 'merge',
    'revise': 'revise',
    'retire': 'retire',
}
TRAILER = 'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'


class Refused(ValueError):
    """The decision cannot be recorded; nothing was written."""


def today():
    return datetime.now(timezone.utc).date().isoformat()


def problems(identifier, review, items):
    """What is wrong with a stored review; atlas.core.check calls this."""
    found = []
    if not isinstance(review, dict):
        return [f'Review is not an object: {identifier}']
    state = review.get('state')
    if state is not None and state not in STATES:
        found.append(f'Unknown review state: {identifier}: {state}')
    if state == 'published' and not items[identifier].get('page'):
        found.append(f'Published without a page: {identifier}')
    if state == 'merge' and review.get('into') not in items:
        found.append(f'Review merges into an unknown breakthrough: {identifier}')
    if review.get('into') == identifier:
        found.append(f'Review merges a breakthrough into itself: {identifier}')
    if not isinstance(review.get('log', []), list):
        found.append(f'Review log is not a list: {identifier}')
    return found


def decide(identifier, state, note=None, into=None, data=None, core=records.CORE):
    """Record one decision (state None clears it). Returns the stored review. Raises Refused."""
    data = data or records.load(core)
    items = data['breakthroughs']
    item = items.get(identifier)
    if item is None:
        raise Refused(f'No breakthrough has the ID {identifier}')
    if state is not None and state not in STATES:
        raise Refused(f'Unknown decision: {state}')
    if state == 'published' and not item.get('page'):
        raise Refused(f'{identifier} has no page yet; run atlas.page define first')
    if state == 'merge' and into not in items:
        raise Refused(f'Merge needs --into naming another breakthrough (got {into})')
    if into == identifier:
        raise Refused('A breakthrough cannot be merged into itself')
    if state in ('hold', 'revise', 'retire') and not (note or '').strip():
        raise Refused(f'A {state} decision needs a note saying why')
    note = (note or '').strip() or None
    review = dict(item.get('review') or {})
    log = list(review.get('log', []))
    log.append(
        {
            'date': today(),
            'state': state,
            **({'note': note} if note else {}),
            **({'into': into} if state == 'merge' else {}),
        }
    )
    review = {
        'state': state,
        'note': note,
        'into': into if state == 'merge' else None,
        'at': today(),
        'log': log,
    }
    item['review'] = review
    records.write_breakthrough(item, core)
    return review


def listing(data, state='any'):
    """Every active breakthrough with a page, or with a decision: (id, title, state, results)."""
    rows = []
    for identifier, item in sorted(data['breakthroughs'].items()):
        if item.get('status') == 'retired':
            continue
        page = item.get('page')
        review = item.get('review') or {}
        current = review.get('state')
        if not page and current is None:
            continue
        if state == 'none' and current is not None:
            continue
        if state not in ('any', 'none') and current != state:
            continue
        rows.append(
            {
                'id': identifier,
                'field': item['field'],
                'title': (page or {}).get('title') or item['title'],
                'state': current,
                'note': review.get('note'),
                'into': review.get('into'),
                'at': review.get('at'),
                'page': bool(page),
                'results': len((page or {}).get('results', [])),
                'judged': bool((page or {}).get('results_run')),
            }
        )
    return rows


def confirmed(item):
    return sum(1 for r in (item.get('page') or {}).get('results', []) if r.get('confirmed') is True)


def distinct(items, one, other):
    """Has a person said these two pages are different breakthroughs (record key `distinct`)?"""
    return other in items[one].get('distinct', []) or one in items[other].get('distinct', [])


def keep_apart(identifiers, core=records.CORE):
    """Mark each page distinct from the others, so automatic review never merges them."""
    data = records.load(core)
    for identifier in identifiers:
        if identifier not in data['breakthroughs']:
            raise Refused(f'No breakthrough {identifier}')
    for identifier in identifiers:
        item = data['breakthroughs'][identifier]
        others = [other for other in identifiers if other != identifier]
        item['distinct'] = sorted(set(item.get('distinct', [])) | set(others))
        records.write_breakthrough(item, core)


def automatic(data, claimed=(), core=records.CORE):
    """Publish judged pages and merge duplicates without a person (owner, 2026-11-14).

    The pool is every published page plus every judged page with no decision that no running
    pass has claimed. Taking the pool strongest first (most confirmed results, then ID), a
    page whose closest kept page scores at least similar.LIKELY is marked `merge` into it;
    otherwise it is kept and published. A published page can therefore give way to a stronger
    duplicate judged later. Merges that point at a page now merged are pointed on to its
    target. Decisions a person made other than publishing (hold, revise, retire, merge) are
    left alone. Returns {'published': [...], 'merged': [(id, into, score)], 'repointed': [...]}.
    """
    items = data['breakthroughs']

    def state(identifier):
        return (items[identifier].get('review') or {}).get('state')

    pool = [
        identifier
        for identifier, item in items.items()
        if item.get('status') == 'active'
        and item.get('page')
        and identifier not in claimed
        and (
            state(identifier) == 'published'
            or (state(identifier) is None and item['page'].get('results_run'))
        )
    ]
    pool.sort(key=lambda identifier: (-confirmed(items[identifier]), identifier))
    index = Index(data)
    kept, out = [], {'published': [], 'merged': [], 'repointed': []}
    for identifier in pool:
        vector = index.vectors[identifier]
        best = max(
            (
                (cosine(vector, index.vectors[other]), other)
                for other in kept
                if not distinct(items, identifier, other)
            ),
            default=(0, None),
        )
        if best[0] >= LIKELY:
            score, into = round(best[0], 3), best[1]
            note = (
                f'Automatic: duplicate of {into} (similarity {score}); {into} has '
                f'{confirmed(items[into])} confirmed results, this page {confirmed(items[identifier])}.'
            )
            items[identifier]['review'] = decide(identifier, 'merge', note, into, data, core)
            out['merged'].append((identifier, into, score))
        else:
            kept.append(identifier)
            if state(identifier) != 'published':
                items[identifier]['review'] = decide(identifier, 'published', data=data, core=core)
                out['published'].append(identifier)
    # A merge into a page that has itself been merged points on to where that page went.
    for identifier, item in items.items():
        review = item.get('review') or {}
        target = review.get('into')
        if review.get('state') != 'merge' or state(target) != 'merge':
            continue
        seen = {identifier}
        while state(target) == 'merge' and target not in seen:
            seen.add(target)
            target = items[target]['review']['into']
        if target != review['into'] and target != identifier:
            note = f'{review.get("note") or ""} Pointed on: {review["into"]} merged into {target}.'
            item['review'] = decide(identifier, 'merge', note.strip(), target, data, core)
            out['repointed'].append(identifier)
    return out


def main(argv=None, core=records.CORE):
    parser = argparse.ArgumentParser(description='Review breakthrough pages for publication.')
    steps = parser.add_subparsers(dest='step', required=True)
    shown = steps.add_parser('list', help='entries with a page or a decision')
    shown.add_argument('--state', default='any', choices=('any', 'none') + STATES)
    for verb in VERBS:
        sub = steps.add_parser(verb)
        sub.add_argument('ids', nargs='+', metavar='ID')
        sub.add_argument('--note')
        if verb == 'merge':
            sub.add_argument('--into', required=True)
        sub.add_argument('--no-commit', action='store_true')
    clear = steps.add_parser('clear', help='remove the decision (back to draft)')
    clear.add_argument('ids', nargs='+', metavar='ID')
    clear.add_argument('--no-commit', action='store_true')
    apart = steps.add_parser('distinct', help='mark pages as different breakthroughs')
    apart.add_argument('ids', nargs='+', metavar='ID')
    apart.add_argument('--no-commit', action='store_true')
    auto = steps.add_parser('auto', help='publish judged pages, merging duplicates')
    auto.add_argument('--locks', help='folder of claim files (atlas.page); claimed pages wait')
    auto.add_argument('--no-commit', action='store_true')
    args = parser.parse_args(argv)
    data = records.load(core)
    if args.step == 'auto':
        claimed = set()
        if args.locks and os.path.isdir(args.locks):
            claimed = {name.split('-', 1)[1].rsplit('.', 1)[0] for name in os.listdir(args.locks)}
        out = automatic(data, claimed, core)
        for identifier, into, score in out['merged']:
            print(f'{identifier}: merge into {into} (similarity {score})')
        print(
            f'{len(out["published"])} published, {len(out["merged"])} merged, '
            f'{len(out["repointed"])} merges pointed on'
        )
        changed = out['published'] or out['merged'] or out['repointed']
        if changed:
            found = records.check(records.load(core))
            if found:
                print('atlas/core check failed:\n' + '\n'.join(found))
                return 1
            if not args.no_commit:
                records.commit(
                    f'Review (automatic): {len(out["published"])} published, '
                    f'{len(out["merged"])} merged as duplicates\n\n{TRAILER}'
                )
        return 0
    if args.step == 'distinct':
        try:
            keep_apart(args.ids, core)
        except Refused as error:
            print(error)
            return 1
        print(f'Kept apart: {", ".join(args.ids)}')
        if not args.no_commit:
            records.commit(f'Review: keep {", ".join(args.ids)} apart\n\n{TRAILER}')
        return 0
    if args.step == 'list':
        rows = listing(data, args.state)
        for row in rows:
            extra = f' -> {row["into"]}' if row['into'] else ''
            note = f'  ({row["note"]})' if row['note'] else ''
            print(
                f'{row["id"]:<12} {row["state"] or "draft":<9}{extra} '
                f'{row["results"]:>3} results  {row["title"]}{note}'
            )
        print(f'{len(rows)} entries')
        return 0
    state = None if args.step == 'clear' else VERBS[args.step]
    done = []
    index = Index(data) if state == 'published' else None
    for identifier in args.ids:
        if index is not None and identifier in index.vectors:
            # A quick look for a page already published that says the same thing. It never
            # stops the decision: the owner reads the list.
            print(f'{identifier}: closest published pages')
            print('\n'.join(report(index.nearest(identifier, 'published'))))
        try:
            decide(
                identifier, state, args.__dict__.get('note'), args.__dict__.get('into'), data, core
            )
        except Refused as error:
            print(f'{identifier}: not recorded: {error}')
            continue
        done.append(identifier)
        print(f'{identifier}: {state or "cleared"}')
    if not done:
        return 1
    found = records.check(records.load(core))
    if found:
        print('atlas/core check failed:\n' + '\n'.join(found))
        return 1
    if not args.no_commit:
        records.commit(review_message(state, done))
    return 0 if len(done) == len(args.ids) else 1


def review_message(state, done):
    verb = {None: 'Clear review of'}.get(state, f'Review: {state}')
    shown = ', '.join(done[:6]) + (f' and {len(done) - 6} more' if len(done) > 6 else '')
    return f'{verb} {shown}\n\n{TRAILER}'


if __name__ == '__main__':
    raise SystemExit(main())
