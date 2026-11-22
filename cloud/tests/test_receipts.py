import base64
import copy
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import receipts, storage


class ReceiptTests(unittest.TestCase):
    def test_private_salt_and_exact_finding(self):
        finding = {"as_of": "2026-01-01", "evidence": [{"value": "private"}]}
        with patch.dict(os.environ, REKOR_ENABLED="1"), patch.object(receipts, "_cosign") as cosign:
            receipt = receipts.create_receipt(finding)
            self.assertNotEqual(receipt["digest"], receipts.create_receipt(finding)["digest"])
            decorated = {**finding, "receipt_record": receipt, "watch_review": {"status": "REOPENED"}}
            self.assertEqual(receipts.verify_receipt(decorated, receipt), "LOCAL_ONLY")
            with self.assertRaises(receipts.ReceiptError):
                receipts.verify_receipt(finding, receipt, require_rekor=True)
            with self.assertRaises(receipts.ReceiptError):
                receipts.verify_receipt({**finding, "as_of": "2027-01-01"}, receipt)
            with self.assertRaises(receipts.ReceiptError):
                receipts.verify_receipt({**decorated, "receipt": "replaced"}, receipt)
            cosign.assert_not_called()

    def test_unconfigured_publication_fails_before_signing(self):
        with patch.dict(os.environ, REKOR_ENABLED=""), patch.object(receipts, "_cosign") as cosign:
            with self.assertRaises(receipts.ReceiptError):
                receipts.create_receipt({"id": "test"}, publish=True)
            cosign.assert_not_called()

    def test_signer_receives_only_commitment_and_incomplete_proof_fails(self):
        finding = {"id": "private-id", "evidence": [{"detail": "confidential observation"}]}
        receipt = receipts.create_receipt(finding)

        def sign(*args):
            self.assertEqual(args[0], "sign-blob")
            self.assertEqual(Path(args[-1]).read_bytes(), bytes.fromhex(receipt["digest"]))
            self.assertNotIn("private-id", str(args))
            self.assertNotIn(receipt["nonce"], str(args))
            Path(args[args.index("--bundle") + 1]).write_text("{}", encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test-trust"
            path.touch()
            settings = dict(REKOR_ENABLED="1", REKOR_SIGNING_KEY="test-key", REKOR_PUBLIC_KEY=str(path),
                            REKOR_TRUSTED_ROOT=str(path), REKOR_SIGNING_CONFIG="")
            with patch.dict(os.environ, settings), patch.object(receipts, "_cosign", side_effect=sign) as signer:
                with self.assertRaises(receipts.ReceiptError):
                    receipts.publish_receipt(finding, receipt)
                signer.assert_called_once()

    def test_compare_snapshot_when_attaching(self):
        case = {"id": "sample", "verdict": "SIGNED"}
        receipt = receipts.create_receipt(case)
        case.update(receipt=receipt["digest"], receipt_record=receipt)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, LEDGER_BACKEND="sqlite",
                                                              SQLITE_PATH=str(Path(tmp) / "test.sqlite")):
            storage.save_case(case)
            storage.bind_watch(1, "sample")
            event = storage.stage_watch_event(1, "ntf_1", "2026-01-01T00:00:00.000000+00:00")
            storage.reopen_from_watch(event["event_id"])
            storage.attach_receipt(case, receipt)
            self.assertEqual(storage.get_case("sample")["watch_review"]["event_count"], 1)
            storage.save_case({**case, "summary": "human correction"})
            with self.assertRaises(ValueError):
                storage.attach_receipt(case, receipt)

    def test_offline_signature_timestamp_and_inclusion(self):
        # Public materials made with Cosign 3.1.4, an ephemeral loopback log and an RFC 3161 TSA.
        tool = os.getenv("REKOR_COSIGN") or shutil.which("cosign")
        if not tool:
            self.skipTest("Set REKOR_COSIGN to a Cosign 3 executable for offline bundle verification")
        fixture = json.loads((Path(__file__).parent / "fixtures/local-rekor.json").read_text(encoding="utf-8"))
        finding = fixture["finding"]
        receipt = fixture["receipt"]
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / "operator.pub"
            root = Path(tmp) / "trusted_root.json"
            key.write_text(fixture["public_key"], encoding="utf-8")
            root.write_text(json.dumps(fixture["trusted_root"]), encoding="utf-8")
            with patch.dict(os.environ, REKOR_COSIGN=tool, REKOR_PUBLIC_KEY=str(key), REKOR_TRUSTED_ROOT=str(root)):
                self.assertEqual(receipts.verify_receipt(finding, receipt, require_rekor=True), "REKOR_VERIFIED")
                for mutation in ("signature", "proof", "checkpoint", "timestamp"):
                    with self.subTest(mutation=mutation):
                        changed = copy.deepcopy(receipt)
                        bundle = changed["bundle"]
                        material = bundle["verificationMaterial"]
                        proof = material["tlogEntries"][0]["inclusionProof"]
                        if mutation == "signature":
                            bundle["messageSignature"]["signature"] = base64.b64encode(b"test").decode()
                        elif mutation == "proof":
                            proof["rootHash"] = base64.b64encode(bytes(32)).decode()
                        elif mutation == "checkpoint":
                            proof["checkpoint"]["envelope"] = "modified"
                        else:
                            material.pop("timestampVerificationData")
                        with self.assertRaises(receipts.ReceiptError):
                            receipts.verify_receipt(finding, changed, require_rekor=True)
