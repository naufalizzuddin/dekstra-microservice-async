from django.test import SimpleTestCase
from django.urls import resolve, reverse

from .views import PendaftaranAkunBerkasView


class RegistrationFileRouteTests(SimpleTestCase):
    def test_route_matches_monolith_media_path(self):
        path = reverse("pendaftaran-berkas", kwargs={"id": 1, "kind": "kk"})

        self.assertEqual(path, "/media/pendaftaran/1/kk/")
        self.assertIs(resolve(path).func.view_class, PendaftaranAkunBerkasView)
