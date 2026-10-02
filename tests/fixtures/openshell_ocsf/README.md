# OpenShell OCSF fixtures

Hand-written in the shape of OpenShell's documented OCSF v1.8.0 JSONL
(`docs/observability/ocsf-json-export.mdx` and the gateway `ocsf_log`
section of `docs/how-it-works/gateways/configuration.mdx`, OpenShell commit
82e8893). They are not captured from a running gateway. Supervisor records
(network, HTTP, process, finding) come from the sandbox-local file; gateway
records (config changes, lifecycle) come from the gateway JSONL. The metrics
files follow the metric names in the gateway docs.
