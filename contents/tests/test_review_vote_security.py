from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from contents.models import Content
from wallets.models import WalletLink

User = get_user_model()


class ReviewVoteSecurityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username="owner",
            nickname="owner",
            display_name="Owner",
            email="owner@example.com",
            password="password1234",
            phone="01011112222",
            phone_verified=True,
        )
        WalletLink.objects.create(
            user=self.owner,
            address="0x1111111111111111111111111111111111111111",
            verified_at=timezone.now(),
        )
        self.content = Content.objects.create(
            owner=self.owner,
            content_type="image",
            status="review",
            original_filename="review.png",
            mime_type="image/png",
            file_size=128,
            decision="review",
            blockchain={
                "mint_kind": "review_vote",
                "token_id": 7,
                "vote": {"status": "Pending", "vote_id": "VOTE-7"},
            },
        )
        self.client.force_authenticate(user=self.owner)

    @patch(
        "contents.api.views.content.ContentBlockchainService.get_review_vote_signing_context"
    )
    def test_owner_cannot_request_review_vote_signing_context(self, mocked_context):
        response = self.client.get(
            reverse(
                "content_review_vote_signing",
                kwargs={"public_id": self.content.public_id},
            )
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("자신의 저작물", str(response.json()))
        mocked_context.assert_not_called()

    @patch(
        "contents.api.views.content.ContentBlockchainService.submit_review_vote_signature"
    )
    def test_owner_cannot_cast_review_vote(self, mocked_submit):
        response = self.client.post(
            reverse(
                "content_review_vote_cast",
                kwargs={"public_id": self.content.public_id},
            ),
            {
                "is_original": True,
                "deadline": int(timezone.now().timestamp()) + 60,
                "signature": "0x" + "11" * 65,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("자신의 저작물", str(response.json()))
        mocked_submit.assert_not_called()

    def test_ongoing_vote_list_excludes_pending_vote_after_72_hours_without_end_time(
        self,
    ):
        other_user = User.objects.create_user(
            username="voter",
            nickname="voter",
            display_name="Voter",
            email="voter@example.com",
            password="password1234",
            phone="01033334444",
            phone_verified=True,
        )
        self.client.force_authenticate(user=other_user)
        old_started_at = timezone.now() - timedelta(days=4)
        Content.objects.filter(pk=self.content.pk).update(
            created_at=old_started_at,
            updated_at=old_started_at,
        )

        response = self.client.get(reverse("content_ongoing_votes"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_ongoing_vote_list_keeps_recent_pending_vote_without_end_time(self):
        other_user = User.objects.create_user(
            username="recent-voter",
            nickname="recent-voter",
            display_name="Recent Voter",
            email="recent-voter@example.com",
            password="password1234",
            phone="01055557777",
            phone_verified=True,
        )
        self.client.force_authenticate(user=other_user)

        response = self.client.get(reverse("content_ongoing_votes"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["id"], str(self.content.public_id))
