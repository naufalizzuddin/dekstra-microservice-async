from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers

from accounts.models import AuthAccount

from .events import save_outbox_event
from .models import KartuKeluarga, PendaftaranAkun, Penduduk, WilayahRT, WilayahRW


class WilayahRWSerializer(serializers.ModelSerializer):
    class Meta:
        model = WilayahRW
        fields = ["kode_rw"]


class WilayahRTSerializer(serializers.ModelSerializer):
    class Meta:
        model = WilayahRT
        fields = ["id", "kode_rt"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    rt = serializers.IntegerField(write_only=True)
    rw = serializers.IntegerField(write_only=True)

    class Meta:
        model = PendaftaranAkun
        fields = [
            "id",
            "nomor_kk",
            "nik",
            "nama_lengkap",
            "tempat_lahir",
            "tanggal_lahir",
            "jenis_kelamin",
            "agama",
            "rt",
            "rw",
            "alamat",
            "email",
            "no_hp",
            "password",
            "kk_file",
            "ktp_file",
            "status_verifikasi",
            "verified_at",
        ]
        read_only_fields = ["id", "status_verifikasi", "verified_at"]
        extra_kwargs = {
            "nik": {"validators": []},
            "email": {"validators": []},
        }

    def validate(self, attrs):
        rt_id = attrs.get("rt")
        rw = attrs.get("rw")
        try:
            attrs["_rt_instance"] = WilayahRT.objects.get(id=rt_id, rw__kode_rw=rw)
        except WilayahRT.DoesNotExist:
            raise serializers.ValidationError({"rt": "RT tidak ditemukan pada RW tersebut."})

        if Penduduk.objects.filter(nik=attrs["nik"]).exists():
            raise serializers.ValidationError({"nik": "NIK sudah terdaftar."})
        if PendaftaranAkun.objects.filter(nik=attrs["nik"]).exists():
            raise serializers.ValidationError({"nik": "NIK sedang ditinjau pada pendaftaran."})
        if Penduduk.objects.filter(email=attrs["email"]).exists():
            raise serializers.ValidationError({"email": "Email sudah terdaftar."})
        if PendaftaranAkun.objects.filter(email=attrs["email"]).exists():
            raise serializers.ValidationError({"email": "Email sedang ditinjau pada pendaftaran."})
        if AuthAccount.objects.filter(nik=attrs["nik"]).exists():
            raise serializers.ValidationError({"nik": "NIK sudah terdaftar."})
        if AuthAccount.objects.filter(email=attrs["email"]).exists():
            raise serializers.ValidationError({"email": "Email sudah terdaftar."})
        return attrs

    def create(self, validated_data):
        rt_instance = validated_data.pop("_rt_instance")
        password_plain = validated_data.pop("password")
        validated_data.pop("rt")
        validated_data.pop("rw")
        validated_data["password_hash"] = make_password(password_plain)
        validated_data["rt"] = rt_instance
        instance = PendaftaranAkun.objects.create(**validated_data)
        save_outbox_event(
            "registrasi.created",
            {
                "pendaftaran_id": instance.id,
                "nik": instance.nik,
                "email": instance.email,
                "nama_lengkap": instance.nama_lengkap,
                "rt": instance.rt.kode_rt,
                "rw": instance.rt.rw.kode_rw,
                "status": instance.get_status_verifikasi_display(),
            },
        )
        return instance


class PendaftaranAkunListSerializer(serializers.ModelSerializer):
    class Meta:
        model = PendaftaranAkun
        fields = ["id", "nik", "nama_lengkap", "email", "created_at", "status_verifikasi"]


class PendaftaranAkunDetailSerializer(serializers.ModelSerializer):
    jenis_kelamin_display = serializers.CharField(source="get_jenis_kelamin_display", read_only=True)
    agama_display = serializers.CharField(source="get_agama_display", read_only=True)
    status_verifikasi_display = serializers.CharField(source="get_status_verifikasi_display", read_only=True)
    rt = serializers.StringRelatedField()
    rw = serializers.SerializerMethodField()
    kk_file = serializers.SerializerMethodField()
    ktp_file = serializers.SerializerMethodField()

    def get_rw(self, obj):
        return str(obj.rw) if obj.rw else None

    def get_kk_file(self, obj):
        return self._berkas_url(obj, "kk", obj.kk_file)

    def get_ktp_file(self, obj):
        return self._berkas_url(obj, "ktp", obj.ktp_file)

    def _berkas_url(self, obj, jenis, field):
        if not field:
            return None
        path = reverse("pendaftaran-berkas", kwargs={"id": obj.id, "jenis": jenis})
        request = self.context.get("request")
        return request.build_absolute_uri(path) if request else path

    class Meta:
        model = PendaftaranAkun
        fields = [
            "id",
            "nik",
            "nomor_kk",
            "nama_lengkap",
            "tempat_lahir",
            "tanggal_lahir",
            "jenis_kelamin",
            "jenis_kelamin_display",
            "agama",
            "agama_display",
            "alamat",
            "email",
            "no_hp",
            "status_verifikasi",
            "status_verifikasi_display",
            "rt",
            "rw",
            "kk_file",
            "ktp_file",
            "created_at",
        ]


class VerifikasiPendaftaranSerializer(serializers.Serializer):
    aksi = serializers.IntegerField()

    def validate_aksi(self, value):
        if value not in [0, 1]:
            raise serializers.ValidationError("Aksi harus 0 atau 1")
        return value

    def save(self, *, instance: PendaftaranAkun, actor_user_id: int | None, actor_role: int | None):
        aksi = self.validated_data["aksi"]

        if instance.status_verifikasi != PendaftaranAkun.StatusVerifikasi.DITINJAU:
            raise serializers.ValidationError("Status pendaftaran yang telah ditinjau tidak dapat diubah.")

        if aksi == 0:
            instance.status_verifikasi = PendaftaranAkun.StatusVerifikasi.DITOLAK
            instance.verified_by_user_id = actor_user_id
            instance.verified_by_role = actor_role
            instance.verified_at = timezone.now()
            instance.save(update_fields=["status_verifikasi", "verified_by_user_id", "verified_by_role", "verified_at", "updated_at"])
            save_outbox_event(
                "registrasi.rejected",
                {"pendaftaran_id": instance.id, "nik": instance.nik, "email": instance.email},
            )
            return instance

        with transaction.atomic():
            kk, _ = KartuKeluarga.objects.get_or_create(
                nomor_kk=instance.nomor_kk,
                defaults={
                    "rt": instance.rt,
                    "alamat": instance.alamat,
                    "kk_file": instance.kk_file,
                },
            )
            penduduk = Penduduk.objects.create(
                nik=instance.nik,
                nomor_kk=instance.nomor_kk,
                kk=kk,
                nama_lengkap=instance.nama_lengkap,
                tempat_lahir=instance.tempat_lahir,
                tanggal_lahir=instance.tanggal_lahir,
                jenis_kelamin=instance.jenis_kelamin,
                agama=instance.agama,
                email=instance.email,
                no_hp=instance.no_hp,
                rt=instance.rt,
                ktp_file=instance.ktp_file,
            )
            auth_account = AuthAccount.create_from_registration(
                {
                    "nik": instance.nik,
                    "email": instance.email,
                    "password_hash": instance.password_hash,
                    "penduduk_id_snapshot": str(penduduk.id),
                    "peran": AuthAccount.Peran.WARGA,
                    "rt": instance.rt.kode_rt,
                    "rw": instance.rt.rw.kode_rw,
                }
            )
            instance.status_verifikasi = PendaftaranAkun.StatusVerifikasi.DISETUJUI
            instance.verified_by_user_id = actor_user_id
            instance.verified_by_role = actor_role
            instance.verified_at = timezone.now()
            instance.save(update_fields=["status_verifikasi", "verified_by_user_id", "verified_by_role", "verified_at", "updated_at"])

        event_data = {
            "user_id": auth_account.id,
            "penduduk_id": penduduk.id,
            "nik": penduduk.nik,
            "email": penduduk.email,
            "nama_lengkap": penduduk.nama_lengkap,
            "nomor_kk": penduduk.nomor_kk,
            "tempat_lahir": penduduk.tempat_lahir,
            "tanggal_lahir": penduduk.tanggal_lahir.isoformat() if penduduk.tanggal_lahir else None,
            "jenis_kelamin": penduduk.jenis_kelamin,
            "no_hp": penduduk.no_hp,
            "rt": penduduk.rt.kode_rt,
            "rw": penduduk.rt.rw.kode_rw,
            "alamat": penduduk.kk.alamat,
            "peran": 1,
        }
        save_outbox_event("registrasi.approved", event_data)
        save_outbox_event("penduduk.created", event_data)
        return instance
