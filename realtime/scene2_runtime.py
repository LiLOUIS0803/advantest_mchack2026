"""Causal Scene 2 integration using the supplied NumPy predictor, no file polling."""
import copy
import logging
from .data import ROOT
from .oneapi_adapter import integer
from scene2.temp_predictor import TempPredictor


class TemperatureRuntime:
    def __init__(self,config):
        self.tp=TempPredictor(str(ROOT/'artifacts/scene2/temp_models.json'))
        self.config=config;self.wafer='';self.batch=0;self.completed=[];self.current={};self.cache={};self.errors=[];self.pre_target={};self.ended=False

    def on_event(self,kind,payload):
        if kind=='lot_start':self.tp.reset_bias()
        elif kind=='wafer_start':
            self.ended=False
            self.wafer=payload['wafer'];self.batch=0;self.completed=[];self.current={};self.cache={};self.errors=[];self.pre_target={};self.tp.end_all()
        elif kind=='test_start':
            self.batch+=1;self.tp.end_all();self.cache={};self.current={};self.pre_target={}
            for r in payload['rows']:
                site=r['site']
                if site in self.current:raise ValueError('Scene 2 requires distinct site numbers across active heads')
                self.current[site]={'key':f"{self.batch}:{r['head']}:{site}",'site':site,'head':r['head'],
                    'batch':self.batch,'pid':None,'x':None if r['x']==-32768 else r['x'],'y':None if r['y']==-32768 else r['y'],
                    'pred':[None]*6,'actual':[None]*6,'raw':[None]*6,'forecast':[None]*6,'missing':[None]*6,'completed':False}
        elif kind in ('parametric','multi_parametric'):
            for r in payload['rows']:
                if integer(r['flag']) not in self.config['valid_test_flags']:continue
                if r['site'] not in self.current:raise ValueError('Temperature measurement outside active batch')
                if self.current[r['site']]['head']!=r['head']:raise ValueError('Head mismatch')
                for i,value in enumerate(r['values']):
                    pins=r.get('pins',[])
                    pin=pins[i] if len(pins)==len(r['values']) else r['text'] if len(r['values'])==1 else None
                    alias=self.config.get('measurement_aliases',{}).get(f"{r['number']}|{r['suite']}|{r['measurement']}|{i}")
                    if alias:pin=alias.split('#')[-1] if '#' in alias else ''
                    if len(r['values'])>1 and pin is None:continue
                    if self.config['result_mode']=='apply_result_scaling':
                        if kind=='multi_parametric':raise ValueError('Multiparametric scale requires explicit mapping')
                        value*=10.**r['scaling']
                    key=self.tp._resolve_key(r['number'],pin)
                    sensor=self.tp.key_to_sensor.get(key)
                    if sensor is not None and sensor not in self.pre_target and sensor not in self.cache:
                        # Freeze all sites before consuming the FIRST target value.
                        # Never let another site's target residual change this prediction.
                        predictor=copy.deepcopy(self.tp)
                        self.pre_target[sensor]={site:predictor.predict_site(sensor,site) for site in self.current}
                    kept=self.tp.update(r['site'],r['number'],value,pin=pin)
                    if kept:
                        for k,key in self.tp.target_key.items():
                            if key in self.tp.buf.get(r['site'],{}):self.current[r['site']]['actual'][k-1]=self.tp.buf[r['site']][key]
        elif kind=='test_end':
            for r in payload['rows']:
                d=self.current[r['site']];d.update(pid=r['pid'],pf=integer(r['pf']),sbin=r['sbin'],hbin=r['hbin'],completed=True)
                if r['x']!=-32768 and r['y']!=-32768:d.update(x=r['x'],y=r['y'])
                self.completed.append(d)
            self.current={};self.tp.end_all();self.cache={};self.pre_target={}
        elif kind=='wafer_end':self.ended=True

    def predict(self,k):
        if k not in range(1,7):raise ValueError('Sensor request must be 1 through 6')
        if not self.current:raise ValueError('No active touchdown')
        if k in self.cache:return self.cache[k]
        late=any(self.tp.target_key[k] in self.tp.buf.get(site,{}) for site in self.current)
        if late and k not in self.pre_target:
            raise ValueError('Late prediction has no pre-target snapshot; refusing hindsight prediction')
        if late:
            message='Late request: sensor%d batch%d; returning frozen pre-target prediction, not an on-time prediction'%(k,self.batch)
            logging.warning('%s wafer=%s',message,self.wafer)
            self.errors.append(message)
            self.errors=self.errors[-100:]
        values={}
        for site,d in self.current.items():
            v,info=self.pre_target[k][site] if late else self.tp.predict_site(k,site);values[site]=round(v,3)
            d.setdefault('prediction_timing',[None]*6)[k-1]='late_request_frozen' if late else 'on_time'
            d['pred'][k-1]=values[site];d['raw'][k-1]=info['raw'];d['missing'][k-1]=info['n_missing']
        message=f'prediction {k}:'+''.join(f' ({site},{v})' for site,v in values.items())
        self.cache[k]=message;return message

    def snapshot(self):
        return {'wafer':self.wafer,'batch':self.batch,'ended':self.ended,'devices':copy.deepcopy(self.completed+list(self.current.values())),
                'errors':list(self.errors),'bias_correction':True,'excluded_wafers':[2],
                'model':'Standardized Lasso + received-data online bias correction',
                'limits':{str(k):{'lo':m['limit_lo'],'hi':m['limit_hi']} for k,m in self.tp.models.items()}}
