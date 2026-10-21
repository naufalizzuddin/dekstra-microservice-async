from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers

from .events import save_outbox_event
from .models import BerkasPermohonan, DokumenSurat, JenisSurat, PermohonanSurat, RiwayatPersetujuan
from .tasks import generate_document


def claim(request, key, default=None):
    if request.auth is None:
        return default
    value = request.auth.get(key, default)
    if key in {"user_id", "peran", "rt", "rw"} and isinstance(value, str) and value.isdigit():
        return int(value)
    return value


def permohonan_event_data(permohonan):
    return {
        "permohonan_id": permohonan.id,
        "nomor_permohonan": permohonan.nomor_permohonan,
        "jenis_surat_kode": permohonan.jenis_surat.kode,
        "jenis_surat_nama": permohonan.jenis_surat.nama,
        "pemohon_user_id": permohonan.pemohon_user_id,
        "pemohon_nik": permohonan.pemohon_nik_snapshot,
        "pemohon_nama": permohonan.pemohon_nama_snapshot,
        "rt": permohonan.pemohon_rt_snapshot,
        "rw": permohonan.pemohon_rw_snapshot,
    }


class JenisSuratSerializer(serializers.ModelSerializer):
    class Meta:
        model = JenisSurat
        fields = ["id", "kode", "nama", "aktif"]


class PengajuanSuratSerializer(serializers.ModelSerializer):
    jenis_surat = serializers.CharField(write_only=True)
    pemohon = serializers.SerializerMethodField()

    def get_pemohon(self, obj):
        return obj.pemohon_user_id

    class Meta:
        model = PermohonanSurat
        fields = [
            "id",
            "nomor_permohonan",
            "jenis_surat",
            "pemohon",
            "data",
            "status",
            "diajukan_at",
        ]
        read_only_fields = [
            "id",
            "nomor_permohonan",
            "pemohon",
            "status",
            "diajukan_at",
        ]

    def create(self, validated_data):
        request = self.context["request"]
        kode = validated_data.pop("jenis_surat")
        try:
            jenis_surat = JenisSurat.objects.get(kode=kode, aktif=True)
        except JenisSurat.DoesNotExist:
            raise serializers.ValidationError({"jenis_surat": "Jenis surat tidak ditemukan"})

        data = validated_data.get("data") or {}
        permohonan = PermohonanSurat.objects.create(
            jenis_surat=jenis_surat,
            pemohon_user_id=claim(request, "user_id"),
            pemohon_nik_snapshot=claim(request, "nik", ""),
            pemohon_nama_snapshot=data.get("pemohon_nama") or claim(request, "nik", ""),
            pemohon_rt_snapshot=claim(request, "rt"),
            pemohon_rw_snapshot=claim(request, "rw"),
            **validated_data,
        )
        RiwayatPersetujuan.objects.create(
            permohonan=permohonan,
            tahap=PermohonanSurat.Tahap.RT,
            aksi=RiwayatPersetujuan.Aksi.AJUKAN,
        )
        save_outbox_event(
            "surat.created",
            {
                **permohonan_event_data(permohonan),
                "status": "DIAJUKAN",
                "tahap": "RT",
                "diajukan_at": permohonan.diajukan_at.isoformat(),
            },
        )
        return permohonan


class PermohonanWargaSerializer(serializers.ModelSerializer):
    jenis_surat = serializers.SerializerMethodField()

    def get_jenis_surat(self, obj):
        return {"kode": obj.jenis_surat.kode, "nama": obj.jenis_surat.nama}

    class Meta:
        model = PermohonanSurat
        fields = [
            "id",
            "nomor_permohonan",
            "jenis_surat",
            "status",
            "diajukan_at",
        ]


