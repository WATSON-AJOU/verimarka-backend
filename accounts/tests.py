from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import SocialAccount


User = get_user_model()


class OAuthAccountLinkingTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("accounts.views.views_oauth.fetch_userinfo")
    @patch("accounts.views.views_oauth.exchange_code_for_token")
    def test_google_oauth_links_existing_user_by_email(self, mock_exchange, mock_userinfo):
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
        }

        response = self.client.post(
            "/api/accounts/auth/oauth/google/",
            {
                "code": "google-auth-code",
                "redirect_uri": "https://verimarka.com/auth/google/callback",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.email, "existing@example.com")
        self.assertFalse(response.data["created"])
        self.assertEqual(response.data["user"]["id"], user.id)
        self.assertTrue(
            SocialAccount.objects.filter(
                user=user,
                provider="google",
                provider_sub="google-sub-123",
            ).exists()
        )

    @patch("accounts.views.views_oauth.kakao_fetch_userinfo")
    @patch("accounts.views.views_oauth.kakao_exchange_code_for_token")
    def test_kakao_oauth_links_existing_user_by_email(self, mock_exchange, mock_userinfo):
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
            },
        }

        response = self.client.post(
            "/api/accounts/auth/oauth/kakao/",
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

    @patch("accounts.views.views_oauth.apple_verify_identity_token")
    @patch("accounts.views.views_oauth.apple_exchange_code_for_token")
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
        }

        response = self.client.post(
            "/api/accounts/auth/oauth/apple/",
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
