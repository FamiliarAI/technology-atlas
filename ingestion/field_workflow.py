"""Resumable five-stage field workflow; three independent concept calls per field."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
import uuid

import jsonschema
from . import schemas
from .pipeline import (
    fingerprint,
    locked,
    prompt,
    validate_candidates,
    validate_review,
    normalize_review_metadata,
)
from .providers import (
    Models,
    ProviderState,
    ProviderUnavailable,
    attempt_model,
    cache_model,
    describe,
    stage_entries,
)
from .sources import Archive, digest, now, read_json, write_json

HERE = Path(__file__).resolve().parent
FORMAT_SCHEMA = schemas.obj(
    candidates=schemas.CANDIDATES,
    original_dispositions=schemas.arr(
        schemas.obj(
            original_number={'type': 'integer'},
            original_title=schemas.S,
            status=schemas.enum('covered', 'added', 'not_added'),
            concept_ids=schemas.arr(schemas.S),
            reason=schemas.S,
        )
    ),
    change_log=schemas.arr(
        schemas.obj(concept_ids=schemas.arr(schemas.S), change=schemas.S, reason=schemas.S)
    ),
)
REVIEW_SCHEMA = schemas.obj(
    concept_assessment=schemas.obj(
        summary=schemas.S, revolutionary_significance=schemas.S, scope_and_overlap=schemas.S
    ),
    corrections=schemas.arr(
        schemas.obj(claim_id=schemas.S, proposed_text=schemas.S, reason=schemas.S)
    ),
    evidence_review=schemas.REVIEW,
)
HEADER_RULE = (
    '\n'
    'Use exactly **PREFIX-NN. Title** as the heading for each concept, replacing PREFIX '
    'with the supplied prefix. Use **Change log** for the change-log heading. Keep other '
    'headings distinct from concept headings.\n'
)

REVIEW_INSTRUCTIONS = (
    '\n'
    'Concepts are the primary output. Return a concept_assessment of the revolutionary '
    'capability, scope and overlaps, separately from the evidence_review. Return concrete '
    'corrections containing claim_id, complete proposed_text and reason for the later '
    'rewrite. Preserve concept identity, uncertainty and proposals. Do not reject a '
    'concept solely for missing sources. An empty corrections list is allowed. Do not '
    'place an empty quote in evidence: record failed extraction or missing material as a '
    'limitation in the assessment reason.\n'
)
MAX_REVIEW_PROMPT_BYTES = 900_000
REVIEW_RETRY_RESERVE = 4096
LIMITED_EVIDENCE_INSTRUCTIONS = (
    '\n'
    'Source text may be shortened to fit the review-input budget. Inspect truncated and '
    'review_text_omitted_characters on each artifact. These are partial excerpts, not full '
    'documents; do not infer absence of evidence from omitted material. A text_reference '
    'points to an identical excerpt supplied under another source/artifact; it does not '
    'change the identity of either saved artifact. Keep scope and uncertainty '
    'conservative.\n'
)


def _fair_allocations(lengths, budget):
    """Max-min allocation: short texts finish before longer ones share the rest."""
    result = [0] * len(lengths)
    remaining = max(0, budget)
    ordered = sorted(range(len(lengths)), key=lambda i: (lengths[i], i))
    for position, index in enumerate(ordered):
        share = remaining // (len(ordered) - position)
        result[index] = min(lengths[index], share)
        remaining -= result[index]
    return result


def _compact_review_prompt(payload):
    # Deduplicate exact excerpt text in the prompt only. The validation payload
    # keeps every excerpt associated with its original source/hash.
    rendered = copy.deepcopy(payload)
    seen = {}
    for source in rendered['sources']:
        for artifact in source['artifacts']:
            text = artifact['text']
            if not text:
                continue
            if text in seen:
                artifact['text'] = ''
                artifact['text_reference'] = seen[text]
            else:
                seen[text] = {'source_url': source['url'], 'artifact': artifact['sha256']}
    return (
        prompt('review', INPUT=json.dumps(rendered, ensure_ascii=False, separators=(',', ':')))
        + REVIEW_INSTRUCTIONS
        + LIMITED_EVIDENCE_INSTRUCTIONS
    )


def build_review_input(payload, max_prompt_bytes=MAX_REVIEW_PROMPT_BYTES):
    """Bound the actual prompt, not just each artifact, without changing originals.

    Small inputs retain their exact former serialization/cache key. Oversized
    inputs first avoid JSON escape amplification and duplicate excerpt text,
    then fairly share a prefix budget across sources and their artifacts.
    """
    original_text = prompt('review', INPUT=json.dumps(payload)) + REVIEW_INSTRUCTIONS
    target = max_prompt_bytes - REVIEW_RETRY_RESERVE
    if target <= 0:
        raise ValueError('Review prompt budget is too small')
    if len(original_text.encode('utf-8')) <= target:
        return payload, original_text
    base = copy.deepcopy(payload)
    base['review_input_budget'] = {
        'maximum_prompt_bytes': max_prompt_bytes,
        'retry_reserve_bytes': REVIEW_RETRY_RESERVE,
        'original_prompt_bytes': len(original_text.encode('utf-8')),
        ('method'): (
            'Exact excerpt deduplication and UTF-8 JSON; if needed, max-min prefix '
            'allocation across sources, then artifacts. Full saved source files are '
            'unchanged.'
        ),
    }
    compact = _compact_review_prompt(base)
    if len(compact.encode('utf-8')) <= target:
        return base, compact
    lengths = [[len(a['text']) for a in source['artifacts']] for source in base['sources']]

    def clipped(budget):
        value = copy.deepcopy(base)
        source_limits = _fair_allocations([sum(items) for items in lengths], budget)
        for source, sizes, source_limit in zip(value['sources'], lengths, source_limits):
            for artifact, size, retained in zip(
                source['artifacts'], sizes, _fair_allocations(sizes, source_limit)
            ):
                if retained < size:
                    artifact['text'] = artifact['text'][:retained]
                    artifact['truncated'] = True
                    artifact['review_text_original_characters'] = size
                    artifact['review_text_retained_characters'] = retained
                    artifact['review_text_omitted_characters'] = size - retained
                    artifact['extraction_issues'] = list(artifact.get('extraction_issues', [])) + [
                        f'Review input budget omitted {size - retained} of {size} supplied '
                        'extracted characters; only a partial prefix is supplied. '
                        'The original source file is unchanged.'
                    ]
        return value, _compact_review_prompt(value)

    best, text = clipped(0)
    if len(text.encode('utf-8')) > target:
        raise ValueError(
            (
                'Review metadata alone exceeds the prompt budget; no sources or '
                'substantive record fields were dropped'
            )
        )
    low, high = 0, sum(sum(items) for items in lengths)
    while low < high:
        middle = (low + high + 1) // 2
        candidate, candidate_text = clipped(middle)
        if len(candidate_text.encode('utf-8')) <= target:
            low = middle
            best, text = candidate, candidate_text
        else:
            high = middle - 1
    return best, text


class AccountExhausted(RuntimeError):
    """Every entry in a stage's fallback list is exhausted; the batch stops scheduling."""


