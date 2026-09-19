"""Independent static frontend host with a same-origin JSON API proxy."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from pathlib import Path

WEB = Path(__file__).resolve().parent/'web'
ASSETS = {'/':'index.html','/dashboard.css':'dashboard.css',
          '/scene2-style.css':'scene2-style.css',
          **{f'/{name}.js':f'{name}.js' for name in ('api','app','visuals','outcomes','hierarchy','theme','notifications','task-nav')}}


def serve(port=8770, backend='http://127.0.0.1:8771', host='127.0.0.1', public_origin=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass

        def send(self,body,status=200,ctype='application/json; charset=utf-8'):
            self.send_response(status)
            self.send_header('Content-Type',ctype)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.end_headers();self.wfile.write(body)

        def proxy(self,body=None):
            try:
                req=Request(backend.rstrip('/')+self.path,data=body,
                            headers={'Content-Type':'application/json'},method=self.command)
                with urlopen(req,timeout=10) as response:
                    self.send(response.read(),response.status,response.headers.get('Content-Type','application/json'))
            except HTTPError as e:
                self.send(e.read(),e.code,e.headers.get('Content-Type','application/json'))
            except (URLError,TimeoutError):
                self.send(json.dumps({'error':'Analysis service unavailable. Check that the JSON API is running.'},ensure_ascii=False).encode(),502)

        def do_GET(self):
            path=urlparse(self.path).path
            if path.startswith('/api/'):
                self.proxy();return
            if path not in ASSETS:
                self.send(b'{"error":"Not found"}',404);return
            name=ASSETS[path]
            mime='text/css' if name.endswith('.css') else 'text/javascript' if name.endswith('.js') else 'text/html'
            self.send((WEB/name).read_bytes(),ctype=mime+'; charset=utf-8')

        def do_POST(self):
            origin=self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{port}',f'http://localhost:{port}',public_origin):
                self.send(b'{"error":"Origin rejected"}',403);return
            if not urlparse(self.path).path.startswith('/api/'):
                self.send(b'{"error":"Not found"}',404);return
            try:
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=2_000_000:raise ValueError()
            except ValueError:
                self.send(b'{"error":"Invalid payload size"}',400);return
            self.proxy(self.rfile.read(size))

    print(f'Frontend: http://127.0.0.1:{port} -> JSON API {backend}',flush=True)
    ThreadingHTTPServer((host,port),Handler).serve_forever()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8770)
    parser.add_argument('--backend',default='http://127.0.0.1:8771')
    args=parser.parse_args();serve(args.port,args.backend)
