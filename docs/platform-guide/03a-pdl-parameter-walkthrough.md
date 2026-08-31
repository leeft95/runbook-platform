# Worked change: `table(width=...)`

This is the executable companion to the [change map](03-change-map.md). It
walks through the repository's existing renderer-neutral table-width change:

```text
ctx.artifact.table(...)
    -> layout table(width=...)
    -> LayoutBlock.table_width
    -> compile_layout / _lower_block
    -> ui.table(...)
    -> PDLTableBlock.width
    -> persisted Stage 3 PDL
    -> HTML or Dash
```

Read [Report authoring](subsystems/report-authoring.md) for the layout API,
[Core and PDL](subsystems/core-and-pdl.md) for the shared model and schemas,
and [Testing and validation](05-testing-and-validation.md) for repository-wide
checks. This page is a change walkthrough, not a general architecture tour.

## Goal and acceptance checks

The parameter has one renderer-neutral meaning:

```python
table_ref = ctx.artifact.table(frame, name="prices")
report_grid.table(table_ref, name="prices", width="40vw")
```

`width` controls the table inside its already-computed layout slot. It does
not change the grid's row, column, or span calculation.

The accepted values are deliberately small:

| Value | Meaning | PDL version |
| --- | --- | --- |
| `"fill"` | use the allocated slot; this is the default | `pdl-core/0.1` or `pdl-core/0.2` |
| `"content"` | use the table's natural content width | `pdl-core/0.2` |
| `"6in"`, `"40vw"`, or another accepted lowercase `in`/`vw` length | use that explicit width | `pdl-core/0.2` |

The completed change must satisfy these checkpoints:

- a default table has `width == "fill"` in Python, but omits `width` from its serialized block;
- an explicit non-fill value selects `pdl-core/0.2` and is serialized;
- `"content"` selects `pdl-core/0.2` in the layout compiler, without changing the table's position or span;
- HTML uses a content modifier for `"content"` and an explicit modifier plus `--rb-table-width` for a length;
- native Dash maps `fill` to `100%`, `content` to `auto`, and leaves `40vw` as `40vw`;
- interactive AG Grid remains `100%` wide while consuming resolved style and semantic links.

## 1. Prepare a clean, scoped work area

Run these commands from the repository root. They do not modify source files.

```bash
cd /home/leeft95/git_repos/runbook-platform
git status --short
pixi --version
pixi run python --version
```

On a fresh checkout, install the locked environment before continuing:

```bash
pixi install --locked
```

Inspect only the relevant files and symbols. These searches are intentionally
scoped so a junior can compare the guide with the implementation without
searching the whole repository:

```bash
rg -n "ArtifactRegistry|def table\\(|self\\.artifact = ArtifactRegistry" packages/runbook/runbook-core/src/runbook/core/report_artifacts.py packages/runbook/runbook-sdk/src/runbook/sdk/context.py
rg -n "PDLTableWidth|class PDLTableBlock|class PDLManifest|requires_v02|validate_schema_version_features" packages/runbook/runbook-core/src/runbook/core/pdl/models.py
rg -n "def table\\(|class LayoutBlock|table_width|generated_name|def _lower_block" packages/runbook/runbook-sdk/src/runbook/sdk/layout/models.py packages/runbook/runbook-sdk/src/runbook/sdk/layout/builder.py packages/runbook/runbook-sdk/src/runbook/sdk/layout/compiler.py packages/runbook/runbook-sdk/src/runbook/sdk/ui.py
rg -n "model_dump\\(mode=\\\"json\\\"\\)|stage3_ref|stage4_manifest|execute_report" packages/runbook/runbook-sdk/src/runbook/sdk/execution.py
rg -n "rb-table-content-width|rb-table-explicit-width|table_width = block\\.width|rb-table-width" packages/runbook/runbook-sdk/src/runbook/sdk/html.py
rg -n "_build_native_table|block\\.width|_build_ag_grid|\\\"width\\\": \\\"100%\\\"" packages/runbook/runbook-sdk/src/runbook/sdk/extensions/dash/renderer.py
```

Expected outcome: the current implementation contains every hop named above.
If a search finds a similarly named symbol in another package, keep following
the paths listed here; do not broaden this change without evidence.

