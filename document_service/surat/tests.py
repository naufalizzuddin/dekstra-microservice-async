import uuid

from django.test import SimpleTestCase
from django.urls import resolve, reverse
from rest_framework import permissions

from .views import DownloadBerkasPengajuanView, DownloadBerkasView


class PublicApplicationFileRouteTests(SimpleTestCase):
    def test_route_uses_public_uuid_token(self):
        token = uuid.uuid4()
        path = reverse("berkas-pengajuan-download", kwargs={"token": token})

        self.assertEqual(path, f"/media/permohonan/{token}/")
        self.assertIs(resolve(path).func.view_class, DownloadBerkasPengajuanView)

    def test_route_does_not_require_authentication(self):
        self.assertEqual(DownloadBerkasPengajuanView.authentication_classes, [])
        self.assertEqual(
            DownloadBerkasPengajuanView.permission_classes,
            [permissions.AllowAny],
        )

    def test_final_document_does_not_require_authentication(self):
        self.assertEqual(DownloadBerkasView.authentication_classes, [])
        self.assertEqual(
            DownloadBerkasView.permission_classes,
            [permissions.AllowAny],
        )
