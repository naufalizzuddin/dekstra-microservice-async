from django.urls import path

from .views import DashboardView, InternalKepalaDesaView, NotifikasiListView, NotifikasiTandaiDibacaView, ProfileView

urlpatterns = [
    path("profil/", ProfileView.as_view()),
    path("dashboard/", DashboardView.as_view()),
    path("notifikasi/", NotifikasiListView.as_view()),
    path("notifikasi/<int:id>/read/", NotifikasiTandaiDibacaView.as_view()),
    path("internal/pejabat/kepala-desa/", InternalKepalaDesaView.as_view()),
]
