"""Run the complete field workflow with three refillable field slots."""

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import date
import json
from pathlib import Path
import subprocess
import uuid

from .pipeline import PROJECT, backup, locked
from .sources import digest, now, read_json, write_json

DEFAULT_ROOT = PROJECT / 'ingestion/runs/all-fields'
DEFAULT_BACKUPS = PROJECT.parent / '2026_Takeoff_backups/all-fields'
REVISION = '7bc3997d0e1ee3ccdb4073402fb9744827173dda'


def git_bytes(revision, path):
    return subprocess.check_output(['git', 'show', f'{revision}:{path}'], cwd=PROJECT)


def group_fields(milestones):
    rows = milestones.get('milestones', []) if isinstance(milestones, dict) else milestones
    groups = {}
    for row in rows:
        field = row['field']
        group = groups.setdefault(
            field, {'field': field, 'prefix': row['id'].rsplit('-', 1)[0], 'entries': []}
        )
        if row['id'].rsplit('-', 1)[0] != group['prefix']:
            raise ValueError(f'{field}: inconsistent original ID prefixes')
        group['entries'].append(row)
    prefixes = [g['prefix'] for g in groups.values()]
    if len(prefixes) != len(set(prefixes)):
        raise ValueError('Field prefixes are not unique')
    return list(groups.values())


def prepare(root=DEFAULT_ROOT, revision=REVISION, as_of=None, chemistry_root=None):
    root = Path(root).resolve()
    as_of = as_of or date.today().isoformat()
    date.fromisoformat(as_of)
    commit = subprocess.check_output(['git', 'rev-parse', revision], cwd=PROJECT, text=True).strip()
    canonical = git_bytes(commit, 'web/data/milestones.json')
    groups = group_fields(json.loads(canonical))
    if len(groups) != 66:
        raise ValueError(f'Expected 66 canonical fields, found {len(groups)}')
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / 'batch.json'
    if manifest_path.exists():
        old = read_json(manifest_path)
        if old['revision'] != commit or old['as_of'] != as_of:
            raise ValueError(
                'Batch already prepared with different revision/date; use its existing settings'
            )
        return old
    originals = root / 'originals'
    originals.mkdir(exist_ok=True)
    (originals / 'milestones.json').write_bytes(canonical)
    fields = []
    for group in groups:
        paths = sorted({e['provenance']['markdown'] for e in group['entries']})
        if len(paths) != 1:
            raise ValueError(f'{group["field"]}: expected one original markdown, found {paths}')
        raw = git_bytes(commit, paths[0])
        original = originals / (group['prefix'] + '.md')
        original.write_bytes(raw)
        original_json = originals / (group['prefix'] + '.json')
        write_json(original_json, group['entries'])
        field_root = root / group['prefix']
        prefix = group['prefix']
        if group['field'] == 'Chemistry':
            field_root = Path(chemistry_root or PROJECT / 'ingestion/runs/CHEMREV').resolve()
            if (field_root / 'field.json').exists():
                prefix = read_json(field_root / 'field.json')['prefix']
        boundaries = (
            f'{
                group[("field")]
            }: fundamental discoveries and enabling technologies within this field. '
            'Include cross-field consequences where the central advance belongs to this field; '
            'exclude routine incremental optimization. Use the historical breakthroughs in the '
            'prompt to calibrate revolutionary impact.'
        )
        fields.append(
            {
                'field': group['field'],
                'prefix': prefix,
                'original_prefix': group['prefix'],
                'root': str(field_root),
                'original_path': str(original),
                'original_json': str(original_json),
                'original_git_path': paths[0],
                'original_sha256': digest(raw),
                'original_count': len(group['entries']),
                'boundaries': boundaries,
                'status': 'pending',
            }
        )
    manifest = {
        'revision': commit,
        'as_of': as_of,
        'created_at': now(),
        'status': 'prepared',
        'workers': 3,
        'fields': fields,
    }
    save_manifest(root, manifest)
    return manifest


