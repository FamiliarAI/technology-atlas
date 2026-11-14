"""Whole-atlas runs: selection flags, resumability, serialised writes, stopping on exhaustion,
and which saved copy is read."""

import io
import json
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ingestion.providers import ProviderExhausted

from atlas import batch, brief as briefs, copies, core, find as finding
from atlas.copies import Copy
from atlas.store import rebuild, resolver, sha

SECTIONS = [
    'concept',
    'significance',
    'missing_breakthrough',
    'current_state',
    'completion_criteria',
    'related_concepts',
]
TEXT = 'Results: the device worked for a year in every patient. ' * 40


def record(identifier, urls):
    item = {
        'id': identifier,
        'title': f'Breakthrough {identifier}',
        'change_log': [],
        'unresolved_issues': [],
        'provenance': {},
        'models': {},
        'sources': [{'url': url, 'title': 'Paper ' + url, 'status': 'saved'} for url in urls],
    }
    for section in SECTIONS:
        item[section] = [{'text': f'{section} of {identifier}.', 'source_urls': []}]
    return item


def reply(identifier, urls):
    return {
        'title': 'A plain title',
        'possible': ['People could do more.'],
        'why': ['It would help many people.'],
        'sources': [
            {
                'url': url,
                'who': 'A team',
                'showed': 'They showed a thing.',
                'quote': None,
                'cited_for': 'It supports the case.',
                'not_established': 'It is not the whole breakthrough.',
            }
            for url in urls
        ],
        'shown': ['Something has been shown.'],
        'missing': ['One thing.', 'Another thing.'],
        'milestones': [{'id': 'm1', 'label': 'A result', 'explanation': 'It would matter.'}],
        'uncertain': ['An open question.'],
    }


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.core = self.root / 'core'
        self.db = self.root / 'atlas.sqlite3'
        folder = self.root / 'runs' / 'NRL'
        folder.mkdir(parents=True)
        self.sources = {
            'NRL-01': ['https://example.org/a', 'https://example.org/b'],
            'NRL-02': ['https://example.org/c'],
            'NRL-03': [],
            'NRL-04': [],
        }
        value = {
            'field': {'prefix': 'NRL', 'field': 'Neurology', 'boundaries': 'Neurology.'},
            'created_at': '2026-11-01T00:00:00+00:00',
            'innovations': [record(key, urls) for key, urls in self.sources.items()],
        }
        (folder / 'final-innovations.json').write_text(json.dumps(value))
        core.import_field(folder, self.core)
        patcher = patch(
            'atlas.store.resolver', side_effect=lambda roots: resolver([self.root / 'runs'])
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        rebuild(self.core, self.db)
        calls = patch('atlas.find.CALLS', self.root / 'find')
        calls.start()
        self.addCleanup(calls.stop)

    def tearDown(self):
        self.tmp.cleanup()

    # atlas.batch

    def test_writes_are_serialised_and_committed_every_n(self):
        inside, overlaps, messages = [0], [], []
        guard = threading.Lock()

        def action():
            with guard:
                inside[0] += 1
                overlaps.append(inside[0])
            time.sleep(0.01)
            with guard:
                inside[0] -= 1

        writer = batch.Writer(2, True, lambda done: ' '.join(done), self.core)

        def work(identifier, stop):
            time.sleep(0.005)  # a model call, in parallel
            return writer.write(identifier, action)

        with patch('atlas.core.commit', side_effect=messages.append):
            outcomes, exhausted = batch.run(list('abcde'), work, 4)
            writer.flush()
        self.assertFalse(exhausted)
        self.assertEqual(max(overlaps), 1)
        self.assertEqual([status for status, _ in outcomes.values()], ['done'] * 5)
        self.assertEqual(sorted(' '.join(messages).split()), list('abcde'))
        self.assertEqual([len(message.split()) for message in messages], [2, 2, 1])

    def test_exhaustion_stops_the_run_and_a_failure_does_not(self):
        started = []

        def work(identifier, stop):
            started.append(identifier)
            if identifier == 'b':
                raise RuntimeError('broken page')
            if identifier == 'c':
                raise ProviderExhausted('codex', 'Codex usage exhausted')
            return identifier

        outcomes, exhausted = batch.run(list('abcde'), work, 1)
        self.assertTrue(exhausted)
        self.assertEqual(started, list('abc'))
        self.assertEqual(
            [status for status, _ in outcomes.values()],
            ['done', 'failed', 'failed', 'stopped', 'stopped'],
        )

    def test_adaptive_rises_until_throttled_then_settles_20_percent_below(self):
        throttled, peak, lines = [0], [0], []
        inside = [0]
        guard = threading.Lock()
        path = self.root / 'workers.json'

        def work(identifier, stop):
            with guard:
                inside[0] += 1
                peak[0] = max(peak[0], inside[0])
                # The provider starts refusing connections once 14 calls run at once.
                if inside[0] >= 14:
                    throttled[0] += 1
            time.sleep(0.002)
            with guard:
                inside[0] -= 1
            return identifier

        adaptive = batch.Adaptive(
            start=6,
            most=48,
            path=path,
            throttled=lambda: throttled[0],
            load=lambda: 0,
            log=lines.append,
        )
        outcomes, _ = batch.run([str(n) for n in range(400)], work, adaptive)
        self.assertEqual({status for status, _ in outcomes.values()}, {'done'})
        self.assertTrue(adaptive.settled, lines)
        self.assertGreaterEqual(adaptive.ceiling, 14)
        self.assertEqual(adaptive.limit, int(adaptive.ceiling * 0.8))
        self.assertLessEqual(peak[0], adaptive.ceiling)
        self.assertIn('settling at', ' '.join(lines))
        saved = json.loads(path.read_text())
        self.assertEqual(saved['workers'], adaptive.limit)
        # A later run starts where this one settled, without climbing.
        again = batch.Adaptive(start=6, path=path, throttled=lambda: 0, load=lambda: 0, log=str)
        self.assertEqual((again.limit, again.settled), (adaptive.limit, True))

    def test_adaptive_without_throttling_rises_to_the_cap_and_a_later_run_starts_there(self):
        path = self.root / 'workers.json'
        adaptive = batch.Adaptive(
            start=2, most=10, path=path, throttled=lambda: 0, load=lambda: 0, log=str
        )
        batch.run([str(n) for n in range(200)], lambda identifier, stop: identifier, adaptive)
        self.assertEqual((adaptive.limit, adaptive.settled), (10, False))
        # The level reached is kept with no failure point: a later run starts there, still rising.
        self.assertEqual(json.loads(path.read_text())['ceiling'], None)
        again = batch.Adaptive(
            start=2, most=12, path=path, throttled=lambda: 0, load=lambda: 0, log=str
        )
        self.assertEqual((again.limit, again.settled), (10, False))

    def test_adaptive_backs_off_when_the_machine_is_overloaded(self):
        adaptive = batch.Adaptive(start=10, most=48, throttled=lambda: 0, load=lambda: 3.5, log=str)
        batch.run([str(n) for n in range(5)], lambda identifier, stop: identifier, adaptive)
        self.assertEqual((adaptive.ceiling, adaptive.limit), (10, 8))

    def test_codex_throttling_is_counted_from_its_error_events(self):
        from ingestion import providers

        folder = self.root / 'call'
        folder.mkdir()
        (folder / 'stderr.log').write_text('')
        event = {
            'type': 'error',
            'message': 'Reconnecting... 2/5 (unexpected status 403 Forbidden: Unknown error)',
        }
        (folder / 'stdout.log').write_text(json.dumps(event) + '\n')
        before = providers.throttled()
        providers.note_throttling(folder)
        self.assertEqual(providers.throttled(), before + 1)
        (folder / 'stdout.log').write_text('{"type":"turn.completed"}\n')
        providers.note_throttling(folder)
        self.assertEqual(providers.throttled(), before + 1)

    # atlas.find

    def test_thin_selects_records_with_at_most_one_source_and_skips_done_ones(self):
        data = core.load(self.core)
        self.assertEqual(finding.thin(data), ['NRL-02', 'NRL-03', 'NRL-04'])
        done = self.root / 'find' / 'NRL-03-20261112T000000Z'
        done.mkdir(parents=True)
        (done / 'reports.json').write_text('[]')
        (self.root / 'find' / 'NRL-04-20261112T000000Z').mkdir()  # interrupted: no reports
        called = []

        def stub(identifier, *args, **kwargs):
            called.append(identifier)
            return None, []

        out = io.StringIO()
        with patch('atlas.find.find', side_effect=stub), redirect_stdout(out):
            code = finding.main(
                ['--thin', '--no-commit', '--workers', '2'], core=self.core, path=self.db
            )
        self.assertEqual(code, 0)
        self.assertEqual(sorted(called), ['NRL-02', 'NRL-04'])
        self.assertIn('NRL-03: skipped, already has a finder call record', out.getvalue())
        self.assertIn('Done: 2 breakthroughs, 1 skipped, 0 failed', out.getvalue())
        called.clear()
        with patch('atlas.find.find', side_effect=stub), redirect_stdout(io.StringIO()):
            finding.main(['--thin', '--force', '--no-commit'], core=self.core, path=self.db)
        self.assertEqual(called, ['NRL-02', 'NRL-03', 'NRL-04'])

    def test_parallel_finds_write_through_the_lock_and_rebuild_once_per_breakthrough(self):
        added = self.root / 'added' / 'sources'
        added.mkdir(parents=True)
        digests = {}
        for identifier in ('NRL-03', 'NRL-04'):
            text = TEXT + identifier
            digests[identifier] = sha(text.encode())
            (added / (digests[identifier] + '.html')).write_text(text)

        def search(identifier):
            return lambda prompt: {
                'sources': [
                    {
                        'url': f'https://arxiv.org/abs/{identifier}-{n}',
                        'title': 'Paper',
                        'who': 'A',
                        'year': 2026,
                        'bears_on': 1,
                        'finding': 'A result.',
                    }
                    for n in (1, 2)
                ]
            }

        judge = lambda prompt: {'source_date': None, 'rows': []}
        writer = batch.Writer(25, False, str, self.core)
        rebuilds = []
        real = rebuild

        def counted(core=None, path=None):
            rebuilds.append(threading.get_ident())
            return real(self.core, self.db, roots=[self.root / 'runs', self.root / 'added'])

        def work(identifier, stop):
            saver = lambda url: (
                digests[identifier],
                str(added / (digests[identifier] + '.html')),
                TEXT + identifier,
            )
            return finding.find(
                identifier,
                search=search(identifier),
                judge=judge,
                saver=saver,
                path=self.db,
                core=self.core,
                writer=writer,
                stop=stop,
            )

        with patch('atlas.store.rebuild', side_effect=counted):
            outcomes, _ = batch.run(['NRL-03', 'NRL-04'], work, 2)
        self.assertEqual([status for status, _ in outcomes.values()], ['done', 'done'])
        self.assertEqual(len(rebuilds), 2)
        self.assertEqual(sorted(writer.done), ['NRL-03', 'NRL-04'])
        sources = core.load(self.core)['sources']
        self.assertEqual(
            sorted(url for url in sources if 'arxiv' in url),
            [f'https://arxiv.org/abs/{i}-{n}' for i in ('NRL-03', 'NRL-04') for n in (1, 2)],
        )

    # atlas.brief

    def test_brief_missing_all_workers_and_one_rebuild(self):
        def factory(identifier):
            folder = self.root / 'brief' / identifier
            folder.mkdir(parents=True)
            urls = [url for url in self.sources[identifier]]
            return folder, lambda prompt: reply(identifier, urls)

        rebuilds = []
        with (
            patch('atlas.brief._call', side_effect=factory),
            patch('atlas.store.rebuild', side_effect=lambda **kwargs: rebuilds.append(1)),
            redirect_stdout(io.StringIO()) as out,
        ):
            code = briefs.main(['--all', '--workers', '3', '--no-commit'], self.core, self.db)
        self.assertEqual(code, 0, out.getvalue())
        self.assertEqual(len(rebuilds), 1)
        data = core.load(self.core)
        for identifier in self.sources:
            self.assertEqual(
                data['breakthroughs'][identifier]['brief']['prompt'], briefs.PROMPT_HASH
            )
        self.assertEqual(briefs.wanted(data, missing=True), [])
        self.assertEqual(core.check(data), [])
        # A brief from another prompt counts as missing; one with no brief too.
        item = data['breakthroughs']['NRL-02']
        item['brief']['prompt'] = 'older'
        core.write_breakthrough(item, self.core)
        item = data['breakthroughs']['NRL-03']
        del item['brief']
        core.write_breakthrough(item, self.core)
        self.assertEqual(briefs.wanted(core.load(self.core), missing=True), ['NRL-02', 'NRL-03'])

    def test_brief_failure_continues_and_exhaustion_stops(self):
        def factory(identifier):
            folder = self.root / 'brief' / identifier
            folder.mkdir(parents=True)

            def call(prompt):
                if identifier == 'NRL-01':
                    return {'title': 'broken'}
                if identifier == 'NRL-03':
                    raise ProviderExhausted('codex', 'Codex usage exhausted')
                return reply(identifier, self.sources[identifier])

            return folder, call

        with (
            patch('atlas.brief._call', side_effect=factory),
            patch('atlas.store.rebuild'),
            redirect_stdout(io.StringIO()) as out,
        ):
            code = briefs.main(['--all', '--workers', '1', '--no-commit'], self.core, self.db)
        self.assertEqual(code, 1)
        text = out.getvalue()
        self.assertIn('NRL-01: failed', text)
        self.assertIn('NRL-02: A plain title', text)
        self.assertIn('Stopped: a provider reported exhaustion', text)
        data = core.load(self.core)
        self.assertEqual(
            [
                identifier
                for identifier in self.sources
                if 'brief' in data['breakthroughs'][identifier]
            ],
            ['NRL-02'],
        )

    # atlas.copies

    def test_only_the_page_alternatives_and_pdfs_shown_to_be_the_work_are_read(self):
        folder = self.root / 'copies'
        folder.mkdir()

        def page(name, html):
            path = folder / name
            path.write_text(html)
            return str(path)

        title = 'Quantum error correction below the surface code threshold'
        nature = 'https://www.nature.com/articles/s41586-024-08449-y'
        meta = '<meta name="citation_pdf_url" content="https://www.nature.com/articles/s41586-024-08449-y.pdf">'
        body = 'x' * 1500
        cases = [
            # A blog page linking a different paper and a manual: only the page is read.
            (
                {
                    'url': 'https://www.example.com/research/post',
                    'title': 'A blog post about proofs',
                },
                [
                    Copy('p', page('p.html', '<p>post</p>'), 'post ' * 400, 'source', None),
                    Copy(
                        'o',
                        'o.pdf',
                        'Astree from research to industry ' * 200,
                        'paper_pdf',
                        'https://other.org/astree.pdf',
                    ),
                    Copy(
                        'm',
                        'm.pdf',
                        'Manual ' * 9000,
                        'paper_pdf',
                        'https://www.example.com/docs/manual.pdf',
                    ),
                ],
                'p',
            ),
            # A publisher page: the PDF named by citation_pdf_url is the work; supplements are not.
            (
                {'url': nature, 'title': title},
                [
                    Copy(
                        'n',
                        page('n.html', meta + 'short'),
                        'page ' * 300,
                        'source',
                        nature + '?error=cookies',
                    ),
                    Copy('pdf', 'pdf.pdf', body * 3, 'paper_pdf', nature + '.pdf?error=cookies'),
                    Copy(
                        's',
                        's.pdf',
                        title + body * 9,
                        'paper_pdf',
                        'https://static-content.springer.com/esm/MOESM1_ESM.pdf',
                    ),
                ],
                'pdf',
            ),
            # An arXiv abstract page and its PDF.
            (
                {
                    'url': 'https://arxiv.org/abs/2408.13687',
                    'title': 'https://arxiv.org/abs/2408.13687',
                },
                [
                    Copy('a', 'a.txt', 'abstract ' * 200, 'source', None),
                    Copy(
                        'ap', 'ap.pdf', body * 4, 'paper_pdf', 'https://arxiv.org/pdf/2408.13687v1'
                    ),
                ],
                'ap',
            ),
            # A PubMed cookie wall: the E-utilities abstract and PMC page are read.
            (
                {'url': 'https://pubmed.ncbi.nlm.nih.gov/1/', 'title': 'A trial'},
                [
                    Copy('w', 'w.txt', 'Cookies must be enabled', 'source', None),
                    Copy('e', 'e.xml', body, 'alternative', None),
                    Copy('c', 'c.html', body * 5, 'alternative', None),
                ],
                'c',
            ),
            # A linked PDF whose opening carries the source's title.
            (
                {'url': 'https://lab.example.edu/people/x', 'title': title},
                [
                    Copy('l', 'l.txt', 'Lab page', 'source', None),
                    Copy(
                        't',
                        't.pdf',
                        'Journal\n' + title.upper() + body,
                        'paper_pdf',
                        'https://cdn.example.net/t.pdf',
                    ),
                ],
                't',
            ),
        ]
        for source, found, expected in cases:
            chosen = copies.choose(source, found)
            self.assertEqual(chosen and chosen.sha256, expected, source['url'])
        self.assertIsNone(copies.choose(cases[3][0], cases[3][1][:1]))


if __name__ == '__main__':
    unittest.main()


class SharedLockTests(unittest.TestCase):
    def test_two_processes_take_turns_and_one_thread_may_reenter(self):
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'lock'
            lock = batch.SharedLock(path)
            with lock, lock:  # re-entrant in one thread
                child = subprocess.Popen(
                    [
                        sys.executable,
                        '-c',
                        'import sys, time; from atlas import batch; '
                        't = time.time(); lock = batch.SharedLock(sys.argv[1]); '
                        'lock.__enter__(); print(round(time.time() - t, 1))',
                        str(path),
                    ],
                    stdout=subprocess.PIPE,
                    text=True,
                )
                time.sleep(0.6)
            waited = float(child.communicate(timeout=10)[0])
            self.assertGreaterEqual(waited, 0.4)
