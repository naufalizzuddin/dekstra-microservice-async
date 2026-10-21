from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

from .media_views import admin_media

urlpatterns = [
    path("approval-admin/", admin.site.urls),
    path("", include("surat.urls")),
    path("media/<path:file_path>", admin_media),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
