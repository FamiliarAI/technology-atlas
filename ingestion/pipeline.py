"""Run with python3 -m ingestion.pipeline --help from the repository root."""
import argparse
import copy
from contextlib import contextmanager
from datetime import date
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import uuid

import jsonschema
from . import schemas
from .sources import Archive, digest, invalidate_summaries, now, read_json, web_url, write_json

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
def locked(directory):
    with open(Path(directory) / '.lock', 'a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('This field is already running; wait for it to finish') from None
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


def validate_ledger(value, doc=None):
    if isinstance(value, str):
        text = re.sub(r'^```(?:json)?\s*|\s*```$', '', value.strip())
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            # Some CLIs concatenate progress commentary before the final JSON.
            # Accept one trailing JSON object, never repair its contents.
            start = text.find('{')
            if start < 0:
                raise
            value = json.loads(text[start:])
    jsonschema.validate(value, schemas.LEDGER)
    for source in value['sources']:
        web_url(source['url'])
    if not value['sources']:
        raise ValueError('Source ledger has no verified URLs; stop before formatting')
    if doc is not None:
        expected = {c['id'] for p in doc['problems'] for c in p['claims']}
        mapped = {cid for source in value['sources'] for cid in source['claim_ids']}
        gaps = {g['claim_id'] for g in value['gaps']}
        if mapped | gaps != expected:
            raise ValueError('Source ledger must map every claim to a source or explicit gap, with no unknown IDs')
        if {f['problem_id'] for f in value['freshness']} != {p['id'] for p in doc['problems']}:
            raise ValueError('Source ledger must record a bounded freshness check for every candidate')
    return value


def validate_handoff(doc, ledger):
    validate_candidates(doc)
    validate_ledger(ledger, doc)
    return doc


class ReviewValidationError(ValueError):
    pass


def normalize_passage(text):
    # Explicit presentation characters only: NFKC would also rewrite scientific
    # superscripts and mathematical alphabets, which must remain distinct.
    text = text.translate(str.maketrans({
        'ﬀ': 'ff', 'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬃ': 'ffi', 'ﬄ': 'ffl', 'ﬅ': 'st', 'ﬆ': 'st',
        '‘': "'", '’': "'", '“': '"', '”': '"'}))
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
    pattern = ''.join(r'(?:-|\x00)' if char == '-' else re.escape(char) +
                      (r'\x00?' if char.isascii() and char.isalpha() else '') for char in quote)
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
                matches = [(source_url, item) for (source_url, sha), item in artifacts.items()
                           if sha == reference and item.get('resolved_url') == evidence.get('url')]
                if len(matches) != 1:
                    continue
                evidence['url'], artifact = matches[0]
            evidence['artifact'] = reference
            if evidence.get('completeness') == 'full' and (artifact['truncated'] or artifact['extraction_issues']):
                evidence['completeness'] = 'partial'
                if isinstance(evidence.get('reason'), str):
                    evidence['reason'] += ' [Pipeline capture limit: partial because the supplied extraction is truncated or has recorded issues.]'
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
            raise ValueError('Conclusive assessment requires inspected evidence with verified identity')
    return review


def salvage_review(review, payload):
    """Retain independently valid claims; never turn invalid evidence into support."""
    output, issues = [], {}
    raw_claims = review.get('claims', []) if isinstance(review, dict) else []
    for claim in payload['problem']['claims']:
        matches = [c for c in raw_claims if isinstance(c, dict) and c.get('id') == claim['id']]
        single = copy.deepcopy(payload)
        single['problem']['claims'] = [copy.deepcopy(claim)]
        # Permit any source cited by this problem, as in the full review validator.
        single['problem']['claims'][0]['citations'] = [c for original in payload['problem']['claims'] for c in original['citations']]
        try:
            validate_review({'claims': matches}, single)
            output.append(matches[0])
        except ReviewValidationError as error:
            issues[claim['id']] = str(error)[:1000]
            output.append({'id': claim['id'], 'status': 'unresolved',
                           'reason': 'Review output could not be validated: ' + str(error)[:1000], 'evidence': []})
    return {'claims': output}, issues


def execute(cmd, directory, stdin=None, timeout=3600):
    """Keep logs, stop child processes on timeout/interrupt, never use API-key env auth."""
    env = dict(os.environ)
    for key in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'XAI_API_KEY', 'GROK_API_KEY'):
        env.pop(key, None)
    with tempfile.TemporaryDirectory(prefix='atlas-model-') as cwd, \
            open(directory / 'stdout.log', 'w') as out, open(directory / 'stderr.log', 'w') as err:
        process = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                   stdout=out, stderr=err, text=True, start_new_session=True)
        try:
            process.communicate(stdin, timeout=timeout)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            except ProcessLookupError:
                pass
            raise
    if process.returncode:
        raise RuntimeError(f'Model CLI exited {process.returncode}; inspect {directory / "stderr.log"}. '
                           'If Grok access/credits are exhausted, stop and ask the user to switch accounts.')


