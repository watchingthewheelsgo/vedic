from __future__ import annotations

from functools import lru_cache

from app.agents.claude_runtime import ClaudeRuntime
from app.services.core_job_runtime import CoreJobRuntime
from app.services.place_service import PlaceService
from app.services.skill_runtime import SkillRuntime
from app.services.skill_workspace import SkillWorkspace
from app.services.vedic_calculator import VedicCalculator
from app.settings import Settings, get_settings


class AppContainer:
    """Application dependency graph for the skill-aligned runtime."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.place_service = PlaceService(settings)
        self.calculator = VedicCalculator(settings, self.place_service)
        self.skill_workspace = SkillWorkspace(settings)
        self.agent_runtime = ClaudeRuntime(settings)
        self.skill_runtime = SkillRuntime(
            calculator=self.calculator,
            workspace=self.skill_workspace,
            agent_runtime=self.agent_runtime,
        )
        self.core_job_runtime = CoreJobRuntime(skill_runtime=self.skill_runtime)


@lru_cache(maxsize=1)
def get_container() -> AppContainer:
    return AppContainer(get_settings())
