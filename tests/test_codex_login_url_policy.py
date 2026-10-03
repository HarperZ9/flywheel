"""Provider OAuth flags must remain distinct from credential-bearing URLs."""
import pytest

from harness.codex_account_safety import DEFAULT_ALLOWED_LOGIN_HOSTS, trusted_login_url


@pytest.mark.parametrize('flag', ['true', 'false'])
def test_official_organization_flag_is_not_a_token(flag):
    url = ('https://auth.openai.com/oauth/authorize?response_type=code'
           '&client_id=public-client&scope=openid+profile+email+offline_access'
           f'&id_token_add_organizations={flag}&state=opaque-state'
           '&code_challenge=public-challenge&code_challenge_method=S256')
    assert trusted_login_url(url, DEFAULT_ALLOWED_LOGIN_HOSTS) == url


@pytest.mark.parametrize('query', [
    'id_token_add_organizations=not-a-boolean',
    'id_token_add_organizations=true&id_token_add_organizations=false',
    'id_token_add_organizations=true&access_token=private-value',
    'id_token_add_organizations=true&access%5Ftoken=private-value',
    'id_token_add_organizations=true&api%5Fkey=private-value',
    'id_token_add_organizations=true&redirect_uri=https%3A%2F%2Fexample.test%2F%3Ftoken%3Dprivate',
    'id_token_add_organizations=sk-notarealcredential123',
    'id_token_add_organizations=true&state=sk-notarealcredential123',
    'ID_TOKEN_ADD_ORGANIZATIONS=true',
])
def test_organization_flag_does_not_bypass_credential_checks(query):
    with pytest.raises(ValueError, match='credential-shaped'):
        trusted_login_url('https://auth.openai.com/oauth/authorize?' + query,
                          DEFAULT_ALLOWED_LOGIN_HOSTS)


@pytest.mark.parametrize('query', [
    'api%5Fkey=private-value',
    '%74%6f%6b%65%6e=private-value',
    'state=%73%6b%2dnotarealcredential123',
])
def test_encoded_credential_fields_are_rejected_without_organization_flag(query):
    with pytest.raises(ValueError, match='credential-shaped'):
        trusted_login_url('https://auth.openai.com/oauth/authorize?' + query,
                          DEFAULT_ALLOWED_LOGIN_HOSTS)


@pytest.mark.parametrize('base', [
    'https://auth.openai.com.evil.test/oauth/authorize',
    'http://auth.openai.com/oauth/authorize',
    'https://user:password@auth.openai.com/oauth/authorize',
])
def test_organization_flag_never_relaxes_origin_rules(base):
    with pytest.raises(ValueError):
        trusted_login_url(base + '?id_token_add_organizations=true',
                          DEFAULT_ALLOWED_LOGIN_HOSTS)
