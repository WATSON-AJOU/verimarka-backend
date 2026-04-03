from django.urls import path

from .views import (
    ContentMintView,
    OngoingReviewVoteListView,
    ContentRegisterView,
    ContentReviewVoteEventSyncView,
    ContentReviewVoteCastView,
    ContentReviewVoteSigningContextView,
    ContentReviewVoteStartView,
    ContentReviewVoteStatusView,
    ContentVerifyView,
    ContentWatermarkDownloadView,
    ContentWatermarkView,
)


urlpatterns = [
    path("register/", ContentRegisterView.as_view(), name="content_register"),
    path("verify/", ContentVerifyView.as_view(), name="content_verify"),
    path("ongoing-votes/", OngoingReviewVoteListView.as_view(), name="content_ongoing_votes"),
    path("<uuid:public_id>/watermark/", ContentWatermarkView.as_view(), name="content_watermark"),
    path("<uuid:public_id>/watermark-download/", ContentWatermarkDownloadView.as_view(), name="content_watermark_download"),
    path("<uuid:public_id>/mint/", ContentMintView.as_view(), name="content_mint"),
    path("<uuid:public_id>/review-vote/start/", ContentReviewVoteStartView.as_view(), name="content_review_vote_start"),
    path("<uuid:public_id>/review-vote/", ContentReviewVoteStatusView.as_view(), name="content_review_vote_status"),
    path("<uuid:public_id>/review-vote/signing/", ContentReviewVoteSigningContextView.as_view(), name="content_review_vote_signing"),
    path("<uuid:public_id>/review-vote/vote/", ContentReviewVoteCastView.as_view(), name="content_review_vote_cast"),
    path("internal/review-vote/event-sync/", ContentReviewVoteEventSyncView.as_view(), name="content_review_vote_event_sync"),
]
