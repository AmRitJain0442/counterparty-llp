"""Request-local collection events consumed by the stage interface."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from threading import Lock

_sink = ContextVar("investigation_event_sink", default=None)


def report(name, status, detail, *, collection_agent=None):
    sink = _sink.get()
    if sink:
        event = {"type": "step", "name": name, "status": status, "detail": detail}
        if collection_agent:
            event["collection_agent"] = collection_agent
        sink(event)


def current_sink():
    """Capture this investigation's stream before dispatching work to other threads."""
    return _sink.get()


def attach(sink):
    return _sink.set(sink)


def detach(token):
    _sink.reset(token)


@contextmanager
def record_collection():
    events = []
    outer = _sink.get()
    lock = Lock()

    def capture(event):
        with lock:
            item = {**event, "at": datetime.now(timezone.utc).isoformat()}
            events.append(item)
            if outer:
                outer(item)

    token = attach(capture)
    try:
        yield events
    finally:
        detach(token)
