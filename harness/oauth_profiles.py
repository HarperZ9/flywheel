"""oauth_profiles.py -- who can be signed into, and on what terms.

One profile per provider. `sanction` is the honest sentence the CLI prints:
it states what the provider actually permits, and where flywheel claims
nothing. No profile carries a client id; a registered flow gets one only from
the operator's own environment, so this engine can never run another app's
OAuth client.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Two wire shapes. OpenRouter documents its own parameter names; a registered
# provider gets standard OAuth 2.0 + PKCE (RFC 6749 / 7636).
WIRE_OPENROUTER = "openrouter"
WIRE_OAUTH2 = "oauth2"


@dataclass(frozen=True)
class OAuthProfile:
    """One provider's sign-in shape: how the flow runs, where the token
    lands, and what the honest sanction label is."""

    provider: str
    kind: str                     # pkce | guided-cli | official-cli | registered
    keychain_name: str            # where the token lands; the resolver reads it
    sanction: str                 # one honest sentence for status output
    authorize_url: str = ""
    exchange_url: str = ""
    wire: str = WIRE_OPENROUTER
    client_id: str = ""           # never shipped; operator env only
    client_id_env: str = ""       # registered flows: operator-owned client id
    guide: tuple = field(default=())


PROFILES = {
    "openrouter": OAuthProfile(
        provider="openrouter", kind="pkce",
        keychain_name="OPENROUTER_API_KEY",
        sanction="documented third-party PKCE flow; no registration required",
        authorize_url="https://openrouter.ai/auth",
        exchange_url="https://openrouter.ai/api/v1/auth/keys",
        wire=WIRE_OPENROUTER,
    ),
    "anthropic": OAuthProfile(
        provider="anthropic", kind="official-cli",
        keychain_name="",
        sanction="Claude Code owns account sign-in. Flywheel runs no OAuth "
                 "client of its own, launches the operator-selected CLI only "
                 "when asked, reads account status as labels, and keeps direct "
                 "Anthropic API keys separate",
    ),
    "openai": OAuthProfile(
        provider="openai", kind="registered",
        keychain_name="CHATGPT_OAUTH_TOKEN",
        sanction="needs an app registration you own. Set "
                 "FLYWHEEL_OPENAI_OAUTH_CLIENT_ID, "
                 "FLYWHEEL_OPENAI_OAUTH_AUTHORIZE_URL, and "
                 "FLYWHEEL_OPENAI_OAUTH_EXCHANGE_URL in the engine's "
                 "environment to enable it",
        client_id_env="FLYWHEEL_OPENAI_OAUTH_CLIENT_ID",
        wire=WIRE_OAUTH2,
    ),
}
