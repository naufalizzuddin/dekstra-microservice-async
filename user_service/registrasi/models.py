import os
import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, RegexValidator
from django.db import models
from django.utils import timezone


digit_16_validator = RegexValidator(
    regex=r"^\d{16}$",
    message="Nomor tidak valid (16 digit)",
)
image_extension_validator = FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png"])
no_hp_validator = RegexValidator(
    regex=r"^0\d{9,14}$",
    message="Nomor HP harus diawali 0 dan terdiri dari 10-15 digit angka",
)


def tanggal_lahir_validator(value):
    today = timezone.localdate()
    if value >= today:
        raise ValidationError("Tanggal lahir tidak valid")
    umur = (today - value).days // 365
    if umur < 17:
        raise ValidationError("Umur minimal 17 tahun")


def upload_kk_register_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    tanggal = timezone.now().strftime("%Y-%m-%d")
    waktu = timezone.now().strftime("%H%M%S")
    return f"pendaftaran_akun/kartu_keluarga/{tanggal}/{instance.nik}_{waktu}{ext}"


def upload_ktp_register_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    tanggal = timezone.now().strftime("%Y-%m-%d")
    waktu = timezone.now().strftime("%H%M%S")
    return f"pendaftaran_akun/ktp/{tanggal}/{instance.nik}_{waktu}{ext}"


def upload_kk_final_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"dokumen_pendukung/kartu_keluarga/{instance.nomor_kk}{ext}"


def upload_ktp_final_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"dokumen_pendukung/ktp/{instance.nik}{ext}"


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class WilayahRW(TimeStampedModel):
    kode_rw = models.PositiveSmallIntegerField(primary_key=True)

    class Meta:
        db_table = "wilayah_rw"

    def __str__(self):
        return f"RW {self.kode_rw:02d}"


class WilayahRT(TimeStampedModel):
    id = models.BigAutoField(primary_key=True)
    rw = models.ForeignKey(WilayahRW, on_delete=models.PROTECT, related_name="daftar_rt")
    kode_rt = models.PositiveSmallIntegerField()

    class Meta:
        db_table = "wilayah_rt"
        constraints = [
            models.UniqueConstraint(fields=["rw", "kode_rt"], name="uniq_reg_wilayah_rt_per_rw"),
        ]

    def __str__(self):
        return f"RT {self.kode_rt:02d} / RW {self.rw.kode_rw:02d}"


