from rest_framework import serializers

from .models import WalletLink


class WalletLinkSerializer(serializers.ModelSerializer):
    connected = serializers.SerializerMethodField()

    class Meta:
        model = WalletLink
        fields = (
            "connected",
            "address",
            "chain_id",
            "wallet_type",
            "verified_at",
        )

    def get_connected(self, obj):
        return obj is not None


class WalletChallengeRequestSerializer(serializers.Serializer):
    address = serializers.CharField(max_length=42)


class WalletVerifyRequestSerializer(serializers.Serializer):
    address = serializers.CharField(max_length=42)
    signature = serializers.CharField()
    chain_id = serializers.IntegerField(required=False, allow_null=True)
    wallet_type = serializers.CharField(required=False, allow_blank=True, max_length=50)


class WalletSummarySerializer(serializers.Serializer):
    connected = serializers.BooleanField()
    address = serializers.CharField(allow_null=True, allow_blank=True)
    chain_id = serializers.IntegerField(allow_null=True)
    wallet_type = serializers.CharField(allow_blank=True)
    network_name = serializers.CharField()
    nft_count = serializers.IntegerField(min_value=0, allow_null=True)
    vote_minimum = serializers.IntegerField(min_value=0)
    vote_eligible = serializers.BooleanField()
    lookup_status = serializers.ChoiceField(choices=("not_connected", "ok", "failed"))
    lookup_error = serializers.CharField(allow_blank=True, allow_null=True, required=False)
