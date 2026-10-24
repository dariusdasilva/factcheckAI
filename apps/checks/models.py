"""Core domain models: claims, check runs, evidence, crawl cache, telemetry.

Field lists follow ARCHITECTURE.md §4. Status strings come from the frozen
contract in apps.checks.contracts — the fail-state law applies to every field
that feeds the verdict output.
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class VerdictEnum(models.TextChoices):
    TRUE = "true", _("True")
    FALSE = "false", _("False")
    UNVERIFIED = "unverified", _("Unverified")


class CheckRunStatus(models.TextChoices):
    """Progress states (queued/running) + terminal states (contract, §2.2)."""

    QUEUED = "queued", _("Queued")
    RUNNING = "running", _("Running")
    OK = "ok", _("Ok")
    FALLBACK = "fallback", _("Fallback")
    FAIL_STATE = "fail_state", _("Fail state")


class EvidenceHop(models.TextChoices):
    WIKI = "wiki", _("Wikipedia article (hop 1)")
    CITED_SOURCE = "cited_source", _("Cited source (hop 2)")


class EvidenceFetchStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    FETCHED = "fetched", _("Fetched")
    ERROR = "error", _("Error")
    SKIPPED = "skipped", _("Skipped")


class Claim(models.Model):
    text = models.TextField(
        help_text=_("The claim being fact-checked, stored verbatim."),
    )
    source_url = models.URLField(
        _("source URL"),
        blank=True,
        null=True,
        help_text=_("Page the claim text came from, if any (extension submits this)."),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="claims",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        clipped = self.text if len(self.text) <= 80 else f"{self.text[:77]}..."
        return f"{self.pk}: {clipped}"


class CheckRun(models.Model):
    claim = models.ForeignKey(
        Claim,
        on_delete=models.CASCADE,
        related_name="check_runs",
    )
    status = models.CharField(
        max_length=16,
        choices=CheckRunStatus.choices,
        default=CheckRunStatus.QUEUED,
        db_index=True,
        help_text=_("Exact strings are the cross-chunk contract (§2.2)."),
    )
    provider_used = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text=_("Which provider produced the result: remote_api / ollama."),
    )
    model_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text=_("Model actually used, e.g. google/gemma-4-26b-a4b-it:free."),
    )
    tokens_in = models.PositiveIntegerField(blank=True, null=True)
    tokens_out = models.PositiveIntegerField(blank=True, null=True)
    # Price snapshot at call time — the spend ledger reads these (§3.1).
    price_in_per_mtok = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        blank=True,
        null=True,
    )
    price_out_per_mtok = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        blank=True,
        null=True,
    )
    confidence = models.FloatField(
        blank=True,
        null=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text=_(
            "Display-only, never calibrated (AGENTS.md §4.9) — never gate logic on it."
        ),
    )
    verdict_enum = models.CharField(
        max_length=16,
        choices=VerdictEnum.choices,
        blank=True,
        null=True,
    )
    latency_ms = models.PositiveBigIntegerField(blank=True, null=True)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["claim", "status"]),
        ]

    def __str__(self) -> str:
        return f"CheckRun #{self.pk} [{self.status}] claim={self.claim_id}"


class Evidence(models.Model):
    check_run = models.ForeignKey(
        CheckRun,
        on_delete=models.CASCADE,
        related_name="evidence",
    )
    hop = models.CharField(max_length=16, choices=EvidenceHop.choices)
    url = models.URLField(max_length=2048)
    title = models.CharField(max_length=512, blank=True)
    snippet = models.TextField(
        help_text=_("Labelled snippet; ids [W#]/[S#] are assigned by the packer (§3.2)."),
    )
    relevance = models.FloatField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["check_run", "hop"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_hop_display()}: {self.title or self.url}"


class Source(models.Model):
    """The crawl cache (§3.2): check here before ever spending network."""

    url = models.URLField(max_length=2048, unique=True)
    content_hash = models.CharField(max_length=64, db_index=True)
    domain = models.CharField(max_length=255, db_index=True)
    fetch_status = models.CharField(
        max_length=16,
        choices=EvidenceFetchStatus.choices,
        default=EvidenceFetchStatus.PENDING,
    )
    text_extract = models.TextField(blank=True)
    fetched_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-fetched_at"]

    def __str__(self) -> str:
        return f"{self.fetch_status}: {self.url}"


class AuditLog(models.Model):
    """Fail-state + fallback telemetry (§4), consumed by the admin dashboards."""

    check_run = models.ForeignKey(
        CheckRun,
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    event = models.CharField(max_length=64)
    json_payload = models.JSONField(
        default=dict,
        help_text=_("Structured event data: providers tried, error kinds, timings."),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["check_run", "event"]),
        ]

    def __str__(self) -> str:
        return f"AuditLog #{self.pk} {self.event} (run {self.check_run_id})"
