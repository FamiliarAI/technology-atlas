"""Loopback-only server. Saved research copies are local downloads, never public hosting."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import core as records
from .review import Refused, decide, listing, review_message
from .similar import LIKELY, Index
from .store import (
    DB,
    ROOT,
    breakthrough_data,
    catalog,
    connect,
    encode,
    field_data,
    search_index,
    sha,
)

SITE = ROOT / 'atlas/static/site'  # built React site (atlas/web)
TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.woff2': 'font/woff2',
    '.woff': 'font/woff',
    '.svg': 'image/svg+xml',
    '.webp': 'image/webp',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.ico': 'image/x-icon',
}


class Handler(BaseHTTPRequestHandler):
    def reply(self, data, content_type='application/json', status=200, filename=None):
        if not isinstance(data, bytes):
            data = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.send_header(
            'Content-Security-Policy',
            (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
            ),
        )
        if filename:
            self.send_header('Content-Disposition', 'attachment; filename="' + filename + '"')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        with connect(self.server.db_path) as db:
            if path.startswith('/data/'):
                return self.data(db, path.removeprefix('/data/'))
            # Local-only verified downloads; the site and the export do not use them.
            if path.startswith('/api/assets/') or path.startswith('/api/documents/'):
                table = 'assets' if path.startswith('/api/assets/') else 'documents'
                identifier = path.split('/', 3)[3]
                row = db.execute(f'SELECT * FROM {table} WHERE id=?', (identifier,)).fetchone()
                if not row:
                    return self.reply({'error': 'Not found'}, status=404)
                saved_path = Path(row['path'])
                if not saved_path.is_file():
                    return self.reply({'error': 'Saved file unavailable'}, status=404)
                data = saved_path.read_bytes()
                if sha(data) != row['hash']:
                    return self.reply(
                        {'error': 'Saved file changed; import and verify again'}, status=409
                    )
                return self.reply(data, 'application/octet-stream', filename=saved_path.name)
        if path == '/api/review':
            return self.reply(listing(records.load(self.server.core)))
        if path.startswith('/api/review/'):
            return self.review_state(path.removeprefix('/api/review/'))
        if path.startswith('/api/'):
            return self.reply({'error': 'Not found'}, status=404)
        return self.site(path)

    # The owner's review (atlas.review), local only: read and written straight from atlas/core,
    # so a decision shows at once; the database catches up at the next rebuild.

    def review_state(self, identifier):
        data = records.load(self.server.core)
        item = data['breakthroughs'].get(identifier)
        if item is None:
            return self.reply({'error': 'Not found'}, status=404)
        index = Index(data)
        return self.reply(
            {
                'id': identifier,
                'review': item.get('review'),
                'page': bool(item.get('page')),
                'similar': {
                    'published': index.nearest(identifier, 'published'),
                    'all': index.nearest(identifier, 'all'),
                    'likely': LIKELY,
                },
            }
        )

    def do_POST(self):
        path = unquote(urlsplit(self.path).path)
        if not path.startswith('/api/review/'):
            return self.reply({'error': 'Not found'}, status=404)
        # Only this site may decide: a JSON body (other sites cannot send one without a
        # preflight this server never answers) from this server's own origin.
        origin = self.headers.get('Origin')
        host = self.headers.get('Host')
        if origin not in (f'http://{host}', None) or 'json' not in (
            self.headers.get('Content-Type') or ''
        ):
            return self.reply({'error': 'Refused'}, status=403)
        try:
            length = int(self.headers.get('Content-Length') or 0)
            body = json.loads(self.rfile.read(min(length, 20000)) or b'{}')
        except ValueError:
            return self.reply({'error': 'Not JSON'}, status=400)
        identifier = path.removeprefix('/api/review/')
        state = body.get('state')
        try:
            decide(identifier, state, body.get('note'), body.get('into'), core=self.server.core)
        except Refused as error:
            return self.reply({'error': str(error)}, status=400)
        problems = records.check(records.load(self.server.core))
        if problems:
            return self.reply({'error': 'Check failed: ' + '; '.join(problems[:3])}, status=500)
        warning = None
        if self.server.commit:
            try:
                records.commit(review_message(state, [identifier]))
            except Exception as error:  # noqa: BLE001 - the decision is written; commit later
                warning = f'Saved, not committed ({error}); the next commit of atlas/core takes it'
        return (
            self.review_state(identifier) if warning is None else self.reply({'warning': warning})
        )

    def data(self, db, name):
        """The site's data contract, built on request (the export writes the same files)."""
        value = None
        if name == 'catalog.json':
            value = catalog(db) | {'local': True}  # offers the review tools (Review.jsx)
        elif name == 'search.json':
            value = search_index(db)
        elif name.startswith('field/') and name.endswith('.json'):
            value = field_data(db, name[len('field/') : -len('.json')])
        elif name.startswith('b/') and name.endswith('.json'):
            value = breakthrough_data(db, name[len('b/') : -len('.json')])
        if value is None:
            return self.reply({'error': 'Not found'}, status=404)
        return self.reply(encode(value), 'application/json; charset=utf-8')

    def site(self, path):
        """Built files by path; any other path without a file extension is a client route."""
        root = SITE.resolve()
        target = (root / path.lstrip('/')).resolve()
        if target.is_relative_to(root) and target.is_file() and target.suffix in TYPES:
            return self.reply(target.read_bytes(), TYPES[target.suffix])
        if Path(path).suffix:
            return self.reply({'error': 'Not found'}, status=404)
        index = root / 'index.html'
        if not index.is_file():
            return self.reply(
                {'error': 'Site not built; run npm run build in atlas/web'}, status=404
            )
        return self.reply(index.read_bytes(), TYPES['.html'])

    def log_message(self, *args):
        pass


def serve(port=8765, db_path=DB, core=records.CORE, commit=True):
    if not Path(db_path).exists():
        raise SystemExit('Run python3 -m atlas.store first')
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.db_path = db_path
    server.core = core
    server.commit = commit
    print(f'Technology Atlas: http://127.0.0.1:{port}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    serve(parser.parse_args().port)