class Models:
    def __init__(self, config):
        self.config = config

    def call(self, role, text, schema, directory):
        settings = self.config[role]
        (directory / 'prompt.md').write_text(text)
        write_json(directory / 'model.json', settings)
        if role == 'research':
            cmd = [str(Path(self.config['grok']).expanduser()), '-m', settings['model'],
                   '--reasoning-effort', settings['effort'], '--tools', 'web_search,web_fetch',
                   '--no-subagents', '--no-plan', '--max-turns', '150', '--output-format', 'json',
                   '--prompt-file', str(directory / 'prompt.md')]
            execute(cmd, directory)
            raw = json.loads((directory / 'stdout.log').read_text())
            if raw.get('stopReason') != 'end_turn' or not str(raw.get('text', '')).strip():
                raise ValueError('Research did not finish with usable notes; inspect raw output and account access')
            return raw['text']
        write_json(directory / 'schema.json', schema)
        output = directory / 'response.json'
        cmd = [str(Path(self.config['codex']).expanduser()), 'exec', '--ignore-user-config',
               '--skip-git-repo-check', '--ephemeral', '-s', 'read-only', '-m', settings['model'],
               '-c', f'model_reasoning_effort="{settings["effort"]}"', '--output-schema',
               str(directory / 'schema.json'), '-o', str(output), '--json', '-']
        execute(cmd, directory, text)
        return read_json(output)


