"""Optional private S3 persistence; agent execution always uses a local workspace."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import threading
import zipfile
from typing import Any

from app.settings import Settings

MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_FILES = 10000


class LocalSessionStorage:
    def save(self, directory: Path, include) -> None:
        pass

    def restore(self, directory: Path) -> bool:
        return False


class S3SessionStorage:
    def __init__(self, settings: Settings, *, client: Any = None):
        if not settings.session_s3_bucket or not settings.session_s3_expected_owner:
            raise ValueError("S3 mode requires SESSION_S3_BUCKET and SESSION_S3_EXPECTED_OWNER")
        prefix = settings.session_s3_prefix.strip("/")
        if not prefix or any(p in {".", ".."} for p in prefix.split("/")) or "\\" in prefix:
            raise ValueError("Invalid S3 prefix")
        self.bucket = settings.session_s3_bucket
        self.owner = settings.session_s3_expected_owner
        self.region = settings.session_s3_region
        self.prefix = prefix
        self._client = client
        self._lock = threading.RLock()

    @property
    def client(self):
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "s3",
                region_name=self.region,
                config=Config(
                    connect_timeout=5,
                    read_timeout=30,
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            )
        return self._client

    def key(self, directory: Path):
        name = directory.name
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise ValueError("Invalid session ID")
        return f"{self.prefix}/{name}/workspace.zip"

    def save(self, directory: Path, include) -> None:
        with self._lock, tempfile.TemporaryFile() as archive:
            if (directory / ".meta/rectification_transaction.json").exists():
                raise RuntimeError("Cannot archive an incomplete rectification transaction")
            files = []
            total = 0
            for path in sorted(directory.rglob("*")):
                relative = path.relative_to(directory).as_posix()
                if not include(relative):
                    continue
                if path.is_symlink():
                    raise ValueError("Session archives cannot contain symlinks")
                if not path.is_file():
                    continue
                stat = path.stat()
                total += stat.st_size
                files.append((path, relative, stat.st_size, stat.st_mtime_ns))
            if total > MAX_ARCHIVE_BYTES or len(files) > MAX_FILES:
                raise ValueError("Session archive exceeds size limit")
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                for path, relative, _, _ in files:
                    bundle.write(path, relative)
            if any(
                (path.stat().st_size, path.stat().st_mtime_ns) != (size, modified)
                for path, _, size, modified in files
            ):
                raise RuntimeError("Session changed while archiving; retry when idle")
            archive.seek(0)
            digest = hashlib.file_digest(archive, "sha256").hexdigest()
            archive.seek(0)
            # One object is published only after the entire snapshot is uploaded.
            self.client.upload_fileobj(
                archive,
                self.bucket,
                self.key(directory),
                ExtraArgs={
                    "ExpectedBucketOwner": self.owner,
                    "ServerSideEncryption": "AES256",
                    "ContentType": "application/zip",
                    "Metadata": {"sha256": digest},
                },
            )

    def restore(self, directory: Path) -> bool:
        with self._lock:
            if directory.exists():
                return True
            from botocore.exceptions import ClientError

            try:
                response = self.client.get_object(
                    Bucket=self.bucket, Key=self.key(directory), ExpectedBucketOwner=self.owner
                )
            except ClientError as error:
                if error.response["Error"]["Code"] in {"NoSuchKey", "404"}:
                    return False
                raise
            body = response["Body"]
            try:
                with tempfile.TemporaryFile() as archive:
                    total = 0
                    digest = hashlib.sha256()
                    while chunk := body.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_ARCHIVE_BYTES:
                            raise ValueError("Session archive exceeds size limit")
                        digest.update(chunk)
                        archive.write(chunk)
                    if digest.hexdigest() != response.get("Metadata", {}).get("sha256"):
                        raise ValueError("Session archive checksum mismatch")
                    archive.seek(0)
                    directory.parent.mkdir(parents=True, exist_ok=True)
                    staging = Path(tempfile.mkdtemp(prefix=".s3-restore-", dir=directory.parent))
                    try:
                        with zipfile.ZipFile(archive) as bundle:
                            entries = bundle.infolist()
                            if (
                                len(entries) > MAX_FILES
                                or sum(e.file_size for e in entries) > MAX_ARCHIVE_BYTES
                            ):
                                raise ValueError("Expanded session archive exceeds size limit")
                            for entry in entries:
                                path = PurePosixPath(entry.filename)
                                if (
                                    path.is_absolute()
                                    or ".." in path.parts
                                    or "\\" in entry.filename
                                    or not path.parts
                                ):
                                    raise ValueError("Unsafe archive path")
                                if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                                    raise ValueError("Archive symlink is not allowed")
                                target = staging.joinpath(*path.parts)
                                if entry.is_dir():
                                    target.mkdir(parents=True, exist_ok=True)
                                else:
                                    target.parent.mkdir(parents=True, exist_ok=True)
                                    with bundle.open(entry) as source, target.open("wb") as dest:
                                        shutil.copyfileobj(source, dest)
                        if not directory.exists():
                            os.rename(staging, directory)
                    finally:
                        if staging.exists():
                            shutil.rmtree(staging)
            finally:
                body.close()
            return True


def create_session_storage(settings: Settings):
    if getattr(settings, "session_storage_backend", "local") == "local":
        return LocalSessionStorage()
    return S3SessionStorage(settings)
