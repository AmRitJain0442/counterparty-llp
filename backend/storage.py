"""Decision ledger. Cloud clients are created only when their backend is selected."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _key(value):
    # Fixed-size document IDs also support case IDs containing "/" or Unicode.
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _case_key(case_id):
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("case id must be a nonempty string")
    return _key(case_id)


def _sqlite_path():
    default = Path(__file__).resolve().parent.parent / ".local" / "ledger.sqlite3"
    return Path(os.environ.get("SQLITE_PATH") or default).expanduser()


@contextmanager
def _connection():
    path = _sqlite_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=30)) as conn, conn:
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ledger (
                 collection TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL,
                 PRIMARY KEY (collection, id))"""
        )
        yield conn


class _SQLiteDocuments:
    def __init__(self, conn):
        self.conn = conn

    def get(self, collection, key):
        row = self.conn.execute(
            "SELECT body FROM ledger WHERE collection=? AND id=?", (collection, key)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, collection, key, doc):
        self.conn.execute(
            """INSERT INTO ledger (collection, id, body) VALUES (?, ?, ?)
               ON CONFLICT (collection, id) DO UPDATE SET body=excluded.body""",
            (collection, key, _json(doc)),
        )


class _SQLiteLedger:
    def get(self, collection, key):
        with _connection() as conn:
            return _SQLiteDocuments(conn).get(collection, key)

    def atomic(self, change):
        with _connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            return change(_SQLiteDocuments(conn))

    def scan(self, collection, *, pending_limit=None):
        with _connection() as conn:
            sql = "SELECT body FROM ledger WHERE collection=?"
            params = [collection]
            if pending_limit is not None:
                sql += " AND json_extract(body, '$.state')='pending' LIMIT ?"
                params.append(pending_limit)
            return [json.loads(row[0]) for row in conn.execute(sql, params)]


class _FirestoreDocuments:
    def __init__(self, client, transaction=None):
        self.client = client
        self.transaction = transaction

    def collection(self, name):
        return self.client.collection("counterparty_" + name)

    def get(self, collection, key):
        ref = self.collection(collection).document(key)
        return ref.get(transaction=self.transaction).to_dict()

    def put(self, collection, key, doc):
        self.transaction.set(self.collection(collection).document(key), doc)


class _FirestoreLedger(_FirestoreDocuments):
    def atomic(self, change):
        from google.cloud import firestore

        @firestore.transactional
        def run(transaction):
            return change(_FirestoreDocuments(self.client, transaction))

        return run(self.client.transaction())

    def scan(self, collection, *, pending_limit=None):
        query = self.collection(collection)
        if pending_limit is not None:
            from google.cloud.firestore_v1.base_query import FieldFilter

            query = query.where(filter=FieldFilter("state", "==", "pending")).limit(pending_limit)
        return [doc.to_dict() for doc in query.stream()]


@lru_cache(maxsize=4)
def _firestore(project, database):
    from google.cloud import firestore

    return _FirestoreLedger(firestore.Client(project=project, database=database))


def _ledger():
    mode = os.environ.get("LEDGER_BACKEND", "sqlite").lower()
    if mode == "sqlite":
        return _SQLiteLedger()
    if mode == "firestore":
        return _firestore(os.getenv("GOOGLE_CLOUD_PROJECT"), os.getenv("FIRESTORE_DATABASE", "(default)"))
    raise ValueError("LEDGER_BACKEND must be sqlite or firestore")


def _decision(doc):
    case = json.loads(doc["decision_json"])
    if "watch_review" in doc:
        case["watch_review"] = doc["watch_review"]
    return case


