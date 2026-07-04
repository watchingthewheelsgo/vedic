from __future__ import annotations

import importlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RuntimePreflightReport:
    """Summary of backend-owned runtime checks."""

    dependencies: dict[str, str]
    ephemeris_files: list[str]
    geonames_path: str


@dataclass(frozen=True)
class StartupConfigPreflightReport:
    """Summary of startup configuration checks that are safe to expose."""

    env_file: str | None
    agent_mode: str
    base_url: str
    model: str


REQUIRED_IMPORTS: tuple[tuple[str, str], ...] = (
    ("swisseph", "pysweph>=2.10.3.5"),
    ("dashaflow", "dashaflow>=0.3 installed with --no-deps"),
    ("jhora", "PyJHora==4.8.6"),
    ("pytz", "pytz>=2024.1"),
    ("numpy", "numpy"),
    ("geocoder", "geocoder"),
    ("geopy", "geopy"),
    ("timezonefinder", "timezonefinder"),
    ("dateutil", "python-dateutil"),
    ("requests", "requests"),
)


def validate_startup_configuration(settings: Any) -> StartupConfigPreflightReport:
    """Fail fast when local startup cannot reach the LLM-backed agent runtime."""

    project_root = Path(settings.project_root)
    env_path = project_root / ".env"
    mock_mode = str(settings.vedic_ai_mode).strip().lower() == "mock"
    errors: list[str] = []

    if not env_path.exists() and not mock_mode:
        errors.append(f"Missing .env file at {env_path}.")

    token = settings.get_agent_auth_token()
    if not mock_mode and not token:
        errors.append(
            "No LLM auth token configured. Set DEEPSEEK_API_KEY (recommended), "
            "or ANTHROPIC_AUTH_TOKEN / ANTHROPIC_API_KEY / OPENAI_API_KEY."
        )

    base_url = str(settings.anthropic_base_url or "").strip()
    if not mock_mode and (not base_url or not base_url.startswith(("http://", "https://"))):
        errors.append("ANTHROPIC_BASE_URL must be a non-empty http(s) URL.")

    model = str(settings.anthropic_model or "").strip()
    if not mock_mode and not model:
        errors.append("ANTHROPIC_MODEL must be set.")

    if not mock_mode:
        try:
            importlib.import_module("claude_agent_sdk")
        except Exception as exc:
            errors.append(
                "claude-agent-sdk is not importable in the backend runtime. "
                f"Run `uv sync --project backend` or `npm run backend:setup`. ({exc})"
            )

    auth_enabled = bool(settings.auth_enabled()) if hasattr(settings, "auth_enabled") else False
    if auth_enabled:
        publishable_key = str(getattr(settings, "clerk_publishable_key", "") or "").strip()
        issuer = str(getattr(settings, "clerk_jwt_issuer", "") or "").strip()
        jwks_url = str(getattr(settings, "clerk_jwks_url", "") or "").strip()
        if not publishable_key:
            errors.append(
                "Clerk auth is enabled. Set VITE_CLERK_PUBLISHABLE_KEY so the React app can "
                "initialize Clerk."
            )
        if not issuer and not jwks_url:
            errors.append(
                "Clerk auth is enabled. Set CLERK_JWT_ISSUER or CLERK_JWKS_URL "
                "so the backend can verify Clerk session tokens."
            )

    if errors:
        raise RuntimeError(
            "Backend startup configuration is not ready:\n"
            + "\n".join(f"- {item}" for item in errors)
            + "\n\nHow to fix:\n"
            + "1. Run `cp .env.example .env` from the project root if `.env` is missing.\n"
            + "2. Edit `.env` and set `DEEPSEEK_API_KEY=...`.\n"
            + "3. Keep `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic` unless you use "
            + "another Claude-compatible provider.\n"
            + "4. Run `npm run dev` again.\n"
            + "\nFor UI-only local testing without an LLM, set `VEDIC_AI_MODE=mock` in `.env` "
            + "or your shell."
            + "\nFor local testing without Clerk, set `VEDIC_AUTH_MODE=disabled`; "
            + "for real auth, set `VEDIC_AUTH_MODE=clerk` and `CLERK_JWT_ISSUER=...`."
        )

    env_source = str(env_path) if env_path.exists() else ("process-env" if os.environ else None)
    return StartupConfigPreflightReport(
        env_file=env_source,
        agent_mode="mock" if mock_mode else "claude",
        base_url=base_url,
        model=model,
    )


def validate_backend_runtime(project_root: Path) -> RuntimePreflightReport:
    """Fail fast when the backend venv cannot run the astrology engine."""

    modules: dict[str, Any] = {}
    missing: list[str] = []
    versions: dict[str, str] = {}

    for module_name, package_hint in REQUIRED_IMPORTS:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            missing.append(f"{module_name} ({package_hint}): {exc}")
            continue
        modules[module_name] = module
        versions[module_name] = str(
            getattr(module, "__version__", None) or getattr(module, "version", None) or "installed"
        )

    if missing:
        raise RuntimeError(
            "Backend runtime dependencies are not ready:\n"
            + "\n".join(f"- {item}" for item in missing)
            + "\nRun `npm run backend:setup` from the project root."
        )

    swisseph_version = versions.get("swisseph", "")
    if swisseph_version == "0.0.0":
        raise RuntimeError(
            "swisseph resolved to an empty stub package. Run `npm run backend:setup` "
            "so the backend installs pysweph and dashaflow in the supported order."
        )

    jhora_root = Path(modules["jhora"].__file__).resolve().parent
    geonames_path = jhora_root / "data" / "geonames_places_5k.csv"
    if not geonames_path.exists():
        raise RuntimeError(
            f"PyJHora GeoNames data is missing at {geonames_path}. "
            "Run `npm run backend:setup` from the project root."
        )

    ephemeris_files = ensure_jhora_ephemeris(project_root=project_root, jhora_root=jhora_root)
    return RuntimePreflightReport(
        dependencies=versions,
        ephemeris_files=[path.name for path in ephemeris_files],
        geonames_path=str(geonames_path),
    )


def ensure_jhora_ephemeris(project_root: Path, jhora_root: Path) -> list[Path]:
    """Copy bundled Swiss Ephemeris files into PyJHora when its wheel lacks them."""

    ephe_dir = jhora_root / "data" / "ephe"
    existing = sorted(ephe_dir.glob("*.se1")) if ephe_dir.exists() else []
    if existing:
        return existing

    bundled_dir = project_root / "backend" / "app" / "calculator" / "ephe"
    bundled = sorted(bundled_dir.glob("*.se1"))
    if not bundled:
        raise RuntimeError(f"Bundled ephemeris files are missing under {bundled_dir}")

    ephe_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for source in bundled:
        target = ephe_dir / source.name
        shutil.copy2(source, target)
        copied.append(target)
    return copied
