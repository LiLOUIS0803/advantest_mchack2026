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
                if engine.completed<16:
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
        self.assertIsNone(engine.predicted_label)
        self.assertEqual(engine.classification_reason,'missing_measurements_or_site')


if __name__=='__main__':unittest.main()
