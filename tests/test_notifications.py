import tempfile
from pathlib import Path
import unittest
from realtime.notifications import NotificationStore, NotificationPolicy


class NotificationTests(unittest.TestCase):
    def test_persistence_deduplication_and_frozen_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'inbox.db';store=NotificationStore(path);policy=NotificationPolicy(store)
            s={'predicted_label':'Mean Trend Up','completed':24,'ended':False,'wafer':'14','lot':'A','mode':'replay','failed':2}
            for _ in range(2):policy.observe({'type':'test_end'},s)
            self.assertEqual(store.unread(),0)
            policy.observe({'type':'test_end'},s)
            s['failed']=10
            for _ in range(4):policy.observe({'type':'test_end'},s)
            policy.observe({'type':'wafer_end'},s)
            self.assertEqual(store.unread(),1)
            reopened=NotificationStore(path);item=reopened.list()[0]
            self.assertEqual(reopened.get(item['id'])['report']['state']['failed'],2)
            reopened.update(item['id'],'acknowledged');self.assertEqual(reopened.unread(),0)
            reopened.update(item['id'],'resolved')
            self.assertEqual(len(reopened.get(item['id'])['actions']),2)
            with self.assertRaises(ValueError):reopened.update(item['id'],'new')
            self.assertEqual(len(reopened.list('W14','resolved')),1)

    def test_normal_resets_streak_and_new_run_can_notify(self):
        with tempfile.TemporaryDirectory() as directory:
            store=NotificationStore(Path(directory)/'db');policy=NotificationPolicy(store)
            s={'predicted_label':'Normal','completed':24,'ended':False,'wafer':'1','lot':'A'}
            for label in ['Site unbalance','Site unbalance','Normal','Site unbalance']:
                s['predicted_label']=label;policy.observe({'type':'test_end'},s)
            self.assertEqual(store.unread(),0)
            policy.observe({'type':'wafer_end'},s);self.assertEqual(store.unread(),1)
            policy.observe({'type':'wafer_start'},s);policy.observe({'type':'wafer_end'},s)
            self.assertEqual(store.unread(),2)
