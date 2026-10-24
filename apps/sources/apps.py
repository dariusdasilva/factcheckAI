from django.apps import AppConfig


class SourcesConfig(AppConfig):
    """Django app config for the Wikipedia evidence pipeline.

    No models are defined here yet — the ``Source``/``Evidence`` tables are owned by
    Chunk A (deliverable A2). This config exists so the app can be added to
    ``INSTALLED_APPS`` once the Django project scaffold lands.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sources"
    verbose_name = "Wikipedia evidence pipeline"
