from pathlib import Path

from rest_framework import serializers

from contents.models import Content
from contents.input_safety import validate_uploaded_content_file
from contents.storage import S3StorageService


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
            "document_metadata",
            "blockchain",
            "timing_ms",
            "created_at",
            "updated_at",
            "analyzed_at",
        )
        read_only_fields = fields

    def _local_file_exists(self, file_field) -> bool:
        if not file_field:
            return False
        try:
            return Path(file_field.path).exists()
        except (NotImplementedError, ValueError, OSError):
            return False

    def get_file_url(self, obj):
        if obj.original_storage_key and S3StorageService.is_enabled():
            return S3StorageService.generate_presigned_get_url(key=obj.original_storage_key)

        request = self.context.get("request")
        if not self._local_file_exists(obj.original_file):
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

        output_path = watermark.get("output_path")
        if output_path:
            try:
                if not Path(output_path).exists():
                    return None
            except (TypeError, OSError):
                return None

        request = self.context.get("request")
        return request.build_absolute_uri(output_url) if request else output_url


class ContentRegisterSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, value):
        return validate_uploaded_content_file(value)


class ContentVerifySerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, value):
        return validate_uploaded_content_file(value)


class ReviewVoteSignatureSerializer(serializers.Serializer):
    is_original = serializers.BooleanField()
    deadline = serializers.IntegerField(min_value=1)
    signature = serializers.CharField()

    def validate_signature(self, value: str) -> str:
        signature = (value or "").strip()
        if not signature:
            raise serializers.ValidationError("지갑 서명이 필요합니다.")
        if not signature.startswith("0x"):
            raise serializers.ValidationError("서명 형식이 올바르지 않습니다.")
        return signature


class ReviewVoteStartSerializer(serializers.Serializer):
    notify_by_email = serializers.BooleanField(required=False, default=False)
