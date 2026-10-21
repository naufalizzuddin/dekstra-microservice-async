from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


digit_16_validator = RegexValidator(
    regex=r"^\d{16}$",
    message="Nomor tidak valid (16 digit)",
)


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuthAccountManager(BaseUserManager):
    def create_user(self, nik, email, password=None, **extra_fields):
        if not nik:
            raise ValueError("NIK wajib diisi.")
        if not email:
            raise ValueError("Email wajib diisi.")

        account = self.model(nik=nik, email=self.normalize_email(email), **extra_fields)
        if password:
            account.set_password(password)
        else:
            account.set_unusable_password()
        account.save(using=self._db)
        return account

    def create_superuser(self, nik, email, password=None, **extra_fields):
        extra_fields.setdefault("peran", AuthAccount.Peran.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(nik=nik, email=email, password=password, **extra_fields)


class AuthAccount(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    class Peran(models.IntegerChoices):
        WARGA = 1, "Warga"
        RT = 2, "RT"
        RW = 3, "RW"
        KEPALA_DESA = 4, "Kepala Desa"
        ADMIN = 5, "Admin"

    id = models.BigAutoField(primary_key=True)
    nik = models.CharField(max_length=16, unique=True, validators=[digit_16_validator])
    email = models.EmailField(max_length=160, unique=True)
    peran = models.PositiveSmallIntegerField(choices=Peran.choices)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    penduduk_id_snapshot = models.CharField(max_length=64, null=True, blank=True)
    rt_snapshot = models.PositiveSmallIntegerField(null=True, blank=True)
    rw_snapshot = models.PositiveSmallIntegerField(null=True, blank=True)
    terakhir_login_at = models.DateTimeField(null=True, blank=True)

    objects = AuthAccountManager()

    USERNAME_FIELD = "nik"
    REQUIRED_FIELDS = ["email"]

    class Meta:
        db_table = "auth_account"

    def __str__(self):
        return f"{self.nik} - {self.email} - {self.get_peran_display()}"

    @classmethod
    def create_from_registration(cls, payload: dict):
        password_hash = payload.get("password_hash")
        password = payload.get("password")
        account = cls(
            nik=payload["nik"],
            email=payload["email"],
            peran=payload.get("peran", cls.Peran.WARGA),
            penduduk_id_snapshot=payload.get("penduduk_id_snapshot"),
            rt_snapshot=payload.get("rt"),
            rw_snapshot=payload.get("rw"),
            is_active=payload.get("is_active", True),
        )
        if password_hash:
            account.password = password_hash
        else:
            account.password = make_password(password)
        account.save()
        return account


class OTPEmail(models.Model):
    class Tujuan(models.IntegerChoices):
        LOGIN = 1, "Login"
        RESET_PASSWORD = 2, "Reset Password"

    id = models.BigAutoField(primary_key=True)
    account = models.ForeignKey(AuthAccount, on_delete=models.CASCADE, related_name="otp_email")
    tujuan = models.PositiveSmallIntegerField(choices=Tujuan.choices)
    kode_hash = models.CharField(max_length=255)
    kedaluwarsa_at = models.DateTimeField()
    dipakai_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "otp_email"
        indexes = [
            models.Index(fields=["account", "tujuan"], name="idx_otp_account_tujuan"),
            models.Index(fields=["kedaluwarsa_at"], name="idx_otp_expiry"),
        ]


class OutboxEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    event_id = models.UUIDField(unique=True)
    event_type = models.CharField(max_length=100)
    source = models.CharField(max_length=100)
    payload = models.JSONField()
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "outbox_event"
        indexes = [
            models.Index(fields=["event_type", "published_at"], name="idx_auth_outbox_type"),
        ]


class ProcessedEvent(models.Model):
    event_id = models.UUIDField(unique=True)
    event_type = models.CharField(max_length=100)
    processed_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "processed_event"

