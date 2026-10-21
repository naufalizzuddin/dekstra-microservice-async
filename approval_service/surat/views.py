import json
from datetime import timedelta
from pathlib import Path

from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import BerkasPermohonan, DokumenSurat, JenisSurat, PermohonanSurat, RiwayatPersetujuan
from .serializers import (
    BerkasSuratSerializer,
    JenisSuratSerializer,
    PengajuanSuratSerializer,
    PermohonanWargaSerializer,
    RiwayatPengajuanDetailSerializer,
    RiwayatPengajuanSerializer,
    RiwayatPersetujuanDetailSerializer,
    RiwayatPersetujuanListSerializer,
    RiwayatPersetujuanSerializer,
    claim,
)


class JenisSuratListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        queryset = JenisSurat.objects.filter(aktif=True).order_by("kode")
        return Response(JenisSuratSerializer(queryset, many=True).data)


class PengajuanSuratView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = (
            PermohonanSurat.objects.select_related("jenis_surat")
            .filter(pemohon_user_id=claim(request, "user_id"))
            .order_by("-diajukan_at")
        )
        return Response(PermohonanWargaSerializer(queryset, many=True).data)

    def post(self, request):
        payload = {key: request.data.get(key) for key in request.data.keys()}
        payload.pop("file_berkas", None)
        data = payload.get("data")
        if isinstance(data, str):
            try:
                payload["data"] = json.loads(data)
            except json.JSONDecodeError:
                return Response({"data": "Data pengajuan harus berupa JSON yang valid."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = PengajuanSuratSerializer(data=payload, context={"request": request})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            instance = serializer.save()
            for file in request.FILES.getlist("file_berkas"):
                BerkasPermohonan.objects.create(permohonan=instance, file_berkas=file)
        return Response(
            PengajuanSuratSerializer(
                instance,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )


class BerkasSuratView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = BerkasSuratSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response({"id": obj.id, "diunggah_at": obj.diunggah_at}, status=status.HTTP_201_CREATED)


class DownloadBerkasPengajuanView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        berkas = get_object_or_404(BerkasPermohonan, public_token=token)
        if not berkas.file_berkas or not berkas.file_berkas.storage.exists(berkas.file_berkas.name):
            return Response({"detail": "Berkas tidak ditemukan."}, status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(
            berkas.file_berkas.open("rb"),
            filename=Path(berkas.file_berkas.name).name,
        )
        response["Cache-Control"] = "private, no-store"
        return response


class RiwayatPersetujuanListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = (
            PermohonanSurat.objects.select_related("jenis_surat")
            .prefetch_related("riwayat")
            .filter(status=PermohonanSurat.Status.DIAJUKAN)
        )
        role = claim(request, "peran")
        if role == 2:
            queryset = queryset.filter(current_tahap=PermohonanSurat.Tahap.RT, pemohon_rt_snapshot=claim(request, "rt"))
        elif role == 3:
            queryset = queryset.filter(current_tahap=PermohonanSurat.Tahap.RW, pemohon_rw_snapshot=claim(request, "rw"))
        elif role == 5:
            queryset = queryset.filter(current_tahap=PermohonanSurat.Tahap.ADMIN)
        elif role == 4:
            queryset = queryset.filter(current_tahap=PermohonanSurat.Tahap.KEPALA_DESA)
        else:
            return Response({"message": "Data tidak ditemukan"}, status=204)
        nomor_filter = request.query_params.get("nomor_permohonan")
        if nomor_filter:
            queryset = queryset.filter(nomor_permohonan=nomor_filter)
        return Response(RiwayatPersetujuanListSerializer(queryset.order_by("-diajukan_at"), many=True).data)


class InternalDashboardStatsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        try:
            role = int(request.query_params.get("role") or 0)
        except ValueError:
            role = 0
        rt = request.query_params.get("rt")
        rw = request.query_params.get("rw")
        today = timezone.localdate()
        dates = [today - timedelta(days=i) for i in range(6, -1, -1)]

        queryset = PermohonanSurat.objects.all()
        if role == 2 and rt:
            queryset = queryset.filter(pemohon_rt_snapshot=rt)
        elif role == 3 and rw:
            queryset = queryset.filter(pemohon_rw_snapshot=rw)

        active = queryset.filter(status=PermohonanSurat.Status.DIAJUKAN)
        progress = {
            "menunggu_verifikasi_rt": active.filter(current_tahap=PermohonanSurat.Tahap.RT).count(),
            "menunggu_verifikasi_rw": active.filter(current_tahap=PermohonanSurat.Tahap.RW).count(),
            "menunggu_verifikasi_admin": active.filter(current_tahap=PermohonanSurat.Tahap.ADMIN).count(),
            "menunggu_verifikasi_kades": active.filter(current_tahap=PermohonanSurat.Tahap.KEPALA_DESA).count(),
        }

        stage_by_role = {
            2: PermohonanSurat.Tahap.RT,
            3: PermohonanSurat.Tahap.RW,
            5: PermohonanSurat.Tahap.ADMIN,
            4: PermohonanSurat.Tahap.KEPALA_DESA,
        }
        stage = stage_by_role.get(role)
        approved_today = 0
        if stage:
            role_key = {
                2: "rt",
                3: "rw",
                5: "admin",
                4: "kades",
            }[role]
            progress[f"disetujui_{role_key}"] = (
                RiwayatPersetujuan.objects.filter(
                    permohonan__in=queryset,
                    tahap=stage,
                    aksi=RiwayatPersetujuan.Aksi.SETUJU,
                ).count()
            )
            progress[f"ditolak_{role_key}"] = (
                RiwayatPersetujuan.objects.filter(
                    permohonan__in=queryset,
                    tahap=stage,
                    aksi=RiwayatPersetujuan.Aksi.TOLAK,
                ).count()
            )
            approved_today = RiwayatPersetujuan.objects.filter(
                permohonan__in=queryset,
                tahap=stage,
                aksi=RiwayatPersetujuan.Aksi.SETUJU,
                waktu__date=today,
            ).count()

        chart = [
            {
                "tanggal": str(date),
                "jumlah": queryset.filter(diajukan_at__date=date).count(),
            }
            for date in dates
        ]

        return Response(
            {
                "progress": progress,
                "cards": {
                    "surat_perlu_verifikasi": progress["menunggu_verifikasi_admin"],
                    "disetujui_hari_ini_rt": approved_today if role == 2 else 0,
                    "disetujui_hari_ini_rw": approved_today if role == 3 else 0,
                    "disetujui_hari_ini_admin": approved_today if role == 5 else 0,
                    "disetujui_hari_ini_kades": approved_today if role == 4 else 0,
                },
                "pengajuan_7_hari_terakhir": chart,
            }
        )


class RiwayatPersetujuanDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        queryset = PermohonanSurat.objects.select_related(
            "jenis_surat"
        ).prefetch_related("berkas", "riwayat")
        role = claim(request, "peran")
        if role == 2:
            queryset = queryset.filter(
                current_tahap=PermohonanSurat.Tahap.RT,
                pemohon_rt_snapshot=claim(request, "rt"),
            )
        elif role == 3:
            queryset = queryset.filter(
                current_tahap=PermohonanSurat.Tahap.RW,
                pemohon_rw_snapshot=claim(request, "rw"),
            )
        elif role == 5:
            queryset = queryset.filter(
                current_tahap=PermohonanSurat.Tahap.ADMIN
            )
        elif role == 4:
            queryset = queryset.filter(
                current_tahap=PermohonanSurat.Tahap.KEPALA_DESA
            )
        else:
            return Response({"message": "Data tidak ditemukan"}, status=404)

        obj = queryset.filter(id=id).first()
        if not obj:
            return Response({"message": "Data tidak ditemukan"}, status=404)
        return Response(
            RiwayatPersetujuanDetailSerializer(
                obj,
                context={"request": request},
            ).data
        )


class RiwayatPersetujuanView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = RiwayatPersetujuanSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(
            {
                "id": obj.id,
                "tahap": obj.tahap,
                "aksi": obj.aksi,
                "waktu": obj.waktu,
                "catatan": obj.catatan,
                "oleh_akun": obj.oleh_user_id,
            },
            status=status.HTTP_201_CREATED,
        )


class RiwayatPengajuanWargaView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = (
            PermohonanSurat.objects.select_related(
                "jenis_surat",
                "dokumen",
            )
            .prefetch_related("riwayat")
            .filter(pemohon_user_id=claim(request, "user_id"))
            .order_by("-diajukan_at")
        )
        return Response(RiwayatPengajuanSerializer(queryset, many=True).data)


class RiwayatPengajuanDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, nomor_permohonan):
        obj = get_object_or_404(
            PermohonanSurat.objects.select_related("jenis_surat").prefetch_related("riwayat"),
            nomor_permohonan=nomor_permohonan,
            pemohon_user_id=claim(request, "user_id"),
        )
        return Response(RiwayatPengajuanDetailSerializer(obj, context={"request": request}).data)


class DownloadBerkasView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        doc = get_object_or_404(DokumenSurat, public_token=token)
        if not doc.file_final or not doc.file_final.name:
            return Response({"detail": "Dokumen belum tersedia."}, status=status.HTTP_404_NOT_FOUND)
        if not doc.file_final.storage.exists(doc.file_final.name):
            return Response(
                {"detail": "File dokumen belum ditemukan. Silakan tunggu proses generate atau generate ulang dokumen."},
                status=status.HTTP_404_NOT_FOUND,
            )
        response = FileResponse(doc.file_final.open("rb"))
        response["Cache-Control"] = "private, no-store"
        return response
