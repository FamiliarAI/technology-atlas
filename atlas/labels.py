"""Milestone labels: python3 -m atlas.labels ID_OR_FIELD ... [--missing] [--workers N] [--no-commit]."""

import argparse
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from ingestion.providers import Models

from . import core as records, store
from .core import CORE
from .store import CONFIG, ROOT

CALLS = ROOT / 'atlas/data/labels'
MODEL = 'gpt-6.1-sol'
SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['milestones'],
    'properties': {
        'milestones': {
            'type': 'array',
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'required': ['id', 'label'],
                'properties': {'id': {'type': 'string'}, 'label': {'type': 'string'}},
            },
        },
    },
}

PROMPT = (
    'You are writing short labels for the milestones of one proposed scientific or '
    'engineering breakthrough. Each milestone below is a completion criterion: a paragraph '
    'describing something a qualifying result must show.\n'
    '\n'
    'For each milestone write one label: a plain statement of what must be shown for that '
    'milestone to count as met.\n'
    '\n'
    'Rules:\n'
    '- 6 to 10 words, never more than 12. No full stop at the end.\n'
    '- Name the one core requirement. The paragraph holds the detail, so do not enumerate: '
    'never list more than three items, and prefer a summary noun ("full resource costs") '
    'to a list.\n'
    "- Say the concrete thing demonstrated, using this breakthrough's own terms, "
    'quantities and thresholds where the paragraph gives them. A reader who knows the '
    'field should be able to look at a paper and say yes or no.\n'
    '- Use only what the paragraph says. Do not add numbers, thresholds or requirements it '
    'does not contain.\n'
    '- Do not start with "Proposed" or "Optional". Do not hedge ("should", "may", "aims '
    'to"). If the paragraph says the milestone is an optional stronger result, start the '
    'label with "Stronger:".\n'
    "- Do not repeat the breakthrough's title. Make the labels of one breakthrough clearly "
    'different from each other.\n'
    '- A milestone about reporting, accounting, reproducibility or stated limits is still '
    'a milestone: name what must be reported or reproduced.\n'
    '\n'
    'Example. Paragraph: "Proposed demonstration: operate an encoded universal gate set, '
    'such as Clifford plus T, across a family of increasing code distances. On comparable '
    'logical workloads, show that error per operation decreases with distance, with '
    'quantified uncertainty…"\n'
    'Label: "Universal encoded gate set whose error per operation falls as code distance '
    'increases"\n'
    '\n'
    'Breakthrough: {title}\n'
    'What it is: {concept}\n'
    '\n'
    'Milestones:\n'
    '{milestones}\n'
    '\n'
    'Return every milestone id exactly once.\n'
)


def _call(identifier):
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = (CALLS / f'{identifier}-{stamp}').resolve()
    folder.mkdir(parents=True)
    entry = {'provider': 'codex', 'model': MODEL, 'effort': 'medium'}
    return folder, lambda prompt: Models(config).call('format', prompt, SCHEMA, folder, entry=entry)


def _written_before(identifier, milestones):
    for folder in sorted(CALLS.glob(f'{identifier}-*')):
        if (folder / 'success.json').is_file():
            return True
        # Legacy Grok calls have no success marker. A complete envelope must also
        # pass the label checks; failed or partial calls do not count.
        try:
            envelope = json.loads((folder / 'raw.json').read_text(encoding='utf-8'))
            if not isinstance(envelope, dict):
                continue
            if envelope.get('stopReason') != 'end_turn':
                continue
            if envelope.get('structuredOutputError') is not None:
                continue
            _validate(identifier, envelope.get('structuredOutput'), milestones)
        except (OSError, ValueError):
            continue
        return True
    return False


def _validate(identifier, result, milestones):
    def reject(reason):
        raise ValueError(f'{identifier}: {reason}')

    if not isinstance(result, dict) or set(result) != {'milestones'}:
        reject('answer does not match schema')
    rows = result['milestones']
    if not isinstance(rows, list):
        reject('milestones do not match schema')
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'id', 'label'}:
            reject('milestone does not match schema')
        if not isinstance(row['id'], str) or not isinstance(row['label'], str):
            reject('milestone id and label must be strings (schema)')
    ids = [row['id'] for row in rows]
    if len(ids) != len(set(ids)) or set(ids) != {m['id'] for m in milestones}:
        reject('returned milestone ids must match exactly, each once')
    seen = set()
    for row in rows:
        label = row['label']
        words = label.split()
        if len(words) < 3:
            reject(f'{row["id"]}: label must have at least 3 words')
        if len(words) > 12:
            reject(f'{row["id"]}: label exceeds 12 words')
        if len(label) > 100:
            reject(f'{row["id"]}: label exceeds 100 characters')
        if re.match(r'^(proposed|optional)\b', label.lstrip(), re.IGNORECASE):
            reject(f'{row["id"]}: forbidden first word')
        if label.rstrip().endswith('.'):
            reject(f'{row["id"]}: label ends with a full stop')
        if label.casefold() in seen:
            reject(f'{row["id"]}: duplicate label ignoring case')
        seen.add(label.casefold())
    return {row['id']: row['label'] for row in rows}


