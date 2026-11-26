"""Exercise the Caddy file on disposable containers.

The public-name check adds `tls internal` only in a temporary file so Let's
Encrypt is not contacted. The atlas.localhost check uses the committed file.
"""

from __future__ import annotations

import json
import socket
import ssl
import subprocess
import time
from http.client import HTTPConnection, HTTPSConnection
from pathlib import Path

from isolation import assert_owned, live_markers

ROOT = Path(__file__).resolve().parents[2]
CADDYFILE = ROOT / "infrastructure" / "caddy" / "Caddyfile"
RESULT = ROOT / "var" / "production-drill" / "proxy.json"
WORK = ROOT / "var" / "production-drill"
NETWORK = "atlas-prod-drill-proxy"
CA_VOLUME = "atlas-prod-drill-proxy-caddy"
API = "atlas-prod-drill-proxy-api"
WEB = "atlas-prod-drill-proxy-web"
CADDY = "atlas-prod-drill-proxy-caddy"
STUB = """
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = f"{os.environ['ROLE']}:{self.path}".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return

ThreadingHTTPServer(("0.0.0.0", int(os.environ["PORT"])), Handler).serve_forever()
"""


class Pinned(HTTPSConnection):
    def connect(self) -> None:
        raw = socket.create_connection(("127.0.0.1", self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def owned(name: str) -> str:
    assert_owned(name)
    return name


def cleanup() -> None:
    for name in (CADDY, API, WEB):
        subprocess.run(["docker", "rm", "-f", owned(name)], capture_output=True, check=False)
    subprocess.run(["docker", "volume", "rm", "-f", owned(CA_VOLUME)], capture_output=True, check=False)
    subprocess.run(["docker", "network", "rm", owned(NETWORK)], capture_output=True, check=False)


def free_pair() -> tuple[int, int]:
    for http_port, https_port in ((19080, 19443), (19180, 19543), (19280, 19643)):
        if _free(http_port) and _free(https_port):
            return http_port, https_port
    raise RuntimeError("no free loopback ports for the proxy drill")


def _free(port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def start_stubs() -> None:
    stub = WORK / "stub.py"
    stub.write_text(STUB, encoding="utf-8")
    for name, role, port in ((API, "api", "8000"), (WEB, "web", "3000")):
        result = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                owned(name),
                "--network",
                owned(NETWORK),
                "--network-alias",
                role,
                "-e",
                f"ROLE={role}",
                "-e",
                f"PORT={port}",
                "-v",
                f"{stub}:/stub.py:ro",
                "python:3.12-slim",
                "python",
                "/stub.py",
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode("utf-8", "replace")[-300:])


def start_caddy(host: str, http_port: int, https_port: int, config: Path) -> None:
    subprocess.run(["docker", "rm", "-f", owned(CADDY)], capture_output=True, check=False)
    result = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            owned(CADDY),
            "--network",
            owned(NETWORK),
            "-p",
            f"127.0.0.1:{http_port}:80",
            "-p",
            f"127.0.0.1:{https_port}:443",
            "-e",
            f"ATLAS_SITE_HOST={host}",
            "-v",
            f"{config}:/etc/caddy/Caddyfile:ro",
            "-v",
            f"{owned(CA_VOLUME)}:/data",
            "caddy:2.10-alpine",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace")[-300:])


def wait_ca() -> Path:
    destination = WORK / "proxy-ca.crt"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        copied = subprocess.run(
            [
                "docker",
                "cp",
                f"{owned(CADDY)}:/data/caddy/pki/authorities/local/root.crt",
                str(destination),
            ],
            capture_output=True,
            check=False,
        )
        if copied.returncode == 0 and destination.is_file() and destination.stat().st_size > 0:
            return destination
        time.sleep(1)
    raise RuntimeError("Caddy local CA was not written")


def request(host: str, port: int, path: str, ca_file: Path) -> tuple[int, dict[str, str], bytes]:
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=str(ca_file))
    deadline = time.monotonic() + 25
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        connection = Pinned(host, port, context=context, timeout=20)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            payload = response.read()
            headers = {key.lower(): value for key, value in response.headers.items()}
            return response.status, headers, payload
        except (OSError, ssl.SSLError, TimeoutError) as exc:
            last_error = exc
            time.sleep(1)
        finally:
            connection.close()
    raise RuntimeError(f"proxy request failed: {last_error}")


def header_problems(headers: dict[str, str], *, hsts: bool, api: bool) -> list[str]:
    issues = []
    expected = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "strict-origin-when-cross-origin",
        "content-security-policy": "frame-ancestors 'none'",
    }
    for key, value in expected.items():
        if headers.get(key) != value:
            issues.append(f"missing {key}")
    if "permissions-policy" not in headers:
        issues.append("missing permissions-policy")
    if "server" in headers:
        issues.append("server header is present")
    if hsts and "strict-transport-security" not in headers:
        issues.append("missing strict-transport-security")
    if not hsts and "strict-transport-security" in headers:
        issues.append("localhost received strict-transport-security")
    if api and headers.get("cache-control") != "no-store":
        issues.append("api cache-control is not no-store")
    return issues


