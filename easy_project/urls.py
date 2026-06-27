from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from boards.frontend import frontend_app

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("api/v1/", include("boards.api_urls")),
    path("app/", frontend_app, name="frontend_app"),
    path("app/<path:asset_path>", frontend_app, name="frontend_asset"),
    path("", include("boards.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