class SafetyReviewBlocked(RuntimeError):
    """A provider safety refusal requires resolution; never auto-retry this input."""


REFUSAL_PREFIX = "Invalid prompt: we've limited access to this content for safety reasons"


def provider_safety_refusal(folder):
    """Inspect provider error events only, never research or source content."""
    path = Path(folder) / 'stdout.log'
    if not path.exists():
        return None
    text = path.read_text(errors='replace')
    try:
        envelope = json.loads(text)
    except ValueError:
        envelope = None
    # Claude reports a safety refusal as the stop reason of its result envelope.
    if isinstance(envelope, dict) and envelope.get('stop_reason') == 'refusal':
        return 'Claude stopped with stop_reason refusal'
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        message = None
        if event.get('type') == 'error':
            message = event.get('message')
        elif event.get('type') == 'turn.failed' and isinstance(event.get('error'), dict):
            message = event['error'].get('message')
        if isinstance(message, str) and message.startswith(REFUSAL_PREFIX):
            return message
    return None


def persist_safety_block(root, name, key, folder, message):
    blocked = Path(root) / 'workflow-blocked'
    blocked.mkdir(exist_ok=True)
    path = blocked / (name + '-' + key + '.json')
    if not path.exists():
        write_json(
            path,
            {
                'stage': name,
                'input_hash': key,
                'status': 'safety_blocked',
                'recorded_at': now(),
                'source_attempt': str(Path(folder).resolve()),
                'provider_message': message,
                'source_log_sha256': digest((Path(folder) / 'stdout.log').read_bytes()),
                ('next_action'): (
                    'Do not retry, filter, or reroute the blocked input. Await an '
                    'explicitly permitted task scope.'
                ),
            },
        )
    return path


