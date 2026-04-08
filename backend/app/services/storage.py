from typing import Optional
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings


class TigrisStorage:
    def __init__(self):
        if not settings.AWS_ENDPOINT_URL_S3:
            raise ValueError("Tigris storage not configured. Set AWS_ENDPOINT_URL_S3.")

        self.s3_client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_ENDPOINT_URL_S3,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )
        self.bucket_name = settings.TIGRIS_BUCKET_NAME

    def generate_stream_url(
        self,
        camera_id: str,
        org_id: str,
        expires_in: Optional[int] = None,
    ) -> str:
        """Generate a signed URL for downloading a stream playlist."""
        key = f"{org_id}/cameras/{camera_id}/stream.m3u8"
        expires_in = expires_in or settings.STREAM_URL_EXPIRY_SECONDS

        url = self.s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket_name,
                "Key": key,
            },
            ExpiresIn=expires_in,
        )
        return url

    def generate_segment_url(
        self,
        camera_id: str,
        org_id: str,
        segment_name: str,
        expires_in: Optional[int] = None,
    ) -> str:
        """Generate a signed URL for downloading a specific HLS segment."""
        key = f"{org_id}/cameras/{camera_id}/{segment_name}"
        expires_in = expires_in or settings.SEGMENT_URL_EXPIRY_SECONDS

        url = self.s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket_name,
                "Key": key,
            },
            ExpiresIn=expires_in,
        )
        return url

    def generate_upload_url(
        self,
        camera_id: str,
        org_id: str,
        filename: str,
        expires_in: Optional[int] = None,
    ) -> tuple[str, str]:
        """
        Generate a signed URL for uploading a file (segment or playlist).
        Returns (upload_url, s3_key).

        Args:
            camera_id: Camera identifier
            org_id: Organization identifier
            filename: The actual filename (e.g., "segment_00000.ts" or "stream.m3u8")
            expires_in: URL expiry time in seconds
        """
        s3_key = f"{org_id}/cameras/{camera_id}/{filename}"
        expires_in = expires_in or settings.UPLOAD_URL_EXPIRY_SECONDS

        # Use correct content type based on file extension
        if filename.endswith(".m3u8"):
            content_type = "application/vnd.apple.mpegurl"
        else:
            content_type = "video/mp2t"

        url = self.s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket_name,
                "Key": s3_key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
        return url, s3_key

    def delete_object(self, s3_key: str) -> bool:
        """Delete an object from storage."""
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key,
            )
            return True
        except ClientError:
            return False

    def list_objects(self, prefix: str) -> list[str]:
        """List all objects with a given prefix."""
        objects = []
        try:
            paginator = self.s3_client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                for obj in page.get("Contents", []):
                    objects.append(obj["Key"])
        except ClientError:
            pass
        return objects

    def cleanup_old_segments(self, org_id: str, camera_id: str, keep_count: int = 60):
        """Delete old segments, keeping only the most recent ones.
        Uses batch delete (up to 1000 objects per call) for efficiency."""
        import logging
        logger = logging.getLogger(__name__)

        prefix = f"{org_id}/cameras/{camera_id}/"
        try:
            paginator = self.s3_client.get_paginator("list_objects_v2")
            segments = []

            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if key.endswith(".ts") and "segment_" in key:
                        segments.append(key)

            segments.sort()

            if len(segments) > keep_count:
                to_delete = segments[:-keep_count]

                # S3 batch delete supports up to 1000 objects per call
                for i in range(0, len(to_delete), 1000):
                    batch = to_delete[i : i + 1000]
                    self.s3_client.delete_objects(
                        Bucket=self.bucket_name,
                        Delete={
                            "Objects": [{"Key": key} for key in batch],
                            "Quiet": True,
                        },
                    )
                    logger.debug("Batch deleted %d old segments", len(batch))

        except ClientError as e:
            logger.warning("Error cleaning up segments: %s", e)

    def get_playlist(self, camera_id: str, org_id: str) -> bytes:
        """Get the HLS playlist for a camera."""
        key = f"{org_id}/cameras/{camera_id}/stream.m3u8"

        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=key,
            )
            return response["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                raise FileNotFoundError(f"Playlist not found: {key}")
            raise

    def save_playlist(self, camera_id: str, org_id: str, content: str):
        """Save the HLS playlist for a camera."""
        key = f"{org_id}/cameras/{camera_id}/stream.m3u8"

        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType="application/vnd.apple.mpegurl",
        )

    def get_segment(self, camera_id: str, org_id: str, filename: str) -> bytes:
        """Get a specific HLS segment."""
        key = f"{org_id}/cameras/{camera_id}/{filename}"

        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=key,
            )
            return response["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                raise FileNotFoundError(f"Segment not found: {key}")
            raise

    def delete_camera_storage(self, org_id: str, camera_id: str) -> int:
        """
        Delete all storage objects for a camera.
        Returns count of deleted objects.
        """
        prefix = f"{org_id}/cameras/{camera_id}/"
        objects = self.list_objects(prefix)

        deleted_count = 0
        for obj_key in objects:
            if self.delete_object(obj_key):
                deleted_count += 1

        return deleted_count


storage: Optional[TigrisStorage] = None


def get_storage() -> TigrisStorage:
    global storage
    if storage is None:
        storage = TigrisStorage()
    return storage
