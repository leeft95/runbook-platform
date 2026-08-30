# Dash rendering

## Purpose

The SDK Dash renderer turns the same PDL manifest into a host-embeddable,
namespaced Dash page. Native static tables are the default; AG Grid is an
explicit interactive table choice.

## Owns

- `sdk/extensions/dash/renderer.py`: PDL traversal, component IDs, controls,
  callbacks, native tables, AG Grid, plots, links, and route-resolver use.
- `sdk/extensions/dash/tables.py`: AG Grid column/style translation.
- `sdk/extensions/dash/renderer_extensions.py`: public
  `DashRendererExtension` hooks.
- `sdk/extensions/dash/page.py` and `ids.py`: page and namespace support.

## Does not own

The renderer does not define PDL meaning, source/queue execution, Operations UI
branding, or host authentication/routes. The host supplies route resolution;
private presentation is injected via the public extension protocol.

## Start here

- `packages/runbook/runbook-sdk/src/runbook/sdk/extensions/dash/renderer.py`
- `packages/runbook/runbook-sdk/src/runbook/sdk/extensions/dash/tables.py`
- `packages/runbook/runbook-sdk/src/runbook/sdk/extensions/dash/renderer_extensions.py`
- `docs/dash-renderer-extensions.md`

## Data/control flow

```{mermaid}
flowchart TB
    pdl[PDLManifest] --> renderer[render_dash_page]
    renderer --> controls[Declarative controls + callbacks]
    renderer --> static[Native static table default]
    renderer --> ag[AG Grid interactive opt-in]
    renderer --> host[Host routes / extension]
```

## Public contracts

PDL interactions declare control semantics; the renderer binds namespaced IDs,
decodes values, and registers callbacks. `DashRendererExtension` may wrap a
page, control, or block and may supply custom control handling, while public
IDs, callback semantics, artifact reads, and namespacing remain Runbook-owned.
Semantic report/plot/URL links use `RouteResolver`; unresolved destinations
must become clear accessible errors.

Operations UI Dash/AG Grid pages under `runbook-services/src/runbook/services/dash`
are a separate control-plane product and do not share this renderer's owner or
contracts.

## Common modifications

For a new report-neutral feature change PDL and update HTML plus Dash. For a
Dash-only component or host integration use `DashRendererExtension`. For table
interactivity change renderer translation/tests, not `TableStylePlan`.

## Consumers

`sdk/execution.py` and private report hosts call `render_dash_page` or
`compose_report_page`. Hosts own the Dash app, routes, and authentication.

## Tests

- `tests/sdk/test_pdl_interactive.py`
- `tests/sdk/test_dash_renderer_extensions.py`
- `tests/sdk/test_dash_navigation.py`
- `tests/sdk/test_pdl_multipage.py`, `test_standalone_link.py`

## Common mistakes

- Treating AG Grid as the default output or as a core table contract.
- Putting host routes or private component IDs into PDL.
- Registering callbacks outside the renderer's namespace rules.
- Confusing Operations UI branding (`OperationsBrand`) with report rendering.