## 2. Decide the ownership before editing

Ask whether the option still has meaning if the renderer changes. Table fill,
content width, and an explicit `in`/`vw` length do, so the semantic belongs on
the renderer-neutral PDL table block. A Dash component property, CSS class, or
AG Grid switch would remain renderer-specific and must not be added to PDL.

Make these decisions explicit in the change description:

1. The data artifact owns table data and optional style/link references; it does not own layout width.
2. `PDLTableBlock.width` owns the persisted table-width meaning.
3. The existing PDL version gate remains opt-in: omitted/default `fill` stays on `pdl-core/0.1`; any non-fill width uses `pdl-core/0.2`.
4. Layout placement remains unchanged; each renderer decides how to use the width inside its slot.
5. AG Grid keeps its existing full-slot sizing model; do not add autosizing for this parameter.

Do not confuse two unrelated widths. `PDLTableBlock.width` is the block
width. `TableStylePlan` sizing entries use `width_px` for individual table
columns or rows. The latter is resolved by the table-style system and is not a
replacement for the former.

## 3. Confirm artifact registration is already the right boundary

Open:

```bash
sed -n '1,125p' packages/runbook/runbook-core/src/runbook/core/report_artifacts.py
sed -n '35,90p' packages/runbook/runbook-sdk/src/runbook/sdk/context.py
```

`Ctx` creates an `ArtifactRegistry`. `ArtifactRegistry.table()` validates the
artifact name, writes the DataFrame through the context's table writer, and
returns a `TableArtifactRef` containing `data_ref` and optional style, HTML,
and link references. A table is registered before layout references it:

```python
table_ref = ctx.artifact.table(frame, name="prices", style=style)
```

There is no `width` argument here. Width is layout/PDL metadata, not artifact
data or style metadata. Keep the registration call unchanged while following
this feature. If a proposed implementation adds width to `ArtifactRegistry`,
stop and re-check the ownership decision.

Checkpoint: `table_ref` is a `TableArtifactRef`, and the layout call receives
that ref rather than the DataFrame.

## 4. Add or review the PDL contract

Open the model and schema files:

```bash
sed -n '125,180p' packages/runbook/runbook-core/src/runbook/core/pdl/models.py
sed -n '250,285p' packages/runbook/runbook-core/src/runbook/core/pdl/models.py
rg -n '"width"|"tableBlock"|"schema_version"' packages/runbook/runbook-core/src/runbook/core/pdl/spec.json packages/runbook/runbook-core/src/runbook/core/pdl/spec-0.2.json
```

The type and model field are:

```python
PDLTableWidth = Annotated[
    str,
    StringConstraints(pattern=r"^(?:fill|content|[0-9]+(?:\.[0-9]+)?(?:in|vw))$"),
]


class PDLTableBlock(PDLBlockBase, TableArtifactRef):
    type: Literal["table"] = "table"
    columns: list[PDLColumn] | None = None
    width: PDLTableWidth = Field(default="fill", exclude_if=lambda value: value == "fill")
```

The regex permits `fill`, `content`, and non-negative decimal numbers with
lowercase `in` or `vw` units. It accepts zero and does not impose a maximum.
It rejects values such as `6px`, `60%`, `6 IN`, `-6in`, `calc(6in)`, and
`1e2in`. Do not add an early check such as
`width not in {"fill", "content"}`: that would incorrectly reject valid
explicit widths like `6in` and `40vw`. Reuse the `PDLTableWidth` constraint.

There is no `spec-0.1.json` in this repository. The schema paths are:

```text
packages/runbook/runbook-core/src/runbook/core/pdl/spec.json       # pdl-core/0.1
packages/runbook/runbook-core/src/runbook/core/pdl/spec-0.2.json   # pdl-core/0.2
```

The v0.1 table schema deliberately has no `width` property. The v0.2 table
schema has the width property and the same pattern/default. Do not add width
to `spec.json` merely because the Python model has a default.

### Preserve the old wire contract

`Field(..., exclude_if=lambda value: value == "fill")` makes the Python default
available to renderers while keeping the default implicit in serialized PDL:

```python
manifest = PDLManifest(..., schema_version="pdl-core/0.1", page=page)
payload = manifest.model_dump(mode="json")
assert "width" not in payload["page"]["blocks"][0]
```

