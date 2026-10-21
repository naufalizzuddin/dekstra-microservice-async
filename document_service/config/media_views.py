from pathlib import Path

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404


@staff_member_required
def admin_media(request, file_path):
    media_root = Path(settings.MEDIA_ROOT).resolve()
    requested_file = (media_root / file_path).resolve()
    if requested_file != media_root and media_root not in requested_file.parents:
        raise Http404
    if not requested_file.is_file():
        raise Http404
    return FileResponse(requested_file.open("rb"), filename=requested_file.name)
