import copy
import io
import logging
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import Mock, patch
import urllib.error
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ingestion import schemas
from ingestion.pipeline import (
    backup,
    locked,
    validate_candidates,
    validate_review,
    Models,
    execute,
    passage_matches,
    normalize_review_metadata,
)
from ingestion.sources import Archive, digest, extract, read_json, write_json

URL = 'https://example.org/paper'
PDF = 'https://example.org/paper.pdf'
PASSAGE = 'The experiment demonstrated operation for two hours under laboratory conditions.'
HTML = (
    f'<html><head><meta name="citation_pdf_url" content="{PDF}"></head>'
    f'<body><h1>Experiment report</h1><p>{PASSAGE}</p></body></html>'
).encode()
PLAIN = f'<html><body><h1>Experiment report</h1><p>{PASSAGE}</p></body></html>'.encode()


def paper_pdf():
    # Minimal valid single-page PDF fixture with real extractable text and xref.
    stream = f'BT /F1 10 Tf 10 100 Td ({PASSAGE}) Tj ET'.encode()
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        (
            b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 200] /Resources << /Font << '
            b'/F1 4 0 R >> >> /Contents 5 0 R >>'
        ),
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        f'<< /Length {len(stream)} >>\nstream\n'.encode() + stream + b'\nendstream',
    ]
    body = b'%PDF-1.4\n'
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(body))
        body += f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(body)
    body += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    body += b''.join(f'{o:010d} 00000 n \n'.encode() for o in offsets[1:])
    body += f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    return body


def candidates():
    return {
        'problems': [
            {
                'id': 'TEST-01',
                'title': 'Long-term operation',
                'claims': [
                    {
                        'id': f'TEST-01-{kind}',
                        'kind': kind,
                        'text': 'Operation for two hours in a laboratory',
                        'citations': [{'url': URL, 'quote': PASSAGE, 'locator': 'Results'}],
                    }
                    for kind in ('problem', 'completion', 'current_state', 'significance')
                ],
            }
        ],
        'sources': [
            {
                'url': URL,
                'title': 'Experiment report',
                'authors': None,
                'publisher': None,
                'published': None,
                'identifier': None,
            }
        ],
        'excluded': [],
        'coverage_note': 'Only one synthetic candidate; no scientific conclusions.',
    }


