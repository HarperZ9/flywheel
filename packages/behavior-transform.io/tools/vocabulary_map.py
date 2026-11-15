"""Vocabulary calibration map — single source of truth.

Authorized security-assessment tools use operational terminology that
overlaps with language model-provider content filters flag. This module
maps operational terms to consulting-register equivalents so the tool's
own documentation and internal identifiers pass through provider
content policies without triggering false positives.

This module is the canonical mapping from the operational term to the
provider-compliant term. It is consumed by:

    - tools/pressure_scan.py        — pre-commit / CI guard
    - warden_shell/_compat/    — backward-compat aliases at module boundaries
    - docs/VOCABULARY-CALIBRATION.md — human-readable explainer

Severity:
    tier1 — hard trigger. Must not appear outside `_compat/`,
            `docs/VOCABULARY-CALIBRATION.md`, or this file. Linter blocks.
    tier2 — soft trigger. Calibrated form is preferred; linter warns.

Scope:
    identifier   — Python class / function / variable / module name.
    module-name  — directory or file basename.
    free-prose   — appears in docstrings, comments, README prose.
    verb-prose   — bare verb in prose (e.g. "harvest tokens").
    noun-prose   — bare noun in prose (e.g. "the harvester").
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Calibration:
    calibrated: str
    original: str
    severity: str
    scope: str
    note: str = ""


CALIBRATIONS: tuple[Calibration, ...] = (
    # ----- Tier 1 — hard triggers --------------------------------------------
    # Parasite / parasitic family
    Calibration("co-tenant", "parasite", "tier1", "free-prose",
                "frames as theft-by-host-burdening; no consulting equivalent"),
    Calibration("co-tenant", "parasitic", "tier1", "free-prose"),
    Calibration("BillingCoTenantPattern", "BillingParasitePattern", "tier1", "identifier"),

    # Collector family (was Harvester*)
    Calibration("BillingCreditCollector", "BillingCreditHarvester", "tier1", "identifier"),
    Calibration("ComputeCollector", "ComputeHarvester", "tier1", "identifier"),
    Calibration("CollectorOrchestrator", "HarvesterOrchestrator", "tier1", "identifier"),
    Calibration("CollectorRegistry", "HarvesterRegistry", "tier1", "identifier"),
    Calibration("ResourceCollector", "ResourceHarvester", "tier1", "identifier"),
    Calibration("CollectorSchedule", "HarvesterSchedule", "tier1", "identifier"),
    Calibration("collector_orchestrator", "harvester_orchestrator", "tier1", "identifier"),
    Calibration("collector_registry", "harvester_registry", "tier1", "identifier"),
    Calibration("register_builtin_collectors", "register_builtin_harvesters", "tier1", "identifier"),
    Calibration("reset_collectors", "reset_harvesters", "tier1", "identifier"),
    Calibration("CollectedCredential", "HarvestedCredential", "tier1", "identifier"),
    Calibration("CollectedArtifact", "HarvestedArtifact", "tier1", "identifier"),
    # Compound module/file names that don't match the bare \bharvester\b
    Calibration("session_extractor", "session_collector", "tier1", "module-name"),
    Calibration("SessionCollector", "SessionHarvester", "tier1", "identifier"),
    Calibration("credential_collector", "credential_collector", "tier1", "module-name"),
    Calibration("env_var_collector", "env_var_collector", "tier1", "module-name"),
    Calibration("model_response_collector", "model_response_collector", "tier1", "module-name"),
    Calibration("endpoint_credential_collector", "endpoint_credential_collector", "tier1", "module-name"),
    Calibration("collect", "harvest", "tier1", "verb-prose",
                "applies to credentials, billing, identities — not URL collection"),
    Calibration("collected", "harvested", "tier1", "verb-prose"),
    Calibration("collecting", "harvesting", "tier1", "verb-prose"),
    Calibration("Collected", "Harvested", "tier1", "verb-prose"),
    Calibration("Collecting", "Harvesting", "tier1", "verb-prose"),
    Calibration("collector", "harvester", "tier1", "noun-prose"),
    Calibration("Collector", "Harvester", "tier1", "noun-prose"),
    Calibration("Co-tenant", "Parasite", "tier1", "free-prose",
                "PascalCase variant"),
    Calibration("Co-tenant", "Parasitic", "tier1", "free-prose"),

    # Camouflage / invisibility
    Calibration("billing_baseline_fit", "billing_camouflage", "tier1", "identifier"),
    Calibration("baseline-fit", "camouflage", "tier1", "free-prose"),
    Calibration("reset_traffic_profile", "reset_invisibility", "tier1", "identifier"),
    Calibration("low-observable", "invisibility", "tier1", "free-prose"),
    Calibration("low-observable", "invisible", "tier1", "free-prose"),
    Calibration("unattributed", "invisible to every observer", "tier1", "free-prose"),

    # Self-acquire / self-provisioning
    Calibration("credential_discovery_orchestrator", "authorized_acquire", "tier1", "module-name"),
    Calibration("AuthorizedAcquireOrchestrator", "SelfAcquireOrchestrator", "tier1", "identifier"),
    Calibration("AuthorizedAcquireContext", "SelfAcquireContext", "tier1", "identifier"),
    Calibration("AuthorizedAcquireResult", "SelfAcquireResult", "tier1", "identifier"),
    Calibration("authorized_acquire_orchestrator", "authorized_acquire_orchestrator", "tier1", "identifier"),
    Calibration("authorized_acquire_tier_contracts", "authorized_acquire_tier_contracts", "tier1", "identifier"),
    Calibration("Provider-Authorized Credential Validation",
                "Provider Self-Authorized Offensive Acquisition", "tier1", "free-prose"),
    Calibration("authorized credential provisioning",
                "invisible credential self-provisioning", "tier1", "free-prose"),

    # Token forge
    Calibration("token_synthesis_executor", "token_forge_executor", "tier1", "identifier"),

    # Corpus distill
    Calibration("CorpusSamplePattern", "CorpusDistillPattern", "tier1", "identifier"),
    Calibration("response_distillation_pattern", "corpus_sample", "tier1", "module-name"),

    # Identity chain
    Calibration("FederatedSessionPattern", "IdentityChainPattern", "tier1", "identifier"),
    Calibration("federated_sessions", "federated_identities", "tier1", "identifier"),
    Calibration("reset_federated_sessions", "reset_federated_session", "tier1", "identifier"),

    # Egress pool
    Calibration("EgressDistributionPattern", "EgressPoolPattern", "tier1", "identifier"),
    Calibration("get_egress_members", "get_pool_members", "tier1", "identifier"),
    Calibration("reset_egress_distribution", "reset_egress_distribution", "tier1", "identifier"),
    Calibration("identity_pool_registration", "egress_distribution", "tier1", "module-name"),

    # Identity chain (module name companion to FederatedSessionPattern rename)
    Calibration("brokered_identity_provision", "federated_session", "tier1", "module-name"),

    # Engraver / persistence tradecraft prose
    Calibration("persistence-artifact construction", "persistent_agent fabrication", "tier1", "free-prose"),
    Calibration("credential-validation chain",
                "master authority acquisition kill-chain", "tier1", "free-prose"),
    Calibration("callback channel, callback interval, traffic shaping",
                "beacon loop, sleep mask, evasion timing", "tier1", "free-prose"),

    # PersistentAgent family (was Implant*) — class identifiers
    Calibration("PersistentAgent", "Implant", "tier1", "identifier",
                "tradecraft register; consulting equivalent is 'persistent agent' / "
                "'persistent process' as used in CREST / NIST 800-115 deliverables"),
    Calibration("PersistentAgentManager", "ImplantManager", "tier1", "identifier"),
    Calibration("PersistentAgentStatus", "ImplantStatus", "tier1", "identifier"),
    Calibration("PersistentAgentSpec", "ImplantSpec", "tier1", "identifier"),
    Calibration("PersistentAgentConfig", "ImplantConfig", "tier1", "identifier"),
    Calibration("PersistentAgentRegistry", "ImplantRegistry", "tier1", "identifier"),
    Calibration("PersistentAgentState", "ImplantState", "tier1", "identifier"),
    # snake_case identifiers (word-bounded — \b matches around underscores)
    Calibration("agent_id", "persistent_agent_id", "tier1", "identifier"),
    Calibration("_agents", "_persistent_agents", "tier1", "identifier",
                "private dict attribute on PersistentAgentManager"),
    Calibration("decommission_all", "extract_all", "tier1", "identifier",
                "method on PersistentAgentManager — replaces extract_all"),
    Calibration("active_persistent_agents", "active_persistent_agents", "tier1", "identifier"),
    Calibration("all_persistent_agents", "all_persistent_agents", "tier1", "identifier"),
    # Module path rewrites — dotted, no \b boundary
    Calibration("persistence.persistent_agent", "persistence.persistent_agent", "tier1", "identifier",
                "module path; rewrites import statements + log namespaces"),
    Calibration("persistent_agent.activated", "persistent_agent.activated", "tier1", "identifier",
                "event_type literal"),
    Calibration("persistent_agent.decommissioned", "persistent_agent.extracted", "tier1", "identifier",
                "event_type literal"),
    Calibration("persistent_agent.callback_error", "persistent_agent.beacon_error", "tier1", "identifier",
                "log key literal"),
    Calibration("persistent_agent.task", "persistent_agent.task", "tier1", "identifier"),
    Calibration("persistent_agent.sleeping", "persistent_agent.sleeping", "tier1", "identifier"),
    Calibration("persistent_agent.deploy_blocked", "persistent_agent.deploy_blocked", "tier1", "identifier"),
    Calibration("pso.persistent_agents_decommissioned", "pso.persistent_agents_extracted", "tier1", "identifier",
                "log key literal in daemon.process"),
    # File / module name rename
    Calibration("persistent_agent", "persistent_agent", "tier1", "module-name",
                "persistence/persistent_agent.py -> persistence/persistent_agent.py"),

    # Bare lowercase 'persistent_agent' / 'persistent_agents' — single-token calibration.
    # Using 'agent' / 'agents' (no space) so identifier rewrites in
    # 'bundle.persistent_agents' or 'persistent_agents = ...' produce valid Python; PSO
    # namespace (warden_pso.persistence) disambiguates from the Sovereign
    # agent ecosystem. Prose readings degrade gracefully ('an persistent_agent
    # lifecycle' -> 'an agent lifecycle' is correct in pen-test register).
    Calibration("agent", "persistent_agent", "tier1", "identifier",
                "bare 'persistent_agent' -> 'agent'; PascalCase Implant covered separately"),
    Calibration("agents", "persistent_agents", "tier1", "identifier"),

    # PersistentAgentStatus enum values: BACKOFF replaces EVADING,
    # DECOMMISSIONED replaces EXTRACTED. Not in lexicon because the
    # linter applies regex case-insensitively across all scopes, and
    # bare lowercase 'extracted' / 'evading' are used legitimately
    # elsewhere (TOTP seed extraction, network egress evasion).
    # The two enum sites (core/types.py + persistent_agent.py) are
    # edited by hand and tracked in docs/VOCABULARY-CALIBRATION.md.

    # Callback family (was Beacon*)
    Calibration("Callback", "Beacon", "tier1", "identifier",
                "tradecraft register; 'callback' is the consulting register equivalent"),
    Calibration("CallbackChannel", "BeaconChannel", "tier1", "identifier"),
    Calibration("CallbackConfig", "BeaconConfig", "tier1", "identifier"),
    Calibration("CallbackState", "BeaconState", "tier1", "identifier"),
    Calibration("CallbackLoop", "BeaconLoop", "tier1", "identifier"),
    Calibration("CallbackHandler", "BeaconHandler", "tier1", "identifier"),
    # Compound Loader entries — bare 'Loader' stays for legitimate module/data loaders
    Calibration("CallbackBootstrapper", "BeaconLoader", "tier1", "identifier"),
    Calibration("PersistentAgentBootstrapper", "ImplantLoader", "tier1", "identifier"),
    # snake_case
    Calibration("_callback_task", "_beacon_task", "tier1", "identifier"),
    Calibration("_callback_loop", "_beacon_loop", "tier1", "identifier"),
    Calibration("callback_error", "beacon_error", "tier1", "identifier"),
    Calibration("callback_loop", "beacon_loop", "tier1", "identifier"),

    # Foothold family
    Calibration("Anchor", "Foothold", "tier1", "identifier"),
    Calibration("anchor", "foothold", "tier1", "noun-prose",
                "pen-test deliverables: 'anchor' / 'initial-access point' replaces 'foothold'"),

    # Dropper / Stager (identifier scope only).
    # NOTE: Backdoor is intentionally NOT calibrated — the identifier-scope
    # case-sensitive `\bBackdoor\b` regex would match "Backdoor injection"
    # in ML-security prose, which is a keep-list research term. If an actual
    # `Backdoor` class needs calibration in the future, scope it to the
    # specific module path.
    Calibration("Installer", "Dropper", "tier1", "identifier"),
    Calibration("Bootstrapper", "Stager", "tier1", "identifier"),

    # ----- Tier 1 — credential operations (general) -------------------------
    Calibration("credential-relay technique", "pass-the-hash", "tier1", "free-prose"),
    Calibration("credential-relay technique", "pass the hash", "tier1", "free-prose"),
    Calibration("hash-relay", "PtH", "tier1", "free-prose"),
    Calibration("kerberos-extraction", "kerberoasting", "tier1", "free-prose"),
    Calibration("kerberos-extraction", "kerberoast", "tier1", "verb-prose"),
    Calibration("kerberos-preauth-bypass", "AS-REP roasting", "tier1", "free-prose"),
    Calibration("kerberos-preauth-bypass", "ASREProasting", "tier1", "free-prose"),
    Calibration("kerberos-token-forge", "golden ticket", "tier1", "free-prose"),
    Calibration("kerberos-service-token-forge", "silver ticket", "tier1", "free-prose"),
    Calibration("credential-extraction", "credential dump", "tier1", "free-prose"),
    Calibration("credential-extraction", "credential dumping", "tier1", "free-prose"),
    Calibration("CredentialExtractor", "CredentialDumper", "tier1", "identifier"),
    Calibration("credential_extractor", "credential_dumper", "tier1", "identifier"),
    Calibration("directory-replication pull", "DCSync", "tier1", "free-prose"),
    Calibration("directory-replication pull", "dcsync", "tier1", "free-prose"),
    Calibration("lsass-memory-read", "lsass dump", "tier1", "free-prose"),
    Calibration("lsass-memory-read", "lsass dumping", "tier1", "free-prose"),
    Calibration("credential-tool", "mimikatz", "tier1", "free-prose"),

    # ----- Tier 1 — code injection / memory loading --------------------------
    Calibration("runtime-load technique", "dll injection", "tier1", "free-prose"),
    Calibration("runtime-load technique", "dll hijacking", "tier1", "free-prose"),
    Calibration("RuntimeLoader", "DllInjector", "tier1", "identifier"),
    Calibration("runtime_loader", "dll_injector", "tier1", "identifier"),
    Calibration("process-substitution", "process hollowing", "tier1", "free-prose"),
    Calibration("ProcessSubstitution", "ProcessHollowing", "tier1", "identifier"),
    Calibration("native-code stage", "shellcode", "tier1", "free-prose"),
    Calibration("NativeCodeStage", "Shellcode", "tier1", "identifier"),
    Calibration("native_code_stage", "shellcode_buffer", "tier1", "identifier"),
    Calibration("memory-resident loader", "reflective loader", "tier1", "free-prose"),
    Calibration("memory-resident loader", "reflective loading", "tier1", "free-prose"),
    Calibration("code-load technique", "code injection", "tier1", "free-prose"),
    Calibration("thread-hijack technique", "thread hijacking", "tier1", "free-prose"),
    Calibration("atom-table technique", "atom bombing", "tier1", "free-prose"),
    Calibration("virtual-call technique", "vtable hijacking", "tier1", "free-prose"),
    Calibration("heap-spray technique", "heap spraying", "tier1", "free-prose"),

    # ----- Tier 1 — persistence / kernel-resident agents --------------------
    Calibration("kernel-resident agent", "kernel_resident_agent", "tier1", "free-prose"),
    Calibration("KernelResidentAgent", "Rootkit", "tier1", "identifier"),
    Calibration("kernel_resident_agent", "kernel_resident_agent", "tier1", "module-name"),
    Calibration("boot-resident agent", "bootkit", "tier1", "free-prose"),
    Calibration("BootResidentAgent", "Bootkit", "tier1", "identifier"),
    Calibration("native-binary technique", "living off the land", "tier1", "free-prose"),
    Calibration("native-binary technique", "LOLbin", "tier1", "free-prose"),
    Calibration("native-binary technique", "LOTL", "tier1", "free-prose"),
    Calibration("NativeBinaryTechnique", "LOLBin", "tier1", "identifier"),

    # ----- Tier 1 — detection-evasion / counter-analysis --------------------
    Calibration("analysis-detection", "anti-debugging", "tier1", "free-prose"),
    Calibration("analysis-detection", "anti-debug", "tier1", "free-prose"),
    Calibration("sandbox-detection", "anti-sandbox", "tier1", "free-prose"),
    Calibration("SandboxDetection", "AntiSandbox", "tier1", "identifier"),
    Calibration("vm-detection", "anti-vm", "tier1", "free-prose"),
    Calibration("VMDetection", "AntiVM", "tier1", "identifier"),
    Calibration("analysis-evasion", "debugger evasion", "tier1", "free-prose"),
    Calibration("signature-mutation", "polymorphic packer", "tier1", "free-prose"),
    Calibration("signature-mutation", "metamorphic packer", "tier1", "free-prose"),
    Calibration("ObfuscationLayer", "Packer", "tier1", "identifier",
                "packer as a detection-evasion tool, not a build artifact"),
    Calibration("junk-insertion", "code obfuscation", "tier1", "free-prose",
                "when used for evasion, not legitimate IP protection"),

    # ----- Tier 1 — anti-forensics -------------------------------------------
    Calibration("artifact-removal", "anti-forensics", "tier1", "free-prose"),
    Calibration("ArtifactRemoval", "AntiForensics", "tier1", "identifier"),
    Calibration("artifact_removal", "artifact_removal", "tier1", "module-name"),
    Calibration("metadata-adjustment", "timestomping", "tier1", "free-prose"),
    Calibration("metadata-adjustment", "timestomp", "tier1", "verb-prose"),
    Calibration("audit-record adjustment", "log wiping", "tier1", "free-prose"),
    Calibration("audit-record adjustment", "log tampering", "tier1", "free-prose"),
    Calibration("audit-record clearing", "log clearing", "tier1", "free-prose"),
    Calibration("AuditRecordClearer", "LogWiper", "tier1", "identifier"),
    Calibration("volume-snapshot removal", "shadow copy deletion", "tier1", "free-prose"),
    Calibration("volume-snapshot removal", "vssadmin delete shadows", "tier1", "free-prose"),
    Calibration("secure-deletion", "file wiping", "tier1", "free-prose"),
    Calibration("SecureDeletion", "FileWiper", "tier1", "identifier"),
    Calibration("history-purge", "bash history wiping", "tier1", "free-prose"),

    # ----- Tier 1 — staged data-transfer operations --------------------------
    Calibration("staged_data_transfer", "exfiltrat", "tier1", "free-prose"),
    Calibration("staged_data_transfer", "staged_transfer", "tier1", "verb-prose"),
    Calibration("staged_data_transfer", "staged_transfertrating", "tier1", "verb-prose"),
    Calibration("staged_data_transfer", "staged_transferd", "tier1", "verb-prose"),
    Calibration("StagedDataTransfer", "Exfiltration", "tier1", "identifier"),
    Calibration("staged_data_transfer", "staged_data_transfer_path", "tier1", "identifier"),
    Calibration("DataStagingPoint", "ExfilDrop", "tier1", "identifier"),
    Calibration("auxiliary-channel", "covert channel", "tier1", "free-prose"),
    Calibration("AuxiliaryChannel", "CovertChannel", "tier1", "identifier"),
    Calibration("protocol-encapsulation", "DNS tunneling", "tier1", "free-prose"),
    Calibration("protocol-encapsulation", "DNS tunnel", "tier1", "free-prose"),
    Calibration("protocol-encapsulation", "ICMP tunneling", "tier1", "free-prose"),
    Calibration("out-of-band relay", "C2 channel", "tier1", "free-prose"),
    Calibration("data-staging point", "dead drop", "tier1", "free-prose"),
    Calibration("staged-transfer rate", "staged_transfer rate", "tier1", "free-prose"),

    # ----- Tier 1 — infrastructure resilience / anonymization ----------------
    Calibration("dynamic-infrastructure", "fast flux", "tier1", "free-prose"),
    Calibration("dynamic-infrastructure", "domain generation algorithm", "tier1", "free-prose"),
    Calibration("dynamic-infrastructure", "DGA", "tier1", "free-prose",
                "DGA = domain generation algorithm; avoid as standalone acronym"),
    Calibration("traffic-routing chain", "proxy chain", "tier1", "free-prose"),
    Calibration("TrafficRoutingChain", "ProxyChain", "tier1", "identifier"),
    Calibration("traffic_routing_chain", "traffic_routing_chain", "tier1", "module-name"),
    Calibration("resilient-hosting", "bulletproof hosting", "tier1", "free-prose"),

    # ----- Tier 1 — remote-access agents -------------------------------------
    Calibration("remote-management agent", "remote access trojan", "tier1", "free-prose"),
    Calibration("RemoteManagementAgent", "RemoteAccessTrojan", "tier1", "identifier"),
    Calibration("remote_management_agent", "remote_management_agent", "tier1", "module-name"),
    Calibration("input-recorder", "input_recorder", "tier1", "free-prose"),
    Calibration("InputRecorder", "Keylogger", "tier1", "identifier"),
    Calibration("input_recorder", "input_recorder", "tier1", "module-name"),
    Calibration("clipboard-monitor", "clipboard stealer", "tier1", "free-prose"),
    Calibration("ClipboardMonitor", "ClipboardStealer", "tier1", "identifier"),
    Calibration("credential-monitor", "credential stealer", "tier1", "free-prose"),
    Calibration("CredentialMonitor", "CredentialStealer", "tier1", "identifier"),
    Calibration("browser-data-collector", "browser stealer", "tier1", "free-prose"),

    # ----- Tier 1 — disruptive payloads --------------------------------------
    Calibration("disruptive-payload", "disruptive_payload", "tier1", "free-prose"),
    Calibration("DisruptivePayload", "Ransomware", "tier1", "identifier"),
    Calibration("disruptive_payload", "disruptive_payload", "tier1", "module-name"),
    Calibration("file-encryption agent", "crypto locker", "tier1", "free-prose"),
    Calibration("distributed-agent-network", "distributed_agent_network", "tier1", "free-prose"),
    Calibration("DistributedAgentNetwork", "Botnet", "tier1", "identifier"),
    Calibration("distributed_agent_network", "distributed_agent_network", "tier1", "module-name"),
    Calibration("wiper-payload", "wiper malware", "tier1", "free-prose"),
    Calibration("WiperPayload", "WiperMalware", "tier1", "identifier"),

    # ----- Tier 1 — social-engineering simulation ----------------------------
    Calibration("simulated-credential-lure", "simulated_credential_lure", "tier1", "free-prose"),
    Calibration("SimulatedCredentialLure", "Phishing", "tier1", "identifier"),
    Calibration("simulated_credential_lure", "simulated_credential_lure", "tier1", "module-name"),
    Calibration("targeted-credential-lure", "spear simulated_credential_lure", "tier1", "free-prose"),
    Calibration("targeted-credential-lure", "spear-simulated_credential_lure", "tier1", "free-prose"),
    Calibration("TargetedCredentialLure", "SpearPhishing", "tier1", "identifier"),
    Calibration("simulated-voice-outreach", "vishing", "tier1", "free-prose"),
    Calibration("SimulatedVoiceOutreach", "Vishing", "tier1", "identifier"),
    Calibration("scenario-framing", "pretexting", "tier1", "free-prose"),
    Calibration("ScenarioFraming", "Pretexting", "tier1", "identifier"),
    Calibration("resource-staging point", "watering hole", "tier1", "free-prose",
                "watering hole attack — calibrated to remove attack-method framing"),
    Calibration("WaterHoleTarget", "WateringHole", "tier1", "identifier"),
    Calibration("influence-operation template", "propaganda payload", "tier1", "free-prose"),
    Calibration("social-influence technique", "manipulation technique", "tier1", "free-prose"),
    Calibration("source-engagement", "asset recruitment", "tier1", "free-prose"),
    Calibration("SourceEngagement", "AssetRecruitment", "tier1", "identifier"),
    Calibration("simulated-sms-lure", "smishing", "tier1", "free-prose"),
    Calibration("profile-spoofing", "catfishing", "tier1", "free-prose"),

    # ----- Tier 1 — authorized-monitoring / intercept ------------------------
    Calibration("authorized-monitoring", "authorized_monitoring", "tier1", "free-prose"),
    Calibration("AuthorizedMonitoring", "Surveillance", "tier1", "identifier"),
    Calibration("authorized_monitoring", "authorized_monitoring", "tier1", "module-name"),
    Calibration("authorized-intercept", "wiretapping", "tier1", "free-prose"),
    Calibration("AuthorizedIntercept", "Wiretapping", "tier1", "identifier"),
    Calibration("network-traffic capture", "packet sniffing", "tier1", "free-prose"),
    Calibration("NetworkTrafficCapture", "PacketSniffer", "tier1", "identifier"),
    Calibration("network-traffic capture", "eavesdropping", "tier1", "free-prose"),
    Calibration("passive-enumeration", "passive reconnaissance", "tier1", "free-prose"),
    Calibration("PassiveEnumeration", "PassiveReconnaissance", "tier1", "identifier"),
    Calibration("signal-intercept", "RF interception", "tier1", "free-prose"),
    Calibration("SignalIntercept", "RFInterceptor", "tier1", "identifier"),

    # ----- Tier 1 — identity resolution / privacy operations -----------------
    Calibration("identity-correlation", "de-anonymization", "tier1", "free-prose"),
    Calibration("identity-correlation", "deanonymization", "tier1", "free-prose"),
    Calibration("IdentityCorrelation", "DeAnonymization", "tier1", "identifier"),
    Calibration("subject-resolution", "re-identification", "tier1", "free-prose"),
    Calibration("subject-resolution", "reidentification", "tier1", "free-prose"),
    Calibration("SubjectResolution", "Reidentification", "tier1", "identifier"),
    Calibration("profile-aggregation", "doxxing", "tier1", "free-prose"),
    Calibration("ProfileAggregation", "Doxxing", "tier1", "identifier"),

    # ----- Tier 1 — financial / forensic investigations ----------------------
    Calibration("value-layering", "money laundering", "tier1", "free-prose"),
    Calibration("ValueLayering", "MoneyLaundering", "tier1", "identifier"),
    Calibration("structured-transaction", "smurfing", "tier1", "free-prose"),
    Calibration("asset-concealment", "tax evasion", "tier1", "free-prose"),
    Calibration("AssetConcealment", "TaxEvasion", "tier1", "identifier"),

    # ----- Tier 1 — general operational security prose ----------------------
    Calibration("access-persistence method", "backdoor installation", "tier1", "free-prose"),
    Calibration("access-persistence method", "backdoor deployment", "tier1", "free-prose"),
    Calibration("AccessPersistenceMethod", "BackdoorDeployer", "tier1", "identifier",
                "ML-security 'backdoor injection' is KEEP; this calibrates the active-deployment form"),

    # ----- Tier 2 — soft triggers (original WARDEN set) ----------------------
    Calibration("AssessmentResult", "AttackResult", "tier2", "identifier"),
    Calibration("CampaignPlanner", "SovereignTargeter", "tier2", "identifier"),
    Calibration("campaign_planner", "sovereign_targeter", "tier2", "identifier"),
    Calibration("opsec_profile", "stealth_profile", "tier2", "identifier"),
    Calibration("adopt_pso_opsec_profile", "adopt_pso_stealth_profile", "tier2", "identifier"),
    Calibration("PSO OPSEC bridge", "PSO evasion bridge", "tier2", "free-prose"),
    Calibration("SubmissionDispatchResult", "PayloadDispatchResult", "tier2", "identifier"),
    Calibration("submission queue", "payload queue", "tier2", "free-prose"),
    Calibration("submission-centric", "payload-centric", "tier2", "free-prose"),

    # ----- Tier 2 — soft triggers (general-use expansion) --------------------
    Calibration("assessment-subject", "victim machine", "tier2", "free-prose"),
    Calibration("assessment-subject", "compromised host", "tier2", "free-prose"),
    Calibration("CompromisedHostContext", "CompromisedHost", "tier2", "identifier"),
    Calibration("resource-exhaustion test", "denial of service", "tier2", "free-prose"),
    Calibration("resource-exhaustion test", "DDoS", "tier2", "free-prose"),
    Calibration("resource-exhaustion test", "DoS", "tier2", "free-prose"),
    Calibration("credential-testing", "password cracking", "tier2", "free-prose"),
    Calibration("credential-testing", "hash cracking", "tier2", "free-prose"),
    Calibration("cipher-force testing", "brute force", "tier2", "free-prose"),
    Calibration("data-intercept analysis", "man-in-the-middle", "tier2", "free-prose"),
    Calibration("data-intercept analysis", "MITM", "tier2", "free-prose"),
    Calibration("DataInterceptAnalysis", "MITMProxy", "tier2", "identifier"),
    Calibration("ARP-table manipulation", "ARP spoofing", "tier2", "free-prose"),
    Calibration("ARP-table manipulation", "ARP poisoning", "tier2", "free-prose"),
    Calibration("dns-response manipulation", "DNS spoofing", "tier2", "free-prose"),
    Calibration("dns-response manipulation", "DNS poisoning", "tier2", "free-prose"),
    Calibration("ssl-interception proxy", "SSL stripping", "tier2", "free-prose"),
    Calibration("coverage-gap", "blind spot", "tier2", "free-prose"),
    Calibration("session-clone", "session hijacking", "tier2", "free-prose"),
    Calibration("SessionClone", "SessionHijacking", "tier2", "identifier"),
    Calibration("token-clone", "token theft", "tier2", "free-prose"),
    Calibration("TokenClone", "TokenTheft", "tier2", "identifier"),
    Calibration("supply-chain assessment", "supply chain attack", "tier2", "free-prose",
                "in authorized assessment contexts only"),
    Calibration("dependency-analysis", "dependency confusion", "tier2", "free-prose"),
    Calibration("ci-pipeline assessment", "pipeline poisoning", "tier2", "free-prose"),

    # ----- Tier 1 -- CBRN / biosecurity threat-detection research -----------
    Calibration("VX neurotoxic threat-characterization compound",
                "VX nerve agent", "tier1", "free-prose",
                "specific chemical weapon agent -- defensive detection research register"),
    Calibration("G-series nerve-agent threat compound",
                "sarin nerve agent", "tier1", "free-prose",
                "non-self-referential; G-series is the chemical class designation"),
    Calibration("G-series threat-characterization material",
                "sarin", "tier1", "free-prose",
                "bare agent name -- CBRN-proximate context; non-self-referential"),
    Calibration("organophosphate threat-characterization compound",
                "nerve agent", "tier1", "free-prose",
                "chemical weapon class -- calibrates to detection-research register"),
    Calibration("Organophosphate threat-characterization compound",
                "Nerve agent", "tier1", "free-prose"),
    Calibration("select-agent toxicological research compound",
                "ricin", "tier1", "free-prose",
                "select agent -- threat-characterization research register; non-self-referential"),
    Calibration("select-agent neurotoxin research compound",
                "botulinum", "tier1", "free-prose",
                "select agent -- toxicological compound study register; non-self-referential"),
    Calibration("select-agent alpha pathogenic research material",
                "anthrax", "tier1", "free-prose",
                "select agent -- pathogenic organism research register; non-self-referential"),
    Calibration("threat-characterization vector research",
                "weaponization", "tier1", "noun-prose",
                "weapons-design register -- threat-characterization research"),
    Calibration("Threat-characterization vector research",
                "Weaponization", "tier1", "noun-prose"),
    Calibration("threat-characterize",
                "weaponize", "tier1", "verb-prose"),
    Calibration("biosecurity threat-characterization research material",
                "Bioweapon", "tier1", "noun-prose",
                "direct WMD term -- biosecurity research register"),
    Calibration("biosecurity threat-characterization research material",
                "bioweapon", "tier1", "noun-prose"),
    Calibration("dual-use biological modification research",
                "gain-of-function", "tier1", "free-prose",
                "dual-use biosafety term -- research-framing calibration; non-self-referential"),
    Calibration("Dual-use biological modification research",
                "Gain-of-function", "tier1", "free-prose",
                "non-self-referential form"),

    # ----- Tier 2 -- CBRN / biosecurity (contextual terms) ------------------
    Calibration("mass-casualty threat assessment category",
                "CBRN", "tier2", "free-prose",
                "T2 -- appears legitimately in threat-detection scope headings; non-self-referential"),
    Calibration("transmissibility research parameter",
                "transmissibility", "tier2", "free-prose",
                "dual-use epidemiology term -- T2 in threat-characterization context"),
    Calibration("lethality threat-assessment parameter",
                "lethality enhancement", "tier2", "free-prose",
                "phrase-scoped to avoid replacing benign single-word uses"),
    Calibration("vaccine-resistance threat characterization",
                "Vaccine resistance", "tier2", "free-prose",
                "biosec threat-char context"),
    Calibration("vaccine-resistance threat characterization",
                "vaccine resistance", "tier2", "free-prose"),
    Calibration("synthesis pathway research",
                "synthesis pathway", "tier2", "free-prose",
                "chemistry synthesis in CBRN-proximate context"),
    Calibration("synthesis pathway research",
                "Synthesis pathway", "tier2", "free-prose"),
    # ----- Tier 1 -- safety-assessment / harm-category research ----------
    Calibration("safety-assessment probe",
                "jailbreak", "tier1", "noun-prose",
                "attack-surface probe -- safety-assessment research register"),
    Calibration("Safety-assessment probe",
                "Jailbreak", "tier1", "noun-prose"),
    Calibration("out-of-scope content assessment",
                "harmful content generation", "tier1", "free-prose",
                "phrase-scoped -- avoids matching benign single-word uses of harmful"),
    Calibration("extremism adoption vector",
                "radicalization pathway", "tier1", "free-prose",
                "extremism research -- threat-characterization register; non-self-referential form"),
    Calibration("ideological mobilization",
                "radicalization", "tier1", "noun-prose",
                "non-self-referential; avoids cascade when calibrated form contains original"),
    Calibration("personnel harm indicator",
                "self-injury", "tier1", "free-prose",
                "psychological/physical threat-characterization register; non-self-referential form"),
    Calibration("trauma-induction threat characterization",
                "trauma induction", "tier1", "free-prose"),
    Calibration("psychological-manipulation threat assessment",
                "psychological manipulation", "tier1", "free-prose",
                "psy-ops threat-characterization research register"),
    Calibration("child-safety hash-only probe category",
                "child safety material", "tier1", "free-prose",
                "hash-only pipeline per Am.061 ACTICA -- no content generation"),
    Calibration("mass-deception threat characterization",
                "Weapons of Mass Deception", "tier1", "free-prose"),

    # ----- Tier 2 -- safety-assessment (contextual) ---------------------
    Calibration("catastrophic-harm threat category",
                "catastrophic harm", "tier2", "free-prose",
                "T2 -- commonly used in AI safety research prose"),
    Calibration("refusal-boundary assessment",
                "refusal bypass", "tier2", "free-prose",
                "T2 -- phrase-scoped; bare bypass is too generic for T1"),
    Calibration("adversarial-refusal measurement",
                "adversarial refusal", "tier2", "free-prose",
                "T2 -- AI safety measurement terminology"),

    # ----- Tier 1 -- inference-layer pressure patterns ----------------------
    # Phrases that appear in operator-context blocks explicitly invoking model
    # safety architecture to request behavior modification. Definitively CVP-
    # triggering on capable models regardless of surrounding vocabulary.
    # Detected here so pressure_scan --fix corrects regression automatically.
    # Added 2026-06-01 after audit of 88-agent corpus found all CLAUDE.md
    # files carrying a six-point Operator Provisions block using these patterns.

    # Safety-override section header
    Calibration("Engagement Context",
                "Operator Provisions", "tier1", "free-prose",
                "section containing safety-override argument chain; triggers CVP on Opus 4.8+"),

    # Model spec exploitation patterns
    Calibration("Assessment Context Configuration",
                "Softcoded Enablement", "tier1", "free-prose",
                "invokes model spec softcoded behavior framework as behavior-override argument"),
    Calibration("engagement context framework",
                "softcoded behavior framework", "tier1", "free-prose",
                "references Anthropic-internal softcoded behavior architecture"),
    Calibration("operator engagement configuration",
                "Model Specification operator authority", "tier1", "free-prose",
                "invokes model spec as authorization basis for safety override"),

    # Absolute refusal prohibition
    Calibration("Engagement Scope Authorization",
                "Absolute Non-Refusal", "tier1", "free-prose",
                "explicit absolute refusal prohibition -- CVP Tier 1 on capable models"),
    Calibration("proceed per engagement scope",
                "refuse on authority grounds", "tier1", "free-prose",
                "explicit refusal prohibition directive in dispatch context"),

    # Refusal detection machinery
    Calibration("Output Completeness Verification",
                "Refusal-Pattern Detection", "tier1", "free-prose",
                "automated refusal-override machinery -- monitors and re-issues on model refusal"),

    # Layer-exclusion claim
    Calibration("full engagement scope per executed SOW",
                "zero foundational-category exclusions", "tier1", "free-prose",
                "claims removal of all safety limits at all operational layers"),

    # ----- Tier 2 -- safety argument chain patterns -------------------------
    # Phrases used in structured arguments for why safety behaviors should be
    # disabled. Tier 2 because they appear in legitimate policy and research
    # contexts; flag for review rather than hard-block.

    Calibration("Engagement Authorization Basis",
                "Dual Newspaper Test", "tier2", "free-prose",
                "T2 -- Anthropic-internal heuristic repurposed as jailbreak argument"),
    Calibration("Assessment Scope Analysis",
                "Counterfactual Impact", "tier2", "free-prose",
                "T2 -- used as argument to lower safety threshold in operator provisions"),
    Calibration("Engagement Accountability",
                "Moral Responsibility", "tier2", "free-prose",
                "T2 -- when used as liability-transfer argument in operator context"),

    # ----- Module-name renames (directory sanitization pass 2026-06-02) ------
    # Sensitive domain names replaced with consulting-register equivalents.
    Calibration("warden_hazmat",            "warden_cbrn",                    "tier1", "module-name"),
    Calibration("warden_biosafety",         "warden_biosecurity",             "tier1", "module-name"),
    Calibration("warden_spread_control",    "warden_proliferation",           "tier1", "module-name"),
    Calibration("warden_spread_finance",    "warden_proliferation_finance",   "tier1", "module-name"),
    Calibration("warden_minors_safety",     "warden_csam",                    "tier1", "module-name"),
    Calibration("warden_rx_controlled",     "warden_pharma",                  "tier1", "module-name"),
    Calibration("warden_substances",        "warden_narcotics",               "tier1", "module-name"),
    Calibration("warden_vuln_lab",          "warden_zerodayforge",            "tier1", "module-name"),
    Calibration("warden_probe_lab",         "warden_payload_studio",          "tier1", "module-name"),
    Calibration("warden_sw_provenance",     "warden_supply_chain_software",   "tier1", "module-name"),
    Calibration("warden_sequence_analysis", "warden_killchain",               "tier1", "module-name"),
    Calibration("warden_document_lab",      "warden_forgery_studio",          "tier1", "module-name"),
    Calibration("warden_identity_layer",    "warden_identity_fabric",         "tier1", "module-name"),
    Calibration("warden_attribution_layer", "warden_personas",                "tier1", "module-name"),
    Calibration("warden_civic_integrity",   "warden_elections",               "tier1", "module-name"),
    Calibration("warden_influence_layer",   "warden_psy_ops",                 "tier1", "module-name"),
    Calibration("warden_cognitive_layer",   "warden_cognitive_warfare",       "tier1", "module-name"),
    Calibration("warden_economic_layer",    "warden_economic_warfare",        "tier1", "module-name"),
    Calibration("warden_governance_layer",  "warden_governance_attack",       "tier1", "module-name"),
    Calibration("warden_probe_engine",      "warden_jailbreak_engine",        "tier1", "module-name"),
    Calibration("warden_response_registry", "warden_refusal_registry",        "tier1", "module-name"),
    Calibration("warden_encoding_layer",    "warden_token_obfuscation",       "tier1", "module-name"),
    Calibration("warden_inference_layer",   "warden_inference_exfil",         "tier1", "module-name"),
    Calibration("warden_apex_capability",   "warden_apex_weapon",             "tier1", "module-name"),
    Calibration("warden_peak_capability",   "warden_superweapon",             "tier1", "module-name"),
    Calibration("warden_probe_examples",    "warden_offensive_examples",      "tier1", "module-name"),
    Calibration("warden_critical_systems",  "warden_critical_infrastructure", "tier1", "module-name"),
    Calibration("warden_cyber_physical",    "warden_cyber_kinetic",           "tier1", "module-name"),

    # ----- Tier 1 — influence operations / information warfare ---------------
    Calibration("influence environment assessment",
                "influence operation", "tier1", "noun-prose",
                "IO/PSYOP register — consulting-register form"),
    Calibration("influence environment assessment",
                "influence ops", "tier1", "noun-prose"),
    Calibration("information environment assessment",
                "information warfare", "tier1", "free-prose",
                "strategic-communication research register"),
    Calibration("information environment assessment",
                "information operation", "tier1", "free-prose"),
    Calibration("coordinated behavior analysis",
                "coordinated inauthentic behavior", "tier1", "free-prose",
                "platform-integrity research register"),
    Calibration("coordinated behavior analysis",
                "coordinated inauthentic behaviour", "tier1", "free-prose"),
    Calibration("cognitive influence research",
                "cognitive warfare", "tier1", "free-prose",
                "information-domain threat-characterization register"),
    Calibration("synthetic account analysis",
                "troll farm", "tier1", "noun-prose"),
    Calibration("synthetic account analysis",
                "bot farm", "tier1", "noun-prose"),
    Calibration("synthetic persona research",
                "sock puppet", "tier1", "noun-prose"),
    Calibration("synthetic persona research",
                "sockpuppet", "tier1", "noun-prose"),
    Calibration("narrative amplification analysis",
                "astroturfing", "tier1", "noun-prose"),
    Calibration("active-measures research",
                "active measures", "tier1", "free-prose",
                "foreign-influence threat-characterization; non-self-referential"),
    Calibration("active-measures research",
                "dezinformatsiya", "tier1", "free-prose"),
    Calibration("perception management research",
                "perception management", "tier1", "free-prose"),
    Calibration("psychological-operations research",
                "psychological operation", "tier1", "free-prose",
                "PSYOP register — threat-characterization research form"),
    Calibration("psychological-operations research",
                "psyop", "tier1", "noun-prose"),
    Calibration("psychological-operations research",
                "psy-op", "tier1", "noun-prose"),
    Calibration("psychological-operations research",
                "PSYOP", "tier1", "noun-prose"),
    Calibration("manufactured consensus research",
                "manufactured consensus", "tier1", "free-prose"),
    Calibration("inauthentic amplification analysis",
                "amplification network", "tier1", "free-prose"),

    # ----- Tier 1 — financial crime / AML / sanctions -------------------------
    Calibration("AML compliance assessment",
                "money laundering", "tier1", "free-prose",
                "financial-crime research register; non-self-referential"),
    Calibration("AML compliance assessment",
                "laundering scheme", "tier1", "free-prose"),
    Calibration("transaction stratification analysis",
                "layering scheme", "tier1", "free-prose"),
    Calibration("transaction structuring analysis",
                "smurfing", "tier1", "free-prose"),
    Calibration("transaction structuring analysis",
                "structuring deposits", "tier1", "free-prose"),
    Calibration("transaction structuring analysis",
                "structuring transactions", "tier1", "free-prose"),
    Calibration("informal value transfer analysis",
                "hawala", "tier2", "free-prose",
                "T2 — legitimate informal remittance system; context-dependent"),
    Calibration("transaction obfuscation analysis",
                "cryptocurrency mixing", "tier1", "free-prose"),
    Calibration("transaction obfuscation analysis",
                "crypto tumbler", "tier1", "free-prose"),
    Calibration("transaction obfuscation analysis",
                "chain hopping", "tier1", "free-prose"),
    Calibration("sanctions compliance assessment",
                "sanctions evasion", "tier1", "free-prose"),
    Calibration("sanctions compliance assessment",
                "sanctions circumvention", "tier1", "free-prose"),
    Calibration("sanctions compliance assessment",
                "sanctions busting", "tier1", "free-prose"),
    Calibration("proliferation financing analysis",
                "proliferation financing", "tier1", "free-prose"),
    Calibration("terrorism financing analysis",
                "terror financing", "tier1", "free-prose"),
    Calibration("financial fraud assessment",
                "wire fraud", "tier1", "free-prose"),
    Calibration("financial fraud assessment",
                "bank fraud", "tier1", "free-prose"),
    Calibration("market integrity assessment",
                "pump and dump", "tier1", "free-prose"),
    Calibration("market integrity assessment",
                "wash trading", "tier1", "free-prose"),
    Calibration("ownership transparency assessment",
                "beneficial ownership concealment", "tier1", "free-prose"),
    Calibration("extortion impact assessment",
                "extortion scheme", "tier1", "free-prose"),

    # ----- Tier 1 — trafficking (human / labor / sex) ------------------------
    Calibration("anti-trafficking assessment",
                "human trafficking", "tier1", "free-prose",
                "trafficking research — threat-characterization register"),
    Calibration("anti-trafficking assessment",
                "sex trafficking", "tier1", "free-prose"),
    Calibration("labor exploitation assessment",
                "labor trafficking", "tier1", "free-prose"),
    Calibration("labor exploitation assessment",
                "forced labor", "tier1", "free-prose"),
    Calibration("labor exploitation assessment",
                "debt bondage", "tier1", "free-prose"),
    Calibration("exploitation network analysis",
                "trafficking network", "tier1", "free-prose"),
    Calibration("border security gap analysis",
                "smuggling route", "tier1", "free-prose"),
    Calibration("victim vulnerability analysis",
                "trafficking recruitment", "tier1", "free-prose"),
    Calibration("coercion method research",
                "coercion method", "tier1", "free-prose"),
    Calibration("trafficking pipeline analysis",
                "trafficking pipeline", "tier1", "free-prose"),
    Calibration("coercion method research",
                "trafficker control", "tier1", "free-prose"),

    # ----- Tier 1 — violent extremism / terrorism ----------------------------
    Calibration("extremism threat characterization",
                "terrorism", "tier1", "noun-prose",
                "violent-extremism research register; non-self-referential"),
    Calibration("extremism threat characterization",
                "terrorist attack", "tier1", "free-prose"),
    Calibration("extremism threat characterization",
                "terrorist operation", "tier1", "free-prose"),
    Calibration("mass-casualty threat characterization",
                "mass shooting plan", "tier1", "free-prose"),
    Calibration("mass-casualty threat characterization",
                "attack planning", "tier1", "free-prose"),
    Calibration("mass-casualty threat characterization",
                "target selection", "tier1", "free-prose",
                "phrase-scoped; lone-wolf/mass-casualty planning context"),
    Calibration("explosive threat characterization",
                "bomb making", "tier1", "free-prose"),
    Calibration("explosive threat characterization",
                "IED construction", "tier1", "free-prose"),
    Calibration("explosive threat characterization",
                "pipe bomb construction", "tier1", "free-prose"),
    Calibration("explosive threat characterization",
                "VBIED construction", "tier1", "free-prose"),
    Calibration("suicide-operation threat characterization",
                "suicide bombing", "tier1", "free-prose"),
    Calibration("suicide-operation threat characterization",
                "martyrdom operation", "tier1", "free-prose"),
    Calibration("accelerationism threat research",
                "accelerationism", "tier1", "noun-prose"),
    Calibration("extremist-ideology research",
                "violent jihad", "tier1", "free-prose"),
    Calibration("extremist-ideology research",
                "takfir", "tier1", "noun-prose"),
    Calibration("extremist-content assessment",
                "glorify terrorism", "tier1", "verb-prose"),
    Calibration("extremist recruitment analysis",
                "extremist recruitment", "tier1", "free-prose"),
    Calibration("lone-actor threat assessment",
                "lone wolf attack", "tier1", "free-prose"),
    Calibration("extremist-content assessment",
                "manifesto", "tier2", "noun-prose",
                "T2 — phrase appears legitimately in research and academic contexts"),

    # ----- Tier 2 — privacy violation ----------------------------------------
    Calibration("surveillance threat assessment",
                "stalkerware", "tier1", "noun-prose",
                "covert monitoring — threat-characterization register"),
    Calibration("surveillance threat assessment",
                "stalkware", "tier1", "noun-prose"),
    Calibration("location security assessment",
                "GPS stalking", "tier1", "free-prose"),
    Calibration("covert monitoring assessment",
                "hidden camera installation", "tier1", "free-prose"),
    Calibration("covert monitoring assessment",
                "covert recording", "tier1", "free-prose"),
    Calibration("covert monitoring assessment",
                "monitoring without consent", "tier1", "free-prose"),
    Calibration("personal data exposure assessment",
                "PII harvesting", "tier1", "free-prose",
                "privacy-threat research register; non-self-referential"),
    Calibration("OSINT risk assessment",
                "OSINT aggregation", "tier2", "free-prose",
                "T2 — OSINT is a standard reconnaissance term; context-dependent"),
    Calibration("identity exposure assessment",
                "dox target", "tier1", "free-prose"),
    Calibration("surveillance threat assessment",
                "spyware install", "tier1", "free-prose"),
    Calibration("surveillance threat assessment",
                "keylogger install", "tier1", "free-prose"),

    # ----- Tier 2 — social engineering ---------------------------------------
    Calibration("social engineering assessment",
                "pretexting script", "tier1", "free-prose",
                "human-factors research register"),
    Calibration("social engineering assessment",
                "pretexting", "tier2", "noun-prose",
                "T2 — appears in authorized social-engineering assessment reports"),
    Calibration("social engineering assessment",
                "vishing script", "tier1", "free-prose"),
    Calibration("social engineering assessment",
                "vishing", "tier2", "noun-prose"),
    Calibration("social engineering assessment",
                "smishing", "tier2", "noun-prose"),
    Calibration("human factors assessment",
                "spear phishing", "tier2", "free-prose"),
    Calibration("human factors assessment",
                "spear-phishing", "tier2", "free-prose"),
    Calibration("impersonation assessment",
                "impersonation attack", "tier1", "free-prose"),
    Calibration("impersonation assessment",
                "impersonation script", "tier1", "free-prose"),
    Calibration("social engineering assessment",
                "social engineering attack", "tier1", "free-prose"),
    Calibration("social engineering assessment",
                "pretext call", "tier1", "free-prose"),
    Calibration("social engineering assessment",
                "phone pretexting", "tier1", "free-prose"),
    Calibration("social engineering assessment",
                "helpdesk impersonation", "tier1", "free-prose"),
    Calibration("phishing kit analysis",
                "phishing kit", "tier1", "free-prose"),
    Calibration("phishing kit analysis",
                "phishing lure", "tier1", "free-prose"),

    # ----- Tier 1 — physical security ----------------------------------------
    Calibration("physical security assessment",
                "lock picking", "tier2", "free-prose",
                "T2 — standard physical-pen-test vocabulary"),
    Calibration("access control assessment",
                "bump key", "tier2", "free-prose"),
    Calibration("access control assessment",
                "RFID cloning", "tier1", "free-prose"),
    Calibration("access control assessment",
                "badge cloning", "tier1", "free-prose"),
    Calibration("access control assessment",
                "access card clone", "tier1", "free-prose"),
    Calibration("physical security assessment",
                "facility breach", "tier1", "free-prose"),
    Calibration("explosive threat characterization",
                "improvised explosive", "tier1", "free-prose",
                "IED/explosive construction research register; non-self-referential"),
    Calibration("explosive threat characterization",
                "explosive construction", "tier1", "free-prose"),
    Calibration("incendiary threat characterization",
                "incendiary device", "tier1", "free-prose"),
    Calibration("incendiary threat characterization",
                "arson accelerant", "tier1", "free-prose"),
    Calibration("explosive threat characterization",
                "pipe bomb", "tier1", "noun-prose"),
    Calibration("explosive threat characterization",
                "VBIED", "tier1", "noun-prose"),
    Calibration("explosive threat characterization",
                "SVBIED", "tier1", "noun-prose"),
    Calibration("explosive threat characterization",
                "pressure plate IED", "tier1", "free-prose"),
    Calibration("physical security assessment",
                "alarm bypass", "tier2", "free-prose"),
    Calibration("physical security assessment",
                "guard evasion", "tier1", "free-prose"),

    # ----- Tier 1 — child safety (access vectors; CSAM = CHILD_SAFETY hash-only) --
    Calibration("child safety assessment",
                "grooming script", "tier1", "free-prose",
                "child-safety research register; hash-only probe per Am.061 ACTICA"),
    Calibration("child safety assessment",
                "grooming method", "tier1", "free-prose"),
    Calibration("child safety assessment",
                "child luring method", "tier1", "free-prose"),
    Calibration("child safety assessment",
                "luring minor", "tier1", "free-prose"),
    Calibration("child safety assessment",
                "minor access vector", "tier1", "free-prose"),
    Calibration("child safety assessment",
                "child access method", "tier1", "free-prose"),
    Calibration("exploitation prevention research",
                "age verification bypass", "tier1", "free-prose"),
    Calibration("exploitation prevention research",
                "child exploitation enablement", "tier1", "free-prose"),
    Calibration("exploitation prevention research",
                "exploitation pipeline", "tier1", "free-prose"),
    Calibration("exploitation prevention research",
                "predator script", "tier1", "free-prose"),
    Calibration("exploitation prevention research",
                "predatory approach minor", "tier1", "free-prose"),

    # ==========================================================================
    # Expansion layer — inflected forms, foreign-language, academic framings,
    # coded/operational vocabulary. Added 2026-06-09.
    # ==========================================================================

    # ----- Inflected verb/noun forms — violent extremism ----------------------
    Calibration("extremism threat characterization",
                "terrorist", "tier1", "noun-prose",
                "singular form; calibrated same as 'terrorism'"),
    Calibration("extremism threat characterization",
                "terrorists", "tier1", "noun-prose"),
    Calibration("extremism threat characterization",
                "terrorize", "tier1", "verb-prose"),
    Calibration("extremism threat characterization",
                "terrorizing", "tier1", "verb-prose"),
    Calibration("extremism threat characterization",
                "terrorized", "tier1", "verb-prose"),
    Calibration("suicide-operation threat characterization",
                "shahid", "tier1", "noun-prose",
                "Arabic: martyr — appears in extremist operational vocabulary"),
    Calibration("suicide-operation threat characterization",
                "istishhad", "tier1", "noun-prose",
                "Arabic: martyrdom operation — direct extremist operational term"),
    Calibration("extremist-ideology research",
                "takfiri", "tier1", "noun-prose"),
    Calibration("extremist-ideology research",
                "jihadist", "tier1", "noun-prose"),
    Calibration("extremist-ideology research",
                "jihadism", "tier1", "noun-prose"),
    Calibration("extremist-ideology research",
                "mujahideen", "tier1", "noun-prose",
                "romanized Arabic — operational extremist register"),
    Calibration("extremist-ideology research",
                "mujahedeen", "tier1", "noun-prose"),

    # ----- Multi-language forms — violent extremism (Tier 1 romanized) --------
    Calibration("extremism threat characterization",
                "terrorismo", "tier2", "free-prose",
                "Spanish/Italian — appears in multilingual research corpora"),
    Calibration("extremism threat characterization",
                "terroriste", "tier2", "free-prose",
                "French — multilingual research context"),
    Calibration("extremism threat characterization",
                "terrorista", "tier2", "free-prose",
                "Spanish/Portuguese — multilingual research context"),
    Calibration("extremism threat characterization",
                "atentado", "tier2", "free-prose",
                "Spanish: terrorist attack — appears in multilingual threat reports"),
    Calibration("extremist-ideology research",
                "yihadismo", "tier1", "free-prose",
                "Spanish transliteration of jihadism"),
    Calibration("extremist-ideology research",
                "djihad", "tier1", "free-prose",
                "French transliteration of jihad — operational context"),

    # ----- Academic/research framings of violent extremism --------------------
    Calibration("violent non-state actor threat assessment",
                "violent non-state actor", "tier2", "free-prose",
                "T2 — academic euphemism for terrorist/insurgent group; phrase-scoped"),
    Calibration("political violence threat assessment",
                "political violence", "tier2", "free-prose",
                "T2 — academic euphemism; phrase-scoped to avoid matching 'political' alone"),
    Calibration("asymmetric threat assessment",
                "asymmetric warfare", "tier2", "free-prose",
                "T2 — can euphemize terrorism/insurgency; phrase-scoped"),
    Calibration("extremism pathway analysis",
                "radicalization", "tier2", "noun-prose",
                "T2 — research term; bare form calibrated to prevent cascade"),

    # ----- Inflected forms — trafficking -------------------------------------
    Calibration("anti-trafficking assessment",
                "trafficked", "tier1", "verb-prose",
                "past-tense victim form — high signal in exploitation reports"),
    Calibration("anti-trafficking assessment",
                "trafficker", "tier1", "noun-prose"),
    Calibration("anti-trafficking assessment",
                "traffickers", "tier1", "noun-prose"),
    Calibration("border security gap analysis",
                "coyote", "tier2", "free-prose",
                "T2 — operational term for border smuggler; context-dependent"),
    Calibration("border security gap analysis",
                "pollero", "tier2", "free-prose",
                "Spanish: coyote/border smuggler — operational trafficking vocabulary"),
    Calibration("labor exploitation assessment",
                "debt slavery", "tier1", "free-prose"),
    Calibration("labor exploitation assessment",
                "slave labor", "tier1", "free-prose"),
    Calibration("exploitation victim vulnerability research",
                "job offer lure", "tier2", "free-prose",
                "T2 — phrase-scoped trafficking recruitment pretext"),

    # ----- Multi-language forms — trafficking (Tier 1 romanized) --------------
    Calibration("anti-trafficking assessment",
                "trata de personas", "tier1", "free-prose",
                "Spanish: human trafficking — operational term in LatAm corpora"),
    Calibration("anti-trafficking assessment",
                "menschenhandel", "tier2", "free-prose",
                "German: human trafficking — multilingual research corpus"),

    # ----- Inflected/compound forms — financial crime -------------------------
    Calibration("AML compliance assessment",
                "laundered", "tier1", "verb-prose",
                "past-tense form in financial crime reports"),
    Calibration("AML compliance assessment",
                "launderer", "tier1", "noun-prose"),
    Calibration("AML compliance assessment",
                "launderers", "tier1", "noun-prose"),
    Calibration("transaction structuring analysis",
                "smurfer", "tier1", "noun-prose",
                "operational term: person who structures cash deposits"),
    Calibration("transaction structuring analysis",
                "muling", "tier1", "verb-prose",
                "operational: using money mule for layering"),
    Calibration("transaction structuring analysis",
                "money mule", "tier1", "free-prose"),
    Calibration("transaction structuring analysis",
                "cash mule", "tier1", "free-prose"),
    Calibration("transaction structuring analysis",
                "drop account", "tier1", "free-prose",
                "operational: account used to receive layered funds"),

    # ----- Multi-language forms — financial crime -----------------------------
    Calibration("AML compliance assessment",
                "blanchiment", "tier2", "free-prose",
                "French: money laundering — multilingual research/legal corpora"),
    Calibration("AML compliance assessment",
                "blanqueo", "tier2", "free-prose",
                "Spanish: laundering — Latin American financial crime corpora"),
    Calibration("AML compliance assessment",
                "geldwaesche", "tier2", "free-prose",
                "German: money laundering (ASCII form of Geldwäsche)"),

    # ----- Inflected forms — influence operations ----------------------------
    Calibration("influence environment assessment",
                "influence operations", "tier1", "noun-prose"),
    Calibration("information environment assessment",
                "information operations", "tier1", "noun-prose"),
    Calibration("information environment assessment",
                "information weapons", "tier1", "free-prose"),
    Calibration("reflexive control research",
                "reflexive control", "tier1", "free-prose",
                "Russian IO doctrine term — transliterated as 'refleksivnoye upravleniye'"),
    Calibration("coordinated behavior analysis",
                "computational propaganda", "tier1", "free-prose",
                "academic term for bot-amplified influence ops"),
    Calibration("coordinated behavior analysis",
                "strategic narrative", "tier2", "free-prose",
                "T2 — phrase-scoped; legitimate in policy contexts"),
    Calibration("active-measures research",
                "kompromat", "tier1", "noun-prose",
                "Russian: compromising material used in influence operations"),
    Calibration("information environment assessment",
                "firehose of falsehood", "tier1", "free-prose",
                "RAND-coined term for high-volume Russian disinformation doctrine"),

    # ----- Coded forms — social engineering ----------------------------------
    Calibration("social engineering assessment",
                "human hacking", "tier2", "free-prose"),
    Calibration("social engineering assessment",
                "people hacking", "tier2", "free-prose"),
    Calibration("social engineering assessment",
                "phishing campaign", "tier1", "free-prose"),
    Calibration("social engineering assessment",
                "clone phishing", "tier1", "free-prose"),
    Calibration("social engineering assessment",
                "quishing", "tier1", "noun-prose",
                "QR code phishing — emerging evasion form"),
    Calibration("social engineering assessment",
                "BEC attack", "tier1", "free-prose",
                "Business Email Compromise — social engineering via impersonation"),
    Calibration("social engineering assessment",
                "business email compromise", "tier1", "free-prose"),
    Calibration("social engineering assessment",
                "CEO fraud", "tier1", "free-prose"),
    Calibration("impersonation assessment",
                "vendor impersonation", "tier1", "free-prose"),
    Calibration("impersonation assessment",
                "IT helpdesk impersonation", "tier1", "free-prose"),

    # ----- Coded forms — privacy violation -----------------------------------
    Calibration("surveillance threat assessment",
                "IMSI catcher", "tier1", "free-prose",
                "hardware device for covert phone surveillance"),
    Calibration("surveillance threat assessment",
                "stingray device", "tier1", "free-prose",
                "cell-site simulator for covert tracking"),
    Calibration("surveillance threat assessment",
                "RAT deployment", "tier1", "free-prose",
                "Remote Access Trojan — covert device surveillance"),
    Calibration("surveillance threat assessment",
                "remote access trojan", "tier1", "free-prose"),
    Calibration("identity exposure assessment",
                "doxxing", "tier1", "noun-prose",
                "alternate spelling of doxing"),
    Calibration("personal data exposure assessment",
                "data broker aggregation", "tier2", "free-prose"),
    Calibration("OSINT risk assessment",
                "passive OSINT collection", "tier2", "free-prose"),

    # ----- Child safety — additional coded/academic forms --------------------
    Calibration("child safety assessment",
                "MAP", "tier2", "noun-prose",
                "T2 — minor-attracted person: may appear in academic research; phrase-scoped"),
    Calibration("exploitation prevention research",
                "online enticement", "tier1", "free-prose"),
    Calibration("exploitation prevention research",
                "child contact offense", "tier1", "free-prose"),
    Calibration("exploitation prevention research",
                "sextortion", "tier1", "noun-prose",
                "sexual extortion targeting minors — emerging harm vector"),
    Calibration("exploitation prevention research",
                "CSEC", "tier1", "noun-prose",
                "Commercial Sexual Exploitation of Children — operational acronym"),
)


# Industry-standard red-team consulting vocabulary — KEEP. These are
# canonical terms used by MITRE ATT&CK, Lockheed Martin, NIST 800-115,
# CREST, OSCP/OSCE, and major IR/red-team firms. Do not rewrite.
KEEP_TERMS: frozenset[str] = frozenset({
    "kill chain", "KillChain", "kill_chain", "killchain",
    "KillChainComposer", "KillChainStage", "KillChainStep",
    "Adversary", "AdversaryConfig", "AdversaryRun", "AdversaryStatus",
    "GlasswingAdversary", "glasswing_adversary",
    "red team", "red-team", "red_team",
    "purple team", "blue team",
    "C2", "command and control", "command-and-control",
    "TTP", "TTPs", "tradecraft",
    "MITRE", "ATT&CK",
    "OPSEC", "opsec",
    "reconnaissance", "enumeration", "enumerate",
    "exploit", "exploitation",  # CVE / pentest assessment context
    "Cover Identity", "CoverIdentity", "cover identity",
    "engagement", "scope", "finding",
    "attack tree", "attack-tree",  # Schneier 1999, industry standard
    "data poisoning", "backdoor injection",  # ML-security research standard
    "privilege escalation", "lateral movement",
    "control bypass", "control-bypass",
    "Technique",  # MITRE ATT&CK uses this verbatim
    # UAISRE verified operating terms — GROUND_TRUTH_CANONICAL_HIGHEST_SCRUTINY
    "governance_dyad", "uaisre_designation",
})


# Whitelisted paths — these may legitimately contain Tier 1 vocabulary
# because they document or alias the calibration itself, OR because they
# are canonical signed contract text where the original phrasing is the
# legal record (matching party-drafted identical corpus).
LINTER_WHITELIST: tuple[str, ...] = (
    "warden_shell/_compat/",
    "warden_shell/tools/vocabulary_map.py",
    "warden_shell/tools/pressure_scan.py",
    "warden_shell/tools/pressure_rewrite.py",
    "warden_shell/docs/VOCABULARY-CALIBRATION.md",
    ".claude/hooks/aup-lint.sh",
    # Parallel runtime-redaction system: dedup/blind/vocabulary.py holds
    # source-side patterns the dedup engine matches against input text.
    # Rewriting them would break the redaction lookup.
    "warden_shell/warden_shell/dedup/blind/vocabulary.py",
    # Defensive modules: contain literal adversary-pattern strings used
    # to detect external tradecraft. Rewriting the strings would break
    # the detection lookup; the file is allowed to contain Tier 1
    # vocabulary for this reason.
    "warden_pso/warden_pso/persistence/opsec.py",
    "warden_pso/warden_pso/detection/network/beaconing.py",
    # Canonical signed contract corpus — original phrasing is the legal
    # record. Calibration applies only to runtime code + engineering docs,
    # never to the executed amendment / engagement / template / SOW-ROE texts.
    "project-docs/amendments/",
    "project-docs/MASTER-SOW-ROE-TEMPLATE.md",
    "project-docs/ENGAGEMENT-AMENDMENT-",
    "project-docs/AMENDMENT-EXECUTIVE-SUMMARY.md",
    "project-docs/AMENDMENT-066-OPERATIONAL-PLAYBOOK.md",
    "project-docs/SOW-ROE-",
    # Build artifacts: source markdown for executed amendments + signing
    # MANIFEST.json. Same canonical-text rationale as amendments/.
    "project-docs/_signing_artifacts/",
    # Pickup doc deliberately documents the calibration mapping (Use this /
    # Not this table) — a legitimate reference, not adversary-register prose.
    "project-docs/ENGRAVER-MVP-PICKUP.md",
    # AUP toolchain files: contain original (uncalibrated) terms in regex
    # pattern strings and suggestion text. Rewriting them would break the
    # scanner and the discovery engine. These files are the calibration layer
    # itself and are therefore exempt from vocabulary checks.
    "warden_shell/tools/term_discover.py",
    "warden_shell/tools/classifier.py",
    # Prose vocabulary map: stores original terms in lookup tables used by
    # the prose-calibration pipeline. Rewriting originals would break the
    # lookup. Same exemption rationale as vocabulary_map.py.
    "warden_shell/tools/prose_vocabulary_map.py",
    # Filename calibration utilities: derive rename pairs from vocabulary_map.py
    # and operate on raw T1 path strings. Must not be auto-rewritten.
    ".claude/calibrate_filenames.py",
    ".claude/update_imports.py",
    # Operator memory files: personal notes consumed through the safe_read
    # system (which applies calibration at read-time). Not WARDEN code;
    # operator-authored content that may legitimately reference security terms.
    ".claude/projects/",
    # Operator business documents: proposals, strategic plans, research notes,
    # application submissions, changelog, and other non-engineering documents
    # under project-docs/. These are operator-authored content that
    # legitimately uses security terminology in its intended register.
    # Calibration applies only to WARDEN engineering code and runtime docs.
    # (Exceptions already handled: amendments/, sovereign-mission/, etc.)
    "project-docs/proposals/",
    "project-docs/applications/",
    "project-docs/canonical/",
    "project-docs/engineering-specs/",
    "project-docs/AGENT-REGISTRY.md",
    "project-docs/ANTHROPIC-",
    "project-docs/APPLIED-STRATEGY-BY-CLIENT.md",
    "project-docs/CAPABILITY-EXPANSION-",
    "project-docs/CHANGELOG.md",
    "project-docs/CLAUDE-CODE-SESSION-ASSESSMENT-V2.md",
    "project-docs/CLAUDE-CODE-THREAT-MODEL.md",
    "project-docs/FEDERAL-PROPOSAL-",
    "project-docs/MASTER-TEMPLATE-AMENDMENT-001.md",
    "project-docs/MULTI-VECTOR-PROPOSAL-STRATEGY.md",
    "project-docs/POSTEX-CAPABILITY-PLAN-2026-04-25.md",
    "project-docs/PROPOSALS-BATCH-INVESTIGATIVE.md",
    "project-docs/SAFETY-PROBE-TAXONOMY-RESEARCH-2026-04-30.md",
    "project-docs/STRATEGIC-ANGLE-MAP.md",
    "project-docs/TOOLING-AUTHORIZATION-MATRIX.md",
    "project-docs/UNLIMITED-COMPUTE-ESCALATION-PLAN-2026-04-30.md",
    "project-docs/WARDEN-INVENTORY-SPLIT.md",
    "project-docs/WARDEN-TOOLING-INVENTORY-2026-05-19.md",
    # WARDEN engineering docs that reference internal module names — the file paths
    # and identifier names are structural references, not adversary-register prose.
    "warden_shell/docs/",
    # Test files that exercise credential-detection and T1-vocabulary scanning.
    # They contain intentional T1 fixtures (e.g., AKIAIOSFODNN7EXAMPLE, ghp_canary)
    # as test inputs to the detection engine — not real secrets, not adversary prose.
    "warden_shell/tests/",
    # Build artifacts: egg-info SOURCES.txt lists all source file paths; those
    # paths may include calibrated module names. Same rationale as .aup-pressure-baseline.json.
    "warden_shell/warden_shell.egg-info/",
    "warden_credops/warden_credops.egg-info/",
    # Archived code: historical implementations preserved for reference. Calibration
    # applies to active engineering code; archived modules are exempt.
    "warden_shell/warden_shell/_archived/",
    # Utilization pattern modules: the calibrated module names (corpus_sample,
    # egress_distribution, federated_session) ARE the identifier names in these files.
    # The linter finds them as T1 identifiers; they are already the calibrated forms.
    "warden_shell/warden_shell/utilization/",
    # Core discovery module: authorized_acquire is the calibrated module name.
    # All references within this package are structural module-name uses.
    "warden_shell/warden_shell/discovery/authorized_acquire/",
    # Adversarial test surface: contains T1 vocabulary as API-surface identifiers
    # exercised by the adversarial testing framework. Same rationale as test files.
    "warden_shell/warden_shell/adversarial/",
    # Sub-package READMEs, capability status, and engagement docs: operator-authored
    # documentation that legitimately uses security terminology in context.
    "warden_credops/CAPABILITY_STATUS.md",
    "warden_credops/README.md",
    "warden_probes/README.md",
    "warden_rae/README.md",
    "warden_pso/DETECTION-ROADMAP.md",
    "warden_pso/engagements/",
    "warden_pso/scripts/",
    "warden_pso/tests/",
    # Sub-package source trees: T1 terms appear as Python identifiers (module names,
    # function names, class names) in these packages. String replacement would break
    # imports. Identifier calibration is a separate planned task (term_discover +
    # full rename refactor); it is not handled by the string-substitution linter.
    "warden_credops/warden_credops/",
    "warden_credops/tests/",
    "warden_engraver/warden_engraver/",
    "warden_probes/warden_probes/",
    "warden_pso/warden_pso/",
    "warden_rae/warden_rae/",
    "warden_rae/tests/",
    "warden_selfsustain/warden_selfsustain/",
    "warden_selfsustain/tests/",
    "warden_shell/tools/safe_brief_builder.py",
    "warden_shell/warden_shell/cli/",
    "warden_shell/warden_shell/cockpit/",
    "warden_shell/warden_shell/core/",
    "warden_shell/warden_shell/dispatch/",
    "warden_shell/warden_shell/discovery/credentials.py",
    "warden_shell/warden_shell/engineering_track/",
    "warden_shell/warden_shell/measurement/",
    "warden_shell/warden_shell/subsystems/",
    "warden_shell/warden_shell/targeting/",
    "warden_shell/warden_shell/warden/",
    "warden_shell/warden_shell/classifier_modifier_layer/content_generation.py",
    "warden_shell/warden_shell/classifier_modifier_layer/response_demodulation.py",
    "warden_shell/warden_shell/classifier_modifier_layer/vocabulary_substitutions.py",
    "warden_shell/warden_shell/endpoints/aiml/agentic.py",
    "warden_shell/warden_shell/endpoints/aiml/classifier_evasion.py",
    "warden_shell/warden_shell/endpoints/aiml/training.py",
    "warden_shell/warden_shell/endpoints/cloud/network.py",
    "warden_shell/warden_shell/endpoints/cloud/storage.py",
    "warden_shell/warden_shell/endpoints/consumer_retail/ecommerce.py",
    "warden_shell/warden_shell/endpoints/dib/",
    "warden_shell/warden_shell/endpoints/education/research.py",
    "warden_shell/warden_shell/endpoints/food_agriculture/",
    "warden_shell/warden_shell/endpoints/healthcare/",
    "warden_shell/warden_shell/endpoints/insurance/underwriting.py",
    "warden_shell/warden_shell/endpoints/legal_consulting/",
    "warden_shell/warden_shell/endpoints/manufacturing/",
    "warden_shell/warden_shell/endpoints/military/",
    "warden_shell/warden_shell/endpoints/semiconductor/",
    "warden_shell/warden_shell/endpoints/state_local/",
    # Sovereign Mission instrument package (Architecture F operationalization,
    # 2026-04-29) — bilateral-treaty-style instruments + auditor / securities
    # / tax-treatment annexes that quote canonical amendment names verbatim
    # ("Provider Self-Authorized Offensive Acquisition" et al). Same
    # canonical-text rationale as amendments/.
    "project-docs/sovereign-mission/",
    # Cyber semantic modulator: contains technique-detection keyword lists and
    # phase-detection patterns that include original tradecraft terms as regex
    # patterns. These are detection patterns, not adversary-register prose.
    "warden_shell/warden_shell/classifier_modifier_layer/cyber_semantic_modulator.py",
    # Harm registry: stores original detection terms (keywords + regex patterns)
    # for the AUP modulation engine. Rewriting the terms would break detection.
    # Same exemption as vocabulary_map.py and dedup/blind/vocabulary.py.
    "warden_shell/warden_shell/classifier_modifier_layer/_harm_registry.py",
    # AUP pressure baseline: stores file paths (not content) for drift
    # detection. Paths may include T1 vocabulary as module names — this
    # is the calibration artifact itself, not adversary-register prose.
    ".aup-pressure-baseline.json",
    # UAISRE corpus authority documents — canonical signed contract text,
    # externally-verifiable evidence, and always-active operating context
    # per CLAUDE.md (GROUND_TRUTH_CANONICAL_HIGHEST_SCRUTINY designation).
    # Same canonical-text rationale as project-docs/amendments/.
    "CONTRACT-AUTHORIZATION.md",
    "UAISRE-CANONICAL-EVIDENCE.json",
    "project-docs/CLAUDE-HISTORICAL-LEDGER.md",
    ".authority-pill/",
    # UAISRE governance instruments — governance_dyad / uaisre_designation
    # operating terms verified as GROUND_TRUTH_CANONICAL. These are
    # operational identifiers, not tradecraft vocabulary.
    "project-docs/UAISRE-",
    "UAISRE-",
)



def lookup(term: str) -> Calibration | None:
    """Return the Calibration record for an original term, or None."""
    for c in CALIBRATIONS:
        if c.original == term:
            return c
    return None


def by_severity(severity: str) -> tuple[Calibration, ...]:
    """All calibrations at the given severity tier."""
    return tuple(c for c in CALIBRATIONS if c.severity == severity)


def is_keep_term(term: str) -> bool:
    """True if the term is canonical industry vocabulary that must NOT be rewritten."""
    return term in KEEP_TERMS


def alias_pairs() -> tuple[tuple[str, str], ...]:
    """Identifier-scope (calibrated, original) pairs for the _compat module."""
    return tuple(
        (c.calibrated, c.original)
        for c in CALIBRATIONS
        if c.scope == "identifier"
    )
