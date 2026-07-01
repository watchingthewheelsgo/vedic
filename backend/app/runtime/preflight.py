from __future__ import annotations

import importlib
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
            getattr(module, "__version__", None)
            or getattr(module, "version", None)
            or "installed"
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
    geonames_path = jhora_root / "data" / "geonames_places_5k_IN.csv"
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
