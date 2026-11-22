import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend import storage


class BatchCacheTests(unittest.TestCase):
    def test_local_expiry_and_observation_date(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "SQLITE_PATH": str(Path(tmp) / "cache.sqlite"), "LEDGER_BACKEND": "sqlite",
            "BIGQUERY_CACHE_TABLE": "",
        }):
            with patch("backend.storage.time.time", return_value=100):
                storage.put_cached_batch("scope-a", [1], as_of="2026-01-01", ttl_seconds=2)
                self.assertEqual(storage.get_cached_batch("scope-a"),
                                 {"mode": "CACHED", "as_of": "2026-01-01", "data": [1]})
                self.assertIsNone(storage.get_cached_batch("scope-b"))
            with patch("backend.storage.time.time", return_value=102):
                self.assertIsNone(storage.get_cached_batch("scope-a"))

    def test_cloud_queries_keep_values_in_parameters(self):
        client = Mock()
        table = "test-infra.counterparty.batch_cache"
        with patch.dict(os.environ, BIGQUERY_CACHE_TABLE=table), patch.object(storage, "_bigquery", return_value=client):
            storage.put_cached_batch("private-scope", {"person": "private-value"}, as_of="2025-04-02", ttl_seconds=60)
            sql = client.query.call_args.args[0]
            params = client.query.call_args.kwargs["job_config"].query_parameters
            self.assertNotIn("private", sql)
            self.assertNotIn("private-scope", [p.value for p in params])
            self.assertIn('"private-value"', next(p.value for p in params if p.name == "data"))
            client.query.return_value.result.return_value = [("2025-04-02", '{"person":"private-value"}')]
            self.assertEqual(storage.get_cached_batch("private-scope")["mode"], "CACHED")
            self.assertIn("expires_at > CURRENT_TIMESTAMP()", client.query.call_args.args[0])
            os.environ["BIGQUERY_CACHE_TABLE"] = "invalid table"
            with self.assertRaises(ValueError):
                storage.get_cached_batch("private-scope")

    def test_cloud_cache_disabled_without_table(self):
        with patch.dict(os.environ, LEDGER_BACKEND="firestore", BIGQUERY_CACHE_TABLE=""):
            storage.put_cached_batch("scope", [], as_of="2026-01-01", ttl_seconds=60)
            self.assertIsNone(storage.get_cached_batch("scope"))
