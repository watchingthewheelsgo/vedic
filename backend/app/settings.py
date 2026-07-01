from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the skill-aligned backend.

    This backend owns HTTP, workspace state, calculation code, tool scripts,
    dependencies, and agent orchestration. The vendored `.claude/skills`
    directory is only the source of truth for workflow prompts, resources,
    concepts, and output contracts.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8787, alias="PORT")
    reload: bool = Field(default=False, alias="RELOAD")

    vedic_astro_skills_root: str | None = Field(default=None, alias="VEDIC_ASTRO_SKILLS_ROOT")
    vedic_geonames_path: str | None = Field(default=None, alias="VEDIC_GEONAMES_PATH")
    vedic_ai_mode: str = Field(default="", alias="VEDIC_AI_MODE")

    anthropic_base_url: str = Field(
        default="https://api.deepseek.com/anthropic", alias="ANTHROPIC_BASE_URL"
    )
    anthropic_auth_token: str = Field(default="", alias="ANTHROPIC_AUTH_TOKEN")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="deepseek-v4-pro[1m]", alias="ANTHROPIC_MODEL")
    anthropic_default_opus_model: str = Field(
        default="deepseek-v4-pro[1m]", alias="ANTHROPIC_DEFAULT_OPUS_MODEL"
    )
    anthropic_default_sonnet_model: str = Field(
        default="deepseek-v4-pro[1m]", alias="ANTHROPIC_DEFAULT_SONNET_MODEL"
    )
    anthropic_default_haiku_model: str = Field(
        default="deepseek-v4-flash", alias="ANTHROPIC_DEFAULT_HAIKU_MODEL"
    )
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    agent_effort: str = Field(default="max", alias="AGENT_EFFORT")
    agent_max_turns: int = Field(default=8, alias="AGENT_MAX_TURNS")
    agent_timeout_ms: int = Field(default=420_000, alias="AGENT_TIMEOUT_MS")

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def tapvox_root(self) -> Path:
        return self.project_root.parent

    @property
    def calculator_root(self) -> Path:
        return self.project_root / "backend" / "app" / "calculator"

    @property
    def skills_root(self) -> Path:
        if self.vedic_astro_skills_root:
            return Path(self.vedic_astro_skills_root).expanduser().resolve()
        return self.project_root / ".claude" / "skills"

    def calculator_site_packages(self) -> Path:
        runtime_site_packages = self.runtime_site_packages()
        if (runtime_site_packages / "jhora").exists():
            return runtime_site_packages
        raise RuntimeError(
            "Calculator dependencies not found in the backend runtime. "
            "Run `npm run backend:setup` from the project root."
        )

    def runtime_site_packages(self) -> Path:
        """Return the site-packages directory for the active backend interpreter."""

        import sysconfig

        purelib = sysconfig.get_paths().get("purelib")
        if not purelib:
            raise RuntimeError("Cannot resolve backend runtime site-packages")
        return Path(purelib).resolve()

    def geonames_path(self) -> Path:
        if self.vedic_geonames_path:
            explicit = Path(self.vedic_geonames_path).expanduser().resolve()
            if explicit.exists():
                return explicit
        candidate = self.calculator_site_packages() / "jhora" / "data" / "geonames_places_5k_IN.csv"
        if candidate.exists():
            return candidate
        raise RuntimeError("Cannot find PyJHora GeoNames CSV. Set VEDIC_GEONAMES_PATH.")

    def get_agent_auth_token(self) -> str:
        for value in [
            self.anthropic_auth_token,
            self.deepseek_api_key,
            self.anthropic_api_key,
            os.environ.get("OPENAI_API_KEY", ""),
        ]:
            if value and value.strip():
                return value.strip()
        return ""

    def agent_config_summary(self) -> dict[str, object]:
        configured = self.vedic_ai_mode != "mock" and bool(self.get_agent_auth_token())
        return {
            "mode": "claude" if configured else "mock",
            "baseUrl": self.anthropic_base_url,
            "model": self.anthropic_model,
            "maxTurns": self.agent_max_turns,
            "timeoutMs": self.agent_timeout_ms,
            "skillRuntime": "claude-agent-sdk-python",
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
