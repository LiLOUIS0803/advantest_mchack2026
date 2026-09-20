"""HC report receiver and web host; standard library only, no model execution."""
import argparse,gzip,io,hashlib,hmac,json,math,os,sqlite3,statistics,time
from contextlib import contextmanager
from pathlib import Path
from http.server import BaseHTTPRequestHandler,HTTPServer
try:
    from http.server import ThreadingHTTPServer
except ImportError:  # HC installations may provide Python 3.6.
    from socketserver import ThreadingMixIn

    class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True
from urllib.parse import urlparse,parse_qs

WEB=Path(__file__).parent/'web'


class Store:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS streams (id TEXT PRIMARY KEY,started REAL,seq INTEGER,received REAL,payload TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY,payload TEXT,status TEXT,actions TEXT)')

    @contextmanager
    def db(self):
        db=sqlite3.connect(str(self.path),timeout=20);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()

    def ingest(self,p):
        if p.get('version')!=1 or not isinstance(p.get('run_id'),str):raise ValueError('Invalid packet version/run')
        if p.get('kind')=='state':
            if not isinstance(p.get('seq'),int) or p['seq']<1:raise ValueError('Invalid sequence')
            for name in ('scene1','scene2','reference'):
                if not isinstance(p.get(name),dict):raise ValueError('Missing '+name)
            if not isinstance(p.get('columns'),list) or len(p['columns'])!=len(p.get('series',[])):raise ValueError('Invalid measurement schema')
            started=float(p['started_at'])
            if not math.isfinite(started):raise ValueError('Invalid start time')
            with self.db() as db:
                old=db.execute('SELECT started,seq FROM streams WHERE id=?',(p['run_id'],)).fetchone()
                if old and old['started']!=started:raise ValueError('Run identity changed')
                if old and old['seq']>=p['seq']:return
                db.execute('INSERT OR REPLACE INTO streams VALUES (?,?,?,?,?)',
                           (p['run_id'],started,p['seq'],time.time(),json.dumps(p,allow_nan=False)))
        elif p.get('kind')=='report':
            report=p['report']
            if not isinstance(report.get('id'),str) or not isinstance(report.get('report'),dict):raise ValueError('Invalid report')
            report['source_run']=p['run_id']
            with self.db() as db:db.execute('INSERT OR IGNORE INTO reports VALUES (?,?,?,?)',
                                            (report['id'],json.dumps(report,allow_nan=False),'new','[]'))
        else:raise ValueError('Unknown packet kind')

    def state(self,run=None):
        with self.db() as db:
            row=db.execute('SELECT * FROM streams WHERE id=?',(run,)).fetchone() if run else db.execute('SELECT * FROM streams ORDER BY started DESC LIMIT 1').fetchone()
        if row is None:return None
        p=json.loads(row['payload']);p['received_at']=row['received'];p['age_seconds']=max(0,time.time()-row['received']);return p

    def reports(self,q='',status='',run=None):
        with self.db() as db:rows=db.execute('SELECT * FROM reports ORDER BY rowid DESC').fetchall()
        items=[];unread=0
        for row in rows:
            r=json.loads(row['payload'])
            if run and r['source_run']!=run:continue
            unread+=row['status']=='new'
            item={k:v for k,v in r.items() if k not in ('report','actions','summary')}
            item.update(r.get('summary',{}));item['status']=row['status']
            if status and status!=row['status']:continue
            if q.casefold() not in f"{item.get('lot','')} W{item.get('wafer','')} {item.get('label','')}".casefold():continue
            items.append(item)
        return {'items':items[:100],'unread':unread}

    def report(self,ident,status=None):
        with self.db() as db:
            row=db.execute('SELECT * FROM reports WHERE id=?',(ident,)).fetchone()
            if row is None:raise ValueError('Unknown report')
            actions=json.loads(row['actions']);current=row['status']
            if status is not None:
                if status not in ('acknowledged','resolved'):raise ValueError('Invalid status')
                if current=='resolved' and status!=current:raise ValueError('Cannot reopen a resolved report')
                if current!=status:
                    actions.append({'at':time.time(),'status':status,'actor':'hc_dashboard'})
                    db.execute('UPDATE reports SET status=?,actions=? WHERE id=?',(status,json.dumps(actions),ident))
                current=status
        r=json.loads(row['payload']);r.update(status=current,actions=actions);return r


def chart(p,index):
    if not 0<=index<len(p['columns']):raise ValueError('Invalid test index')
    ref=p['reference'];center=ref['center'][index];scale=ref['scale'][index];point=ref['point'][index]
    low=center-scale*point;high=center+scale*point;devices=p['scene1']['devices'];points=[];windows=[]
    for n,(di,value) in enumerate(p['series'][index],1):
        d=devices[di];points.append({'n':n,'key':d['key'],'pid':d.get('pid'),'value':value,'outlier':value<low or value>high})
        if n>=16 and n%4==0:
            a=[x['value'] for x in points[n-16:n-8]];b=[x['value'] for x in points[n-8:n]]
            windows.append({'n':n,'delta':(statistics.mean(b)-statistics.mean(a))/scale,
                            'spread':max(statistics.stdev(b),scale*1e-6,1e-12)/max(statistics.stdev(a),scale*1e-6,1e-12)})
    return {'index':index,'test':p['columns'][index],'points':points,'windows':windows,'center':center,'low':low,'high':high,
            'down':-ref['down'][index],'up':ref['up'][index],'spread_low':ref['spread_lo'][index],'spread_high':ref['spread_hi'][index]}


