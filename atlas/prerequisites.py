"""Prerequisite order: python3 -m atlas.prerequisites FIELD [FIELD ...] | --all.

One model call per field sees that field's breakthroughs in full and a one-line catalog of
every breakthrough, and returns what each of the field's breakthroughs needs and what needs it.
Links are stored inside the dependent breakthrough's record as
prerequisites: [{id, reason, model, field}], where field is the call that produced the link.
Re-running a field replaces that field's links in atlas/core/, then rebuilds the database.
"""

import argparse
import json
from contextlib import closing
from datetime import datetime, timezone

from ingestion.pipeline import Models
from . import core as records, store
from .core import CORE
from .store import CONFIG, DB, ROOT, connect

CALLS = ROOT / 'atlas/data/prerequisites'
ID = r'^[A-Z]{2,8}-\d{2}$'

LINKS = {
    'type': 'array',
    'items': {
        'type': 'object',
        'additionalProperties': False,
        'required': ['id', 'reason'],
        'properties': {
            'id': {'type': 'string', 'pattern': ID},
            'reason': {'type': 'string', 'minLength': 20, 'maxLength': 400},
        },
    },
}
# One entry per breakthrough of the field, so each one is considered in turn.
SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['breakthroughs'],
    'properties': {
        'breakthroughs': {
            'type': 'array',
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'required': ['breakthrough', 'needs', 'needed_by'],
                'properties': {
                    'breakthrough': {'type': 'string', 'pattern': ID},
                    'needs': LINKS,
                    'needed_by': LINKS,
                },
            },
        }
    },
}

PROMPT = (
    'You are ordering proposed future breakthroughs into a technology tree.\n'
    '\n'
    'A link "A needs B" means B is expected to come first on the way to A: A builds on B, '
    "uses B as a component, its milestones assume B's result, or B is the expected route "
    'to A even if other routes are conceivable. It is not enough that B would merely help, '
    'speed up, or share a topic with A, or that the two are discussed together. If A and B '
    'describe essentially the same capability, there is no link.\n'
    '\n'
    'Below are the breakthroughs of one field in full, then a one-line catalog of every '
    "breakthrough in every field. Return one entry for each of this field's breakthroughs, "
    'in order. For each, look through the whole catalog, in every field:\n'
    '- needs: the breakthroughs it builds on.\n'
    '- needed_by: the breakthroughs that build on it.\n'
    'Use only IDs from the catalog. reason: one sentence naming the specific capability '
    'the dependent breakthrough takes from the other.\n'
    '\n'
    'Most breakthroughs have zero to three prerequisites.\n'
    '\n'
    'Field: {name} ({prefix})\n'
    '\n'
    '{field}\n'
    '\n'
    'Catalog:\n'
    '{catalog}\n'
)


def describe(item):
    parts = [f'## {item["id"]}: {item["title"]}']
    for key, label in [
        ('concept', 'Concept'),
        ('missing_breakthrough', 'What is still missing'),
        ('related_concepts', 'Related'),
    ]:
        parts.append(label + ': ' + ' '.join(paragraph['text'] for paragraph in item[key]))
    parts += [
        f'Milestone {criterion_number}: {criterion["text"]}'
        for criterion_number, criterion in enumerate(item['completion_criteria'], 1)
    ]
    return '\n'.join(parts)


def reaches(graph, start, target):
    """True when start transitively needs target."""
    seen, stack = set(), [start]
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node not in seen:
            seen.add(node)
            stack.extend(graph.get(node, ()))
    return False


def _call(prefix, config):
    calls = CALLS / f'{prefix}-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")}'
    calls.mkdir(parents=True)
    return calls, lambda prompt: Models(config).call('format', prompt, SCHEMA, calls)


