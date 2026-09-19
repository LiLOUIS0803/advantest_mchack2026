"""Native ACS callbacks; inference runs on an ordered worker queue."""
import json
import logging
import threading
from oneapi import Monitor, DataType, toHead, toSite
from libACSAction import ActionManager
from realtime.oneapi_adapter import snapshot_record
from realtime.combined_bridge import CombinedBridge


class EdgeMonitor(Monitor):
    def __init__(self,session,config,on_change=lambda:None):
        Monitor.__init__(self)
        self.config=config;self.actions_lock=threading.RLock()
        def notify(tester,message):
            with self.actions_lock:ActionManager.set_message(tester,message)
        self.bridge=CombinedBridge(session,config,notify,on_change)
        self.worker=self.bridge.start()
        self.types={getattr(DataType,name):kind for name,kind in (
            ('DATA_TYP_PRODUCTION_LOTSTART','lot_start'),
            ('DATA_TYP_PRODUCTION_WAFERSTART','wafer_start'),
            ('DATA_TYP_PRODUCTION_WAFEREND','wafer_end'),
            ('DATA_TYP_PRODUCTION_TESTSTART','test_start'),
            ('DATA_TYP_PRODUCTION_TESTEND','test_end'),
            ('DATA_TYP_MEASURED_PARAMETRIC','parametric'),
            ('DATA_TYP_MEASURED_MULTI_PARAM','multi_parametric'))}

    def consumeData(self,tc,data):
        kind=self.types.get(data.getType())
        if kind is None:return
        try:
            payload=snapshot_record(kind,data,toHead,toSite)
            self.bridge.enqueue(tc.testerId,kind,payload)
        except Exception as error:self.bridge.fail(error)

    def consumeTPRequest(self,tc,request):
        try:
            body=json.loads(request)
            if body.get('key')=='prod_action':
                # Preserve the official action protocol; never replace with arbitrary JSON.
                with self.actions_lock:return ActionManager.get_prod(tc.testerId)
            if body.get('key')=='predict':
                message=self.bridge.request_prediction(str(tc.testerId),body.get('data'),
                         timeout=float(self.config.get('prediction_timeout',.7)))
                with self.actions_lock:
                    ActionManager.set_wait(tc.testerId,int(self.config.get('prediction_wait',10)),message)
                    return ActionManager.get(tc.testerId)
            if body.get('key')=='health':return 'error' if self.bridge.failed else 'ok'
            # Scenario 2 temperature requests must not invoke dummy wait/prediction actions.
            logging.info('Ignored TP request: %s',body.get('key'))
            return ''
        except Exception:
            logging.exception('Invalid TP request');return ''
