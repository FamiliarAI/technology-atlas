import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest

from ingestion.sources import Archive, request_url, fetch
from ingestion.tests.test_pipeline import paper_pdf


class SourceURLTests(unittest.TestCase):
    def test_encoding_preserves_existing_escapes_and_reserved_delimiters(self):
        value='https://example.org/AAP/PDF/CHT_Child Population café%20v2%2F.pdf?q=a b&sig=x%2By#résumé'
        encoded=request_url(value)
        self.assertEqual(encoded,'https://example.org/AAP/PDF/CHT_Child%20Population%20caf%C3%A9%20v2%2F.pdf?q=a%20b&sig=x%2By#r%C3%A9sum%C3%A9')
        self.assertEqual(request_url(encoded),encoded)
        self.assertEqual(request_url('https://example.org/already%2520encoded.pdf'),'https://example.org/already%2520encoded.pdf')
        with self.assertRaisesRegex(ValueError,'control'):request_url('https://example.org/a\nb.pdf')

    def test_space_containing_source_and_declared_pdf_links_capture_with_original_keys(self):
        requests=[]
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                if self.path=='/landing':
                    body=b'<html><h1>Research paper</h1><meta name="citation_pdf_url" content="/AAP/PDF/CHT_Child Population Characteristics.pdf"><a href="/caf\xc3\xa9%20paper.pdf">PDF</a></html>'
                    ctype='text/html'
                else:body=paper_pdf();ctype='application/pdf'
                self.send_response(200);self.send_header('Content-Type',ctype);self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base=f'http://127.0.0.1:{server.server_port}'
            original=base+'/AAP/PDF/CHT_Child Population Characteristics.pdf'
            with tempfile.TemporaryDirectory() as tmp:
                archive=Archive(tmp);archive.capture(original);archive.capture(base+'/landing')
                self.assertIn(original,archive.state)
                self.assertEqual(archive.state[original]['artifacts'][0]['resolved_url'],original.replace(' ','%20'))
                self.assertIn('/AAP/PDF/CHT_Child%20Population%20Characteristics.pdf',requests)
                self.assertIn('/caf%C3%A9%20paper.pdf',requests)
                operations=archive.state[base+'/landing']['operations']
                self.assertEqual(operations['paper_pdf:'+original]['status'],'saved')
                self.assertTrue(all(op['status']=='saved' for op in operations.values()))
        finally:server.shutdown();server.server_close();thread.join()

    def test_malformed_pdf_is_recorded_without_aborting_other_links(self):
        source='https://example.org/landing';good='https://example.org/good.pdf';bad='javascript:download.pdf'
        calls=[]
        def getter(url):
            calls.append(url)
            if url==source:return f'<html><h1>Paper</h1><a href="{bad}">bad</a><a href="{good}">good</a></html>'.encode(),'text/html',url
            return paper_pdf(),'application/pdf',url
        with tempfile.TemporaryDirectory() as tmp:
            archive=Archive(tmp,getter=getter);archive.capture(source)
            ops=archive.state[source]['operations']
            self.assertEqual(ops['paper_pdf:'+bad]['status'],'failed')
            self.assertEqual(ops['paper_pdf:'+good]['status'],'saved')
            self.assertNotIn(bad,calls)

    def test_http_invalid_url_is_a_recorded_nontransient_failure(self):
        calls=[]
        def getter(url):
            calls.append(url);raise http.client.InvalidURL('malformed transport URL')
        with tempfile.TemporaryDirectory() as tmp:
            archive=Archive(tmp,getter=getter);archive.capture('https://example.org/paper')
            op=archive.state['https://example.org/paper']['operations']['source:https://example.org/paper']
            self.assertEqual(op['status'],'failed');self.assertEqual(len(calls),1)
