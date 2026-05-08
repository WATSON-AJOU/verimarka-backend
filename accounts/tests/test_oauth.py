from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import SocialAccount

User = get_user_model()


class AuthCookieTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="cookie@example.com",
            email="cookie@example.com",
            password="Password123",
            nickname="cookienick",
            display_name="Cookie User",
        )

    def test_login_sets_http_only_refresh_cookie_without_body_refresh(self):
        response = self.client.post(
            reverse("login"),
            {"email": "cookie@example.com", "password": "Password123"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertNotIn("refresh", response.data)
        self.assertIn("verimarka_refresh_token", response.cookies)
        self.assertTrue(response.cookies["verimarka_refresh_token"]["httponly"])

    def test_token_refresh_reads_refresh_cookie(self):
        login_response = self.client.post(
            reverse("login"),
            {"email": "cookie@example.com", "password": "Password123"},
            format="json",
        )
        self.client.cookies["verimarka_refresh_token"] = login_response.cookies[
            "verimarka_refresh_token"
        ].value

        response = self.client.post(reverse("token_refresh"), {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertNotIn("refresh", response.data)


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": (
            "rest_framework_simplejwt.authentication.JWTAuthentication",
        ),
        "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
        "DEFAULT_THROTTLE_RATES": {"auth": "2/min", "oauth": "2/min"},
        "EXCEPTION_HANDLER": "config.exceptions.verimarka_exception_handler",
    }
)
class AuthThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        User.objects.create_user(
            username="throttle@example.com",
            email="throttle@example.com",
            password="Password123",
            nickname="throttlenick",
            display_name="Throttle User",
        )

    def tearDown(self):
        cache.clear()

    def test_login_is_rate_limited(self):
        payload = {"email": "throttle@example.com", "password": "wrong-password"}

        responses = [
            self.client.post(reverse("login"), payload, format="json")
            for _ in range(11)
        ]

        self.assertTrue(all(response.status_code == 400 for response in responses[:10]))
        self.assertEqual(responses[-1].status_code, 429)


class OAuthAccountLinkingTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("accounts.api.views_oauth.fetch_userinfo")
    @patch("accounts.api.views_oauth.exchange_code_for_token")
    def test_google_oauth_links_existing_user_by_email(
        self, mock_exchange, mock_userinfo
    ):
        user = User.objects.create_user(
            username="existing-user",
            email="existing@example.com",
            password="Password123",
            nickname="existingnick",
            display_name="Existing User",
        )
        user.is_staff = True
        user.save(update_fields=["is_staff"])

        mock_exchange.return_value = {"access_token": "google-access-token"}
        mock_userinfo.return_value = {
            "sub": "google-sub-123",
            "email": "existing@example.com",
            "email_verified": True,
        }

        response = self.client.post(
            reverse("oauth_google"),
            {
                "code": "google-auth-code",
                "redirect_uri": "https://verimarka.com/auth/google/callback",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(response.data["created"])
        self.assertEqual(response.data["user"]["id"], user.id)
        self.assertTrue(
            SocialAccount.objects.filter(
                user=user,
                provider="google",
                provider_sub="google-sub-123",
            ).exists()
        )

    @patch("accounts.api.views_oauth.kakao_fetch_userinfo")
    @patch("accounts.api.views_oauth.kakao_exchange_code_for_token")
    def test_kakao_oauth_links_existing_user_by_email(
        self, mock_exchange, mock_userinfo
    ):
        user = User.objects.create_user(
            username="existing-kakao-user",
            email="kakao@example.com",
            password="Password123",
            nickname="kakaonick",
            display_name="Kakao User",
        )

        mock_exchange.return_value = {"access_token": "kakao-access-token"}
        mock_userinfo.return_value = {
            "id": 999999,
            "kakao_account": {
                "email": "kakao@example.com",
                "is_email_verified": True,
            },
        }

        response = self.client.post(
            reverse("oauth_kakao"),
            {
                "code": "kakao-auth-code",
                "redirect_uri": "https://verimarka.com/auth/kakao/callback",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["created"])
        self.assertEqual(response.data["user"]["id"], user.id)
        self.assertTrue(
            SocialAccount.objects.filter(
                user=user,
                provider="kakao",
                provider_sub="999999",
            ).exists()
        )

    @patch("accounts.api.views_oauth.apple_verify_identity_token")
    @patch("accounts.api.views_oauth.apple_exchange_code_for_token")
    def test_apple_oauth_links_existing_user_by_email(self, mock_exchange, mock_verify):
        user = User.objects.create_user(
            username="existing-apple-user",
            email="apple@example.com",
            password="Password123",
            nickname="applenick",
            display_name="Apple User",
        )

        mock_exchange.return_value = {"id_token": "apple-id-token"}
        mock_verify.return_value = {
            "sub": "apple-sub-123",
            "email": "apple@example.com",
            "email_verified": "true",
        }

        response = self.client.post(
            reverse("oauth_apple"),
            {
                "code": "apple-auth-code",
                "redirect_uri": "https://verimarka.com/auth/apple/callback",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["created"])
        self.assertEqual(response.data["user"]["id"], user.id)
        self.assertTrue(
            SocialAccount.objects.filter(
                user=user,
                provider="apple",
                provider_sub="apple-sub-123",
            ).exists()
        )

    @patch("accounts.api.views_oauth.fetch_userinfo")
    @patch("accounts.api.views_oauth.exchange_code_for_token")
    def test_google_oauth_rejects_unverified_email_linking(
        self, mock_exchange, mock_userinfo
    ):
        user = User.objects.create_user(
            username="unverified-link-user",
            email="unverified@example.com",
            password="Password123",
            nickname="unverifiednick",
            display_name="Unverified User",
        )

        mock_exchange.return_value = {"access_token": "google-access-token"}
        mock_userinfo.return_value = {
            "sub": "google-unverified-sub",
            "email": "unverified@example.com",
            "email_verified": False,
        }

        response = self.client.post(
            reverse("oauth_google"),
            {
                "code": "google-auth-code",
                "redirect_uri": "https://verimarka.com/auth/google/callback",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            SocialAccount.objects.filter(
                user=user,
                provider="google",
                provider_sub="google-unverified-sub",
            ).exists()
        )

    @patch("accounts.api.views_oauth.fetch_userinfo")
    @patch("accounts.api.views_oauth.exchange_code_for_token")
    def test_admin_google_oauth_does_not_create_non_admin_user(
        self, mock_exchange, mock_userinfo
    ):
        mock_exchange.return_value = {"access_token": "google-access-token"}
        mock_userinfo.return_value = {
            "sub": "new-google-admin-sub",
            "email": "new-admin-attempt@example.com",
            "email_verified": True,
        }

        response = self.client.post(
            reverse("admin_oauth_google"),
            {
                "code": "google-auth-code",
                "redirect_uri": "https://admin.verimarka.com/auth/google/callback",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            User.objects.filter(email="new-admin-attempt@example.com").exists()
        )
        self.assertFalse(
            SocialAccount.objects.filter(
                provider="google", provider_sub="new-google-admin-sub"
            ).exists()
        )

    @patch("accounts.api.views_oauth.fetch_userinfo")
    @patch("accounts.api.views_oauth.exchange_code_for_token")
    def test_admin_google_oauth_links_existing_admin_by_verified_email(
        self, mock_exchange, mock_userinfo
    ):
        user = User.objects.create_user(
            username="existing-admin-oauth",
            email="admin-oauth@example.com",
            password="Password123",
            nickname="adminoauth",
            display_name="Admin OAuth",
            is_staff=True,
        )

        mock_exchange.return_value = {"access_token": "google-access-token"}
        mock_userinfo.return_value = {
            "sub": "admin-google-sub",
            "email": "admin-oauth@example.com",
            "email_verified": True,
        }

        response = self.client.post(
            reverse("admin_oauth_google"),
            {
                "code": "google-auth-code",
                "redirect_uri": "https://admin.verimarka.com/auth/google/callback",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["created"])
        self.assertEqual(response.data["user"]["id"], user.id)
        self.assertTrue(
            SocialAccount.objects.filter(
                user=user, provider="google", provider_sub="admin-google-sub"
            ).exists()
        )


class LogoutTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_logout_blacklists_refresh_token(self):
        user = User.objects.create_user(
            username="logout-user",
            email="logout@example.com",
            password="Password123",
            nickname="logoutnick",
            display_name="Logout User",
        )
        refresh = RefreshToken.for_user(user)

        response = self.client.post(
            reverse("logout"),
            {"refresh": str(refresh)},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["refresh_blacklisted"])
        self.assertEqual(BlacklistedToken.objects.count(), 1)
