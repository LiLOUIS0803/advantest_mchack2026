"""Persistent local inbox; no external delivery or machine actions."""
import json
import sqlite3
import uuid
import os
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
from .data import ROOT


def now(): return datetime.now(timezone.utc).isoformat()


class NotificationStore:
    def __init__(self,path=None):
        self.path=path or Path(os.environ.get('REPORT_DIR',str(ROOT/'reports')))/'notifications.sqlite3'
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS notifications (id TEXT PRIMARY KEY, run_id TEXT, label TEXT, created_at TEXT, status TEXT, summary TEXT, report TEXT, actions TEXT, UNIQUE(run_id,label))')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path);db.row_factory=sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self,run_id,state,trigger):
        stamp=now();summary={k:state.get(k) for k in ('wafer','lot','mode','batch','completed','failed','yield','classification_confidence')}
        summary.update(trigger=trigger,delivery='local_inbox',provisional=not state['ended'])
        report={'captured_at':stamp,'trigger':trigger,'state':state,
                'note':'Uncalibrated prediction; no external delivery or machine stop.'}
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO notifications VALUES (?,?,?,?,?,?,?,?)',
                       (str(uuid.uuid4()),run_id,state['predicted_label'],stamp,'new',json.dumps(summary),json.dumps(report),'[]'))

    def list(self,query='',status=''):
        if status not in ('','new','acknowledged','resolved'):raise ValueError('Invalid status')
        with self.connect() as db:
            rows=db.execute('SELECT id,run_id,label,created_at,status,summary FROM notifications ORDER BY created_at DESC').fetchall()
        items=[]
        for row in rows:
            item=dict(row);item.update(json.loads(item.pop('summary')))
            if status and item['status']!=status:continue
            if query and query.casefold() not in f'{item["lot"]} W{item["wafer"]} {item["label"]}'.casefold():continue
            items.append(item)
        return items[:100]

    def unread(self):
        with self.connect() as db:return db.execute("SELECT count(*) FROM notifications WHERE status='new'").fetchone()[0]

    def get(self,ident):
        with self.connect() as db:row=db.execute('SELECT * FROM notifications WHERE id=?',(ident,)).fetchone()
        if row is None:raise ValueError('Notification not found')
        item=dict(row)
        for key in ('summary','report','actions'):item[key]=json.loads(item[key])
        return item

    def update(self,ident,status):
        if status not in ('acknowledged','resolved'):raise ValueError('Invalid status')
        with self.connect() as db:
            row=db.execute('SELECT status,actions FROM notifications WHERE id=?',(ident,)).fetchone()
            if row is None:raise ValueError('Notification not found')
            if row['status']==status:return
            if row['status']=='resolved':raise ValueError('Resolved notification cannot be reopened')
            actions=json.loads(row['actions']);actions.append({'at':now(),'status':status,'actor':'local_dashboard'})
            db.execute('UPDATE notifications SET status=?,actions=? WHERE id=?',(status,json.dumps(actions),ident))


class NotificationPolicy:
    def __init__(self,store):self.store=store;self.reset()
    def reset(self):self.run_id=str(uuid.uuid4());self.label=None;self.streak=0
    def observe(self,event,state):
        kind=event['type']
        if kind=='wafer_start':self.reset();return
        if kind not in ('test_end','wafer_end'):return
        label=state.get('predicted_label')
        if kind=='test_end':
            self.streak=self.streak+1 if label==self.label else 1;self.label=label
        if label is None or label=='Normal':return
        if kind=='wafer_end':self.store.create(self.run_id,state,'wafer_end')
        elif state['completed']>=24 and self.streak>=3:self.store.create(self.run_id,state,'three_consecutive_completed_batches')
