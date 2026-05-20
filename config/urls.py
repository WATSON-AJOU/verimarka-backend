from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView

from accounts.api.views_auth import CookieTokenRefreshView
from config.health import health_check

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health_check, name="health_check"),
    # JWT
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path(
        "api/auth/token/refresh/",
        CookieTokenRefreshView.as_view(),
        name="token_refresh",
    ),
    # account
    path("api/accounts/", include("accounts.urls")),
    path("api/logs/", include("logs.urls")),
    path("api/operations/", include("operations.urls")),
    path("api/wallets/", include("wallets.urls")),
    path("api/analysis/", include("analysis.urls")),
    path("api/contents/", include("contents.urls")),
]