class BerkasSuratSerializer(serializers.ModelSerializer):
    nomor_permohonan = serializers.CharField(write_only=True)

    class Meta:
        model = BerkasPermohonan
        fields = ["id", "file_berkas", "diunggah_at", "nomor_permohonan"]
        read_only_fields = ["id", "diunggah_at"]

    def create(self, validated_data):
        request = self.context["request"]
        nomor = validated_data.pop("nomor_permohonan")
        try:
            permohonan = PermohonanSurat.objects.get(nomor_permohonan=nomor)
        except PermohonanSurat.DoesNotExist:
            raise serializers.ValidationError({"nomor_permohonan": "Nomor permohonan tidak ditemukan"})
        if permohonan.pemohon_user_id != claim(request, "user_id"):
            raise serializers.ValidationError("Permohonan bukan milik user login")
        obj = BerkasPermohonan.objects.create(permohonan=permohonan, **validated_data)
        save_outbox_event(
            "surat.attachment_uploaded",
            {"permohonan_id": permohonan.id, "nomor_permohonan": permohonan.nomor_permohonan, "berkas_id": obj.id},
        )
        return obj


class RiwayatPersetujuanListSerializer(serializers.ModelSerializer):
    jenis_surat = serializers.SerializerMethodField()
    pemohon = serializers.SerializerMethodField()
    riwayat_aksi = serializers.SerializerMethodField()
    riwayat_tahap = serializers.IntegerField(
        source="current_tahap",
        read_only=True,
    )

    def get_jenis_surat(self, obj):
        return {"kode": obj.jenis_surat.kode, "nama": obj.jenis_surat.nama}

    def get_pemohon(self, obj):
        return {"nik": obj.pemohon_nik_snapshot, "nama": obj.pemohon_nama_snapshot}

    def get_riwayat_aksi(self, obj):
        latest = obj.riwayat.order_by("-waktu").first()
        return latest.aksi if latest else RiwayatPersetujuan.Aksi.AJUKAN

    class Meta:
        model = PermohonanSurat
        fields = [
            "id",
            "nomor_permohonan",
            "jenis_surat",
            "pemohon",
            "data",
            "status",
            "diajukan_at",
            "riwayat_aksi",
            "riwayat_tahap",
        ]


class BerkasPermohonanSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    def get_file_url(self, obj):
        request = self.context.get("request")
        if not obj.file_berkas:
            return None
        path = reverse(
            "berkas-pengajuan-download",
            kwargs={"token": obj.public_token},
        )
        return request.build_absolute_uri(path) if request else path

    class Meta:
        model = BerkasPermohonan
        fields = ["id", "file_url", "diunggah_at"]


class RiwayatPersetujuanDetailSerializer(serializers.ModelSerializer):
    jenis_surat = serializers.SerializerMethodField()
    pemohon = serializers.SerializerMethodField()
    riwayat_aksi = serializers.SerializerMethodField()
    riwayat_tahap = serializers.IntegerField(
        source="current_tahap",
        read_only=True,
    )
    berkas = BerkasPermohonanSerializer(many=True, read_only=True)
    riwayat = serializers.SerializerMethodField()

    def get_jenis_surat(self, obj):
        return {"kode": obj.jenis_surat.kode, "nama": obj.jenis_surat.nama}

    def get_pemohon(self, obj):
        return {
            "nik": obj.pemohon_nik_snapshot,
            "nama": obj.pemohon_nama_snapshot,
        }

    def get_riwayat_aksi(self, obj):
        latest = obj.riwayat.order_by("-waktu").first()
        return latest.aksi if latest else RiwayatPersetujuan.Aksi.AJUKAN

    def get_riwayat(self, obj):
        role_names = {
            1: "Warga",
            2: "RT",
            3: "RW",
            4: "Kepala Desa",
            5: "Admin",
        }
        return [
            {
                "actor": role_names.get(item.oleh_role_snapshot, "SYSTEM"),
                "status": item.get_aksi_display().upper(),
                "timestamp": item.waktu,
                "catatan": item.catatan,
            }
            for item in obj.riwayat.filter(
                aksi=RiwayatPersetujuan.Aksi.SETUJU
            ).order_by("waktu")
        ]

    class Meta:
        model = PermohonanSurat
        fields = [
            "id",
            "nomor_permohonan",
            "jenis_surat",
            "pemohon",
            "data",
            "status",
            "diajukan_at",
            "riwayat_aksi",
            "riwayat_tahap",
            "berkas",
            "riwayat",
        ]


