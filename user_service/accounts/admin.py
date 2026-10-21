from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AuthAccount, OTPEmail, OutboxEvent, ProcessedEvent


@admin.register(AuthAccount)
class AuthAccountAdmin(UserAdmin):
    list_display = ("nik", "email", "peran", "is_active", "is_staff", "rt_snapshot", "rw_snapshot")
    list_filter = ("peran", "is_active", "is_staff", "is_superuser")
    search_fields = ("nik", "email")
    ordering = ("nik",)

    fieldsets = (
        (None, {"fields": ("nik", "email", "password")}),
        ("Role dan Status", {"fields": ("peran", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Snapshot Wilayah", {"fields": ("penduduk_id_snapshot", "rt_snapshot", "rw_snapshot")}),
        ("Aktivitas", {"fields": ("last_login", "terakhir_login_at")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("nik", "email", "peran", "password1", "password2", "is_active", "is_staff", "is_superuser"),
        }),
    )


@admin.register(OTPEmail)
class OTPEmailAdmin(admin.ModelAdmin):
    list_display = ("account", "tujuan", "kedaluwarsa_at", "dipakai_at", "created_at")
    list_filter = ("tujuan", "dipakai_at")
    search_fields = ("account__nik", "account__email")


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "source", "published_at", "created_at")
    list_filter = ("event_type", "source", "published_at")
    search_fields = ("event_id", "event_type", "source")
    readonly_fields = ("event_id", "created_at")


@admin.register(ProcessedEvent)
class ProcessedEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "processed_at")
    list_filter = ("event_type",)
    search_fields = ("event_id", "event_type")
