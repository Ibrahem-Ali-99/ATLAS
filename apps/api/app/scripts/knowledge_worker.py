"""Run the durable knowledge-ingestion worker until interrupted."""

from __future__ import annotations

import signal
import threading

from app.domains.knowledge.worker import start, stop


def main() -> None:
    event = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: event.set())
    thread = start(event)
    try:
        event.wait()
    finally:
        stop(event, thread)


if __name__ == "__main__":
    main()
