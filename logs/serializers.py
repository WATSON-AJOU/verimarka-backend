from rest_framework import serializers


class HistoryItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    type = serializers.ChoiceField(choices=["allow", "block", "review", "verify"])
    file_name = serializers.CharField()
    summary = serializers.CharField()
    timestamp = serializers.CharField()
    cosine = serializers.CharField()
    phash = serializers.CharField()
    extra = serializers.CharField()
    preview_url = serializers.CharField(allow_blank=True, allow_null=True)
