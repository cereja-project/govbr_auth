"""Bounded, process-local traces containing only already-sanitized events."""

import secrets
from copy import deepcopy
from threading import RLock
from time import monotonic
from collections.abc import Callable


class Trace:
    """One voluntary capture; exported snapshots never contain its access key."""

    def __init__(self, clock: Callable[[], float], max_events: int = 128) -> None:
        self.clock = clock
        self.created = clock()
        self.max_events = max_events
        self.events: list[dict[str, object]] = []
        self.truncated = False
        self.completed = False
        self.lock = RLock()

    def append(
        self, phase: str, *, evidence: str = "observed", request: dict | None = None
    ) -> int | None:
        with self.lock:
            if len(self.events) >= self.max_events:
                self.truncated = True
                return None
            number = len(self.events)
            self.events.append(
                {
                    "id": number,
                    "phase": phase,
                    "evidence": evidence,
                    "status": "running",
                    "at_ms": round((self.clock() - self.created) * 1000, 3),
                    "duration_ms": None,
                    "request": request,
                    "response": None,
                }
            )
            return number

    def finish(
        self,
        number: int | None,
        *,
        status: int | None = 200,
        headers: dict | None = None,
        body: dict | None = None,
    ) -> None:
        with self.lock:
            if number is None:
                return
            event = self.events[number]
            event["status"] = "error" if status is None or status >= 400 else "success"
            event["duration_ms"] = round(
                max(0, (self.clock() - self.created) * 1000 - event["at_ms"]), 3
            )
            event["response"] = (
                None
                if status is None
                else {
                    "status": status,
                    "headers": headers or {},
                    "body": body,
                }
            )

    def inferred(self, phase: str) -> None:
        number = self.append(phase, evidence="inferred")
        self.finish(number)
        if number is not None:
            with self.lock:
                self.events[number]["duration_ms"] = None
                self.events[number]["response"] = None

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            return {
                "version": 1,
                "events": deepcopy(self.events),
                "completed": self.completed,
                "truncated": self.truncated,
                "redacted": True,
                "capture": "FakeGov local; uma captura por navegador; dados apenas em memória",
            }


class TraceStore:
    """Expire and evict traces rather than retaining global authentication logs."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = monotonic,
        ttl: int = 600,
        capacity: int = 64,
    ) -> None:
        self.clock, self.ttl, self.capacity = clock, ttl, capacity
        self.traces: dict[str, Trace] = {}
        self.lock = RLock()

    def _prune(self) -> None:
        expired = [
            key
            for key, trace in self.traces.items()
            if self.clock() - trace.created >= self.ttl
        ]
        for key in expired:
            del self.traces[key]

    def start(self, previous: str = "") -> tuple[str, Trace]:
        with self.lock:
            self._prune()
            self.traces.pop(previous, None)
            if len(self.traces) >= self.capacity:
                del self.traces[next(iter(self.traces))]
            key = secrets.token_urlsafe(32)
            trace = Trace(self.clock)
            self.traces[key] = trace
            return key, trace

    def get(self, key: str) -> Trace | None:
        with self.lock:
            self._prune()
            return self.traces.get(key)

    def stop(self, key: str) -> None:
        with self.lock:
            self.traces.pop(key, None)
