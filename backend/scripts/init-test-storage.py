"""Create test-only object storage buckets in the isolated MinIO service."""

from __future__ import annotations

import os
import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def main() -> None:
    client = boto3.client(
        "s3",
        endpoint_url="http://127.0.0.1:9000",
        aws_access_key_id=os.environ["AKS_MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["AKS_MINIO_SECRET_KEY"],
        region_name="us-east-1",
    )
    buckets = {
        os.environ["AKS_MINIO_BUCKET"],
        "averqel",
        "averqel-library",
        "documents",
        "library",
        "private",
        "private-bucket",
        "tenant-bucket",
        "test-bucket",
    }
    for attempt in range(30):
        try:
            existing = {bucket["Name"] for bucket in client.list_buckets()["Buckets"]}
            for bucket in sorted(buckets - existing):
                client.create_bucket(Bucket=bucket)
            return
        except (BotoCoreError, ClientError):
            if attempt == 29:
                raise
            time.sleep(1)


if __name__ == "__main__":
    main()
