from django.contrib import admin

from .models import KartuKeluarga, OutboxEvent, PendaftaranAkun, Penduduk, ProcessedEvent, WilayahRT, WilayahRW


@admin.register(WilayahRW)
class WilayahRWAdmin(admin.ModelAdmin):
    list_display = ("kode_rw", "created_at", "updated_at")
    search_fields = ("kode_rw",)


@admin.register(WilayahRT)
class WilayahRTAdmin(admin.ModelAdmin):
    list_display = ("id", "kode_rt", "rw", "created_at", "updated_at")
    list_filter = ("rw",)
    search_fields = ("kode_rt", "rw__kode_rw")


@admin.register(KartuKeluarga)
class KartuKeluargaAdmin(admin.ModelAdmin):
    list_display = ("nomor_kk", "rt", "alamat", "created_at", "updated_at")
    list_filter = ("rt__rw", "rt")
    search_fields = ("nomor_kk", "alamat")


@admin.register(Penduduk)
class PendudukAdmin(admin.ModelAdmin):
    list_display = ("nik", "nama_lengkap", "email", "rt", "status_kependudukan", "created_at")
    list_filter = ("status_kependudukan", "jenis_kelamin", "agama", "rt__rw", "rt")
    search_fields = ("nik", "nomor_kk", "nama_lengkap", "email", "no_hp")


@admin.register(PendaftaranAkun)
class PendaftaranAkunAdmin(admin.ModelAdmin):
    list_display = ("id", "nik", "nama_lengkap", "email", "rt", "status_verifikasi", "verified_at", "created_at")
    list_filter = ("status_verifikasi", "jenis_kelamin", "agama", "rt__rw", "rt")
    search_fields = ("nik", "nomor_kk", "nama_lengkap", "email", "no_hp")
    readonly_fields = ("password_hash",)


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
