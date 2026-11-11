"""Run with python3 -m ingestion.pipeline --help from the repository root."""

import argparse
import copy
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import re
import shutil

import jsonschema
from . import schemas
from .providers import Models, execute  # noqa: F401  (atlas/add.py and prerequisites.py)
from .sources import Archive, digest, now, web_url, write_json

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
KINDS = {'problem', 'completion', 'current_state', 'significance'}


def fingerprint(value):
    return digest(json.dumps(value, sort_keys=True).encode())


def prompt(name, **values):
    text = (HERE / 'prompts' / f'{name}.md').read_text()
    # One substitution pass: data containing template syntax stays data.
    return re.sub(r'{{([A-Z_]+)}}', lambda m: str(values[m[1]]), text)


@contextmanager
def locked(directory, name='.lock'):
    """One writer per directory and lock name; a second process fails at once."""
    with open(Path(directory) / name, 'a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(
                f'Another process is already running in {directory}; wait for it to finish'
            ) from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def validate_candidates(doc):
    jsonschema.validate(doc, schemas.CANDIDATES)
    sources = [s['url'] for s in doc['sources']]
    if len(sources) != len(set(sources)):
        raise ValueError('Duplicate source URLs')
    for url in sources:
        web_url(url)
    problem_ids, claim_ids = set(), set()
    for problem in doc['problems']:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', problem['id']) or problem['id'] in problem_ids:
            raise ValueError('Invalid or duplicate problem ID')
        problem_ids.add(problem['id'])
        claims = problem['claims']
        if len(claims) != 4 or {c['kind'] for c in claims} != KINDS:
            raise ValueError('Each problem needs all four material claim kinds exactly once')
        for c in claims:
            if not c['id'].strip() or c['id'] in claim_ids or not c['text'].strip():
                raise ValueError('Empty claim or duplicate claim ID')
            claim_ids.add(c['id'])
            if any(x['url'] not in sources for x in c['citations']):
                raise ValueError('Citation references a missing source')
    return doc


class ReviewValidationError(ValueError):
    pass


def normalize_passage(text):
    # Explicit presentation characters only: NFKC would also rewrite scientific
    # superscripts and mathematical alphabets, which must remain distinct.
    text = text.translate(
        str.maketrans(
            {
                'ﬀ': 'ff',
                'ﬁ': 'fi',
                'ﬂ': 'fl',
                'ﬃ': 'ffi',
                'ﬄ': 'ffl',
                'ﬅ': 'st',
                'ﬆ': 'st',
                '‘': "'",
                '’': "'",
                '“': '"',
                '”': '"',
            }
        )
    )
    text = ' '.join(text.split())
    # Single/double delimiters around a complete quoted span are equivalent.
    # Never reinterpret contractions, possessives, primes, or unmatched marks.
    text = re.sub(r"(?<![\w'])'([^'\n]+)'(?![\w'])", lambda m: '"' + m[1] + '"', text)
    # PDF line layout can add spaces around the hyphen in a compound word.
    return re.sub(r'(?<=[A-Za-z])\s*-\s*(?=[A-Za-z])', '-', text)


def passage_matches(passage, text):
    quote = normalize_passage(passage)
    if not quote:
        return False
    if quote in normalize_passage(text):
        return True
    # Only a physical line-end hyphen may be omitted or retained by the quote.
    # No fuzzy similarity, word substitution or general punctuation stripping.
    wrapped = re.sub(r'(?<=[A-Za-z])-[ \t]*\r?\n\s*(?=[A-Za-z])', '\x00', text)
    pattern = ''.join(
        r'(?:-|\x00)'
        if char == '-'
        else re.escape(char) + (r'\x00?' if char.isascii() and char.isalpha() else '')
        for char in quote
    )
    return re.search(pattern, normalize_passage(wrapped)) is not None