def save_case(case: dict) -> dict:
    """Upsert a JSON decision by id, preserving its creation time and review state."""
    case = dict(case)
    key = _case_key(case.get("id"))
    case.pop("watch_review", None)  # Only a committed watch event may set this.
    # A string preserves nested JSON arrays, which Firestore fields cannot represent.
    encoded = _json(case)

    def save(tx):
        doc = tx.get("cases", key) or {"created_at": _utc_now()}
        doc["decision_json"] = encoded
        tx.put("cases", key, doc)
        return _decision(doc)

    return _ledger().atomic(save)


def list_cases() -> list[dict]:
    docs = _ledger().scan("cases")
    # Stable tie-break even across replicas with identical creation timestamps.
    cases = [(doc["created_at"], _decision(doc)) for doc in docs]
    cases.sort(key=lambda item: (item[0], item[1]["id"]), reverse=True)
    return [case for _, case in cases]


def get_case(id: str) -> dict | None:
    doc = _ledger().get("cases", _case_key(id))
    return _decision(doc) if doc else None


def _watch_key(watch_id):
    key = str(watch_id)
    if not re.fullmatch(r"[1-9][0-9]{0,19}", key):
        raise ValueError("expected a positive Crustdata watch id")
    return key


def bind_watch(watch_id: int | str, case_id: str) -> None:
    """Bind a dedicated entity watch once. Only the trusted control plane calls this."""
    watch = _watch_key(watch_id)
    case = _case_key(case_id)

    def bind(tx):
        if tx.get("cases", case) is None:
            raise KeyError("case does not exist")
        binding = tx.get("watch_bindings", watch)
        if binding is None:
            tx.put("watch_bindings", watch, {"case": case})
        elif binding["case"] != case:
            raise ValueError("watch already belongs to another case")

    _ledger().atomic(bind)


def stage_watch_event(watch_id, notification_id: str, delivered_at: str) -> dict:
    """Commit a minimal outbox row before trying to publish its ID."""
    watch = _watch_key(watch_id)
    event_id = _key(f"crustdata/v1/{watch}/{notification_id}")

    def stage(tx):
        event = tx.get("watch_events", event_id)
        if event is not None:
            return event
        binding = tx.get("watch_bindings", watch)
        if binding is None:
            raise KeyError("unbound watch")
        event = {
            "event_id": event_id,
            "case": binding["case"],
            "as_of": delivered_at,
            "state": "pending",
        }
        tx.put("watch_events", event_id, event)
        return event

    return _ledger().atomic(stage)


def pending_watch_events(limit: int = 100) -> list[str]:
    if not 1 <= limit <= 1000:
        raise ValueError("outbox limit must be 1 to 1000")
    return [event["event_id"] for event in _ledger().scan("watch_events", pending_limit=limit)]


def mark_watch_published(event_id: str) -> None:
    def mark(tx):
        event = tx.get("watch_events", event_id)
        if event is None:
            raise KeyError("unknown event")
        # A push may have committed before the publisher's confirmation arrived.
        if event["state"] == "pending":
            tx.put("watch_events", event_id, {**event, "state": "published"})

    _ledger().atomic(mark)


def reopen_from_watch(event_id: str) -> bool:
    """Apply a staged event at most once, even after a lost publish or push ACK."""
    def apply(tx):
        event = tx.get("watch_events", event_id)
        if event is None:
            raise KeyError("unknown event")
        if event["state"] == "applied":
            return False
        doc = tx.get("cases", event["case"])
        if doc is None:
            raise KeyError("bound case is missing")
        previous = doc.get("watch_review", {})
        # Deliveries may arrive out of order. Times are normalized UTC strings.
        latest_date, latest_id = max(
            (previous.get("as_of", ""), previous.get("event_id", "")),
            (event["as_of"], event_id),
        )
        doc["watch_review"] = {
            "status": "REOPENED",
            "event_count": previous.get("event_count", 0) + 1,
            "as_of": latest_date,
            "event_id": latest_id,
        }
        tx.put("cases", event["case"], doc)
        tx.put("watch_events", event_id, {**event, "state": "applied"})
        return True

    return _ledger().atomic(apply)