class Pipeline:
    def __init__(self, directory, models=None, archive=None):
        self.root = Path(directory).resolve()
        self.spec = read_json(self.root / 'field.json')
        if not self.spec:
            raise ValueError('Initialize this field first')
        self.config = read_json(HERE / 'config.json')
        # A formatting-only recovery from an observed output budget exhaustion.
        # Keep the model; lower reasoning on the next run and record it in receipts.
        if self.config['format']['effort'] == 'high':
            for receipt_path in self.root.glob('attempts/format-*/receipt.json'):
                receipt = read_json(receipt_path)
                output = receipt_path.parent / 'stdout.log'
                if receipt.get('status') != 'failed' or not output.exists():
                    continue
                for line in output.read_text().splitlines():
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if event.get('type') in ('error', 'turn.failed') and 'max_output_tokens' in json.dumps(event):
                        self.config['format']['effort'] = 'medium'
        self.models = models or Models(self.config)
        self.archive = archive or Archive(self.root)
        self.state = read_json(self.root / 'state.json', {'cache': {}, 'revision': None})

    def step(self, name, role, text, schema=None, validator=None):
        key = fingerprint({'name': name, 'role': self.config[role], 'text': text, 'schema': schema})
        cached = self.state['cache'].get(key)
        if cached:
            path = self.root / cached['path']
            if digest(path.read_bytes()) != cached['sha256']:
                raise ValueError('Cached output changed; create an explicit revision instead')
            self.last_step_directory = path.parent
            value = read_json(path)
            if validator:
                validator(value)
            return value
        directory = self.root / 'attempts' / f'{name}-{uuid.uuid4().hex}'
        directory.mkdir(parents=True)
        (directory / 'prompt.md').write_text(text)
        receipt = {'step': name, 'model': self.config[role], 'started_at': now(), 'status': 'running'}
        write_json(directory / 'receipt.json', receipt)
        print(f'{name}: started', flush=True)
        try:
            recovered = None
            if (name == 'source-ledger' or name.startswith('review-')) and validator:
                for old in self.root.glob(f'attempts/{name}-*/receipt.json'):
                    prior = read_json(old)
                    candidate = old.parent / 'result.json'
                    if (prior.get('status') == 'failed' and prior.get('model') == self.config[role]
                            and candidate.exists() and (old.parent / 'prompt.md').read_text() == text):
                        try:
                            validator(read_json(candidate))
                        except (ValueError, jsonschema.ValidationError):
                            continue
                        recovered = read_json(candidate)
                        receipt['recovered_from'] = str(candidate.relative_to(self.root))
                        break
            value = recovered if recovered is not None else self.models.call(role, text, schema, directory)
            write_json(directory / 'result.json', value)
            self.last_step_directory = directory
            if schema:
                jsonschema.validate(value, schema)
            if validator:
                validator(value)
            path = directory / 'result.json'
            self.last_step_directory = directory
            self.state['cache'][key] = {'path': str(path.relative_to(self.root)), 'sha256': digest(path.read_bytes())}
            write_json(self.root / 'state.json', self.state)
            receipt.update(status='complete', finished_at=now())
            print(f'{name}: complete', flush=True)
            return value
        except BaseException as error:
            receipt.update(status='failed', finished_at=now(), error=str(error))
            raise
        finally:
            write_json(directory / 'receipt.json', receipt)

    def candidates(self):
        if self.state['revision']:
            entry = self.state['revision']
            path = self.root / entry['path']
            if digest(path.read_bytes()) != entry['sha256']:
                raise ValueError('Revision changed on disk; import a new revision')
            return validate_candidates(read_json(path))
        notes = self.step('research', 'research', prompt('research', FIELD=self.spec['field'],
                          BOUNDARIES=self.spec['boundaries'], AS_OF=self.spec['as_of'], PREFIX=self.spec['prefix']))
        legacy_text = prompt('format', NOTES=notes)
        text = prompt('format', NOTES=notes + self.research_url_context(self.last_step_directory))
        def format_key(value):
            return fingerprint({'name': 'format', 'role': self.config['format'], 'text': value, 'schema': schemas.CANDIDATES})
        if format_key(text) not in self.state['cache'] and format_key(legacy_text) in self.state['cache']:
            prior = self.step('format', 'format', legacy_text, schemas.CANDIDATES, validate_candidates)
            if prior['sources']:
                return prior  # Provenance enrichment must not redo a usable completed format step.
        # Existing successful outputs remain resumable. New research must hand off
        # an explicit, validated ledger before the formatting model runs.
        if format_key(text) in self.state['cache']:
            return self.step('format', 'format', text, schemas.CANDIDATES, validate_candidates)
        saved = self.state.get('source_ledger')
        policy = fingerprint({'prompt': (HERE / 'prompts/source_ledger.md').read_text(), 'schema': schemas.LEDGER, 'model': self.config['research']})
        if saved and saved['notes_hash'] == fingerprint(notes) and saved.get('policy') == policy:
            path = self.root / saved['path']
            if digest(path.read_bytes()) != saved['sha256']:
                raise ValueError('Cached source ledger changed')
            ledger = validate_ledger(read_json(path))
        else:
            ledger = self.step('source-ledger', 'research', prompt('source_ledger', INPUT=json.dumps({
                'field': self.spec, 'notes': notes, 'leads': text, 'candidates': None})), validator=validate_ledger)
            path = self.last_step_directory / 'result.json'
            self.state['source_ledger'] = {'notes_hash': fingerprint(notes), 'policy': policy, 'path': str(path.relative_to(self.root)),
                                          'sha256': digest(path.read_bytes())}
            write_json(self.root / 'state.json', self.state)
            ledger = validate_ledger(ledger)
        write_json(self.root / 'source-ledger.json', ledger)
        return self.step('format', 'format', prompt('format', NOTES=notes + '\nSOURCE LEDGER:\n' + json.dumps(ledger)),
                         schemas.CANDIDATES, lambda doc: validate_handoff(doc, ledger))

    def repair_sources(self):
        doc = validate_candidates(read_json(self.root / 'candidates.json'))
        research = []
        for entry in self.state['cache'].values():
            path = self.root / entry['path']
            if path.parent.name.startswith('research-'):
                if digest(path.read_bytes()) != entry['sha256']:
                    raise ValueError('Saved research changed')
                research.append((path, read_json(path)))
        if not research:
            raise ValueError('No saved research to repair')
        path, notes = research[-1]
        context = self.research_url_context(path.parent)
        ledger = self.step('source-ledger', 'research', prompt('source_ledger',
            INPUT=json.dumps({'field': self.spec, 'candidates': doc, 'notes': notes, 'leads': context})),
            validator=validate_ledger)
        ledger = validate_ledger(ledger, doc)
        write_json(self.root / 'source-ledger.json', ledger)
        repaired = self.step('format-repaired', 'format', prompt('format', NOTES=json.dumps({
            'original_candidates': doc, 'source_ledger': ledger,
            'instruction': 'Keep every candidate and its ID. Use verified source ledger mappings. Correct dated current-state claims only as explicitly documented in the ledger; label proposed completion criteria as proposals. Preserve gaps.'})) +
            '\n\nFor this source-repair operation, correct author attribution and access descriptions that conflict with the ledger metadata. Preserve candidate IDs and substantive scope; do not turn search listings or uninspected claims into evidence.',
            schemas.CANDIDATES, lambda result: validate_handoff(result, ledger))
        if {p['id'] for p in repaired['problems']} != {p['id'] for p in doc['problems']}:
            raise ValueError('Source repair must preserve candidate IDs')
        revision = self.root / 'source-repair-candidates.json'
        write_json(revision, repaired)
        self.revise(revision, 'Repair missing source handoff and record bounded freshness checks from saved research')
        return repaired

    def research_url_context(self, directory):
        raw = directory / 'stdout.log'
        if not raw.exists():
            return ''
        try:
            session = read_json(raw).get('sessionId')
        except (ValueError, AttributeError):
            return ''
        if not session:
            return ''
        transcript = directory / 'session.md'
        if not transcript.exists():
            result = subprocess.run([str(Path(self.config['grok']).expanduser()), 'export', session, str(transcript)],
                                    capture_output=True, text=True, timeout=30)
            if result.returncode:
                (directory / 'session-export-error.txt').write_text(result.stderr)
                return ''
        urls = list(dict.fromkeys(re.findall(r'^- Web(?:Search: open|Fetch:) (https?://\S+)', transcript.read_text(), re.M)))
        if not urls:
            return ''
        return ('\n\nRESEARCH TOOL PROVENANCE: The session attempted the following URLs. An attempted URL does NOT '
                'prove successful access or support. Match a URL to a source only when the notes and identifier make '
                'the association clear; never invent a match. Use one source record per unique valid URL. Omit '
                'unknown-URL records and citations rather than emitting blank URLs; retain their claims as unresolved.\n'
                + '\n'.join(urls))

    def revise(self, file, reason):
        if not reason.strip():
            raise ValueError('A revision requires a reason')
        doc = validate_candidates(read_json(file))
        folder = self.root / 'revisions'; folder.mkdir(exist_ok=True)
        path = folder / f'{uuid.uuid4().hex}.json'
        write_json(path, doc)
        entry = {'path': str(path.relative_to(self.root)), 'sha256': digest(path.read_bytes()), 'reason': reason,
                 'at': now(), 'previous': self.state['revision']}
        write_json(path.with_suffix('.receipt.json'), entry)
        invalidate_summaries(self.root)
        self.state['revision'] = entry
        write_json(self.root / 'state.json', self.state)

    def run(self, through='review', problem_id=None, retry=False):
        if through == 'research':
            return self.step('research', 'research', prompt('research', FIELD=self.spec['field'],
                             BOUNDARIES=self.spec['boundaries'], AS_OF=self.spec['as_of'], PREFIX=self.spec['prefix']))
        doc = self.candidates()
        write_json(self.root / 'candidates.json', doc)
        if through == 'format':
            return doc
        problems = [p for p in doc['problems'] if problem_id is None or p['id'] == problem_id]
        if problem_id and not problems:
            raise ValueError(f'Unknown problem ID: {problem_id}')
        urls = {c['url'] for p in problems for claim in p['claims'] for c in claim['citations']}
        for url in sorted(urls):
            self.archive.capture(url, retry=retry)
        if through == 'capture':
            return self.archive.state
        reviews, payloads = {}, {}
        for p in problems:
            wanted = {c['url'] for claim in p['claims'] for c in claim['citations']}
            payload = {'field': self.spec, 'problem': p, 'freshness': [f for f in read_json(self.root / 'source-ledger.json', {}).get('freshness', []) if f['problem_id'] == p['id']], 'sources': [
                {**s, 'artifacts': self.archive.evidence(s['url'])} for s in doc['sources'] if s['url'] in wanted]}
            payloads[p['id']] = payload
            if not any(a['text'].strip() for source in payload['sources'] for a in source['artifacts']):
                review = {'claims': [{'id': c['id'], 'status': 'unresolved',
                           'reason': 'No extracted source text is available; support cannot be assessed.',
                           'evidence': []} for c in p['claims']]}
                validate_review(review, payload)
                folder = self.root / 'machine-reviews'; folder.mkdir(exist_ok=True)
                path = folder / f'{p["id"]}-{fingerprint(payload)}.json'
                if not path.exists():
                    write_json(path, {'assessor': 'machine: missing evidence only', 'input': payload, 'review': review})
                reviews[p['id']] = review
            else:
                issue_path = self.root / 'machine-reviews' / f'review-failed-{p["id"]}-{fingerprint(payload)}.json'
                if issue_path.exists() and not retry:
                    reviews[p['id']] = read_json(issue_path)['review']
                    continue
                try:
                    raw_review = self.step('review-' + p['id'], 'review', prompt('review', INPUT=json.dumps(payload)),
                        schemas.REVIEW, lambda r, payload=payload: validate_review(normalize_review_metadata(r, payload), payload))
                    reviews[p['id']] = normalize_review_metadata(raw_review, payload)
                    if issue_path.exists():
                        history = self.root / 'history'; history.mkdir(exist_ok=True)
                        issue_path.rename(history / f'{issue_path.stem}-{uuid.uuid4().hex}.json')
                except (ReviewValidationError, jsonschema.ValidationError) as error:
                    raw = read_json(self.last_step_directory / 'result.json', {})
                    review, issues = salvage_review(normalize_review_metadata(raw, payload), payload)
                    issue_path.parent.mkdir(exist_ok=True)
                    write_json(issue_path, {'assessor': 'machine: invalid review, no support judgment',
                                           'input_hash': fingerprint(payload), 'issues': issues, 'review': review})
                    reviews[p['id']] = review
        field_review = None
        if problem_id is None:
            field_review = self.step('field-review', 'review', prompt('field_review', INPUT=json.dumps(
                {'field': self.spec, 'candidates': doc, 'reviews': reviews})), schemas.FIELD_REVIEW)
        result = self.summarize(doc, problems, reviews, payloads, field_review, problem_id)
        write_json(self.root / ('summary.json' if problem_id is None else f'summary-{problem_id}.json'), result)
        print(json.dumps(result['counts']), flush=True)
        return result

    def summarize(self, doc, problems, reviews, payloads, field_review, scope):
        rows, counts = [], {key: 0 for key in ('supported', 'partially_supported', 'unresolved', 'contradicted', 'collection_incomplete', 'review_failed')}
        for p in problems:
            claims = reviews[p['id']]['claims']
            statuses = {c['status'] for c in claims}
            invalid = any(c['reason'].startswith('Review output could not be validated:') for c in claims)
            available = any(a['text'].strip() for source in payloads[p['id']]['sources'] for a in source['artifacts'])
            status = ('review_failed' if invalid else 'contradicted' if 'contradicted' in statuses else
                      'collection_incomplete' if not available else
                      'supported' if statuses == {'supported'} else
                      'partially_supported' if 'supported' in statuses else 'unresolved')
            counts[status] += 1
            captures = []
            for source in payloads[p['id']]['sources']:
                url = source['url']
                evidence = [e for c in claims for e in c['evidence'] if e['url'] == url and e['identity_verified']]
                capture = 'saved' if any(e['completeness'] == 'full' for e in evidence) else 'partial' if source['artifacts'] else 'missing'
                failures = [op for op in self.archive.source(url)['operations'].values() if op['status'] == 'failed']
                captures.append({'url': url, 'status': capture, 'failures': failures,
                                 'note': 'Artifact identity/completeness assessed by model; inspect before relying on it',
                                 'artifacts': [{k: v for k, v in a.items() if k != 'text'} for a in source['artifacts']]})
            rows.append({'id': p['id'], 'title': p['title'], 'status': status, 'claim_counts': {key: sum(c['status'] == key for c in claims) for key in ('supported', 'contradicted', 'unresolved')}, 'freshness': payloads[p['id']].get('freshness', []), 'claims': [{**original, 'assessment': assessment} for original in p['claims']
                    for assessment in claims if assessment['id'] == original['id']], 'captures': captures})
        return {'field': self.spec, 'scope': scope or 'whole field', 'counts': counts, 'problems': rows,
                'candidate_hash': fingerprint(doc), 'excluded': doc['excluded'], 'field_review': field_review,
                'completion': 'Review generated; inspect result and verify external backup before field completion'}


