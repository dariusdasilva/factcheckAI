"""Production settings — hardened target for the Render deploy (CI_CD.md)."""

from .base import *  # noqa: F403
from .base import BASE_DIR, env

DEBUG = False

# --- Secrets -------------------------------------------------------------
# Required in production: never inherit the insecure dev fallback from base.py
# (audit #2 finding). A missing DJANGO_SECRET_KEY must fail the deploy loudly.
SECRET_KEY = env("DJANGO_SECRET_KEY")

# --- HTTPS / proxy chain (Render terminates TLS in front of us) -----------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# --- Static files via WhiteNoise -----------------------------------------
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