def make_server(host,port,path,token):
    if len(token)<24:raise ValueError('Use a shared token of at least 24 characters')
    store=Store(path)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,value,status=200,mime='application/json; charset=utf-8'):
            data=value if isinstance(value,bytes) else json.dumps(value,allow_nan=False).encode()
            try:
                self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
                self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):
                self.close_connection=True
        def do_GET(self):
            url=urlparse(self.path);q=parse_qs(url.query);run=q.get('run',[None])[0];path=url.path
            try:
                assets={'/':'tasks.html','/anomaly':'index.html','/temperature':'temperature.html'}
                name=assets.get(path,path.lstrip('/'))
                allowed={'tasks.html','temperature.html','temperature.js','temperature.css','index.html','dashboard.css','api.js','app.js','visuals.js','outcomes.js','hierarchy.js','theme.js','notifications.js','scene2-style.css','task-nav.js'}
                if name in allowed:
                    mime='text/html' if name.endswith('.html') else 'text/css' if name.endswith('.css') else 'text/javascript'
                    return self.send((WEB/name).read_bytes(),mime=mime+'; charset=utf-8')
                if path=='/api/health':return self.send({'status':'ok','role':'hc-receiver'})
                if path=='/api/streams':
                    with store.db() as db:rows=db.execute('SELECT id,received,payload FROM streams ORDER BY started DESC').fetchall()
                    return self.send({'streams':[{'run_id':r['id'],'tester':json.loads(r['payload']).get('tester'),'received_at':r['received']} for r in rows]})
                if path=='/api/notifications':return self.send(store.reports(q.get('q',[''])[0],q.get('status',[''])[0],run))
                if path.startswith('/api/notifications/'):return self.send(store.report(path.rsplit('/',1)[-1]))
                if path=='/api/catalog':return self.send({'live_only':True,'wafers':[],'model':{'model':'Edge inference','training_devices':1920,'measurement_count':0}})
                if path=='/api/evaluation':return self.send({})
                p=store.state(run)
                if p is None:return self.send({'waiting':True,'message':'Waiting for Edge data'},503)
                if path=='/api/temperature':
                    if q.get('live')==['1']:
                        if run:return self.send({'error':'Live temperature view does not accept historical runs'},400)
                        event_age=time.time()-p.get('last_event_at',0) if p.get('last_event_at') else float('inf')
                        if p['age_seconds']>10 or time.time()-p.get('sent_at',0)>15:
                            return self.send({'waiting':True,'message':'Waiting for fresh Edge data'},503)
                        if event_age>60 or not p.get('scene2',{}).get('wafer'):
                            return self.send({'waiting':True,'message':'Waiting for test events'},503)
                        if p['scene2'].get('ended'):
                            return self.send({'waiting':True,'message':'Wafer complete. Waiting for next wafer'},503)
                    return self.send({k:p.get(k) for k in ('run_id','tester','scene2','received_at','age_seconds','last_event_at')})
                if path=='/api/source':return self.send({k:p.get(k) for k in ('run_id','tester','received_at','age_seconds','last_event_at')})
                if path=='/api/tests':return self.send({'tests':p['columns']})
                if path in ('/api/state','/api/export'):
                    state=p['scene1'];state['test_chart']=chart(p,int(q.get('test',['0'])[0]));return self.send(state)
                return self.send({'error':'Not found'},404)
            except (ValueError,KeyError,TypeError,IndexError) as error:self.send({'error':str(error)},400)
        def do_POST(self):
            ingest=urlparse(self.path).path=='/api/ingest'
            if ingest:
                if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):return self.send({'error':'Unauthorized'},401)
            else:
                origin=self.headers.get('Origin')
                if origin and urlparse(origin).netloc!=self.headers.get('Host'):return self.send({'error':'Origin rejected'},403)
            try:
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=32_000_000:raise ValueError('Invalid payload size')
                self.connection.settimeout(65)
                chunks=[];remaining=size
                while remaining:
                    chunk=self.rfile.read(min(remaining,65536))
                    if not chunk:raise ValueError('Incomplete request body; retry the complete packet')
                    chunks.append(chunk);remaining-=len(chunk)
                raw=b''.join(chunks)
                encoding=self.headers.get('Content-Encoding','identity')
                if encoding=='gzip':
                    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:raw=stream.read(128_000_001)
                    if len(raw)>128_000_000:raise ValueError('Expanded payload too large')
                elif encoding!='identity':raise ValueError('Unsupported content encoding')
                data=json.loads(raw,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
                if ingest:store.ingest(data)
                elif urlparse(self.path).path.startswith('/api/notifications/'):
                    store.report(urlparse(self.path).path.rsplit('/',1)[-1],data['status'])
                else:return self.send({'error':'HC does not control the tester'},404)
                self.send({'ok':True})
            except (ValueError,KeyError,TypeError) as error:self.send({'error':str(error)},400)
            except (OSError,EOFError) as error:
                self.close_connection=True
                self.send({'error':'Interrupted request; retry the complete packet'},400)
    return ThreadingHTTPServer((host,port),Handler)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--host',default='0.0.0.0');parser.add_argument('--port',type=int,default=8770)
    parser.add_argument('--data',default='hc-reports.sqlite3');parser.add_argument('--token-file',required=True)
    args=parser.parse_args();token=Path(args.token_file).read_text().strip()
    print('HC dashboard: http://127.0.0.1:'+str(args.port),flush=True)
    make_server(args.host,args.port,args.data,token).serve_forever()
if __name__=='__main__':main()
