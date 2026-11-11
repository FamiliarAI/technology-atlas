import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ingestion.field_workflow import (
    AccountExhausted,
    SafetyReviewBlocked,
    FieldWorkflow,
    account_exhausted,
    concept_ids,
    normalize_and_validate_review,
    validate_format,
    validate_research,
    workflow_lock,
    build_review_input,
    REVIEW_INSTRUCTIONS,
)


class FieldWorkflowTests(unittest.TestCase):
    def test_reconciliation_must_preserve_independent_concepts(self):
        first = '**PHY-01. One**\ntext\n**PHY-02. Two**\n'
        self.assertEqual(concept_ids(first, 'PHY'), ['PHY-01', 'PHY-02'])
        with self.assertRaisesRegex(ValueError, 'dropped'):
            validate_research('**PHY-01. One**\n', 'PHY', concept_ids(first, 'PHY'))
        self.assertEqual(
            len(validate_research(first + '**PHY-03. Three**\n', 'PHY', concept_ids(first, 'PHY'))),
            3,
        )

    def test_cached_stage_resumes_without_call_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            flow = FieldWorkflow(directory, config={})
            calls = []

            def call(folder, error):
                calls.append(folder)
                return {'good': 1}

            value, folder = flow.stage(
                'test', {'input': 1}, call, lambda v: self.assertEqual(v['good'], 1)
            )
            flow.stage('test', {'input': 1}, call, lambda v: self.assertEqual(v['good'], 1))
            self.assertEqual(len(calls), 1)
            (folder / 'result.json').write_text('{"good":2}')
            with self.assertRaisesRegex(ValueError, 'changed'):
                flow.stage('test', {'input': 1}, call, lambda v: None)

    def test_bounded_retry_preserves_failed_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            flow = FieldWorkflow(directory, config={})
            calls = []

            def call(folder, error):
                calls.append(error)
                if error is None:
                    raise ValueError('bad quote')
                return {'ok': True}

            flow.stage('test', {}, call, lambda v: None, retries=1)
            self.assertEqual(calls, [None, 'bad quote'])
            states = [
                json.loads(p.read_text())['status']
                for p in Path(directory).glob('attempts/*/receipt.json')
            ]
            self.assertCountEqual(states, ['failed', 'complete'])

    def test_account_exhaustion_never_retried(self):
        self.assertTrue(account_exhausted('Insufficient credits'))
        self.assertFalse(account_exhausted('connection timed out'))
        with tempfile.TemporaryDirectory() as directory:
            flow = FieldWorkflow(directory, config={})
            calls = []

            def call(folder, error):
                calls.append(1)
                raise AccountExhausted('switch account')

            with self.assertRaises(AccountExhausted):
                flow.stage('research', {}, call, lambda v: None, retries=1)
            self.assertEqual(len(calls), 1)

    def test_grok_usage_balance_exhaustion_stops_without_retry(self):
        message = (
            'responses API error status=402 Payment Required error_message=Grok Build '
            'usage balance exhausted'
        )
        self.assertTrue(account_exhausted(message))
        self.assertTrue(account_exhausted('Grok Build usage balance exhausted'))
        self.assertTrue(account_exhausted('responses API error status=402 Payment Required'))
        self.assertFalse(account_exhausted('Publisher download returned HTTP 402 Payment Required'))
        self.assertFalse(account_exhausted('responses API error status=500 Internal Server Error'))
        with tempfile.TemporaryDirectory() as directory:
            flow = FieldWorkflow(
                directory, config={'grok': 'grok', 'research': {'model': 'test', 'effort': 'high'}}
            )
            launches = []

            class Process:
                returncode = 1

                def __init__(self, cmd, **kw):
                    launches.append(cmd)
                    kw['stderr'].write(message)
                    kw['stderr'].flush()

                def wait(self, timeout):
                    return 1

            with patch('ingestion.field_workflow.subprocess.Popen', Process):
                with self.assertRaisesRegex(AccountExhausted, 'switch accounts'):
                    flow.stage(
                        'reconcile',
                        {},
                        lambda folder, error: flow.grok('prompt', folder, 'test-session', True),
                        lambda v: None,
                        retries=1,
                    )
            self.assertEqual(len(launches), 1)
            receipt = json.loads(
                next(Path(directory).glob('attempts/reconcile-*/receipt.json')).read_text()
            )
            self.assertEqual(receipt['status'], 'failed')
            self.assertIn('switch accounts', receipt['error'])

    def test_free_usage_exhaustion_code_raises_account_exhausted(self):
        message = (
            'API error (status 429 Too Many Requests): subscription:free-usage-exhausted: '
            'Included free usage exhausted'
        )
        self.assertTrue(account_exhausted(message))
        self.assertTrue(account_exhausted('subscription:free-usage-exhausted'))
        self.assertFalse(account_exhausted('Publisher returned HTTP 429 Too Many Requests'))
        with tempfile.TemporaryDirectory() as directory:
            flow = FieldWorkflow(
                directory, config={'grok': 'grok', 'research': {'model': 'test', 'effort': 'high'}}
            )
            folder = Path(directory) / 'attempt'
            folder.mkdir()

            class Process:
                returncode = 1

                def __init__(self, command, **kwargs):
                    kwargs['stderr'].write(message)
                    kwargs['stderr'].flush()

                def wait(self, timeout):
                    return 1

            with patch('ingestion.field_workflow.subprocess.Popen', Process):
                with self.assertRaises(AccountExhausted):
                    flow.grok('test', folder, 'test-session', True)

    def test_provider_safety_refusal_is_not_retried_or_resent_on_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            flow = FieldWorkflow(directory, config={})
            calls = []

            def call(folder, error):
                calls.append(folder)
                event = {
                    'type': 'turn.failed',
                    'error': {
                        ('message'): (
                            "Invalid prompt: we've limited access to this content for "
                            'safety reasons. Provider refusal.'
                        )
                    },
                }
                (folder / 'stdout.log').write_text(json.dumps(event) + '\n')
                raise RuntimeError('Model CLI exited 1')

            with self.assertRaises(SafetyReviewBlocked):
                flow.stage('review-X-01', {'input': 'same'}, call, lambda v: None, retries=1)
            self.assertEqual(len(calls), 1)
            # A fresh controller instance must honor the durable block too.
            resumed = FieldWorkflow(directory, config={})
            with self.assertRaises(SafetyReviewBlocked):
                resumed.stage('review-X-01', {'input': 'same'}, call, lambda v: None, retries=1)
            self.assertEqual(len(calls), 1)
            # Source capture or extraction metadata changes cannot evade the refusal.
            with self.assertRaises(SafetyReviewBlocked):
                resumed.stage(
                    'review-X-01',
                    {'input': 'same', 'empty_source_warning': True},
                    call,
                    lambda v: None,
                    retries=1,
                )
            self.assertEqual(len(calls), 1)
            receipt = json.loads((calls[0] / 'receipt.json').read_text())
            self.assertEqual(receipt['status'], 'failed')
            self.assertEqual(receipt['failure_kind'], 'provider_safety_refusal')
            self.assertTrue(Path(receipt['blocked_marker']).is_file())

    def test_source_text_does_not_create_safety_block(self):
        with tempfile.TemporaryDirectory() as directory:
            flow = FieldWorkflow(directory, config={})
            calls = []

            def call(folder, error):
                calls.append(folder)
                (folder / 'stdout.log').write_text(
                    json.dumps(
                        {
                            'type': 'item.completed',
                            'item': {
                                ('text'): (
                                    "Invalid prompt: we've limited access to this content for "
                                    'safety reasons'
                                )
                            },
                        }
                    )
                    + '\n'
                )
                if error is None:
                    raise RuntimeError('temporary failure')
                return {'ok': True}

            flow.stage('review-X-01', {}, call, lambda v: None, retries=1)
            self.assertEqual(len(calls), 2)
            self.assertFalse((Path(directory) / 'workflow-blocked').exists())

    def test_same_session_resume_uses_persistent_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {'grok': 'grok', 'research': {'model': 'test', 'effort': 'high'}}
            flow = FieldWorkflow(directory, config=config)
            folder = Path(directory) / 'attempt'
            folder.mkdir()
            calls = []

            class Process:
                returncode = 0

                def __init__(self, cmd, **kw):
                    calls.append((cmd, kw['cwd']))
                    kw['stdout'].write(
                        json.dumps(
                            {'sessionId': 'test-session', 'stopReason': 'end_turn', 'text': 'notes'}
                        )
                    )
                    kw['stdout'].flush()

                def wait(self, timeout):
                    return 0

            with patch('ingestion.field_workflow.subprocess.Popen', Process):
                value = flow.grok('prompt', folder, 'test-session', True)
            self.assertEqual(value['session_id'], 'test-session')
            self.assertIn('--resume', calls[0][0])
            self.assertNotIn('--fork-session', calls[0][0])
            self.assertTrue(calls[0][1].is_dir())

    def test_empty_extraction_limitation_can_move_without_status_change(self):
        payload = {
            'problem': {
                'claims': [{'id': 'X-01-problem', 'citations': [{'url': 'https://example.org'}]}]
            },
            'sources': [
                {
                    'url': 'https://example.org',
                    'artifacts': [
                        {
                            'sha256': 'abc',
                            'text': '[Page 1]',
                            'truncated': False,
                            'extraction_issues': [],
                        }
                    ],
                }
            ],
        }
        value = {
            'concept_assessment': {
                'summary': 'Keep concept',
                'revolutionary_significance': 'A new capability',
                'scope_and_overlap': 'Distinct',
            },
            'corrections': [],
            'evidence_review': {
                'claims': [
                    {
                        'id': 'X-01-problem',
                        'status': 'unresolved',
                        'reason': 'No usable text',
                        'evidence': [
                            {
                                'url': 'https://example.org',
                                'artifact': 'abc',
                                'identity_verified': False,
                                'completeness': 'unknown',
                                'relation': 'unresolved',
                                'passage': '',
                                'locator': 'page 1',
                                'reason': 'Only a page marker was extracted',
                            }
                        ],
                    }
                ]
            },
        }
        original = copy.deepcopy(value)
        fixed, audit = normalize_and_validate_review(value, payload)
        self.assertEqual(value, original)
        self.assertEqual(fixed['evidence_review']['claims'][0]['status'], 'unresolved')
        self.assertEqual(fixed['evidence_review']['claims'][0]['evidence'], [])
        self.assertIn('Only a page marker', fixed['evidence_review']['claims'][0]['reason'])
        self.assertEqual(len(audit), 1)
        bad = copy.deepcopy(value)
        bad['evidence_review']['claims'][0]['evidence'][0]['passage'] = 'Fabricated quotation'
        with self.assertRaises(ValueError):
            normalize_and_validate_review(bad, payload)

    def test_format_rejects_dropped_concept_or_original_disposition(self):
        def candidate(identifier):
            return {
                'id': identifier,
                'title': 'Concept',
                'claims': [
                    {
                        'id': identifier + '-' + kind,
                        'kind': kind,
                        'text': 'Proposal',
                        'citations': [],
                    }
                    for kind in ('problem', 'completion', 'current_state', 'significance')
                ],
            }

        value = {
            'candidates': {
                'problems': [candidate('PHY-01')],
                'sources': [],
                'excluded': [],
                'coverage_note': 'Limited',
            },
            'original_dispositions': [
                {
                    'original_number': 1,
                    'original_title': 'Old',
                    'status': 'covered',
                    'concept_ids': ['PHY-01'],
                    'reason': 'Same capability',
                }
            ],
            'change_log': [],
        }
        validate_format(value, ['PHY-01'], [1])
        with self.assertRaisesRegex(ValueError, 'lost or invented'):
            validate_format(value, ['PHY-01', 'PHY-02'], [1])
        with self.assertRaisesRegex(ValueError, 'every original'):
            validate_format(value, ['PHY-01'], [1, 2])

    def test_review_pool_is_bounded_and_failure_blocks_completion(self):
        import threading
        import time

        active = 0
        peak = 0
        lock = threading.Lock()
        calls = {}

        class FakeModels:
            def call(self, role, text, schema, folder):
                nonlocal active, peak
                payload = json.loads((folder / 'input.json').read_text())
                identifier = payload['problem']['id']
                with lock:
                    active += 1
                    peak = max(peak, active)
                    calls[identifier] = calls.get(identifier, 0) + 1
                try:
                    time.sleep(0.02)
                    if identifier == 'PHY-04':
                        raise ValueError('invalid review')
                    return {
                        'concept_assessment': {
                            'summary': 'Keep',
                            'revolutionary_significance': 'Broad capability',
                            'scope_and_overlap': 'Distinct',
                        },
                        'corrections': [],
                        'evidence_review': {
                            'claims': [
                                {
                                    'id': c['id'],
                                    'status': 'unresolved',
                                    'reason': 'No supplied evidence',
                                    'evidence': [],
                                }
                                for c in payload['problem']['claims']
                            ]
                        },
                    }
                finally:
                    with lock:
                        active -= 1

        doc = {
            'problems': [
                {'id': f'PHY-{i:02d}', 'claims': [{'id': f'PHY-{i:02d}-problem', 'citations': []}]}
                for i in range(1, 8)
            ],
            'sources': [],
        }
        with tempfile.TemporaryDirectory() as directory:
            flow = FieldWorkflow(
                directory,
                config={'review': {'model': 'fake', 'effort': 'medium'}},
                models=FakeModels(),
            )
            with self.assertRaisesRegex(ValueError, 'blocked by failed reviews'):
                flow.review(doc, {}, {})
            self.assertLessEqual(peak, 3)
            self.assertGreater(peak, 1)
            self.assertEqual(calls['PHY-04'], 2)
            reviews = json.loads((Path(directory) / 'reconciled-reviews.json').read_text())
            self.assertEqual(reviews['PHY-04']['status'], 'failed')
            self.assertEqual(sum(v['status'] == 'complete' for v in reviews.values()), 6)

    def test_failed_capture_recovers_open_copy_under_original_url(self):
        import io
        from ingestion.sources import Archive

        original = 'https://publisher.example/blocked'
        alternate = 'https://www.ebi.ac.uk/europepmc/webservices/rest/PMC123/fullTextXML'

        def getter(url):
            if url == original:
                raise ValueError('publisher blocked')
            self.assertEqual(url, alternate)
            return (
                (
                    b'<article><article-title>Test source</article-title><abstract>Verified'
                    b' scientific evidence for this example.</abstract></article>'
                ),
                'application/xml',
                url,
            )

        doc = {
            'sources': [{'url': original, 'title': 'Test source', 'identifier': '10.1234/example'}],
            'problems': [
                {
                    'id': 'PHY-01',
                    'claims': [{'id': 'PHY-01-problem', 'citations': [{'url': original}]}],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            flow = FieldWorkflow(directory, config={})
            with (
                patch(
                    'ingestion.field_workflow.Archive', lambda root: Archive(root, getter=getter)
                ),
                patch(
                    'ingestion.field_workflow.urllib.request.urlopen',
                    return_value=io.BytesIO(
                        b'{"resultList":{"result":[{"isOpenAccess":"Y","pmcid":"PMC123"}]}}'
                    ),
                ) as lookup,
            ):
                evidence = flow.capture(doc)
                flow.capture(doc)
            self.assertEqual(lookup.call_count, 1)
            self.assertIn('Verified scientific evidence', evidence[original][0]['text'])
            index = json.loads((Path(directory) / 'source-file-index.json').read_text())
            self.assertEqual(index[0]['url'], original)
            self.assertEqual(index[0]['status'], 'saved')
            self.assertTrue(Path(index[0]['artifacts'][0]['absolute_path']).is_file())
            self.assertEqual(index[0]['failed_operations'][0]['status'], 'failed')

    def test_empty_successful_http_response_is_capture_failure(self):
        from ingestion.sources import Archive

        with tempfile.TemporaryDirectory() as directory:
            archive = Archive(directory, getter=lambda url: (b'', 'text/html', url))
            result = archive.capture('https://example.org/empty')
            self.assertEqual(result['artifacts'], [])
            operation = next(iter(result['operations'].values()))
            self.assertEqual(operation['status'], 'failed')
            self.assertIn('empty (0 bytes)', operation['attempts'][0]['error'])
            self.assertEqual(list((Path(directory) / 'sources').iterdir()), [])
            # Nonempty input retains its previous behavior.
            archive.getter = lambda url: (
                b'<html><p>A usable research abstract.</p></html>',
                'text/html',
                url,
            )
            self.assertEqual(len(archive.capture('https://example.org/valid')['artifacts']), 1)

    def test_legacy_empty_artifact_does_not_block_recovery_or_count_as_saved(self):
        import io
        from ingestion.sources import Archive, digest, write_json

        original = 'https://publisher.example/empty'
        doc = {
            'sources': [{'url': original, 'title': 'Example', 'identifier': '10.1234/example'}],
            'problems': [],
        }
        for found in (False, True):
            with self.subTest(open_copy=found), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive = Archive(root)
                empty = root / 'sources' / (digest(b'') + '.html')
                empty.write_bytes(b'')
                archive.state = {
                    original: {
                        'artifacts': [
                            {
                                'sha256': digest(b''),
                                'path': str(empty.relative_to(root)),
                                'format': 'html',
                                'kind': 'source',
                                'resolved_url': original,
                                'retrieved_at': 'old',
                                'extraction_issues': [],
                            }
                        ],
                        'operations': {
                            'source:' + original: {
                                'status': 'saved',
                                'target': original,
                                'artifact': digest(b''),
                                'attempts': [],
                                'pdf_urls': [],
                            }
                        },
                    }
                }
                archive.save()

                def getter(url):
                    return (
                        b'<article><abstract>Recovered scientific evidence.</abstract></article>',
                        'application/xml',
                        url,
                    )

                response = {
                    'resultList': {
                        'result': [{'isOpenAccess': 'Y', 'pmcid': 'PMC123'}] if found else []
                    }
                }
                flow = FieldWorkflow(root, config={})
                with (
                    patch('ingestion.field_workflow.Archive', lambda r: Archive(r, getter=getter)),
                    patch(
                        'ingestion.field_workflow.urllib.request.urlopen',
                        return_value=io.BytesIO(json.dumps(response).encode()),
                    ) as lookup,
                ):
                    evidence = flow.capture(doc)
                self.assertEqual(lookup.call_count, 1)
                self.assertTrue(empty.exists())
                self.assertEqual(empty.stat().st_size, 0)
                index = json.loads((root / 'source-file-index.json').read_text())[0]
                self.assertEqual(index['status'], 'saved' if found else 'not_captured')
                self.assertTrue(index['artifacts'][0]['empty'])
                self.assertEqual(index['artifacts'][0]['byte_count'], 0)
                self.assertIn(
                    'empty (0 bytes)', ' '.join(evidence[original][0]['extraction_issues'])
                )
                self.assertTrue(evidence[original][0]['empty'])
                self.assertEqual(evidence[original][0]['text'], '')
                if found:
                    self.assertEqual(len(evidence[original]), 2)

    def test_review_budget_preserves_small_inputs_exactly(self):
        from ingestion.pipeline import prompt

        payload = {
            'problem': {'id': 'PHY-01'},
            'sources': [
                {
                    'url': 'https://example.org',
                    'artifacts': [
                        {
                            'sha256': 'abc',
                            'path': 'sources/abc.txt',
                            'text': 'A short source.',
                            'truncated': False,
                            'extraction_issues': [],
                        }
                    ],
                }
            ],
        }
        original = copy.deepcopy(payload)
        bounded, text = build_review_input(payload)
        self.assertEqual(bounded, payload)
        self.assertEqual(payload, original)
        self.assertEqual(text, prompt('review', INPUT=json.dumps(payload)) + REVIEW_INSTRUCTIONS)

    def test_large_review_budget_keeps_all_sources_and_explicit_partial_excerpts(self):
        payload = {
            'problem': {'id': 'PHY-01', 'text': 'Do not shorten this concept'},
            'sources': [],
        }
        for i in range(3):
            payload['sources'].append(
                {
                    'url': f'https://example.org/{i}',
                    'artifacts': [
                        {
                            'sha256': f'{i}-{j}',
                            'path': f'sources/{i}-{j}.txt',
                            'text': (f'source{i} artifact{j} evidence ' + ('文' if i == 0 else 'x'))
                            * 2000,
                            'truncated': False,
                            'extraction_issues': [],
                        }
                        for j in range(4)
                    ],
                }
            )
        original = copy.deepcopy(payload)
        bounded, text = build_review_input(payload, max_prompt_bytes=50_000)
        self.assertLessEqual(len(text.encode('utf-8')), 50_000 - 4096)
        self.assertEqual(payload, original)
        self.assertEqual(bounded['problem'], payload['problem'])
        self.assertEqual(len(bounded['sources']), 3)
        for before, after in zip(payload['sources'], bounded['sources']):
            self.assertEqual(before['url'], after['url'])
            self.assertEqual(len(after['artifacts']), 4)
            for old, new in zip(before['artifacts'], after['artifacts']):
                self.assertEqual(old['sha256'], new['sha256'])
                self.assertEqual(old['path'], new['path'])
                self.assertTrue(new['text'])
                self.assertTrue(old['text'].startswith(new['text']))
                self.assertTrue(new['truncated'])
                self.assertTrue(new['extraction_issues'])
                self.assertEqual(
                    new['review_text_omitted_characters'], len(old['text']) - len(new['text'])
                )
                self.assertEqual(new['review_text_retained_characters'], len(new['text']))
        self.assertIn('partial excerpts', text)

    def test_review_budget_deduplicates_exact_text_before_truncation(self):
        artifacts = [
            {
                'sha256': str(i),
                'path': f'sources/{i}.txt',
                'text': 'Evidence sentence. ' * 1500,
                'truncated': False,
                'extraction_issues': [],
            }
            for i in range(3)
        ]
        payload = {
            'problem': {'id': 'PHY-01'},
            'sources': [
                {'url': f'https://example.org/{i}', 'artifacts': [a]}
                for i, a in enumerate(artifacts)
            ],
        }
        bounded, text = build_review_input(payload, max_prompt_bytes=40_000)
        self.assertLessEqual(len(text.encode('utf-8')), 40_000 - 4096)
        self.assertIn('text_reference', text)
        self.assertTrue(
            all(
                not a['truncated'] and a['text'] == artifacts[0]['text']
                for s in bounded['sources']
                for a in s['artifacts']
            )
        )

    def test_review_budget_avoids_escape_amplification_before_truncation(self):
        payload = {
            'problem': {'id': 'PHY-01'},
            'sources': [
                {
                    'url': 'https://example.org',
                    'artifacts': [
                        {
                            'sha256': 'abc',
                            'path': 'sources/abc.txt',
                            'text': '文' * 10000,
                            'truncated': False,
                            'extraction_issues': [],
                        }
                    ],
                }
            ],
        }
        bounded, text = build_review_input(payload, max_prompt_bytes=40_000)
        self.assertLessEqual(len(text.encode('utf-8')), 40_000 - 4096)
        self.assertEqual(
            bounded['sources'][0]['artifacts'][0]['text'],
            payload['sources'][0]['artifacts'][0]['text'],
        )
        self.assertFalse(bounded['sources'][0]['artifacts'][0]['truncated'])

    def test_workflow_lock_prevents_same_field_writers(self):
        with tempfile.TemporaryDirectory() as directory:
            with workflow_lock(Path(directory)):
                with self.assertRaisesRegex(RuntimeError, 'already running'):
                    with workflow_lock(Path(directory)):
                        pass

    def test_concept_ids_accept_atx_and_bold_without_claim_lines(self):
        body = (
            '\n'
            'CSC-01-problem: claim\n'
            '**CSC-01-significance. Claim**\n'
            '## CSC-01-current_state. Claim\n'
        )
        bold = '**CSC-01. One**' + body + '**CSC-02. Two**\n'
        atx = '## CSC-01. One' + body + '### CSC-02. Two\n'
        self.assertEqual(concept_ids(bold, 'CSC'), ['CSC-01', 'CSC-02'])
        self.assertEqual(concept_ids(atx, 'CSC'), concept_ids(bold, 'CSC'))
        self.assertEqual(validate_research(atx, 'CSC'), ['CSC-01', 'CSC-02'])


if __name__ == '__main__':
    unittest.main()