For an explicit value:

```python
manifest = PDLManifest(..., schema_version="pdl-core/0.2", page=page)
payload = manifest.model_dump(mode="json")
assert payload["page"]["blocks"][0]["width"] == "40vw"
```

Use the actual model dump in the example above. Do not substitute a generic
`dict()` call or treat JSON Schema validation as a Stage 3 runtime operation.

### Keep the version gate in both producers and the model

`sdk/ui.py::manifest()` selects the version from page features. The current
feature test is equivalent to:

```python
requires_v02 = any(
    isinstance(block, PDLLinkBlock)
    or (isinstance(block, PDLTableBlock) and (bool(block.links) or block.width != "fill"))
    for block in page.blocks
)
schema_version = "pdl-core/0.2" if requires_v02 else "pdl-core/0.1"
```

`PDLManifest.validate_schema_version_features()` repeats the invariant for
manifests constructed outside the SDK. The current reference implementation
raises this exact message when a v0.1 manifest contains a linked or non-fill
table feature:

```text
pdl-core/0.1 does not support linked or content-width table blocks; use pdl-core/0.2
```

The wording is historical: the check also covers explicit lengths such as
`40vw`. If you show the current code or assert its message, keep the exact
wording; do not infer that only `content` is supported by v0.2. Do not add
speculative nullable or `allOf` repairs for this feature.

Checkpoint: default `fill` remains compatible with v0.1; `content`, `6in`, and
`40vw` are rejected under v0.1 and accepted/serialized under v0.2.

## 5. Carry the field through layout authoring

Open the draft model and helper:

```bash
sed -n '1,45p' packages/runbook/runbook-sdk/src/runbook/sdk/layout/models.py
sed -n '100,135p' packages/runbook/runbook-sdk/src/runbook/sdk/layout/builder.py
sed -n '540,565p' packages/runbook/runbook-sdk/src/runbook/sdk/layout/builder.py
sed -n '670,700p' packages/runbook/runbook-sdk/src/runbook/sdk/layout/builder.py
sed -n '770,795p' packages/runbook/runbook-sdk/src/runbook/sdk/layout/builder.py
```

`LayoutBlock` is the authoring draft. When showing it in a change or review,
include all fields relevant to name generation; an incomplete class that
omits `generated_name` is misleading:

```python
@dataclass
class LayoutBlock:
    kind: BlockKind
    value: TableArtifactRef | PDLLinkDestination | str
    name: str | None = None
    title: str | None = None
    col_span: int = 1
    row_span: int = 1
    columns: list[PDLColumn] | None = None
    table_width: PDLTableWidth = "fill"
    extensions: dict[str, dict[str, Any]] | None = None
    label: str | None = None
    generated_name: bool = field(default=False, repr=False)
```

The canonical `layout.builder.table()` helper accepts `width` and stores it
unchanged as `table_width`. The helper validates the artifact reference and
spans; Pydantic's `PDLTableWidth` constraint validates the width when the
block becomes PDL. There is no separate explicit-width enum check in the
builder.

The composable convenience methods are exactly these three:

```python
Grid.table(ref, **kwargs)
Row.table(ref, **kwargs)
Stack.table(ref, **kwargs)
```

Each delegates to the canonical `table(ref, **kwargs)` helper and then adds the
block. There is no `Report.table()` or `Section.table()` method. For a direct
Report or Section child, use the canonical helper explicitly:

```python
from runbook.sdk.layout import table

layout.add(table(table_ref, name="prices", width="40vw"))
section.add(table(table_ref, name="prices", width="40vw"))
```

Normally prefer a `Grid`, `Row`, or `Stack` when composing peers:

```python
with layout.grid(columns=1) as report_grid:
    report_grid.table(table_ref, name="prices", width="40vw")
```

Checkpoint: after authoring, inspect the draft and confirm
`block.table_width == "40vw"`; no coordinates or artifact refs were changed.

## 6. Lower the draft without changing occupancy

Open the compiler and low-level UI helper:

```bash
sed -n '245,285p' packages/runbook/runbook-sdk/src/runbook/sdk/layout/compiler.py
sed -n '180,225p' packages/runbook/runbook-sdk/src/runbook/sdk/ui.py
```

