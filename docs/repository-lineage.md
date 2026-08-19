# Repository lineage

This repository is the reconciled public platform/control-plane snapshot. The
reconciliation started from platform commit `4df3f40` on branch
`reconcile/private-platform-updates`. The source implementations were
inspected read-only and ported as coherent final states; generated files,
private plans, and employer-specific data were not copied.

## Reconciled changes

| Platform change | Source commit(s) |
| --- | --- |
| Operations dashboard, run detail/log pages, immutable worker logs, repository queries, runner diagnostics, and package assets | `278414bcd03aea778923f2fe46ac4e9ef5c617ff` |
| Grid-based source/profile configuration, dashboard grid, modal JavaScript, same-page links, and profile schedule removal | `4f3126b70d0f42c98bc04cca32beec74173130b6`, `9adb9a6a5bb65eb394985ebf528ae0e098a50852`, `c0c6761fea2b5892414e5d81bad3d4e84dad97b1`, `ad64cfc35250d3471f98639cd2043af8fd55f1d8`, `421f89a9b67de40ffb875a39cd977cf08d95d317` |
| Stale append/full dataset-pointer recovery and shared previous-state loading | `037b8d1f475a64d75da0044d09ed3bfbfcbb9d41` |
| Interrupted-run persistence, commit-before-shutdown handling, and Stage 2 progress diagnostics | `1075b4de365bd31589e464d79b1d807195387007` |

Commit `6ddab9810fd00ff9aad6bfff2d724a2b73b6aeb5` was inspected for context
but its VS Code-only changes were intentionally excluded. Generated pointer
files and other private/generated artifacts were also intentionally excluded.

The reconciled platform commits preserve this provenance in their commit
bodies. Profile configuration has no schedule field: source schedules create
scheduled roots, while profiles run manually or through ready-dataset fanout.
