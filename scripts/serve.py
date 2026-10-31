"""Loopback HTTP API and static frontend, backed by SQLite (no dependencies)."""
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit,unquote
import json,os,sqlite3,tempfile,argparse
from database import Database,DEFAULT_DB,APIError,ROOT

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT/'web'),**kwargs)
    @property
    def database(self):return self.server.database
    def end_headers(self):
        self.send_header('Cache-Control','no-store');super().end_headers()
    def _guard(self,mutation=False):
        expected={f'localhost:{self.server.server_port}',f'127.0.0.1:{self.server.server_port}'}
        if self.headers.get('Host') not in expected:raise APIError(403,'Localhost access only')
        origin=self.headers.get('Origin')
        if origin and origin not in {'http://'+h for h in expected}:raise APIError(403,'Cross-origin requests are not allowed')
        if mutation and self.headers.get('Content-Type','').split(';')[0]!='application/json':raise APIError(415,'Use application/json')
    def _body(self):
        try:length=int(self.headers.get('Content-Length','0'))
        except ValueError:raise APIError(400,'Invalid request size')
        if length<1 or length>8500000:raise APIError(413,'Request must be between 1 byte and 8.5 MB')
        try:return json.loads(self.rfile.read(length))
        except (UnicodeDecodeError,ValueError):raise APIError(400,'Invalid JSON')
    def _json(self,value,status=200):
        body=json.dumps(value,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def _error(self,error):
        if isinstance(error,APIError):self._json({'error':error.code,'message':str(error),'details':error.details},error.status)
        elif isinstance(error,sqlite3.IntegrityError):self._json({'error':'integrity_conflict','message':'Database integrity validation rejected the change.'},409)
        else:
            self.log_error('API failure: %s',str(error));self._json({'error':'server_error','message':'The operation could not be completed; no transaction was partially saved.'},500)
    def do_GET(self):
        path=urlsplit(self.path).path
        if path.startswith('/api/'):
            try:
                self._guard()
                if path=='/api/bootstrap':return self._json(self.database.bootstrap())
                if path=='/api/source-audit':
                    from source_audit import snapshot
                    return self._json(snapshot(self.database))
                if path=='/api/desk':return self._json(self.database.desk())
                if path=='/api/activity':return self._json(self.database.activity())
                if path=='/api/health':return self._json({'status':'ok','storage':'SQLite','counts':self.database.counts()})
                if path=='/api/migrations':return self._json(self.database.migrations())
                if path=='/api/export':return self._json(self.database.export())
                if path=='/api/backup':
                    fd,name=tempfile.mkstemp(suffix='.sqlite3');os.close(fd)
                    try:
                        self.database.backup(name);payload=Path(name).read_bytes()
                        self.send_response(200);self.send_header('Content-Type','application/vnd.sqlite3');self.send_header('Content-Disposition','attachment; filename="techtree-backup.sqlite3"');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
                    finally:Path(name).unlink(missing_ok=True)
                    return
                raise APIError(404,'Unknown API route')
            except Exception as error:return self._error(error)
        if unquote(path).startswith('/data/'):
            return self._json({'message':'Seed inputs are not runtime data. Use /api/bootstrap.'},410)
        super().do_GET()
    def do_POST(self):
        try:
            self._guard(True);path=urlsplit(self.path).path;value=self._body()
            if path=='/api/submissions':return self._json(self.database.create_submission(value),201)
            if path=='/api/migrate-browser':return self._json(self.database.migrate_browser(value))
            raise APIError(404,'Unknown API route')
        except Exception as error:self._error(error)
    def do_PATCH(self):
        try:
            self._guard(True);path=urlsplit(self.path).path;value=self._body()
            prefix='/api/submissions/'
            if path.startswith(prefix) and path[len(prefix):]:return self._json(self.database.dismiss(unquote(path[len(prefix):]),value))
            raise APIError(404,'Unknown API route')
        except Exception as error:self._error(error)

def make_server(path=DEFAULT_DB,port=4173):
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.database=Database(path);return server
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--db',type=Path,default=DEFAULT_DB);parser.add_argument('--port',type=int,default=4173);args=parser.parse_args()
    server=make_server(args.db,args.port)
    print(f'TechTree running at http://localhost:{server.server_port}\nSQLite: {server.database.path}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