`layout/compiler.py::_lower_block()` owns the translation from the draft to
the positioned PDL block. For a table, it forwards the semantic and lets the
compiler continue to own row/column placement:

```python
return ui.table(
    name=name,
    ref=block.value,
    row=row,
    col=col,
    title=block.title,
    row_span=row_span,
    col_span=col_span,
    columns=block.columns,
    width=block.table_width,
    extensions=block.extensions,
)
```

`sdk/ui.py::table()` creates `PDLTableBlock`, copying `data_ref`, `style_ref`,
`html_ref`, `style_key`, and `links` from the `TableArtifactRef`, then passing
`width` to the PDL model. It must not calculate HTML or Dash properties.

For a stack table, the compiler still emits the table at the page position and
span dictated by the stack. A `content` width changes only the table's
rendered use of that slot. The focused layout test expects the compiled block
to retain its position and full stack span while selecting `pdl-core/0.2`.

Checkpoint: `width="content"` produces a `PDLTableBlock` with
`width == "content"`, and `(row, col, col_span)` remains unchanged. A default
table produces `width == "fill"` and selects `pdl-core/0.1`.

## 7. Follow execution persistence and reload

Open the execution path:

```bash
sed -n '135,285p' packages/runbook/runbook-sdk/src/runbook/sdk/execution.py
```

`execute_report()` runs the report, compiles a `Report` when necessary, writes
registered artifact payloads, and persists Stage 3 as `manifest.stage3.json`.
The Stage 3 serialization is explicitly:

```python
json.dumps(manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
```

That is the point at which default `fill` is omitted from an ordinary table,
while an explicit `40vw` is present.

Stage 4 reloads the persisted JSON through Pydantic before rendering:

```python
stage4_manifest = PDLManifest.model_validate(store.get_json(stage3_ref))
```

It then renders HTML and persists `manifest.stage4.json`, again using
`model_dump(mode="json")`. JSON Schema validation is not a Stage 3 runtime
call. The tests and golden report validation explicitly load
`spec.json`/`spec-0.2.json` with `jsonschema` to check the wire contract.

Checkpoint: inspect both persisted manifests in a test or local store. The
default table has no `width` key in Stage 3; the linked golden table has
`"width": "40vw"`, `schema_version == "pdl-core/0.2"`, and can be reloaded as
`PDLManifest` for Stage 4.

## 8. Give HTML an explicit interpretation

Open the renderer and CSS:

```bash
sed -n '25,60p' packages/runbook/runbook-sdk/src/runbook/sdk/html.py
sed -n '115,145p' packages/runbook/runbook-sdk/src/runbook/sdk/html.py
```

The default table CSS remains full width:

```css
.rb-block table {
  width: 100%;
}

.rb-table-content-width table {
  width: auto;
}

.rb-table-explicit-width table {
  width: var(--rb-table-width);
}
```

The block renderer keeps layout coordinates in the `style` attribute and adds
the width semantic separately:

```python
table_width = None

if isinstance(block, PDLTableBlock):
    if block.width == "content":
        block_classes.append("rb-table-content-width")
    elif block.width != "fill":
        block_classes.append("rb-table-explicit-width")
        table_width = block.width

if table_width is not None:
    position += f" --rb-table-width: {escape(table_width)};"
```

The important explicit-width assignment is `table_width = block.width`, and
the emitted inline custom property is `--rb-table-width: ...`. Therefore:

- `fill` gets no width modifier and uses the default `width: 100%` rule;
- `content` gets `rb-table-content-width`, whose table rule is `width: auto`;
- `40vw` gets `rb-table-explicit-width` plus `--rb-table-width: 40vw;`.

Do not describe the `40vw` path as content or auto. Only `content` maps to
auto; an explicit value remains explicit. The value is HTML-escaped before it
is placed in the style attribute.

Checkpoint: render a manifest for each value and inspect the `<section>`
class/style. The explicit case contains both
`class="rb-block rb-table-explicit-width"` and
`--rb-table-width: 40vw;`.

## 9. Give native Dash and AG Grid explicit decisions

Open the Dash renderer around the two table builders:

```bash
sed -n '375,410p' packages/runbook/runbook-sdk/src/runbook/sdk/extensions/dash/renderer.py
sed -n '450,545p' packages/runbook/runbook-sdk/src/runbook/sdk/extensions/dash/renderer.py
```

