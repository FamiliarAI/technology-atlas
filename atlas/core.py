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


def _json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')


def _rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] if path.exists() else []


def write_breakthrough(item, core=CORE):
    prefix, identifier = item['field'], item['id']
    if any(not s or Path(s).name != s or s in ('.', '..') for s in (prefix, identifier)):
        raise ValueError('Invalid field or breakthrough ID')
    _json(Path(core) / prefix / (identifier + '.json'), item)


def write_sources(sources, core=CORE):
    core = Path(core); core.mkdir(parents=True, exist_ok=True)
    (core / 'sources.jsonl').write_text(''.join(json.dumps(sources[url], ensure_ascii=False) + '\n' for url in sorted(sources)), encoding='utf-8')


def write_progress(rows, core=CORE):
    core = Path(core); core.mkdir(parents=True, exist_ok=True)
    (core / 'progress.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')


def commit(message):
    """Commit atlas/core and nothing else; no change is not an error."""
    subprocess.run(['git', 'add', 'atlas/core'], cwd=ROOT, check=True)
    if subprocess.run(['git', 'diff', '--cached', '--quiet', '--', 'atlas/core'], cwd=ROOT).returncode:
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
    saved = sources.setdefault(url, {k: source.get(k, '') for k in ('url', 'title', 'status')})
    copies = saved.setdefault('copies', [])
    known = {a['sha256'] for a in copies}
    for artifact in source.get('artifacts', []):
        if artifact['sha256'] not in known:
            copies.append({k: v for k, v in artifact.items() if k not in ('path', 'absolute_path')})
            known.add(artifact['sha256'])


def import_field(folder, core=CORE, color=None):
    folder, core = Path(folder), Path(core)
    raw = (folder / 'final-innovations.json').read_bytes()
    value = json.loads(raw); prefix = value['field']['prefix']
    if prefix != folder.name:
        raise ValueError('Field ID mismatch')
    if (core / prefix).exists():
        raise FileExistsError('Field already imported: ' + prefix)
    items = value['innovations']; ids = [i['id'] for i in items]
    if not items or len(ids) != len(set(ids)) or any(not i.startswith(prefix + '-') or Path(i).name != i for i in ids):
        raise ValueError('Invalid breakthrough IDs')
    for item in items:
        for key in ['concept', 'significance', 'missing_breakthrough', 'current_state', 'completion_criteria', 'related_concepts']:
            if not isinstance(item.get(key), list) or not item[key]:
                raise ValueError('Missing final section: ' + key)
    sources = {s['url']: s for s in _rows(core / 'sources.jsonl')}
    for item in items:
        item.update(field=prefix, status='active')
        for n, criterion in enumerate(item['completion_criteria'], 1):
            text = criterion['text']; opening = text.split(':', 1)[0].strip()
            criterion.update(id=f'm{n}', label=opening if len(opening) <= 80 else ' '.join(text.split()[:8]))
        for source in item.get('sources', []):
            _merge_source(sources, source)
        item['sources'] = [s['url'] for s in item.get('sources', [])]
        item['provenance'] = {kind: os.path.relpath((ROOT / loc).resolve(), ROOT) for kind, loc in item.get('provenance', {}).items()}
    field = {'id': prefix, 'name': value['field']['field'], 'color': color if color is not None else store.color(prefix, 0)}
    field.update({k: v for k, v in value['field'].items() if k not in ('prefix', 'field')})
    field.update(created_at=value.get('created_at'), imported_from={'run_hash': store.sha(raw), 'imported_at': datetime.now(timezone.utc).isoformat()}, original_dispositions=value.get('original_dispositions', []), reconciliation_change_log=value.get('reconciliation_change_log', []))
    _json(core / prefix / 'field.json', field)
    for item in items:
        write_breakthrough(item, core)
    write_sources(sources, core)
    if not (core / 'progress.jsonl').exists():
        write_progress([], core)


def check(data):
    problems = []; fields = data['fields']; items = data['breakthroughs']; sources = data['sources']
    for prefix, field in fields.items():
        if field.get('id') != prefix:
            problems.append(f'Field ID does not match folder: {prefix}')
    for identifier, item in items.items():
        if item.get('id') != identifier:
            problems.append(f'Breakthrough ID does not match file: {identifier}')
        prefix = item.get('field')
        if prefix not in fields or not identifier.startswith(str(prefix) + '-') or getattr(data, 'folders', {}).get(identifier, prefix) != prefix:
            problems.append(f'Breakthrough field mismatch: {identifier}')
        milestones = [c.get('id') for c in item['completion_criteria']]
        if None in milestones or len(milestones) != len(set(milestones)):
            problems.append(f'Missing or duplicate milestone ID: {identifier}')
        for link in item.get('prerequisites', []):
            if link['id'] not in items:
                problems.append(f'Unknown prerequisite: {identifier} -> {link["id"]}')
        if 'merged_into' in item and item['merged_into'] not in items:
            problems.append(f'Unknown merged_into: {identifier} -> {item["merged_into"]}')
        for url in item.get('sources', []):
            if url not in sources:
                problems.append(f'Unknown source: {identifier}: {url}')
    visiting, visited = set(), set()

    def visit(identifier):
        if identifier in visiting:
            problems.append('Prerequisite loop: ' + identifier)
            return
        if identifier in visited:
            return
        visiting.add(identifier)
        for link in items[identifier].get('prerequisites', []):
            if link['id'] in items:
                visit(link['id'])
        visiting.remove(identifier); visited.add(identifier)

    for identifier in items:
        visit(identifier)
    for n, row in enumerate(data['progress'], 1):
        identifier = row.get('breakthrough'); item = items.get(identifier)
        if item is None:
            problems.append(f'Unknown progress breakthrough: row {n}: {identifier}')
        elif row.get('milestone') not in {c.get('id') for c in item['completion_criteria']}:
            problems.append(f'Unknown progress milestone: row {n}: {row.get("milestone")}')
        if row.get('url') not in sources:
            problems.append(f'Unknown progress source: row {n}: {row.get("url")}')
        if row.get('verdict') not in ('advances', 'meets', 'contradicts'):
            problems.append(f'Invalid progress verdict: row {n}: {row.get("verdict")}')

    def paths(value, location):
        if isinstance(value, dict):
            for key, child in value.items(): paths(child, location + '.' + key)
        elif isinstance(value, list):
            for n, child in enumerate(value): paths(child, location + f'[{n}]')
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
            for n, prefix in enumerate(sorted(roots)):
                if not (Path(core) / prefix).exists():
                    import_field(roots[prefix], core, color=store.color(prefix, n))
                    imported.append(prefix)
            print('Imported:', ', '.join(imported) or 'already current')
        else:
            problems = check(load(core))
            for problem in problems: print(problem)
            return int(bool(problems))
    except (OSError, ValueError) as error:
        print(error)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
