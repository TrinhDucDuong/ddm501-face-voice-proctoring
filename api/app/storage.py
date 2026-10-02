import hashlib
from datetime import datetime, timezone

import boto3

from .config import Settings


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class ObjectStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.enabled = settings.store_raw_biometrics
        self.client = None

    def _client(self):
        if self.client is None:
            self.client = boto3.client(
                "s3", endpoint_url=self.settings.minio_endpoint,
                aws_access_key_id=self.settings.aws_access_key_id,
                aws_secret_access_key=self.settings.aws_secret_access_key,
            )
        return self.client

    def put_evidence(self, tenant_id, event_id, modality, payload, content_type):
        key = f"evidence/{tenant_id}/{event_id}/{modality}"
        self._client().put_object(Bucket=self.settings.biometric_bucket, Key=key,
                                 Body=payload, ContentType=content_type)
        return key

    def get(self, key):
        item = self._client().get_object(Bucket=self.settings.biometric_bucket, Key=key)
        body = item["Body"]
        try:
            return body.read(), item.get("ContentType", "application/octet-stream")
        finally:
            body.close()

    def put(self, person_id: str, modality: str, payload: bytes, extension: str) -> str | None:
        if not self.enabled:
            return None
        if self.client is None:
            self.client = boto3.client(
                "s3",
                endpoint_url=self.settings.minio_endpoint,
                aws_access_key_id=self.settings.aws_access_key_id,
                aws_secret_access_key=self.settings.aws_secret_access_key,
            )
            buckets = {item["Name"] for item in self.client.list_buckets().get("Buckets", [])}
            if self.settings.biometric_bucket not in buckets:
                self.client.create_bucket(Bucket=self.settings.biometric_bucket)
        stamp = datetime.now(timezone.utc).strftime("%Y/%m/%d/%H%M%S%f")
        key = f"{person_id}/{modality}/{stamp}.{extension}"
        self.client.put_object(Bucket=self.settings.biometric_bucket, Key=key, Body=payload)
        return key