def normalize_review_metadata(review, payload):
    """Normalize reference spelling and conservatively bound capture metadata only."""
    result = copy.deepcopy(review)
    if not isinstance(result, dict) or not isinstance(result.get('claims'), list):
        return result
    artifacts = {(s['url'], a['sha256']): a for s in payload['sources'] for a in s['artifacts']}
    for claim in result['claims']:
        if not isinstance(claim, dict) or not isinstance(claim.get('evidence'), list):
            continue
        for evidence in claim['evidence']:
            if not isinstance(evidence, dict) or not isinstance(evidence.get('artifact'), str):
                continue
            reference = evidence['artifact'].removeprefix('sha256:')
            artifact = artifacts.get((evidence.get('url'), reference))
            if artifact is None:
                # A downloaded PDF may use its resolved URL rather than its
                # parent source-record key. Normalize only an exact, unique
                # supplied hash + resolved-URL pair, never URL similarity.
                matches = [
                    (source_url, item)
                    for (source_url, sha), item in artifacts.items()
                    if sha == reference and item.get('resolved_url') == evidence.get('url')
                ]
                if len(matches) != 1:
                    continue
                evidence['url'], artifact = matches[0]
            evidence['artifact'] = reference
            if evidence.get('completeness') == 'full' and (
                artifact['truncated'] or artifact['extraction_issues']
            ):
                evidence['completeness'] = 'partial'
                if isinstance(evidence.get('reason'), str):
                    evidence['reason'] += (
                        ' [Pipeline capture limit: partial because the supplied extraction '
                        'is truncated or has recorded issues.]'
                    )
    return result


def validate_review(review, payload):
    try:
        return _validate_review(review, payload)
    except (ValueError, jsonschema.ValidationError) as error:
        raise ReviewValidationError(str(error)) from error


def _validate_review(review, payload):
    jsonschema.validate(review, schemas.REVIEW)
    claims = {c['id']: c for c in payload['problem']['claims']}
    ids = [c['id'] for c in review['claims']]
    if len(ids) != len(set(ids)) or set(ids) != set(claims):
        raise ValueError('Review must assess each claim exactly once')
    artifacts = {(s['url'], a['sha256']): a for s in payload['sources'] for a in s['artifacts']}
    for assessment in review['claims']:
        if not assessment['reason'].strip():
            raise ValueError('Assessment requires reasoning')
        permitted = {c['url'] for claim in claims.values() for c in claim['citations']}
        for e in assessment['evidence']:
            a = artifacts.get((e['url'], e['artifact']))
            if e['url'] not in permitted or a is None:
                raise ValueError('Review cites an unavailable artifact or unrelated source')
            if not e['reason'].strip() or not e['locator'].strip():
                raise ValueError('Evidence requires a locator and reasoning')
            if not passage_matches(e['passage'], a['text']):
                raise ValueError('Review passage is absent from its specific saved artifact')
            if e['completeness'] == 'full' and (a['truncated'] or a['extraction_issues']):
                raise ValueError('Incomplete extraction cannot certify full capture')
        status = assessment['status']
        if status != 'unresolved' and not any(
            e['relation'] == status and e['identity_verified'] for e in assessment['evidence']
        ):
            raise ValueError(
                'Conclusive assessment requires inspected evidence with verified identity'
            )
    return review


def backup(directory, destination):
    src, dest = Path(directory).resolve(), Path(destination).resolve()
    if dest.is_relative_to(PROJECT) or dest.is_relative_to(src) or src.is_relative_to(dest):
        raise ValueError(
            'Backup destination must be outside the project and separate from the field directory'
        )
    if dest.exists():
        raise ValueError('Use a new backup destination; existing backups are never overwritten')

    def inventory(root):
        entries = {}
        for p in root.rglob('*'):
            if p.is_symlink():
                raise ValueError('Backup refuses symlinks')
            if p.is_file() and p.name != '.lock':
                entries[str(p.relative_to(root))] = digest(p.read_bytes())
        return entries

    before = inventory(src)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns('.lock'))
    if inventory(src) != before or inventory(dest) != before:
        raise ValueError('Backup differs from source; do not treat it as verified')
    archive = Archive(dest)
    for url in archive.state:
        archive.evidence(url)  # Reopen and hash-check every source from the backup.
    receipt = {'verified_at': now(), 'source': str(src), 'destination': str(dest), 'files': before}
    write_json(dest / 'backup-verification.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    attach = sub.add_parser('attach')
    attach.add_argument('directory', type=Path)
    attach.add_argument('url')
    attach.add_argument('file', type=Path)
    alternative = sub.add_parser('alternative')
    alternative.add_argument('directory', type=Path)
    alternative.add_argument('url')
    alternative.add_argument('alternative_url')
    alternative.add_argument('--retry', action='store_true')
    back = sub.add_parser('backup')
    back.add_argument('directory', type=Path)
    back.add_argument('destination', type=Path)
    args = parser.parse_args()
    try:
        with locked(args.directory):
            if args.command == 'attach':
                print(Archive(args.directory).attach(args.url, args.file))
            elif args.command == 'alternative':
                Archive(args.directory).alternative(args.url, args.alternative_url, args.retry)
            elif args.command == 'backup':
                print(json.dumps(backup(args.directory, args.destination), indent=2))
    except (ValueError, OSError, RuntimeError, jsonschema.ValidationError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
