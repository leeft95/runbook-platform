from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

import pytest
from runbook.core import ReportProfile
from runbook.data import open_blob_store
from runbook.sdk.delivery.email import (
    EmailDeliveryError,
    EmailSendReceipt,
    attempt_report_email_delivery,
    build_report_email_attachment,
    load_email_sender,
    reports_base_url,
    rewrite_dashboard_links,
)
from runbook.sdk.execution import ReportResult


def _result(html_ref: str = "reports/demo/report.html") -> ReportResult:
    return ReportResult(
        report_id="daily/report",
        artifact_id="artifact",
        snapshot_id="snapshot",
        context_hash="context",
        code_version="code",
        prefix="reports/daily",
        html_ref=html_ref,
        stage3_ref="reports/daily/stage3.json",
        stage4_ref="reports/daily/stage4.json",
    )


def test_profile_delivery_is_normalized_and_excluded_from_execution_identity() -> None:
    plain = ReportProfile(profile_id="profile", report_id="report", datasets={"data": "data"})
    configured = ReportProfile(
        profile_id="profile",
        report_id="report",
        datasets={"data": "data"},
        delivery={"email": {"provider": "company", "to": [" a@example.com "]}},
    )
    assert plain.delivery is None
    assert configured.delivery is not None and configured.delivery.email is not None
    assert configured.delivery.email.provider == "company"
    assert configured.delivery.email.to == ("a@example.com",)
    assert plain.execution_config() == configured.execution_config()
    assert "delivery" not in plain.model_dump(mode="json")
    assert "delivery" in configured.model_dump(mode="json")
    with pytest.raises(ValueError, match="duplicate"):
        ReportProfile(
            profile_id="profile",
            report_id="report",
            datasets={"data": "data"},
            delivery={"email": {"provider": "company", "to": ["a@example.com", " A@example.com "]}},
        )


def test_reports_url_validation_and_semantic_rewrite() -> None:
    assert reports_base_url("https://reports.example.test///") == "https://reports.example.test"
    html = (
        '<a href="/report/other" data-runbook-link-kind="report" '
        'data-runbook-report-id="other">Other</a>'
        '<a href="plots/p.html" data-runbook-link-kind="plot" '
        'data-runbook-plot-name="plot/name">Plot</a>'
        '<a href="https://example.test/x" data-runbook-link-kind="url">External</a>'
    )
    rewritten = rewrite_dashboard_links(
        html,
        current_report_id="daily/report",
        dashboard_base_url="https://reports.example.test/",
    )
    assert 'href="https://reports.example.test/reports/other"' in rewritten
    assert 'href="https://reports.example.test/reports/daily%2Freport/plots/plot%2Fname"' in rewritten
    assert 'href="https://example.test/x"' in rewritten
    with pytest.raises(EmailDeliveryError):
        reports_base_url("https://user:password@reports.example.test")
    with pytest.raises(EmailDeliveryError, match="dashboard_base_url_required"):
        rewrite_dashboard_links(
            html,
            current_report_id="daily",
            dashboard_base_url=None,
        )


def test_attachment_is_one_deterministic_html_member_and_preserves_source(tmp_path) -> None:
    store = open_blob_store(f"file:{tmp_path}")
    result = _result()
    source = '<a href="/report/other" data-runbook-link-kind="report" data-runbook-report-id="other">Other</a>'
    store.put_immutable(result.html_ref, source.encode())
    first = build_report_email_attachment(store, result, dashboard_base_url="https://reports.example.test")
    second = build_report_email_attachment(store, result, dashboard_base_url="https://reports.example.test")
    assert first.content == second.content
    assert store.get(result.html_ref) == source.encode()
    with zipfile.ZipFile(io.BytesIO(first.content)) as archive:
        assert archive.namelist() == ["report.html"]
        assert "https://reports.example.test/reports/other" in archive.read("report.html").decode()


def test_sender_discovery_is_deterministic_and_sanitized(monkeypatch) -> None:
    class Sender:
        def send(self, _message):
            return EmailSendReceipt(message_id="message")

    entry_point = SimpleNamespace(
        name="company", group="runbook.email_senders", value="module:create_sender", dist=None
    )
    entry_point.load = lambda: lambda: Sender()
    monkeypatch.setattr("runbook.sdk.delivery.email.metadata.entry_points", lambda: [entry_point])
    assert callable(load_email_sender("company").send)

    def fail():
        raise RuntimeError("password=secret")

    entry_point.load = lambda: fail
    with pytest.raises(EmailDeliveryError, match="factory failed") as error:
        load_email_sender("company")
    assert "secret" not in str(error.value)


def test_delivery_failure_is_operational_metadata_only(tmp_path, monkeypatch) -> None:
    store = open_blob_store(f"file:{tmp_path}")
    result = _result()
    store.put_immutable(result.html_ref, b"<html></html>")
    profile = ReportProfile(
        profile_id="profile",
        report_id="daily",
        datasets={"data": "data"},
        delivery={"email": {"provider": "company", "to": ["person@example.test"]}},
    )

    class Sender:
        def send(self, _message):
            raise RuntimeError("secret should not escape")

    monkeypatch.setattr("runbook.sdk.delivery.email.load_email_sender", lambda _provider: Sender())
    delivery = attempt_report_email_delivery(store=store, profile=profile, result=result)
    assert delivery is not None
    assert delivery["status"] == "failed"
    assert delivery["attempts"] == 1
    assert delivery["error"] == "RuntimeError"
    assert "secret" not in str(delivery)
