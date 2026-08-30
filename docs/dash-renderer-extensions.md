# Dash renderer extensions

For renderer-extension authors and deployment owners

Runbook's Dash renderer owns report semantics and provides an optional,
trusted-Python presentation seam. Pass one object to `render_dash_page` (or to
`compose_report_page`) to customize page chrome, controls, or block wrappers
without copying report execution, validation, or callback code. A report should
already work as static HTML; see [Interactive reports](pdl-interactive.md).

The renderer's default table is native static Dash. AG Grid is selected only
for an explicitly interactive table output. Semantic report, URL, and plot
links are resolved by the public renderer and the host's route resolver; an
extension should not rewrite links or introduce an iframe, `srcDoc`, or
`postMessage` bridge.

This is deliberately separate from `OperationsBrand`: branding customises the
control-plane Operations UI, while a `DashRendererExtension` customises report
presentation. Deployment wiring for both seams is in [Deployment](deployment.md).

```python
from runbook.sdk.extensions.dash import render_dash_page

page = render_dash_page(
    manifest,
    definition,
    ctx,
    namespace="my-report",
    renderer_extension=MyRenderer(),
)
```

An extension implements all three protocol methods below. Each method may
return `None`, which selects the vanilla public renderer for that part.

```python
import json

from runbook.sdk.extensions.dash import DashRenderedControl, DashRendererExtension


class MyRenderer:
    def wrap_page(self, content, *, manifest, namespace):
        return content

    def render_control(self, control, *, component_id, options):
        return None

    def wrap_block(self, body, *, block, title, namespace):
        return None
```

For example, a host can add a provider or other theme around the complete
page, and can replace a select with a component whose native value is an
encoded token. `DashRenderedControl` keeps the public interaction state
unchanged by declaring the property to read and its decoder:

```python
class ThemeRenderer:
    def wrap_page(self, content, *, manifest, namespace):
        return ThemeProvider(content)

    def render_control(self, control, *, component_id, options):
        if control.type == "select":

            def token(value):
                return "runbook-value:" + json.dumps(value, separators=(",", ":"))

            return DashRenderedControl(
                component=ThemeSelect(
                    id=component_id,
                    data=[{"label": str(value), "value": token(value)} for value in options or []],
                    value=None if control.value is None else token(control.value),
                ),
                input_properties=("value",),
                decode=lambda values: (
                    None if values[0] is None else json.loads(values[0].removeprefix("runbook-value:"))
                ),
            )
        return None

    def wrap_block(self, body, *, block, title, namespace):
        return Panel([title, body])
```

The public renderer continues to own manifest parsing and validation, PDL
block traversal, artifact reads, IDs, control option resolution, callback
registration, interaction state/output conversion, and AG Grid semantics.
Extensions only present the already-resolved values. A block's public outer
container ID and grid positioning are retained, and the title node is passed
to `wrap_block` so a custom wrapper can place it exactly once. The body is
rendered by public code before the wrapper is called.

Custom controls may declare different native input properties and decode them
back to the normal logical control value with `DashRenderedControl`. Plain
component returns continue to use the vanilla public control binding. They
must not register report callbacks, invoke handlers, mutate the manifest, or
add new PDL meaning. Report callbacks remain host-owned and are registered by
`DashPage.register_callbacks`.

Renderer extensions are trusted Python presentation code installed by the
host. They are not a sandbox or user-authored PDL feature.
