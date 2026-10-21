from django.contrib import admin

from .models import BerkasPermohonan, DokumenSurat, JenisSurat, OutboxEvent, PermohonanSurat, ProcessedEvent, RiwayatPersetujuan


@admin.register(JenisSurat)
class JenisSuratAdmin(admin.ModelAdmin):
    list_display = ("kode", "nama", "aktif", "template_file", "created_at", "updated_at")
    list_filter = ("aktif",)
    search_fields = ("kode", "nama", "deskripsi")


class BerkasPermohonanInline(admin.TabularInline):
    model = BerkasPermohonan
    extra = 0


class RiwayatPersetujuanInline(admin.TabularInline):
    model = RiwayatPersetujuan
    extra = 0
    readonly_fields = ("waktu",)


@admin.register(PermohonanSurat)
class PermohonanSuratAdmin(admin.ModelAdmin):
    list_display = ("nomor_permohonan", "jenis_surat", "pemohon_nama_snapshot", "status", "current_tahap", "diajukan_at")
    list_filter = ("status", "current_tahap", "jenis_surat", "pemohon_rt_snapshot", "pemohon_rw_snapshot")
    search_fields = ("nomor_permohonan", "pemohon_nik_snapshot", "pemohon_nama_snapshot")
    inlines = (BerkasPermohonanInline, RiwayatPersetujuanInline)


@admin.register(BerkasPermohonan)
class BerkasPermohonanAdmin(admin.ModelAdmin):
    list_display = ("id", "permohonan", "file_berkas", "diunggah_at")
    search_fields = ("permohonan__nomor_permohonan",)


@admin.register(RiwayatPersetujuan)
class RiwayatPersetujuanAdmin(admin.ModelAdmin):
    list_display = ("id", "permohonan", "tahap", "aksi", "oleh_user_id", "waktu")
    list_filter = ("tahap", "aksi")
    search_fields = ("permohonan__nomor_permohonan", "catatan")


@admin.register(DokumenSurat)
class DokumenSuratAdmin(admin.ModelAdmin):
    list_display = ("id", "permohonan", "status_generate", "file_final", "dibuat_at")
    list_filter = ("status_generate",)
    search_fields = ("permohonan__nomor_permohonan", "error_message")
    readonly_fields = ("public_token", "dibuat_at")


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
