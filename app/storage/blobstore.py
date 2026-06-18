from typing import BinaryIO, Protocol

import boto3
from botocore.client import Config

from app.config import Settings


class BlobStore(Protocol):
    def put(
        self, key: str, data: BinaryIO, content_length: int, content_type: str
    ) -> None: ...
    def presign_get(self, key: str) -> str: ...


class S3BlobStore:
    def __init__(self, settings: Settings):
        self._bucket = settings.s3_bucket
        self._ttl = settings.presign_ttl_seconds
        common = dict(
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(signature_version="s3v4"),
        )
        self._internal = boto3.client(
            "s3",
            endpoint_url=settings.s3_internal_endpoint,
            **common,
        )
        self._public = boto3.client(
            "s3",
            endpoint_url=settings.s3_public_endpoint,
            **common,
        )

    def put(
        self, key: str, data: BinaryIO, content_length: int, content_type: str
    ) -> None:
        self._internal.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentLength=content_length,
            ContentType=content_type,
        )

    def presign_get(self, key: str) -> str:
        return self._public.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=self._ttl,
        )
