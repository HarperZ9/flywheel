# Trace redaction

Flywheel redacts credentials, and on request personal data, when trace
content leaves your custody in an export. When stored content would be sent
to a model (a bench replay), a credential in it refuses the whole send
instead of being redacted. The copy you keep is stored as it arrived, so
redaction never costs you your own record.

One catalog serves trace export and the bench replay guard. Other paths keep
their own detectors for now: the cross-harness adapters, credential handles,
the gateway trace write guard (`validate_no_raw_secrets`) and the desktop app.
The catalog's version is
`trace-redact/2026-09-26.3`, and every redaction report names it.

## How a match is replaced

Each match becomes `[REDACTED:<rule>:<tag>]`. The tag is the first eight hex
characters of an HMAC of the matched text under a key the caller passes. One
key gives one secret one tag, so you can see that two redactions were the
same value. An export uses a fresh random key by default, so two exports
cannot be linked through their tags.

A report lists the catalog version, the count per rule and the number of
lines affected. It never contains the matched text.

## How lines are read

A transcript line is JSON. The line is parsed and every decoded string value
is scanned, so escapes such as `\n` inside a PEM block or `\u0067` for a
letter do not hide a secret. A string that is itself JSON is parsed and
walked too, up to four levels. Object keys are scanned as well, since a token
can be a key, and a number is scanned as its decimal text, so a card number
stored as a JSON number is found. A value stored under a credential-named
key, such as `api_key`, `password`, `authorization`, any name ending in
`_key` or `-key` after a prefix (`SECRET_KEY`, `signing_key`) or any name
containing `secret`, is replaced whole. A line
that does not parse is scanned as raw text and again with its JSON escapes
decoded, and each match is replaced in the raw bytes.

Flywheel caps tool output at 4000 characters, which can cut a token. A token
prefix that reaches the end of a string value is redacted even when it is
shorter than the full token.

Every pattern runs in time linear in its input. A test feeds each one
adversarial input shaped to be its worst case and holds it to 50 ms per MiB,
a budget that scales on machines slower than the reference one. Input made
of real matches, or of candidates a check must reject, costs one check per
candidate. A second test holds an eight-fold larger flood to at most 20 times
the time of the smaller one, plus 10 ms, in one of up to three rounds. That
separates linear from quadratic growth (8 against 64); it does not separate
linear from slightly faster growth. Long strings are
scanned in 64 KiB windows that overlap by 8 KiB. A scan that runs past its
time budget stops with `SCAN_BUDGET_EXCEEDED`.

## Rules

Credential rules run by default. Personal-data rules run when you ask for
them. The IP address and coordinate rules are off in every Flywheel command
today: no option turns them on, and only code that calls the library can
name them.

| Rule | Class | Default | Matches, and known false positives |
| --- | --- | --- | --- |
| `pem_private_key` | credential | on | Any PEM private-key block. An unterminated block is redacted to the end of the text |
| `aws_access_key_id` | credential | on | A 20-character id starting AKIA or ASIA |
| `aws_secret_assignment` | credential | on | The value assigned to aws_secret_access_key |
| `github_token` | credential | on | GitHub token prefixes (ghp_, gho_, ghu_, ghs_, ghr_, github_pat_) |
| `sk_api_key` | credential | on | sk- keys. A hyphenated name that starts sk- and runs 20 or more characters also matches |
| `slack_token` | credential | on | Slack xox tokens |
| `stripe_key` | credential | on | Stripe live secret and restricted keys |
| `google_api_key` | credential | on | Google API keys |
| `jwt` | credential | on | A JWT whose header decodes to JSON with alg. A token with an empty signature is not matched |
| `bearer_token` | credential | on | A bearer value of 16 or more characters holding a digit or a symbol |
| `basic_auth` | credential | on | A Basic value that decodes to user:password |
| `url_userinfo` | credential | on | URL userinfo with a password, or a user part of 16 or more characters |
| `credential_assignment` | credential | on | A value of 8 or more characters assigned to a credential-named key, including any name ending in `_key` or `-key` and any name holding `secret`. Example code such as `token = get_token(user)` also matches, and so does `PWD=/path` |
| `azure_key_assignment` | credential | on | Azure AccountKey= and SharedAccessKey= values |
| `npm_token` | credential | on | npm access tokens |
| `pypi_token` | credential | on | PyPI API tokens |
| `hf_token` | credential | on | Hugging Face tokens |
| `cookie_header` | credential | on | Cookie and Set-Cookie values that hold name=value. Prose such as `cookie: a=b` also matches |
| `url_signature_param` | credential | on | The sig, X-Amz-Signature, X-Amz-Credential, X-Goog-Signature and access_token query parameters |
| `oauth_code_param` | credential | on | A code parameter, only in a URL that also carries state or whose path names oauth, callback or authorize. A bare code= is kept |
| `docker_auth` | credential | on | Docker config auth values |
| `kubeconfig_secret` | credential | on | kubeconfig client-key-data and token values |
| `age_secret_key` | credential | on | age secret keys |
| `putty_key` | credential | on | A PuTTY key file body from its first line through Private-MAC |
| `email` | personal | on request | Email addresses. A git or ssh remote such as git@github.com also matches |
| `phone` | personal | on request | E.164 and North American numbers. Ten-digit ids and timestamps also match |
| `card_number` | personal | on request | 13 to 19 digits that pass Luhn. About one random long number in ten passes Luhn |
| `us_ssn` | personal | on request | US Social Security numbers in valid ranges |
| `iban` | personal | on request | IBANs that pass mod 97 |
| `ipv4` | personal | named only | IPv4 addresses. Version strings such as 1.2.3.4 match |
| `ipv6` | personal | named only | IPv6 addresses with at least three hex digits |
| `lat_long` | personal | named only | Decimal coordinate pairs |

## What it does not detect

Each item below is asserted by a test that feeds it through with every rule
on and checks that it comes out unchanged. This is the list of known misses,
not a complete one: passing redaction does not show that a store is free of
secrets or personal data.

| Miss | What passes through |
| --- | --- |
| `password_without_named_key` | A password written in prose, with no credential-named key |
| `secret_split_across_lines` | A secret split across lines, tool calls or messages |
| `encoded_secret` | A secret encoded as base64 or hex (Docker auth values aside) |
| `custom_token_format` | A token format the catalog does not name |
| `bare_azure_key` | An Azure key with no prefix and no assignment name |
| `secret_in_binary_content` | A secret inside an image, a PDF or compressed binary |
| `personal_free_text` | Names, street addresses, dates of birth and health facts |
| `national_id_other_than_ssn_or_iban` | National identifiers other than US Social Security numbers and IBANs |
| `unicode_lookalike` | A token written with look-alike Unicode letters |
| `json_nested_deeper_than_four_levels` | JSON nested more than four levels deep inside strings, where only the key name would reveal the secret |

## Where it applies

- Export: credential rules on by default, personal rules with
  `--redact-personal`, and none with `--no-redact`.
- Content sent to a model from stored traces passes the credential guard
  first, and a hit refuses the send; nothing is redacted on that path.
  Guards that refuse content use credential rules only; a personal-data rule
  never stops a run.
- The desktop app keeps its own detector for chat text in this release.
