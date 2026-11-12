"""Which saved copy of a source to read.

A source can have several saved copies: the page itself, deliberate alternatives (an E-utilities
abstract, a PMC article, a hand-attached file) and PDFs linked from the page. The capture code
keeps every PDF a page links to (`citation_pdf_url` metadata, and any link whose type or path
says PDF), so a linked PDF may be a different work: a manual, a cited paper, a supplement.

Rule: the page itself (`source`), `alternative` and `manual` copies are trusted. A `paper_pdf`
copy is trusted only with positive evidence that it is the same work, and never when it is a
supplement:
- the page's own `citation_pdf_url` metadata names it; or
- it sits under the page's own path on the same host (nature.com/articles/X -> X.pdf,
  pmc.../articles/PMCn/ -> PMCn/pdf/..., biorxiv .../v1 -> v1.full.pdf), or it is the arXiv PDF
  of an arXiv abstract or HTML page; or
- the source's title (at least 20 letters and digits) appears near the start of its text.
Among trusted copies with at least MIN_TEXT characters, the one with the most text is read.
"""

import json
import re
import urllib.parse
from collections import namedtuple
from html.parser import HTMLParser
from pathlib import Path

from ingestion.sources import MIN_TEXT, extract

from .store import ROOT

ADDED = ROOT / 'atlas/data/added'
FORMATS = {'pdf': 'application/pdf', 'xml': 'application/xml', 'txt': 'text/plain'}
SUPPLEMENT = re.compile(r'moesm|supplement|/esm/|/suppl', re.I)
TITLE_MIN = 20
TITLE_SPAN = 5000

# link is the URL the copy was fetched from, when known.
Copy = namedtuple('Copy', 'sha256 path text kind link')


def copy_text(file):
    """Extracted text of a saved copy file; empty when it cannot be read."""
    body = Path(file).read_bytes()
    kind = FORMATS.get(Path(file).suffix.lstrip('.').lower(), 'text/html')
    if body.startswith(b'%PDF-'):
        kind = 'application/pdf'
    try:
        return extract(body, kind)[1]
    except ValueError:
        return ''


_links = {}


def archive_links(root=ADDED):
    """sha256 -> fetched URL for copies in the atlas/data/added archive."""
    path = Path(root) / 'captures.json'
    if not path.is_file():
        return {}
    stamp = (str(path), path.stat().st_mtime_ns)
    if stamp not in _links:
        state = json.loads(path.read_text())
        _links.clear()
        _links[stamp] = {
            artifact['sha256']: artifact.get('resolved_url')
            for source in state.values()
            for artifact in source.get('artifacts', [])
        }
    return _links[stamp]


def known_copies(source, db):
    """Each recorded copy of a source found on this computer, as a Copy."""
    found = []
    links = None
    for copy in source.get('copies', []):
        row = db.execute('SELECT path FROM assets WHERE id=?', (copy['sha256'],)).fetchone()
        if row is None or not Path(row['path']).is_file():
            continue
        link = copy.get('resolved_url')
        if link is None:
            links = archive_links() if links is None else links
            link = links.get(copy['sha256'])
        found.append(Copy(copy['sha256'], row['path'], copy_text(row['path']), copy['kind'], link))
    return found


class _Citation(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'meta' and (values.get('name') or '').lower() == 'citation_pdf_url':
            if values.get('content'):
                self.urls.append(values['content'])


def normal(url):
    """Host without www, and path without trailing slash; scheme and query ignored."""
    parts = urllib.parse.urlsplit(url.strip())
    host = (parts.hostname or '').removeprefix('www.')
    return host + parts.path.rstrip('/')


def citations(copies, url):
    """Normalised citation_pdf_url values declared by the saved HTML pages of a source."""
    found = set()
    for copy in copies:
        if copy.kind != 'source' or not copy.path.endswith('.html'):
            continue
        parser = _Citation()
        try:
            parser.feed(Path(copy.path).read_bytes().decode('utf-8', errors='replace'))
        except AssertionError:
            continue
        found |= {normal(urllib.parse.urljoin(copy.link or url, pdf)) for pdf in parser.urls}
    return found


def same_paper_link(url, link):
    """True when link is the PDF of the page at url by its address alone."""
    page, pdf = urllib.parse.urlsplit(url), urllib.parse.urlsplit(link)
    if (page.hostname or '').removeprefix('www.') != (pdf.hostname or '').removeprefix('www.'):
        return False
    arxiv = re.fullmatch(r'/(?:abs|html|pdf)/(.+?)(?:v\d+)?/?', page.path)
    if (page.hostname or '').endswith('arxiv.org') and arxiv:
        return re.fullmatch(r'/pdf/' + re.escape(arxiv.group(1)) + r'(v\d+)?(\.pdf)?', pdf.path)
    path = re.sub(r'\.html?$', '', page.path.rstrip('/'))
    return path.count('/') >= 2 and pdf.path.startswith((path + '/', path + '.'))


def squeeze(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())


def trust(copy, url, title, cited):
    """Why a copy can be read as the source, or None."""
    if copy.kind != 'paper_pdf':
        return copy.kind
    if SUPPLEMENT.search(copy.link or '') or 'supplementary' in copy.text[:300].lower():
        return None
    if copy.link and normal(copy.link) in cited:
        return 'citation metadata'
    if copy.link and same_paper_link(url, copy.link):
        return 'paper link of the page'
    name = squeeze(title or '')
    if title != url and len(name) >= TITLE_MIN and name[:80] in squeeze(copy.text[:TITLE_SPAN]):
        return 'title in opening'
    return None


def trusted(source, copies):
    """The copies that can be read as the source itself, each with its reason."""
    url = source.get('url', '')
    cited = citations(copies, url)
    out = []
    for copy in copies:
        reason = trust(copy, url, source.get('title') or '', cited)
        if reason:
            out.append((copy, reason))
    return out


def choose(source, copies, minimum=MIN_TEXT):
    """The trusted copy with the most text, among those with at least minimum characters."""
    readable = [copy for copy, _ in trusted(source, copies) if len(copy.text.strip()) >= minimum]
    return max(readable, key=lambda copy: len(copy.text.strip()), default=None)
