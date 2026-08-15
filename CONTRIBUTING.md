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
