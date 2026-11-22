"""Authenticated Crustdata ingress, Pub/Sub push consumer and local outbox recovery."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from . import storage


router = APIRouter(prefix="/watch", tags=["watch"])
log = logging.getLogger(__name__)
SIGNATURE = re.compile(r"t=([0-9]{1,12}),v1=([0-9a-fA-F]{64})")
EVENT_ID = re.compile(r"[0-9a-f]{64}")


def _setting(name):
    value = os.environ.get(name)
    if not value:
        raise HTTPException(503, f"Configure {name} for watch delivery")
    return value


async def _body(request, limit):
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise HTTPException(413, "Watch request exceeds the size limit")
        body.extend(chunk)
    return bytes(body)


def _json_object(raw):
    try:
        value = json.loads(raw)
    except (ValueError, RecursionError):
        raise HTTPException(400, "Invalid JSON") from None
    if not isinstance(value, dict):
        raise HTTPException(422, "Expected a JSON object")
    return value


def _verify_webhook(raw, signature):
    # Crustdata uses the account API key as the HMAC secret.
    secret = _setting("WATCH_WEBHOOK_SECRET").encode()
    match = SIGNATURE.fullmatch(signature)
    if not match or abs(time.time() - int(match[1])) > 300:
        raise HTTPException(401, "Invalid or expired webhook signature")
    expected = hmac.new(secret, match[1].encode() + b"." + raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, match[2].lower()):
        raise HTTPException(401, "Invalid or expired webhook signature")


def _event_fields(body):
    meta = body.get("metadata")
    if not isinstance(meta, dict) or meta.get("kind") != "entity" or meta.get("dataset") not in ("company", "person"):
        raise HTTPException(422, "Expected a person or company entity watch")
    if meta.get("test") is True:
        return None
    delivery = meta.get("payload_delivery", {})
    if not isinstance(delivery, dict) or delivery.get("type", "inline") != "inline":
        raise HTTPException(422, "Configure the watch for inline delivery")
    results = body.get("results")
    if not isinstance(results, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("changes"), list) for item in results
    ):
        raise HTTPException(422, "Expected inline change sets")
    if not any(item["changes"] for item in results):
        return None  # Free baseline, including an empty result set.
    watch_id = meta.get("watch_id")
    if not re.fullmatch(r"[1-9][0-9]{0,19}", str(watch_id)):
        raise HTTPException(422, "Invalid watch id")
    notification_id = meta.get("notification_id")
    if not isinstance(notification_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,160}", notification_id):
        raise HTTPException(422, "Invalid notification id")
    try:
        timestamp = datetime.fromisoformat(str(meta.get("delivered_at")).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError
        delivered_at = timestamp.astimezone(timezone.utc).isoformat(timespec="microseconds")
    except (ValueError, OverflowError):
        raise HTTPException(422, "Expected a delivery time with a timezone") from None
    return watch_id, notification_id, delivered_at


@lru_cache(maxsize=1)
def _publisher():
    from google.cloud import pubsub_v1

    return pubsub_v1.PublisherClient()


def _dispatch(event_id):
    default = "pubsub" if os.getenv("LEDGER_BACKEND", "sqlite").lower() == "firestore" else "local"
    mode = os.environ.get("WATCH_TRANSPORT", default)
    if mode == "local":
        return "reopened" if storage.reopen_from_watch(event_id) else "duplicate"
    if mode != "pubsub":
        raise HTTPException(503, "WATCH_TRANSPORT must be local or pubsub")
    topic = _setting("PUBSUB_TOPIC")
    # Wait for the service ACK. A timeout leaves the row eligible for redrive.
    _publisher().publish(topic, event_id.encode("ascii")).result(timeout=15)
    storage.mark_watch_published(event_id)
    return "queued"


def _accept(fields):
    try:
        event = storage.stage_watch_event(*fields)
    except KeyError:
        raise HTTPException(409, "Bind this provider watch to its case first") from None
    except Exception as exc:
        log.warning("Watch staging unavailable (%s)", type(exc).__name__)
        raise HTTPException(503, "Ledger unavailable. Retry this notification") from None
    if event["state"] != "pending":
        return "duplicate"
    try:
        return _dispatch(event["event_id"])
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("Watch dispatch pending (%s)", type(exc).__name__)
        raise HTTPException(503, "Event saved. Delivery is pending") from None


@router.post("/webhook", status_code=202)
async def webhook(request: Request):
    raw = await _body(request, 2 * 1024 * 1024)
    _verify_webhook(raw, request.headers.get("x-crustdata-signature", ""))
    fields = _event_fields(_json_object(raw))
    if fields is None:
        return {"status": "ignored"}
    return {"status": await run_in_threadpool(_accept, fields)}


def _verify_push(authorization):
    audience = _setting("PUBSUB_PUSH_AUDIENCE")
    email = _setting("PUBSUB_PUSH_SERVICE_ACCOUNT")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 16384:
        raise HTTPException(401, "Google push ID token required")
    from google.auth.exceptions import GoogleAuthError, TransportError
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2.id_token import verify_oauth2_token

    try:
        claims = verify_oauth2_token(token, GoogleRequest(), audience=audience)
    except TransportError:
        raise HTTPException(503, "Google signing keys unavailable") from None
    except (ValueError, GoogleAuthError):
        raise HTTPException(401, "Invalid push ID token") from None
    if claims.get("email") != email or claims.get("email_verified") is not True:
        raise HTTPException(403, "Unexpected push service account")


@router.post("/pubsub", status_code=204, response_class=Response)
async def pubsub(request: Request):
    await run_in_threadpool(_verify_push, request.headers.get("authorization", ""))
    envelope = _json_object(await _body(request, 16 * 1024))
    if envelope.get("subscription") != _setting("PUBSUB_SUBSCRIPTION"):
        raise HTTPException(403, "Unexpected push subscription")
    message = envelope.get("message")
    try:
        event_id = base64.b64decode(message["data"], validate=True).decode("ascii")
        if not EVENT_ID.fullmatch(event_id):
            raise ValueError
    except (KeyError, TypeError, ValueError, binascii.Error):
        raise HTTPException(422, "Expected a wrapped watch event id") from None
    try:
        await run_in_threadpool(storage.reopen_from_watch, event_id)
    except KeyError:
        raise HTTPException(404, "Staged watch event unavailable") from None
    except Exception as exc:
        log.warning("Watch update unavailable (%s)", type(exc).__name__)
        raise HTTPException(503, "Ledger unavailable. Retry this event") from None
    return Response(status_code=204)


# Separate public callback target. The case API can retain its own ingress policy.
app = FastAPI(title="Counterparty watch", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(router)


def _main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    bind = sub.add_parser("bind", help="bind a provider-issued watch to its existing case")
    bind.add_argument("watch_id")
    bind.add_argument("case_id")
    drain = sub.add_parser("drain", help="retry a bounded batch of pending events")
    drain.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if args.command == "bind":
        storage.bind_watch(args.watch_id, args.case_id)
    else:
        events = storage.pending_watch_events(args.limit)
        for event_id in events:
            _dispatch(event_id)
        print(f"Dispatched {len(events)} pending event(s)")


if __name__ == "__main__":
    _main()
