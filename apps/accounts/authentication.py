"""Bearer-key authentication for the Firefox extension (audit #2 finding).

`POST /api/v1/auth/keys/` issues `fcai_…` keys, and this module is what makes
them usable. DRF's TokenAuthentication only validates the authtoken table —
without this class, issued extension keys are dead credentials.

Key format: `Authorization: Token fcai_<43 urlsafe chars>` (Bearer accepted
too, for curl-friendliness). Keys are compared by SHA-256 hash — the plaintext
is never stored (§6).
"""

from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from apps.accounts.models import ApiKey

API_KEY_PREFIX = "fcai_"
_ACCEPTED_KEYWORDS = (b"token", b"bearer")


class ApiKeyAuthentication(BaseAuthentication):
    """Authenticate extension requests bearing an issued API key.

    Returns None for credentials that don't look like ours so the remaining
    authenticators (session, DRF token) can handle them.
    """

    def authenticate(self, request):
        header = get_authorization_header(request)
        parts = header.split()
        if len(parts) != 2 or parts[0].lower() not in _ACCEPTED_KEYWORDS:
            return None
        try:
            credential = parts[1].decode()
        except UnicodeError:
            return None
        if not credential.startswith(API_KEY_PREFIX):
            return None  # not an extension key — let TokenAuthentication try

        key = (
            ApiKey.objects.select_related("user")
            .filter(
                key_hash=ApiKey.hash_key(credential),
                revoked_at__isnull=True,
            )
            .first()
        )
        if key is None:
            # Explicit 401 rather than silent fallthrough: a well-formed fcai_
            # credential that doesn't resolve is invalid, not "no credentials".
            raise AuthenticationFailed("Invalid or revoked API key.")
        return (key.user, key)

    def authenticate_header(self, request):
        # Advertise the challenge scheme so failures are 401, not 403.
        return "Token"
