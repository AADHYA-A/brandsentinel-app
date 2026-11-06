"""Object storage for uploaded images: local filesystem (encrypted at rest) or S3-compatible bucket."""
from __future__ import annotations
import uuid
from .config import settings
from .db import FERNET


def save(data: bytes, ext: str, tenant: str) -> str:
    name = f"{tenant}/{uuid.uuid4().hex}{ext}.enc"
    blob = FERNET.encrypt(data)
    if settings.s3_bucket:
        import boto3
        c = boto3.client("s3", endpoint_url=settings.s3_endpoint or None)
        c.put_object(Bucket=settings.s3_bucket, Key=name, Body=blob, ServerSideEncryption="AES256")
        return "s3://" + name
    p = settings.data_path / "uploads" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(blob)
    return str(p)


def read(path: str) -> bytes:
    if path.startswith("s3://"):
        import boto3
        c = boto3.client("s3", endpoint_url=settings.s3_endpoint or None)
        blob = c.get_object(Bucket=settings.s3_bucket, Key=path[5:])["Body"].read()
    else:
        blob = open(path, "rb").read()
    return FERNET.decrypt(blob)
