# Public Boundary

`secret-redact-io` publishes generic IO safety mechanics:

- redaction policy rules for common secret-shaped values;
- guarded file read and write helpers;
- guarded HTTP fetch helper;
- guarded subprocess helper;
- hash-only receipt records.

The package does not publish private environment rules, credentials, or any
deployment-specific configuration.
