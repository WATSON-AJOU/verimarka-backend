from pathlib import Path

import boto3
from django.conf import settings


class S3StorageService:
    _client = None

    @classmethod
    def is_enabled(cls) -> bool:
        return bool(
            settings.AWS_S3_ENABLED
            and settings.AWS_STORAGE_BUCKET_NAME
            and settings.AWS_DEFAULT_REGION
        )

    @classmethod
    def upload_file(cls, *, local_path: str, key: str, content_type: str | None = None) -> str:
        client = cls._get_client()
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        client.upload_file(
            Filename=local_path,
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=key,
            ExtraArgs=extra_args or None,
        )
        return key

    @classmethod
    def generate_presigned_get_url(cls, *, key: str, expires_in: int | None = None) -> str:
        client = cls._get_client()
        return client.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                "Key": key,
            },
            ExpiresIn=expires_in or settings.AWS_QUERYSTRING_EXPIRE,
        )

    @classmethod
    def build_s3_uri(cls, *, key: str) -> str:
        return f"s3://{settings.AWS_STORAGE_BUCKET_NAME}/{key}"

    @classmethod
    def build_content_key(
        cls,
        *,
        owner_id: int,
        content_public_id: str,
        filename: str,
        stage: str,
    ) -> str:
        safe_name = Path(filename).name
        prefix = stage.strip("/ ")
        return f"{prefix}/{owner_id}/{content_public_id}/{safe_name}"

    @classmethod
    def _get_client(cls):
        if cls._client is not None:
            return cls._client

        session = boto3.session.Session(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
            region_name=settings.AWS_DEFAULT_REGION or None,
        )

        cls._client = session.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL or None,
            use_ssl=settings.AWS_S3_USE_SSL,
            config=boto3.session.Config(
                s3={"addressing_style": settings.AWS_S3_ADDRESSING_STYLE}
            ),
        )
        return cls._client
