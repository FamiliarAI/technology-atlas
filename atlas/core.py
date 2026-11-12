"""File-backed atlas records: python3 -m atlas.core {import,check}."""

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import store

ROOT = store.ROOT
CORE = ROOT / 'atlas/core'


class _Loaded(dict):
    """Keep file locations for checking, outside the persisted records."""


def replace_text(path, text):
    """Write text to path atomically, so a concurrent reader sees the old or the new file."""
    path = Path(path)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(text, encoding='utf-8')
    os.replace(temp, path)


def _json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    replace_text(path, json.dumps(value, indent=1, ensure_ascii=False) + '\n')


def _rows(path):
    return (
        [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
        if path.exists()
        else []
    )


def write_breakthrough(item, core=CORE):
    prefix, identifier = item['field'], item['id']
    if any(
        not component or Path(component).name != component or component in ('.', '..')
        for component in (prefix, identifier)
    ):
        raise ValueError('Invalid field or breakthrough ID')
    _json(Path(core) / prefix / (identifier + '.json'), item)


def write_sources(sources, core=CORE):
    core = Path(core)
    core.mkdir(parents=True, exist_ok=True)
    replace_text(
        core / 'sources.jsonl',
        ''.join(json.dumps(sources[url], ensure_ascii=False) + '\n' for url in sorted(sources)),
    )


def write_progress(rows, core=CORE):
    core = Path(core)
    core.mkdir(parents=True, exist_ok=True)
    replace_text(
        core / 'progress.jsonl', ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows)
    )


def commit(message):
    """Commit atlas/core and nothing else; no change is not an error."""
    subprocess.run(['git', 'add', 'atlas/core'], cwd=ROOT, check=True)
    if subprocess.run(
        ['git', 'diff', '--cached', '--quiet', '--', 'atlas/core'], cwd=ROOT
    ).returncode:
        subprocess.run(['git', 'commit', '-m', message, '--', 'atlas/core'], cwd=ROOT, check=True)


def load(core=CORE):
    core = Path(core)
    if not core.is_dir():
        raise ValueError('Core folder does not exist: ' + str(core))
    data = _Loaded(fields={}, breakthroughs={}, sources={}, progress=_rows(core / 'progress.jsonl'))
    data.folders = {}
    for path in sorted(core.glob('*/*.json')):
        value = json.loads(path.read_text(encoding='utf-8'))
        if path.name == 'field.json':
            data['fields'][path.parent.name] = value
        else:
            if path.stem in data['breakthroughs']:
                raise ValueError('Duplicate breakthrough file: ' + path.stem)
            data['breakthroughs'][path.stem] = value
            data.folders[path.stem] = path.parent.name
    for source in _rows(core / 'sources.jsonl'):
        if source['url'] in data['sources']:
            raise ValueError('Duplicate source URL: ' + source['url'])
        data['sources'][source['url']] = source
    return data


def _merge_source(sources, source):
    url = source['url']
    saved = sources.setdefault(
        url, {key: source.get(key, '') for key in ('url', 'title', 'status')}
    )
    copies = saved.setdefault('copies', [])
    known = {artifact['sha256'] for artifact in copies}
    for artifact in source.get('artifacts', []):
        if artifact['sha256'] not in known:
            copies.append(
                {
                    key: value
                    for key, value in artifact.items()
                    if key not in ('path', 'absolute_path')
                }
            )
            known.add(artifact['sha256'])


def next_color(prefix, core=CORE):
    """A colour no imported field uses. Existing fields are never recoloured.

    store.color steps round the hue circle by position; the new field takes the first
    position whose colour is still free, so the result does not depend on import order.
    """
    used = set()
    for path in Path(core).glob('*/field.json'):
        used.add(json.loads(path.read_text(encoding='utf-8')).get('color'))
    position = 0
    while store.color(prefix, position) in used and position < 1000:
        position += 1
    return store.color(prefix, position)


def import_field(folder, core=CORE, color=None):
    folder, core = Path(folder), Path(core)
    raw = (folder / 'final-innovations.json').read_bytes()
    value = json.loads(raw)
    prefix = value['field']['prefix']
    if prefix != folder.name:
        raise ValueError('Field ID mismatch')
    if (core / prefix).exists():
        raise FileExistsError('Field already imported: ' + prefix)
    items = value['innovations']
    ids = [identifier['id'] for identifier in items]
    if (
        not items
        or len(ids) != len(set(ids))
        or any(
            not identifier.startswith(prefix + '-') or Path(identifier).name != identifier
            for identifier in ids
        )
    ):
        raise ValueError('Invalid breakthrough IDs')
    for item in items:
        for key in [
            'concept',
            'significance',
            'missing_breakthrough',
            'current_state',
            'completion_criteria',
            'related_concepts',
        ]:
            if not isinstance(item.get(key), list) or not item[key]:
                raise ValueError('Missing final section: ' + key)
    sources = {source['url']: source for source in _rows(core / 'sources.jsonl')}
    for item in items:
        item.update(field=prefix, status='active')
        for criterion_number, criterion in enumerate(item['completion_criteria'], 1):
            text = criterion['text']
            opening = text.split(':', 1)[0].strip()
            criterion.update(
                id=f'm{criterion_number}',
                label=opening if len(opening) <= 80 else ' '.join(text.split()[:8]),
            )
        for source in item.get('sources', []):
            _merge_source(sources, source)
        item['sources'] = [source['url'] for source in item.get('sources', [])]
        item['provenance'] = {
            kind: os.path.relpath((ROOT / location).resolve(), ROOT)
            for kind, location in item.get('provenance', {}).items()
        }
    field = {
        'id': prefix,
        'name': value['field']['field'],
        'color': color if color is not None else next_color(prefix, core),
    }
    field.update(
        {
            key: metadata
            for key, metadata in value['field'].items()
            if key not in ('prefix', 'field')
        }
    )
    field.update(
        created_at=value.get('created_at'),
        imported_from={
            'run_hash': store.sha(raw),
            'imported_at': datetime.now(timezone.utc).isoformat(),
        },
        original_dispositions=value.get('original_dispositions', []),
        reconciliation_change_log=value.get('reconciliation_change_log', []),
        withheld=value.get('withheld', []),
    )
    _json(core / prefix / 'field.json', field)
    for item in items:
        write_breakthrough(item, core)
    write_sources(sources, core)
    if not (core / 'progress.jsonl').exists():
        write_progress([], core)


