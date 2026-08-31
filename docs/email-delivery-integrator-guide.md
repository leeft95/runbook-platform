# Email delivery integrator guide

This guide is for a private deployment that wants to provide a mail sender for
Runbook. Install an integration package in the same Python environment as
`runbook-worker`; do not modify report or worker code for provider wiring.

## Public seam

The SDK provides `EmailMessage`, `EmailAttachment`, `EmailSendReceipt`, and
the synchronous `EmailSender` protocol. A provider package implements
`send(message)` and exposes a zero-argument factory in the
`runbook.email_senders` entry-point group:

`EmailMessage.html_body` is the report HTML and must be mapped to the
provider's HTML body field. `attachments` defaults to an empty tuple; automatic
delivery supplies no attachment. Integrators may explicitly pass generic
`EmailAttachment` values (for example, an image or PDF) when constructing a
message.

```python
import os

from runbook.sdk.delivery.email import EmailMessage, EmailSendReceipt, EmailSender


class CompanyEmailSender:
    def send(self, message):
        # Translate the generic message to the private provider API.
        return EmailSendReceipt(message_id="provider-message-id")


def create_sender() -> EmailSender:
    # Read provider settings from deployment secret injection.
    os.environ["COMPANY_SMTP_HOST"]
    return CompanyEmailSender()
```

Register it in the integration package's `pyproject.toml`:

```toml
[project.entry-points."runbook.email_senders"]
company = "runbook_private.delivery.email:create_sender"
```

The provider ID is the profile's `delivery.email.provider` value. Provider
settings and credentials belong only to the private package and its secret
manager. Illustrative names might be `COMPANY_SMTP_HOST`,
`COMPANY_SMTP_PORT`, `COMPANY_SMTP_USERNAME`, `COMPANY_SMTP_PASSWORD`, and
`COMPANY_SMTP_FROM`, or provider-specific Graph settings. Runbook does not
standardize those names.

## Deployment checklist

1. Implement the generic protocol and a fresh sender from a zero-argument
   factory.
2. Register one `runbook.email_senders` entry point for the logical provider.
3. Install the integration package in the worker image/environment, not only
   in Operations or a notebook.
4. Inject provider credentials and from-address policy through deployment
   secrets. Never put them in profile JSON, PDL, or `Run.result`.
5. Set the deployment-level dashboard URL in the worker runtime:

   ```bash
   export RUNBOOK_REPORTS_BASE_URL="https://reports.example.com"
   ```

   The dashboard should serve `/reports/<report-id>` and
   `/reports/<report-id>/plots/<plot-name>`.
6. Verify discovery in the worker environment:

   ```bash
   pixi run python -c "from runbook.sdk.delivery.email import load_email_sender; sender = load_email_sender('company'); assert callable(sender.send)"
   ```

7. Configure a test profile with a test recipient and `provider: "company"`.
8. Execute one controlled report and verify that the run is `success`, the
   email metadata is in `Run.result.delivery.email`, the report is present in
   `EmailMessage.html_body`, no automatic attachment is present, dashboard
   links work, and external URLs are unchanged.

The provider should translate `EmailMessage.to`, `cc`, `subject`, HTML
`html_body`, and any explicitly supplied attachments into its own transport
API. Live sends belong in opt-in deployment tests; normal CI should use a fake
provider/client.

## Failure and retry behavior

Report execution and publication complete before discovery or sending begins.
A provider failure leaves the report run successful and records only a
sanitized error type. If semantic report/plot links exist without a valid
`RUNBOOK_REPORTS_BASE_URL`, Runbook records `dashboard_base_url_required`
without sending broken links. A profile with no delivery policy never loads a
provider.

Retry the existing successful run after fixing deployment configuration:

```bash
runbook-worker --deliver-run-id RUN_ID
```

The worker loads the pinned profile revision and existing immutable HTML and
does not call `execute_report`. A normal retry refuses a prior `sent` result;
use `--force` only for an intentional duplicate resend. Attempt counts
increment across retries.

## Security checklist

- Keep provider credentials in secret management and inject them only where
  workers need them.
- Never place credentials in `report_profiles.json`, PDL, or `Run.result`.
- Do not log recipient lists, message bodies, attachment bytes, or raw
  credential-bearing provider exceptions.
- Keep TLS and provider certificate verification enabled in production.
- Ensure `RUNBOOK_REPORTS_BASE_URL` has no credentials, query, or fragment.
- Use a test recipient and a fake provider for routine CI.

## Minimal provider tests

Downstream tests can keep transport calls fake and deterministic:

```python
def test_sender_factory(monkeypatch):
    monkeypatch.setenv("COMPANY_SMTP_HOST", "smtp.example.test")
    sender = create_sender()
    assert callable(sender.send)


def test_sender_maps_public_message(fake_provider, attachment):
    sender = CompanyEmailSender(fake_provider)
    receipt = sender.send(
        EmailMessage(
            to=("research@example.com",),
            cc=(),
            subject="Report",
            html_body="<p>Report</p>",
            attachments=(attachment,),
        )
    )
    assert receipt.message_id
```

For live SMTP, Graph, SES, or other integration checks, use an explicit
opt-in suite and deployment test account. The public platform intentionally
ships the provider seam, not a concrete transport.
