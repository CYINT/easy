import mimetypes

from django.conf import settings
from django.http import FileResponse, Http404
from django.views.decorators.http import require_GET

FRONTEND_ROOT = settings.BASE_DIR / "frontend"
ALLOWED_ASSETS = {
    "index.html",
    "src/api.js",
    "src/app.js",
    "src/styles.css",
}


@require_GET
def frontend_app(request, asset_path="index.html"):
    normalized = asset_path.strip("/") or "index.html"
    if normalized not in ALLOWED_ASSETS:
        raise Http404("Frontend asset not found.")
    target = (FRONTEND_ROOT / normalized).resolve()
    if FRONTEND_ROOT.resolve() not in target.parents and target != FRONTEND_ROOT.resolve():
        raise Http404("Frontend asset not found.")
    if not target.exists() or not target.is_file():
        raise Http404("Frontend asset not found.")
    content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(target.open("rb"), content_type=content_type)
