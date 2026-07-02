#!/usr/bin/env python3
"""
Prepare backend runtime dependencies for the Vedic calculator.

This is intentionally backend-owned. Skills describe workflow, concepts,
prompts, and output contracts; they do not create venvs or install packages.

Usage:
  uv sync --project backend
  uv run --project backend python scripts/setup-backend-runtime.py
  uv run --project backend python scripts/setup-backend-runtime.py --check-only
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
DEFAULT_VENV = BACKEND_DIR / ".venv"
MIN_PYTHON = (3, 11)
# Upper bound only used when searching for a fallback interpreter; the runtime
# supports 3.11 and newer.
MAX_PYTHON = (3, 13)

REQUIRED_PACKAGES: tuple[tuple[str, str, list[str]], ...] = (
    ("pysweph", ">=2.10.3.5", []),
    ("pytz", ">=2024.1", []),
    ("numpy", "", []),
    ("geocoder", "", []),
    ("geopy", "", []),
    ("requests", "", []),
    ("timezonefinder", "", []),
    ("python-dateutil", "", []),
    ("dashaflow", ">=0.3", ["--no-deps"]),
    ("PyJHora", "==4.8.6", []),
    ("markdown", ">=3.6", []),
)


def log(message: str, level: str = "INFO") -> None:
    prefixes = {"INFO": "[info]", "OK": "[ok]", "WARN": "[warn]", "ERR": "[err]"}
    print(f"{prefixes.get(level, '[info]')} {message}")


def get_venv_python(venv_dir: Path) -> Path:
    if platform.system() == "Windows":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def supported_version(version_info: tuple[int, int]) -> bool:
    return version_info >= MIN_PYTHON


def find_python() -> str | None:
    current = sys.version_info
    if supported_version((current.major, current.minor)):
        return sys.executable

    if platform.system() == "Windows":
        for minor in range(MAX_PYTHON[1], MIN_PYTHON[1] - 1, -1):
            command = ["py", f"-3.{minor}", "--version"]
            result = subprocess.run(command, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return f"py -3.{minor}"

    for minor in range(MAX_PYTHON[1], MIN_PYTHON[1] - 1, -1):
        name = f"python3.{minor}"
        if shutil.which(name):
            return name
    return None


def run_cmd(
    command: list[str],
    description: str,
    *,
    timeout: int = 600,
    env: dict[str, str] | None = None,
) -> bool:
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if result.returncode == 0:
        return True
    tail = "\n".join(part for part in [result.stdout[-600:], result.stderr[-1200:]] if part)
    log(f"{description} failed\n{tail}", "ERR")
    return False


def create_venv(venv_dir: Path) -> bool:
    python_cmd = find_python()
    if not python_cmd:
        log("Python 3.11 or newer is required for this backend runtime.", "ERR")
        return False
    command = python_cmd.split() + ["-m", "venv", str(venv_dir)]
    log(f"Creating backend venv: {venv_dir}")
    return run_cmd(command, "create backend venv")


def ensure_pip(python_exe: Path) -> bool:
    if run_cmd([str(python_exe), "-m", "pip", "--version"], "check pip", timeout=60):
        return True
    log("pip is missing; bootstrapping with ensurepip", "WARN")
    return run_cmd([str(python_exe), "-m", "ensurepip", "--upgrade"], "bootstrap pip", timeout=120)


def install_packages(python_exe: Path) -> bool:
    if not ensure_pip(python_exe):
        return False

    run_cmd([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"], "upgrade pip")
    for package, version_spec, extra_args in REQUIRED_PACKAGES:
        spec = f"{package}{version_spec}"
        log(f"Installing {spec} {' '.join(extra_args)}".strip())
        command = [str(python_exe), "-m", "pip", "install", spec, *extra_args]
        if not run_cmd(command, f"install {package}", timeout=900):
            return False
    return True


def backend_env() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(BACKEND_DIR) if not existing else f"{BACKEND_DIR}{os.pathsep}{existing}"
    return env


def run_python(python_exe: Path, code: str, *, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(python_exe), "-c", code],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=backend_env(),
    )


def validate(python_exe: Path) -> bool:
    code = f"""
from pathlib import Path
import sys
sys.path.insert(0, r"{BACKEND_DIR}")
from app.runtime.preflight import validate_backend_runtime
from app.calculator.ashtakavarga_pyjhora import calculate_ashtakavarga_fixed

report = validate_backend_runtime(Path(r"{PROJECT_ROOT}"))
r = calculate_ashtakavarga_fixed(2002, 12, 11, 20, 47, 25.4333, 119.0, 8.0)
total = sum(r["sarvashtakavarga"].values())
print("dependencies=" + ",".join(sorted(report.dependencies.keys())))
print(f"SAV_RESULT={{total}}")
assert total == 337, f"SAV={{total}} != 337"
"""
    result = run_python(python_exe, code, timeout=120)
    if result.returncode == 0 and "SAV_RESULT=337" in result.stdout:
        for line in result.stdout.strip().splitlines():
            if line.startswith("dependencies=") or line.startswith("SAV_RESULT="):
                log(line, "OK")
        return True

    output = "\n".join(part for part in [result.stdout[-800:], result.stderr[-1600:]] if part)
    log(f"backend runtime validation failed\n{output}", "ERR")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare backend calculator runtime")
    parser.add_argument("--target", type=Path, default=DEFAULT_VENV, help="backend venv path")
    parser.add_argument("--check-only", action="store_true", help="validate only; do not install")
    args = parser.parse_args()

    venv_dir = args.target.expanduser().resolve()
    python_exe = get_venv_python(venv_dir)

    if not python_exe.exists():
        if args.check_only:
            log(f"Backend venv does not exist: {venv_dir}", "ERR")
            return 1
        if not create_venv(venv_dir):
            return 1

    python_exe = get_venv_python(venv_dir)
    log(f"Backend Python: {python_exe}")

    if validate(python_exe):
        log("Backend runtime is ready", "OK")
        return 0

    if args.check_only:
        log("Run `npm run backend:setup` to install missing backend dependencies.", "ERR")
        return 1

    if not install_packages(python_exe):
        return 1

    if not validate(python_exe):
        return 1

    log("Backend runtime setup complete", "OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
