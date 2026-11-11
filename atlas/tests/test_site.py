"""The site's data contract and the static export."""

import json
import re
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

from atlas import core
from atlas.export import export
from atlas.server import Handler
from atlas.store import (
    CORE,
    REGION,
    REGIONS,
    breakthrough_data,
    catalog,
    claims,
    connect,
    cut,
    encode,
    field_data,
    rebuild,
    region,
    search_index,
    sha,
    site_files,
)

BUDGET = 300_000
SECTIONS = [
    'concept',
    'significance',
    'missing_breakthrough',
    'current_state',
    'completion_criteria',
    'related_concepts',
]
INDEX = (
    '<!doctype html>\n<html lang="en">\n  <head>\n    <meta charset="utf-8" />\n'
    '    <meta\n      name="description"\n      content="Default."\n    />\n'
    '    <title>Technology Atlas</title>\n'
    '    <script type="module" crossorigin src="/assets/index.js"></script>\n'
    '  </head>\n  <body><div id="root"></div></body>\n</html>\n'
)


def record(identifier, title, url):
    item = {
        'id': identifier,
        'title': title,
        'change_log': [],
        'unresolved_issues': ['Partial evidence'],
        'provenance': {},
        'sources': [{'url': url, 'title': 'Paper', 'status': 'saved', 'artifacts': []}],
    }
    for section in SECTIONS:
        item[section] = [
            {'text': f'Milestone text for {identifier}: ' + 'word ' * 60, 'source_urls': [url]}
        ]
    return item


class SiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.core = self.root / 'core'
        self.db = self.root / 'atlas.sqlite3'
        body = b'saved copy'
        self.hash = sha(body)
        for prefix, name in [('QUA', 'Quantum Computing'), ('ZZZ', 'Unmapped Field')]:
            folder = self.root / 'runs' / prefix
            (folder / 'sources').mkdir(parents=True)
            (folder / 'sources' / (self.hash + '.html')).write_bytes(body)
            value = {
                'field': {'prefix': prefix, 'field': name, 'boundaries': name + ' scope.'},
                'created_at': '2026-11-01T00:00:00+00:00',
                'innovations': [
                    record(f'{prefix}-01', f'{name} first <&> "one"', 'https://example.org/a'),
                    record(f'{prefix}-02', f'{name} second', 'https://example.org/b'),
                ],
            }
            (folder / 'final-innovations.json').write_text(json.dumps(value))
            core.import_field(folder, self.core)
        data = core.load(self.core)
        item = data['breakthroughs']['QUA-02']
        item['prerequisites'] = [
            {'id': 'QUA-01', 'reason': 'Needs the first.', 'model': 'm', 'field': 'QUA'}
        ]
        core.write_breakthrough(item, self.core)
        path = self.core / 'QUA' / 'field.json'
        field = json.loads(path.read_text())
        field['withheld'] = [
            {'id': 'QUA-03', 'title': 'Refused', 'stage': 'review-QUA-03', 'reason': 'Refusal.'}
        ]
        path.write_text(json.dumps(field))
        core.write_progress(
            [
                {
                    'breakthrough': 'QUA-01',
                    'milestone': 'm1',
                    'url': 'https://example.org/a',
                    'copy': self.hash,
                    'source_date': '2026-10-01',
                    'verdict': 'advances',
                    'quote': 'quote',
                    'by': 'model',
                    'added_at': '2026-11-02',
                }
            ],
            self.core,
        )
        rebuild(self.core, self.db, roots=[self.root / 'runs'])
        self.site = self.root / 'site'
        (self.site / 'assets').mkdir(parents=True)
        (self.site / 'index.html').write_text(INDEX)
        (self.site / 'assets' / 'index.js').write_text('run()')

    def tearDown(self):
        self.tmp.cleanup()

    def test_catalog_is_compact(self):
        with connect(self.db) as db:
            data = catalog(db)
        self.assertEqual(
            list(data), ['as_of', 'regions', 'fields', 'breakthroughs', 'recent', 'withheld']
        )
        self.assertEqual(data['withheld'], [{'id': 'QUA-03', 'title': 'Refused', 'field': 'QUA'}])
        self.assertEqual(data['regions'], list(REGIONS))
        fields = {field['id']: field for field in data['fields']}
        self.assertEqual(
            fields['QUA'],
            {
                'id': 'QUA',
                'name': 'Quantum Computing',
                'region': 'Computing and Information',
                'breakthroughs': 2,
                'milestones': {'none': 1, 'in_progress': 1, 'met': 0},
            },
        )
        self.assertEqual(fields['ZZZ']['region'], region('ZZZ'))
        first = data['breakthroughs'][0]
        self.assertEqual(
            first,
            {
                'id': 'QUA-01',
                'field': 'QUA',
                'title': 'Quantum Computing first <&> "one"',
                'milestones': ['in_progress'],
                'prerequisites': [],
                'moved_at': '2026-11-02',
            },
        )
        self.assertEqual(data['breakthroughs'][1]['prerequisites'], ['QUA-01'])
        self.assertNotIn('search_text', encode(data).decode())
        self.assertEqual(data['recent'][0]['label'], 'Milestone text for QUA-01')

    def test_field_breakthrough_and_search_files(self):
        with connect(self.db) as db:
            field = field_data(db, 'QUA')
            item = breakthrough_data(db, 'QUA-02')
            first = breakthrough_data(db, 'QUA-01')
            index = search_index(db)
            self.assertIsNone(field_data(db, 'NOPE'))
            self.assertIsNone(breakthrough_data(db, 'QUA-99'))
        self.assertEqual(field['boundaries'], 'Quantum Computing scope.')
        self.assertEqual(
            field['withheld'],
            [{'id': 'QUA-03', 'title': 'Refused', 'stage': 'review-QUA-03', 'reason': 'Refusal.'}],
        )
        with connect(self.db) as db:
            self.assertEqual(field_data(db, 'ZZZ')['withheld'], [])
        self.assertEqual(field['breakthroughs'][0]['milestones'][0]['status'], 'in_progress')
        self.assertEqual(field['breakthroughs'][0]['unlocks'], ['QUA-02'])
        self.assertEqual(field['breakthroughs'][0]['source_count'], 1)
        self.assertTrue(field['breakthroughs'][0]['summary'].startswith('Milestone text'))
        self.assertEqual(
            item['needs'],
            [
                {
                    'id': 'QUA-01',
                    'title': 'Quantum Computing first <&> "one"',
                    'field': 'QUA',
                    'field_name': 'Quantum Computing',
                    'reason': 'Needs the first.',
                }
            ],
        )
        self.assertEqual(first['unlocks'][0]['id'], 'QUA-02')
        self.assertEqual(first['unlocks'][0]['reason'], 'Needs the first.')
        self.assertEqual(
            first['sources'],
            [{'url': 'https://example.org/a', 'title': 'Paper', 'status': 'saved'}],
        )
        text = encode(first).decode()
        for leak in ['provenance', self.hash, '/sources/', 'artifacts', str(self.root)]:
            self.assertNotIn(leak, text)
        judged = [row for row in first['progress'] if row['verdict']]
        self.assertEqual(judged[0]['quote'], 'quote')
        entry = index[0]
        self.assertEqual(list(entry), ['id', 'field', 'title', 'summary'])
        self.assertLessEqual(len(entry['summary']), 161)
        self.assertTrue(entry['summary'].endswith('…'))

    def test_cut_keeps_whole_words(self):
        self.assertEqual(cut('short text'), 'short text')
        self.assertEqual(cut('alpha beta gamma', 12), 'alpha beta…')

    def test_claims_lists_every_needs_link_with_its_reason(self):
        with connect(self.db) as db:
            data = claims(db)
            links = sum(len(item['prerequisites']) for item in catalog(db)['breakthroughs'])
        self.assertEqual(
            data, [{'id': 'QUA-02', 'needs': 'QUA-01', 'reason': 'Needs the first.', 'model': 'm'}]
        )
        self.assertEqual(len(data), links)

    def test_server_serves_the_data_files(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.db_path = self.db
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            for path in [
                '/data/catalog.json',
                '/data/search.json',
                '/data/claims.json',
                '/data/field/QUA.json',
                '/data/b/QUA-01.json',
            ]:
                with urlopen(base + path) as res:
                    self.assertEqual(res.headers['Content-Type'], 'application/json; charset=utf-8')
                    json.load(res)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_export_writes_site_data_and_one_page_per_route(self):
        out = self.root / 'out'
        result = export(out, self.db, self.site, base_url='https://atlas.example/')
        self.assertEqual(result['data'], 3 + 2 + 4)
        self.assertEqual((out / 'assets/index.js').read_text(), 'run()')
        with connect(self.db) as db:
            self.assertEqual(json.loads((out / 'data/catalog.json').read_text()), catalog(db))
        for name in [
            'search.json',
            'claims.json',
            'field/QUA.json',
            'field/ZZZ.json',
            'b/QUA-01.json',
        ]:
            self.assertTrue((out / 'data' / name).is_file(), name)
        routes = ['', 'atlas', 'claims', 'about', 'field/QUA', 'field/ZZZ', 'b/QUA-01', 'b/ZZZ-02']
        for route in routes:
            page = (out / route / 'index.html').read_text()
            self.assertEqual(page.count('<title>'), 1)
            self.assertEqual(page.count('name="description"'), 1)
            self.assertIn('src="/assets/index.js"', page)
            self.assertIn('property="og:image"', page)
        page = (out / 'b/QUA-01/index.html').read_text()
        self.assertIn(
            '<title>Quantum Computing first &lt;&amp;&gt; &quot;one&quot; · QUA-01 · '
            'Technology Atlas</title>',
            page,
        )
        self.assertIn('content="https://atlas.example/share/QUA-01.png"', page)
        self.assertIn('content="https://atlas.example/b/QUA-01"', page)
        self.assertIn(
            'content="https://atlas.example/share/default.png"', (out / 'index.html').read_text()
        )
        self.assertIn(
            'content="https://atlas.example/share/field-QUA.png"',
            (out / 'field/QUA/index.html').read_text(),
        )
        # The share cards are drawn for atlas.share to screenshot; they are not pages.
        self.assertFalse((out / 'share').exists())
        self.assertEqual(result['images'], 0)
        self.assertEqual(len(result['without_image']), result['pages'])
        description = re.search(r'name="description" content="([^"]*)"', page).group(1)
        self.assertTrue(description.startswith('Milestone text for QUA-01'))
        self.assertTrue((out / '404.html').is_file())
        exported = [path.name for path in out.rglob('*')]
        self.assertNotIn(self.hash + '.html', exported)
        self.assertNotIn('atlas.sqlite3', exported)

    def test_export_copies_share_images_and_reports_pages_without_one(self):
        cards = self.root / 'cards'
        (cards / 'share').mkdir(parents=True)
        for name in ['default', 'field-QUA', 'QUA-01']:
            (cards / 'share' / f'{name}.png').write_bytes(b'png ' + name.encode())
        (cards / 'share' / 'notes.txt').write_text('not an image')
        out = self.root / 'out'
        result = export(out, self.db, self.site, share=cards)
        self.assertEqual(result['images'], 3)
        self.assertEqual((out / 'share/QUA-01.png').read_bytes(), b'png QUA-01')
        self.assertFalse((out / 'share/notes.txt').exists())
        self.assertEqual(
            result['without_image'], ['/field/ZZZ', '/b/QUA-02', '/b/ZZZ-01', '/b/ZZZ-02']
        )
        self.assertEqual([p.name for p in (out / 'share').iterdir() if p.is_dir()], [])
        with self.assertRaises(SystemExit):
            export(self.root / 'again', self.db, self.site, share=self.root / 'nowhere')
        self.assertFalse((self.root / 'again').exists())

    def test_share_cards_cover_every_page_image(self):
        from atlas.export import routes
        from atlas.share import cards

        with connect(self.db) as db:
            files = dict(site_files(db))
        names = {name for _, name in cards(files['catalog.json'])}
        self.assertEqual({f'{image}.png' for *_, image in routes(files)}, names)
        self.assertEqual(
            cards(files['catalog.json'], ['default', 'QUA', 'QUA-01']),
            [
                ('/share/default', 'default.png'),
                ('/share/field/QUA', 'field-QUA.png'),
                ('/share/b/QUA-01', 'QUA-01.png'),
            ],
        )
        with self.assertRaises(SystemExit):
            cards(files['catalog.json'], ['NOPE-01'])

    def test_export_replaces_its_own_output_only(self):
        out = self.root / 'out'
        export(out, self.db, self.site)
        (out / 'stale.txt').write_text('old')
        export(out, self.db, self.site)
        self.assertFalse((out / 'stale.txt').exists())
        self.assertIn('content="/share/default.png"', (out / 'atlas/index.html').read_text())
        other = self.root / 'other'
        other.mkdir()
        (other / 'keep.txt').write_text('mine')
        with self.assertRaises(SystemExit):
            export(other, self.db, self.site)
        self.assertEqual((other / 'keep.txt').read_text(), 'mine')


class RealCoreTests(unittest.TestCase):
    def test_every_core_field_has_a_named_region(self):
        fields = sorted(path.parent.name for path in CORE.glob('*/field.json'))
        if not fields:
            self.skipTest('atlas/core not present')
        self.assertEqual([field for field in fields if field not in REGION], [])
        counts = [len(members) for members in REGIONS.values()]
        self.assertEqual(sum(counts), len(REGION))

    def test_catalog_of_the_real_core_is_within_budget(self):
        if not (CORE / 'sources.jsonl').exists():
            self.skipTest('atlas/core not present')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'atlas.sqlite3'
            rebuild(CORE, path, roots=[])
            with connect(path) as db:
                size = len(encode(catalog(db)))
                self.assertGreater(len(catalog(db)['breakthroughs']), 700)
        self.assertLess(size, BUDGET)


if __name__ == '__main__':
    unittest.main()
