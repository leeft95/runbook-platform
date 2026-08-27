# Dash renderer extensions

Runbook's Dash renderer owns report semantics and provides an optional,
trusted-Python presentation seam. Pass one object to `render_dash_page` (or to
`compose_report_page`) to customize page chrome, controls, or block wrappers
without copying report execution, validation, or callback code.

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
from runbook.sdk.extensions.dash import DashRendererExtension


class MyRenderer:
    def wrap_page(self, content, *, manifest, namespace):
        return content

    def render_control(self, control, *, component_id, options):
        return None

    def wrap_block(self, body, *, block, title, namespace):
        return None
```

For example, a host can add a provider or other theme around the complete
page, and can replace the visual component for a select while keeping its
public ID and `value` property:

```python
class ThemeRenderer:
    def wrap_page(self, content, *, manifest, namespace):
        return ThemeProvider(content)

    def render_control(self, control, *, component_id, options):
        if control.type == "select":
            return ThemeSelect(id=component_id, data=options or [], value=control.value)
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

Extensions must expose the semantic Dash properties expected by public
callbacks (`value`, `start_date`, `end_date`, `children`, `figure`, or
`rowData`). They must not register report callbacks, invoke handlers, mutate
the manifest, or add new PDL meaning. Report callbacks remain host-owned and
are registered by `DashPage.register_callbacks`.

Renderer extensions are trusted Python presentation code installed by the
host. They are not a sandbox or user-authored PDL feature.
