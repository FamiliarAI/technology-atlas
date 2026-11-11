"""Milestone labels: python3 -m atlas.labels ID_OR_FIELD ... [--no-commit]."""

import argparse
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import core as records, store
from .core import CORE
from .store import CONFIG, ROOT

CALLS = ROOT / 'atlas/data/labels'
MODEL = 'grok-4.7'
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
    'describing something a qualifying result must show.\n\n'
    'For each milestone write one label: a plain statement of what must be shown for that '
    'milestone to count as met.\n\n'
    'Rules:\n'
    '- 6 to 10 words, never more than 12. No full stop at the end.\n'
    '- Name the one core requirement. The paragraph holds the detail, so do not enumerate: '
    'never list more than three items, and prefer a summary noun ("full resource costs") '
    'to a list.\n'
    '- Say the concrete thing demonstrated, using this breakthrough\'s own terms, quantities '
    'and thresholds where the paragraph gives them. A reader who knows the field should be '
    'able to look at a paper and say yes or no.\n'
    '- Use only what the paragraph says. Do not add numbers, thresholds or requirements it '
    'does not contain.\n'
    '- Do not start with "Proposed" or "Optional". Do not hedge ("should", "may", "aims to"). '
    'If the paragraph says the milestone is an optional stronger result, start the label '
    'with "Stronger:".\n'
    '- Do not repeat the breakthrough\'s title. Make the labels of one breakthrough clearly '
    'different from each other.\n'
    '- A milestone about reporting, accounting, reproducibility or stated limits is still '
    'a milestone: name what must be reported or reproduced.\n\n'
    'Example. Paragraph: "Proposed demonstration: operate an encoded universal gate set, '
    'such as Clifford plus T, across a family of increasing code distances. On comparable '
    'logical workloads, show that error per operation decreases with distance, with '
    'quantified uncertainty…"\n'
    'Label: "Universal encoded gate set whose error per operation falls as code distance '
    'increases"\n\n'
    'Breakthrough: {title}\n'
    'What it is: {concept}\n\n'
    'Milestones:\n'
    '{milestones}\n\n'
    'Return every milestone id exactly once.\n'
)


def _schema_args(schema_path):
    """Keep the CLI's schema transport in one place; currently pass inline JSON."""
    return ['--json-schema', schema_path.read_text(encoding='utf-8')]


def _call(identifier):
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    grok = str(Path(config['grok']).expanduser())
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = (CALLS / f'{identifier}-{stamp}').resolve()
    folder.mkdir(parents=True)
    schema = folder / 'schema.json'
    schema.write_text(json.dumps(SCHEMA, indent=2) + '\n', encoding='utf-8')

    def call(prompt):
        prompt_path = folder / 'prompt.md'
        prompt_path.write_text(prompt, encoding='utf-8')
        command = [
            grok, '-m', MODEL, '--reasoning-effort', 'high', '--tools', '',
            '--disable-web-search', '--no-subagents', '--no-plan', '--max-turns', '1',
            '--output-format', 'json',
        ]
        command += _schema_args(schema) + ['--prompt-file', str(prompt_path)]
        result = subprocess.run(command, cwd=folder, capture_output=True, check=False)
        (folder / 'raw.json').write_bytes(result.stdout)
        if result.returncode:
            raise ValueError(f'{identifier}: Grok exited with status {result.returncode}')
        try:
            envelope = json.loads(result.stdout)
        except (ValueError, UnicodeError) as error:
            raise ValueError(f'{identifier}: invalid Grok JSON output') from error
        if not isinstance(envelope, dict):
            raise ValueError(f'{identifier}: invalid Grok output envelope')
        if envelope.get('structuredOutputError') is not None:
            raise ValueError(f'{identifier}: {envelope["structuredOutputError"]}')
        if envelope.get('stopReason') != 'end_turn':
            raise ValueError(f'{identifier}: stopReason is not end_turn')
        if not isinstance(envelope.get('structuredOutput'), dict):
            raise ValueError(f'{identifier}: structuredOutput is not an object')
        return envelope['structuredOutput']

    return folder, call


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
    start = next(a for key, a, _ in _members(source, len(source) - len(source.lstrip()))
                 if key == 'completion_criteria')
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


def relabel(identifier, call=None, core=CORE):
    """Replace one breakthrough's labels; return (id, old, new) in milestone order."""
    paths = [p for p in Path(core).glob('*/*.json')
             if p.stem == identifier and p.name != 'field.json']
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
    if call is None:
        _, call = _call(identifier)
    replacements = _validate(identifier, call(prompt), milestones)
    updated = _replace_labels(source, milestones, replacements)
    if updated != source:
        path.write_bytes(updated.encode('utf-8'))
    return [(m['id'], m['label'], replacements[m['id']]) for m in milestones]


def main(argv=None, core=CORE):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('identifiers', nargs='+', metavar='ID_OR_FIELD')
    parser.add_argument('--no-commit', action='store_true')
    args = parser.parse_args(argv)
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
                identifier for identifier, item in data['breakthroughs'].items()
                if data.folders[identifier] == argument and item.get('status') == 'active'
            )
        elif argument in data['breakthroughs']:
            identifiers.append(argument)
        else:
            print(f'{argument}: unknown breakthrough or field')
            failed = True
    identifiers = list(dict.fromkeys(identifiers))

    def work(identifier):
        folder = None
        try:
            folder, call = _call(identifier)
            changes = relabel(identifier, call=call, core=core)
            return folder, changes, None
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            return folder, None, error

    folders = []
    completed = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for identifier, (folder, changes, error) in zip(
            identifiers, pool.map(work, identifiers)
        ):
            if folder is not None:
                folders.append(str(folder.relative_to(ROOT)))
            if error is not None:
                print(f'{identifier}: {error}')
                failed = True
                continue
            completed += 1
            print(f'{identifier}: {len(changes)} labels')
            for milestone, old, new in changes:
                print(f'  {milestone}: {old} -> {new}')
    try:
        store.rebuild(core=core)
        if not args.no_commit and completed:
            message = (
                f'Relabel milestones for {", ".join(args.identifiers)} '
                f'({completed} breakthroughs)\n\nModel: {MODEL}\nCalls:\n'
                + '\n'.join(folders)
            )
            records.commit(message)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(error)
        failed = True
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