def blocked_marker(root, name):
    """The recorded safety refusal for a stage, whatever its input hash, or None."""
    for path in sorted((Path(root) / 'workflow-blocked').glob(name + '-*.json')):
        marker = read_json(path)
        if marker.get('stage') == name and marker.get('status') == 'safety_blocked':
            return path
    return None


def refusal_reason(marker):
    return 'Provider safety refusal: ' + str(read_json(marker).get('provider_message', ''))


def workflow_lock(root):
    return locked(root, '.workflow.lock')


def concept_headings(notes, prefix=None):
    """Locate concept entries in ordinary bold or ATX Markdown headings."""
    identifier = (re.escape(prefix) if prefix is not None else r'[A-Za-z0-9_-]+') + r'-\d+'
    pattern = (
        r'^(?:\*\*(' + identifier + r')\.[ \t]+[^\n]+\*\*[ \t]*'
        r'|[ ]{0,3}#{1,6}[ \t]+(?:\*\*)?(' + identifier + r')\.[ \t]+[^\n]+)$'
    )
    return [
        (match[1] or match[2], match.start(), match.end())
        for match in re.finditer(pattern, notes, re.M)
    ]


def concept_ids(notes, prefix):
    # Claim references lack the standalone ID-plus-period heading shape.
    return [identifier for identifier, _, _ in concept_headings(notes, prefix)]


def validate_research(notes, prefix, required_ids=()):
    if not isinstance(notes, str) or not notes.strip():
        raise ValueError('Empty research')
    ids = concept_ids(notes, prefix)
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('Research requires unique concept headings in the requested format')
    if set(required_ids) - set(ids):
        raise ValueError('Reconciliation dropped first-pass concepts')
    return ids


def validate_format(value, expected_ids, original_numbers=()):
    jsonschema.validate(value, FORMAT_SCHEMA)
    validate_candidates(value['candidates'])
    ids = {p['id'] for p in value['candidates']['problems']}
    if ids != set(expected_ids):
        raise ValueError('Formatting lost or invented a reconciled concept')
    numbers = [d['original_number'] for d in value['original_dispositions']]
    if not numbers or len(numbers) != len(set(numbers)):
        raise ValueError('Missing or duplicated original-entry dispositions')
    if original_numbers and set(numbers) != set(original_numbers):
        raise ValueError('Not every original entry has a disposition')
    if any(
        set(d['concept_ids']) - ids for d in value['original_dispositions'] + value['change_log']
    ):
        raise ValueError('Unknown concept reference in reconciliation metadata')
    return value


