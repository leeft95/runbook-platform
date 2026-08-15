# Security

Please do not report security issues in public issues. Contact the
repository owner privately with a description, reproduction, and impact.

The bundled service has no authentication and binds to loopback by default.
Do not expose it directly to untrusted networks. Keep credentials in the
runtime environment or a secret manager; never commit them to source or
configuration files.
