"""One ordered event stream; synchronous prediction requests use queue barriers."""
import concurrent.futures
import time
from .oneapi_adapter import EventBridge
from .scene2_runtime import TemperatureRuntime


class CombinedBridge(EventBridge):
    def __init__(self,session,config,notify,on_change=lambda:None):
        super().__init__(session,config,notify)
        self.temperature=TemperatureRuntime(config);self.on_change=on_change
        self.scene1_error=None;self.scene2_error=None;self.last_event_at=None
        self.input_tester=None;self.temperature_active=False

    def process(self,tester,kind,payload):
        if kind=='predict':
            future=payload['future']
            if not future.set_running_or_notify_cancel():return
            try:
                if tester!=self.input_tester or not self.temperature_active or self.scene2_error:
                    raise ValueError('Temperature task has no valid active wafer')
                result=self.temperature.predict(payload['sensor'])
                future.set_result(result);self.on_change()
            except Exception as error:
                self.temperature.errors.append(str(error));future.set_exception(error)
            return
        if self.input_tester is None:self.input_tester=tester
        if tester!=self.input_tester:raise ValueError('One container supports one tester')
        self.last_event_at=time.time()
        if kind=='wafer_start':
            if str(payload['wafer']).lstrip('Ww0')=='2':raise ValueError('W2 is excluded from both tasks')
            self.temperature_active=True
        if not self.scene1_error:
            try:super().process(tester,kind,payload)
            except Exception as error:
                self.scene1_error=str(error);self.session.error='Anomaly task: '+str(error)
        if not self.scene2_error:
            try:self.temperature.on_event(kind,payload)
            except Exception as error:
                self.scene2_error=str(error);self.temperature.errors.append(str(error))
        if kind=='wafer_end':self.temperature_active=False
        if kind in ('wafer_start','test_start','test_end','wafer_end','lot_start') or any(
                r.get('number') in (100,120,140,160,180,200) for r in payload.get('rows',[])):
            self.on_change()

    def request_prediction(self,tester,sensor,timeout=.7):
        if self.failed:raise ValueError('ONEAPI input is in an error state')
        if isinstance(sensor,bool) or str(sensor) not in ('1','2','3','4','5','6'):raise ValueError('Invalid sensor request')
        future=concurrent.futures.Future()
        self.enqueue(tester,'predict',{'sensor':int(sensor),'future':future})
        try:return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            future.cancel();raise TimeoutError('Prediction queue deadline exceeded')
