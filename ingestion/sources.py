"""Retain original artifacts and retry failed operations without losing successes."""

import hashlib
import http.client
import io
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

MAX_BYTES = 40 * 1024 * 1024
UA = 'AtlasIngestion/1.0 (private research source capture)'


# A PubMed page often reaches the capture code as a short "Cookies must be enabled" page. Its
# abstract comes from NCBI E-utilities instead, and the full text from PMC when it names one.
PUBMED = re.compile(r'^https?://pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/?(?:[?#].*)?$')
EFETCH = (
    'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={}'
    '&rettype=abstract&retmode=xml'
)
PMC_PAGE = 'https://pmc.ncbi.nlm.nih.gov/articles/{}/'
# Free full copies for sources whose own page cannot be read (Archive.open_access).
CLINICAL_TRIAL = re.compile(r'clinicaltrials\.gov/.*?(NCT\d{8})', re.I)
CT_API = 'https://clinicaltrials.gov/api/v2/studies/{}?format=json'
EPMC_SEARCH = (
    'https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={}&format=json'
    '&resultType=lite&pageSize=5'
)
EPMC_FULLTEXT = 'https://www.ebi.ac.uk/europepmc/webservices/rest/{}/fullTextXML'
DOI = re.compile(r'\b(10\.\d{4,9}/[^\s?#"<>]+)', re.I)


def _plain(text):
    return re.sub(r'[^a-z0-9]+', ' ', (text or '').lower()).strip()


def europe_pmc(url, title='', getter=None):
    """The PMC ID of the paper at url when Europe PMC holds its full text: looked up by the DOI
    in the URL, else by the title (at least 20 letters, matched exactly after folding case and
    punctuation, so another paper is never taken for it). None when not found."""
    getter = getter or fetch
    doi = DOI.search(urllib.parse.unquote(url))
    if doi:
        query = f'DOI:"{doi.group(1).rstrip(".")}"'
    elif len(_plain(title)) >= 20:
        query = f'TITLE:"{title.strip()}"'
    else:
        return None
    try:
        body, _, _ = getter(EPMC_SEARCH.format(urllib.parse.quote(query)))
        results = json.loads(body).get('resultList', {}).get('result', [])
    except (OSError, ValueError):
        return None
    for result in results:
        if not result.get('pmcid') or 'Y' not in (result.get('inPMC'), result.get('isOpenAccess')):
            continue
        if doi or _plain(result.get('title')) == _plain(title):
            return result['pmcid']
    return None


NCBI_INTERVAL_S = 0.34  # NCBI allows 3 requests a second without a key.
MIN_TEXT = 1000  # Shorter extracted text is a cookie wall or error page, not a paper.


def pubmed_id(url):
    match = PUBMED.match(url.strip())
    return match.group(1) if match else None


def pmc_id(body):
    """The PMC ID named in a PubMed efetch XML record, or None."""
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    for element in root.iter('ArticleId'):
        value = (element.text or '').strip()
        if element.get('IdType') == 'pmc' and re.fullmatch(r'PMC\d+', value):
            return value
    return None


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    tmp.replace(path)


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else default


def web_url(url):
    if re.search(r'[\x00-\x1f\x7f]', url):
        raise ValueError('Source URL contains control characters')
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password:
        raise ValueError('Expected an HTTP(S) source URL without credentials')
    return url


def request_url(url):
    """Encode transport characters without rewriting canonical provenance URLs."""
    p = urllib.parse.urlsplit(web_url(url))
    if re.search(r'\s', p.netloc):
        raise ValueError('Source URL hostname contains whitespace')
    port = p.port  # Validate malformed ports before urllib constructs a request.
    netloc = p.netloc
    if not netloc.isascii():
        netloc = p.hostname.encode('idna').decode('ascii') + (
            f':{port}' if port is not None else ''
        )
    # Preserve existing percent escapes and URL delimiters; encode literal spaces/Unicode.
    safe = "/%:@!$&'()*+,;="
    return urllib.parse.urlunsplit(
        (
            p.scheme,
            netloc,
            urllib.parse.quote(p.path, safe=safe),
            urllib.parse.quote(p.query, safe=safe + '?[]'),
            urllib.parse.quote(p.fragment, safe=safe + '?[]'),
        )
    )


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, request_url(newurl))


def fetch(url):
    req = urllib.request.Request(request_url(url), headers={'User-Agent': UA})
    with urllib.request.build_opener(Redirect).open(req, timeout=40) as response:
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError('Source exceeds 40 MiB; obtain a manual copy')
        return body, response.headers.get_content_type(), response.geturl()


class HTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.pdfs, self.skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style', 'noscript'):
            self.skip += 1
        if tag == 'meta' and a.get('name', '').lower() == 'citation_pdf_url' and a.get('content'):
            self.pdfs.append(a['content'])
        if (
            tag in ('link', 'a')
            and a.get('href')
            and (
                a.get('type', '').lower() == 'application/pdf'
                or urllib.parse.urlparse(a['href']).path.lower().endswith('.pdf')
            )
        ):
            self.pdfs.append(a['href'])

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.text.append(data.strip())


