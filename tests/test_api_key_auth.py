"""Audit #2 finding #1: issued `fcai_…` keys must actually authenticate.

Before this suite existed, `POST /auth/keys/` minted keys that nothing could
verify: DRF's TokenAuthentication only knows the authtoken table, so every
extension request 403'd at integration time. These tests pin the contract the
extension (Chunk D) relies on.
"""

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.accounts.models import ApiKey

pytestmark = [pytest.mark.django_db]

CHECKS_URL = "/api/v1/checks/"
KEYS_URL = "/api/v1/auth/keys/"


@pytest.fixture()
def user_and_key(django_user_model):
    """A user plus a key minted through the public endpoint (not by hand)."""
    user = django_user_model.objects.create_user(username="keyuser", password="x")
    session = APIClient()
    session.force_authenticate(user=user)
    issued = session.post(KEYS_URL).json()
    return user, issued["key"]


@pytest.mark.parametrize("scheme", ["Token", "Bearer"])
def test_issued_key_authenticates(user_and_key, scheme):
    _, key = user_and_key
    client = APIClient()
    response = client.post(
        CHECKS_URL,
        {"claim": "A key minted by the API must authenticate."},
        format="json",
        HTTP_AUTHORIZATION=f"{scheme} {key}",
    )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"


def test_issued_key_can_poll_its_own_runs(user_and_key):
    _, key = user_and_key
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {key}")
    check_id = client.post(
        CHECKS_URL, {"claim": "poll via issued key"}, format="json"
    ).json()["check_id"]

    polled = client.get(f"{CHECKS_URL}{check_id}/")
    assert polled.status_code == 200
    assert polled.json()["check_id"] == check_id


def test_revoked_key_is_rejected_with_401(user_and_key):
    _, key = user_and_key
    stored = ApiKey.objects.get(key_hash=ApiKey.hash_key(key))
    stored.revoke()

    response = APIClient().post(
        CHECKS_URL,
        {"claim": "revoked keys must not authenticate"},
        format="json",
        HTTP_AUTHORIZATION=f"Token {key}",
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or revoked API key."


def test_unknown_fcai_key_is_rejected_with_401(user_and_key):
    # Well-formed prefix, no matching row: an invalid credential, not "anonymous".
    response = APIClient().post(
        CHECKS_URL,
        {"claim": "garbage keys must not authenticate"},
        format="json",
        HTTP_AUTHORIZATION="Token fcai_" + "z" * 43,
    )
    assert response.status_code == 401


def test_anonymous_request_is_still_401(user_and_key):
    assert APIClient().get(CHECKS_URL).status_code == 401


def test_drf_authtoken_still_works_alongside_api_keys(user_and_key):
    # T asks for a session but the README documents DRF tokens for manual use;
    # ApiKeyAuthentication must defer to TokenAuthentication for non-fcai keys.
    user, _ = user_and_key
    token, _ = Token.objects.get_or_create(user=user)

    response = APIClient().post(
        CHECKS_URL,
        {"claim": "DRF authtokens keep working"},
        format="json",
        HTTP_AUTHORIZATION=f"Token {token.key}",
    )
    assert response.status_code == 202


def test_session_auth_still_works_alongside_api_keys(user_and_key):
    from django.test import Client

    user, _ = user_and_key
    web = Client()
    web.force_login(user)
    assert web.get(CHECKS_URL).status_code == 200
