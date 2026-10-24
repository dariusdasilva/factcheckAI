"""URLs for the accounts app (A3)."""

from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("settings/model/", views.model_settings, name="model-settings"),
    path("auth/token/", views.obtain_token, name="token"),
    path("auth/keys/", views.create_api_key, name="api-key-create"),
]
