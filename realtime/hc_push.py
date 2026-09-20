"""Durable Edge -> HC outbox. Network work never runs in SDK callbacks."""
import copy,gzip,json,logging,os,sqlite3,threading,time,uuid
from pathlib import Path
from urllib.request import Request,urlopen
import numpy as np


class PushClient:
    def __init__(self,session,url,token,directory):
        self.session=session;self.url=url;self.token=token;self.run_id=str(uuid.uuid4());self.started=time.time();self.seq=0
        self.bridge=None;self.dirty=threading.Event();self.path=Path(directory)/'hc-outbox.sqlite3'
        self.path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.path)
        try:
            with db:db.execute('CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY,payload TEXT)')
        finally:db.close()
        self.db_lock=threading.Lock()
        self.queued_reports=set()

    def changed(self):self.dirty.set()

    def queue(self,packet,key):
        encoded=json.dumps(packet,allow_nan=False,separators=(',',':'))
        with self.db_lock:
            db=sqlite3.connect(self.path)
            try:
                with db:db.execute('INSERT OR REPLACE INTO outbox VALUES (?,?)',(key,encoded))
            finally:db.close()

    def capture(self):
        with self.session.lock:
            engine=self.session.engine;state=copy.deepcopy(engine.snapshot());self.seq+=1
            state.update(error=self.session.error,running=False,paused=False)
            ids={d['key']:i for i,d in enumerate(state['devices'])}
            # Compact point references; HC reconstructs only the selected chart.
            series=[[[ids[key],value] for key,value in points] for points in engine.series]
            reference={k:engine.model[k].tolist() for k in ('center','scale','point','up','down','spread_lo','spread_hi')}
            reports=[self.session.notifications.get(item['id']) for item in self.session.notifications.list()
                     if item['run_id']==self.session.notification_policy.run_id]
            packet={'version':1,'kind':'state','run_id':self.run_id,'started_at':self.started,'seq':self.seq,
                    'tester':self.bridge.input_tester or 'waiting','sent_at':time.time(),'last_event_at':self.bridge.last_event_at,'scene1':state,
                    'scene2':self.bridge.temperature.snapshot(),'columns':engine.columns,'series':series,'reference':reference}
        self.queue(packet,'state:'+self.run_id)
        for report in reports:
            if report['id'] in self.queued_reports:continue
            self.queue({'version':1,'kind':'report','run_id':self.run_id,'tester':packet['tester'],'report':report},'report:'+report['id'])
            self.queued_reports.add(report['id'])

    def send_once(self):
        with self.db_lock:
            db=sqlite3.connect(self.path)
            try:row=db.execute('SELECT id,payload FROM outbox ORDER BY rowid LIMIT 1').fetchone()
            finally:db.close()
        if row is None:return False
        body=gzip.compress(row[1].encode(),compresslevel=1)
        request=Request(self.url,data=body,headers={'Content-Type':'application/json','Content-Encoding':'gzip','Authorization':'Bearer '+self.token})
        with urlopen(request,timeout=60) as response:
            if response.status!=200:raise RuntimeError('HC rejected packet')
        with self.db_lock:
            db=sqlite3.connect(self.path)
            try:
                with db:db.execute('DELETE FROM outbox WHERE id=? AND payload=?',row)
            finally:db.close()
        return True

    def start(self,bridge):
        self.bridge=bridge
        def collect():
            while True:
                self.dirty.wait(timeout=5);self.dirty.clear()
                try:self.capture()
                except Exception:logging.exception('Cannot persist HC report snapshot')
                time.sleep(.8)
        def send():
            while True:
                try:
                    if not self.send_once():time.sleep(.5)
                except Exception as error:
                    logging.warning('HC unavailable; report queued: %s',error);time.sleep(3)
        for fn in (collect,send):threading.Thread(target=fn,daemon=True).start()
