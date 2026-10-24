from django.contrib import admin

from apps.accounts.models import ApiKey, ModelSetting

# Key hashes are never displayed as raw keys — they don't exist in hint form.
admin.site.register(ApiKey)
admin.site.register(ModelSetting)