def extract(body, content_type):
    """Return format, text, issues, declared PDF links. Never certify completeness."""
    if body.startswith(b'%PDF-'):
        from pypdf import PdfReader

        class CaptureWarnings(logging.Handler):
            def __init__(self):
                super().__init__(logging.WARNING)
                self.messages = []

            def emit(self, record):
                message = record.getMessage()[:500]
                if message not in self.messages and len(self.messages) < 10:
                    self.messages.append(message)

        warnings = CaptureWarnings()
        logger = logging.getLogger('pypdf')
        logger.addHandler(warnings)
        try:
            reader = PdfReader(io.BytesIO(body))
            pages = [p.extract_text() or '' for p in reader.pages]
            text = '\n\n'.join(f'[Page {i}]\n{value}' for i, value in enumerate(pages, 1))
            # Decode UTF-16 pairs and replace lone surrogates emitted by PDF extraction.
            text = text.encode('utf-16-le', errors='surrogatepass').decode(
                'utf-16-le', errors='replace'
            )
            issues = (
                []
                if all(value.strip() for value in pages) and pages
                else ['Some PDF pages have no extractable text; inspect original']
            )
            issues.extend('PDF extraction warning: ' + message for message in warnings.messages)
            return 'pdf', text, issues, []
        except Exception as e:
            return 'pdf', '', [f'PDF extraction failed: {type(e).__name__}; inspect manually'], []
        finally:
            logger.removeHandler(warnings)
    if 'pdf' in content_type:
        raise ValueError('Response claims PDF but has no PDF header')
    decoded = body.decode('utf-8', errors='replace')
    if 'html' in content_type or re.search(r'<(?:!doctype html|html)\b', decoded[:500], re.I):
        parser = HTML()
        parser.feed(decoded)
        text = '\n'.join(parser.text)
        if re.search(
            (
                'verify you are human|checking your browser|just a moment|access '
                'denied|captcha|enable javascript and cookies|checking your browser before '
                'accessing'
            ),
            text[:3000],
            re.I,
        ):
            raise ValueError('Access challenge; seek a legitimate alternative or manual copy')
        return 'html', text, [] if text else ['No extractable text'], parser.pdfs
    if 'xml' in content_type:
        import xml.etree.ElementTree as ET

        try:
            text = ' '.join(ET.fromstring(body).itertext())
            return 'xml', text, [] if text.strip() else ['No extractable text'], []
        except ET.ParseError:
            return 'xml', '', ['XML extraction failed; inspect original'], []
    if content_type.startswith('text/plain'):
        return 'txt', decoded, [], []
    if 'json' in content_type:
        # A structured record (the ClinicalTrials.gov API) is kept and read as its text.
        return 'txt', decoded, [] if decoded.strip() else ['No extractable text'], []
    raise ValueError(f'Unsupported source format {content_type}; obtain a readable copy')


