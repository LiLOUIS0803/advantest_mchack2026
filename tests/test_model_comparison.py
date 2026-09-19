import unittest
from types import SimpleNamespace

import numpy as np

from hackathon.app.hierarchical import DieBaseline, HierarchicalAnalyzer
from realtime.compare_models import die_diagnosis, record_first


class ComparisonTests(unittest.TestCase):
    def analyzer(self):
        return HierarchicalAnalyzer(DieBaseline.from_arrays(
            [str(i) for i in range(12)], np.zeros(12), np.ones(12)))

    def test_single_site_does_not_override_direction_and_real_pids_survive(self):
        analyzer = self.analyzer()
        for pid in (101, 207, 309):
            analyzer.add_die({'pid': pid, 'site': 4}, {str(i): 8. for i in range(12)})
        result = die_diagnosis(analyzer)
        self.assertEqual(result['kind'], 'mean_trend_up')
        self.assertEqual(result['affected_pids'], [101, 207, 309])

    def test_mixed_signs_and_minimum_evidence(self):
        analyzer = self.analyzer()
        for pid in (1, 2):
            analyzer.add_die({'pid': pid}, {str(i): 8.*(-1)**i for i in range(12)})
        self.assertIsNone(die_diagnosis(analyzer))
        analyzer.add_die({'pid': 3}, {str(i): 8.*(-1)**i for i in range(12)})
        self.assertEqual(die_diagnosis(analyzer)['kind'], 'stdev_trend_up')

    def test_first_alert_and_unstarted_bound_are_not_rewritten(self):
        engine = SimpleNamespace(batch=5, stage='measurement', completed=16,
                                 total_devices=80, current={'a': 1, 'b': 1, 'c': 1, 'd': 1})
        log = {}
        record_first(log, 'Mean Trend Up', 42, engine)
        engine.completed, engine.batch = 40, 11
        record_first(log, 'Mean Trend Up', 99, engine)
        self.assertEqual(log['Mean Trend Up']['event_index'], 42)
        self.assertEqual(log['Mean Trend Up']['potential_unstarted_devices'], 60)
        self.assertIsNone(log['Mean Trend Up']['estimated_saved_seconds'])


if __name__ == '__main__':
    unittest.main()