def save_manifest(root, manifest):
    """Only the batch controller writes the shared manifest."""
    manifest['updated_at'] = now()
    temporary = root / 'batch.next.json'
    write_json(temporary, manifest)
    temporary.replace(root / 'batch.json')
    lines = [
        '# Field ingestion progress',
        '',
        f'Original Git revision: `{manifest["revision"]}`',
        '',
        f'Batch status: **{manifest["status"]}**. Three active fields maximum.',
        '',
        '| Field | Status | Current step | Output |',
        '| --- | --- | --- | --- |',
    ]
    for entry in manifest['fields']:
        directory = Path(entry['root'])
        final = directory / 'final-innovations.md'
        phase = ''
        workflow = read_json(directory / 'workflow-receipt.json', {})
        if workflow:
            phase = str(workflow.get('stage', workflow.get('status', '')))
        output = f'[Final material]({final})' if entry['status'] == 'complete' else ''
        lines.append(f'| {entry["field"]} | {entry["status"]} | {phase} | {output} |')
    (root / 'progress.md').write_text('\n'.join(lines) + '\n')


def validate_final(root):
    """Check completion artifacts rather than trusting a worker's success return."""
    from .final_rewrite import FINAL_SCHEMA, validate_record, merge_records

    root = Path(root)
    output = read_json(root / 'final-innovations.json')
    if not output or not (root / 'final-innovations.md').is_file():
        raise ValueError('Final JSON and readable document are required')
    candidates = read_json(root / 'reconciled-candidates.json')
    reviews = read_json(root / 'reconciled-reviews.json')
    expected = [p['id'] for p in candidates['problems']]
    records = merge_records(output['innovations'], expected)
    for record in records:
        identifier = record['id']
        if reviews.get(identifier, {}).get('status') != 'complete':
            raise ValueError(f'{identifier}: review incomplete')
        review = Path(reviews[identifier]['path']) / 'validated.json'
        if read_json(review) != reviews[identifier]['review']:
            raise ValueError(f'{identifier}: validated review has changed')
        validate_record(
            {k: record[k] for k in FINAL_SCHEMA['properties']},
            {'candidate': {'id': identifier}, 'source_index': record['sources']},
        )
        for source in record['sources']:
            for artifact in source['artifacts']:
                path = Path(artifact['absolute_path'])
                if not path.is_file() or digest(path.read_bytes()) != artifact['sha256']:
                    raise ValueError(f'{identifier}: missing or changed source {path}')
    expected_originals = read_json(root / 'reconciled-structured.json')['original_dispositions']
    if output['original_dispositions'] != expected_originals:
        raise ValueError('Original-entry dispositions were not preserved')
    return {
        'concepts': len(records),
        'final_sha256': digest((root / 'final-innovations.json').read_bytes()),
    }


def backup_valid(entry):
    destination = entry.get('backup')
    if not destination:
        return False
    dest = Path(destination)
    receipt = read_json(dest / 'backup-verification.json', {})
    if receipt.get('source') != entry['root'] or not receipt.get('files'):
        return False
    for name, sha in receipt['files'].items():
        path = dest / name
        if not path.is_file() or digest(path.read_bytes()) != sha:
            return False
    return receipt['files'].get('final-innovations.json') == entry.get('final_sha256')


def finish_field(entry, as_of, backups, runner, backup_fn=backup):
    root = Path(entry['root'])
    # Existing Chemistry can bypass fresh research only when all final artifacts validate.
    try:
        validation = validate_final(root)
    except (ValueError, KeyError, TypeError, FileNotFoundError):
        runner(
            root,
            Path(entry['original_path']),
            entry['field'],
            entry['prefix'],
            as_of,
            entry['boundaries'],
        )
        validation = validate_final(root)
    if digest(Path(entry['original_path']).read_bytes()) != entry['original_sha256']:
        raise ValueError('Original field research changed since batch preparation')
    destination = Path(backups) / f'{entry["original_prefix"]}-{uuid.uuid4().hex}'
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup_fn(root, destination)
    result = {**validation, 'backup': str(destination), 'finished_at': now()}
    if not backup_valid({**entry, **result}):
        raise ValueError('External backup verification failed')
    return result