def _check_brief(identifier, item, sources):
    """The reader's version names the record's milestones in order and only known sources."""
    brief = item['brief']
    if not isinstance(brief, dict):
        return [f'Brief is not an object: {identifier}']
    problems = []
    milestones = [criterion.get('id') for criterion in item['completion_criteria']]
    if [milestone.get('id') for milestone in brief.get('milestones', [])] != milestones:
        problems.append(f'Brief milestones do not match the record: {identifier}')
    urls = [source.get('url') for source in brief.get('sources', [])]
    if len(urls) != len(set(urls)):
        problems.append(f'Duplicate brief source: {identifier}')
    for url in urls:
        if url not in sources:
            problems.append(f'Unknown brief source: {identifier}: {url}')
    return problems


def check(data):
    problems = []
    fields = data['fields']
    items = data['breakthroughs']
    sources = data['sources']
    for prefix, field in fields.items():
        if field.get('id') != prefix:
            problems.append(f'Field ID does not match folder: {prefix}')
    for identifier, item in items.items():
        if item.get('id') != identifier:
            problems.append(f'Breakthrough ID does not match file: {identifier}')
        prefix = item.get('field')
        if (
            prefix not in fields
            or not identifier.startswith(str(prefix) + '-')
            or getattr(data, 'folders', {}).get(identifier, prefix) != prefix
        ):
            problems.append(f'Breakthrough field mismatch: {identifier}')
        milestones = [criterion.get('id') for criterion in item['completion_criteria']]
        if None in milestones or len(milestones) != len(set(milestones)):
            problems.append(f'Missing or duplicate milestone ID: {identifier}')
        if 'merged_into' in item and item['merged_into'] not in items:
            problems.append(f'Unknown merged_into: {identifier} -> {item["merged_into"]}')
        for url in item.get('sources', []):
            if url not in sources:
                problems.append(f'Unknown source: {identifier}: {url}')
        if 'brief' in item:
            problems += _check_brief(identifier, item, sources)
    for row_number, row in enumerate(data['progress'], 1):
        identifier = row.get('breakthrough')
        item = items.get(identifier)
        milestone = row.get('milestone')
        if item is None:
            problems.append(f'Unknown progress breakthrough: row {row_number}: {identifier}')
        elif 'milestone' not in row:
            problems.append(f'Missing progress milestone: row {row_number}')
        elif milestone is not None and milestone not in {
            criterion.get('id') for criterion in item['completion_criteria']
        }:
            problems.append(f'Unknown progress milestone: row {row_number}: {milestone}')
        if row.get('url') not in sources:
            problems.append(f'Unknown progress source: row {row_number}: {row.get("url")}')
        # milestone null: a step toward the breakthrough as a whole, which cannot meet it.
        verdicts = ('advances', 'contradicts')
        if milestone is not None:
            verdicts += ('meets',)
        if row.get('verdict') not in verdicts:
            problems.append(f'Invalid progress verdict: row {row_number}: {row.get("verdict")}')

    def paths(value, location):
        if isinstance(value, dict):
            for key, child in value.items():
                paths(child, location + '.' + key)
        elif isinstance(value, list):
            for row_number, child in enumerate(value):
                paths(child, location + f'[{row_number}]')
        elif isinstance(value, str) and value.startswith(('/Users/', '/private/')):
            problems.append('Absolute path: ' + location)

    paths(data, 'core')
    return problems


def main(argv=None, core=CORE):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['import', 'check'])
    args = parser.parse_args(argv)
    try:
        if args.command == 'import':
            roots = store.completed_fields()
            imported = []
            for prefix in sorted(roots):
                if not (Path(core) / prefix).exists():
                    import_field(roots[prefix], core)
                    imported.append(prefix)
            print('Imported:', ', '.join(imported) or 'already current')
        else:
            problems = check(load(core))
            for problem in problems:
                print(problem)
            return int(bool(problems))
    except (OSError, ValueError) as error:
        print(error)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
