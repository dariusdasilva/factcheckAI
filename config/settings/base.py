"""Base settings shared by every environment (dev, prod).

Secrets and deployment-specific values come from environment variables or the
gitignored `.env` file (via django-environ). Never commit secrets here.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

# --- Core -----------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-only-insecure-key-adjust-in-prod")
DEBUG = env.bool("DJANGO_DEBUG", default=False)  # dev.py forces True; prod.py forces False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# --- Applications ---------------------------------------------------------
# django-q2 lands with Chunk A4 (task queue) — kept out until then.
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework.authtoken",  # DRF token auth (extension bearer keys)
    "corsheaders",
    "django_q",  # task queue (A4); workers run as `manage.py qcluster`
    # Project apps (checks/accounts = A; sources = C; inference is a plain
    # package with no models, so it is imported directly and not registered).
    "apps.checks",
    "apps.accounts",
    "apps.sources",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",  # must sit above CommonMiddleware
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Database (ARCHITECTURE.md §2.1: SQLite in dev / PostgreSQL in prod) ---
# DATABASE_URL drives the switch: unset → local sqlite; postgres://… → Postgres.
DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    ),
}

# --- API (ARCHITECTURE.md §3: JSON only, token/session auth) -------------
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    # Token auth for the extension; session auth for the web app (§2.1).
    # ApiKeyAuthentication first so issued `fcai_…` keys authenticate (the
    # extension path); it defers to the others for non-prefixed credentials.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.ApiKeyAuthentication",
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    # 100 req/day/user default throttle (§3) — A4 acceptance blocks #101.
    "DEFAULT_THROTTLE_CLASSES": ["apps.checks.throttling.AuthenticatedUserThrottle"],
    "DEFAULT_THROTTLE_RATES": {"authenticated_user_day": "100/day"},
    # Throttle scopes land with A4 (100 req/day/user) — global default then.
    "DEFAULT_PAGINATION_CLASS": "apps.checks.pagination.CheckRunPagination",
}

# --- CORS (§6: only the web app origin allow-listed) ----------------------
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:8000"]
)

# --- Internationalization -------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static files ---------------------------------------------------------
STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Caching --------------------------------------------------------------
# LocMem is enough for dev/demo (CI_CD.md decision: no Redis for the demo).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "factcheckai-default",
    },
}

# --- Task queue (A4, django-q2) -------------------------------------------
# DB-backed broker: no Redis needed for the demo (CI_CD.md). B5's 90 s latency
# cut-off governs the *task* itself; worker timeout must exceed it safely.
Q_CLUSTER = {
    "name": "factcheckai",
    "workers": 2,
    "timeout": 120,    # worker hard timeout; comfortably above B5's 90 s cut-off
    "retry": 150,      # retry > timeout (per django-q2 warning semantics)
    "max_attempts": 2,
    "catch_up": False,
    # NOTE: django-q2 (the maintained fork) reads this key lowercase and treats
    # it as the DATABASE ALIAS for the broker queue table — `"ORM": True` from
    # the old django-q docs silently falls back to a Redis broker.
    "orm": "default",
}

# --- Inference (Chunk B) ----------------------------------------------------
# Remote tier (OpenRouter) and the local Ollama tier. These are the defaults
# behind each user's per-tier ModelSetting; the providers read them at run time.
OPENROUTER_API_KEY = env("OPENROUTER_API_KEY", default="")
DEFAULT_REMOTE_MODEL = env("DEFAULT_REMOTE_MODEL", default="google/gemma-4-26b-a4b-it:free")
DEFAULT_LOCAL_MODEL = env("DEFAULT_LOCAL_MODEL", default="gemma4:e4b-it-qat")
OLLAMA_BASE_URL = env("OLLAMA_BASE_URL", default="http://localhost:11434")