Native Dash builds an `html.Table` and maps the PDL semantic directly in its
table style:

```python
"width": (
    "100%"
    if block.width == "fill"
    else "auto"
    if block.width == "content"
    else block.width
),
```

So `40vw` reaches native Dash as `40vw`; it does not become `auto`.

Interactive outputs choose AG Grid through the existing interaction path (the
public fixture is `reports/pnl_explorer.py`). `_build_ag_grid()` still returns
the renderer-owned full-slot style:

```python
"width": "100%",
```

AG Grid consumes the resolved table style, semantic links, hidden rows/columns,
and cell metadata. Its `100%` container width is an intentional fallback for
this slice; do not add a second width/autosizing implementation. Column
`width_px` values from `TableStylePlan` continue to control individual columns
where configured, but they are not `PDLTableBlock.width`.

Checkpoint: native Dash tests expect `fill -> 100%`, `content -> auto`, and
`6.5in -> 6.5in`. The AG Grid test expects `config.style["width"] == "100%"`
even when the PDL table block carries `width="40vw"`.

## 10. Use the existing tests as contract checkpoints

Inspect the named tests before editing implementation:

```bash
rg -n "def test_(table_width|pdl_|default_width|non_fill_width)|def test_stack_table_|def test_market_dashboard" tests/core/pdl/test_table_block.py tests/sdk/test_layout.py
rg -n "def test_(table_width|prerendered)|def test_native_table_width|def test_ag_grid|def test_linked_table" tests/sdk/test_html_bundle.py tests/sdk/test_dash_navigation.py tests/sdk/test_pdl_interactive.py tests/sdk/test_linked_table_report.py
```

The contract coverage is:

- `tests/core/pdl/test_table_block.py`: default, accepted and rejected values, v0.1/v0.2 compatibility, serialization, and packaged JSON Schema guards;
- `tests/sdk/test_layout.py::test_stack_table_content_width_survives_compilation_without_changing_occupancy`;
- `tests/sdk/test_layout.py::test_stack_table_defaults_to_fill_and_pdl_01`;
- `tests/sdk/test_html_bundle.py::test_table_width_modifier_and_css_preserve_fill_behavior`;
- `tests/sdk/test_dash_navigation.py::test_native_table_width_maps_fill_to_full_and_content_to_auto`;
- `tests/sdk/test_pdl_interactive.py::test_ag_grid_consumes_resolved_style_and_semantic_links`;
- `tests/sdk/test_linked_table_report.py::test_linked_table_golden_publishes_semantic_links_and_plot_pages`.

Run the focused file-level suite after each implementation boundary, or once
after a small documentation-only review:

```bash
pixi run pytest tests/core/pdl/test_table_block.py tests/sdk/test_layout.py tests/sdk/test_html_bundle.py tests/sdk/test_dash_navigation.py tests/sdk/test_pdl_interactive.py tests/sdk/test_linked_table_report.py -q
```

Expected outcomes include:

```text
default model width: fill
default serialized width: omitted
explicit serialized width: content / 6in / 40vw
content compilation: pdl-core/0.2, same occupancy
HTML: content modifier or explicit class/custom property
native Dash: fill 100%, content auto, explicit unchanged
AG Grid: 100% container width and semantic link/style metadata
golden: v0.2 JSON Schema, persisted 40vw, HTML links and plot pages
```

Do not weaken a test to make a wrong layer pass. A failed schema test means the
serialized contract or version gate is wrong; a failed HTML/Dash test means a
renderer mapping is wrong; a failed occupancy test means the compiler has
interpreted a semantic that it should only carry.

## 11. Check the public and golden examples

Inspect the examples with exact scoped commands:

```bash
rg -n "ctx\\.artifact\\.table|report_grid\\.table|width=|pdl-core/0\\.1|pdl-core/0\\.2" reports/linked_table_report.py reports/market_dashboard.py reports/pnl_explorer.py tests/sdk/test_linked_table_report.py tests/sdk/test_layout.py
rg -n "width|table|Grid|Stack|Row" docs/composable-report-layouts.md
```

The examples exercise different contracts:

