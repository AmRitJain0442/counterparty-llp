"""Decision ledger. Cloud clients are created only when their backend is selected."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from contextlib import closing, contextmanager
from datetime import date, datetime, timezone
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


def attach_receipt(case: dict, receipt: dict) -> None:
    """Attach the verified bundle only if the snapshot sent for signing is still current."""
    key = _case_key(case["id"])
    snapshot = {k: v for k, v in case.items() if k != "watch_review"}
    expected = _json(snapshot)

    def attach(tx):
        doc = tx.get("cases", key)
        if doc is None or doc["decision_json"] != expected:
            raise ValueError("Case changed during signing. Re-read the decision before attaching a receipt")
        updated = {**snapshot, "receipt": receipt["digest"], "receipt_record": receipt}
        tx.put("cases", key, {**doc, "decision_json": _json(updated)})

    _ledger().atomic(attach)


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


@contextmanager
def _local_cache():
    with _connection() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS batch_cache (
                 cache_key TEXT PRIMARY KEY, as_of TEXT NOT NULL,
                 data_json TEXT NOT NULL, expires_at REAL NOT NULL)"""
        )
        yield conn


def _cache_key(key):
    if not isinstance(key, str) or not key.strip():
        raise ValueError("batch cache key must be a nonempty scoped string")
    return _key(key)


def _cache_table():
    table = os.getenv("BIGQUERY_CACHE_TABLE")
    # BigQuery supports parameters for values only. Validate the configured identifier.
    if table and not re.fullmatch(r"[a-z][a-z0-9-]*\.[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*", table):
        raise ValueError("BIGQUERY_CACHE_TABLE must be project.dataset.table")
    return table


@lru_cache(maxsize=4)
def _bigquery(project, location):
    from google.cloud import bigquery

    return bigquery.Client(project=project, location=location)


def _cache_query(table, sql, parameters):
    from google.cloud import bigquery

    client = _bigquery(os.getenv("GOOGLE_CLOUD_PROJECT") or table.split(".")[0], os.getenv("BIGQUERY_LOCATION"))
    config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter(name, kind, value) for name, kind, value in parameters
    ])
    return client.query(sql, job_config=config).result(timeout=45)


def put_cached_batch(key: str, data, *, as_of: str, ttl_seconds: int) -> None:
    """Cache a scoped private batch with its source date and a TTL of up to 30 days."""
    cache_key = _cache_key(key)
    if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 30 * 86400:
        raise ValueError("batch TTL must be 1 second to 30 days")
    try:
        if len(as_of) == 10:
            date.fromisoformat(as_of)
        elif datetime.fromisoformat(as_of.replace("Z", "+00:00")).tzinfo is None:
            raise ValueError
    except (TypeError, ValueError, AttributeError):
        raise ValueError("as_of must be an ISO date or timestamp with a timezone") from None
    encoded = _json(data)
    table = _cache_table()
    if table:
        _cache_query(table,
            f"""INSERT INTO `{table}` (cache_key, as_of, data_json, stored_at, expires_at)
                VALUES (@key, @as_of, @data, CURRENT_TIMESTAMP(),
                        TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL @ttl SECOND))""",
            [("key", "STRING", cache_key), ("as_of", "STRING", as_of),
             ("data", "STRING", encoded), ("ttl", "INT64", ttl_seconds)])
    elif os.environ.get("LEDGER_BACKEND", "sqlite").lower() == "sqlite":
        with _local_cache() as conn:
            now = time.time()
            conn.execute("DELETE FROM batch_cache WHERE expires_at <= ?", (now,))
            conn.execute(
                "INSERT OR REPLACE INTO batch_cache VALUES (?, ?, ?, ?)",
                (cache_key, as_of, encoded, now + ttl_seconds),
            )


def get_cached_batch(key: str) -> dict | None:
    cache_key = _cache_key(key)
    table = _cache_table()
    if table:
        # Test the latest write for expiration so an older value cannot resurface.
        rows = _cache_query(table,
            f"""SELECT as_of, data_json FROM (
                    SELECT as_of, data_json, expires_at FROM `{table}`
                    WHERE cache_key = @key
                      AND stored_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
                    ORDER BY stored_at DESC LIMIT 1
                ) WHERE expires_at > CURRENT_TIMESTAMP()""",
            [("key", "STRING", cache_key)])
        row = next(iter(rows), None)
    elif os.environ.get("LEDGER_BACKEND", "sqlite").lower() == "sqlite":
        with _local_cache() as conn:
            row = conn.execute(
                "SELECT as_of, data_json FROM batch_cache WHERE cache_key=? AND expires_at>?",
                (cache_key, time.time()),
            ).fetchone()
    else:
        return None
    return {"mode": "CACHED", "as_of": row[0], "data": json.loads(row[1])} if row else None
