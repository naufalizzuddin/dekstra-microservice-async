from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

urlpatterns = [
    path("dashboard-admin/", admin.site.urls),
    path("", include("dashboard.urls")),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
