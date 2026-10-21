from django.urls import path

from .views import (
    PendaftaranAkunBerkasView,
    PendaftaranAkunDetailView,
    PendaftaranAkunListView,
    RegisterView,
    VerifikasiPendaftaranAkunView,
    WilayahRTListView,
    WilayahRWListView,
)

urlpatterns = [
    path("auth/register/", RegisterView.as_view()),
    path("wilayah/rw/", WilayahRWListView.as_view()),
    path("wilayah/rt/", WilayahRTListView.as_view()),
    path("pendaftaran-akun/list/", PendaftaranAkunListView.as_view()),
    path("pendaftaran-akun/<int:id>/", PendaftaranAkunDetailView.as_view()),
    path(
        "media/pendaftaran/<int:id>/<str:kind>/",
        PendaftaranAkunBerkasView.as_view(),
        name="pendaftaran-berkas",
    ),
    path("verifikasi/pendaftaran-akun/<int:id>/", VerifikasiPendaftaranAkunView.as_view()),
]
