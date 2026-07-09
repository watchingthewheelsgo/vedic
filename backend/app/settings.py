from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration for the skill-aligned backend.

    This backend owns HTTP, workspace state, calculation code, tool scripts,
    dependencies, and agent orchestration. The vendored `.claude/skills`
    directory is only the source of truth for workflow prompts, resources,
    concepts, and output contracts. Skills are grouped by first-level
    methodology category, such as `.claude/skills/vedic` and
    `.claude/skills/bazi`.
    """

    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8787, alias="PORT")
    reload: bool = Field(default=False, alias="RELOAD")
    database_url: str = Field(
        default=f"sqlite+aiosqlite:///{PROJECT_ROOT / 'backend' / 'data' / 'vedic.db'}",
        alias="DATABASE_URL",
    )
    database_echo: bool = Field(default=False, alias="DATABASE_ECHO")
    supabase_project_ref: str = Field(default="", alias="SUPABASE_PROJECT_REF")
    supabase_db_password: str = Field(default="", alias="SUPABASE_DB_PASSWORD")
    supabase_db_user: str = Field(default="postgres", alias="SUPABASE_DB_USER")
    supabase_db_name: str = Field(default="postgres", alias="SUPABASE_DB_NAME")
    supabase_db_host: str = Field(default="", alias="SUPABASE_DB_HOST")
    supabase_db_port: int = Field(default=5432, alias="SUPABASE_DB_PORT")
    vedic_auth_mode: str = Field(default="auto", alias="VEDIC_AUTH_MODE")
    clerk_publishable_key: str = Field(default="", alias="VITE_CLERK_PUBLISHABLE_KEY")
    clerk_secret_key: str = Field(default="", alias="CLERK_SECRET_KEY")
    vedic_admin_user_ids: str = Field(default="", alias="VEDIC_ADMIN_USER_IDS")
    vedic_admin_emails: str = Field(default="", alias="VEDIC_ADMIN_EMAILS")

    creem_api_key: str = Field(default="", alias="CREEM_API_KEY")
    creem_webhook_secret: str = Field(default="", alias="CREEM_WEBHOOK_SECRET")
    creem_test_mode: bool = Field(default=True, alias="CREEM_TEST_MODE")
    creem_api_base_url: str = Field(default="", alias="CREEM_API_BASE_URL")
    creem_success_url: str = Field(
        default="http://127.0.0.1:5173/account?billing=success",
        alias="CREEM_SUCCESS_URL",
    )
    creem_product_pro_monthly: str = Field(default="", alias="CREEM_PRODUCT_PRO_MONTHLY")
    creem_product_pro_yearly: str = Field(default="", alias="CREEM_PRODUCT_PRO_YEARLY")
    creem_product_single_report: str = Field(default="", alias="CREEM_PRODUCT_SINGLE_REPORT")

    vedic_astro_skills_root: str | None = Field(default=None, alias="VEDIC_ASTRO_SKILLS_ROOT")
    vedic_geonames_path: str | None = Field(default=None, alias="VEDIC_GEONAMES_PATH")
    vedic_ai_mode: str = Field(default="", alias="VEDIC_AI_MODE")
    amap_web_service_key: str = Field(default="", alias="AMAP_WEB_SERVICE_KEY")
    amap_place_fallback_enabled: bool = Field(default=False, alias="AMAP_PLACE_FALLBACK_ENABLED")
    amap_request_timeout_seconds: float = Field(default=2.5, alias="AMAP_REQUEST_TIMEOUT_SECONDS")
    web_place_search_enabled: bool = Field(default=True, alias="WEB_PLACE_SEARCH_ENABLED")
    web_place_search_url: str = Field(
        default="https://duckduckgo.com/html/", alias="WEB_PLACE_SEARCH_URL"
    )
    web_place_search_timeout_seconds: float = Field(
        default=3.0, alias="WEB_PLACE_SEARCH_TIMEOUT_SECONDS"
    )
    place_lookup_agent_timeout_seconds: float = Field(
        default=45.0, alias="PLACE_LOOKUP_AGENT_TIMEOUT_SECONDS"
    )
    web_place_search_user_agent: str = Field(
        default=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
        ),
        alias="WEB_PLACE_SEARCH_USER_AGENT",
    )

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
        return PROJECT_ROOT

    @property
    def tapvox_root(self) -> Path:
        return self.project_root.parent

    @property
    def calculator_root(self) -> Path:
        return self.project_root / "backend" / "app" / "calculator"

    @property
    def default_database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.project_root / 'backend' / 'data' / 'vedic.db'}"

    @property
    def local_database_urls(self) -> set[str]:
        return {
            self.default_database_url,
            "sqlite+aiosqlite:///./backend/data/vedic.db",
        }

    def resolved_database_url(self) -> str:
        """Return the effective DB URL without requiring secrets in DATABASE_URL."""

        if self._has_custom_database_url():
            return self.database_url
        if self.supabase_project_ref.strip() and self.supabase_db_password.strip():
            return self.supabase_database_url()
        return self.database_url

    def database_source(self) -> str:
        if self._has_custom_database_url():
            return "database_url"
        if self.supabase_project_ref.strip() and self.supabase_db_password.strip():
            return "supabase"
        if self.supabase_project_ref.strip():
            return "local_missing_supabase_password"
        return "local"

    def _has_custom_database_url(self) -> bool:
        return bool(self.database_url) and self.database_url not in self.local_database_urls

    def supabase_database_url(self) -> str:
        project_ref = self.supabase_project_ref.strip()
        host = self.supabase_db_host.strip() or f"db.{project_ref}.supabase.co"
        user = quote(self.supabase_db_user.strip() or "postgres", safe="")
        password = quote(self.supabase_db_password.strip(), safe="")
        database = quote(self.supabase_db_name.strip() or "postgres", safe="")
        return (
            f"postgresql://{user}:{password}@{host}:{self.supabase_db_port}/{database}"
            "?sslmode=require"
        )

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
        # Worldwide GeoNames dataset bundled with PyJHora (cities >= 5k population,
        # 245 countries). Replaces the earlier India-only geonames_places_5k_IN.csv.
        candidate = self.calculator_site_packages() / "jhora" / "data" / "geonames_places_5k.csv"
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

    def auth_config_summary(self) -> dict[str, object]:
        enabled = self.auth_enabled()
        return {
            "mode": "clerk" if enabled else "disabled",
            "publishableKeyConfigured": bool(self.clerk_publishable_key.strip()),
            "secretKeyConfigured": bool(self.clerk_secret_key.strip()),
            "verifier": self.clerk_verifier_source(),
        }

    def creem_effective_api_base_url(self) -> str:
        explicit = self.creem_api_base_url.strip().rstrip("/")
        if explicit:
            return explicit
        return "https://test-api.creem.io" if self.creem_test_mode else "https://api.creem.io"

    def billing_config_summary(self) -> dict[str, object]:
        plan_ids = self.creem_product_ids_by_plan()
        return {
            "provider": "creem",
            "configured": bool(self.creem_api_key.strip()),
            "webhookConfigured": bool(self.creem_webhook_secret.strip()),
            "testMode": self.creem_test_mode,
            "apiBaseUrl": self.creem_effective_api_base_url(),
            "plansConfigured": {
                key: bool(product_id.strip()) for key, product_id in plan_ids.items()
            },
        }

    def creem_product_ids_by_plan(self) -> dict[str, str]:
        return {
            "pro_monthly": self.creem_product_pro_monthly,
            "pro_yearly": self.creem_product_pro_yearly,
            "single_report": self.creem_product_single_report,
        }

    def auth_enabled(self) -> bool:
        mode = self.vedic_auth_mode.strip().lower()
        if mode == "disabled":
            return False
        if mode == "clerk":
            return True
        return bool(self.clerk_publishable_key.strip() or self.clerk_secret_key.strip())

    def clerk_verifier_source(self) -> str:
        if self.clerk_secret_key.strip():
            return "unsigned_jwt_claims_plus_clerk_user_lookup"
        return "unconfigured"

    def is_admin_identity(self, user_id: str, email: str | None = None) -> bool:
        user_ids = _csv_set(self.vedic_admin_user_ids)
        emails = _csv_set(self.vedic_admin_emails)
        if user_id and user_id.lower() in user_ids:
            return True
        return bool(email and email.lower() in emails)


def _csv_set(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
