from django.urls import path

from .views import (
    BerkasSuratView,
    DownloadBerkasPengajuanView,
    DownloadBerkasView,
    InternalDashboardStatsView,
    JenisSuratListView,
    PengajuanSuratView,
    RiwayatPengajuanDetailView,
    RiwayatPengajuanWargaView,
)

urlpatterns = [
    path("jenis-surat/", JenisSuratListView.as_view()),
    path("pengajuan-surat/", PengajuanSuratView.as_view()),
    path("upload/berkas-surat/", BerkasSuratView.as_view()),
    path(
        "media/permohonan/<uuid:token>/",
        DownloadBerkasPengajuanView.as_view(),
        name="berkas-pengajuan-download",
    ),
    path("riwayat-pengajuan/", RiwayatPengajuanWargaView.as_view()),
    path("riwayat-pengajuan/<path:nomor_permohonan>/", RiwayatPengajuanDetailView.as_view()),
    path("berkas/<uuid:token>", DownloadBerkasView.as_view()),
    path("internal/dashboard-stats/", InternalDashboardStatsView.as_view()),
]
