from django.contrib import admin

from nashvegas.models import Migration


class MigrationAdmin(admin.ModelAdmin):
    list_display = ["migration_label", "date_created", "scm_version"]
    list_filter = ["date_created"]
    search_fields = ["content", "migration_label"]


admin.site.register(Migration, MigrationAdmin)
