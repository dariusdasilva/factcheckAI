"""ASGI entry point (kept alongside wsgi for future SSE work — §9 Q5)."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_asgi_application()
