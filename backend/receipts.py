"""Private case commitments and explicitly requested Sigstore transparency receipts."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import tempfile
from pathlib import Path


class ReceiptError(ValueError):
    """The requested level of receipt assurance could not be established."""


def _digest(finding, nonce):
    if not isinstance(finding, dict):
        raise ReceiptError("A finding must be a JSON object")
    # These ledger decorations may be attached after a decision has been sealed.
    payload = {k: v for k, v in finding.items() if k not in ("receipt", "receipt_record", "watch_review")}
    data = json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(b"counterparty-finding-v1\0" + nonce + data.encode("utf-8")).hexdigest()


def _check_commitment(finding, receipt):
    if not isinstance(receipt, dict) or receipt.get("version") != 1:
        raise ReceiptError("Unknown receipt format")
    for field in ("nonce", "digest"):
        value = receipt.get(field)
        if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
            raise ReceiptError(f"Invalid receipt {field}")
    digest = _digest(finding, bytes.fromhex(receipt["nonce"]))
    if not hmac.compare_digest(digest, receipt["digest"]):
        raise ReceiptError("Finding does not match the receipt")
    return bytes.fromhex(digest)


def _setting(name):
    value = os.getenv(name)
    if not value:
        raise ReceiptError(f"Configure {name} for Rekor receipts")
    return value


def _trusted_file(name):
    path = Path(_setting(name)).expanduser().resolve()
    if not path.is_file():
        raise ReceiptError(f"Missing {name} file")
    return str(path)


def _cosign(*arguments):
    # Only operator configuration and private temporary paths reach the command line.
    try:
        subprocess.run(
            [os.environ.get("REKOR_COSIGN", "cosign"), *map(str, arguments)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=90, check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        # Cosign diagnostics can contain service or key references.
        raise ReceiptError(f"Cosign {arguments[0]} failed ({type(exc).__name__})") from None


def _verify_bundle(artifact, bundle_path, bundle, public_key, trust_root):
    if not isinstance(bundle, dict) or not isinstance(bundle.get("messageSignature"), dict):
        raise ReceiptError("Expected a Sigstore blob signature")
    material = bundle.get("verificationMaterial")
    if not isinstance(material, dict) or not material.get("publicKey"):
        raise ReceiptError("Expected a dedicated signing key")
    entries = material.get("tlogEntries")
    if not isinstance(entries, list) or not entries:
        raise ReceiptError("Missing Rekor inclusion proof")
    for entry in entries:
        proof = entry.get("inclusionProof") if isinstance(entry, dict) else None
        if not isinstance(proof, dict) or not proof.get("checkpoint"):
            raise ReceiptError("Missing Rekor checkpoint")
    # Cosign verifies the artifact signature, log entry, Merkle proof, signed
    # checkpoint and RFC 3161 time against independently supplied trust material.
    _cosign("verify-blob", "--offline", "--insecure-ignore-tlog=false", "--use-signed-timestamps",
            "--key", public_key, "--trusted-root", trust_root, "--bundle", bundle_path, artifact)


def verify_receipt(finding: dict, receipt: dict, *, require_rekor: bool = False) -> str:
    """Return LOCAL_ONLY or REKOR_VERIFIED after verification, or raise ReceiptError."""
    commitment = _check_commitment(finding, receipt)
    if receipt.get("status") == "LOCAL_ONLY" and not require_rekor and "bundle" not in receipt:
        return "LOCAL_ONLY"
    if receipt.get("status") != "REKOR_VERIFIED":
        raise ReceiptError("A verified Rekor receipt is required")
    public_key = _trusted_file("REKOR_PUBLIC_KEY")
    trust_root = _trusted_file("REKOR_TRUSTED_ROOT")
    with tempfile.TemporaryDirectory() as tmp:
        artifact = Path(tmp) / "commitment"
        artifact.write_bytes(commitment)
        bundle_path = Path(tmp) / "bundle.json"
        bundle = receipt.get("bundle")
        bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
        _verify_bundle(artifact, bundle_path, bundle, public_key, trust_root)
    return "REKOR_VERIFIED"


def publish_receipt(finding: dict, receipt: dict) -> dict:
    """Publish only a private receipt's salted commitment and verify the returned bundle."""
    if os.getenv("REKOR_ENABLED") != "1":
        raise ReceiptError("Publication requires REKOR_ENABLED=1")
    if verify_receipt(finding, receipt) == "REKOR_VERIFIED":
        return receipt
    key = _setting("REKOR_SIGNING_KEY")
    public_key = _trusted_file("REKOR_PUBLIC_KEY")
    trust_root = _trusted_file("REKOR_TRUSTED_ROOT")
    config = ["--signing-config", _trusted_file("REKOR_SIGNING_CONFIG")] if os.getenv("REKOR_SIGNING_CONFIG") else []
    with tempfile.TemporaryDirectory() as tmp:
        artifact = Path(tmp) / "commitment"
        artifact.write_bytes(bytes.fromhex(receipt["digest"]))
        bundle_path = Path(tmp) / "bundle.json"
        _cosign("sign-blob", "--yes", "--key", key, "--trusted-root", trust_root,
                *config, "--bundle", bundle_path, artifact)
        try:
            bundle = json.loads(bundle_path.read_bytes())
        except (OSError, ValueError):
            raise ReceiptError("Cosign did not return a readable bundle") from None
        _verify_bundle(artifact, bundle_path, bundle, public_key, trust_root)
    return {**receipt, "status": "REKOR_VERIFIED", "bundle": bundle}


def create_receipt(finding: dict, *, publish: bool = False) -> dict:
    """Seal the exact finding. The default path uses only the Python standard library."""
    nonce = secrets.token_bytes(32)
    receipt = {"version": 1, "status": "LOCAL_ONLY", "nonce": nonce.hex(), "digest": _digest(finding, nonce)}
    return publish_receipt(finding, receipt) if publish else receipt


def _main():
    from . import storage

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    verify = sub.add_parser("verify", help="verify the stored receipt")
    verify.add_argument("case_id")
    verify.add_argument("--require-rekor", action="store_true")
    publish = sub.add_parser("publish", help="publish and attach a verified receipt for this case")
    publish.add_argument("case_id")
    args = parser.parse_args()
    case = storage.get_case(args.case_id)
    if case is None or not isinstance(case.get("receipt_record"), dict):
        parser.exit(1, "No stored receipt for that case\n")
    try:
        if args.action == "publish":
            receipt = publish_receipt(case, case["receipt_record"])
            storage.attach_receipt(case, receipt)
            print(receipt["status"])
        else:
            print(verify_receipt(case, case["receipt_record"], require_rekor=args.require_rekor))
    except (ReceiptError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    _main()
