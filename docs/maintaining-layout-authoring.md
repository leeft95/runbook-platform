# Maintaining layout authoring

For platform maintainers and SDK contributors

The layout path is deliberately small and one-way:

```text
Report.add()
  ↓
Grid / Row / Stack children
  ↓
compile_layout()
  ↓
place_blocks()
  ↓
PDLManifest
  ↓
renderer
```

## Where things live

1. Layout state is stored in plain dataclasses owned by `Report`, `Section`,
   `Grid`, `Row`, and `Stack`; there is no global or thread-local current
   builder.
2. First-fit auto-placement is `_place_grid` in
   `runbook.sdk.layout.compiler`.
3. PDL row and column coordinates are generated in `compile_layout`, after
   local Grid and Row widths are scaled to the page-wide LCM column count.
4. PDL validation happens in the existing `pdl-core` Pydantic models when the
   page and manifest are constructed. Stage 4 validates the reloaded JSON too.
5. Rendering starts after compilation: `runbook.sdk.html.render_html` handles
   static output, and `runbook.sdk.extensions.dash.renderer` handles the
   optional interactive page.

The two renderers consume the same PDL table/link semantics. Keep ordinary
tables on the native static Dash path; AG Grid is selected only when an
interaction explicitly owns a table output. Dash route resolution belongs to
the host, not layout compilation, and this reporting path must not grow an
iframe, `srcDoc`, or `postMessage` bridge.

The authoring contract is intentionally constrained: Grid remains flat, Row
accepts direct blocks or Stack slots, Stack accepts direct blocks, and other
layout nesting is rejected. High-level layouts default to `max_columns = 12`,
and LCM normalization is never silently rounded. Keep these rules aligned with
[Composable report layouts](composable-report-layouts.md).

## Adding a layout feature safely

Start with one focused unit test in `tests/sdk/test_layout.py`. Keep the
feature in the narrowest layer: storage in `models.py`, authoring methods in
`builder.py`, and traversal/coordinates/PDL lowering in `compiler.py`. Reuse
existing `runbook.sdk.ui` constructors for table, plot, text, artifacts, and
extensions. Do not import Dash into layout modules or put callbacks in layout
objects. Confirm that empty and invalid input still fail with an error naming
the object, value, and constraint.

## Tests that protect rendering

Run the focused layout tests and the SDK compatibility tests:

```bash
pixi run pytest tests/sdk/test_layout.py -q
pixi run pytest tests/sdk -q
```

The focused suite covers placement, spans, generators, omission, names,
compiled PDL, and static HTML. Existing SDK tests cover the public Dash
renderer and its extension seam. The synthetic large-report test compiles a
loop-generated 100+ block page without analyst coordinates.
