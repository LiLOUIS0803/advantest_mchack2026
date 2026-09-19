"""Regression coverage for SQLite bindings that require string filenames."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from realtime.hc_server import Store


class HCCompatibilityTests(unittest.TestCase):
    def test_store_uses_string_database_path(self):
        connect = sqlite3.connect

        def legacy_connect(filename, **kwargs):
            self.assertIsInstance(filename, str)
            return connect(filename, **kwargs)

        with tempfile.TemporaryDirectory() as folder:
            with patch('realtime.hc_server.sqlite3.connect', side_effect=legacy_connect):
                store = Store(Path(folder) / 'hc.sqlite3')
                self.assertIsNone(store.state())
                self.assertEqual(store.reports()['items'], [])
