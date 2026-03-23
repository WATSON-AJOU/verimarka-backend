from django.urls import path

from .views import (
    ContentMintView,
    ContentRegisterView,
    ContentReviewVoteStartView,
    ContentReviewVoteStatusView,
    ContentVerifyView,
    ContentWatermarkView,
)


urlpatterns = [
    path("register/", ContentRegisterView.as_view(), name="content_register"),
    path("verify/", ContentVerifyView.as_view(), name="content_verify"),
    path("<uuid:public_id>/watermark/", ContentWatermarkView.as_view(), name="content_watermark"),
    path("<uuid:public_id>/mint/", ContentMintView.as_view(), name="content_mint"),
    path("<uuid:public_id>/review-vote/start/", ContentReviewVoteStartView.as_view(), name="content_review_vote_start"),
    path("<uuid:public_id>/review-vote/", ContentReviewVoteStatusView.as_view(), name="content_review_vote_status"),
]
