"""We eat our own dog food: our shipped prose must pass our own detector.

detector.py is deliberately excluded. It is the device catalog: it names every
device it detects ("not X but Y", "instead", em-dash) in its own comments, so it
flags itself by design. Every other module's docstrings and comments, and every
shipped doc, must be clean under our own standard.
"""
import pathlib

import articulate
from articulate import profiles, pysource

ROOT = pathlib.Path(__file__).resolve().parent.parent

DOCS = ["README.md", "editors/vscode/README.md",
        "docs/README.md", "docs/getting-started.md", "docs/walkthrough.md",
        "docs/features.md", "docs/cli.md", "docs/boundaries.md",
        "docs/house-voice.md", "docs/series-and-voice.md", "docs/claude-plugin.md",
        "claude-plugin/README.md", "corpus/PANGRAM.md", "corpus/provenance/README.md", "docs/campaign.md"]
MODULES = ["cli.py", "editor.py", "bench.py", "pangram_records.py", "mcp_server.py", "profiles.py",
           "receipt.py", "lsp_server.py", "pysource.py", "modes.py",
           "genres.py", "masking.py", "claude_cli.py", "__init__.py",
           "house.py", "house_spec.py", "house_settings.py", "house_edits.py", "house_hook.py",
           "house_tools.py", "cli_house.py", "bench_house.py", "voice_identity.py",
           "voice_apply.py", "cli_voice.py", "mcp_local_tools.py", "voice_store.py",
           "voice.py", "voice_tools.py", "authorship.py", "interview.py", "restructure.py",
           "titles.py", "corpus.py", "cli_corpus.py", "negation_load.py",
           "negation_entries.py", "cli_negation.py", "campaign.py", "campaign_promo.py",
           "campaign_persona.py", "campaign_cluster.py", "campaign_corpus.py",
           "campaign_bench.py", "cli_campaign.py", "imagery_lex.py", "device_function.py",
           "voice_register.py", "pack_claims.py", "pack_product.py", "pack_note.py",
           "pack_devices.py", "analogy.py", "pack_analogy_map.py", "pack_privacy.py"]


def _gate(path, text):
    prof = profiles.resolve(path=str(path), text=text)
    r = articulate.check_text(text, profile=prof)
    return r["gate"], [f"L{f['line']} {f['match']!r}" for f in r["high"] + r["medium"]]


def test_shipped_docs_are_clean():
    for doc in DOCS:
        p = ROOT / doc
        gate, hits = _gate(p, p.read_text(encoding="utf-8"))
        assert gate == "ok", f"{doc} fails our own standard: {hits}"


def test_module_prose_is_clean():
    for mod in MODULES:
        p = ROOT / "src" / "articulate" / mod
        prose = pysource.prose_of(p.read_text(encoding="utf-8"))
        gate, hits = _gate(p, prose)
        assert gate == "ok", f"{mod} docstrings/comments fail our own standard: {hits}"


def test_the_house_brief_is_clean():
    """The brief every session receives passes our own standard."""
    from articulate import house
    text = house.brief()
    r = articulate.check_text(text, profile=profiles.resolve(path="brief.md", text=text))
    assert r["gate"] == "ok", [f["match"] for f in r["high"] + r["medium"]]
    assert "—" not in text
