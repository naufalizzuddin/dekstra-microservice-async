from django.contrib import admin

from .models import DashboardChartDaily, DashboardSummary, Notifikasi, ProcessedEvent, ProfileReadModel


@admin.register(ProfileReadModel)
class ProfileReadModelAdmin(admin.ModelAdmin):
    list_display = ("user_id", "nik", "nama_lengkap", "email", "nip", "peran", "rt", "rw", "updated_at")
    list_filter = ("peran", "rt", "rw")
    search_fields = ("nik", "nama_lengkap", "email", "nip")


@admin.register(DashboardSummary)
class DashboardSummaryAdmin(admin.ModelAdmin):
    list_display = ("id", "scope_type", "scope_id", "peran", "updated_at")
    list_filter = ("scope_type", "peran")
    search_fields = ("scope_type", "scope_id")


@admin.register(DashboardChartDaily)
class DashboardChartDailyAdmin(admin.ModelAdmin):
    list_display = ("scope_type", "scope_id", "tanggal", "jumlah_pengajuan", "updated_at")
    list_filter = ("scope_type", "tanggal")
    search_fields = ("scope_type", "scope_id")


@admin.register(Notifikasi)
class NotifikasiAdmin(admin.ModelAdmin):
    list_display = ("id", "penerima_user_id", "tipe", "judul", "sudah_dibaca", "created_at")
    list_filter = ("tipe", "sudah_dibaca")
    search_fields = ("judul", "pesan", "permohonan_nomor")


@admin.register(ProcessedEvent)
class ProcessedEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "processed_at")
    list_filter = ("event_type",)
    search_fields = ("event_id", "event_type")
