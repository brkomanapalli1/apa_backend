from __future__ import annotations

from io import BytesIO
from uuid import uuid4

import boto3
from botocore.client import Config

from app.core.config import settings


class StorageService:
    def __init__(self) -> None:
        protocol = 'https' if settings.MINIO_SECURE else 'http'

        # Internal client for backend container -> MinIO container
        self.client = boto3.client(
            's3',
            endpoint_url=f'{protocol}://{settings.MINIO_INTERNAL_ENDPOINT}',
            aws_access_key_id=settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=settings.MINIO_SECRET_KEY,
            config=Config(signature_version='s3v4'),
            region_name='us-east-1',
        )

        # Public client only for generating browser-usable presigned URLs
        self.public_client = boto3.client(
            's3',
            endpoint_url=f'{protocol}://{settings.MINIO_PUBLIC_ENDPOINT}',
            aws_access_key_id=settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=settings.MINIO_SECRET_KEY,
            config=Config(signature_version='s3v4'),
            region_name='us-east-1',
        )

    def ensure_bucket(self) -> None:
        buckets = [b['Name'] for b in self.client.list_buckets().get('Buckets', [])]
        if settings.MINIO_BUCKET not in buckets:
            self.client.create_bucket(Bucket=settings.MINIO_BUCKET)

    def build_key(self, filename: str) -> str:
        safe = filename.replace('/', '-').replace('..', '-')
        return f'uploads/{uuid4()}-{safe}'

    def get_presigned_upload(self, filename: str, content_type: str) -> tuple[str, str]:
        self.ensure_bucket()
        key = self.build_key(filename)
        url = self.public_client.generate_presigned_url(
            ClientMethod='put_object',
            Params={
                'Bucket': settings.MINIO_BUCKET,
                'Key': key,
                'ContentType': content_type,
            },
            ExpiresIn=settings.PRESIGNED_UPLOAD_EXPIRE_SECONDS,
        )
        return url, key

    def get_presigned_download(self, key: str) -> str:
        self.ensure_bucket()
        return self.public_client.generate_presigned_url(
            ClientMethod='get_object',
            Params={'Bucket': settings.MINIO_BUCKET, 'Key': key},
            ExpiresIn=settings.PRESIGNED_DOWNLOAD_EXPIRE_SECONDS,
        )

    def download_bytes(self, key: str) -> bytes:
        stream = BytesIO()
        self.client.download_fileobj(settings.MINIO_BUCKET, key, stream)
        return stream.getvalue()