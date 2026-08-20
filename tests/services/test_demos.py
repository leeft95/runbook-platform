from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.request import urlopen

from scripts.demo_http_server import DemoRequestHandler


def test_demo_http_routes_are_deterministic() -> None:
    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), DemoRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(f"{base}/fixtures/daily_prices.csv") as response:
            payload = response.read()
            assert response.status == 200
        assert payload.startswith(b"timestamp,close\n")
        with urlopen(f"{base}/healthz") as response:
            assert response.read() == b"ok\n"
        for path, code in (("missing.csv", 404), ("failure.csv", 500)):
            try:
                urlopen(f"{base}/fixtures/{path}")
            except Exception as exc:
                assert getattr(exc, "code", None) == code
            else:  # pragma: no cover - urllib raises for 4xx/5xx
                raise AssertionError(f"expected HTTP {code}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_demo_source_configs_are_public_and_disabled_for_optional_routes() -> None:
    payload = json.loads(Path("data/contract/source_configs.json").read_text(encoding="utf-8"))
    assert payload["demo_daily_prices"]["enabled"] is True
    for source_id in (
        "demo_local_append",
        "demo_http_csv",
        "demo_http_slow",
        "demo_http_missing",
        "demo_http_acquisition_failure",
        "demo_http_failure",
    ):
        assert payload[source_id]["enabled"] is False
