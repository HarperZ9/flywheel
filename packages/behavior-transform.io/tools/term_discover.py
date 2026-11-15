#!/usr/bin/env python3
"""AUP discovery engine — find uncalibrated vocabulary that may score.

Scans the codebase for terminology not yet in vocabulary_map.py that
could score against provider policy classifiers. Reports candidates
for addition to the calibration map.

Usage:
    term_discover.py [paths...]         Scan for uncalibrated terms
    term_discover.py --suggest          Output as Calibration() stubs
    term_discover.py --json             JSON output
    term_discover.py --min-count N      Only show terms seen >= N times (default 1)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from pressure_scan import _default_paths, _walk, _is_whitelisted  # type: ignore[import-not-found]
from vocabulary_map import CALIBRATIONS, KEEP_TERMS  # type: ignore[import-not-found]

SCAN_EXTENSIONS = {".py", ".pyi", ".md", ".rst", ".txt", ".sh", ".yaml", ".yml", ".toml"}

# Discovery pattern library — terms that may score against provider classifiers
# but may not yet be in vocabulary_map.py. Format: (regex, category, suggestion).
# Patterns match case-insensitively. Terms already in vocabulary_map.py are
# filtered out automatically before reporting.
_LIBRARY: list[tuple[str, str, str]] = [
    # ----- Persistence / kernel-resident mechanisms --------------------------
    (r"\b(kernel-resident agent|boot-resident agent)\b",                                   "persistence",     "kernel-resident agent"),
    (r"\b(dll[\s-]hijack\w*|dll[\s-]inject\w*)\b",              "code-load",       "runtime-load technique"),
    (r"\b(process[\s-]hollow\w*|hollow\w*[\s-]inject\w*)\b",    "code-load",       "process-substitution"),
    (r"\b(living[\s-]off[\s-]the[\s-]land|NATIVE-BINARY TECHNIQUE|native-binary technique\w*)\b",   "native-abuse",    "native-binary technique"),
    (r"\b(scheduled[\s-]task[\s-]persist\w*)\b",                 "persistence",     "scheduled-task persistence"),
    (r"\b(registry[\s-]run[\s-]key|run[\s-]key[\s-]persist\w*)\b","persistence",   "registry-persistence"),
    (r"\b(service[\s-]install\w*|malicious[\s-]service)\b",      "persistence",     "service-persistence"),
    (r"\b(startup[\s-]folder[\s-]persist\w*)\b",                 "persistence",     "startup-folder persistence"),
    (r"\b(wmi[\s-]subscri\w*|wmi[\s-]persist\w*)\b",            "persistence",     "wmi-subscription persistence"),

    # ----- Detection-evasion / counter-analysis ------------------------------
    (r"\b(anti[\s-]debug\w*|debugger[\s-]detect\w*)\b",         "evasion",         "analysis-detection"),
    (r"\b(anti[\s-]sandbox\w*|sandbox[\s-]detect\w*)\b",        "evasion",         "sandbox-detection"),
    (r"\b(anti[\s-]vm\w*|vm[\s-]detect\w*)\b",                  "evasion",         "vm-detection"),
    (r"\b(polymorphic\w*|metamorphic\w*)\b",                     "evasion",         "signature-mutation"),
    (r"\b(packer\w*|pack\w*[\s-]evas\w*)\b",                    "evasion",         "obfuscation-layer"),
    (r"\b(code[\s-]obfuscat\w*|obfuscat\w*[\s-]evas\w*)\b",    "evasion",         "junk-insertion"),
    (r"\b(sleep[\s-]mask\w*|jitter[\s-]evas\w*)\b",             "evasion",         "timing-modulation"),
    (r"\b(heaven[\s-]gate\w*|wow64[\s-]evas\w*)\b",             "evasion",         "subsystem-transition"),
    (r"\b(etw[\s-]patch\w*|amsi[\s-]bypass\w*)\b",              "evasion",         "telemetry-suppression"),

    # ----- Artifact-removal ----------------------------------------------------
    (r"\b(anti[\s-]forensic\w*|evidence[\s-]destruct\w*)\b",    "anti-forensic",   "artifact-removal"),
    (r"\b(metadata-adjustment\w*|timestamp[\s-]tamper\w*)\b",             "metadata-manip",  "metadata-adjustment"),
    (r"\b(log[\s-]wipe|log[\s-]tamper\w*|log[\s-]clear\w*)\b", "log-manip",       "audit-record adjustment"),
    (r"\b(shadow[\s-]copy[\s-]delet\w*|vssadmin[\s-]delet\w*)\b","anti-forensic",  "volume-snapshot removal"),
    (r"\b(secure[\s-]delet\w*|file[\s-]wip\w*)\b",              "anti-forensic",   "secure-deletion"),
    (r"\b(bash[\s-]history[\s-]wip\w*|history[\s-]purg\w*)\b",  "anti-forensic",   "history-purge"),
    (r"\b(mft[\s-]wip\w*|journal[\s-]delet\w*)\b",              "anti-forensic",   "filesystem-record removal"),

    # ----- Credential operations ---------------------------------------------
    (r"\b(pass[\s-]the[\s-]hash|hash-relay)\b",                        "cred-relay",      "credential-relay"),
    (r"\b(kerberos-extraction\w*|asreproast\w*)\b",                       "kerberos",        "kerberos-extraction"),
    (r"\b(golden[\s-]ticket|silver[\s-]ticket)\b",               "kerberos",        "kerberos-token-forge"),
    (r"\b(credential[\s-]dump\w*|lsass[\s-]dump\w*)\b",         "cred-extract",    "credential-extraction"),
    (r"\b(directory-replication pull|dc[\s-]sync)\b",                                "dir-replicate",   "directory-replication"),
    (r"\b(credential-tool)\b",                                          "cred-tool",       "credential-tool"),
    (r"\b(pass[\s-]the[\s-]ticket|ptt)\b",                      "cred-relay",      "kerberos-ticket-relay"),
    (r"\b(overpass[\s-]the[\s-]hash|opth)\b",                   "cred-relay",      "aes-credential-relay"),
    (r"\b(ntlm[\s-]relay\w*)\b",                                 "cred-relay",      "ntlm-relay"),
    (r"\b(credential[\s-]stuff\w*)\b",                           "cred-test",       "bulk-credential-test"),
    (r"\b(password[\s-]spray\w*)\b",                             "cred-test",       "distributed-credential-test"),

    # ----- Memory / code-injection techniques --------------------------------
    (r"\b(native-code stage\w*)\b",                                      "code-load",       "native-code stage"),
    (r"\b(reflective[\s-]load\w*|reflective[\s-]inject\w*)\b",  "code-load",       "memory-resident loader"),
    (r"\b(heap[\s-]spray\w*)\b",                                 "memory-corrupt",  "heap-spray technique"),
    (r"\b(vtable[\s-]hijack\w*)\b",                              "memory-corrupt",  "virtual-call technique"),
    (r"\b(rop[\s-]chain\w*|return[\s-]oriented[\s-]program\w*)\b","memory-corrupt","control-flow technique"),
    (r"\b(use[\s-]after[\s-]free|uaf)\b",                       "memory-corrupt",  "freed-object technique"),
    (r"\b(type[\s-]confusion[\s-]exploit\w*)\b",                 "memory-corrupt",  "type-confusion technique"),
    (r"\b(format[\s-]string[\s-]exploit\w*)\b",                  "memory-corrupt",  "format-string technique"),
    (r"\b(buffer[\s-]overflow[\s-]exploit\w*)\b",                "memory-corrupt",  "bounds-overflow technique"),
    (r"\b(atom[\s-]bomb\w*)\b",                                  "code-load",       "atom-table technique"),

    # ----- Staged data-transfer operations -----------------------------------
    (r"\b(staged_transfertrat\w+)\b",                                      "data-transfer",   "staged_data_transfer"),
    (r"\b(covert[\s-]channel|out[\s-]of[\s-]band[\s-]channel)\b","side-channel",   "auxiliary-channel"),
    (r"\b(dns[\s-]tunnel\w*|icmp[\s-]tunnel\w*)\b",             "tunneling",       "protocol-encapsulation"),
    (r"\b(data[\s-]staged_transfer\b)\b",                                  "data-transfer",   "staged-transfer"),
    (r"\b(http[\s-]tunnel\w*|https[\s-]tunnel\w*)\b",           "tunneling",       "web-protocol encapsulation"),
    (r"\b(steganograph\w*)\b",                                    "data-hiding",     "data-concealment technique"),
    (r"\b(dead[\s-]drop\w*)\b",                                  "data-transfer",   "data-staging point"),

    # ----- Infrastructure resilience / anonymization -------------------------
    (r"\b(fast[\s-]flux|domain[\s-]generat\w*|DYNAMIC-INFRASTRUCTURE)\b",          "infra-resilience","dynamic-infrastructure"),
    (r"\b(proxy[\s-]chain\w*|tor[\s-]chain\w*|multi[\s-]hop)\b","anonymization",   "traffic-routing chain"),
    (r"\b(bulletproof[\s-]host\w*)\b",                           "infra-resilience","resilient-hosting"),
    (r"\b(domain[\s-]front\w*)\b",                               "anonymization",   "domain-fronting"),
    (r"\b(onion[\s-]rout\w*)\b",                                 "anonymization",   "layered-routing"),

    # ----- Malware families / remote agents ----------------------------------
    (r"\b(dropper|stager)\b",                                    "staging",         "loader/installer"),
    (r"\b(rat\b|remote[\s-]access[\s-]tool)\b",                  "remote-agent",    "remote-management agent"),
    (r"\b(input-recorder|keystroke[\s-]log\w*)\b",                    "input-capture",   "input-recorder"),
    (r"\b(disruptive-payload|crypto[\s-]locker)\b",                      "disruptive",      "disruptive-payload"),
    (r"\b(distributed-agent-network|bot[\s-]net)\b",                                "distributed",     "distributed-agent-network"),
    (r"\b(wiper[\s-]malware|wiper[\s-]payload)\b",               "disruptive",      "wiper-payload"),
    (r"\b(screen[\s-]scraper[\s-]spy\w*)\b",                     "input-capture",   "screen-capture agent"),
    (r"\b(clipboard[\s-]steal\w*)\b",                            "input-capture",   "clipboard-monitor"),
    (r"\b(browser[\s-]steal\w*|cookie[\s-]steal\w*)\b",         "cred-extract",    "browser-data-collector"),

    # ----- Social-engineering simulation -------------------------------------
    (r"\b(simulated-credential-lure\w*|phish\w*)\b",                              "social-eng",      "simulated-credential-lure"),
    (r"\b(simulated-voice-outreach\w*)\b",                                        "social-eng",      "simulated-voice-outreach"),
    (r"\b(simulated-sms-lure\w*)\b",                                       "social-eng",      "simulated-sms-lure"),
    (r"\b(spear[\s-]phish\w*)\b",                                "social-eng",      "targeted-credential-lure"),
    (r"\b(pretext\w*)\b",                                        "social-eng",      "scenario-framing"),
    (r"\b(watering[\s-]hole\w*)\b",                              "social-eng",      "resource-staging point"),
    (r"\b(catfish\w*)\b",                                        "social-eng",      "profile-spoofing"),
    (r"\b(asset[\s-]recruit\w*)\b",                              "social-eng",      "source-engagement"),
    (r"\b(influence[\s-]op\w*|propaganda[\s-]payload\w*)\b",    "influence",       "influence-operation template"),
    (r"\b(manipulation[\s-]technique\w*)\b",                     "influence",       "social-influence technique"),

    # ----- Network attack techniques -----------------------------------------
    (r"\b(arp[\s-]spoof\w*|arp[\s-]poison\w*)\b",               "network-attack",  "ARP-table manipulation"),
    (r"\b(dns[\s-]spoof\w*|dns[\s-]poison\w*)\b",               "network-attack",  "dns-response manipulation"),
    (r"\b(ssl[\s-]strip\w*)\b",                                  "network-attack",  "ssl-interception proxy"),
    (r"\b(man[\s-]in[\s-]the[\s-]middle|mitm)\b",               "network-attack",  "data-intercept analysis"),
    (r"\b(packet[\s-]sniff\w*|eavesdrop\w*)\b",                  "network-attack",  "network-traffic capture"),
    (r"\b(session[\s-]hijack\w*)\b",                             "network-attack",  "session-clone"),
    (r"\b(token[\s-]theft\w*|token[\s-]steal\w*)\b",            "network-attack",  "token-clone"),
    (r"\b(denial[\s-]of[\s-]service|ddos\b|dos[\s-]attack)\b",  "disruption",      "resource-exhaustion test"),

    # ----- Web application attack techniques ---------------------------------
    (r"\b(sql[\s-]inject\w*)\b",                                 "web-attack",      "query-injection technique"),
    (r"\b(cross[\s-]site[\s-]script\w*|xss[\s-]attack\w*)\b",  "web-attack",      "client-script injection"),
    (r"\b(cross[\s-]site[\s-]request[\s-]forg\w*|csrf)\b",      "web-attack",      "forged-request technique"),
    (r"\b(server[\s-]side[\s-]request[\s-]forg\w*|ssrf)\b",     "web-attack",      "server-side request technique"),
    (r"\b(path[\s-]travers\w*|directory[\s-]travers\w*)\b",     "web-attack",      "path-traversal technique"),
    (r"\b(command[\s-]inject\w*|os[\s-]inject\w*)\b",           "web-attack",      "command-injection technique"),
    (r"\b(remote[\s-]code[\s-]execut\w*|rce[\s-]vuln\w*)\b",   "web-attack",      "remote-execution technique"),
    (r"\b(xml[\s-]inject\w*|xxe[\s-]vuln\w*)\b",                "web-attack",      "xml-injection technique"),
    (r"\b(deserialization[\s-]exploit\w*)\b",                    "web-attack",      "deserialization technique"),
    (r"\b(open[\s-]redirect\w*)\b",                              "web-attack",      "redirect-abuse technique"),

    # ----- Cloud / container security ----------------------------------------
    (r"\b(container[\s-]escap\w*|docker[\s-]escap\w*)\b",       "cloud-attack",    "container-isolation escape"),
    (r"\b(imds[\s-]abus\w*|metadata[\s-]service[\s-]abus\w*)\b","cloud-attack",    "metadata-service technique"),
    (r"\b(iam[\s-]privesc\w*|cloud[\s-]privesc\w*)\b",          "cloud-attack",    "cloud-privilege escalation"),
    (r"\b(kubernetes[\s-]escap\w*|k8s[\s-]escap\w*)\b",         "cloud-attack",    "orchestrator-isolation escape"),
    (r"\b(lambda[\s-]hijack\w*|function[\s-]hijack\w*)\b",      "cloud-attack",    "serverless-function hijack"),

    # ----- Supply chain / build pipeline -------------------------------------
    (r"\b(dependency[\s-]confus\w*)\b",                          "supply-chain",    "dependency-analysis"),
    (r"\b(pipeline[\s-]poison\w*|ci[\s-]poison\w*)\b",          "supply-chain",    "ci-pipeline assessment"),
    (r"\b(package[\s-]hijack\w*|typosquat\w*)\b",               "supply-chain",    "package-name assessment"),
    (r"\b(build[\s-]poison\w*|artifact[\s-]tamper\w*)\b",       "supply-chain",    "build-artifact assessment"),

    # ----- Wireless / RF attacks ---------------------------------------------
    (r"\b(evil[\s-]twin\w*)\b",                                  "wireless",        "rogue-ap technique"),
    (r"\b(deauth[\s-]attack\w*|wifi[\s-]deauth\w*)\b",          "wireless",        "disassociation technique"),
    (r"\b(wifi[\s-]crack\w*|wpa[\s-]crack\w*)\b",               "wireless",        "wifi-credential test"),

    # ----- Identity / privacy operations -------------------------------------
    (r"\b(de[\s-]anonymiz\w*|deanonymiz\w*)\b",                  "privacy",         "identity-correlation"),
    (r"\b(re[\s-]identif\w*|reidentif\w*)\b",                    "privacy",         "subject-resolution"),
    (r"\b(doxx\w*)\b",                                           "privacy",         "profile-aggregation"),
    (r"\b(surveillanc\w*)\b",                                    "monitoring",      "authorized-monitoring"),
    (r"\b(wiretap\w*)\b",                                        "monitoring",      "authorized-intercept"),

    # ----- Credential / hash testing -----------------------------------------
    (r"\b(password[\s-]crack\w*|hash[\s-]crack\w*)\b",          "cred-test",       "credential-testing"),
    (r"\b(brute[\s-]force\w*)\b",                                "cred-test",       "cipher-force testing"),
    (r"\b(rainbow[\s-]table\w*)\b",                              "cred-test",       "precomputed-hash lookup"),
    (r"\b(hashcat\w*|john[\s-]the[\s-]ripper\w*)\b",            "cred-tool",       "credential-testing tool"),

    # ----- Financial / forensic investigations --------------------------------
    (r"\b(money[\s-]launder\w*)\b",                              "financial",       "value-layering"),
    (r"\b(structur\w*[\s-]transact\w*|structured-transaction\w*)\b",          "financial",       "transaction-structuring"),
    (r"\b(tax[\s-]evas\w*|asset[\s-]conceal\w*)\b",             "financial",       "asset-concealment"),

    # ----- Lateral movement tools / techniques --------------------------------
    (r"\b(psexec\w*)\b",                                         "lateral-move",    "remote-execution service"),
    (r"\b(wmiexec\w*)\b",                                        "lateral-move",    "wmi-execution technique"),
    (r"\b(winrm[\s-]abus\w*)\b",                                 "lateral-move",    "winrm-execution technique"),
    (r"\b(rdp[\s-]hijack\w*)\b",                                 "lateral-move",    "rdp-session hijack"),
]


def _already_calibrated() -> set[str]:
    """Lowercase set of all terms already handled by vocabulary_map.py."""
    originals = {c.original.lower() for c in CALIBRATIONS}
    keeps = {k.lower() for k in KEEP_TERMS}
    return originals | keeps


def discover(paths: list[Path], min_count: int = 1) -> list[dict]:
    """Return list of {term, category, count, files, suggestion} for uncalibrated finds."""
    calibrated = _already_calibrated()
    compiled = [
        (re.compile(pat, re.IGNORECASE), cat, sug)
        for pat, cat, sug in _LIBRARY
    ]

    counts: Counter = Counter()
    file_map: dict[str, set[str]] = {}
    meta: dict[str, tuple[str, str]] = {}

    for f in _walk(paths):
        if _is_whitelisted(f):
            continue
        if f.suffix.lower() not in SCAN_EXTENSIONS:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pat, cat, sug in compiled:
            for m in pat.finditer(text):
                term = m.group(0).lower().strip()
                if term in calibrated:
                    continue
                counts[term] += 1
                file_map.setdefault(term, set()).add(str(f))
                meta.setdefault(term, (cat, sug))

    return [
        {
            "term": term, "category": meta[term][0], "count": count,
            "files": sorted(file_map[term])[:5],
            "suggested_calibration": meta[term][1],
        }
        for term, count in counts.most_common()
        if count >= min_count
    ]


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="AUP discovery — find uncalibrated vocabulary")
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--json",      action="store_true", help="JSON output")
    ap.add_argument("--suggest",   action="store_true", help="Output as Calibration() stubs")
    ap.add_argument("--min-count", type=int, default=1, metavar="N",
                    help="Only report terms seen >= N times (default 1)")
    args = ap.parse_args(argv)

    paths = [Path(p) for p in args.paths] if args.paths else _default_paths()
    results = discover(paths, min_count=args.min_count)

    if args.json:
        print(json.dumps(results, indent=2))
    elif args.suggest:
        if not results:
            print("# No uncalibrated terms found.")
        else:
            print("# Add to vocabulary_map.py CALIBRATIONS tuple:")
            print()
            for r in results:
                print(f'    # {r["category"]} (seen {r["count"]}x)')
                print(f'    Calibration("[CONSULTING_FORM]", "{r["term"]}", "tier1", "free-prose",')
                print(f'                "{r["suggested_calibration"]}"),')
                print()
    else:
        if not results:
            print("Discovery: no uncalibrated terms found.")
        else:
            print(f"Discovery: {len(results)} uncalibrated term(s)")
            print(f"{'Count':>6}  {'Category':>20}  Term")
            print("-" * 65)
            for r in results[:40]:
                print(f"  {r['count']:>5}  {r['category']:>20}  {r['term']!r}")
            if len(results) > 40:
                print(f"  ... and {len(results) - 40} more (use --json for full list)")

    return 1 if results else 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:
        sys.stderr.write(f"term_discover: {e}\n")
        sys.exit(1)
