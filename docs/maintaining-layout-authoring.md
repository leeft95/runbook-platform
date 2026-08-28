# Maintaining layout authoring

For platform maintainers and SDK contributors

The layout path is deliberately small and one-way:

```text
Report.add()
  ↓
Grid.blocks
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
   and `Grid`; there is no global or thread-local current builder.
2. First-fit auto-placement is `_place_grid` in
   `runbook.sdk.layout.compiler`.
3. PDL row and column coordinates are generated in `compile_layout`, after
   local grids are scaled to the page-wide LCM column count.
4. PDL validation happens in the existing `pdl-core` Pydantic models when the
   page and manifest are constructed. Stage 4 validates the reloaded JSON too.
5. Rendering starts after compilation: `runbook.sdk.html.render_html` handles
   static output, and `runbook.sdk.extensions.dash.renderer` handles the
   optional interactive page.

The authoring contract is intentionally flat: nested grids are rejected,
high-level layouts default to `max_columns = 12`, and LCM normalization is
never silently rounded. Keep these rules aligned with
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
