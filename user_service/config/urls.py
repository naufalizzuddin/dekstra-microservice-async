from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path
from rest_framework_simplejwt.views import TokenRefreshView

from .media_views import admin_media

urlpatterns = [
    path("auth-admin/", admin.site.urls),
    path("registrasi-admin/", admin.site.urls),
    path("user-admin/", admin.site.urls),
    path("registrasi-media/<path:file_path>", admin_media),
    path("", include("accounts.urls")),
    path("", include("registrasi.urls")),
    path("auth/refresh/", TokenRefreshView.as_view()),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
