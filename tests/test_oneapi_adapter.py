import unittest
from realtime.oneapi_adapter import EventBridge, snapshot_record


class Engine:
    columns=['1_Main.Test#CP']
    def snapshot(self):
        return dict(completed=4,predicted_label=None,classification_reason='minimum_16_completed_devices')


class Session:
    def __init__(self):
        import threading
        self.lock=threading.RLock();self.engine=Engine();self.events=[];self.error=None
        self.notification_policy=type('Policy',(),{'run_id':'run'})()
        self.notifications=type('Store',(),{'list':lambda self:[]})()
    def apply(self,event):self.events.append(event)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.session=Session();self.sent=[]
        self.config={'valid_test_flags':[0,128],'part_flag_passed':{'0':True,'8':False},
                     'result_mode':'sdk_value','measurement_aliases':{},'queue_capacity':1}
        self.bridge=EventBridge(self.session,self.config,lambda *x:self.sent.append(x))
        self.bridge.process('T','lot_start',{'lot':'L'})
        self.bridge.process('T','wafer_start',{'wafer':'1'})
        self.row=dict(head=1,site=2,x=3,y=4)
        self.bridge.process('T','test_start',{'rows':[self.row]})

    def measurement(self,**kwargs):
        return dict(self.row,number=1,text='Main.Test#CP',suite='Main.Test',measurement='CP',
                    flag=0,values=[12.5],scaling=-3,**kwargs)

    def test_mapping_no_future_identity_and_flag(self):
        self.bridge.process('T','parametric',{'rows':[self.measurement()]})
        event=self.session.events[-1]
        self.assertEqual(event['tests'],['1_Main.Test#CP'])
        self.assertEqual(event['values'],[[12.5]])
        self.assertNotIn('pid',self.session.events[1]['devices'][0])
        self.bridge.process('T','test_end',{'rows':[dict(self.row,pf='8',pid='D7',sbin=2,hbin=2)]})
        result=self.session.events[-1]['outcomes'][0]
        self.assertFalse(result['passed']);self.assertEqual(result['pid'],'D7')
        self.assertEqual(result['key'],event['keys'][0]);self.assertEqual(self.sent,[])

    def test_unknown_flags_and_other_tester_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unconfigured PartFlag'):
            self.bridge.process('T','test_end',{'rows':[dict(self.row,pf=16,pid='D7')]})
        with self.assertRaisesRegex(ValueError,'one tester'):
            self.bridge.process('OTHER','wafer_start',{'wafer':'4'})

    def test_supplied_log_text_and_hex_flags(self):
        row=self.measurement();row.update(text='CP',measurement='Main.Test.measurement',flag='0x0')
        self.bridge.process('T','multi_parametric',{'rows':[row]})
        self.assertEqual(self.session.events[-1]['tests'],['1_Main.Test#CP'])

    def test_invalid_measurement_skipped_and_scale_explicit(self):
        row=self.measurement();row['flag']=2;before=len(self.session.events)
        self.bridge.process('T','parametric',{'rows':[row]})
        self.assertEqual(len(self.session.events),before)
        self.config['result_mode']='apply_result_scaling';row['flag']=128
        self.bridge.process('T','parametric',{'rows':[row]})
        self.assertAlmostEqual(self.session.events[-1]['values'][0][0],.0125)

    def test_multi_requires_explicit_index_alias(self):
        row=self.measurement();row['values']=[5.,6.]
        before=len(self.session.events)
        self.bridge.process('T','multi_parametric',{'rows':[row]})
        self.assertEqual(len(self.session.events),before)
        self.config['measurement_aliases']['1|Main.Test|CP|1']='1_Main.Test#CP'
        self.bridge.process('T','multi_parametric',{'rows':[row]})
        self.assertEqual(self.session.events[-1]['values'],[[6.]])

    def test_overflow_latches_error(self):
        self.bridge.enqueue('T','wafer_end',{});self.bridge.enqueue('T','wafer_end',{})
        self.assertTrue(self.bridge.failed);self.assertIn('queue full',self.session.error)

    def test_only_new_local_report_triggers_message(self):
        item={'id':'N','run_id':'run','wafer':'1','label':'Site unbalance',
              'classification_confidence':{'score':.8}}
        self.session.notifications.list=lambda:[item]
        self.bridge.deliver();self.bridge.deliver()
        self.assertEqual(len(self.sent),1);self.assertIn('80.0%',self.sent[0][1])

    def test_callback_copies_values(self):
        class Native:
            values=[1.,2.]
            def get_ResultCount(self):return 1
            def query_HeadSite(self,i):return 258
            def query_TestNumber(self,i):return 1
            def query_TestText(self,i):return 'Main.Test#CP'
            def query_TestSuite(self,i):return 'Main.Test'
            def query_MeasurementName(self,i):return 'CP'
            def query_TestFlag(self,i):return 0
            def query_Results(self,i):return self.values
        native=Native();record=snapshot_record('multi_parametric',native,lambda x:1,lambda x:2)
        native.values[0]=999
        self.assertEqual(record['rows'][0]['values'],[1.,2.])
