"""Throttling (A4): 100 requests/day per authenticated user (ARCHITECTURE.md §3).

Applied globally via REST_FRAMEWORK defaults. The health probe is exempted at
its view (clients pre-flight it before every check — throttling it would break
that contract). Anonymous users are rejected before throttling (auth first).
"""

from rest_framework.throttling import UserRateThrottle


class AuthenticatedUserThrottle(UserRateThrottle):
    scope = "authenticated_user_day"
