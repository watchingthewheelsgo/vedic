import asyncio
import hashlib
import io
import shutil
import zipfile
from types import SimpleNamespace
import pytest
from botocore.exceptions import ClientError
from app.services.session_storage import S3SessionStorage, create_session_storage
from app.services.skill_workspace import SkillWorkspace
from app.services.metadata_store import MetadataStore
from app.db.engine import init_db, close_db


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.fail = False

    def upload_fileobj(self, body, bucket, key, ExtraArgs):
        if self.fail:
            raise RuntimeError("S3 unavailable")
        assert ExtraArgs["ServerSideEncryption"] == "AES256"
        assert ExtraArgs["ExpectedBucketOwner"] == "123456789012"
        self.objects[key] = (body.read(), ExtraArgs["Metadata"])

    def get_object(self, **args):
        if args["Key"] not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        data, meta = self.objects[args["Key"]]
        return {"Body": io.BytesIO(data), "Metadata": meta}


def settings(tmp_path, mode="s3"):
    return SimpleNamespace(
        project_root=tmp_path,
        session_storage_backend=mode,
        session_s3_bucket="test",
        session_s3_region="us-west-2",
        session_s3_prefix="sessions",
        session_s3_expected_owner="123456789012",
    )


def test_local_mode_never_initializes_aws(tmp_path, monkeypatch):
    import boto3

    def fail(*args, **kwargs):
        raise AssertionError("Local mode must never contact AWS")

    monkeypatch.setattr(boto3, "client", fail)
    workspace = SkillWorkspace(settings(tmp_path, "local"))
    sid = workspace.create_session("session_local")
    workspace.write_artifact(sid, "consultation_report.md", "hello")
    workspace.persist_session(sid)
    assert workspace.read_artifact_text(sid, "consultation_report.md") == "hello"
    with pytest.raises(LookupError):
        workspace.require_session_dir("missing")


def test_s3_sync_restore_integration_and_failed_upload_preserves_snapshot(tmp_path):
    async def run():
        cfg = settings(tmp_path)
        cfg.database_url = f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}"
        cfg.database_echo = False
        await init_db(cfg)
        try:
            workspace = SkillWorkspace(cfg)
            fake = FakeS3()
            workspace.storage = S3SessionStorage(cfg, client=fake)
            sid = workspace.create_session("session_test")
            workspace.write_artifact(sid, "consultation_report.md", "original")
            workspace.write_artifact(sid, "exports/report.pdf", "PDF fixture")
            workspace.write_artifact(sid, ".env", "must not archive")
            await MetadataStore(workspace).sync_session_from_files(
                sid, owner_user_id="alice", status="completed"
            )
            directory = workspace.session_dir(sid)
            key = workspace.storage.key(directory)
            old = fake.objects[key]
            workspace.write_artifact(sid, "consultation_report.md", "new")
            fake.fail = True
            with pytest.raises(RuntimeError):
                workspace.persist_session(sid)
            assert fake.objects[key] == old
            assert workspace.read_artifact_text(sid, "consultation_report.md") == "new"
            shutil.rmtree(directory)
            assert workspace.read_artifact_text(sid, "consultation_report.md") == "original"
            assert (directory / "exports/report.pdf").exists()
            assert not (directory / ".env").exists()
        finally:
            await close_db()

    asyncio.run(run())


@pytest.mark.parametrize("bad", ["../escape", "/absolute", "a/../../escape", "a\\escape"])
def test_restore_rejects_unsafe_archives_atomically(tmp_path, bad):
    fake = FakeS3()
    storage = S3SessionStorage(settings(tmp_path), client=fake)
    dest = tmp_path / "sessions" / "session_bad"
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as z:
        z.writestr("consultation_report.md", "good")
        z.writestr(bad, "bad")
    data = body.getvalue()
    fake.objects[storage.key(dest)] = (data, {"sha256": hashlib.sha256(data).hexdigest()})
    with pytest.raises(ValueError):
        storage.restore(dest)
    assert not dest.exists()
    assert not (tmp_path / "escape").exists()


def test_invalid_s3_configuration_fails_without_network(tmp_path):
    cfg = settings(tmp_path)
    cfg.session_s3_bucket = ""
    with pytest.raises(ValueError):
        create_session_storage(cfg)


def test_restore_checksum_and_upload_symlink_protection(tmp_path):
    fake = FakeS3()
    storage = S3SessionStorage(settings(tmp_path), client=fake)
    dest = tmp_path / "session_test"
    fake.objects[storage.key(dest)] = (b"broken", {"sha256": "invalid"})
    with pytest.raises(ValueError, match="checksum"):
        storage.restore(dest)
    assert not dest.exists()
    dest.mkdir()
    outside = tmp_path / "secret"
    outside.write_text("private")
    (dest / "consultation_report.md").symlink_to(outside)
    with pytest.raises(ValueError, match="symlinks"):
        storage.save(dest, lambda _: True)
