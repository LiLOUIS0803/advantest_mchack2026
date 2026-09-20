import unittest
from unittest.mock import patch
from realtime.classifier_engine import ClassifierEngine
from realtime.data import manifest
from realtime.replay import events, apply_event


class ClassifierIntegrationTests(unittest.TestCase):
    def test_single_label_site_enabled_without_truth_lookup(self):
        entry=next(e for e in manifest() if int(e['wafer'])==1)
        engine=ClassifierEngine()
        with patch('realtime.wafer_classifier.official_labels',side_effect=AssertionError('Truth accessed')):
            for event in events(entry):
                previous=engine.predicted_label
                apply_event(engine,event)
                s=engine.snapshot()
                self.assertLessEqual(len(s['predicted_labels']),1)
                if engine.completed==0:
                    self.assertIsNone(s['predicted_label'])
                    self.assertIsNone(s['classification_confidence'])
                if s['predicted_label'] is not None:
                    self.assertGreaterEqual(s['classification_confidence']['score'],0)
                    self.assertLessEqual(s['classification_confidence']['score'],1)
                    self.assertFalse(s['classification_confidence']['calibrated'])
                if event['type']=='measurement':self.assertEqual(previous,engine.predicted_label)
        self.assertEqual(engine.predicted_label,'Site unbalance')
        self.assertEqual(s['passed']+s['failed'],80)
        self.assertTrue(all(a['formal_label'] is None for a in s['alerts']))
        engine.reset('4')
        self.assertIsNone(engine.predicted_label)
        self.assertIsNone(engine.classification_confidence)
        self.assertEqual(engine.classification_history,[])

    def test_incomplete_measurements_do_not_get_filled_with_normal_values(self):
        engine=ClassifierEngine();engine.reset('4')
        for batch in range(4):
            keys=[f'{batch}:{i}' for i in range(4)]
            engine.start_batch(batch+1,[{'key':k,'site':i+1} for i,k in enumerate(keys)])
            engine.finish_batch([{'key':k,'passed':True} for k in keys])
        self.assertIn(engine.predicted_label,engine.class_labels)
        self.assertEqual(engine.classification_reason,'partial_data')
        self.assertTrue(engine.classification_confidence['partial_data'])
        self.assertFalse(engine.classification_confidence['calibrated'])
        self.assertGreater(len(engine.classification_confidence['fallback_features']),0)
        q=engine.snapshot()['data_quality']
        self.assertEqual(q['completed_dies'],16)
        self.assertEqual(q['missing_values'],16*len(engine.columns))
        self.assertEqual(q['affected_dies'],16)
        self.assertEqual(q['measurement_completeness'],0)
        self.assertEqual(q['missing_test_count'],len(engine.columns))
        self.assertEqual(q['missing_tests'][0],{'test':engine.columns[0],'missing_dies':16})
        engine.reset('5')
        self.assertEqual(engine.snapshot()['data_quality']['missing_values'],0)

    def test_first_completed_die_without_site_has_provisional_prediction(self):
        engine=ClassifierEngine();engine.reset('4')
        engine.start_batch(1,[{'key':'a'}])
        engine.finish_batch([{'key':'a','passed':False}])
        self.assertIn(engine.predicted_label,engine.class_labels)
        self.assertEqual(engine.classification_confidence['observed_features'],1)
        self.assertEqual(engine.data_quality['missing_sites'],1)
        self.assertGreaterEqual(engine.classification_confidence['score'],0)
        self.assertLessEqual(engine.classification_confidence['score'],1)

    def test_partial_features_match_complete_features_when_observed(self):
        import numpy as np
        from realtime.classifier_features import extract,extract_partial
        engine=ClassifierEngine();rng=np.random.default_rng(17)
        x=rng.normal(size=(20,len(engine.columns)))
        rows=[['','','',i%4+1,'','',8 if i%3==0 else 0] for i in range(20)]
        original=extract(engine.columns,rows,x);partial=extract_partial(engine.columns,rows,x)
        for k in original:self.assertAlmostEqual(original[k],partial[k],places=9)
        x[:,0]=np.nan
        self.assertTrue(all(np.isfinite(v) for v in extract_partial(engine.columns,rows,x).values()))


if __name__=='__main__':unittest.main()
