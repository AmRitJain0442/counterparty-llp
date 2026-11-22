"""Exercise both HTTP hops with a real HMAC and a locally signed Google-format JWT."""

import base64
import hashlib
import hmac
import json
import os
import re
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from google.auth import crypt, jwt

from backend import storage, watch


class WatchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        settings = {
            "LEDGER_BACKEND": "sqlite", "SQLITE_PATH": str(Path(tmp.name) / "ledger.sqlite"),
            "WATCH_TRANSPORT": "local", "WATCH_WEBHOOK_SECRET": "test-signing-key",
            "PUBSUB_TOPIC": "projects/demo-infra/topics/watch",
            "PUBSUB_SUBSCRIPTION": "projects/demo-infra/subscriptions/watch-push",
            "PUBSUB_PUSH_SERVICE_ACCOUNT": "push@demo-infra.iam.gserviceaccount.com",
            "PUBSUB_PUSH_AUDIENCE": "https://watch.example.test/watch/pubsub",
        }
        if os.getenv("COUNTERPARTY_TEST_FIRESTORE") == "1":
            self.assertRegex(os.environ["FIRESTORE_EMULATOR_HOST"], r"^(localhost|127\.0\.0\.1):[0-9]+$")
            settings.update(LEDGER_BACKEND="firestore", GOOGLE_CLOUD_PROJECT="demo-" + uuid4().hex[:12],
                            FIRESTORE_DATABASE="(default)")
        env = patch.dict(os.environ, settings)
        env.start()
        self.addCleanup(env.stop)
        self.client = TestClient(watch.app)
        self.addCleanup(self.client.close)
        self.case = {"id": "first/1", "verdict": "HELD", "flow": [[1, 2]]}
        storage.save_case(self.case)
        storage.save_case({"id": "second"})
        storage.bind_watch(17, self.case["id"])
        self.body = {
            "metadata": {"kind": "entity", "dataset": "company", "watch_id": 17,
                         "notification_id": "ntf_123", "delivered_at": "2026-01-02T00:15:00Z"},
            "results": [{"changes": [{"field": "headcount.total"}], "record": {"private": "evidence"}}],
            "case_id": "second",  # The signed payload still cannot choose its case.
        }

    def webhook(self, *, offset=0, tamper=False):
        raw = json.dumps(self.body).encode()
        stamp = str(int(time.time()) + offset)
        sig = hmac.new(b"test-signing-key", stamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
        return self.client.post("/watch/webhook", content=raw + (b" " if tamper else b""),
                                headers={"x-crustdata-signature": f"t={stamp},v1={sig}"})

    def test_auth_baseline_and_binding(self):
        self.assertEqual(self.client.post("/watch/webhook", json=self.body).status_code, 401)
        self.assertEqual(self.webhook(offset=-310).status_code, 401)
        self.assertEqual(self.webhook(tamper=True).status_code, 401)
        self.body["metadata"]["test"] = True
        self.assertEqual(self.webhook().json(), {"status": "ignored"})
        del self.body["metadata"]["test"]
        self.body["metadata"]["watch_id"] = 18
        self.assertEqual(self.webhook().status_code, 409)
        self.body["results"][0]["changes"] = []
        self.assertEqual(self.webhook().json(), {"status": "ignored"})
        storage.bind_watch(17, self.case["id"])
        with self.assertRaises(ValueError):
            storage.bind_watch(17, "second")
        self.assertEqual(storage.get_case(self.case["id"]), self.case)
        self.assertIsNone(storage.get_case("missing"))
        self.assertEqual([c["id"] for c in storage.list_cases()], ["second", "first/1"])

    def test_reopen_and_concurrent_redelivery(self):
        self.assertEqual(self.webhook().json(), {"status": "reopened"})
        self.assertEqual(self.webhook().json(), {"status": "duplicate"})
        self.body["metadata"].update(notification_id="ntf_100", delivered_at="2026-01-01T00:15:00Z")
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.webhook(), range(8)))
        # Firestore can exhaust its transaction attempts under contention. Retry every NACK.
        for i, response in enumerate(results):
            if response.status_code == 503:
                results[i] = self.webhook()
        self.assertTrue(all(r.status_code == 202 for r in results))
        self.assertEqual(sum(r.json()["status"] == "reopened" for r in results), 1)
        saved = storage.save_case(self.case)
        review = saved.pop("watch_review")
        self.assertEqual(review["event_count"], 2)
        self.assertEqual(review["as_of"], "2026-01-02T00:15:00.000000+00:00")
        self.assertEqual(saved, self.case)
        self.assertNotIn("watch_review", storage.get_case("second"))

    def test_publish_retry_and_authenticated_push(self):
        os.environ["WATCH_TRANSPORT"] = "pubsub"
        publisher = Mock()
        publisher.publish.return_value.result.side_effect = [TimeoutError(), "message-1"]
        with patch.object(watch, "_publisher", return_value=publisher):
            self.assertEqual(self.webhook().status_code, 503)
            [staged] = storage.pending_watch_events()
            self.assertEqual(self.webhook().json(), {"status": "queued"})
            self.assertEqual(self.webhook().json(), {"status": "duplicate"})
        self.assertEqual(storage.pending_watch_events(), [])
        self.assertNotIn("watch_review", storage.get_case(self.case["id"]))
        for call in publisher.publish.call_args_list:
            self.assertEqual(call.args, (os.environ["PUBSUB_TOPIC"], staged.encode()))
        self.assertTrue(re.fullmatch("[0-9a-f]{64}", staged))
        envelope = {"message": {"data": base64.b64encode(staged.encode()).decode()},
                    "subscription": os.environ["PUBSUB_SUBSCRIPTION"]}
        push = "/watch/pubsub"
        self.assertEqual(self.client.post(push, json=envelope).status_code, 401)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(timezone.utc)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "local test issuer")])
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(1).not_valid_before(now - timedelta(hours=1))
                .not_valid_after(now + timedelta(hours=1)).sign(key, hashes.SHA256()))
        certs = {"test-key": cert.public_bytes(serialization.Encoding.PEM).decode()}
        response = SimpleNamespace(status=200, data=json.dumps(certs).encode())
        claims = {"iat": int(now.timestamp()), "exp": int(now.timestamp()) + 600,
                  "iss": "https://accounts.google.com", "aud": os.environ["PUBSUB_PUSH_AUDIENCE"],
                  "email": os.environ["PUBSUB_PUSH_SERVICE_ACCOUNT"], "email_verified": True}

        def headers(**overrides):
            token = jwt.encode(crypt.RSASigner(key, key_id="test-key"), {**claims, **overrides}).decode()
            return {"Authorization": "Bearer " + token}

        with patch("google.auth.transport.requests.Request", return_value=Mock(return_value=response)):
            for change, code in [({"aud": "other"}, 401), ({"iss": "other"}, 401),
                                 ({"email": "other"}, 403), ({"email_verified": False}, 403)]:
                self.assertEqual(self.client.post(push, json=envelope, headers=headers(**change)).status_code, code)
            other = {**envelope, "subscription": "projects/demo-infra/subscriptions/other"}
            self.assertEqual(self.client.post(push, json=other, headers=headers()).status_code, 403)
            for _ in range(2):
                self.assertEqual(self.client.post(push, json=envelope, headers=headers()).status_code, 204)
        self.assertEqual(storage.get_case(self.case["id"])["watch_review"]["event_count"], 1)
        storage.mark_watch_published(staged)
        self.assertFalse(storage.reopen_from_watch(staged))
