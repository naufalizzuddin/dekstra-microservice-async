from django.urls import path

from .views import (
    RiwayatPersetujuanDetailView,
    RiwayatPersetujuanListView,
    RiwayatPersetujuanView,
)

urlpatterns = [
    path("riwayat-persetujuan/", RiwayatPersetujuanView.as_view()),
    path("riwayat-persetujuan/list/", RiwayatPersetujuanListView.as_view()),
    path("riwayat-persetujuan/<int:id>/", RiwayatPersetujuanDetailView.as_view()),
]
