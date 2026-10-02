from __future__ import annotations

import asyncio
import json
from datetime import date
from types import SimpleNamespace

from app.auth import AuthenticatedUser
from app.db.engine import close_db, init_db
from app.services.atlas import (
    AtlasQuestion,
    allowed_refs,
    ask_atlas,
    collect_reference_ids,
    parse_answer,
)
from app.services.daily_journal import JournalInput, save_journal


def test_reference_ids_are_collected_from_id_keys():
    context = {
        "claims": [{"claimId": "claim.career.1", "supportingFactIds": ["fact.mars.h10"]}],
        "timingWindows": [{"windowId": "tw.1", "label": "not an id"}],
    }
    assert collect_reference_ids(context) == {"claim.career.1", "fact.mars.h10", "tw.1"}


def test_answer_refs_are_limited_to_supplied_evidence():
    evidence = {
        "day": {"pillar": "己酉"},
        "journal": {"learnedDayPatterns": [{"kind": "stem", "key": "甲"}]},
        "vedicReading": {"claims": [{"claimId": "claim.career.1"}]},
    }
    raw = json.dumps(
        {
            "headline": "Close something today.",
            "answer": "Finish what is already in motion.",
            "lenses": [
                {
                    "source": "vedic",
                    "text": "Career claim.",
                    "refs": ["claim.career.1", "claim.made.up"],
                },
                {
                    "source": "bazi",
                    "text": "Wealth day.",
                    "refs": ["day:己酉", "pattern:stem:甲", "day:甲子"],
                },
            ],
            "followUps": ["Why?"],
        },
        ensure_ascii=False,
    )
    answer = parse_answer("```json\n" + raw + "\n```", allowed_refs(evidence))
    assert answer.lenses[0].refs == ["claim.career.1"]
    assert answer.lenses[1].refs == ["day:己酉", "pattern:stem:甲"]


def test_atlas_uses_only_the_callers_journal(monkeypatch, tmp_path):
    import app.container

    prompts = []

    async def generate(task, prompt, **kwargs):
        prompts.append(prompt)
        return SimpleNamespace(
            raw_text=json.dumps(
                {
                    "headline": "Keep it light today.",
                    "answer": "A steady day.",
                    "lenses": [],
                    "followUps": [],
                }
            )
        )

    runtime = SimpleNamespace(is_configured=lambda: True, run_direct_prompt_task=generate)
    monkeypatch.setattr(
        app.container, "get_container", lambda: SimpleNamespace(agent_runtime=runtime)
    )

    async def run():
        await init_db(
            SimpleNamespace(
                database_url=f"sqlite+aiosqlite:///{tmp_path / 'atlas.db'}", database_echo=False
            )
        )
        try:
            alice = AuthenticatedUser(user_id="alice", auth_mode="clerk")
            bob = AuthenticatedUser(user_id="bob", auth_mode="clerk")
            await save_journal(
                JournalInput(day=date(2026, 10, 1), timezone="UTC", mood=4, note="ALICE_NOTE"),
                alice,
            )
            await save_journal(
                JournalInput(day=date(2026, 10, 1), timezone="UTC", mood=2, note="BOB_NOTE"), bob
            )

            result = await ask_atlas(
                AtlasQuestion(message="What should I focus on?", day=date(2026, 10, 2)), alice
            )
            assert result["day"] == "己酉"
            assert result["sources"] == {"vedic": False, "journalDays": 1, "notesShared": True}
            assert "ALICE_NOTE" in prompts[-1] and "BOB_NOTE" not in prompts[-1]

            await ask_atlas(
                AtlasQuestion(message="Again", day=date(2026, 10, 2), useNotes=False), alice
            )
            assert "ALICE_NOTE" not in prompts[-1]
        finally:
            await close_db()

    asyncio.run(run())


def test_atlas_reads_the_owned_agent_context(monkeypatch):
    import app.container
    from app.services.atlas import load_vedic_reading

    checked = []

    async def assert_access(session_id, owner):
        checked.append((session_id, owner))

    container = SimpleNamespace(
        metadata_store=SimpleNamespace(assert_session_access=assert_access),
        skill_workspace=SimpleNamespace(
            read_artifact_text=lambda session_id, path: json.dumps({"claims": [{"claimId": "c1"}]})
        ),
    )
    monkeypatch.setattr(app.container, "get_container", lambda: container)
    reading = asyncio.run(load_vedic_reading("session_1", "alice"))
    assert reading == {"claims": [{"claimId": "c1"}]}
    assert checked == [("session_1", "alice")]
