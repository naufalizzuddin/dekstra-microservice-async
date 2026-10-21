import uuid

from django.db import models
from django.utils import timezone


class ProfileReadModel(models.Model):
    user_id = models.PositiveIntegerField(primary_key=True)
    account_id = models.PositiveIntegerField(null=True, blank=True)
    penduduk_id = models.PositiveIntegerField(null=True, blank=True)
    nik = models.CharField(max_length=16, unique=True)
    nomor_kk = models.CharField(max_length=16, null=True, blank=True)
    nama_lengkap = models.CharField(max_length=150)
    jenis_kelamin = models.PositiveSmallIntegerField(null=True, blank=True)
    tempat_lahir = models.CharField(max_length=80, null=True, blank=True)
    tanggal_lahir = models.DateField(null=True, blank=True)
    alamat = models.CharField(max_length=255, null=True, blank=True)
    email = models.EmailField(max_length=160)
    nomor_telepon = models.CharField(max_length=32, null=True, blank=True)
    nip = models.CharField(max_length=32, null=True, blank=True)
    peran = models.PositiveSmallIntegerField()
    rt = models.PositiveSmallIntegerField(null=True, blank=True)
    rw = models.PositiveSmallIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "profile_read_model"
        indexes = [
            models.Index(fields=["peran", "rt", "rw"], name="idx_dash_profile_scope"),
        ]


class DashboardSummary(models.Model):
    id = models.BigAutoField(primary_key=True)
    scope_type = models.CharField(max_length=30)
    scope_id = models.CharField(max_length=50)
    peran = models.PositiveSmallIntegerField()
    isi_cards_json = models.JSONField(default=dict)
    progress_json = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dashboard_summary"
        constraints = [
            models.UniqueConstraint(fields=["scope_type", "scope_id", "peran"], name="uniq_dash_summary_scope"),
        ]


class DashboardChartDaily(models.Model):
    id = models.BigAutoField(primary_key=True)
    scope_type = models.CharField(max_length=30)
    scope_id = models.CharField(max_length=50)
    tanggal = models.DateField()
    jumlah_pengajuan = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dashboard_chart_daily"
        constraints = [
            models.UniqueConstraint(fields=["scope_type", "scope_id", "tanggal"], name="uniq_dash_chart_daily"),
        ]


class Notifikasi(models.Model):
    id = models.BigAutoField(primary_key=True)
    penerima_user_id = models.PositiveIntegerField()
    tipe = models.CharField(max_length=80)
    judul = models.CharField(max_length=160)
    pesan = models.TextField()
    permohonan_nomor = models.CharField(max_length=50, null=True, blank=True)
    sudah_dibaca = models.BooleanField(default=False)
    dibaca_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "notifikasi"
        indexes = [
            models.Index(fields=["penerima_user_id", "sudah_dibaca", "-created_at"], name="idx_dash_notif_user"),
        ]


class ProcessedEvent(models.Model):
    event_id = models.UUIDField(unique=True)
    event_type = models.CharField(max_length=100)
    processed_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "processed_event"
