"""Resolve optional public identifiers before collecting independent evidence."""
import os
import re
import time
from threading import Lock

import requests

from .progress import report

_tickers = {}
_loaded = 0.0
_ticker_lock = Lock()


def _normal(name):
    return " ".join(re.findall(r"[^\W_]+", str(name).casefold()))


def _sec_id(subject, user_agent):
    global _tickers, _loaded
    with _ticker_lock:
        if time.monotonic() - _loaded >= 86400 or not _tickers:
            response = requests.get("https://www.sec.gov/files/company_tickers.json",
                                    headers={"User-Agent": user_agent}, timeout=8)
            response.raise_for_status()
            _tickers = response.json()
            _loaded = time.monotonic()
        matches = [row["cik_str"] for row in _tickers.values()
                   if _normal(subject) in (_normal(row["ticker"]), _normal(row["title"]))]
    if len(set(matches)) == 1:
        return str(matches[0])
    return None


def resolve_public_ids(desk, subject, inputs):
    resolved = dict(inputs)
    if desk == "company" and not inputs.get("cik") and os.getenv("SEC_USER_AGENT"):
        try:
            cik = _sec_id(subject, os.environ["SEC_USER_AGENT"])
            if cik:
                resolved["cik"] = cik
        except (requests.RequestException, ValueError, KeyError):
            report("EDGAR identity", "unavailable", "The SEC issuer index was unavailable.")
    if desk == "estate" and not inputs.get("orgnr"):
        try:
            r = requests.get("https://data.brreg.no/enhetsregisteret/api/enheter",
                             params={"navn": subject, "size": 20}, timeout=8)
            r.raise_for_status()
            candidates = r.json().get("_embedded", {}).get("enheter", [])
            matches = [row for row in candidates if _normal(row.get("navn")) == _normal(subject)]
            if len(matches) == 1:
                resolved["orgnr"] = matches[0]["organisasjonsnummer"]
        except (requests.RequestException, ValueError, KeyError):
            report("Registry identity", "unavailable", "The registry name index was unavailable.")
    return resolved
