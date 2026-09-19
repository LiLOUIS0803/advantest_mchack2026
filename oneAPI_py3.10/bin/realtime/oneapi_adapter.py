"""Ordered, single-tester bridge. SDK objects never leave the callback thread."""
import logging
import math
import queue
import threading


def integer(value):
    if isinstance(value,str):
        return int(value,16) if value.lower().startswith('0x') else int(value)
    return int(value)


def snapshot_record(kind, data, to_head, to_site):
    """Copy just required primitives while the native SDK object is alive."""
    if kind=='lot_start':return {'lot':str(data.get_LotId())}
    if kind=='wafer_start':return {'wafer':str(data.get_WaferId())}
    if kind=='wafer_end':return {}
    rows=[]
    for i in range(data.get_ResultCount()):
        hs=data.query_HeadSite(i)
        row={'head':int(to_head(hs)),'site':int(to_site(hs))}
        if kind in ('test_start','test_end'):
            row.update(x=int(data.query_XCoord(i)),y=int(data.query_YCoord(i)))
        if kind=='test_end':
            row.update(pid=str(data.query_PartId(i)),pf=data.query_PartFlag(i),
                       sbin=int(data.query_SBinResult(i)),hbin=int(data.query_HBinResult(i)))
        if kind in ('parametric','multi_parametric'):
            row.update(number=int(data.query_TestNumber(i)),text=str(data.query_TestText(i)),
                       suite=str(data.query_TestSuite(i)),measurement=str(data.query_MeasurementName(i)),
                       flag=data.query_TestFlag(i))
            if kind=='parametric':
                row.update(values=[float(data.query_Result(i))],scaling=int(data.query_ResultScaling(i)))
            else:
                row.update(values=[float(x) for x in data.query_Results(i)],scaling=0)
                try:row['pins']=[str(data.query_PinName(pid)) for pid in data.query_PinResults(i)]
                except (AttributeError,TypeError):row['pins']=[]
        rows.append(row)
    return {'rows':rows}


class EventBridge:
    def __init__(self, session, config, notify):
        self.session=session;self.config=config;self.notify=notify
        self.tester=None;self.lot='';self.wafer=None;self.batch=0;self.keys={};self.sent=set()
        self.failed=False;self.active=False;self.ignored=0
        self.queue=queue.Queue(maxsize=int(config.get('queue_capacity',4096)))
        self.column_set=set(session.engine.columns)

    def fail(self,error):
        self.failed=True
        with self.session.lock:self.session.error='ONEAPI stream rejected: '+str(error)
        logging.error('ONEAPI stream rejected; restart required: %s',error)

    def enqueue(self,tester,kind,payload):
        if self.failed:return
        try:self.queue.put_nowait((str(tester),kind,payload))
        except queue.Full:self.fail('Input queue full; data must not be silently dropped')

    def run(self):
        while True:
            item=self.queue.get()
            try:
                if not self.failed:
                    with self.session.lock:self.process(*item)
            except Exception as error:self.fail(error)
            finally:self.queue.task_done()

    def start(self):
        thread=threading.Thread(target=self.run,daemon=True,name='oneapi-analysis')
        thread.start();return thread

    def apply(self,event):self.session.apply(event)

    def process(self,tester,kind,payload):
        if self.tester is None:self.tester=tester
        if tester!=self.tester:raise ValueError('One container supports one tester; received '+tester)
        if kind=='lot_start':
            if self.active:raise ValueError('LotStart before previous WaferEnd')
            self.lot=payload['lot'];return
        if kind=='wafer_start':
            if self.active:raise ValueError('Overlapping wafers are not supported')
            self.wafer=payload['wafer'];self.batch=0;self.keys={};self.sent=set();self.ignored=0
            self.apply({'type':'wafer_start','wafer':self.wafer,'lot':self.lot,'mode':'live'})
            self.active=True;return
        if not self.active:raise ValueError('CP WaferStart required before testing')
        if kind=='test_start':
            if self.keys:raise ValueError('TestStart before previous TestEnd')
            self.batch+=1;devices=[]
            for row in payload['rows']:
                identity=(row['head'],row['site'])
                if identity in self.keys:raise ValueError('Duplicate head/site')
                key=f'{tester}:{self.wafer}:{self.batch}:{identity[0]}:{identity[1]}'
                self.keys[identity]=key;devices.append(dict(row,key=key))
            if not devices:raise ValueError('Empty TestStart')
            self.apply({'type':'test_start','batch':self.batch,'devices':devices});return
        if kind in ('parametric','multi_parametric'):
            for row in payload['rows']:
                key=self.keys.get((row['head'],row['site']))
                if key is None:raise ValueError('Measurement without matching TestStart')
                if integer(row['flag']) not in self.config['valid_test_flags']:
                    logging.warning('Ignoring invalid measurement flag: %s',row['flag']);continue
                base=f"{row['number']}|{row['suite']}|{row['measurement']}"
                for index,value in enumerate(row['values']):
                    alias=self.config.get('measurement_aliases',{}).get(base+'|'+str(index))
                    candidates=[alias] if alias else []
                    if len(row['values'])==1:
                        candidates += [f"{row['number']}_{row['text']}",
                            f"{row['number']}_{row['suite']}#{row['text']}",
                            f"{row['number']}_{row['suite']}#{row['measurement']}",f"{row['number']}_{row['suite']}"]
                    matches=set(candidates)&self.column_set
                    if len(matches)>1:raise ValueError('Ambiguous measurement mapping: '+base)
                    if not matches:
                        self.ignored+=1
                        if self.ignored<=10:logging.warning('Unmapped measurement: %s|%s',base,index)
                        continue
                    if self.config['result_mode']=='apply_result_scaling':
                        if kind=='multi_parametric':raise ValueError('Explicit multiparametric scale handling required')
                        value*=10.**row['scaling']
                    elif self.config['result_mode']!='sdk_value':raise ValueError('Unknown result_mode')
                    if not math.isfinite(value):continue
                    self.apply({'type':'measurement','keys':[key],'tests':[next(iter(matches))],
                                'values':[[value]],'stage':row['suite']})
            return
        if kind=='test_end':
            outcomes=[]
            for row in payload['rows']:
                pf=integer(row['pf']);mapping=self.config['part_flag_passed']
                if str(pf) not in mapping:raise ValueError('Unconfigured PartFlag: '+str(pf))
                passed=mapping[str(pf)]
                if not isinstance(passed,bool):raise ValueError('PartFlag mapping must use booleans')
                key=self.keys.get((row['head'],row['site']))
                if key is None:raise ValueError('TestEnd without matching TestStart')
                outcomes.append(dict(row,key=key,pf=pf,passed=passed))
            self.apply({'type':'test_end','outcomes':outcomes});self.keys={}
            state=self.session.engine.snapshot()
            logging.info('Wafer %s completed=%s label=%s reason=%s unmapped=%s',self.wafer,
                         state['completed'],state['predicted_label'],state['classification_reason'],self.ignored)
            self.deliver();return
        if kind=='wafer_end':
            self.apply({'type':'wafer_end'});self.active=False;self.deliver();return
        raise ValueError('Unsupported event '+kind)

    def deliver(self):
        run=self.session.notification_policy.run_id
        for item in self.session.notifications.list():
            if item['run_id']!=run or item['id'] in self.sent:continue
            confidence=item.get('classification_confidence')
            score=f"{confidence['score']:.1%}" if confidence else 'N/A'
            message=f"Wafer {item['wafer']} | {item['label']} | Confidence {score} (uncalibrated) | Report {item['id']}"
            self.notify(self.tester,message)
            self.sent.add(item['id'])