class RiwayatPengajuanSerializer(serializers.ModelSerializer):
    jenis_surat = serializers.SerializerMethodField()
    riwayat_aksi = serializers.SerializerMethodField()
    riwayat_tahap = serializers.IntegerField(
        source="current_tahap",
        read_only=True,
    )
    public_token = serializers.SerializerMethodField()

    def get_jenis_surat(self, obj):
        return {"kode": obj.jenis_surat.kode, "nama": obj.jenis_surat.nama}

    def get_riwayat_aksi(self, obj):
        latest = obj.riwayat.order_by("-waktu").first()
        return latest.aksi if latest else RiwayatPersetujuan.Aksi.AJUKAN

    def get_public_token(self, obj):
        return str(obj.dokumen.public_token) if hasattr(obj, "dokumen") else None

    class Meta:
        model = PermohonanSurat
        fields = [
            "id",
            "nomor_permohonan",
            "jenis_surat",
            "data",
            "status",
            "diajukan_at",
            "riwayat_aksi",
            "riwayat_tahap",
            "public_token",
        ]


class RiwayatPersetujuanSerializer(serializers.Serializer):
    nomor_permohonan = serializers.CharField()
    aksi = serializers.IntegerField()
    catatan = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_aksi(self, value):
        if value not in [RiwayatPersetujuan.Aksi.SETUJU, RiwayatPersetujuan.Aksi.TOLAK]:
            raise serializers.ValidationError("Aksi harus SETUJU(2) atau TOLAK(3)")
        return value

    def validate(self, attrs):
        request = self.context["request"]
        try:
            permohonan = PermohonanSurat.objects.select_related("jenis_surat").get(nomor_permohonan=attrs["nomor_permohonan"])
        except PermohonanSurat.DoesNotExist:
            raise serializers.ValidationError({"nomor_permohonan": "Nomor permohonan tidak ditemukan"})
        role = claim(request, "peran")
        expected_role_by_tahap = {
            PermohonanSurat.Tahap.RT: 2,
            PermohonanSurat.Tahap.RW: 3,
            PermohonanSurat.Tahap.ADMIN: 5,
            PermohonanSurat.Tahap.KEPALA_DESA: 4,
        }
        if permohonan.status != PermohonanSurat.Status.DIAJUKAN:
            raise serializers.ValidationError("Permohonan tidak dalam status diajukan")
        if expected_role_by_tahap.get(permohonan.current_tahap) != role:
            raise serializers.ValidationError("Role user tidak sesuai dengan tahap saat ini")
        if role == 2 and permohonan.pemohon_rt_snapshot != claim(request, "rt"):
            raise serializers.ValidationError("RT user tidak sesuai dengan RT pemohon")
        if role == 3 and permohonan.pemohon_rw_snapshot != claim(request, "rw"):
            raise serializers.ValidationError("RW user tidak sesuai dengan RW pemohon")
        attrs["permohonan"] = permohonan
        return attrs

    def save(self):
        request = self.context["request"]
        permohonan = self.validated_data["permohonan"]
        aksi = self.validated_data["aksi"]
        catatan = self.validated_data.get("catatan")
        tahap_sekarang = permohonan.current_tahap

        with transaction.atomic():
            approval_history = RiwayatPersetujuan.objects.create(
                permohonan=permohonan,
                tahap=tahap_sekarang,
                aksi=aksi,
                oleh_user_id=claim(request, "user_id"),
                oleh_role_snapshot=claim(request, "peran"),
                catatan=catatan,
            )
            if aksi == RiwayatPersetujuan.Aksi.TOLAK:
                permohonan.status = PermohonanSurat.Status.DITOLAK
                permohonan.save(update_fields=["status", "updated_at"])
                event_type = "surat.rejected"
                event_data = {
                    **permohonan_event_data(permohonan),
                    "rejected_by_user_id": claim(request, "user_id"),
                    "tahap": permohonan.get_current_tahap_display(),
                    "catatan": catatan,
                }
            else:
                next_map = {
                    PermohonanSurat.Tahap.RT: PermohonanSurat.Tahap.RW,
                    PermohonanSurat.Tahap.RW: PermohonanSurat.Tahap.ADMIN,
                    PermohonanSurat.Tahap.ADMIN: PermohonanSurat.Tahap.KEPALA_DESA,
                    PermohonanSurat.Tahap.KEPALA_DESA: PermohonanSurat.Tahap.SELESAI,
                }
                event_map = {
                    PermohonanSurat.Tahap.RT: "surat.approved_by_rt",
                    PermohonanSurat.Tahap.RW: "surat.approved_by_rw",
                    PermohonanSurat.Tahap.ADMIN: "surat.approved_by_admin",
                    PermohonanSurat.Tahap.KEPALA_DESA: "surat.approved_by_kades",
                }
                next_tahap = next_map[tahap_sekarang]
                permohonan.current_tahap = next_tahap
                if next_tahap == PermohonanSurat.Tahap.SELESAI:
                    permohonan.status = PermohonanSurat.Status.SELESAI
                    permohonan.selesai_at = timezone.now()
                permohonan.save(update_fields=["current_tahap", "status", "selesai_at", "updated_at"])
                event_type = event_map[tahap_sekarang]
                event_data = {
                    **permohonan_event_data(permohonan),
                    "approved_by_user_id": claim(request, "user_id"),
                    "previous_tahap": PermohonanSurat.Tahap(tahap_sekarang).label,
                    "next_tahap": PermohonanSurat.Tahap(next_tahap).label,
                    "catatan": catatan,
                }
                if next_tahap == PermohonanSurat.Tahap.SELESAI:
                    DokumenSurat.objects.get_or_create(permohonan=permohonan)
                    save_outbox_event("surat.completed", permohonan_event_data(permohonan))
                    generate_document.apply_async(args=[permohonan.id], queue="document")

        save_outbox_event(event_type, event_data)
        return approval_history


