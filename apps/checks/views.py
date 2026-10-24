"""REST views for the checks API (deliverable A3).

Endpoints (ARCHITECTURE.md §3):
- POST/GET /api/v1/checks/ , GET /api/v1/checks/{id}/  — ChecksViewSet
- GET  /api/v1/spend/    — stub until B4's spend ledger
- GET  /api/v1/models/   — stub until B3's live catalog  (never hardcode for real)
- POST /api/v1/sources/  — extension pushes scraped page text into the Source cache
"""

import hashlib
import logging
from urllib.parse import urlsplit

from django.conf import settings
from django.db import connection
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_q.tasks import async_task
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.checks import serializers as ser
from apps.checks.models import (
    CheckRun,
    CheckRunStatus,
    Claim,
    EvidenceFetchStatus,
    Source,
)
from apps.checks.source_serializers import SourcePushSerializer

logger = logging.getLogger(__name__)

# --- health (A1) ------------------------------------------------------------


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
@throttle_classes([])  # health is the degradation pre-flight probe: never throttle it
def health(request: Request) -> Response:
    """GET /api/v1/health/ — public liveness/readiness probe (deliverable A1).

    Per ARCHITECTURE.md §3 this is used by both clients to pre-emptively show a
    "degraded" state. The provider component is filled in by Chunk B.
    """
    db_ok = _database_ok()

    queue_component = (
        "ok"
        if "django_q" in settings.INSTALLED_APPS and hasattr(settings, "Q_CLUSTER")
        else "not_configured"
    )
    components = {
        "database": "ok" if db_ok else "unreachable",
        "queue": queue_component,
    }
    return Response(
        {
            "status": "ok" if db_ok else "degraded",
            "service": "factcheckai-api",
            "components": components,
        },
        status=200 if db_ok else 503,
    )


# --- checks: submit / poll / list -----------------------------------------


class ChecksViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return ser.SubmitCheckSerializer
        if self.action == "retrieve":
            return ser.CheckRunResultSerializer
        return ser.CheckRunListSerializer

    def get_queryset(self):
        return (
            CheckRun.objects.select_related("claim")
            .filter(claim__created_by=self.request.user)
            .order_by("-created_at")
        )

    def create(self, request: Request, *args, **kwargs) -> Response:
        """POST /checks/ → 202 + check_id; the result is fetched via polling."""
        in_serializer = ser.SubmitCheckSerializer(data=request.data)
        in_serializer.is_valid(raise_exception=True)
        data = in_serializer.validated_data

        claim = Claim.objects.create(
            text=data["claim"],
            source_url=(data.get("context") or {}).get("source_url") or None,
            created_by=request.user,
        )
        run = CheckRun.objects.create(claim=claim)

        # Enqueue on the Django-Q2 ORM broker (A4) — the qcluster worker picks
        # it up and transitions queued → running → ok. When Chunk B lands,
        # only apps.checks.tasks.run_check changes; this call stays.
        async_task("apps.checks.tasks.run_check", run.pk, group="checks")

        return Response(
            {"check_id": run.pk, "status": CheckRunStatus.QUEUED},
            status=status.HTTP_202_ACCEPTED,
        )

    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        run = get_object_or_404(self.get_queryset(), pk=kwargs["pk"])
        out_serializer = ser.CheckRunResultSerializer(run)
        return Response(out_serializer.data)


# --- spend / models stubs (B3/B4 replace these) ----------------------------


@api_view(["GET"])
def spend_stub(request: Request) -> Response:
    """GET /spend/ — shape frozen now, maths land with B4's ledger."""
    return Response(
        {
            "month_to_date_usd": None,
            "by_provider": {},
            "avg_cost_per_check_usd": None,
            "note": "stub: populated by the spend ledger (Chunk B4)",
        }
    )


@api_view(["GET"])
def model_catalog_stub(request: Request) -> Response:
    """GET /models/ — placeholder rows so D can build pickers now.

    WARNING (A2 rule from AGENTS.md §5): the real catalog is always rendered
    from the live OpenRouter/Ollama endpoints with a cache — this static list
    is illustrative only and disappears with Chunk B3.
    """
    return Response(
        {
            "stub": True,
            "api_models": [
                {
                    "id": "google/gemma-4-26b-a4b-it:free",
                    "context_window": 262144,
                    "price_in_per_mtok": "0.000000",
                    "price_out_per_mtok": "0.000000",
                },
                {
                    "id": "google/gemma-4-31b-it",
                    "context_window": 262144,
                    "price_in_per_mtok": "0.200000",
                    "price_out_per_mtok": "0.400000",
                },
            ],
            "local_models": [],
            "note": "stub: live catalog (OpenRouter + Ollama /api/tags) lands with B3",
        }
    )


# --- sources: extension push into the crawl cache --------------------------


@api_view(["POST"])
def store_source(request: Request) -> Response:
    """POST /sources/ — upsert scraped page text keyed by URL (§4 Source).

    Returns ``cached`` = True when the URL already had a row (chunk C's
    "cache hit = no refetch" semantics rely on this table).
    """
    serializer = SourcePushSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    url = serializer.validated_data["url"]
    text = serializer.validated_data["text"]

    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    domain = urlsplit(url).netloc

    source, created = Source.objects.get_or_create(
        url=url,
        defaults={
            "content_hash": content_hash,
            "domain": domain,
            "fetch_status": EvidenceFetchStatus.FETCHED,
            "text_extract": text,
            "fetched_at": timezone.now(),
        },
    )
    if not created:
        source.content_hash = content_hash
        source.domain = domain
        source.text_extract = text
        source.fetch_status = EvidenceFetchStatus.FETCHED
        source.fetched_at = timezone.now()
        source.save(
            update_fields=[
                "content_hash",
                "domain",
                "text_extract",
                "fetch_status",
                "fetched_at",
            ]
        )

    return Response(
        {
            "id": source.pk,
            "url": source.url,
            "cached": not created,
        },
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )
