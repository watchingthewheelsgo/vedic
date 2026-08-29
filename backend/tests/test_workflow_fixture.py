from __future__ import annotations

import json
from pathlib import Path

from app.schemas import SkillBirthInput


def test_full_workflow_default_birth_input_matches_the_live_api_contract() -> None:
    fixture_path = Path(__file__).parents[2] / "scripts" / "fixtures" / "workflow-birth-input.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    validated = SkillBirthInput.model_validate(payload)

    assert validated.display_name == "Workflow Test"
    assert validated.time_source == "user_reported_time"
    assert "coord=WGS84" in validated.birth_place
