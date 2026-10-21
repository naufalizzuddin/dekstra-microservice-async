from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .events import mark_event_published, save_outbox_event
from .models import AuthAccount, OTPEmail
from .tasks import send_otp_email


def generate_otp():
    if settings.LOAD_TESTING:
        return settings.LOAD_TEST_OTP

    from random import randint

    return str(randint(100000, 999999))


def otp_expiry_delta():
    if settings.LOAD_TESTING:
        return timedelta(hours=settings.LOAD_TEST_OTP_TTL_HOURS)
    return timedelta(minutes=5)


def token_response_for(account: AuthAccount):
    refresh = RefreshToken.for_user(account)
    refresh["nik"] = account.nik
    refresh["email"] = account.email
    refresh["peran"] = account.peran
    refresh["rt"] = account.rt_snapshot
    refresh["rw"] = account.rw_snapshot

    account.terakhir_login_at = timezone.now()
    account.save(update_fields=["terakhir_login_at", "updated_at"])

    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
        "peran": account.peran,
        "nik": account.nik,
        "email": account.email,
    }


class AccountLookupMixin:
    def get_account(self, attrs):
        nik = attrs.get("nik")
        email = attrs.get("email")

        if not (nik or email):
            raise serializers.ValidationError("Isi field NIK atau EMAIL")

        try:
            if email:
                return AuthAccount.objects.get(email=email)
            return AuthAccount.objects.get(nik=nik)
        except AuthAccount.DoesNotExist:
            raise serializers.ValidationError("Akun tidak ditemukan")

    def check_account_password(self, account, password):
        if not account.check_password(password):
            raise serializers.ValidationError("Password salah")
        if not account.is_active:
            raise serializers.ValidationError("Akun nonaktif")


class LoginOTPRequestSerializer(AccountLookupMixin, serializers.Serializer):
    nik = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        account = self.get_account(attrs)
        self.check_account_password(account, attrs.get("password"))

        otp = generate_otp()
        with transaction.atomic():
            OTPEmail.objects.filter(account=account, tujuan=OTPEmail.Tujuan.LOGIN).delete()
            OTPEmail.objects.create(
                account=account,
                tujuan=OTPEmail.Tujuan.LOGIN,
                kode_hash=make_password(otp),
                kedaluwarsa_at=timezone.now() + otp_expiry_delta(),
            )
            event = save_outbox_event(
                "otp.login_requested",
                {
                    "account_id": account.id,
                    "nik": account.nik,
                    "email": account.email,
                    "otp": otp,
                    "tujuan": "login",
                },
            )

        if settings.OTP_EMAIL_ENABLED:
            send_otp_email.apply_async(args=[event], queue="otp")
        else:
            mark_event_published(event["event_id"])
        response = {"message": "OTP telah dikirim"}
        if settings.OTP_EXPOSE_IN_RESPONSE or settings.LOAD_TESTING:
            response["otp"] = otp
        return response


class LoginSerializer(AccountLookupMixin, serializers.Serializer):
    nik = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    password = serializers.CharField(write_only=True)
    otp = serializers.CharField(write_only=True)

    def validate(self, attrs):
        account = self.get_account(attrs)
        self.check_account_password(account, attrs.get("password"))

        if settings.LOAD_TESTING and attrs.get("otp") == settings.LOAD_TEST_OTP:
            return token_response_for(account)

        otp_records = OTPEmail.objects.filter(account=account, tujuan=OTPEmail.Tujuan.LOGIN)
        for otp_record in otp_records:
            if check_password(attrs.get("otp"), otp_record.kode_hash):
                if otp_record.kedaluwarsa_at < timezone.now():
                    otp_record.delete()
                    raise serializers.ValidationError("Kode OTP telah kedaluwarsa")
                otp_record.delete()
                return token_response_for(account)

        raise serializers.ValidationError("OTP salah atau tidak ditemukan")


class ResetPasswordOTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate(self, attrs):
        try:
            account = AuthAccount.objects.get(email=attrs["email"])
        except AuthAccount.DoesNotExist:
            raise serializers.ValidationError("Akun dengan EMAIL tersebut tidak ditemukan")

        otp = generate_otp()
        with transaction.atomic():
            OTPEmail.objects.filter(account=account, tujuan=OTPEmail.Tujuan.RESET_PASSWORD).delete()
            OTPEmail.objects.create(
                account=account,
                tujuan=OTPEmail.Tujuan.RESET_PASSWORD,
                kode_hash=make_password(otp),
                kedaluwarsa_at=timezone.now() + otp_expiry_delta(),
            )
            event = save_outbox_event(
                "otp.reset_password_requested",
                {
                    "account_id": account.id,
                    "nik": account.nik,
                    "email": account.email,
                    "otp": otp,
                    "tujuan": "reset_password",
                },
            )

        send_otp_email.apply_async(args=[event], queue="otp")
        return {"message": "OTP reset password dikirim ke email terdaftar."}


class ResetPasswordVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        try:
            account = AuthAccount.objects.get(email=attrs["email"])
        except AuthAccount.DoesNotExist:
            raise serializers.ValidationError("Akun dengan EMAIL tersebut tidak ditemukan")

        otp_records = OTPEmail.objects.filter(
            account=account,
            tujuan=OTPEmail.Tujuan.RESET_PASSWORD,
        )
        for otp_record in otp_records:
            if check_password(attrs["otp"], otp_record.kode_hash):
                if otp_record.kedaluwarsa_at < timezone.now():
                    otp_record.delete()
                    raise serializers.ValidationError("Kode OTP telah kedaluwarsa")

                account.set_password(attrs["new_password"])
                account.save(update_fields=["password", "updated_at"])
                otp_record.delete()
                save_outbox_event(
                    "auth.password_changed",
                    {"account_id": account.id, "nik": account.nik, "email": account.email},
                )
                return {"message": "Password berhasil diperbarui."}

        raise serializers.ValidationError("OTP tidak valid")


class InternalAccountCreateSerializer(serializers.Serializer):
    nik = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField(required=False, write_only=True)
    password_hash = serializers.CharField(required=False, write_only=True)
    peran = serializers.IntegerField(default=AuthAccount.Peran.WARGA)
    penduduk_id_snapshot = serializers.CharField(required=False, allow_blank=True)
    rt = serializers.IntegerField(required=False, allow_null=True)
    rw = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs):
        if not (attrs.get("password") or attrs.get("password_hash")):
            raise serializers.ValidationError("password atau password_hash wajib diisi.")
        if AuthAccount.objects.filter(nik=attrs["nik"]).exists():
            raise serializers.ValidationError({"nik": "NIK sudah terdaftar di user_service."})
        if AuthAccount.objects.filter(email=attrs["email"]).exists():
            raise serializers.ValidationError({"email": "Email sudah terdaftar di user_service."})
        return attrs

    def create(self, validated_data):
        account = AuthAccount.create_from_registration(validated_data)
        save_outbox_event(
            "auth.account_created",
            {
                "account_id": account.id,
                "nik": account.nik,
                "email": account.email,
                "peran": account.peran,
                "rt": account.rt_snapshot,
                "rw": account.rw_snapshot,
            },
        )
        return account
