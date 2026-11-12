"""PubMed pages that capture as a cookie wall get the E-utilities abstract and the PMC page."""

import tempfile
import unittest
from pathlib import Path

from ingestion.sources import EFETCH, Archive, pmc_id, pubmed_id

URL = 'https://pubmed.ncbi.nlm.nih.gov/123/'
WALL = b'<html><body>Cookies must be enabled</body></html>'
ABSTRACT = 'We report that the treatment worked in most patients. ' * 30
XML = (
    '<PubmedArticleSet><PubmedArticle><Article><ArticleTitle>A trial</ArticleTitle>'
    f'<Abstract><AbstractText>{ABSTRACT}</AbstractText></Abstract></Article>'
    '<ArticleIdList><ArticleId IdType="pubmed">123</ArticleId>'
    '<ArticleId IdType="pmc">PMC456</ArticleId></ArticleIdList></PubmedArticle></PubmedArticleSet>'
).encode()
PMC = ('<html><body>Full text. ' + 'Results: it worked. ' * 200 + '</body></html>').encode()


class PubMedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.requests = []
        self.waits = []

    def tearDown(self):
        self.tmp.cleanup()

    def get(self, url):
        self.requests.append(url)
        if url == URL:
            return WALL, 'text/html', url
        if url == EFETCH.format('123'):
            return XML, 'text/xml', url
        if url == 'https://pmc.ncbi.nlm.nih.gov/articles/PMC456/':
            return PMC, 'text/html', url
        raise AssertionError(url)

    def test_ids(self):
        self.assertEqual(pubmed_id(URL), '123')
        self.assertEqual(pubmed_id('https://pubmed.ncbi.nlm.nih.gov/123'), '123')
        self.assertEqual(pubmed_id('https://pubmed.ncbi.nlm.nih.gov/123/?dopt=Abstract'), '123')
        self.assertIsNone(pubmed_id('https://pmc.ncbi.nlm.nih.gov/articles/PMC456/'))
        self.assertEqual(pmc_id(XML), 'PMC456')
        self.assertIsNone(pmc_id(b'<PubmedArticleSet/>'))
        self.assertIsNone(pmc_id(b'not xml'))

    def test_cookie_wall_gets_abstract_and_pmc_copies_as_alternatives(self):
        archive = Archive(self.root, self.get, self.waits.append)
        archive.capture(URL)
        page = archive.pubmed(URL)
        self.assertEqual(page, 'https://pmc.ncbi.nlm.nih.gov/articles/PMC456/')
        self.assertEqual(
            self.requests,
            [URL, EFETCH.format('123'), 'https://pmc.ncbi.nlm.nih.gov/articles/PMC456/'],
        )
        self.assertEqual(self.waits, [0.34, 0.34])
        kinds = [(a['kind'], a['format']) for a in archive.source(URL)['artifacts']]
        self.assertEqual(
            kinds, [('source', 'html'), ('alternative', 'xml'), ('alternative', 'html')]
        )
        texts = {a['kind'] + a['format']: a['text'] for a in archive.evidence(URL)}
        self.assertIn('the treatment worked', texts['alternativexml'])
        # A second call fetches nothing: the copies already have enough text.
        archive.pubmed(URL)
        self.assertEqual(len(self.requests), 3)

    def test_other_urls_and_readable_pages_are_left_alone(self):
        archive = Archive(self.root, lambda url: (PMC, 'text/html', url), self.waits.append)
        archive.capture(URL)
        self.assertIsNone(archive.pubmed(URL))
        self.assertIsNone(archive.pubmed('https://arxiv.org/abs/1'))
        self.assertEqual(self.waits, [])


if __name__ == '__main__':
    unittest.main()