- `reports/linked_table_report.py` registers a styled/linked table, calls `Grid.table(..., width="40vw")`, and is covered by the linked-table golden test. That test checks Stage 3 persistence, v0.2 JSON Schema validation, Stage 4 reload, HTML explicit-width markup, semantic links, linked plot pages, and native Dash routes.
- `reports/pnl_explorer.py` is the explicit interactive-output fixture. Its dashboard interaction makes the Dash renderer choose AG Grid; do not use it as evidence that AG Grid should adopt HTML width modifiers.
- `reports/market_dashboard.py` leaves table width at the default. `tests/sdk/test_layout.py::test_market_dashboard_golden_executes_and_uses_renderer_extension` checks that its Stage 3 manifest remains `pdl-core/0.1`, table `width` keys are omitted, and the v0.1 schema validates.
- `docs/composable-report-layouts.md` is the public authoring example. Keep analyst-facing prose about `fill`, `content`, and explicit lengths; renderer internals belong in this page.

If adding a new real parameter rather than reviewing this existing slice,
update one real public/golden example and its test. Avoid a synthetic report
that exercises only a helper in isolation.

## 12. Failure traps

Check these before asking for help:

| Symptom | Likely mistake | Correct boundary |
| --- | --- | --- |
| `spec-0.1.json` cannot be found | wrong filename | use `pdl/spec.json` for v0.1 and `pdl/spec-0.2.json` for v0.2 |
| `40vw` is rejected by the builder | copied an enum-only validation guard | reuse `PDLTableWidth`; explicit `in`/`vw` lengths are valid |
| artifact code has a width field | layout metadata was put in registration | keep width on `LayoutBlock` → `PDLTableBlock` |
| `Report.table(...)` or `Section.table(...)` fails | assumed convenience methods that do not exist | use `Grid.table`, `Row.table`, `Stack.table`, or `.add(table(...))` |
| v0.1 default payload contains `width: fill` | default was serialized unconditionally | keep the Pydantic `exclude_if` behavior and test `model_dump(mode="json")` |
| v0.1 accepts an explicit width | version gate is missing or only checks links | gate every `block.width != "fill"` and validate in `PDLManifest` |
| exact validator-message assertion fails | wording was paraphrased | current text is `linked or content-width table blocks`; preserve it when asserting current behavior |
| table moves or changes span after width support | compiler interpreted width as placement | `_lower_block()` forwards `table_width`; placement remains compiler-owned |
| explicit HTML width renders as auto | treated every non-fill value as content | only `content` gets `width: auto`; lengths use the class/custom property |
| AG Grid is expected to be `40vw` | copied native HTML/Dash behavior | interactive AG Grid intentionally keeps `width: 100%` in this slice |
| column sizing is confused with block width | mixed style and layout contracts | `TableStylePlan` `width_px` is per-column/row; `PDLTableBlock.width` is block-level |
| a JSON Schema issue prompts a broad model rewrite | runtime and golden validation were conflated | inspect the exact fixture and schema test; no speculative nullable/`allOf` repair is part of this change |

## 13. Final validation and handoff

Run the focused suite, then the standard repository checks documented in
[Testing and validation](05-testing-and-validation.md):

```bash
pixi run pytest tests/core/pdl/test_table_block.py tests/sdk/test_layout.py tests/sdk/test_html_bundle.py tests/sdk/test_dash_navigation.py tests/sdk/test_pdl_interactive.py tests/sdk/test_linked_table_report.py -q
pixi run docs
pixi run format-check
pixi run lint
pixi run typecheck
pixi run test
```

`pre-commit run --all-files` is an optional final check when its hooks are
available. `pixi run docs` is important here: it builds the Sphinx site with
warnings as errors, so a broken relative link or malformed directive fails the
build.

Before handoff, report:

- the three docs files changed (`03-change-map.md`, this page, and `index.md`), or the exact implementation files if this walkthrough is being applied to a new feature;
- focused test and standard-check results;
- whether default serialization stayed v0.1-compatible and explicit widths selected v0.2;
- any known limitation, especially the intentional AG Grid `100%` fallback.

The implementation rule to carry forward is simple: add a semantic once,
carry it through the authoring draft, compiler, PDL, and persisted manifest,
then make each renderer's interpretation explicit.
