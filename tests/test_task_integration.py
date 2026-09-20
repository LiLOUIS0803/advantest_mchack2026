import concurrent.futures,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from realtime.server import Session
from realtime.notifications import NotificationStore,NotificationPolicy
from realtime.combined_bridge import CombinedBridge
from realtime.hc_server import Store,make_server,chart
from realtime.hc_push import PushClient


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.folder=Path(self.tmp.name)
        with patch.dict('os.environ',{'REPORT_DIR':self.tmp.name}):self.session=Session()
        self.config={'valid_test_flags':[0,128],'part_flag_passed':{'0':True,'8':False},'result_mode':'sdk_value','measurement_aliases':{}}
        self.bridge=CombinedBridge(self.session,self.config,lambda *a:None)
        self.bridge.process('tester','lot_start',{'lot':'L'})
        self.bridge.process('tester','wafer_start',{'wafer':'4'})
        self.row={'head':1,'site':1,'x':-1,'y':1}
        self.bridge.process('tester','test_start',{'rows':[self.row]})
    def tearDown(self):self.tmp.cleanup()
    def predict(self,k):
        f=concurrent.futures.Future();self.bridge.process('tester','predict',{'sensor':k,'future':f});return f.result()
    def test_prediction_causal_and_duplicate_stable(self):
        p=self.predict(1);self.assertTrue(p.startswith('prediction 1: (1,'))
        row=dict(self.row,number=100,text='CP',suite='Main.sensor1',measurement='Main.sensor1.measurement',flag='0x0',values=[28.],scaling=0)
        self.bridge.process('tester','parametric',{'rows':[row]})
        self.assertEqual(self.predict(1),p)
        self.assertEqual(self.bridge.temperature.current[1]['x'],-1)
        row['number']=120;row['suite']='Main.sensor2';row['text']='DS0'
        self.bridge.process('tester','parametric',{'rows':[row]})
        frozen=self.bridge.temperature.pre_target[2][1][0]
        self.assertIn(str(round(frozen,3)),self.predict(2))
        self.assertEqual(self.bridge.temperature.current[1]['prediction_timing'][1],'late_request_frozen')
        self.assertIsNone(self.session.engine.predicted_label)
    def test_anomaly_failure_does_not_stop_temperature(self):
        self.bridge.process('tester','test_start',{'rows':[self.row]})
        self.assertIsNotNone(self.bridge.scene1_error)
        self.assertTrue(self.predict(1).startswith('prediction 1:'))
        self.assertFalse(self.bridge.failed)
    def test_temperature_failure_does_not_stop_anomaly(self):
        self.bridge.scene2_error='Test failure'
        self.bridge.process('tester','test_end',{'rows':[dict(self.row,pid='D1',pf=0,sbin=1,hbin=1)]})
        self.assertEqual(self.session.engine.completed,1)
        self.assertIsNone(self.bridge.scene1_error)
    def test_expired_prediction_not_executed(self):
        f=concurrent.futures.Future();f.cancel()
        self.bridge.process('tester','predict',{'sensor':1,'future':f})
        self.assertEqual(self.bridge.temperature.cache,{})
    def test_preview_is_causal_and_never_changes_official_predictor(self):
        import copy
        runtime=self.bridge.temperature
        before=copy.deepcopy((runtime.tp.buf,runtime.tp.bias,runtime.tp.last_pred,runtime.tp.last_raw,runtime.tp.stats,runtime.cache))
        first=runtime.snapshot()['devices'][0]['preview']
        self.assertEqual([p['sensor'] for p in first],[1,2,3,4,5,6])
        self.assertEqual(first[-1]['predicted_inputs'],5)
        self.assertTrue(all(not p['sent_to_tester'] for p in first))
        self.assertEqual(before,(runtime.tp.buf,runtime.tp.bias,runtime.tp.last_pred,runtime.tp.last_raw,runtime.tp.stats,runtime.cache))
        row=dict(self.row,number=100,text='CP',suite='Main.sensor1',measurement='Main.sensor1.measurement',flag=0,values=[28.],scaling=0)
        runtime.on_event('parametric',{'rows':[row]})
        next_preview=runtime.snapshot()['devices'][0]['preview']
        self.assertEqual([p['sensor'] for p in next_preview],[2,3,4,5,6])
        self.assertEqual(next_preview[0]['steps_ahead'],1)
        self.assertEqual(next_preview[0]['measured_inputs'],1)
        self.assertEqual(next_preview[0]['suites_ahead'],501)
    def test_flow_targets_follow_suites_not_test_number_arithmetic(self):
        runtime=self.bridge.temperature
        row=dict(self.row,number=999999,text='CP',suite='Main.subflow1.Flow1_Suite250',measurement='x',flag=0,values=[28.],scaling=0)
        runtime.on_event('parametric',{'rows':[row]})
        d=runtime.snapshot()['devices'][0]
        self.assertEqual([p['sensor'] for p in d['preview']],[2,3,4,5,6])
        self.assertEqual(d['preview'][0]['suites_ahead'],251)
        row['suite']='Unknown.program'
        runtime.on_event('parametric',{'rows':[row]})
        self.assertEqual(runtime.snapshot()['devices'][0]['preview'],[])
        runtime.on_event('test_end',{'rows':[dict(self.row,pid='D1',pf=0,sbin=1,hbin=1)]})
        runtime.on_event('test_start',{'rows':[self.row]})
        self.assertEqual(runtime.snapshot()['devices'][-1]['flow_position'],0)
    def test_late_prediction_frozen_before_target_updates(self):
        runtime=self.bridge.temperature
        expected=runtime.tp.predict_site(1,1)[0]
        runtime.tp.end_all()
        row=dict(self.row,number=100,text='CP',suite='Main.sensor1',measurement='Main.sensor1.measurement',flag=0,values=[999.],scaling=0)
        self.bridge.process('tester','parametric',{'rows':[row]})
        row['values']=[-999.]
        self.bridge.process('tester','parametric',{'rows':[row]})
        self.assertIn(str(round(expected,3)),self.predict(1))
        self.assertEqual(runtime.current[1]['actual'][0],-999.)
        runtime.on_event('test_end',{'rows':[dict(self.row,pid='D1',pf=0,sbin=1,hbin=1)]})
        self.assertEqual(runtime.pre_target,{})
    def test_hc_auth_persistence_reordering_and_separate_pages(self):
        token='x'*32;server=make_server('127.0.0.1',0,self.folder/'hc.db',token)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base='http://127.0.0.1:'+str(server.server_port)
            client=PushClient(self.session,base+'/api/ingest',token,self.folder);client.bridge=self.bridge
            self.predict(1);client.capture()
            with patch('realtime.hc_push.urlopen',side_effect=OSError('offline')):
                with self.assertRaises(OSError):client.send_once()
            self.assertTrue(client.send_once())
            store=Store(self.folder/'hc.db');state=store.state();self.assertEqual(state['scene2']['devices'][0]['pred'][0],self.bridge.temperature.current[1]['pred'][0])
            older=dict(state,seq=0)
            with self.assertRaises(ValueError):store.ingest(older)
            older=dict(state);older['scene1']={'wrong':True};store.ingest(older)
            self.assertNotIn('wrong',store.state()['scene1'])
            for path in ('/anomaly','/temperature'):
                with urlopen(base+path) as r:self.assertIn(b'lang="en"',r.read())
            with urlopen(base+'/api/temperature') as r:self.assertNotIn('scene1',json.load(r))
            with urlopen(base+'/api/state') as r:self.assertNotIn('scene2',json.load(r))
            with self.assertRaises(HTTPError) as error:urlopen(Request(base+'/api/ingest',data=b'{}'))
            self.assertEqual(error.exception.code,401)
            error.exception.close()
        finally:server.shutdown();server.server_close();thread.join()
    def test_hc_ack_survives_duplicate_report(self):
        store=Store(self.folder/'hc.db');p={'version':1,'kind':'report','run_id':'r','report':{'id':'a','summary':{'wafer':'4'},'report':{'state':{}}}}
        store.ingest(p);store.report('a','acknowledged');store.ingest(p)
        self.assertEqual(Store(self.folder/'hc.db').report('a')['status'],'acknowledged')
