from django.contrib import admin

from apps.checks.models import AuditLog, CheckRun, Claim, Evidence, Source

admin.site.register(Claim)
admin.site.register(CheckRun)
admin.site.register(Evidence)
admin.site.register(Source)
admin.site.register(AuditLog)