def run(prefix, call=None, path=DB, core=CORE):
    (
        """One model call for one field; stores links that pass the checks. Returns """
        """(stored, rejected)."""
    )
    with closing(connect(path)) as db:
        field = db.execute('SELECT name FROM fields WHERE id=?', (prefix,)).fetchone()
        if not field:
            raise SystemExit('Unknown field ' + prefix)
        names = dict(db.execute('SELECT id, name FROM fields').fetchall())
        rows = {
            row['id']: (row['field'], json.loads(row['payload']))
            for row in db.execute('SELECT id, field, payload FROM breakthroughs ORDER BY id')
        }
        catalog = '\n'.join(
            f'- {identifier} [{names[field_prefix]}] {item["title"]}: '
            f'{item["concept"][0]["text"][:200]}'
            for identifier, (field_prefix, item) in rows.items()
        )
        mine = '\n\n'.join(
            describe(item) for field_prefix, item in rows.values() if field_prefix == prefix
        )
        config = json.loads(CONFIG.read_text())
        model = config['format']['model']
        if call is None:
            _, call = _call(prefix, config)
        result = call(PROMPT.format(name=field['name'], prefix=prefix, field=mine, catalog=catalog))

        # Edit file records, whose sources are URLs, rather than expanded DB payloads.
        data = records.load(core)
        rows = {
            identifier: (field_prefix, data['breakthroughs'][identifier])
            for identifier, (field_prefix, _) in rows.items()
        }
        before = {identifier: json.dumps(item) for identifier, (_, item) in rows.items()}
        # This field's earlier links are replaced; links from other fields' calls stay.
        for _, item in rows.values():
            if 'prerequisites' in item:
                item['prerequisites'] = [
                    prerequisite
                    for prerequisite in item['prerequisites']
                    if prerequisite['field'] != prefix
                ]
        graph = {
            identifier: {prerequisite['id'] for prerequisite in item.get('prerequisites', [])}
            for identifier, (_, item) in rows.items()
        }
        links = [
            (entry['breakthrough'], neighbor['id'], neighbor['reason'])
            for entry in result['breakthroughs']
            for neighbor in entry['needs']
        ]
        links += [
            (neighbor['id'], entry['breakthrough'], neighbor['reason'])
            for entry in result['breakthroughs']
            for neighbor in entry['needed_by']
        ]
        # A link reported from both sides is one link; the first reason is kept.
        unique_links = {
            (dependent, prerequisite_id): (dependent, prerequisite_id, reason)
            for dependent, prerequisite_id, reason in reversed(links)
        }
        links = list(unique_links.values())[::-1]
        stored, rejected = [], []
        for dependent, prerequisite_id, reason in links:
            link = {'breakthrough': dependent, 'needs': prerequisite_id, 'reason': reason}
            if dependent not in rows or prerequisite_id not in rows:
                why = 'unknown ID'
            elif dependent == prerequisite_id:
                why = 'links to itself'
            elif prefix not in (rows[dependent][0], rows[prerequisite_id][0]):
                why = 'neither side in this field'
            elif prerequisite_id in graph[dependent]:
                why = 'duplicate'
            elif reaches(graph, prerequisite_id, dependent):
                why = 'closes a loop'
            else:
                graph[dependent].add(prerequisite_id)
                rows[dependent][1].setdefault('prerequisites', []).append(
                    {'id': prerequisite_id, 'reason': reason, 'model': model, 'field': prefix}
                )
                stored.append(link)
                continue
            rejected.append((link, why))
        for identifier, (_, item) in rows.items():
            if json.dumps(item) != before[identifier]:
                records.write_breakthrough(item, core)
    store.rebuild(core=core, path=path)
    return stored, rejected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fields', nargs='*')
    parser.add_argument('--all', action='store_true', help='every imported field, one call each')
    parser.add_argument(
        '--no-commit', action='store_true', help='write core and rebuild without committing'
    )
    args = parser.parse_args()
    with closing(connect(DB)) as db:
        prefixes = (
            [row['id'] for row in db.execute('SELECT id FROM fields ORDER BY id')]
            if args.all
            else args.fields
        )
    if not prefixes:
        parser.error('name a field or pass --all')
    config = json.loads(CONFIG.read_text())
    calls = []
    total = 0
    for prefix in prefixes:
        folder, call = _call(prefix, config)
        calls.append(str(folder.relative_to(ROOT) if folder.is_relative_to(ROOT) else folder))
        stored, rejected = run(prefix, call=call)
        total += len(stored)
        print(f'{prefix}: {len(stored)} stored, {len(rejected)} rejected')
        for link in stored:
            print(f'  stored   {link["breakthrough"]} needs {link["needs"]}: {link["reason"]}')
        for link, why in rejected:
            print(f'  rejected {link["breakthrough"]} needs {link["needs"]}: {why}')
    if not args.no_commit:
        message = (
            f'Update prerequisites for {(", ").join(prefixes)} ({total} links)\n\nModel: {
                config[("format")][("model")]
            }\nCalls:\n'
            + '\n'.join(calls)
        )
        records.commit(message)


if __name__ == '__main__':
    main()
