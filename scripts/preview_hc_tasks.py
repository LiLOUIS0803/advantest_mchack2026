"""Prepare a clearly marked local replay snapshot for both independent HC pages."""
import os,sys,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from realtime.server import Session
from realtime.data import manifest
from realtime.replay import events
from realtime.scene2_runtime import TemperatureRuntime
from realtime.hc_push import PushClient
import json

def main():
    p=argparse.ArgumentParser();p.add_argument('--wafer',type=int,default=1);p.add_argument('--directory',default='reports/hc-preview');a=p.parse_args()
    folder=Path(a.directory);folder.mkdir(parents=True,exist_ok=True);os.environ['REPORT_DIR']=str(folder)
    session=Session();config=json.loads((ROOT/'oneAPI_py3.10/bin/adapter_config.json').read_text());temp=TemperatureRuntime(config)
    entry=next(e for e in manifest() if int(e['wafer'])==a.wafer)
    for event in events(entry):
        session.apply(event);kind=event['type']
        if kind=='wafer_start':temp.on_event(kind,event)
        elif kind=='test_start':temp.on_event(kind,{'rows':[{'head':1,'site':d['site'],'x':-32768,'y':-32768} for d in event['devices']]})
        elif kind=='measurement':
            rows=[]
            for col,idx in enumerate(event['indices']):
                name=session.engine.columns[idx];number=int(name.split('_')[0])
                if number not in temp.tp.pins_of_num:continue
                suitepin=name.split('_',1)[1];suite,_,pin=suitepin.partition('#')
                for di,key in enumerate(event['keys']):
                    site=session.engine.devices[key]['site']
                    rows.append(dict(head=1,site=site,number=number,text=pin,suite=suite,measurement=suite+'.measurement',flag=0,values=[event['values'][di][col]],scaling=0))
            temp.on_event('parametric',{'rows':rows})
            k=1 if event['stage'].startswith('\u524d') else int(event['stage'][6])+1
            if k<=6:temp.predict(k)
        elif kind=='test_end':temp.on_event(kind,{'rows':[dict(r,head=1,site=session.engine.devices[r['key']]['site']) for r in event['outcomes']]})
    bridge=type('Bridge',(),{'temperature':temp,'input_tester':'CSV replay (not live)','last_event_at':None})()
    client=PushClient(session,'http://127.0.0.1:1/api/ingest','demo-token',folder);client.bridge=bridge;client.capture()
    from realtime.hc_server import Store
    store=Store(folder/'hc.sqlite3')
    import sqlite3
    db=sqlite3.connect(client.path)
    try:
        for row in db.execute('SELECT payload FROM outbox'):store.ingest(json.loads(row[0]))
    finally:db.close()
    print('Preview database:',folder/'hc.sqlite3')
if __name__=='__main__':main()
