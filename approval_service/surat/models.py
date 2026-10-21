import os
import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def upload_berkas_permohonan_path(instance, filename):
    tanggal = timezone.now().strftime("%Y-%m-%d")
    nik = instance.permohonan.pemohon_nik_snapshot
    return f"permohonan/berkas/{tanggal}_{nik}/{filename}"


def upload_dokumen_surat_path(instance, filename):
    tanggal = timezone.now().strftime("%Y-%m-%d")
    nik = instance.permohonan.pemohon_nik_snapshot
    return f"permohonan/dokumen_final/{tanggal}_{nik}/{filename}"


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class JenisSurat(TimeStampedModel):
    def validate_template(value):
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in [".docx", ".xlsx"]:
            raise ValidationError("Template harus docx atau xlsx")

    id = models.BigAutoField(primary_key=True)
    kode = models.CharField(max_length=20, unique=True)
    nama = models.CharField(max_length=120)
    deskripsi = models.TextField(null=True, blank=True)
    aktif = models.BooleanField(default=True)
    template_file = models.FileField(upload_to="template_surat/", validators=[validate_template], null=True, blank=True)

    class Meta:
        db_table = "jenis_surat"


class PermohonanSurat(TimeStampedModel):
    class Status(models.IntegerChoices):
        DIAJUKAN = 1, "Diajukan"
        DITOLAK = 2, "Ditolak"
        SELESAI = 3, "Selesai"

    class Tahap(models.IntegerChoices):
        RT = 1, "RT"
        RW = 2, "RW"
        ADMIN = 3, "Admin"
        KEPALA_DESA = 4, "Kepala Desa"
        SELESAI = 5, "Selesai"

    id = models.BigAutoField(primary_key=True)
    nomor_permohonan = models.CharField(max_length=50, unique=True, blank=True)
    jenis_surat = models.ForeignKey(JenisSurat, on_delete=models.PROTECT, related_name="permohonan")
    pemohon_user_id = models.PositiveIntegerField()
    pemohon_nik_snapshot = models.CharField(max_length=16)
    pemohon_nama_snapshot = models.CharField(max_length=150)
    pemohon_rt_snapshot = models.PositiveSmallIntegerField()
    pemohon_rw_snapshot = models.PositiveSmallIntegerField()
    data = models.JSONField(default=dict)
    status = models.PositiveSmallIntegerField(choices=Status.choices, default=Status.DIAJUKAN)
    current_tahap = models.PositiveSmallIntegerField(choices=Tahap.choices, default=Tahap.RT)
    diajukan_at = models.DateTimeField(default=timezone.now)
    selesai_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "permohonan_surat"
        indexes = [
            models.Index(fields=["pemohon_user_id", "-diajukan_at"], name="idx_surat_pemohon_waktu"),
            models.Index(fields=["current_tahap", "status"], name="idx_surat_tahap_status"),
        ]

    def save(self, *args, **kwargs):
        needs_final_number = self._state.adding and not self.nomor_permohonan
        if needs_final_number:
            self.nomor_permohonan = f"PENDING/{uuid.uuid4()}"
        super().save(*args, **kwargs)
        if needs_final_number:
            now = timezone.localtime()
            self.nomor_permohonan = f"{now:%Y}/{now:%m}/{self.jenis_surat.kode}/{self.id}"
            super().save(update_fields=["nomor_permohonan"])


class BerkasPermohonan(models.Model):
    id = models.BigAutoField(primary_key=True)
    public_token = models.UUIDField(default=uuid.uuid4, unique=True)
    permohonan = models.ForeignKey(PermohonanSurat, on_delete=models.CASCADE, related_name="berkas")
    file_berkas = models.FileField(upload_to=upload_berkas_permohonan_path)
    diunggah_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "berkas_permohonan"


class RiwayatPersetujuan(models.Model):
    class Aksi(models.IntegerChoices):
        AJUKAN = 1, "Ajukan"
        SETUJU = 2, "Setuju"
        TOLAK = 3, "Tolak"

    id = models.BigAutoField(primary_key=True)
    permohonan = models.ForeignKey(PermohonanSurat, on_delete=models.CASCADE, related_name="riwayat")
    tahap = models.PositiveSmallIntegerField(choices=PermohonanSurat.Tahap.choices)
    aksi = models.PositiveSmallIntegerField(choices=Aksi.choices)
    oleh_user_id = models.PositiveIntegerField(null=True, blank=True)
    oleh_role_snapshot = models.PositiveSmallIntegerField(null=True, blank=True)
    catatan = models.TextField(null=True, blank=True)
    waktu = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "riwayat_persetujuan"
        indexes = [
            models.Index(fields=["permohonan", "-waktu"], name="idx_surat_riwayat_perm_waktu"),
            models.Index(fields=["tahap", "aksi"], name="idx_surat_riwayat_tahap_aksi"),
        ]


class DokumenSurat(models.Model):
    class StatusGenerate(models.IntegerChoices):
        MENUNGGU = 1, "Menunggu"
        DIPROSES = 2, "Diproses"
        SELESAI = 3, "Selesai"
        GAGAL = 4, "Gagal"

    id = models.BigAutoField(primary_key=True)
    public_token = models.UUIDField(default=uuid.uuid4, unique=True)
    permohonan = models.OneToOneField(PermohonanSurat, on_delete=models.CASCADE, related_name="dokumen")
    file_final = models.FileField(upload_to=upload_dokumen_surat_path, null=True, blank=True)
    status_generate = models.PositiveSmallIntegerField(choices=StatusGenerate.choices, default=StatusGenerate.MENUNGGU)
    error_message = models.TextField(null=True, blank=True)
    dibuat_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "dokumen_surat"


class OutboxEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    event_id = models.UUIDField(default=uuid.uuid4, unique=True)
    event_type = models.CharField(max_length=100)
    source = models.CharField(max_length=100, default="approval_service")
    payload = models.JSONField()
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "outbox_event"
        indexes = [models.Index(fields=["event_type", "published_at"], name="idx_surat_outbox_type")]


class ProcessedEvent(models.Model):
    event_id = models.UUIDField(unique=True)
    event_type = models.CharField(max_length=100)
    processed_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "processed_event"
