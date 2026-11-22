"""Small projected account price card, cached without personal data."""
import os
import threading
import time
from datetime import datetime, timezone

import requests

from .providers import OPERATIONS, throttle

_lock = threading.Lock()
_cached = None
_expires = 0.0


def capabilities():
    global _cached, _expires
    with _lock:
        if _cached and time.monotonic() < _expires:
            return _cached
        card = {
            "as_of": datetime.now(timezone.utc).isoformat(), "status": "unconfigured",
            "credits": None, "endpoints": [],
            "vertex_configured": bool(os.getenv("GOOGLE_CLOUD_PROJECT")),
        }
        token = os.getenv("CRUSTDATA_API_KEY")
        if token:
            headers = {"Authorization": f"Bearer {token}", "x-api-version": "2025-11-01"}
            try:
                for op in ("account_endpoints", "account_credits"):
                    throttle("crustdata" + op, 12)
                    throttle("crustdata:overall", .6)
                    url = "https://api.crustdata.com" + OPERATIONS[op]
                    response = requests.get(url, headers=headers, timeout=12, allow_redirects=False)
                    response.raise_for_status()
                    data = response.json()
                    if op == "account_endpoints":
                        paths = set(OPERATIONS.values())
                        card["endpoints"] = [{k: row.get(k) for k in
                                              ("path", "status", "effective_rate_limit_rpm", "base_credits")}
                                             for row in data["endpoints"] if row["path"] in paths]
                    else:
                        card["credits"] = data["account"]["credits"]
                card["status"] = "available"
            except (requests.RequestException, ValueError, KeyError):
                card["status"] = "unavailable"
        _cached = card
        _expires = time.monotonic() + (120 if card["status"] == "available" else 15)
        return card
