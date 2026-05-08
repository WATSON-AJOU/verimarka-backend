from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.api.views_email import hash_code as hash_email_code
from accounts.api.views_sms import hash_code as hash_sms_code
from accounts.models import SmsVerification
from accounts.services.email_verification_store import get_code_hash
from accounts.services.fake_redis import FakeRedis

User = get_user_model()


class ProfileMeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="profile-user",
            email="old@example.com",
            password="Password123!",
            nickname="oldnick",
            display_name="Old Name",
            email_verified=True,
            email_verified_at=timezone.now(),
        )
        self.client.force_authenticate(self.user)

    def test_patch_me_normalizes_fields_and_resets_email_verification(self):
        response = self.client.patch(
            reverse("me"),
            {
                "nickname": "  New   Nick  ",
                "display_name": "  New   Name  ",
                "email": "  New@Example.COM  ",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.nickname, "New Nick")
        self.assertEqual(self.user.display_name, "New Name")
        self.assertEqual(self.user.email, "new@example.com")
        self.assertFalse(self.user.email_verified)
        self.assertIsNone(self.user.email_verified_at)
        self.assertEqual(response.data["email"], "new@example.com")

    def test_display_name_availability_excludes_current_user(self):
        User.objects.create_user(
            username="other-user",
            email="other@example.com",
            password="Password123!",
            nickname="othernick",
            display_name="Taken Name",
        )

        own_response = self.client.get(
            reverse("display_name_availability"),
            data={"display_name": "Old Name"},
        )
        taken_response = self.client.get(
            reverse("display_name_availability"),
            data={"display_name": "Taken Name"},
        )

        self.assertEqual(own_response.status_code, 200)
        self.assertTrue(own_response.data["available"])
        self.assertEqual(taken_response.status_code, 200)
        self.assertFalse(taken_response.data["available"])


class PhoneVerificationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="phone-user",
            email="phone@example.com",
            password="Password123!",
            nickname="phonenick",
            display_name="Phone User",
        )
        self.client.force_authenticate(self.user)

    @patch("accounts.api.views_sms.send_verification_sms")
    @patch("accounts.api.views_sms.generate_verification_code", return_value="123456")
    def test_send_code_normalizes_phone_and_stores_hashed_code(
        self, mock_generate_code, mock_send_sms
    ):
        response = self.client.post(
            reverse("phone_send_code"),
            {"phone": "010-1234-5678"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        verification = SmsVerification.objects.get(user=self.user)
        self.assertEqual(verification.phone, "01012345678")
        self.assertEqual(verification.code_hash, hash_sms_code("123456"))
        self.assertEqual(response.data["daily_remaining"], 2)
        mock_generate_code.assert_called_once_with()
        mock_send_sms.assert_called_once_with("01012345678", "123456")

    def test_verify_code_rejects_wrong_code_and_increments_fail_count(self):
        verification = SmsVerification.objects.create(
            user=self.user,
            phone="01012345678",
            code_hash=hash_sms_code("123456"),
            expires_at=timezone.now() + timedelta(minutes=3),
        )

        response = self.client.post(
            reverse("phone_verify_code"),
            {"phone": "010-1234-5678", "code": "000000"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        verification.refresh_from_db()
        self.assertEqual(verification.fail_count, 1)
        self.user.refresh_from_db()
        self.assertFalse(self.user.phone_verified)

    def test_verify_code_updates_user_and_marks_request_verified(self):
        verification = SmsVerification.objects.create(
            user=self.user,
            phone="01012345678",
            code_hash=hash_sms_code("123456"),
            expires_at=timezone.now() + timedelta(minutes=3),
        )

        response = self.client.post(
            reverse("phone_verify_code"),
            {"phone": "010-1234-5678", "code": "123456"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        verification.refresh_from_db()
        self.assertEqual(self.user.phone, "01012345678")
        self.assertTrue(self.user.phone_verified)
        self.assertIsNotNone(self.user.phone_verified_at)
        self.assertIsNotNone(verification.verified_at)


class EmailVerificationTests(TestCase):
    def setUp(self):
        FakeRedis.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="email-user",
            email="email@example.com",
            password="Password123!",
            nickname="emailnick",
            display_name="Email User",
        )
        self.client.force_authenticate(self.user)

    def tearDown(self):
        FakeRedis.clear()

    @patch("accounts.api.views_email.send_verification_email")
    @patch("accounts.api.views_email.generate_verification_code", return_value="654321")
    def test_send_code_normalizes_email_and_stores_hashed_code(
        self, mock_generate_code, mock_send_email
    ):
        response = self.client.post(
            reverse("email_send_code"),
            {"email": "  New@Example.COM  "},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            get_code_hash(self.user.id, "new@example.com"),
            hash_email_code("654321"),
        )
        self.assertEqual(response.data["daily_remaining"], 2)
        mock_generate_code.assert_called_once_with()
        mock_send_email.assert_called_once_with("new@example.com", "654321")

    def test_verify_code_updates_user_and_deletes_saved_code(self):
        from accounts.services.email_verification_store import store_code

        store_code(self.user.id, "new@example.com", "654321")

        response = self.client.post(
            reverse("email_verify_code"),
            {"email": "  New@Example.COM  ", "code": "654321"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")
        self.assertTrue(self.user.email_verified)
        self.assertIsNotNone(self.user.email_verified_at)
        self.assertIsNone(get_code_hash(self.user.id, "new@example.com"))

    def test_verify_code_rejects_email_used_by_other_verified_user(self):
        User.objects.create_user(
            username="verified-other",
            email="taken@example.com",
            password="Password123!",
            nickname="verifiedother",
            display_name="Verified Other",
            email_verified=True,
        )
        from accounts.services.email_verification_store import store_code

        store_code(self.user.id, "taken@example.com", "654321")

        response = self.client.post(
            reverse("email_verify_code"),
            {"email": "taken@example.com", "code": "654321"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "email@example.com")
        self.assertFalse(self.user.email_verified)