def write_aggregate(root, manifest):
    """Publish a deterministic collection only after every canonical field is complete."""
    entries = manifest['fields']
    if len(entries) != 66 or any(e['status'] != 'complete' for e in entries):
        raise ValueError('All 66 fields must be complete before aggregation')
    fields = []
    for entry in entries:
        path = Path(entry['root']) / 'final-innovations.json'
        if digest(path.read_bytes()) != entry['final_sha256']:
            raise ValueError(f'{entry["field"]}: final output changed before aggregation')
        value = read_json(path)
        fields.append(
            {
                'field': entry['field'],
                'prefix': entry['prefix'],
                'final_output': str(path),
                'final_sha256': entry['final_sha256'],
                'verified_backup': entry['backup'],
                'innovations': value['innovations'],
                'original_dispositions': value['original_dispositions'],
            }
        )
    aggregate = {
        'original_git_revision': manifest['revision'],
        'as_of': manifest['as_of'],
        'field_count': len(fields),
        'innovation_count': sum(len(f['innovations']) for f in fields),
        'fields': fields,
    }
    temporary = Path(root) / 'final-innovations.next.json'
    write_json(temporary, aggregate)
    temporary.replace(Path(root) / 'final-innovations.json')
    return aggregate


def run(root=DEFAULT_ROOT, backups=DEFAULT_BACKUPS, runner=None):
    root = Path(root).resolve()
    backups = Path(backups).resolve()
    if backups.is_relative_to(PROJECT):
        raise ValueError('Backups must be outside the project')
    from .field_workflow import run_field, AccountExhausted

    runner = runner or run_field
    with locked(root):
        manifest = read_json(root / 'batch.json')
        if not manifest:
            raise ValueError('Prepare the canonical roster first')
        pending = []
        for entry in manifest['fields']:
            if entry['status'] == 'complete':
                try:
                    validation = validate_final(entry['root'])
                    if validation['final_sha256'] == entry.get('final_sha256') and backup_valid(
                        entry
                    ):
                        continue
                except (ValueError, KeyError, TypeError, FileNotFoundError):
                    pass
            entry.update(status='pending')
            entry.pop('error', None)
            pending.append(entry)
        manifest['status'] = 'running'
        save_manifest(root, manifest)
        halted = False
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {}

            def refill():
                while pending and len(futures) < 3 and not halted:
                    entry = pending.pop(0)
                    entry.update(status='running', started_at=now())
                    futures[
                        pool.submit(finish_field, entry, manifest['as_of'], backups, runner)
                    ] = entry
                    print('START ' + entry['field'], flush=True)
                save_manifest(root, manifest)

            refill()
            while futures:
                done, _ = wait(futures, timeout=30, return_when=FIRST_COMPLETED)
                for future in done:
                    entry = futures.pop(future)
                    try:
                        entry.update(future.result())
                        entry['status'] = 'complete'
                        print('COMPLETE ' + entry['field'], flush=True)
                    except AccountExhausted as error:
                        entry.update(status='account_required', error=str(error))
                        halted = True
                        manifest.update(
                            status='account_required',
                            action=(
                                'Grok access exhausted. Ask the user to switch to the '
                                'second account; never request credentials.'
                            ),
                        )
                        print(manifest['action'], flush=True)
                    except Exception as error:
                        entry.update(status='failed', error=str(error))
                        print('FAILED ' + entry['field'] + ': ' + str(error), flush=True)
                refill()
        if not halted:
            manifest['status'] = (
                'complete'
                if all(e['status'] == 'complete' for e in manifest['fields'])
                else 'incomplete'
            )
        if manifest['status'] == 'complete':
            try:
                aggregate = write_aggregate(root, manifest)
                manifest['aggregate'] = {
                    'path': str(root / 'final-innovations.json'),
                    'innovations': aggregate['innovation_count'],
                }
            except Exception as error:
                manifest.update(status='incomplete', aggregate_error=str(error))
        save_manifest(root, manifest)
        return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    p.add_argument('--revision', default=REVISION)
    p.add_argument('--as-of', default=date.today().isoformat())
    p.add_argument('--chemistry-root', type=Path)
    p = sub.add_parser('run')
    p.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    p.add_argument('--backups', type=Path, default=DEFAULT_BACKUPS)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.root, args.revision, args.as_of, args.chemistry_root)
        print(f'Prepared {len(result["fields"])} fields: {args.root / "progress.md"}')
    else:
        result = run(args.root, args.backups)
        print(
            json.dumps(
                {
                    'status': result['status'],
                    'complete': sum(e['status'] == 'complete' for e in result['fields']),
                }
            )
        )
        if result['status'] != 'complete':
            raise SystemExit(2 if result['status'] == 'account_required' else 1)


if __name__ == '__main__':
    main()
