from django.contrib import admin

from .models import WalletConnectionChallenge, WalletLink


@admin.register(WalletLink)
class WalletLinkAdmin(admin.ModelAdmin):
    list_display = ("user", "address", "chain_id", "wallet_type", "verified_at")
    search_fields = ("user__email", "user__username", "address")


@admin.register(WalletConnectionChallenge)
class WalletConnectionChallengeAdmin(admin.ModelAdmin):
    list_display = ("user", "address", "expires_at", "used_at", "created_at")
    search_fields = ("user__email", "user__username", "address", "nonce")
