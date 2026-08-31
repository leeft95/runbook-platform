# Post-publish email delivery

Runbook can optionally send the HTML report produced by a successful profile
run. Delivery is a post-publish step:

```text
snapshot -> report execution -> PDL -> HTML publication -> optional email
```

It never participates in PDL, layout, calculation caching, report rendering,
snapshot identity, or artifact identity. A profile's `delivery.email` policy is
pinned with its configuration revision, but it is deliberately excluded from
`ReportProfile.execution_config()`.

## Profile configuration

Add the optional policy to a profile JSON object:

```json
{
  "report_id": "daily_report",
  "title": "Daily report",
  "datasets": {"prices": "daily_prices"},
  "delivery": {
    "email": {
      "provider": "company",
      "to": ["research@example.com"],
      "cc": [],
      "subject": "Daily report"
    }
  }
}
```

`provider` selects an installed integration. `to` and `cc` are recipient
policy, and `subject` optionally overrides the profile title. Recipient
whitespace is stripped and duplicates are rejected. An empty `delivery` value
means no delivery. The Operations UI exposes the same object through its
generic JSON editor.

The public platform does not define SMTP, Graph, SES, credentials, or a
from-address field. A private integration supplies a zero-argument factory
through the `runbook.email_senders` entry-point group. See the
[integrator guide](email-delivery-integrator-guide.md).

## Runtime and HTML contract

The worker reads the already-published `ReportResult.html_ref`; it does not
execute or render the report again. It sends one deterministic ZIP attachment
named `<report-id>.zip` with exactly one member, `report.html`. The original
immutable HTML object and linked plot pages remain unchanged.

Runbook semantic report and plot anchors in the email copy become dashboard
links. Configure one deployment-level URL in the worker environment:

```bash
export RUNBOOK_REPORTS_BASE_URL="https://reports.example.com"
```

The URL must be `http` or `https`, without credentials, query, or fragment;
trailing slashes are normalized. The route contract is:

```text
/reports/<report-id>
/reports/<current-report-id>/plots/<plot-name>
```

Path segments are URL encoded. External URL anchors are retained exactly. If
semantic report/plot links exist but the base URL is absent or invalid,
delivery is recorded as failed and no email is sent. A report without those
links may be sent without the setting.

## Results and retry

The run remains `success` when email fails. Operational metadata is stored in
`Run.result.delivery.email`: status, provider, attempt count, timestamp,
optional provider message ID, and sanitized exception type. Recipients,
message content, attachment bytes, credentials, and raw provider exceptions
are not persisted or logged. Allow-listed machine-readable failures may also
include `delivery.email.reason`; currently the only value is
`dashboard_base_url_required`.

Retry a failed delivery from its existing successful run:

```bash
runbook-worker --deliver-run-id RUN_ID
runbook-worker --deliver-run-id RUN_ID --force  # intentional resend
```

Retry reads the pinned profile revision and immutable HTML references, never
calls `execute_report`, and only updates delivery metadata. Ordinary retry
refuses an already-sent message; `--force` explicitly permits a duplicate.

## Ownership and limitations

Report authors own the profile policy. Deployment integrators own the sender,
transport settings, secret injection, provider-specific validation, and
dashboard host. The public release has no concrete mail provider, PDF output,
template DSL, inline plot rendering, queue, or scheduling system. Delivery is
synchronous in the worker process and intentionally has no provider-specific
retry policy.

For the full downstream implementation and worker-runtime checklist, read
the [email delivery integrator guide](email-delivery-integrator-guide.md).