def _members(source, start):
    """Yield object keys and value spans without reserializing unrelated JSON bytes."""
    decoder = json.JSONDecoder()
    position = start + 1
    while True:
        position = re.compile(r'[\s,]*').match(source, position).end()
        if source[position] == '}':
            return
        key, end = decoder.raw_decode(source, position)
        position = re.compile(r'\s*:\s*').match(source, end).end()
        _, end = decoder.raw_decode(source, position)
        yield key, position, end
        position = end


def _replace_labels(source, milestones, replacements):
    start = next(
        a
        for key, a, _ in _members(source, len(source) - len(source.lstrip()))
        if key == 'completion_criteria'
    )
    position = start + 1
    edits = []
    for milestone in milestones:
        position = re.compile(r'[\s,]*').match(source, position).end()
        for key, begin, end in _members(source, position):
            if key == 'label' and milestone['label'] != replacements[milestone['id']]:
                value = json.dumps(replacements[milestone['id']], ensure_ascii=False)
                edits.append((begin, end, value))
        _, position = json.JSONDecoder().raw_decode(source, position)
    for begin, end, value in reversed(edits):
        source = source[:begin] + value + source[end:]
    return source


def _prepare(identifier, core):
    paths = [
        p for p in Path(core).glob('*/*.json') if p.stem == identifier and p.name != 'field.json'
    ]
    if len(paths) != 1:
        raise ValueError(f'{identifier}: expected exactly one breakthrough file')
    path = paths[0]
    source = path.read_bytes().decode('utf-8')
    item = json.loads(source)
    milestones = item['completion_criteria']
    prompt = PROMPT.format(
        title=item['title'],
        concept=item['concept'][0]['text'],
        milestones='\n'.join(f'{m["id"]}: {m["text"]}' for m in milestones),
    )
    return path, source, milestones, prompt


def _apply(identifier, prepared, result):
    path, source, milestones, _ = prepared
    replacements = _validate(identifier, result, milestones)
    updated = _replace_labels(source, milestones, replacements)
    if updated != source:
        path.write_bytes(updated.encode('utf-8'))
    return [(m['id'], m['label'], replacements[m['id']]) for m in milestones]


def relabel(identifier, call=None, core=CORE):
    """Replace one breakthrough's labels; return (id, old, new) in milestone order."""
    prepared = _prepare(identifier, core)
    folder = None
    if call is None:
        folder, call = _call(identifier)
    changes = _apply(identifier, prepared, call(prepared[3]))
    if folder is not None:
        _success(folder)
    return changes


def _success(folder):
    (folder / 'success.json').write_text(json.dumps({'model': MODEL}) + '\n', encoding='utf-8')


def main(argv=None, core=CORE):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('identifiers', nargs='*', metavar='ID_OR_FIELD')
    parser.add_argument(
        '--missing', action='store_true', help='skip previously labelled breakthroughs'
    )
    parser.add_argument('--workers', type=int, default=3, help='parallel model calls (default: 3)')
    parser.add_argument('--no-commit', action='store_true')
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error('--workers must be at least 1')
    if not args.identifiers and not args.missing:
        parser.error('name a breakthrough or field, or pass --missing')
    failed = False
    identifiers = []
    try:
        data = records.load(core)
    except (OSError, ValueError) as error:
        print(error)
        return 1
    for argument in args.identifiers:
        if Path(argument).name == argument and (Path(core) / argument).is_dir():
            identifiers.extend(
                identifier
                for identifier, item in data['breakthroughs'].items()
                if data.folders[identifier] == argument and item.get('status') == 'active'
            )
        elif argument in data['breakthroughs']:
            identifiers.append(argument)
        else:
            print(f'{argument}: unknown breakthrough or field')
            failed = True
    identifiers = list(dict.fromkeys(identifiers))

    if not args.identifiers and args.missing:
        identifiers = sorted(
            identifier
            for identifier, item in data['breakthroughs'].items()
            if item.get('status') == 'active'
        )

    folders = []
    completed = 0
    errors = (OSError, ValueError, RuntimeError, subprocess.SubprocessError)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = []
        for identifier in identifiers:
            try:
                prepared = _prepare(identifier, core)
                if args.missing and _written_before(identifier, prepared[2]):
                    continue
                folder, call = _call(identifier)
                jobs.append((identifier, folder, prepared, pool.submit(call, prepared[3])))
            except errors as error:
                print(f'{identifier}: {error}')
                failed = True
        # Only model calls run in workers. Apply and report in input order, even
        # when calls finish out of order; commit once after all writes finish.
        for identifier, folder, prepared, future in jobs:
            folders.append(str(folder.relative_to(ROOT) if folder.is_relative_to(ROOT) else folder))
            try:
                changes = _apply(identifier, prepared, future.result())
                _success(folder)
            except errors as error:
                print(f'{identifier}: {error}')
                failed = True
                continue
            completed += 1
            print(f'{identifier}: {len(changes)} labels')
            for milestone, old, new in changes:
                print(f'  {milestone}: {old} -> {new}')
    try:
        if completed:
            store.rebuild(core=core)
        if not args.no_commit and completed:
            message = (
                f'Relabel milestones for {", ".join(args.identifiers) or "missing"} '
                f'({completed} breakthroughs)\n\nModel: {MODEL}\nCalls:\n' + '\n'.join(folders)
            )
            records.commit(message)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(error)
        failed = True
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
