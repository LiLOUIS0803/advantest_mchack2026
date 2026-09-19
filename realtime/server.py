"""Local dashboard + normalized event API. One stream per server instance."""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from .data import ROOT, manifest
from .classifier_engine import ClassifierEngine as Engine
from .replay import events, apply_event
from .notifications import NotificationStore, NotificationPolicy


class Session:
    def __init__(self):
        self.lock = threading.RLock()
        self.engine = Engine()
        self.running = False
        self.paused = False
        self.error = None
        self.delay = .15
        self.iterator = None
        self.notifications=NotificationStore()
        self.notification_policy=NotificationPolicy(self.notifications)

    def apply(self,event):
        apply_event(self.engine,event)
        if event['type'] in ('wafer_start','test_end','wafer_end'):
            self.notification_policy.observe(event,self.engine.snapshot())

    def run(self):
        while True:
            with self.lock:
                if self.running and not self.paused:
                    try:
                        self.apply(next(self.iterator))
                    except StopIteration:
                        self.running = False
                    except Exception as exc:
                        self.error = str(exc)
                        self.running = False
                delay = self.delay
            time.sleep(delay)


def serve(port=8765, api_only=False, session=None, live_only=False):
    session = session or Session()
    entries = [] if live_only else manifest()
    threading.Thread(target=session.run,daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass

        def send(self,body,status=200,ctype='application/json; charset=utf-8'):
            payload = body if isinstance(body,bytes) else json.dumps(body,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type',ctype)
            self.send_header('Content-Length',str(len(payload)))
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            path=urlparse(self.path).path
            assets={'/':'index.html','/dashboard.css':'dashboard.css',
                    '/scene2-style.css':'scene2-style.css',
                    **{f'/{name}.js':f'{name}.js' for name in ('api','app','visuals','outcomes','hierarchy','theme','notifications','task-nav')}}
            if path in assets and not api_only:
                name=assets[path]
                ctype='text/css' if name.endswith('.css') else 'text/javascript' if name.endswith('.js') else 'text/html'
                self.send((ROOT/'realtime/web'/name).read_bytes(),ctype=ctype+'; charset=utf-8')
            elif path=='/api/health':
                self.send({'status':'ok','api_version':1})
            elif path=='/api/notifications' or path.startswith('/api/notifications/'):
                try:
                    if path=='/api/notifications':
                        q=parse_qs(urlparse(self.path).query)
                        self.send({'items':session.notifications.list(q.get('q',[''])[0],q.get('status',[''])[0]),'unread':session.notifications.unread()})
                    else:self.send(session.notifications.get(path.rsplit('/',1)[-1]))
                except ValueError as exc:self.send({'error':str(exc)},400)
            elif path=='/api/catalog':
                self.send({'live_only':live_only,'wafers':[{'wafer':r['wafer'],'split':r['split']} for r in entries],
                           'model':session.engine.info})
            elif path=='/api/tests':
                self.send({'tests':session.engine.columns})
            elif path in ('/api/state','/api/export'):
                with session.lock:
                    try:
                        query=parse_qs(urlparse(self.path).query)
                        index=int(query['test'][0]) if 'test' in query else None
                        state=session.engine.snapshot(index)
                    except (ValueError, IndexError) as exc:
                        self.send({'error':str(exc)},400)
                        return
                    state.update(running=session.running,paused=session.paused,error=session.error)
                    state['schema_version']=1
                    self.send(state)
            elif path=='/api/evaluation':
                file=ROOT/'reports/wafer_classifier/comparison.json'
                self.send(json.loads(file.read_text(encoding='utf-8')) if file.exists() else {})
            else:
                self.send({'error':'Not found'},404)

        def do_POST(self):
            # Local UI requests only; no cross-origin browser control.
            origin=self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{port}',f'http://localhost:{port}'):
                self.send({'error':'Origin rejected'},403)
                return
            try:
                size=int(self.headers.get('Content-Length',0))
                if not 0 < size <= 2_000_000:
                    raise ValueError('Invalid payload size')
                body=json.loads(self.rfile.read(size))
                with session.lock:
                    if live_only and self.path in ('/api/replay','/api/pause','/api/events'):
                        raise ValueError('Live input is owned by the ONEAPI adapter')
                    if self.path.startswith('/api/notifications/'):
                        session.notifications.update(self.path.rsplit('/',1)[-1],body['status'])
                    elif self.path=='/api/replay':
                        entry=next((e for e in entries if int(e['wafer'])==int(body['wafer'])),None)
                        if entry is None:
                            raise ValueError('Unknown or excluded wafer')
                        iterator=iter(events(entry))
                        first=next(iterator)
                        session.apply(first)
                        session.iterator=iterator
                        session.delay=max(.01,min(2.,float(body.get('delay',.15))))
                        session.running=True
                        session.paused=False
                        session.error=None
                    elif self.path=='/api/pause':
                        session.paused=bool(body.get('paused',True))
                    elif self.path=='/api/events':
                        if session.running:
                            raise ValueError('Replay active; use a separate server instance for live data')
                        session.apply(body)
                    else:
                        self.send({'error':'Not found'},404)
                        return
                self.send({'ok':True})
            except (ValueError,KeyError,TypeError,IndexError) as exc:
                self.send({'error':str(exc)},400)

    print(f'{"JSON API" if api_only else "Dashboard"}: http://127.0.0.1:{port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--api-only',action='store_true',help='Serve JSON endpoints only; use realtime.frontend for the UI')
    args=parser.parse_args()
    serve(args.port,args.api_only)
