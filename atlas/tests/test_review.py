"""The owner's review: decisions on records, the duplicate search, and the public view."""

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from atlas import core, review, similar, store
from atlas.store import rebuild, resolver
from atlas.tests.test_batch import record

PAGE = json.loads(
    (Path(__file__).resolve().parents[1] / 'core' / 'SUR' / 'SUR-01.json').read_text()
)['page']

PAGE_TITLE = 'Drug-free operational tolerance after deceased-donor organ transplantation'


def page_for(identifier, title):
    page = copy.deepcopy(PAGE)
    page['id'] = identifier
    page['title'] = title
    return page


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.core = self.root / 'core'
        self.db = self.root / 'atlas.sqlite3'
        folder = self.root / 'runs' / 'NRL'
        folder.mkdir(parents=True)
        value = {
            'field': {'prefix': 'NRL', 'field': 'Neurology', 'boundaries': 'Neurology.'},
            'created_at': '2026-11-01T00:00:00+00:00',
            'innovations': [record(f'NRL-0{n}', []) for n in (1, 2, 3)],
        }
        (folder / 'final-innovations.json').write_text(json.dumps(value))
        core.import_field(folder, self.core)
        data = core.load(self.core)
        titles = {
            'NRL-01': 'Operational tolerance in deceased-donor organ transplantation',
            'NRL-02': PAGE_TITLE,
        }
        for identifier, title in titles.items():
            item = data['breakthroughs'][identifier]
            item['page'] = page_for(identifier, title)
            core.write_breakthrough(item, self.core)
        patcher = patch(
            'atlas.store.resolver', side_effect=lambda roots: resolver([self.root / 'runs'])
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_decisions_are_logged_checked_and_refused_when_incomplete(self):
        stored = review.decide('NRL-01', 'published', core=self.core)
        self.assertEqual(stored['state'], 'published')
        self.assertEqual(core.check(core.load(self.core)), [])
        refusals = [
            ('NRL-03', 'published', None, None, 'has no page'),
            ('NRL-01', 'hold', None, None, 'needs a note'),
            ('NRL-01', 'merge', None, 'NRL-09', 'needs --into'),
            ('NRL-01', 'merge', None, 'NRL-01', 'itself'),
            ('NRL-01', 'bogus', None, None, 'Unknown decision'),
        ]
        for identifier, state, note, into, text in refusals:
            with self.assertRaisesRegex(review.Refused, text):
                review.decide(identifier, state, note, into, core=self.core)
        review.decide('NRL-01', 'merge', 'same work', 'NRL-02', core=self.core)
        review.decide('NRL-01', None, core=self.core)
        stored = core.load(self.core)['breakthroughs']['NRL-01']['review']
        self.assertIsNone(stored['state'])
        self.assertEqual([row['state'] for row in stored['log']], ['published', 'merge', None])
        self.assertEqual(stored['log'][1]['into'], 'NRL-02')
        # A hand edit that breaks the rules is caught by the check.
        data = core.load(self.core)
        item = data['breakthroughs']['NRL-03']
        item['review'] = {'state': 'published', 'log': []}
        core.write_breakthrough(item, self.core)
        self.assertIn('Published without a page: NRL-03', core.check(core.load(self.core)))

    def test_publishing_lists_the_closest_published_pages_and_never_blocks(self):
        review.decide('NRL-01', 'published', core=self.core)
        index = similar.Index(core.load(self.core))
        nearest = index.nearest('NRL-02', 'published')
        self.assertEqual([row['id'] for row in nearest], ['NRL-01'])
        self.assertGreaterEqual(nearest[0]['score'], similar.LIKELY)
        out = io.StringIO()
        with patch('atlas.core.commit'), redirect_stdout(out):
            code = review.main(['publish', 'NRL-02'], core=self.core)
        self.assertEqual(code, 0)
        self.assertIn('likely duplicate', out.getvalue())
        self.assertIn('NRL-02: published', out.getvalue())
        rows = review.listing(core.load(self.core), 'published')
        self.assertEqual([row['id'] for row in rows], ['NRL-01', 'NRL-02'])

    def test_the_public_view_holds_only_published_breakthroughs(self):
        review.decide('NRL-02', 'published', core=self.core)
        review.decide('NRL-01', 'hold', 'check the regulator source', core=self.core)
        rebuild(self.core, self.db)
        db = store.connect(self.db)
        try:
            everything = dict(store.site_files(db))
            public = dict(store.site_files(db, public=True))
        finally:
            db.close()
        self.assertEqual(
            sorted(name for name in everything if name.startswith('b/')),
            ['b/NRL-01.json', 'b/NRL-02.json', 'b/NRL-03.json'],
        )
        self.assertEqual(
            sorted(name for name in public if name.startswith('b/')), ['b/NRL-02.json']
        )
        self.assertEqual([b['id'] for b in public['catalog.json']['breakthroughs']], ['NRL-02'])
        self.assertTrue(public['b/NRL-02.json']['published'])
        # Lists describe a published breakthrough by its page: title, definition, and marks
        # from its confirmed results.
        listed = public['field/NRL.json']['breakthroughs'][0]
        self.assertEqual(listed['title'], PAGE_TITLE)
        self.assertEqual(listed['summary'], PAGE['definition'])
        self.assertEqual(listed['milestones'], store.page_milestones(PAGE))
        self.assertFalse(everything['b/NRL-01.json']['published'])
        # The owner's notes never reach the site data.
        self.assertNotIn('regulator source', json.dumps(everything))


if __name__ == '__main__':
    unittest.main()


class AutomaticTests(ReviewTests):
    def test_the_stronger_duplicate_is_published_and_merges_follow_it(self):
        data = core.load(self.core)
        weaker = data['breakthroughs']['NRL-01']
        stronger = data['breakthroughs']['NRL-02']
        stronger['page']['results_run'] = '2026-11-14'
        for result in stronger['page']['results']:
            result['confirmed'] = True
        for result in weaker['page']['results']:
            result['confirmed'] = False
        core.write_breakthrough(stronger, self.core)
        core.write_breakthrough(weaker, self.core)
        review.decide('NRL-01', 'published', core=self.core)
        review.decide('NRL-03', 'merge', 'same work', 'NRL-01', core=self.core)
        out = review.automatic(core.load(self.core), core=self.core)
        self.assertEqual(out['published'], ['NRL-02'])
        self.assertEqual([(a, b) for a, b, _ in out['merged']], [('NRL-01', 'NRL-02')])
        self.assertEqual(out['repointed'], ['NRL-03'])
        items = core.load(self.core)['breakthroughs']
        self.assertEqual(items['NRL-01']['review']['into'], 'NRL-02')
        self.assertEqual(items['NRL-03']['review']['into'], 'NRL-02')
        self.assertIn('Automatic: duplicate of NRL-02', items['NRL-01']['review']['note'])
        self.assertEqual(core.check(core.load(self.core)), [])
        # A second run changes nothing; a claimed page waits.
        again = review.automatic(core.load(self.core), core=self.core)
        self.assertEqual(again, {'published': [], 'merged': [], 'repointed': []})

    def test_pages_kept_apart_are_never_merged(self):
        data = core.load(self.core)
        stronger = data['breakthroughs']['NRL-02']
        stronger['page']['results_run'] = '2026-11-14'
        core.write_breakthrough(stronger, self.core)
        review.decide('NRL-01', 'published', core=self.core)
        review.keep_apart(['NRL-01', 'NRL-02'], core=self.core)
        out = review.automatic(core.load(self.core), core=self.core)
        self.assertNotIn(('NRL-01', 'NRL-02'), [(a, b) for a, b, _ in out['merged']])
        self.assertNotIn(('NRL-02', 'NRL-01'), [(a, b) for a, b, _ in out['merged']])
        items = core.load(self.core)['breakthroughs']
        self.assertEqual(items['NRL-01']['distinct'], ['NRL-02'])
        self.assertEqual(core.check(core.load(self.core)), [])


class NewBreakthroughTests(ReviewTests):
    def test_a_breakthrough_is_added_with_the_next_id_and_passes_the_check(self):
        identifier = core.new_breakthrough(
            'NRL',
            'Synthetic consciousness test',
            'A note.',
            ['https://example.org/a'],
            core=self.core,
        )
        self.assertEqual(identifier, 'NRL-04')
        item = core.load(self.core)['breakthroughs']['NRL-04']
        self.assertEqual(item['concept'][0]['source_urls'], ['https://example.org/a'])
        self.assertIn('Sources given: https://example.org/a', item['concept'][0]['text'])
        self.assertEqual(core.check(core.load(self.core)), [])
        with self.assertRaisesRegex(ValueError, 'already has this title'):
            core.new_breakthrough('NRL', 'synthetic  consciousness test', core=self.core)
        with self.assertRaisesRegex(ValueError, 'No field'):
            core.new_breakthrough('XYZ', 'Anything', core=self.core)
