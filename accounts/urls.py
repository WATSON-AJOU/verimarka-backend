from django.urls import path
from .views import MeView
from .views_oauth import GoogleOAuthLoginView


urlpatterns = [
    # POST /api/auth/token/ 으로 access 발급
    # GET /api/accounts/me/
    # Header: Authorization: Bearer <access>
    path("me/", MeView.as_view(), name="me"),
    # /api/accounts/auth/oauth/google/
    path("auth/oauth/google/", GoogleOAuthLoginView.as_view(), name="oauth_google"),
]
