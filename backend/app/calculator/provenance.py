from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import jhora
import pytz


RUNTIME_DISTRIBUTIONS = (
    "PyJHora",
    "pysweph",
    "pytz",
    "numpy",
    "python-dateutil",
)


@dataclass(frozen=True)
class CalculationRuntimeProvenance:
    provider_versions: dict[str, str]
    timezone_database_version: str
    ephemeris_data_fingerprint: str

    @property
    def summary(self) -> str:
        providers = ", ".join(
            f"{name} {package_version}" for name, package_version in self.provider_versions.items()
        )
        return f"{providers}; tzdb {self.timezone_database_version}"


@lru_cache(maxsize=1)
def calculation_runtime_provenance() -> CalculationRuntimeProvenance:
    versions = {name: _distribution_version(name) for name in RUNTIME_DISTRIBUTIONS}
    ephemeris_dir = Path(jhora.__file__).resolve().parent / "data" / "ephe"
    return CalculationRuntimeProvenance(
        provider_versions=versions,
        timezone_database_version=str(getattr(pytz, "OLSON_VERSION", pytz.VERSION)),
        ephemeris_data_fingerprint=_directory_fingerprint(ephemeris_dir),
    )


def _distribution_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError as exc:
        raise RuntimeError(f"Required calculation distribution is missing: {name}") from exc


def _directory_fingerprint(directory: Path) -> str:
    files = sorted(path for path in directory.iterdir() if path.is_file())
    if not files:
        raise RuntimeError(f"No ephemeris data files found under {directory}")
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"