def backup(directory, destination):
    src, dest = Path(directory).resolve(), Path(destination).resolve()
    if dest.is_relative_to(PROJECT) or dest.is_relative_to(src) or src.is_relative_to(dest):
        raise ValueError('Backup destination must be outside the project and separate from the field directory')
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


def init_field(field, prefix, boundaries, as_of):
    if not re.fullmatch('[A-Z][A-Z0-9]{1,9}', prefix):
        raise ValueError('Use a 2–10 character uppercase field abbreviation')
    date.fromisoformat(as_of)
    if not field.strip() or not boundaries.strip():
        raise ValueError('Field and boundaries are required')
    root = HERE / 'runs' / prefix
    # Check before creating private outputs; never assume the ignore rule exists.
    result = subprocess.run(['git', 'check-ignore', '--quiet', str(root / 'sources' / 'probe.pdf')], cwd=PROJECT)
    if result.returncode:
        raise ValueError('ingestion/runs must be Git-ignored before creating field outputs')
    spec = {'field': field, 'prefix': prefix, 'boundaries': boundaries, 'as_of': as_of}
    if root.exists():
        if read_json(root / 'field.json') != spec:
            raise ValueError('Field already exists with different settings; choose a new abbreviation')
        return root
    root.mkdir(parents=True)
    write_json(root / 'field.json', spec)
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init')
    init.add_argument('field'); init.add_argument('prefix')
    init.add_argument('--boundaries', required=True); init.add_argument('--as-of', required=True)
    run = sub.add_parser('run')
    run.add_argument('directory', type=Path)
    run.add_argument('--through', choices=['research', 'format', 'capture', 'review'], default='review')
    run.add_argument('--problem'); run.add_argument('--retry', action='store_true')
    repair = sub.add_parser('repair-sources', help='Repair source ledger using saved research, then create a candidate revision')
    repair.add_argument('directory', type=Path)
    attach = sub.add_parser('attach')
    attach.add_argument('directory', type=Path); attach.add_argument('url'); attach.add_argument('file', type=Path)
    alternative = sub.add_parser('alternative')
    alternative.add_argument('directory', type=Path); alternative.add_argument('url'); alternative.add_argument('alternative_url')
    alternative.add_argument('--retry', action='store_true')
    revise = sub.add_parser('revise')
    revise.add_argument('directory', type=Path); revise.add_argument('file', type=Path); revise.add_argument('--reason', required=True)
    back = sub.add_parser('backup')
    back.add_argument('directory', type=Path); back.add_argument('destination', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'init':
            print(init_field(args.field, args.prefix, args.boundaries, args.as_of)); return
        with locked(args.directory):
            if args.command == 'run':
                Pipeline(args.directory).run(args.through, args.problem, args.retry)
            elif args.command == 'repair-sources':
                Pipeline(args.directory).repair_sources()
            elif args.command == 'attach':
                print(Archive(args.directory).attach(args.url, args.file))
            elif args.command == 'alternative':
                Archive(args.directory).alternative(args.url, args.alternative_url, args.retry)
            elif args.command == 'revise':
                Pipeline(args.directory).revise(args.file, args.reason)
            elif args.command == 'backup':
                print(json.dumps(backup(args.directory, args.destination), indent=2))
    except (ValueError, OSError, RuntimeError, jsonschema.ValidationError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
