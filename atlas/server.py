"""Loopback-only server. Saved research copies are local downloads, never public hosting."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from .store import DB, ROOT, catalog, connect, progress, progress_summary, sha

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
            if path == '/api/catalog':
                return self.reply(catalog(db))
            if path == '/api/progress':
                return self.reply(progress_summary(db))
            if path.startswith('/api/breakthroughs/'):
                identifier = path.removeprefix('/api/breakthroughs/')
                row = db.execute(
                    'SELECT payload FROM breakthroughs WHERE id=?', (identifier,)
                ).fetchone()
                if not row:
                    return self.reply({'error': 'Not found'}, status=404)
                item = json.loads(row['payload'])
                item['progress'], item['milestone_status'] = progress(
                    db, identifier, len(item['completion_criteria'])
                )
                item['documents'] = [
                    row['id'].split(':', 1)[1]
                    for row in db.execute(
                        'SELECT id FROM documents WHERE id LIKE ?', (identifier + ':%',)
                    )
                ]
                # Do not expose filesystem paths through the browser API.
                item.pop('provenance', None)
                for source in item.get('sources', []):
                    for artifact in source.get('artifacts', []):
                        artifact.pop('path', None)
                        artifact.pop('absolute_path', None)
                return self.reply(item)
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
        if path.startswith('/api/'):
            return self.reply({'error': 'Not found'}, status=404)
        return self.site(path)

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


def serve(port=8765, db_path=DB):
    if not Path(db_path).exists():
        raise SystemExit('Run python3 -m atlas.store first')
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.db_path = db_path
    print(f'Technology Atlas: http://127.0.0.1:{port}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    serve(parser.parse_args().port)