class RiwayatPengajuanDetailSerializer(serializers.ModelSerializer):
    jenis_surat = serializers.SerializerMethodField()
    pemohon = serializers.SerializerMethodField()
    riwayat = serializers.SerializerMethodField()
    berkas = serializers.SerializerMethodField()
    dokumen_token = serializers.SerializerMethodField()
    riwayat_tahap = serializers.IntegerField(source="current_tahap", read_only=True)
    riwayat_aksi = serializers.SerializerMethodField()

    def get_jenis_surat(self, obj):
        return {"kode": obj.jenis_surat.kode, "nama": obj.jenis_surat.nama}

    def get_pemohon(self, obj):
        return {
            "nik": obj.pemohon_nik_snapshot,
            "nama": obj.pemohon_nama_snapshot,
            "rt": obj.pemohon_rt_snapshot,
            "rw": obj.pemohon_rw_snapshot,
        }

    def get_riwayat(self, obj):
        return [
            {
                "status": item.get_aksi_display(),
                "timestamp": item.waktu,
                "description": item.catatan or "-",
                "actor": item.get_tahap_display(),
            }
            for item in obj.riwayat.order_by("waktu")
        ]

    def get_berkas(self, obj):
        request = self.context.get("request")

        return [
            {
                "id": item.id,
                "file_url": (
                    request.build_absolute_uri(
                        reverse(
                            "berkas-pengajuan-download",
                            kwargs={"token": item.public_token},
                        )
                    )
                    if request and item.file_berkas
                    else reverse(
                        "berkas-pengajuan-download",
                        kwargs={"token": item.public_token},
                    )
                    if item.file_berkas
                    else None
                ),
                "diunggah_at": item.diunggah_at,
            }
            for item in obj.berkas.order_by("diunggah_at")
        ]

    def get_dokumen_token(self, obj):
        return str(obj.dokumen.public_token) if hasattr(obj, "dokumen") else None

    def get_riwayat_aksi(self, obj):
        latest = obj.riwayat.order_by("-waktu").first()
        return latest.aksi if latest else RiwayatPersetujuan.Aksi.AJUKAN

    class Meta:
        model = PermohonanSurat
        fields = [
            "id",
            "nomor_permohonan",
            "jenis_surat",
            "pemohon",
            "data",
            "status",
            "current_tahap",
            "riwayat_tahap",
            "riwayat_aksi",
            "diajukan_at",
            "riwayat",
            "berkas",
            "dokumen_token",
        ]
