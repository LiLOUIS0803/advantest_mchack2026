import unittest
import numpy as np
from realtime.engine import Engine
from realtime.data import manifest
from realtime.replay import events, apply_event
from realtime.metrics import window_statistics
from realtime.evaluate import compare_labels


class CausalityTests(unittest.TestCase):
    def test_fail_results_only_appear_at_testend_and_match_csv(self):
        from realtime.data import read_wafer
        entry=next(e for e in manifest() if int(e['wafer'])==14)
        _,rows,_=read_wafer(entry)
        engine=Engine()
        seen_end=False
        for event in events(entry):
            if event['type']=='test_end' and not seen_end:
                snap=engine.snapshot()
                self.assertEqual(snap['failed'],0)
                self.assertEqual(snap['failed_devices'],[])
                self.assertTrue(all(d.get('pf') is None for d in snap['devices']))
                seen_end=True
            apply_event(engine,event)
        snap=engine.snapshot()
        failed=[r for r in rows if r[6]=='8']
        self.assertEqual(snap['failed'],len(failed))
        self.assertEqual(snap['passed']+snap['failed'],snap['completed'])
        self.assertEqual({d['pid'] for d in snap['failed_devices']},{r[0] for r in failed})
        self.assertEqual(sum(t['batch_failed'] for t in snap['timeline']),snap['failed'])
        self.assertTrue(all(d['pf']==8 and d['sbin'] is not None for d in snap['failed_devices']))

    def test_exclusion_and_fitted_sources(self):
        model=Engine()
        train={int(e['wafer']) for e in manifest() if e['split']=='train_normal'}
        self.assertEqual(set(model.info['training_wafers']),train)
        self.assertNotIn(2,train)
        self.assertFalse(any(int(e['wafer'])==2 for e in manifest()))
        with self.assertRaises(ValueError): model.reset('W02')

    def test_unseen_results_and_pid_are_not_used(self):
        entry=next(e for e in manifest() if int(e['wafer'])==14)
        stream=iter(events(entry)); engine=Engine()
        for _ in range(3): apply_event(engine,next(stream))
        self.assertEqual(engine.completed,0)
        self.assertIsNone(engine.snapshot()['yield'])
        self.assertEqual(engine.pids,{})
        self.assertTrue(all(np.isnan(v[30:]).all() for v in engine.current.values()))
        self.assertEqual(engine.measured,120)

    def test_single_device_delivery_matches_multisite_delivery(self):
        entry=next(e for e in manifest() if int(e['wafer'])==18)
        a,b=Engine(),Engine()
        for index,event in enumerate(events(entry)):
            apply_event(a,event)
            if event['type']=='measurement':
                for key, values in zip(event['keys'],event['values']):
                    apply_event(b,{**event,'keys':[key],'values':[values]})
            else:
                apply_event(b,event)
            if index==40: break
        # Changing transport grouping must not change the anomaly decision.
        sa,sb=a.snapshot(),b.snapshot()
        sa.pop('analysis_ms');sb.pop('analysis_ms')
        self.assertEqual(sa,sb)
        self.assertLess(sa['completed'],80)

    def test_invalid_or_duplicate_event_does_not_count_twice(self):
        e=Engine();e.reset('4');e.start_batch(1,[{'key':'a','site':1}])
        e.measurement(['a'],[0],[[e.model['center'][0]]])
        with self.assertRaises(ValueError): e.measurement(['a'],[0],[[1.]])
        with self.assertRaises(ValueError): e.finish_batch([{'key':'a','pid':'1','passed':'false'}])
        self.assertEqual(e.completed,0)
        e.finish_batch([{'key':'a','pid':'1','passed':True}])
        with self.assertRaises(ValueError): e.finish_batch([{'key':'a','pid':'1','passed':True}])
        self.assertEqual(e.completed,1)

    def test_low_yield_requires_completed_outcomes(self):
        e=Engine();e.reset('3')
        for batch in range(1,5):
            keys=[f'{batch}:{i}' for i in range(4)]
            e.start_batch(batch,[{'key':k} for k in keys])
            if batch==4: self.assertNotIn('low_yield',e.latest)
            e.finish_batch([{'key':k,'pid':k,'passed':False} for k in keys])
        self.assertIn('low_yield',e.latest)
        self.assertEqual(e.snapshot()['yield'],0)

    def test_point_warning_does_not_imply_wafer_anomaly(self):
        e=Engine();e.reset('4');e.start_batch(1,[{'key':'a'}])
        value=e.model['center'][0]+2*e.model['point'][0]*e.model['scale'][0]
        e.measurement(['a'],[0],[[value]])
        self.assertEqual(e.snapshot()['status'],'warning')
        self.assertIsNone(e.snapshot()['alerts'][0]['devices'][0]['pid'])

    def test_map_and_curves_only_reveal_received_data(self):
        entry=next(e for e in manifest() if int(e['wafer'])==14)
        stream=iter(events(entry)); e=Engine()
        apply_event(e,next(stream));apply_event(e,next(stream))
        self.assertEqual(len(e.snapshot()['devices']),4)
        self.assertTrue(all(d['x'] is None and d['pid'] is None for d in e.snapshot()['devices']))
        self.assertEqual(e.test_chart(0)['points'],[])
        apply_event(e,next(stream))
        self.assertEqual(len(e.test_chart(0)['points']),4)
        self.assertEqual(e.test_chart(30)['points'],[])
        self.assertEqual(e.test_chart(0)['windows'],[])
        self.assertTrue(all(p['pid'] is None for p in e.test_chart(0)['points']))
        for event in stream:
            apply_event(e,event)
            if event['type']=='test_end':break
        state=e.snapshot(0)
        self.assertTrue(all(d['x'] is not None and d['completed'] for d in state['devices']))
        self.assertTrue(all(p['pid'] is not None for p in state['test_chart']['points']))
        self.assertEqual(len(state['test_chart']['points']),4)

    def test_chart_statistics_match_detector_window(self):
        e=Engine();e.reset('4')
        for batch in range(1,5):
            keys=[f'{batch}:{n}' for n in range(4)]
            e.start_batch(batch,[{'key':k,'x':-32768,'y':-32768} for k in keys])
            e.measurement(keys,[0],[[float(n)] for n in range((batch-1)*4,batch*4)])
            e.finish_batch([{'key':k,'passed':True} for k in keys])
        curve=e.test_chart(0)
        self.assertEqual(len(curve['windows']),1)
        self.assertAlmostEqual(curve['windows'][0]['delta'],8/e.model['scale'][0])
        self.assertTrue(all(d['x'] is None for d in e.snapshot()['devices']))

    def test_mean_and_sample_std_not_median_or_mad(self):
        before=np.array([0.,0.,0.,0.,0.,0.,0.,8.])
        after=before*2
        stats=window_statistics(np.concatenate([before,after]),1.)
        self.assertEqual(stats['delta'],1.)
        self.assertAlmostEqual(stats['spread'],2.)
        self.assertAlmostEqual(stats['before_std'],np.std(before,ddof=1))
        self.assertNotEqual(stats['delta'],np.median(after)-np.median(before))

    def test_strict_label_evaluation_counts_extras_and_misses(self):
        result=compare_labels('Mean Trend Up',['Mean Trend Up','Stdev Trend Up'])
        self.assertFalse(result['exact_match'])
        self.assertEqual(result['extra_labels'],['Stdev Trend Up'])
        result=compare_labels('Stdev Trend Down',['Normal'])
        self.assertEqual(result['missed_labels'],['Stdev Trend Down'])
        self.assertTrue(compare_labels('Normal',['Normal'])['exact_match'])
        self.assertIsNone(compare_labels('Site unbalance',['Normal'],False)['exact_match'])

    def test_auxiliary_warning_has_no_formal_label(self):
        e=Engine();e.reset('4');e.start_batch(1,[{'key':'a'}])
        value=e.model['center'][0]+2*e.model['point'][0]*e.model['scale'][0]
        e.measurement(['a'],[0],[[value]])
        self.assertIsNone(e.snapshot()['alerts'][0]['formal_label'])
        self.assertEqual(e.snapshot()['predicted_labels'],[])
        self.assertEqual(e.snapshot()['formal_alert_count'],0)

    def test_formal_trend_requires_same_tests_in_two_windows(self):
        e=Engine();e.reset('4')
        e.model['scale'][:5]=1
        e.model['up'][:5]=1
        e.model['active'][:5]=True
        for batch,value in enumerate([0.,0.,2.,4.,8.],1):
            keys=[f'{batch}:{i}' for i in range(4)]
            e.start_batch(batch,[{'key':k} for k in keys])
            e.measurement(keys,list(range(5)),np.full((4,5),value))
            if batch==4:
                self.assertNotIn('mean_trend_up',e.latest)
            e.finish_batch([{'key':k,'passed':True} for k in keys])
        self.assertEqual(e.latest['mean_trend_up']['first_batch'],5)


if __name__=='__main__': unittest.main()