def normalize_and_validate_review(value, payload):
    """Move empty extraction-limit entries out of quote evidence, with an audit."""
    jsonschema.validate(value, REVIEW_SCHEMA)
    result = copy.deepcopy(value)
    audit = []
    for claim in result['evidence_review']['claims']:
        kept = []
        for evidence in claim['evidence']:
            if (
                not evidence['passage'].strip()
                and evidence['relation'] == 'unresolved'
                and not evidence['identity_verified']
            ):
                # Confirm the supplied artifact exists before relocating its limitation.
                matches = [
                    a
                    for s in payload['sources']
                    if s['url'] == evidence['url']
                    for a in s['artifacts']
                    if a['sha256'] == evidence['artifact'].removeprefix('sha256:')
                ]
                if len(matches) != 1:
                    raise ValueError('Empty evidence entry references an unavailable artifact')
                claim['reason'] += ' [Capture limitation: ' + evidence['reason'] + ']'
                audit.append({'claim_id': claim['id'], 'moved_empty_evidence': evidence})
            else:
                kept.append(evidence)
        claim['evidence'] = kept
    before_metadata = result['evidence_review']
    result['evidence_review'] = normalize_review_metadata(before_metadata, payload)
    for before_claim, after_claim in zip(
        before_metadata['claims'], result['evidence_review']['claims']
    ):
        for index, (before, after) in enumerate(
            zip(before_claim['evidence'], after_claim['evidence'])
        ):
            if (before['url'], before['artifact']) != (after['url'], after['artifact']):
                audit.append(
                    {
                        'claim_id': after_claim['id'],
                        'evidence_index': index,
                        'source_reference_before': {
                            'url': before['url'],
                            'artifact': before['artifact'],
                        },
                        'source_reference_after': {
                            'url': after['url'],
                            'artifact': after['artifact'],
                        },
                        ('reason'): (
                            'Normalized an exact supplied artifact reference; resolved URL '
                            'aliases require a unique hash and resolved-URL match. Raw '
                            'output is retained.'
                        ),
                    }
                )
    validate_review(result['evidence_review'], payload)
    ids = {c['id'] for c in payload['problem']['claims']}
    if any(
        c['claim_id'] not in ids or not c['proposed_text'].strip() for c in result['corrections']
    ):
        raise ValueError('Review correction has an unknown claim or empty replacement')
    return result, audit


FRESH_RECONCILE = (
    '\n'
    'This is a new conversation: the preceding turn is not available. The FIRST-PASS LIST '
    'above is the complete output of that independent research pass. Treat it as the '
    'preceding turn and continue from it.\n'
)


