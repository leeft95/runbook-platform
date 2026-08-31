from __future__ import annotations

import asyncio
from types import SimpleNamespace

import dash
from runbook.services.config import validate_config
from runbook.services.dash import _config
from runbook.services.dash._config import (
    PROFILE_COLUMNS,
    PROFILE_SPEC,
    _payload_from_row,
    _profile_new_row,
    register_config_page,
)


class _Session:
    def __init__(self, repository: "_Repository") -> None:
        self.repository = repository

    async def __aenter__(self) -> "_Session":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def begin(self) -> "_Session":
        return self


class _Sessions:
    def __init__(self, repository: "_Repository") -> None:
        self.repository = repository

    def __call__(self) -> _Session:
        return _Session(self.repository)


class _Repository:
    def __init__(self, _session: _Session) -> None:
        self.queued: list[dict[str, object]] = []

    async def latest_config(self, kind: str, config_id: str) -> SimpleNamespace:
        return SimpleNamespace(config_id=config_id, kind=kind, revision=1, config_hash=f"hash-{kind}")

    async def queue_run(self, **kwargs: object) -> SimpleNamespace:
        self.queued.append(kwargs)
        return SimpleNamespace(run_id=f"{kwargs['kind']}-run")


def _callback_key(app: dash.Dash, prefix: str) -> str:
    key = next(key for key in app.callback_map if key.startswith(f"..{prefix}-grid.rowData"))
    return key


def _invoke(app: dash.Dash, prefix: str, trigger: str, kind: str, monkeypatch):
    key = _callback_key(app, prefix)
    monkeypatch.setattr(_config, "ctx", SimpleNamespace(triggered_id=trigger))
    row = {"_row_key": f"{kind}:one", "_new": False, "config_id": f"{kind}-one"}
    callback = app.callback_map[key]["callback"].__wrapped__
    return asyncio.run(
        callback(
            None,
            None,
            None,
            None,
            1,
            None,
            [row],
            [row],
        )
    )


def test_profile_delivery_has_generic_editor_field_and_validates_payload() -> None:
    row = _profile_new_row()
    row.update(
        {
            "config_id": "profile",
            "report_id": "report",
            "datasets": {"data": "data"},
            "delivery": {"email": {"provider": "company", "to": ["person@example.test"]}},
        }
    )
    config_id, payload = _payload_from_row("profile", row)
    assert config_id == "profile"
    assert payload["delivery"]["email"]["provider"] == "company"
    assert any(column["field"] == "delivery" and column["headerName"] == "Delivery" for column in PROFILE_COLUMNS)
    assert PROFILE_SPEC.complex_fields["delivery"] == "delivery"
    assert validate_config("profile", config_id, payload).model.delivery is not None

    row["delivery"] = {"email": {"provider": "company", "to": ["a@example.test", " a@example.test "]}}
    try:
        validate_config("profile", config_id, _payload_from_row("profile", row)[1])
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("malformed delivery payload was accepted")


def test_confirmed_profile_run_queues_once_and_source_run_trigger_is_unchanged(monkeypatch) -> None:
    repository = _Repository(None)  # type: ignore[arg-type]
    monkeypatch.setattr(_config, "AsyncRunRepository", lambda _session: repository)
    app = dash.Dash(__name__, use_pages=True, pages_folder="")
    register_config_page(
        app,
        _Sessions(repository),
        module="tests.config_ui_profile",
        kind="profile",
        path="/config-ui-profile",
        name="Config UI Profiles",
        order=1,
    )
    register_config_page(
        app,
        _Sessions(repository),
        module="tests.config_ui_source",
        kind="source",
        path="/config-ui-source",
        name="Config UI Sources",
        order=2,
    )

    profile_result = _invoke(app, "runbook-ui-profiles", "runbook-ui-profiles-run-confirm", "profile", monkeypatch)
    assert profile_result[1] == "Queued profile-run."
    assert len(repository.queued) == 1
    assert repository.queued[0]["kind"] == "profile"
    assert repository.queued[0]["trigger"] == "manual"

    source_result = _invoke(app, "runbook-ui-sources", "runbook-ui-sources-run", "source", monkeypatch)
    assert source_result[1] == "Queued source-run."
    assert len(repository.queued) == 2
    assert repository.queued[1]["kind"] == "source"
    assert repository.queued[1]["trigger"] == "manual"
