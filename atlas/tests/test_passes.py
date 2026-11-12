"""The source top-up (atlas.find) and the reader's version (atlas.brief), with stubbed calls."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from atlas import brief as briefs, core, find as finding
from atlas.copies import Copy
from atlas.store import breakthrough_data, connect, rebuild, resolver, sha

TEXT = (
    'Abstract. We report a working prototype that holds its state for ninety days in a '
    'controlled trial of twelve participants.'
)
TEXT += ' Methods follow.' * 80
SECTIONS = ['concept', 'significance', 'missing_breakthrough', 'current_state', 'related_concepts']


QUOTE = 'We report a working prototype that holds its state for ninety days'


def answer(urls, ids=('m1', 'm2'), quote=QUOTE):
    return {
        'title': 'A device that keeps working for months',
        'possible': ['People could use it every day.'],
        'why': ['Patients would not need repeat surgery.'],
        'sources': [
            {
                'url': url,
                'who': 'A group of engineers',
                'showed': 'A prototype held its state for ninety days.',
                'quote': quote,
                'cited_for': 'It is the longest result so far.',
                'not_established': 'It does not show use outside a trial.',
            }
            for url in urls
        ],
        'shown': ['One prototype has worked for ninety days.'],
        'missing': ['Years of use.', 'A larger trial.'],
        'milestones': [
            {'id': identifier, 'label': 'Works for a year', 'explanation': 'It must last.'}
            for identifier in ids
        ],
        'uncertain': ['Whether the result repeats.'],
    }


class PassTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.core = self.root / 'core'
        self.db = self.root / 'atlas.sqlite3'
        folder = self.root / 'runs' / 'NRL'
        (folder / 'sources').mkdir(parents=True)
        body = ('<html><body>' + TEXT + '</body></html>').encode()
        self.hash = sha(body)
        (folder / 'sources' / (self.hash + '.html')).write_bytes(body)
        saved = 'https://example.org/saved'
        unsaved = 'https://example.org/unsaved'
        item = {
            'id': 'NRL-17',
            'title': 'A durable interface',
            'change_log': [],
            'unresolved_issues': ['Durability is unproven.'],
            'provenance': {},
            'models': {'research': 'gpt-6.1-terra'},
            'sources': [
                {
                    'url': saved,
                    'title': 'Saved paper',
                    'status': 'saved',
                    'artifacts': [{'sha256': self.hash, 'format': 'html', 'kind': 'source'}],
                },
                {'url': unsaved, 'title': 'Unsaved paper', 'status': 'not_captured'},
            ],
            'completion_criteria': [
                {'text': 'First: hold state for a year.', 'source_urls': []},
                {'text': 'Second: restore sensation.', 'source_urls': []},
            ],
        }
        for section in SECTIONS:
            item[section] = [{'text': f'{section} text.', 'source_urls': [saved, unsaved]}]
        value = {
            'field': {'prefix': 'NRL', 'field': 'Neurology', 'boundaries': 'Neurology.'},
            'created_at': '2026-11-01T00:00:00+00:00',
            'innovations': [item],
        }
        (folder / 'final-innovations.json').write_text(json.dumps(value))
        core.import_field(folder, self.core)
        self.roots = [self.root / 'runs']
        patcher = patch('atlas.store.resolver', side_effect=lambda roots: resolver(self.roots))
        patcher.start()
        self.addCleanup(patcher.stop)
        rebuild(self.core, self.db)
        self.saved, self.unsaved = saved, unsaved
        self.path = self.core / 'NRL' / 'NRL-17.json'

    def tearDown(self):
        self.tmp.cleanup()

    # atlas.find

    def test_find_sends_each_url_through_add_and_skips_an_unsaveable_one(self):
        added = self.root / 'added' / 'sources'
        added.mkdir(parents=True)
        new = 'Results: the implant recorded signals for 400 days without loss of channels. ' * 20
        wall = 'pubmed.ncbi.nlm.nih.gov Cookies must be enabled'
        digest = sha(new.encode())
        (added / (digest + '.html')).write_text(new)
        self.roots.append(self.root / 'added')

        def saver(url):
            if url.endswith('/gone'):
                raise SystemExit('Could not save ' + url)
            if url.endswith('/wall'):
                return sha(wall.encode()), 'wall.html', wall
            return digest, str(added / (digest + '.html')), new

        prompts = []

        def search(text):
            prompts.append(text)
            return {
                'sources': [
                    {
                        'url': 'https://arxiv.org/abs/1',
                        'title': 'A 400-day implant',
                        'who': 'A. Author and colleagues',
                        'year': 2026,
                        'bears_on': 1,
                        'finding': 'Recorded for 400 days.',
                    },
                    {
                        'url': 'https://example.org/gone',
                        'title': 'Gone',
                        'who': 'B',
                        'year': 2025,
                        'bears_on': 0,
                        'finding': 'Nothing.',
                    },
                    {
                        'url': 'https://example.org/wall',
                        'title': 'Wall',
                        'who': 'D',
                        'year': 2023,
                        'bears_on': 1,
                        'finding': 'Behind a cookie wall.',
                    },
                    {
                        'url': self.saved,
                        'title': 'Saved paper',
                        'who': 'C',
                        'year': 2024,
                        'bears_on': 2,
                        'finding': 'Already cited.',
                    },
                ]
            }

        judge = lambda text: {
            'source_date': '2026',
            'rows': [
                {
                    'breakthrough': 'NRL-17',
                    'criterion': 1,
                    'verdict': 'advances',
                    'quote': 'the implant recorded signals for 400 days',
                },
                {
                    'breakthrough': 'NRL-17',
                    'criterion': 2,
                    'verdict': 'meets',
                    'quote': 'a sentence the paper never contains at all',
                },
                {
                    'breakthrough': 'NRL-18',
                    'criterion': 1,
                    'verdict': 'advances',
                    'quote': 'the implant recorded signals for 400 days',
                },
            ],
        }
        _, reports = finding.find(
            'NRL-17',
            limit=5,
            search=search,
            judge=judge,
            saver=saver,
            path=self.db,
            core=self.core,
        )
        self.assertIn('up to 5 further primary sources', prompts[0])
        self.assertIn('Milestone 2: Second: restore sensation.', prompts[0])
        self.assertIn('- Saved paper (https://example.org/saved)', prompts[0])
        first, gone, wall, cited = reports
        self.assertTrue(first['saved'])
        self.assertEqual([row['criterion'] for row in first['stored']], [1])
        self.assertEqual(
            [why for _, why in first['rejected']],
            ['quote not found in saved copy', 'other breakthrough, not stored'],
        )
        self.assertEqual((gone['saved'], gone['skipped']), (False, 'Could not save ' + gone['url']))
        self.assertEqual(
            wall['skipped'], 'Saved copy has 47 characters of text; not a readable paper'
        )
        self.assertEqual(cited['skipped'], 'already cited')
        data = core.load(self.core)
        # A new source gets the title the search returned, not its URL.
        self.assertEqual(data['sources']['https://arxiv.org/abs/1']['title'], 'A 400-day implant')
        self.assertNotIn('https://example.org/gone', data['sources'])
        self.assertNotIn('https://example.org/wall', data['sources'])
        self.assertEqual([row['url'] for row in data['progress']], ['https://arxiv.org/abs/1'])

    def test_find_with_urls_skips_the_search(self):
        text = 'Results: the device kept working for a year in every patient. ' * 20
        digest = sha(text.encode())
        searches = []
        _, reports = finding.find(
            'NRL-17',
            search=searches.append,
            judge=lambda prompt: {'source_date': None, 'rows': []},
            saver=lambda url: (digest, 'paper.html', text, 'alternative'),
            path=self.db,
            core=self.core,
            urls=['https://pubmed.ncbi.nlm.nih.gov/123/'],
        )
        self.assertEqual(searches, [])
        self.assertTrue(reports[0]['saved'])
        source = core.load(self.core)['sources']['https://pubmed.ncbi.nlm.nih.gov/123/']
        self.assertEqual(
            source['copies'], [{'sha256': digest, 'format': 'html', 'kind': 'alternative'}]
        )

    def test_save_prefers_the_fullest_copy_and_fetches_pubmed_text_for_a_cookie_wall(self):
        from ingestion.sources import EFETCH, Archive
        from atlas import add as adding

        url = 'https://pubmed.ncbi.nlm.nih.gov/123/'
        abstract = 'We report that the treatment worked in most patients. ' * 30
        xml = (
            '<PubmedArticleSet><PubmedArticle><AbstractText>'
            + abstract
            + '</AbstractText></PubmedArticle></PubmedArticleSet>'
        ).encode()
        pages = {
            url: (b'<html><body>Cookies must be enabled</body></html>', 'text/html', url),
            EFETCH.format('123'): (xml, 'text/xml', EFETCH.format('123')),
        }
        added = self.root / 'added'
        added.mkdir()
        archive = lambda root: Archive(root, lambda target: pages[target], lambda wait: None)
        with patch('atlas.add.ADDED', added), patch('atlas.add.Archive', archive):
            sha256, file, text, kind, _ = adding.save(url, self.db, self.core)
        self.assertEqual(kind, 'alternative')
        self.assertIn('the treatment worked', text)
        self.assertTrue(file.endswith('.xml'))
        # A recorded copy with enough text is used without capturing anything.
        with patch('atlas.add.Archive', side_effect=AssertionError('no capture')):
            chosen = adding.save(self.saved, self.db, self.core)
        self.assertEqual((chosen[0], chosen[3]), (self.hash, 'source'))

    def test_pubmed_lists_cookie_walls_and_records_fetched_copies(self):
        from ingestion.sources import EFETCH, Archive
        from atlas import pubmed

        url = 'https://pubmed.ncbi.nlm.nih.gov/77/'
        wall = b'<html><body>Cookies must be enabled</body></html>'
        added = self.root / 'added'
        (added / 'sources').mkdir(parents=True)
        (added / 'sources' / (sha(wall) + '.html')).write_bytes(wall)
        self.roots.append(added)
        data = core.load(self.core)
        data['sources'][url] = {
            'url': url,
            'title': 'A trial',
            'status': 'saved',
            'copies': [{'sha256': sha(wall), 'format': 'html', 'kind': 'source'}],
        }
        data['breakthroughs']['NRL-17']['sources'].append(url)
        core.write_breakthrough(data['breakthroughs']['NRL-17'], self.core)
        core.write_sources(data['sources'], self.core)
        rebuild(self.core, self.db)
        with connect(self.db) as db:
            self.assertEqual(pubmed.short(core.load(self.core), [url, self.saved], db), [url])
        self.assertEqual(pubmed.main(['--list'], core=self.core, path=self.db), 0)
        xml = (
            '<PubmedArticleSet><AbstractText>' + 'It worked. ' * 120 + '</AbstractText>'
            '</PubmedArticleSet>'
        ).encode()
        archive = Archive(added, lambda target: (xml, 'text/xml', target), lambda wait: None)
        with patch('atlas.add.ADDED', added):
            result = pubmed.recapture([url], self.core, self.db, archive)
        self.assertGreater(result[url], 1000)
        copies = core.load(self.core)['sources'][url]['copies']
        self.assertEqual([copy['kind'] for copy in copies], ['source', 'alternative'])
        self.assertIn(EFETCH.format('77'), json.dumps(archive.state))
        with connect(self.db) as db:
            self.assertEqual(pubmed.short(core.load(self.core), [url], db), [])

    # atlas.brief

    def test_brief_accepts_a_good_answer_and_changes_no_other_byte(self):
        before = self.path.read_text(encoding='utf-8')
        prompts = []

        def call(text):
            prompts.append(text)
            return answer([self.saved, self.unsaved])

        result, attempts = briefs.brief('NRL-17', call=call, core=self.core, path=self.db)
        self.assertEqual(attempts, 1)
        self.assertIn('Saved text (opening):\n<<<\n' + TEXT, prompts[0])
        self.assertIn('saved copy: no\n', prompts[0])
        self.assertIn('m1 (', prompts[0])
        after = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(after['models']['brief'], 'gpt-6.1-sol')
        self.assertEqual(
            [(source['checked'], source['quote']) for source in after['brief']['sources']],
            [(True, QUOTE), (False, None)],
        )
        stripped = copy.deepcopy(after)
        del stripped['brief'], stripped['models']['brief']
        self.assertEqual(json.dumps(stripped, indent=1, ensure_ascii=False) + '\n', before)
        self.assertEqual(result, after['brief'])
        self.assertEqual(core.check(core.load(self.core)), [])

    def test_brief_rejects_bad_answers_and_retries_once_with_the_problem(self):
        both = [self.saved, self.unsaved]
        good = answer(both)
        long_label = dict(
            good['milestones'][0],
            label='one two three four five six seven eight nine ten eleven twelve',
        )
        cases = {
            'milestones must be exactly m1, m2': answer(both, ids=('m2', 'm1')),
            'is not one of the given URLs': answer(both + ['https://elsewhere.org']),
            'appears twice': answer([self.saved, self.saved, self.unsaved]),
            'missing: \\[.https://example.org/saved.\\]': answer([self.unsaved]),
            'must be in the order given': answer([self.unsaved, self.saved]),
            'title is 67 characters; the limit is 60': dict(good, title='x' * 67),
            'possible entry 1 is 441 characters; the limit is 400': dict(
                good, possible=['x' * 441]
            ),
            'missing entry 1 is 177 characters; the limit is 160': dict(
                good, missing=['x' * 177, 'y']
            ),
            'missing has 5 entries; it must have 2 to 4': dict(good, missing=['A gap.'] * 5),
            'why has 0 entries; it must have 1 to 2': dict(good, why=[]),
            'label has 12 words; the limit is 10': dict(
                good, milestones=[long_label, good['milestones'][1]]
            ),
            'who is 89 characters; the limit is 80': answer(both)
            | {'sources': [dict(good['sources'][0], who='w' * 89), good['sources'][1]]},
        }
        before = self.path.read_bytes()
        for problem, bad in cases.items():
            prompts = []

            def call(text):
                prompts.append(text)
                return bad

            with self.assertRaisesRegex(ValueError, problem):
                briefs.brief('NRL-17', call=call, core=self.core, path=self.db)
            self.assertEqual(len(prompts), 2)
            self.assertIn('Your previous answer was rejected:\n- ', prompts[1])
            self.assertRegex(prompts[1], problem)
            self.assertEqual(self.path.read_bytes(), before)
        # Every problem is stated in the one retry.
        prompts = []

        def two(text):
            prompts.append(text)
            return dict(good, title='x' * 67, possible=['y' * 441])

        with self.assertRaises(ValueError):
            briefs.brief('NRL-17', call=two, core=self.core, path=self.db)
        self.assertIn('- title is 67 characters', prompts[1])
        self.assertIn('- possible entry 1 is 441 characters', prompts[1])
        # Within 10% of a limit is accepted; a short quote is not a rejection, only unchecked.
        result, attempts = briefs.brief(
            'NRL-17',
            call=lambda text: dict(answer(both, quote='We report a working'), title='x' * 66),
            core=self.core,
            path=self.db,
        )
        self.assertEqual((attempts, result['sources'][0]['checked']), (1, False))
        replies = [cases['appears twice'], good]
        _, attempts = briefs.brief(
            'NRL-17', call=lambda text: replies.pop(0), core=self.core, path=self.db
        )
        self.assertEqual(attempts, 2)

    def test_an_unmatched_quote_becomes_null_and_unchecked(self):
        result, _ = briefs.brief(
            'NRL-17',
            call=lambda text: answer(
                [self.saved, self.unsaved],
                quote='a passage of forty characters that is not in the paper',
            ),
            core=self.core,
            path=self.db,
        )
        self.assertEqual(
            (result['sources'][0]['quote'], result['sources'][0]['checked']), (None, False)
        )

    def test_a_cookie_wall_copy_counts_as_no_saved_text(self):
        wall = 'pubmed.ncbi.nlm.nih.gov Cookies must be enabled'
        prompts = []

        def call(text):
            prompts.append(text)
            return answer([self.saved, self.unsaved], quote='Cookies must be enabled')

        cookie = [Copy(self.hash, 'wall.txt', wall, 'source', self.saved)]
        with patch('atlas.brief.known_copies', return_value=cookie):
            result, _ = briefs.brief('NRL-17', call=call, core=self.core, path=self.db)
        self.assertNotIn(wall, prompts[0])
        self.assertEqual(prompts[0].count('Saved text: none'), 2)
        self.assertEqual(
            (result['sources'][0]['quote'], result['sources'][0]['checked']), (None, False)
        )

    # atlas.core check and the site data

    def test_check_validates_a_brief(self):
        data = core.load(self.core)
        data['breakthroughs']['NRL-17']['brief'] = answer(
            [self.saved, 'https://unknown.org', self.saved], ids=('m1',)
        )
        self.assertEqual(
            core.check(data),
            [
                'Brief milestones do not match the record: NRL-17',
                'Duplicate brief source: NRL-17',
                'Unknown brief source: NRL-17: https://unknown.org',
            ],
        )

    def test_b_file_carries_the_brief_and_papers_with_only_judged_rows(self):
        with connect(self.db) as db:
            self.assertNotIn('brief', breakthrough_data(db, 'NRL-17'))
        data = core.load(self.core)
        data['sources']['https://arxiv.org/abs/9'] = {
            'url': 'https://arxiv.org/abs/9',
            'title': 'Judged paper',
            'status': 'saved',
            'copies': [],
        }
        core.write_sources(data['sources'], self.core)
        core.write_progress(
            [
                {
                    'breakthrough': 'NRL-17',
                    'milestone': None,
                    'url': 'https://arxiv.org/abs/9',
                    'copy': self.hash,
                    'source_date': None,
                    'verdict': 'advances',
                    'quote': 'quote',
                    'by': 'model',
                    'added_at': '2026-11-11',
                }
            ],
            self.core,
        )
        rebuild(self.core, self.db)
        briefs.brief(
            'NRL-17',
            call=lambda text: answer([self.saved, self.unsaved, 'https://arxiv.org/abs/9']),
            core=self.core,
            path=self.db,
        )
        rebuild(self.core, self.db)
        with connect(self.db) as db:
            item = breakthrough_data(db, 'NRL-17')
        self.assertEqual(
            item['sources'],
            [
                {'url': self.saved, 'title': 'Saved paper', 'status': 'saved'},
                {'url': self.unsaved, 'title': 'Unsaved paper', 'status': 'not_captured'},
                {'url': 'https://arxiv.org/abs/9', 'title': 'Judged paper', 'status': 'saved'},
            ],
        )
        self.assertEqual(
            [
                (source['url'], source['title'], source['status'], source['checked'])
                for source in item['brief']['sources']
            ],
            [
                (self.saved, 'Saved paper', 'saved', True),
                (self.unsaved, 'Unsaved paper', 'not_captured', False),
                ('https://arxiv.org/abs/9', 'Judged paper', 'saved', False),
            ],
        )
        self.assertEqual(item['brief']['title'], 'A device that keeps working for months')
        self.assertNotIn(self.hash, json.dumps(item))


if __name__ == '__main__':
    unittest.main()
