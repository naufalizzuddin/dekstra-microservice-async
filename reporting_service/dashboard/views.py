import json
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DashboardChartDaily, DashboardSummary, Notifikasi, ProfileReadModel
from .serializers import DashboardSerializer, NotifikasiSerializer, ProfileSerializer


def claim(request, key, default=None):
    if request.auth is None:
        return default
    return request.auth.get(key, default)


def current_profile_or_claims(request):
    profile = ProfileReadModel.objects.filter(user_id=claim(request, "user_id")).first()
    if profile:
        return {
            "exists": True,
            "peran": profile.peran,
            "rt": profile.rt,
            "rw": profile.rw,
            "profile": profile,
        }
    return {
        "exists": False,
        "peran": int(claim(request, "peran", 1) or 1),
        "rt": claim(request, "rt"),
        "rw": claim(request, "rw"),
        "profile": None,
    }


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def total_warga_for(identity):
    queryset = ProfileReadModel.objects.filter(peran=1)
    if identity["peran"] == 2:
        rt = to_int(identity["rt"])
        if rt is None:
            return 0
        queryset = queryset.filter(rt=rt)
    elif identity["peran"] == 3:
        rw = to_int(identity["rw"])
        if rw is None:
            return 0
        queryset = queryset.filter(rw=rw)
    return queryset.count()


def fetch_document_dashboard_stats(identity):
    params = {"role": identity["peran"]}
    if identity["rt"] is not None:
        params["rt"] = identity["rt"]
    if identity["rw"] is not None:
        params["rw"] = identity["rw"]

    url = f"{settings.DOCUMENT_SERVICE_URL.rstrip('/')}/internal/dashboard-stats/?{urlencode(params)}"
    try:
        with urlopen(url, timeout=settings.DOCUMENT_DASHBOARD_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None


def contract_dashboard_cards(identity, cards, progress, total_warga):
    role = identity["peran"]

    if role == 2:
        return {
            "total_warga_rt": total_warga,
            "menunggu_verifikasi_rt": progress.get("menunggu_verifikasi_rt", 0),
            "disetujui_hari_ini_rt": cards.get("disetujui_hari_ini_rt", 0),
        }
    if role == 3:
        return {
            "total_warga_rw": total_warga,
            "menunggu_verifikasi_rw": progress.get("menunggu_verifikasi_rw", 0),
            "disetujui_hari_ini_rw": cards.get("disetujui_hari_ini_rw", 0),
        }
    if role == 4:
        return {
            "total_warga_desa": total_warga,
            "menunggu_verifikasi_kades": progress.get("menunggu_verifikasi_kades", 0),
            "disetujui_hari_ini_kades": cards.get("disetujui_hari_ini_kades", 0),
        }
    return {
        "total_data_penduduk": total_warga,
        "pendaftaran_perlu_verifikasi": cards.get(
            "pendaftaran_perlu_verifikasi",
            0,
        ),
        "surat_perlu_verifikasi": progress.get(
            "menunggu_verifikasi_admin",
            0,
        ),
    }


def role_display(role):
    return {
        1: "Warga",
        2: "RT",
        3: "RW",
        4: "Kepala Desa",
        5: "Admin",
    }.get(role, str(role))


class ProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        identity = current_profile_or_claims(request)
        if identity["profile"]:
            return Response(ProfileSerializer(identity["profile"]).data)
        return Response(
            {
                "nik": claim(request, "nik", ""),
                "nomor_kk": None,
                "nama_lengkap": "",
                "jenis_kelamin": None,
                "tempat_lahir": None,
                "tanggal_lahir": None,
                "alamat": None,
                "email": "",
                "nomor_telepon": None,
                "peran": role_display(identity["peran"]),
                "rt": identity["rt"],
                "rw": identity["rw"],
            }
        )


class InternalKepalaDesaView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        profile = (
            ProfileReadModel.objects.filter(peran=4)
            .exclude(nama_lengkap="")
            .order_by("user_id")
            .first()
        )
        if not profile:
            return Response({"nama_lengkap": None, "nip": None}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                "user_id": profile.user_id,
                "nik": profile.nik,
                "nama_lengkap": profile.nama_lengkap,
                "nip": profile.nip,
            }
        )


class DashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        identity = current_profile_or_claims(request)
        if identity["peran"] not in {2, 3, 4, 5}:
            return Response(
                {"detail": "Role tidak diizinkan."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if identity["peran"] == 2:
            scope_type, scope_id = "rt", identity["rt"]
        elif identity["peran"] == 3:
            scope_type, scope_id = "rw", identity["rw"]
        else:
            scope_type, scope_id = "desa", "all"

        summary = DashboardSummary.objects.filter(
            scope_type=scope_type,
            scope_id=str(scope_id),
            peran=identity["peran"],
        ).first()
        today = timezone.localdate()
        dates = [today - timedelta(days=i) for i in range(6, -1, -1)]
        chart_rows = DashboardChartDaily.objects.filter(
            scope_type=scope_type,
            scope_id=str(scope_id),
            tanggal__in=dates,
        )
        count_map = {row.tanggal: row.jumlah_pengajuan for row in chart_rows}
        fallback_cards = summary.isi_cards_json if summary else {}
        fallback_progress = summary.progress_json if summary else {}
        fallback_chart = [
            {"tanggal": str(date), "jumlah": count_map.get(date, 0)}
            for date in dates
        ]

        document_stats = (
            fetch_document_dashboard_stats(identity)
            if settings.REPORTING_DASHBOARD_FETCH_DOCUMENT_STATS
            else None
        )
        progress = document_stats.get("progress", fallback_progress) if document_stats else fallback_progress
        cards = fallback_cards
        if document_stats:
            cards = {**fallback_cards, **document_stats.get("cards", {})}
        cards = contract_dashboard_cards(
            identity,
            cards,
            progress,
            total_warga_for(identity),
        )

        data = {
            "peran": role_display(identity["peran"]),
            "isi_cards": cards,
            "progress": progress,
            "pengajuan_7_hari_terakhir": document_stats.get("pengajuan_7_hari_terakhir", fallback_chart)
            if document_stats
            else fallback_chart,
        }
        return Response(DashboardSerializer(data).data)


class NotifikasiListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = Notifikasi.objects.filter(penerima_user_id=claim(request, "user_id")).order_by("-created_at")
        return Response(NotifikasiSerializer(queryset, many=True).data)


class NotifikasiTandaiDibacaView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        notif = get_object_or_404(Notifikasi, id=id, penerima_user_id=claim(request, "user_id"))
        if not notif.sudah_dibaca:
            notif.sudah_dibaca = True
            notif.dibaca_at = timezone.now()
            notif.save(update_fields=["sudah_dibaca", "dibaca_at"])
        return Response({"message": "Notifikasi ditandai sebagai dibaca"}, status=status.HTTP_200_OK)
