"""REST views for the checks API."""

import logging

from django.db import connection
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger(__name__)


def _database_ok() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:  # pragma: no cover - depends on live DB outage
        logger.exception("Health check: database unreachable")
        return False
    return True


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """GET /api/v1/health/ — public liveness/readiness probe (deliverable A1).

    Per ARCHITECTURE.md §3 this is used by both clients to pre-emptively show a
    "degraded" state. Provider and queue components are filled in by Chunks
    B (inference) and A4 (task queue) as those come online.
    """
    db_ok = _database_ok()
    components = {
        "database": "ok" if db_ok else "unreachable",
    }
    return Response(
        {
            "status": "ok" if db_ok else "degraded",
            "service": "factcheckai-api",
            "components": components,
        },
        status=200 if db_ok else 503,
    )
