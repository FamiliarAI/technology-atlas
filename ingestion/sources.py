"""Retain original artifacts and retry failed operations without losing successes."""
import hashlib
import http.client
import io
import json
import logging
import re
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

MAX_BYTES = 40 * 1024 * 1024
UA = 'AtlasIngestion/1.0 (private research source capture)'


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


def invalidate_summaries(root):
    for path in Path(root).glob('summary*.json'):
        history = Path(root) / 'history'
        history.mkdir(exist_ok=True)
        path.rename(history / f'{path.stem}-{uuid.uuid4().hex}.json')


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
        netloc = p.hostname.encode('idna').decode('ascii') + (f':{port}' if port is not None else '')
    # Preserve existing percent escapes and URL delimiters; encode literal spaces/Unicode.
    safe = "/%:@!$&'()*+,;="
    return urllib.parse.urlunsplit((p.scheme, netloc,
        urllib.parse.quote(p.path, safe=safe),
        urllib.parse.quote(p.query, safe=safe+'?[]'),
        urllib.parse.quote(p.fragment, safe=safe+'?[]')))


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
        if tag in ('link', 'a') and a.get('href') and (a.get('type', '').lower() == 'application/pdf' or urllib.parse.urlparse(a['href']).path.lower().endswith('.pdf')):
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
            issues = [] if all(value.strip() for value in pages) and pages else ['Some PDF pages have no extractable text; inspect original']
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
        parser = HTML(); parser.feed(decoded)
        text = '\n'.join(parser.text)
        if re.search(r'verify you are human|checking your browser|just a moment|access denied|captcha|enable javascript and cookies|checking your browser before accessing', text[:3000], re.I):
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
        invalidate_summaries(self.root)
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
        artifact = {'sha256': sha, 'path': str(path.relative_to(self.root)),
                    'format': ext, 'kind': kind, 'resolved_url': resolved,
                    'retrieved_at': now(), 'extraction_issues': issues}
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
                op.update(status='saved', artifact=sha, pdf_urls=[urllib.parse.urljoin(resolved, u) for u in pdfs], next_action=None)
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
                                delay = max(0, (parsedate_to_datetime(wait) - datetime.now(timezone.utc)).total_seconds())
                            except (ValueError, TypeError):
                                delay = 5
                message = str(error)
                op['attempts'].append({'at': now(), 'result': 'failed', 'error': message})
                op.update(status='failed', next_action=(f'Retry this operation after {delay:g} seconds' if transient else
                          'Inspect source; supply a legitimate alternative URL or manual copy'))
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

    def attach(self, url, file):
        file = Path(file)
        if file.stat().st_size > MAX_BYTES:
            raise ValueError('Manual copy exceeds 40 MiB')
        types = {'.pdf': 'application/pdf', '.html': 'text/html', '.htm': 'text/html', '.xml': 'application/xml', '.txt': 'text/plain'}
        sha, _ = self.retain(url, file.read_bytes(), types.get(file.suffix.lower(), ''), url, 'manual')
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
            ctype = {'pdf': 'application/pdf', 'html': 'text/html', 'xml': 'application/xml', 'txt': 'text/plain'}[a['format']]
            _, text, issues, _ = extract(body, ctype)
            if not body:
                issues = list(issues) + ['Retained artifact is empty (0 bytes); no source content is available']
            item = {**a, 'text': text[:120000], 'truncated': len(text) > 120000, 'extraction_issues': issues}
            if not body:
                item.update(byte_count=0, empty=True)
            items.append(item)
        return items
