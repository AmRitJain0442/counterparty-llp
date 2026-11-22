"""Show real run counters for one configured company watch without exposing delivery settings."""
import os
import re
from datetime import datetime, timezone

import requests

from .providers import throttle


def watch_history():
    watch_id = os.getenv("CRUSTDATA_WATCH_ID", "")
    token = os.getenv("CRUSTDATA_API_KEY")
    view = {"as_of": datetime.now(timezone.utc).isoformat(), "mode": "LIVE",
            "status": "unconfigured", "runs": []}
    if not token or not re.fullmatch(r"[1-9]\d{0,18}", watch_id):
        return view
    base = f"https://api.crustdata.com/watch/company/{watch_id}"
    headers = {"Authorization": f"Bearer {token}", "x-api-version": "2025-11-01"}
    try:
        with requests.Session() as session:
            throttle("crustdata:overall", .6)
            current = session.get(base, headers=headers, timeout=10, allow_redirects=False)
            current.raise_for_status()
            config = current.json()
            throttle("crustdata:overall", .6)
            history = session.get(base + "/runs", params={"limit": 12}, headers=headers, timeout=10,
                                  allow_redirects=False)
            history.raise_for_status()
            rows = history.json()["runs"]
        view.update(status=config["status"], watch_id=watch_id, domains=config.get("entities", {}).get("domains", []),
                    refresh_days=config.get("config", {}).get("refresh_frequency_days"),
                    expires_at=config.get("config", {}).get("expires_at"),
                    runs=[{k: row.get(k) for k in ("id", "started_at", "completed_at", "status", "credits_deducted",
                                                   "records_searched", "records_matched")} for row in rows])
    except (requests.RequestException, ValueError, KeyError):
        view["status"] = "unavailable"
    return view
