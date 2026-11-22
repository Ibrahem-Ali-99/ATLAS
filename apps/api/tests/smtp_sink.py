"""Local SMTP sink for sandbox delivery tests.

The process-wide sink speaks enough SMTP for ``smtplib`` to deliver a message.
It is not Mailpit. Mailpit is the development mailbox in Docker Compose.
"""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass, field


@dataclass
class SmtpSink:
    mode: str = "accept"
    messages: list[bytes] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    port: int = 0
    _socket: socket.socket | None = None
    _thread: threading.Thread | None = None
    _stopped: threading.Event = field(default_factory=threading.Event)

    def start(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(8)
        server.settimeout(0.2)
        self.port = server.getsockname()[1]
        self._socket = server
        self._thread = threading.Thread(target=self._serve, name="atlas-smtp-sink", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        if self._socket is not None:
            self._socket.close()

    def _serve(self) -> None:
        assert self._socket is not None
        while not self._stopped.is_set():
            try:
                connection, _address = self._socket.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            threading.Thread(
                target=self._session,
                args=(connection,),
                name="atlas-smtp-client",
                daemon=True,
            ).start()

    def _session(self, connection: socket.socket) -> None:
        try:
            connection.settimeout(5)
            reader = connection.makefile("rb")
            connection.sendall(b"220 atlas-sandbox ESMTP\r\n")
            while True:
                line = reader.readline()
                if not line:
                    return
                command = line.decode("utf-8", "replace").strip().upper()
                if command.startswith("EHLO") or command.startswith("HELO"):
                    connection.sendall(b"250 hello\r\n")
                elif command.startswith("MAIL FROM") or command.startswith("RCPT TO"):
                    connection.sendall(b"250 OK\r\n")
                elif command == "DATA":
                    connection.sendall(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                    chunks: list[bytes] = []
                    while True:
                        data_line = reader.readline()
                        if not data_line or data_line in {b".\r\n", b".\n"}:
                            break
                        chunks.append(data_line)
                    if self.mode == "timeout":
                        time.sleep(2)
                        return
                    with self.lock:
                        self.messages.append(b"".join(chunks))
                    connection.sendall(b"250 OK\r\n")
                elif command == "QUIT":
                    connection.sendall(b"221 bye\r\n")
                    return
                else:
                    connection.sendall(b"250 OK\r\n")
        except OSError:
            return
        finally:
            connection.close()


SINK: SmtpSink | None = None


def start_process_sink() -> SmtpSink:
    global SINK
    if SINK is None:
        SINK = SmtpSink()
        SINK.start()
    return SINK
