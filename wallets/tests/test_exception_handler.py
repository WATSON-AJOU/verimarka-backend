import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

User = get_user_model()


class WalletExceptionHandlerTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="wallet-user",
            nickname="wallet-user",
            display_name="Wallet User",
            email="wallet@example.com",
            password="password1234",
            phone="01099998888",
            phone_verified=True,
        )
        self.client.force_authenticate(user=self.user)

    def test_wallet_challenge_validation_error_keeps_field_errors_and_standard_fields(
        self,
    ):
        response = self.client.post(
            reverse("wallet_connect_challenge"),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error_code"], "INVALID_INPUT")
        self.assertIn("address", response.json())
        self.assertIn("errors", response.json())

    def test_unauthenticated_error_uses_stable_code_and_message(self):
        client = APIClient()

        response = client.get(reverse("wallet_summary"))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error_code"], "AUTHENTICATION_REQUIRED")
        self.assertEqual(response.json()["error_message"], "로그인이 필요합니다.")
        self.assertIn("errors", response.json())

    def test_not_found_error_uses_stable_code_and_message(self):
        response = self.client.get(
            reverse("content_review_vote_status", args=[uuid.uuid4()])
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error_code"], "NOT_FOUND")
        self.assertEqual(
            response.json()["error_message"], "요청한 대상을 찾을 수 없습니다."
        )
        self.assertIn("errors", response.json())
