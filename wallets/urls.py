from django.urls import path

from .api.views import WalletConnectChallengeView, WalletConnectVerifyView, WalletLinkView, WalletSummaryView


urlpatterns = [
    path("me/", WalletLinkView.as_view(), name="wallet_me"),
    path("summary/", WalletSummaryView.as_view(), name="wallet_summary"),
    path("connect/challenge/", WalletConnectChallengeView.as_view(), name="wallet_connect_challenge"),
    path("connect/verify/", WalletConnectVerifyView.as_view(), name="wallet_connect_verify"),
]
