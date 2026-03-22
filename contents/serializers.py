from rest_framework import serializers

from .models import Content
from .storage import S3StorageService


class ContentSerializer(serializers.ModelSerializer):
    owner_id = serializers.IntegerField(source="owner.id", read_only=True)
    file_url = serializers.SerializerMethodField()
    watermark_file_url = serializers.SerializerMethodField()

    class Meta:
        model = Content
        fields = (
            "id",
            "public_id",
            "owner_id",
            "content_type",
            "status",
            "original_filename",
            "original_storage_key",
            "mime_type",
            "file_size",
            "file_url",
            "watermark_file_url",
            "decision",
            "reason",
            "next_action",
            "top_cosine",
            "top_phash_dist",
            "top_match",
            "candidates",
            "watermark",
            "blockchain",
            "timing_ms",
            "created_at",
            "updated_at",
            "analyzed_at",
        )
        read_only_fields = fields

    def get_file_url(self, obj):
        if obj.original_storage_key and S3StorageService.is_enabled():
            return S3StorageService.generate_presigned_get_url(key=obj.original_storage_key)

        request = self.context.get("request")
        if not obj.original_file:
            return None
        url = obj.original_file.url
        return request.build_absolute_uri(url) if request else url

    def get_watermark_file_url(self, obj):
        watermark = obj.watermark or {}
        output_key = watermark.get("output_key")
        output_url = watermark.get("output_url")

        if output_key and S3StorageService.is_enabled():
            return S3StorageService.generate_presigned_get_url(key=output_key)

        if not output_url:
            return None

        if output_url.startswith("http://") or output_url.startswith("https://"):
            return output_url

        request = self.context.get("request")
        return request.build_absolute_uri(output_url) if request else output_url


class ContentRegisterSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, value):
        mime_type = (getattr(value, "content_type", "") or "").lower()
        allowed_types = {"image/png", "image/jpeg"}
        if mime_type not in allowed_types:
            raise serializers.ValidationError("JPG 또는 PNG 파일만 업로드할 수 있습니다.")

        max_bytes = 20 * 1024 * 1024
        if value.size > max_bytes:
            raise serializers.ValidationError("파일 크기는 20MB 이하만 가능합니다.")

        return value


class ContentVerifySerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, value):
        mime_type = (getattr(value, "content_type", "") or "").lower()
        allowed_types = {"image/png", "image/jpeg"}
        if mime_type not in allowed_types:
            raise serializers.ValidationError("JPG 또는 PNG 파일만 업로드할 수 있습니다.")

        max_bytes = 20 * 1024 * 1024
        if value.size > max_bytes:
            raise serializers.ValidationError("파일 크기는 20MB 이하만 가능합니다.")

        return value
