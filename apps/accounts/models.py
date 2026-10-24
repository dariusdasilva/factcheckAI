"""User-scope models: hashed API keys (extension bearer tokens) and the
per-tier default model settings (§3.1)."""

import hashlib

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ApiKey(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    key_hash = models.CharField(
        max_length=64,
        unique=True,
        help_text=_("SHA-256 hex digest of the key. Never store plaintext (§6)."),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    @staticmethod
    def hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def revoke(self) -> None:
        """Mark revoked; past requests keep their sessions, future ones fail."""
        self.revoked_at = timezone.now()
        self.save(update_fields=["revoked_at"])

    def __str__(self) -> str:
        state = "active" if self.is_active else "revoked"
        return f"ApiKey #{self.pk} ({state}) for {self.user}"


class ModelSetting(models.Model):
    class Tier(models.TextChoices):
        API = "api", _("API (OpenRouter)")
        LOCAL = "local", _("Local (Ollama)")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="model_settings",
    )
    tier = models.CharField(max_length=8, choices=Tier.choices)
    model_id = models.CharField(max_length=255)
    spend_cap_monthly = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(0)],
        help_text=_(
            "API tier only (§3.1). null = apply the implementation default ($5)."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user", "tier"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "tier"],
                name="modelsetting_user_tier_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(tier__in=["api", "local"]),
                name="modelsetting_tier_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user}: {self.tier} -> {self.model_id}"
