from django.test import SimpleTestCase
from django.urls import resolve

from .views import (
    RiwayatPersetujuanDetailView,
    RiwayatPersetujuanListView,
    RiwayatPersetujuanView,
)


class ApprovalRouteTests(SimpleTestCase):
    def test_approval_action_route(self):
        self.assertIs(resolve("/riwayat-persetujuan/").func.view_class, RiwayatPersetujuanView)

    def test_approval_list_route(self):
        self.assertIs(resolve("/riwayat-persetujuan/list/").func.view_class, RiwayatPersetujuanListView)

    def test_approval_detail_route(self):
        self.assertIs(resolve("/riwayat-persetujuan/1/").func.view_class, RiwayatPersetujuanDetailView)
