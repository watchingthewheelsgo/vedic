from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.auth import AuthenticatedUser
from app.db.engine import init_db, close_db
from app.services.daily_journal import (
    JournalInput,
    ReflectionActionInput,
    update_reflection_action,
    ReflectionInput,
    calendar_day,
    read_journal,
    save_journal,
    delete_journal,
    reflect_on_entry,
    summarize,
)


def test_calendar_cycle_and_validation():
    start = date(2024, 2, 10)
    assert (
        calendar_day(start, "Asia/Shanghai")["pillar"]
        == calendar_day(start + timedelta(days=60), "Asia/Shanghai")["pillar"]
    )
    assert (
        calendar_day(start, "Asia/Shanghai")["pillar"]
        != calendar_day(start + timedelta(days=1), "Asia/Shanghai")["pillar"]
    )
    with pytest.raises(ValueError):
        calendar_day(start, "Not/AZone")
    for changes in ({"mood": 6}, {"timezone": "No/Zone"}):
        values = {"day": start, "timezone": "UTC", "mood": 3, "note": "A quiet day"} | changes
        with pytest.raises(ValidationError):
            JournalInput(**values)
    # A mood alone is a complete check-in.
    assert JournalInput(day=start, timezone="UTC", mood=4, note="  ").note == ""
    assert JournalInput(day=start, timezone="UTC", mood=4).note == ""


def test_owner_isolation_idempotent_save_and_delete(tmp_path):
    async def run():
        await init_db(
            SimpleNamespace(
                database_url=f"sqlite+aiosqlite:///{tmp_path / 'journal.db'}", database_echo=False
            )
        )
        try:
            alice = AuthenticatedUser(user_id="alice", auth_mode="clerk")
            bob = AuthenticatedUser(user_id="bob", auth_mode="clerk")
            entry = JournalInput(
                day=date(2024, 2, 10), timezone="Asia/Shanghai", mood=4, note="Private day"
            )
            await save_journal(entry, alice)
            await save_journal(entry.model_copy(update={"mood": 5}), alice)
            assert (await read_journal("UTC", alice))["entries"][0]["mood"] == 5
            assert len((await read_journal("UTC", alice))["entries"]) == 1
            assert not (await read_journal("UTC", bob))["entries"]
            await delete_journal(entry.day, bob)
            assert len((await read_journal("UTC", alice))["entries"]) == 1
            await delete_journal(entry.day, alice)
            assert not (await read_journal("UTC", alice))["entries"]
            with pytest.raises(HTTPException) as exc:
                await save_journal(entry.model_copy(update={"day": date(2099, 1, 1)}), alice)
            assert exc.value.status_code == 422
        finally:
            await close_db()

    asyncio.run(run())


def test_statistics_do_not_rank_tiny_samples():
    entries = [{"mood": 5, "calendar": {"stem": "甲"}}] * 6
    assert summarize(entries)["byStem"][0]["averageMood"] is None
    assert summarize(entries + entries)["byStem"][0]["averageMood"] == 5
    assert summarize([])["averageMood"] is None


def test_reflection_uses_only_owned_selected_entry_and_persists(monkeypatch, tmp_path):
    import app.container

    calls = []

    async def generate(task, prompt, **kwargs):
        calls.append(prompt)
        lens = {
            "interpretation": "A reflective possibility, not a prediction.",
            "action": "Write one next step.",
        }
        return SimpleNamespace(
            raw_text=json.dumps(
                {
                    "summary": "Reflection",
                    "bazi": lens,
                    "vedic": lens,
                    "tarot": lens,
                    "questionToReflectOn": "What helped?",
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
                database_url=f"sqlite+aiosqlite:///{tmp_path / 'qa.db'}", database_echo=False
            )
        )
        try:
            alice = AuthenticatedUser(user_id="alice", auth_mode="clerk")
            bob = AuthenticatedUser(user_id="bob", auth_mode="clerk")
            entry = JournalInput(
                day=date(2024, 2, 10), timezone="UTC", mood=3, note="Selected note"
            )
            await save_journal(entry, alice)
            await save_journal(
                entry.model_copy(update={"day": date(2024, 2, 11), "note": "DO_NOT_SEND"}), alice
            )
            request = ReflectionInput(
                day=entry.day, question="How can I reflect?", request_id="unique-request-001"
            )
            with pytest.raises(HTTPException) as exc:
                await reflect_on_entry(request, bob)
            assert exc.value.status_code == 404
            assert not calls
            first = await reflect_on_entry(request, alice)
            again = await reflect_on_entry(request, alice)
            assert first == again and len(calls) == 1
            assert "Selected note" in calls[0] and "DO_NOT_SEND" not in calls[0]
            assert first["vedicSessionId"] is None
            action = ReflectionActionInput(
                day=entry.day, reflection_id=first["requestId"], lens="bazi", status="planned"
            )
            with pytest.raises(HTTPException) as forbidden:
                await update_reflection_action(action, bob)
            assert forbidden.value.status_code == 404
            assert (await update_reflection_action(action, alice))["actionStates"][
                "bazi"
            ] == "planned"
            assert (
                await update_reflection_action(action.model_copy(update={"status": "done"}), alice)
            )["actionStates"]["bazi"] == "done"
            assert not (
                await update_reflection_action(action.model_copy(update={"status": "none"}), alice)
            )["actionStates"]

            entries = (await read_journal("UTC", alice))["entries"]
            assert entries[1]["reflections"][0]["noteSnapshot"] == "Selected note"
        finally:
            await close_db()

    asyncio.run(run())
