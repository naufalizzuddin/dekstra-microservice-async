from rest_framework import serializers

from .models import DashboardSummary, Notifikasi, ProfileReadModel


class ProfileSerializer(serializers.ModelSerializer):
    jenis_kelamin = serializers.SerializerMethodField()
    peran = serializers.SerializerMethodField()

    def get_jenis_kelamin(self, obj):
        return {1: "Laki-laki", 2: "Perempuan"}.get(obj.jenis_kelamin)

    def get_peran(self, obj):
        return {
            1: "Warga",
            2: "RT",
            3: "RW",
            4: "Kepala Desa",
            5: "Admin",
        }.get(obj.peran)

    class Meta:
        model = ProfileReadModel
        fields = [
            "nik",
            "nomor_kk",
            "nama_lengkap",
            "jenis_kelamin",
            "tempat_lahir",
            "tanggal_lahir",
            "alamat",
            "email",
            "nomor_telepon",
            "peran",
            "rt",
            "rw",
        ]


class DashboardSerializer(serializers.Serializer):
    peran = serializers.CharField()
    isi_cards = serializers.DictField()
    progress = serializers.DictField()
    pengajuan_7_hari_terakhir = serializers.ListField()


class NotifikasiSerializer(serializers.ModelSerializer):
    permohonan = serializers.CharField(
        source="permohonan_nomor",
        read_only=True,
    )
    nomor_permohonan = serializers.CharField(
        source="permohonan_nomor",
        read_only=True,
    )

    class Meta:
        model = Notifikasi
        fields = [
            "id",
            "tipe",
            "judul",
            "pesan",
            "sudah_dibaca",
            "dibaca_at",
            "created_at",
            "permohonan",
            "nomor_permohonan",
        ]