class FieldWorkflow:
    def __init__(self, root, config=None, models=None, state=None):
        self.root = Path(root).resolve()
        self.config = config or read_json(HERE / 'config.json')
        self.models = models or Models(self.config)
        self.state = state or ProviderState()
        (self.root / 'attempts').mkdir(parents=True, exist_ok=True)
        self.cache = self.root / 'workflow-cache'
        self.cache.mkdir(exist_ok=True)

    def stage(self, name, inputs, call, validate, retries=0, entries=None):
        """Per-stage immutable attempts and content-verified success cache.

        With `entries`, an ordered fallback list, each entry has its own cache key: the
        inputs plus that entry's {model, effort}, so keys made before fallback lists still
        match. `inputs` may instead be a function of the entry. Every entry's cache is
        checked before any call. The next entry is tried only after its provider reports
        exhaustion or the call times out; any other failure keeps the same-model retry.
        `call(folder, error, entry)` makes one attempt; `entry` is None without entries.
        """
        # A metadata or source-capture change must not silently resend content
        # already refused by the provider. A recorded refusal blocks this stage
        # for every model until explicitly resolved, whatever the current input hash.
        blocked_path = blocked_marker(self.root, name)
        if blocked_path:
            raise SafetyReviewBlocked(
                (
                    'Provider safety refusal remains unresolved for this stage; no '
                    'model call made, even if input metadata changed. See '
                )
                + str(blocked_path)
            )
        options = []
        for entry in entries or [None]:
            if entry is None:
                key_inputs = inputs
            elif callable(inputs):
                key_inputs = inputs(entry)
            else:
                key_inputs = {**inputs, 'model': cache_model(entry)}
            options.append((entry, fingerprint(key_inputs)))
        for entry, key in options:
            cached_path = self.cache / (name + '-' + key + '.json')
            if cached_path.exists():
                cached = read_json(cached_path)
                result = read_json(Path(cached['path']))
                if fingerprint(result) != cached['hash']:
                    raise ValueError('Cached stage output changed: ' + name)
                validate(result)
                return result, Path(cached['path']).parent
        unavailable = []
        last_error = None
        for entry, key in options:
            provider = entry.get('provider') if entry else None
            if provider and not self.state.available(provider):
                unavailable.append(describe(entry) + ': exhausted earlier, cooling down')
                continue
            try:
                return self.attempts(name, key, entry, call, validate, retries)
            except ProviderUnavailable as error:
                if error.reason == 'exhausted':
                    self.state.exhausted(error.provider)
                unavailable.append(str(error))
                last_error = error
        raise AccountExhausted(
            'No provider could run ' + name + ': ' + '; '.join(unavailable)
        ) from last_error

    def attempts(self, name, key, entry, call, validate, retries):
        """Immutable attempt folders for one entry, with its same-model retries."""
        cached_path = self.cache / (name + '-' + key + '.json')
        last = None
        for attempt in range(retries + 1):
            folder = self.root / 'attempts' / (name + '-' + uuid.uuid4().hex)
            folder.mkdir()
            receipt = {'stage': name, 'input_hash': key, 'status': 'running', 'started_at': now()}
            for field in ('provider', 'model', 'effort', 'search', 'mode'):
                if entry and field in entry:
                    receipt[field] = entry[field]
            write_json(folder / 'receipt.json', receipt)
            try:
                result = call(folder, last, entry)
                write_json(folder / 'result.json', result)
                validate(result)
                served = attempt_model(folder)
                if entry and served and served != entry.get('model'):
                    receipt['served_model'] = served
                receipt.update(status='complete', finished_at=now())
                write_json(folder / 'receipt.json', receipt)
                write_json(
                    cached_path, {'path': str(folder / 'result.json'), 'hash': fingerprint(result)}
                )
                return result, folder
            except BaseException as error:
                safety_message = provider_safety_refusal(folder)
                if safety_message:
                    marker = persist_safety_block(self.root, name, key, folder, safety_message)
                    receipt.update(
                        status='failed',
                        finished_at=now(),
                        error=str(error),
                        failure_kind='provider_safety_refusal',
                        blocked_marker=str(marker),
                    )
                    write_json(folder / 'receipt.json', receipt)
                    raise SafetyReviewBlocked(
                        (
                            'Provider refused this input for safety reasons; automatic retry '
                            'is disabled. See '
                        )
                        + str(marker)
                    ) from error
                receipt.update(status='failed', finished_at=now(), error=str(error))
                if isinstance(error, ProviderUnavailable):
                    receipt['failure_kind'] = 'provider_' + error.reason
                write_json(folder / 'receipt.json', receipt)
                if (
                    isinstance(
                        error,
                        (
                            ProviderUnavailable,
                            AccountExhausted,
                            SafetyReviewBlocked,
                            KeyboardInterrupt,
                            SystemExit,
                        ),
                    )
                    or attempt == retries
                ):
                    raise
                last = str(error)
        raise RuntimeError('Unreachable stage state')

    def research(self, spec, original):
        entries = stage_entries(self.config, 'research')
        text = (
            prompt(
                'research',
                FIELD=spec['field'],
                BOUNDARIES=spec['boundaries'],
                AS_OF=spec['as_of'],
                PREFIX=spec['prefix'],
            )
            + HEADER_RULE
        )
        workdir = self.root / 'grok-workspace'
        workdir.mkdir(exist_ok=True)

        def research_call(folder, error, entry):
            # A new conversation ID belongs to each independent research attempt.
            session = str(uuid.uuid4())
            return self.models.research(entry, text, folder, session, False, workdir)

        first, folder = self.stage(
            'independent-research',
            {'prompt': text},
            research_call,
            lambda v: validate_research(v['text'], spec['prefix']),
            entries=entries,
        )
        (self.root / 'research-notes.md').write_text(first['text'])
        ids = concept_ids(first['text'], spec['prefix'])
        reconcile_text = (
            prompt(
                'reconcile',
                FIELD=spec['field'],
                BOUNDARIES=spec['boundaries'],
                AS_OF=spec['as_of'],
                PREFIX=spec['prefix'],
                NEW_LIST=first['text'],
                ORIGINAL_LIST=original,
            )
            + HEADER_RULE
        )
        # Only a Grok first pass leaves a conversation to continue, and only Grok can
        # continue it. Every other entry starts a new conversation with the extra wording.
        session = first.get('session_id')
        reconcile_entries = []
        for entry in stage_entries(self.config, 'reconcile'):
            resume = entry['provider'] == 'grok' and session is not None
            reconcile_entries.append({**entry, 'mode': 'resume' if resume else 'fresh'})

        def reconcile_inputs(entry):
            if entry['mode'] == 'resume':
                return {'prompt': reconcile_text, 'model': cache_model(entry), 'session': session}
            return {'prompt': reconcile_text + FRESH_RECONCILE, 'model': cache_model(entry)}

        def reconcile_call(folder, error, entry):
            if entry['mode'] == 'resume':
                return self.models.research(entry, reconcile_text, folder, session, True, workdir)
            fresh = str(uuid.uuid4())
            return self.models.research(
                entry, reconcile_text + FRESH_RECONCILE, folder, fresh, False, workdir
            )

        reconciled, _ = self.stage(
            'reconcile',
            reconcile_inputs,
            reconcile_call,
            lambda v: validate_research(v['text'], spec['prefix'], ids),
            entries=reconcile_entries,
        )
        (self.root / 'reconciled-research.md').write_text(reconciled['text'])
        return reconciled['text']

    def structure(self, notes, spec, original):
        expected = validate_research(notes, spec['prefix'])
        original_numbers = sorted(
            set(int(n) for n in re.findall(r'^\s*(\d+)\.\s+\*\*', original, re.M))
        )
        text = prompt('format', NOTES=notes) + (
            '\n'
            'Return candidates in the candidates object. Also structure every historical '
            'disposition with its original_number, and the change log in their dedicated '
            'fields. Preserve every reconciled concept. Use empty quotations when no '
            'actual passage is supplied; never invent one.\n'
        )

        def call(folder, error, entry):
            settings = dict(entry)
            # A bounded formatting recovery: same model, lower reasoning after output
            # exhaustion. The cache key keeps the configured entry.
            if error and 'max_output_tokens' in error and settings['provider'] == 'codex':
                settings['effort'] = 'medium'
            try:
                return self.models.call(
                    'format',
                    text + ('\nPrevious validation failed: ' + error if error else ''),
                    FORMAT_SCHEMA,
                    folder,
                    entry=settings,
                )
            except ProviderUnavailable:
                raise
            except Exception as failure:
                log = folder / 'stdout.log'
                if log.exists() and 'max_output_tokens' in log.read_text():
                    raise RuntimeError(
                        'max_output_tokens: formatting output exhausted'
                    ) from failure
                raise

        value, _ = self.stage(
            'format-reconciled',
            {'prompt': text, 'schema': FORMAT_SCHEMA},
            call,
            lambda v: validate_format(v, expected, original_numbers),
            retries=1,
            entries=stage_entries(self.config, 'format'),
        )
        write_json(self.root / 'reconciled-structured.json', value)
        write_json(self.root / 'reconciled-candidates.json', value['candidates'])
        return value['candidates']

    def capture(self, doc):
        archive = Archive(self.root)
        recovery = read_json(self.root / 'source-recovery.json', {})

        def has_retained_bytes(url):
            # Legacy empty artifacts remain on disk for provenance, but are not captures.
            return any(
                (self.root / a['path']).stat().st_size > 0 for a in archive.state[url]['artifacts']
            )

        for source in doc['sources']:
            url = source['url']
            archive.capture(url)
            if has_retained_bytes(url) or url in recovery:
                continue
            # One bounded legal-copy lookup, only when a DOI is available.
            identifier = source.get('identifier') or url
            match = re.search(r'10\.\d{4,9}/[^\s]+', identifier)
            outcome = {
                'at': now(),
                'status': 'no_identifier',
                'next_action': 'Supply a legitimate copy or retain this access gap',
            }
            if match:
                doi = match[0].rstrip('.,;')
                endpoint = (
                    'https://www.ebi.ac.uk/europepmc/webservices/rest/search?'
                    + urllib.parse.urlencode(
                        {'query': 'DOI:"' + doi + '"', 'format': 'json', 'pageSize': 1}
                    )
                )
                try:
                    with urllib.request.urlopen(endpoint, timeout=30) as response:
                        found = json.load(response).get('resultList', {}).get('result', [])
                    outcome.update(status='no_open_copy', lookup_url=endpoint)
                    if (
                        found
                        and found[0].get('isOpenAccess') == 'Y'
                        and re.fullmatch(r'PMC\d+', found[0].get('pmcid', ''))
                    ):
                        alternative = (
                            'https://www.ebi.ac.uk/europepmc/webservices/rest/'
                            + found[0]['pmcid']
                            + '/fullTextXML'
                        )
                        archive.alternative(url, alternative)
                        outcome.update(
                            status='saved' if has_retained_bytes(url) else 'capture_failed',
                            alternative=alternative,
                        )
                except (OSError, ValueError) as error:
                    outcome.update(status='lookup_failed', error=str(error))
            recovery[url] = outcome
            write_json(self.root / 'source-recovery.json', recovery)
        # Extract once per URL, preserving truncation/extraction metadata in the index.
        evidence = {s['url']: archive.evidence(s['url']) for s in doc['sources']}
        index = []
        for source in doc['sources']:
            url = source['url']
            artifacts = []
            for item in archive.state[url]['artifacts']:
                path = self.root / item['path']
                if not path.is_file() or digest(path.read_bytes()) != item['sha256']:
                    raise ValueError('Source artifact missing or changed: ' + str(path))
                extracted = next(a for a in evidence[url] if a['sha256'] == item['sha256'])
                artifacts.append(
                    {
                        **item,
                        'absolute_path': str(path),
                        'verified': True,
                        'extracted_characters': len(extracted['text']),
                        'truncated': extracted['truncated'],
                        'extraction_issues': extracted['extraction_issues'],
                    }
                )
                if path.stat().st_size == 0:
                    artifacts[-1].update(byte_count=0, empty=True)
            refs = [
                {'concept': p['id'], 'claim': c['id']}
                for p in doc['problems']
                for c in p['claims']
                if any(e['url'] == url for e in c['citations'])
            ]
            index.append(
                {
                    'url': url,
                    'title': source['title'],
                    'status': 'saved'
                    if any(not a.get('empty', False) for a in artifacts)
                    else 'not_captured',
                    'artifacts': artifacts,
                    'used_by': refs,
                    'failed_operations': [
                        v
                        for v in archive.state[url]['operations'].values()
                        if v['status'] == 'failed'
                    ],
                    'recovery': recovery.get(url),
                }
            )
        write_json(self.root / 'source-file-index.json', index)
        return evidence

    def review(self, doc, spec, evidence):
        results = {}

        def one(candidate):
            wanted = {c['url'] for claim in candidate['claims'] for c in claim['citations']}
            payload = {
                'field': spec,
                'problem': candidate,
                'freshness': [],
                'sources': [
                    {**s, 'artifacts': evidence[s['url']]}
                    for s in doc['sources']
                    if s['url'] in wanted
                ],
            }
            payload, text = build_review_input(payload)

            def call(folder, error, entry):
                write_json(folder / 'input.json', payload)
                retry_error = (
                    error.encode('utf-8')[:2048].decode('utf-8', errors='ignore') if error else ''
                )
                model_text = text + (
                    '\nPrevious validation failed: '
                    + retry_error
                    + '\nCheck every quotation against its exact supplied artifact.'
                    if error
                    else ''
                )
                if len(model_text.encode('utf-8')) > MAX_REVIEW_PROMPT_BYTES:
                    raise ValueError('Review prompt exceeds total input budget')
                write_json(
                    folder / 'input-size.json',
                    {
                        'prompt_characters': len(model_text),
                        'prompt_bytes': len(model_text.encode('utf-8')),
                        'maximum_prompt_bytes': MAX_REVIEW_PROMPT_BYTES,
                    },
                )
                return self.models.call('review', model_text, REVIEW_SCHEMA, folder, entry=entry)

            raw, folder = self.stage(
                'review-' + candidate['id'],
                {'prompt': text, 'schema': REVIEW_SCHEMA},
                call,
                lambda v: normalize_and_validate_review(v, payload),
                retries=1,
                entries=stage_entries(self.config, 'review'),
            )
            value, audit = normalize_and_validate_review(raw, payload)
            write_json(folder / 'validated.json', value)
            if audit:
                write_json(
                    folder / 'repair-audit.json',
                    {'at': now(), 'changes': audit, 'scientific_judgments_changed': False},
                )
            return candidate['id'], {'status': 'complete', 'path': str(folder), 'review': value}

        failures = []
        exhausted = None
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(one, p): p['id'] for p in doc['problems']}
            for future in as_completed(futures):
                identifier = futures[future]
                try:
                    identifier, result = future.result()
                    results[identifier] = result
                except SafetyReviewBlocked:
                    # Only a recorded refusal withholds a concept. It is never narrowed,
                    # filtered, retried or sent to another model.
                    stage = 'review-' + identifier
                    marker = blocked_marker(self.root, stage)
                    if marker is None:
                        raise
                    results[identifier] = {
                        'status': 'withheld',
                        'stage': stage,
                        'reason': refusal_reason(marker),
                    }
                except Exception as error:
                    results[identifier] = {'status': 'failed', 'error': str(error)}
                    failures.append(identifier)
                    if isinstance(error, AccountExhausted):
                        exhausted = error
                write_json(self.root / 'reconciled-reviews.json', results)
        if exhausted:
            raise AccountExhausted(str(exhausted))
        if failures:
            raise ValueError('Final rewrite blocked by failed reviews: ' + ', '.join(failures))
        return results