class KartuKeluarga(TimeStampedModel):
    nomor_kk = models.CharField(max_length=16, primary_key=True, validators=[digit_16_validator])
    rt = models.ForeignKey(WilayahRT, on_delete=models.PROTECT, related_name="daftar_kk")
    alamat = models.CharField(max_length=255, null=True, blank=True)
    kk_file = models.FileField(
        upload_to=upload_kk_final_path,
        validators=[image_extension_validator],
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "kartu_keluarga"


class Penduduk(TimeStampedModel):
    class JenisKelamin(models.IntegerChoices):
        LAKI_LAKI = 1, "Laki-laki"
        PEREMPUAN = 2, "Perempuan"

    class StatusKependudukan(models.IntegerChoices):
        AKTIF = 1, "Aktif"
        PINDAH = 2, "Pindah"
        MENINGGAL = 3, "Meninggal"
        NONAKTIF = 4, "Nonaktif"

    class Agama(models.IntegerChoices):
        ISLAM = 1, "Islam"
        KRISTEN = 2, "Kristen"
        KATOLIK = 3, "Katolik"
        HINDU = 4, "Hindu"
        BUDDHA = 5, "Buddha"
        KONGHUCU = 6, "Konghucu"
        KEPERCAYAAN = 7, "Kepercayaan terhadap Tuhan Yang Maha Esa"

    id = models.BigAutoField(primary_key=True)
    nik = models.CharField(max_length=16, unique=True, validators=[digit_16_validator])
    nomor_kk = models.CharField(max_length=16, validators=[digit_16_validator])
    kk = models.ForeignKey(KartuKeluarga, on_delete=models.PROTECT, related_name="daftar_penduduk")
    nama_lengkap = models.CharField(max_length=150)
    tempat_lahir = models.CharField(max_length=80, null=True, blank=True)
    tanggal_lahir = models.DateField(validators=[tanggal_lahir_validator])
    jenis_kelamin = models.PositiveSmallIntegerField(choices=JenisKelamin.choices)
    agama = models.PositiveSmallIntegerField(choices=Agama.choices, null=True, blank=True)
    email = models.EmailField(max_length=160, unique=True)
    no_hp = models.CharField(max_length=32, validators=[no_hp_validator])
    rt = models.ForeignKey(WilayahRT, on_delete=models.PROTECT, related_name="penduduk")
    status_kependudukan = models.PositiveSmallIntegerField(
        choices=StatusKependudukan.choices,
        default=StatusKependudukan.AKTIF,
    )
    ktp_file = models.FileField(
        upload_to=upload_ktp_final_path,
        validators=[image_extension_validator],
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "penduduk"
        indexes = [
            models.Index(fields=["nik"], name="idx_reg_penduduk_nik"),
            models.Index(fields=["rt"], name="idx_reg_penduduk_rt"),
        ]

    @property
    def rw(self):
        return self.rt.rw if self.rt_id else None


class PendaftaranAkun(TimeStampedModel):
    class StatusVerifikasi(models.IntegerChoices):
        DITINJAU = 1, "Ditinjau"
        DITOLAK = 2, "Ditolak"
        DISETUJUI = 3, "Disetujui"

    id = models.BigAutoField(primary_key=True)
    nomor_kk = models.CharField(max_length=16, validators=[digit_16_validator])
    nik = models.CharField(max_length=16, unique=True, validators=[digit_16_validator])
    nama_lengkap = models.CharField(max_length=150)
    tempat_lahir = models.CharField(max_length=100)
    tanggal_lahir = models.DateField(validators=[tanggal_lahir_validator])
    jenis_kelamin = models.PositiveSmallIntegerField(choices=Penduduk.JenisKelamin.choices)
    agama = models.PositiveSmallIntegerField(choices=Penduduk.Agama.choices, null=True, blank=True)
    rt = models.ForeignKey(WilayahRT, on_delete=models.PROTECT, related_name="pendaftaran_akun")
    alamat = models.CharField(max_length=255)
    email = models.EmailField(max_length=160, unique=True)
    no_hp = models.CharField(max_length=32, validators=[no_hp_validator])
    password_hash = models.CharField(max_length=255)
    kk_file = models.FileField(
        validators=[image_extension_validator],
        upload_to=upload_kk_register_path,
        null=True,
        blank=True,
    )
    ktp_file = models.FileField(
        validators=[image_extension_validator],
        upload_to=upload_ktp_register_path,
        null=True,
        blank=True,
    )
    status_verifikasi = models.PositiveSmallIntegerField(
        choices=StatusVerifikasi.choices,
        default=StatusVerifikasi.DITINJAU,
    )
    verified_by_user_id = models.PositiveIntegerField(null=True, blank=True)
    verified_by_role = models.PositiveSmallIntegerField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "pendaftaran_akun"
        indexes = [
            models.Index(fields=["status_verifikasi"], name="idx_reg_pendaftaran_status"),
            models.Index(fields=["nik"], name="idx_reg_pendaftaran_nik"),
            models.Index(fields=["nomor_kk"], name="idx_reg_pendaftaran_kk"),
        ]

    @property
    def rw(self):
        return self.rt.rw if self.rt_id else None


class OutboxEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    event_id = models.UUIDField(default=uuid.uuid4, unique=True)
    event_type = models.CharField(max_length=100)
    source = models.CharField(max_length=100, default="user_service")
    payload = models.JSONField()
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "registrasi_outbox_event"
        indexes = [models.Index(fields=["event_type", "published_at"], name="idx_reg_outbox_type")]


class ProcessedEvent(models.Model):
    event_id = models.UUIDField(unique=True)
    event_type = models.CharField(max_length=100)
    processed_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "registrasi_processed_event"
