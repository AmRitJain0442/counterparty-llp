"""Request-local collection events consumed by the stage interface."""
from contextvars import ContextVar

_sink = ContextVar("investigation_event_sink", default=None)


def report(name, status, detail):
    sink = _sink.get()
    if sink:
        sink({"type": "step", "name": name, "status": status, "detail": detail})


def send(event):
    sink = _sink.get()
    if sink:
        sink(event)


def attach(sink):
    return _sink.set(sink)


def detach(token):
    _sink.reset(token)
