# Contributing

Install Pixi and run the test and lint tasks before submitting changes:

```bash
pixi run test
pixi run lint
pixi run format-check
```

Keep source acquisition in `runbook-data`, keep reports dataset-first, and
preserve deterministic snapshot, cache, and immutable-artifact semantics.
Do not add credentials, private data, vendor-specific configuration, or
deployment secrets to the repository.

For report layout, use the highest-level API that solves the requirement:
`Report` / `Section` / `Grid` with ordinary Python loops, compiled to PDL.
Use raw PDL only as an escape hatch. Do not introduce a new abstraction until
at least two concrete reports need it. Keep layout state explicit and avoid
renderer-specific objects or callback logic in layout code.
