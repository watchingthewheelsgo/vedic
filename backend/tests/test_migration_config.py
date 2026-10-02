from contextlib import nullcontext
from pathlib import Path
import runpy
from types import SimpleNamespace

from alembic import context
from sqlalchemy.engine import make_url


def test_alembic_uses_async_driver_and_preserves_encoded_password(monkeypatch):
    captured = {}
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://signatlas:p%40ss%25word@db/signatlas?sslmode=disable"
    )
    monkeypatch.setattr(context, "config", SimpleNamespace(), raising=False)
    monkeypatch.setattr(context, "is_offline_mode", lambda: True)
    monkeypatch.setattr(context, "configure", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(context, "begin_transaction", nullcontext)
    monkeypatch.setattr(context, "run_migrations", lambda: None)
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "alembic" / "env.py"))
    url = make_url(captured["url"])
    assert url.drivername == "postgresql+asyncpg"
    assert url.password == "p@ss%word"
    assert url.query == {"ssl": "disable"}