class Archive:
    def __init__(self, directory, getter=fetch, sleeper=time.sleep):
        self.root = Path(directory)
        self.path = self.root / 'captures.json'
        self.state = read_json(self.path, {})
        self.getter, self.sleep = getter, sleeper
        (self.root / 'sources').mkdir(exist_ok=True)

    def source(self, url):
        return self.state.setdefault(web_url(url), {'artifacts': [], 'operations': {}})

    def save(self):
        write_json(self.path, self.state)

    def retain(self, url, body, content_type, resolved, kind):
        if not body:
            raise ValueError('Source response is empty (0 bytes)')
        if kind == 'paper_pdf' and not body.startswith(b'%PDF-'):
            raise ValueError('Declared paper PDF returned a non-PDF response')
        ext, text, issues, pdfs = extract(body, content_type)
        sha = digest(body)
        path = self.root / 'sources' / f'{sha}.{ext}'
        if path.exists() and digest(path.read_bytes()) != sha:
            raise ValueError('Stored source hash mismatch')
        if not path.exists():
            path.write_bytes(body)
        artifact = {
            'sha256': sha,
            'path': str(path.relative_to(self.root)),
            'format': ext,
            'kind': kind,
            'resolved_url': resolved,
            'retrieved_at': now(),
            'extraction_issues': issues,
        }
        src = self.source(url)
        if not any(a['sha256'] == sha for a in src['artifacts']):
            src['artifacts'].append(artifact)
        return sha, pdfs

    def operation(self, source_url, target, kind='source', retry=False):
        src = self.source(source_url)
        key = f'{kind}:{target}'
        op = src['operations'].get(key)
        if op and (op['status'] == 'saved' or not retry):
            return op
        op = op or {'target': target, 'kind': kind, 'attempts': []}
        src['operations'][key] = op
        for attempt in range(2):
            try:
                web_url(target)
                body, ctype, resolved = self.getter(target)
                sha, pdfs = self.retain(source_url, body, ctype, resolved, kind)
                op.update(
                    status='saved',
                    artifact=sha,
                    pdf_urls=[urllib.parse.urljoin(resolved, u) for u in pdfs],
                    next_action=None,
                )
                op['attempts'].append({'at': now(), 'result': 'saved', 'artifact': sha})
                self.save()
                return op
            except (OSError, ValueError, TimeoutError, http.client.InvalidURL) as error:
                transient = isinstance(error, (TimeoutError, urllib.error.URLError))
                delay = 5
                if isinstance(error, urllib.error.HTTPError):
                    transient = error.code in (429, 500, 502, 503, 504)
                    wait = error.headers.get('Retry-After') if error.headers else None
                    if wait:
                        try:
                            delay = max(0, int(wait))
                        except ValueError:
                            try:
                                delay = max(
                                    0,
                                    (
                                        parsedate_to_datetime(wait) - datetime.now(timezone.utc)
                                    ).total_seconds(),
                                )
                            except (ValueError, TypeError):
                                delay = 5
                message = str(error)
                op['attempts'].append({'at': now(), 'result': 'failed', 'error': message})
                op.update(
                    status='failed',
                    next_action=(
                        f'Retry this operation after {delay:g} seconds'
                        if transient
                        else 'Inspect source; supply a legitimate alternative URL or manual copy'
                    ),
                )
                self.save()
                if not transient or attempt == 1 or delay > 60:
                    return op
                self.sleep(delay)
        return op

    def capture(self, url, retry=False):
        op = self.operation(url, url, retry=retry)
        for pdf in op.get('pdf_urls', []):
            self.operation(url, pdf, 'paper_pdf', retry=retry)
        return self.source(url)

    def alternative(self, url, alternative, retry=False):
        op = self.operation(url, alternative, 'alternative', retry=retry)
        for pdf in op.get('pdf_urls', []):
            self.operation(url, pdf, 'paper_pdf', retry=retry)

    def pubmed(self, url, retry=False):
        """For a PubMed URL whose captured text is short, retain the E-utilities abstract and,
        when it names one, the PMC article as alternative copies. Returns the PMC URL or None."""
        identifier = pubmed_id(url)
        if identifier is None:
            return None
        texts = [len(item['text'].strip()) for item in self.evidence(url)]
        if max(texts, default=0) >= MIN_TEXT:
            return None
        self.sleep(NCBI_INTERVAL_S)
        efetch = EFETCH.format(identifier)
        op = self.operation(url, efetch, 'alternative', retry=retry)
        if op.get('status') != 'saved':
            return None
        artifact = next(a for a in self.source(url)['artifacts'] if a['sha256'] == op['artifact'])
        pmc = pmc_id((self.root / artifact['path']).read_bytes())
        if pmc is None:
            return None
        self.sleep(NCBI_INTERVAL_S)
        page = PMC_PAGE.format(pmc)
        self.alternative(url, page, retry=retry)
        return page

    def open_access(self, url, title='', retry=False):
        """For a source whose saved text is short (a paywall, a cookie wall, a page built in the
        browser), keep a free full copy as an alternative: a ClinicalTrials.gov study's record
        from its public API, or a paper's full text from Europe PMC when it holds one (found by
        the DOI in the URL, else by exact title). Returns the alternative URL or None."""
        texts = [len(item['text'].strip()) for item in self.evidence(url)]
        if max(texts, default=0) >= MIN_TEXT:
            return None
        trial = CLINICAL_TRIAL.search(url)
        if trial:
            target = CT_API.format(trial.group(1))
        else:
            pmcid = europe_pmc(url, title, self.getter)
            if pmcid is None:
                return None
            target = EPMC_FULLTEXT.format(pmcid)
        self.alternative(url, target, retry=retry)
        return target

    def attach(self, url, file):
        file = Path(file)
        if file.stat().st_size > MAX_BYTES:
            raise ValueError('Manual copy exceeds 40 MiB')
        types = {
            '.pdf': 'application/pdf',
            '.html': 'text/html',
            '.htm': 'text/html',
            '.xml': 'application/xml',
            '.txt': 'text/plain',
        }
        sha, _ = self.retain(
            url, file.read_bytes(), types.get(file.suffix.lower(), ''), url, 'manual'
        )
        self.save()
        return sha

    def evidence(self, url):
        items = []
        for a in self.source(url)['artifacts']:
            path = (self.root / a['path']).resolve()
            if not path.is_relative_to((self.root / 'sources').resolve()):
                raise ValueError('Source path escapes archive')
            body = path.read_bytes()
            if digest(body) != a['sha256']:
                raise ValueError(f'Source hash mismatch: {a["path"]}')
            ctype = {
                'pdf': 'application/pdf',
                'html': 'text/html',
                'xml': 'application/xml',
                'txt': 'text/plain',
            }[a['format']]
            _, text, issues, _ = extract(body, ctype)
            if not body:
                issues = list(issues) + [
                    'Retained artifact is empty (0 bytes); no source content is available'
                ]
            item = {
                **a,
                'text': text[:120000],
                'truncated': len(text) > 120000,
                'extraction_issues': issues,
            }
            if not body:
                item.update(byte_count=0, empty=True)
            items.append(item)
        return items