def main() -> int:
    before = live_markers()
    report: dict[str, object] = {}
    try:
        WORK.mkdir(parents=True, exist_ok=True)
        http_port, https_port = free_pair()
        subprocess.run(["docker", "network", "create", owned(NETWORK)], capture_output=True, check=False)
        subprocess.run(["docker", "volume", "create", owned(CA_VOLUME)], capture_output=True, check=False)
        start_stubs()
        internal = WORK / "Caddyfile.internal"
        internal.write_text(
            CADDYFILE.read_text(encoding="utf-8").replace(
                "{$ATLAS_SITE_HOST:atlas.localhost} {",
                "{$ATLAS_SITE_HOST:atlas.localhost} {\n\ttls internal",
                1,
            ),
            encoding="utf-8",
        )
        start_caddy("proof.example", http_port, https_port, internal)
        ca_file = wait_ca()
        probed = subprocess.run(
            ["docker", "exec", owned(CADDY), "wget", "-q", "-O", "/dev/null", "http://127.0.0.1:2019/config/"],
            capture_output=True,
            check=False,
        )
        report["caddy_admin_health"] = probed.returncode == 0
        status, headers, body = request("proof.example", https_port, "/api/v1/health", ca_file)
        report["public_api_status"] = status
        report["public_api_body"] = body.decode()
        report["public_header_problems"] = header_problems(headers, hsts=True, api=True)
        login_status, login_headers, login_body = request("proof.example", https_port, "/login", ca_file)
        report["public_login_status"] = login_status
        report["public_login_body"] = login_body.decode()
        report["public_login_header_problems"] = header_problems(login_headers, hsts=True, api=False)
        plain = HTTPConnection("127.0.0.1", http_port, timeout=20)
        plain.request("GET", "/api/v1/health", headers={"Host": "proof.example"})
        redirected = plain.getresponse()
        report["http_status"] = redirected.status
        redirected.read()
        plain.close()
        start_caddy("atlas.localhost", http_port, https_port, CADDYFILE)
        local_ca = wait_ca()
        local_status, local_headers, local_body = request(
            "atlas.localhost", https_port, "/api/v1/health", local_ca
        )
        report["local_api_status"] = local_status
        report["local_api_body"] = local_body.decode()
        report["local_header_problems"] = header_problems(local_headers, hsts=False, api=True)
        report["live_projects_unchanged"] = before == live_markers()
        ok = (
            report["caddy_admin_health"] is True
            and status == 200
            and body == b"api:/api/v1/health"
            and report["public_header_problems"] == []
            and login_status == 200
            and login_body == b"web:/login"
            and report["public_login_header_problems"] == []
            and redirected.status in {301, 308}
            and local_status == 200
            and local_body == b"api:/api/v1/health"
            and report["local_header_problems"] == []
            and report["live_projects_unchanged"] is True
        )
        report["ok"] = ok
        RESULT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"drill_proxy ok={str(ok).lower()} http={redirected.status}")
        return 0 if ok else 2
    except (RuntimeError, OSError, ssl.SSLError) as exc:
        logs = subprocess.run(
            ["docker", "logs", "--tail", "50", CADDY],
            capture_output=True,
            text=True,
            check=False,
        )
        detail = (logs.stdout + logs.stderr)[-800:]
        print(f"drill_failed {exc}")
        if detail:
            print(detail)
        return 2
    finally:
        cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
