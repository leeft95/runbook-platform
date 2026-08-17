# Contributing and security

Install Pixi and run the repository checks before submitting a change:

```bash
pixi run test
pixi run lint
pixi run format-check
```

Keep source acquisition in `runbook-data`, keep reports dataset-first, and
preserve deterministic snapshot, cache, and immutable-artifact semantics.
Do not add credentials, private data, vendor-specific configuration, or
deployment secrets to the repository.

For documentation changes, build the site locally with the command on the
{doc}`index` page. CI builds docs for every pull request and publishes the
`main` branch to GitHub Pages.

## Security issues

Please do not report security issues in public issues. Contact the repository
owner privately with a description, reproduction, and impact. The bundled
service has no authentication and binds to loopback by default; do not expose
it directly to untrusted networks.