def reviewed(payload, status='supported'):
    items = payload['sources'][0]['artifacts']
    evidence = (
        []
        if not items
        else [
            {
                'url': URL,
                'artifact': items[0]['sha256'],
                'identity_verified': True,
                'completeness': 'full',
                'relation': status,
                'passage': PASSAGE,
                'locator': 'Results',
                'reason': 'The passage states the same duration and laboratory scope.',
            }
        ]
    )
    return {
        'claims': [
            {
                'id': c['id'],
                'status': status if evidence else 'unresolved',
                'reason': 'Assessed stated scope against the saved report.'
                if evidence
                else 'No readable evidence.',
                'evidence': copy.deepcopy(evidence),
            }
            for c in payload['problem']['claims']
        ]
    }


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_pdf_surrogate_pairs_and_lone_surrogates_are_utf8_safe(self):
        cases = [
            ('Plain text café 𝛼 😀', 'Plain text café 𝛼 😀'),
            ('\ud83d\ude00 \ud835\udefc', '😀 𝛼'),
            ('\ud800start middle\udfff end\udbff', '\ufffdstart middle\ufffd end\ufffd'),
            ('\ud800\ud83d\ude00\udfff', '\ufffd😀\ufffd'),
            ('\udfff\ud800', '\ufffd\ufffd'),
        ]
        for extracted, expected in cases:
            with self.subTest(extracted=ascii(extracted)):
                page = Mock()
                page.extract_text.return_value = extracted
                with patch('pypdf.PdfReader') as reader:
                    reader.return_value.pages = [page]
                    ext, text, issues, links = extract(paper_pdf(), 'application/pdf')
                self.assertEqual(ext, 'pdf')
                self.assertEqual(text, '[Page 1]\n' + expected)
                self.assertEqual(text.encode('utf-8').decode('utf-8'), text)
                self.assertEqual(issues, [])
                self.assertEqual(links, [])

    def test_pdf_skipped_content_warning_is_retained_without_discarding_text(self):
        class Page:
            def extract_text(self):
                logging.getLogger('pypdf._page').warning(
                    'Exceeded form invocations; further form content is skipped.'
                )
                return PASSAGE

        class Reader:
            pages = [Page()]

        with patch('pypdf.PdfReader', return_value=Reader()):
            _, text, issues, _ = extract(paper_pdf(), 'application/pdf')
        self.assertIn(PASSAGE, text)
        self.assertTrue(any('content is skipped' in issue for issue in issues))
        _, _, clean_issues, _ = extract(paper_pdf(), 'application/pdf')
        self.assertEqual([], clean_issues)

    def test_ordinary_pdf_links_are_captured_without_recursive_crawling(self):
        calls = []

        def get(url):
            calls.append(url)
            if url == URL:
                return (
                    (
                        b'<html><a href="/paper.pdf?download=1">Paper</a><a '
                        b'href="/unrelated">More</a></html>'
                    ),
                    'text/html',
                    URL,
                )
            return paper_pdf(), 'application/pdf', url

        archive = Archive(self.root, get)
        archive.capture(URL)
        self.assertEqual([URL, PDF + '?download=1'], calls)
        self.assertEqual(2, len(archive.source(URL)['artifacts']))

    def test_failed_pdf_remains_visible_and_retry_only_fetches_pdf(self):
        calls = []
        available = False

        def get(url):
            calls.append(url)
            if url == URL:
                return HTML, 'text/html', URL
            if not available:
                raise urllib.error.HTTPError(url, 403, 'Blocked', {}, None)
            return paper_pdf(), 'application/pdf', PDF

        archive = Archive(self.root, get, lambda _: None)
        archive.capture(URL)
        first = copy.deepcopy(archive.state[URL]['artifacts'])
        self.assertEqual('failed', archive.state[URL]['operations'][f'paper_pdf:{PDF}']['status'])
        archive.capture(URL)
        self.assertEqual([URL, PDF], calls)
        available = True
        archive.capture(URL, retry=True)
        self.assertEqual([URL, PDF, PDF], calls)
        self.assertEqual(first[0], archive.state[URL]['artifacts'][0])
        self.assertEqual('saved', archive.state[URL]['operations'][f'paper_pdf:{PDF}']['status'])

    def test_repeated_transient_failure_is_bounded_and_keeps_earlier_artifact(self):
        calls, waits = [], []

        def get(url):
            calls.append(url)
            raise TimeoutError('timeout')

        archive = Archive(self.root, get, waits.append)
        file = self.root / 'manual.html'
        file.write_bytes(PLAIN)
        sha = archive.attach(URL, file)
        archive.capture(URL)
        self.assertEqual(2, len(calls))
        self.assertEqual([5], waits)
        self.assertEqual(sha, archive.evidence(URL)[0]['sha256'])
        archive.capture(URL)
        self.assertEqual(2, len(calls))

    def test_long_retry_after_defers_without_sleeping_or_hammering(self):
        calls, waits = [], []

        def get(url):
            calls.append(url)
            raise urllib.error.HTTPError(url, 429, 'wait', {'Retry-After': '600'}, None)

        archive = Archive(self.root, get, waits.append)
        op = archive.operation(URL, URL)
        self.assertEqual(1, len(calls))
        self.assertEqual([], waits)
        self.assertIn('600', op['next_action'])

    def test_manual_copy_without_doi_is_idempotent_and_hash_checked(self):
        archive = Archive(self.root)
        path = self.root / 'copy.html'
        path.write_bytes(PLAIN)
        sha = archive.attach(URL, path)
        self.assertEqual(sha, archive.attach(URL, path))
        self.assertEqual(1, len(archive.source(URL)['artifacts']))
        saved = self.root / archive.source(URL)['artifacts'][0]['path']
        saved.write_bytes(b'corrupted')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            archive.evidence(URL)

    def test_block_page_and_fake_pdf_are_not_successful_captures(self):
        for body, ct in [
            (b'<html>Verify you are human captcha</html>', 'text/html'),
            (PLAIN, 'application/pdf'),
        ]:
            with self.subTest(ct=ct):
                archive = Archive(self.root, lambda _: (body, ct, URL))
                op = archive.operation(URL, URL, retry=True)
                self.assertEqual('failed', op['status'])
                self.assertEqual([], archive.source(URL)['artifacts'])

    def test_html_at_pdf_link_remains_failed_even_with_saved_landing_page(self):
        archive = Archive(self.root, lambda url: (HTML if url == URL else PLAIN, 'text/html', url))
        archive.capture(URL)
        self.assertEqual('failed', archive.source(URL)['operations'][f'paper_pdf:{PDF}']['status'])
        self.assertEqual(1, len(archive.source(URL)['artifacts']))

    def test_relative_pdf_link_uses_resolved_page_url(self):
        calls = []

        def get(url):
            calls.append(url)
            if url == URL:
                return (
                    (
                        b'<html><meta content="full.pdf" name="citation_pdf_url"><body>Paper</b'
                        b'ody></html>'
                    ),
                    'text/html',
                    'https://example.org/articles/1/',
                )
            return PLAIN, 'text/html', url

        Archive(self.root, get).capture(URL)
        self.assertEqual('https://example.org/articles/1/full.pdf', calls[-1])

    def test_malformed_pdf_is_retained_with_extraction_issue(self):
        archive = Archive(
            self.root, lambda _: (b'%PDF-1.4\nnot a real pdf', 'application/pdf', URL)
        )
        archive.capture(URL)
        item = archive.evidence(URL)[0]
        self.assertTrue(item['extraction_issues'])
        self.assertEqual('', item['text'])

    def test_real_http_redirect_pdf_download_and_local_passage_review(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                if self.path == '/start':
                    self.send_response(302)
                    self.send_header('Location', '/article/')
                    self.end_headers()
                    return
                if self.path == '/article/':
                    content = (
                        b'<html><meta name="citation_pdf_url" '
                        b'content="paper.pdf"><body>Experiment report '
                        b'abstract</body></html>'
                    )
                    content_type = 'text/html'
                else:
                    content = paper_pdf()
                    content_type = 'application/pdf'
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.end_headers()
                self.wfile.write(content)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            url = f'http://127.0.0.1:{server.server_port}/start'
            archive = Archive(self.root)
            archive.capture(url)
            artifacts = archive.evidence(url)
            pdf = next(a for a in artifacts if a['format'] == 'pdf')
            self.assertIn(PASSAGE, pdf['text'])
            self.assertFalse(pdf['extraction_issues'])
            self.assertEqual(['/start', '/article/', '/article/paper.pdf'], requests)
            archive.capture(url)
            self.assertEqual(3, len(requests))
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_valid_pdf_extracts_pages_without_old_80_page_limit(self):
        from pypdf import PdfWriter

        writer = PdfWriter()
        for _ in range(81):
            writer.add_blank_page(width=72, height=72)
        output = io.BytesIO()
        writer.write(output)
        ext, text, issues, links = extract(output.getvalue(), 'application/pdf')
        self.assertEqual('pdf', ext)
        self.assertIn('[Page 81]', text)
        self.assertTrue(issues)
        self.assertFalse(links)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.doc = candidates()
        self.payload = {
            'problem': self.doc['problems'][0],
            'sources': [
                {
                    'url': URL,
                    'artifacts': [
                        {
                            'sha256': digest(PLAIN),
                            'text': PASSAGE,
                            'truncated': False,
                            'extraction_issues': [],
                        }
                    ],
                }
            ],
        }
        self.review = reviewed(self.payload)

    def test_capture_metadata_normalization_preserves_claims_and_raw_output(self):
        original = copy.deepcopy(self.review)
        self.payload['sources'][0]['artifacts'][0]['truncated'] = True
        self.review['claims'][0]['evidence'][0]['artifact'] = (
            'sha256:' + self.review['claims'][0]['evidence'][0]['artifact']
        )
        raw = copy.deepcopy(self.review)
        normalized = normalize_review_metadata(self.review, self.payload)
        validate_review(normalized, self.payload)
        self.assertEqual(raw, self.review)
        self.assertEqual(original['claims'][0]['status'], normalized['claims'][0]['status'])
        self.assertEqual(original['claims'][0]['reason'], normalized['claims'][0]['reason'])
        self.assertEqual('partial', normalized['claims'][0]['evidence'][0]['completeness'])
        self.assertEqual(
            original['claims'][0]['evidence'][0]['artifact'],
            normalized['claims'][0]['evidence'][0]['artifact'],
        )

    def test_metadata_normalization_does_not_repair_unknown_hashes_or_quotes(self):
        self.review['claims'][0]['evidence'][0]['artifact'] = 'sha256:made-up'
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            validate_review(normalize_review_metadata(self.review, self.payload), self.payload)
        self.review = reviewed(self.payload)
        self.review['claims'][0]['evidence'][0]['passage'] = 'A fabricated result'
        with self.assertRaisesRegex(ValueError, 'absent'):
            validate_review(normalize_review_metadata(self.review, self.payload), self.payload)

    def test_resolved_url_reference_requires_unique_same_artifact_and_is_audited(self):
        from ingestion.field_workflow import normalize_and_validate_review

        resolved = 'https://repository.example/actual-paper.pdf'
        self.payload['sources'][0]['artifacts'][0]['resolved_url'] = resolved
        self.review['claims'][0]['evidence'][0]['url'] = resolved
        self.review['claims'][0]['evidence'][0]['artifact'] = (
            'sha256:' + self.review['claims'][0]['evidence'][0]['artifact']
        )
        raw = {
            'concept_assessment': {
                'summary': 'Keep',
                'revolutionary_significance': 'New capability',
                'scope_and_overlap': 'Distinct',
            },
            'corrections': [],
            'evidence_review': self.review,
        }
        original = copy.deepcopy(raw)
        fixed, audit = normalize_and_validate_review(raw, self.payload)
        self.assertEqual(raw, original)
        fixed_evidence = fixed['evidence_review']['claims'][0]['evidence'][0]
        self.assertEqual(fixed_evidence['url'], URL)
        self.assertEqual(fixed_evidence['artifact'], digest(PLAIN))
        self.assertEqual(fixed_evidence['passage'], PASSAGE)
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0]['source_reference_before']['url'], resolved)
        self.assertEqual(audit[0]['source_reference_after']['url'], URL)

    def test_resolved_url_normalization_rejects_wrong_hash_or_ambiguity(self):
        resolved = 'https://repository.example/actual-paper.pdf'
        self.payload['sources'][0]['artifacts'][0]['resolved_url'] = resolved
        self.review['claims'][0]['evidence'][0]['url'] = resolved
        self.review['claims'][0]['evidence'][0]['artifact'] = 'made-up'
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            validate_review(normalize_review_metadata(self.review, self.payload), self.payload)
        self.review['claims'][0]['evidence'][0]['artifact'] = digest(PLAIN)
        duplicate = copy.deepcopy(self.payload['sources'][0])
        duplicate['url'] = 'https://example.org/other-record'
        self.payload['sources'].append(duplicate)
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            validate_review(normalize_review_metadata(self.review, self.payload), self.payload)
        self.payload['sources'].pop()
        self.review['claims'][0]['evidence'][0]['url'] = (
            'https://repository.example/similar-paper.pdf'
        )
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            validate_review(normalize_review_metadata(self.review, self.payload), self.payload)

    def test_pdf_presentation_ligatures_match_without_rewriting_math(self):
        self.assertTrue(
            passage_matches(
                'unless there are efficient quantum algorithms',
                'unless there are eﬃcient quantum algorithms',
            )
        )
        for plain, ligature in [
            ('ff', 'ﬀ'),
            ('fi', 'ﬁ'),
            ('fl', 'ﬂ'),
            ('ffi', 'ﬃ'),
            ('ffl', 'ﬄ'),
            ('st', 'ﬅ'),
            ('st', 'ﬆ'),
        ]:
            self.assertTrue(passage_matches(plain, ligature))
        self.assertFalse(passage_matches('x2 = 4', 'x² = 4'))
        self.assertFalse(passage_matches('H2O', 'H₂O'))
        self.assertFalse(passage_matches('A = 1', '𝐀 = 1'))
        self.assertFalse(
            passage_matches('efficient algorithms exist', 'efficient algorithms do not exist')
        )

    def test_quote_glyphs_match_only_as_delimiters_not_lexical_apostrophes(self):
        quoted = (
            'data is not transmitted as SFQ voltage pulses but as positive (logic ‘1’) or '
            'negative (logic ‘0’) current'
        )
        source = (
            'data is not transmitted as SFQ\n'
            'voltage pulses but as positive (logic “1”) or negative (logic\n'
            '“0”) current'
        )
        self.assertTrue(passage_matches(quoted, source))
        self.assertTrue(passage_matches("the 'reset state' is zero", 'the “reset state” is zero'))
        self.assertTrue(passage_matches("doesn't", 'doesn’t'))
        self.assertFalse(passage_matches('doesn"t', "doesn't"))
        self.assertFalse(passage_matches('researchers" results', "researchers' results"))
        self.assertFalse(passage_matches('f"(x)', "f'(x)"))
        self.assertFalse(passage_matches('logic ‘1’', 'logic “0”'))
        self.assertFalse(passage_matches('is transmitted as SFQ', 'is not transmitted as SFQ'))

    def test_typography_validation_preserves_raw_review_and_artifact_text(self):
        for source in self.payload['sources']:
            for artifact in source['artifacts']:
                artifact['text'] = 'An eﬃcient process uses logic “1”.'
        for claim in self.review['claims']:
            claim['evidence'][0]['passage'] = 'An efficient process uses logic ‘1’.'
        original_review = copy.deepcopy(self.review)
        original_payload = copy.deepcopy(self.payload)
        validate_review(self.review, self.payload)
        self.assertEqual(self.review, original_review)
        self.assertEqual(self.payload, original_payload)

    def test_line_end_hyphenation_matches_without_loosening_words_or_numbers(self):
        text = 'The series-\nconnected cells ran for 30 hours, respec-\ntively.'
        self.assertTrue(
            passage_matches('The series-connected cells ran for 30 hours, respectively.', text)
        )
        self.assertFalse(
            passage_matches('The series-connected cells ran for 300 hours, respectively.', text)
        )
        self.assertFalse(
            passage_matches('The series-connected cells ran for 30 days, respectively.', text)
        )
        self.assertFalse(passage_matches('resign', 're-sign'))
        self.assertFalse(passage_matches('nowhere', 'now here'))

    def test_pdf_hyphen_layout_is_not_a_fabricated_quote(self):
        self.payload['sources'][0]['artifacts'][0]['text'] = (
            'The series - connected cells ran for 30 hours.'
        )
        for c in self.review['claims']:
            c['evidence'][0]['passage'] = 'The series -connected cells ran for 30 hours.'
        validate_review(self.review, self.payload)
        self.review['claims'][0]['evidence'][0]['passage'] = (
            'The series -connected cells ran for 300 hours.'
        )
        with self.assertRaisesRegex(ValueError, 'absent'):
            validate_review(self.review, self.payload)

    def test_supported_claim_requires_its_own_saved_passage_and_identity(self):
        validate_review(self.review, self.payload)
        for change in (
            {'artifact': 'made-up'},
            {'passage': 'A claim absent from the paper'},
            {'identity_verified': False},
        ):
            with self.subTest(change=change):
                bad = copy.deepcopy(self.review)
                bad['claims'][0]['evidence'][0].update(change)
                with self.assertRaises(ValueError):
                    validate_review(bad, self.payload)

    def test_quote_presence_does_not_override_scientific_scope_assessment(self):
        self.payload['problem']['claims'][0]['text'] = (
            'Operation for a lifetime in all environments'
        )
        self.review['claims'][0].update(
            status='unresolved', reason='Two laboratory hours do not establish lifetime operation.'
        )
        self.review['claims'][0]['evidence'][0]['relation'] = 'unresolved'
        validate_review(self.review, self.payload)
        self.assertEqual('unresolved', self.review['claims'][0]['status'])

    def test_reviewer_can_link_existing_problem_source_to_another_claim(self):
        self.payload['problem']['claims'][0]['citations'] = []
        validate_review(self.review, self.payload)
        self.assertEqual('supported', self.review['claims'][0]['status'])

    def test_missing_text_is_unresolved_not_contradicted(self):
        self.payload['sources'][0]['artifacts'] = []
        review = reviewed(self.payload)
        validate_review(review, self.payload)
        self.assertTrue(all(c['status'] == 'unresolved' for c in review['claims']))
        review['claims'][0]['status'] = 'contradicted'
        with self.assertRaises(ValueError):
            validate_review(review, self.payload)

    def test_missing_duplicate_or_unrelated_claim_evidence_rejected(self):
        for change in ('missing', 'duplicate', 'unrelated'):
            bad = copy.deepcopy(self.review)
            if change == 'missing':
                bad['claims'].pop()
            if change == 'duplicate':
                bad['claims'].append(bad['claims'][0])
            if change == 'unrelated':
                bad['claims'][0]['evidence'][0]['url'] = 'https://example.org/other'
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_review(bad, self.payload)

    def test_truncated_source_cannot_be_certified_complete(self):
        self.payload['sources'][0]['artifacts'][0]['truncated'] = True
        with self.assertRaisesRegex(ValueError, 'full capture'):
            validate_review(self.review, self.payload)

    def test_bad_optional_citation_does_not_cancel_valid_support(self):
        other = 'https://example.org/missing'
        self.payload['problem']['claims'][0]['citations'].append(
            {'url': other, 'quote': '', 'locator': ''}
        )
        self.payload['sources'].append({'url': other, 'artifacts': []})
        validate_review(self.review, self.payload)

    def test_incomplete_candidates_and_broken_references_are_rejected(self):
        for change in ('kinds', 'url', 'duplicate'):
            bad = copy.deepcopy(self.doc)
            if change == 'kinds':
                bad['problems'][0]['claims'].pop()
            if change == 'url':
                bad['sources'] = []
            if change == 'duplicate':
                bad['problems'].append(bad['problems'][0])
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_candidates(bad)


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'field'
        self.root.mkdir()
        self.config = read_json(Path(__file__).parents[1] / 'config.json')

    def test_backup_reopens_every_source_and_refuses_overwrite(self):
        archive = Archive(self.root, lambda url: (PLAIN, 'text/html', url))
        archive.capture(URL)
        dest = Path(self.temp.name) / 'backup'
        receipt = backup(self.root, dest)
        self.assertTrue(receipt['files'])
        self.assertEqual(archive.evidence(URL), Archive(dest).evidence(URL))
        with self.assertRaises(ValueError):
            backup(self.root, dest)
        with self.assertRaises(ValueError):
            backup(self.root, self.root / 'nested')

    def test_concurrent_run_lock_is_released_after_failure(self):
        with self.assertRaises(RuntimeError):
            with locked(self.root):
                with self.assertRaises(ValueError):
                    with locked(self.root):
                        pass
                raise RuntimeError('failure')
        with locked(self.root):
            pass

    def test_model_cli_exit_failure_keeps_logs(self):
        with self.assertRaisesRegex(RuntimeError, 'exited 2'):
            execute(['/bin/sh', '-c', 'echo failed >&2; exit 2'], self.root)
        self.assertIn('failed', (self.root / 'stderr.log').read_text())

    def test_timeout_stops_process(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            execute(['/bin/sleep', '5'], self.root, timeout=0.02)

    def test_model_cli_failure_message_names_no_provider_account(self):
        with self.assertRaises(RuntimeError) as caught:
            execute(['/bin/sh', '-c', 'exit 3'], self.root)
        self.assertNotIn('Grok', str(caught.exception))
        self.assertNotIn('credits', str(caught.exception))

    def test_model_adapter_uses_configured_cli_schema_and_preserves_raw_output(self):
        adapter = Models(self.config)

        def fake_execute(cmd, directory, stdin=None, timeout=3600, cwd=None, check=True):
            self.assertNotIn('--search', cmd)
            self.assertIn('--ignore-user-config', cmd)
            self.assertIn('read-only', cmd)
            self.assertIn(self.config['format']['model'], cmd)
            write_json(directory / 'response.json', candidates())
            return 0

        with patch('ingestion.providers.execute', fake_execute):
            result = adapter.call('format', 'Format only', schemas.CANDIDATES, self.root)
        self.assertEqual(candidates(), result)
        self.assertTrue((self.root / 'schema.json').exists())


if __name__ == '__main__':
    unittest.main()
