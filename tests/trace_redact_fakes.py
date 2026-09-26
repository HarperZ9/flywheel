"""Credential-shaped and personal-data fakes, assembled at run time.

No literal token sits in the repository, so push protection has nothing to
flag and nothing here is a real secret. Every value is synthetic.
"""
import base64


def _b64url(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def credential_fakes() -> dict:
    pem_body = "MIIB" + "a" * 60
    return {
        "pem_private_key": "-----BEGIN " + "RSA PRIVATE KEY-----\n" + pem_body
                           + "\n-----END RSA " + "PRIVATE KEY-----",
        "aws_access_key_id": "AK" + "IA" + "ABCDEFGHIJKLMNOP",
        "aws_secret_assignment": "aws_secret_" + "access_key = " + "A" * 40,
        "github_token": "gh" + "p_" + "x" * 36,
        "sk_api_key": "sk-" + "proj-" + "a" * 40,
        "slack_token": "xo" + "xb-" + "1" * 12 + "-" + "a" * 20,
        "stripe_key": "sk_" + "live_" + "a" * 24,
        "google_api_key": "AI" + "za" + "b" * 35,
        "jwt": _b64url('{"alg":"HS256","typ":"JWT"}') + "." + _b64url('{"sub":"12345"}')
               + "." + "s" * 43,
        "bearer_token": "Authorization: " + "Bearer " + "tok_" + "9" * 24,
        "basic_auth": "Basic " + base64.b64encode(b"user:pass1234").decode(),
        "url_userinfo": "https://" + "user:hunter2hunter2" + "@example.com/",
        "credential_assignment": "pass" + "word=" + "correcthorse",
        "azure_key_assignment": "Account" + "Key=" + "A" * 40 + "==",
        "npm_token": "np" + "m_" + "a" * 36,
        "pypi_token": "pypi-" + "AgEIcHlwaS5vcmc" + "a" * 60,
        "hf_token": "h" + "f_" + "a" * 34,
        "cookie_header": "Cookie: " + "session=" + "abc123" * 4,
        "url_signature_param": "https://bucket.example/o?X-Amz-" + "Signature=" + "f" * 64,
        "oauth_code_param": "https://app.example/callback?" + "code=" + "c" * 20 + "&state=xyz",
        "docker_auth": '{"auths":{"r":{"auth":"' + base64.b64encode(b"u:p1234567").decode()
                       + '"}}}',
        "kubeconfig_secret": "    client-key-" + "data: " + "L" * 64,
        "age_secret_key": "AGE-SECRET-" + "KEY-1" + "Q" * 58,
        "putty_key": "PuTTY-User-" + "Key-File-3: ssh-ed25519\nEncryption: none\n"
                     + "Private-Lines: 1\nAAAA\nPrivate-" + "MAC: " + "f" * 64,
    }


def personal_fakes() -> dict:
    return {
        "email": "reach me at jane.doe@example.org today",
        "phone": "call (415) 555-0123 after five",
        "card_number": "card 4111 1111 1111 1111 on file",
        "us_ssn": "ssn 123-45-6789 on the form",
        "iban": "pay GB82 WEST 1234 5698 7654 32 now",
        "ipv4": "host 10.1.2.3 answered",
        "ipv6": "host 2001:db8::1 answered",
        "lat_long": "met at 47.6062, -122.3321 today",
    }
