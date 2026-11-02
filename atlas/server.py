"""Loopback-only server. Saved research copies are local downloads, never public hosting."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from .store import DB, ROOT, catalog, connect, progress, progress_summary, sha

STATIC = ROOT / 'atlas/static'
TREE = STATIC / 'tree'  # built React tech tree (atlas/web)
TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.woff2': 'font/woff2', '.woff': 'font/woff', '.svg': 'image/svg+xml'}

class Handler(BaseHTTPRequestHandler):
    def reply(self, data, content_type='application/json', status=200, filename=None):
        if not isinstance(data, bytes): data = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        if filename: self.send_header('Content-Disposition', 'attachment; filename="' + filename + '"')
        self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        with connect(self.server.db_path) as db:
            if path == '/api/catalog': return self.reply(catalog(db))
            if path == '/api/progress': return self.reply(progress_summary(db))
            if path.startswith('/api/breakthroughs/'):
                identifier = path.removeprefix('/api/breakthroughs/')
                row = db.execute('SELECT payload,field FROM breakthroughs WHERE id=?', (identifier,)).fetchone()
                if not row: return self.reply({'error':'Not found'}, status=404)
                item = json.loads(row['payload'])
                f = db.execute('SELECT run_hash FROM fields WHERE id=?', (row['field'],)).fetchone()
                item['run'] = dict(db.execute('SELECT hash, imported_at FROM runs WHERE hash=?', (f['run_hash'],)).fetchone())
                item['progress'], item['milestone_status'] = progress(db, identifier, len(item['completion_criteria']))
                item['documents'] = [r['id'].split(':',1)[1] for r in db.execute('SELECT id FROM documents WHERE id LIKE ?', (identifier + ':%',))]
                # Do not expose filesystem paths through the browser API.
                item.pop('provenance', None)
                for s in item.get('sources', []):
                    for a in s.get('artifacts', []):
                        a.pop('path', None); a.pop('absolute_path', None)
                return self.reply(item)
            if path.startswith('/api/assets/') or path.startswith('/api/documents/'):
                table = 'assets' if path.startswith('/api/assets/') else 'documents'
                identifier = path.split('/',3)[3]
                row = db.execute(f'SELECT * FROM {table} WHERE id=?', (identifier,)).fetchone()
                if not row: return self.reply({'error':'Not found'}, status=404)
                p = Path(row['path'])
                if not p.is_file(): return self.reply({'error':'Saved file unavailable'}, status=404)
                data = p.read_bytes()
                if sha(data) != row['hash']: return self.reply({'error':'Saved file changed; import and verify again'}, status=409)
                return self.reply(data, 'application/octet-stream', filename=p.name)
        if path == '/tree' or path.startswith('/tree/'):
            rel = path.removeprefix('/tree').lstrip('/') or 'index.html'
            target = (TREE / rel).resolve()
            if not target.is_relative_to(TREE.resolve()) or not target.is_file() or target.suffix not in TYPES:
                target = TREE / 'index.html'  # client-side routes fall back to the app
            if not target.is_file(): return self.reply({'error':'Tree not built; run npm run build in atlas/web'}, status=404)
            return self.reply(target.read_bytes(), TYPES[target.suffix])
        files = {'/':('index.html','text/html; charset=utf-8'), '/app.js':('app.js','text/javascript; charset=utf-8'), '/style.css':('style.css','text/css; charset=utf-8')}
        if path in files:
            name, mime = files[path]; return self.reply((STATIC/name).read_bytes(),mime)
        return self.reply({'error':'Not found'},status=404)

    def log_message(self, *args): pass

def serve(port=8765, db_path=DB):
    if not Path(db_path).exists(): raise SystemExit('Run python3 -m atlas.store first')
    server = ThreadingHTTPServer(('127.0.0.1',port),Handler); server.db_path = db_path
    print(f'Technology Atlas: http://127.0.0.1:{port}',flush=True)
    server.serve_forever()

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);serve(p.parse_args().port)
