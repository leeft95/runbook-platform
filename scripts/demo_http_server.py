"""Deterministic standard-library HTTP fixtures for local Phase B demos."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures"


class DemoRequestHandler(BaseHTTPRequestHandler):
    """Serve public CSV fixtures plus deterministic readiness/failure routes."""

    server_version = "runbook-demo/1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        request = urlsplit(self.path)
        if request.path == "/healthz":
            self._respond(200, b"ok\n", "text/plain; charset=utf-8")
            return
        if request.path in {"/slow.csv", "/fixtures/slow.csv"}:
            self._slow_response(parse_qs(request.query).get("delay", ["2"])[0])
            return
        if request.path in {
            "/missing.csv",
            "/fixtures/missing.csv",
            "/fixtures/acquisition-missing.csv",
        }:
            self._respond(404, b"missing demo fixture\n", "text/plain; charset=utf-8")
            return
        if request.path in {"/failure.csv", "/fixtures/failure.csv"}:
            self._respond(500, b"demo source failure\n", "text/plain; charset=utf-8")
            return
        fixture = {
            "/daily_prices.csv": "daily_prices.csv",
            "/fixtures/daily_prices.csv": "daily_prices.csv",
            "/intraday_bars.csv": "intraday_bars.csv",
            "/fixtures/intraday_bars.csv": "intraday_bars.csv",
        }.get(request.path)
        if fixture is None:
            self._respond(404, b"unknown demo route\n", "text/plain; charset=utf-8")
            return
        self._respond(200, (FIXTURES / fixture).read_bytes(), "text/csv; charset=utf-8")

    def _slow_response(self, value: str) -> None:
        import time

        try:
            delay = min(max(float(value), 0.0), 30.0)
        except ValueError:
            delay = 2.0
        time.sleep(delay)
        self._respond(200, (FIXTURES / "daily_prices.csv").read_bytes(), "text/csv; charset=utf-8")

    def _respond(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def serve(host: str = "127.0.0.1", port: int = 8766) -> None:
    """Serve demo routes until interrupted."""
    server = ThreadingHTTPServer((host, port), DemoRequestHandler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