def run_field(root, original_path, field, prefix, as_of, boundaries, state=None):
    """Execute one field, resuming validated stages and preserving every attempt.

    `state` is the batch's shared provider exhaustion record.
    """
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    spec = {'field': field, 'prefix': prefix, 'as_of': as_of, 'boundaries': boundaries}
    if (root / 'field.json').exists() and read_json(root / 'field.json') != spec:
        raise ValueError('Field settings differ from existing run')
    original = Path(original_path).read_text()
    with workflow_lock(root):
        prior = root / 'original-list.md'
        if prior.exists() and prior.read_text() != original:
            raise ValueError('Original list changed; use a new run directory')
        prior.write_text(original)
        write_json(
            root / 'original-list-provenance.json',
            {'path': str(Path(original_path).resolve()), 'sha256': digest(original.encode())},
        )
        write_json(root / 'field.json', spec)
        workflow = FieldWorkflow(root, state=state)
        receipt = {'started_at': now(), 'status': 'running', 'stage': 'research'}

        def status(stage):
            receipt.update(stage=stage, updated_at=now())
            write_json(root / 'workflow-receipt.json', receipt)

        try:
            status('research_and_reconcile')
            notes = workflow.research(spec, original)
            status('structure')
            doc = workflow.structure(notes, spec, original)
            status('capture')
            evidence = workflow.capture(doc)
            status('review')
            workflow.review(doc, spec, evidence)
            status('final_rewrite')
            from .final_rewrite import run

            run(root, workers=3, state=workflow.state)
            if not (root / 'final-innovations.json').is_file():
                raise ValueError('Final rewrite returned without a consolidated output')
            final = read_json(root / 'final-innovations.json')
            receipt.update(
                status='complete',
                finished_at=now(),
                concepts=len(final['innovations']),
                withheld=[item['id'] for item in final.get('withheld', [])],
            )
            write_json(root / 'workflow-receipt.json', receipt)
            return read_json(root / 'final-innovations.json')
        except BaseException as error:
            receipt.update(
                status='account_exhausted' if isinstance(error, AccountExhausted) else 'failed',
                finished_at=now(),
                error=str(error),
            )
            write_json(root / 'workflow-receipt.json', receipt)
            raise
