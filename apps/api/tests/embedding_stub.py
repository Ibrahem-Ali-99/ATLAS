import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

from tests.ai_clients import hash_embedding


class _Handler(BaseHTTPRequestHandler):
    """OpenAI-compatible embeddings backed by the test hash. Not a live provider."""

    protocol_version: ClassVar[str] = "HTTP/1.1"

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        raw = body.get("input", "")
        texts = raw if isinstance(raw, list) else [raw]
        payload = json.dumps(
            {
                "data": [
                    {"index": index, "embedding": hash_embedding(str(text))}
                    for index, text in enumerate(texts)
                ]
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


class EmbeddingStub:
    def __enter__(self) -> "EmbeddingStub":
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._httpd.shutdown()
        self._thread.join(timeout=5)
        self._httpd.server_close()

    @property
    def url(self) -> str:
        host, port = self._httpd.server_address
        return f"http://{host}:{port}"
