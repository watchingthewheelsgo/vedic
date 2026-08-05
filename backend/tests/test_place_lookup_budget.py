from __future__ import annotations

import pytest

from app.services.place_lookup_budget import PlaceLookupBudget, PlaceLookupRateLimitError


def test_place_lookup_budget_limits_each_client_and_releases_concurrency() -> None:
    budget = PlaceLookupBudget(limit=1, window_seconds=60, max_concurrent=1)

    budget.acquire("client-a")
    with pytest.raises(PlaceLookupRateLimitError):
        budget.acquire("client-a")
    budget.release()

    # The request window still applies after the in-flight slot is released.
    with pytest.raises(PlaceLookupRateLimitError):
        budget.acquire("client-a")


def test_place_lookup_budget_does_not_share_request_windows_between_clients() -> None:
    budget = PlaceLookupBudget(limit=1, window_seconds=60, max_concurrent=2)

    budget.acquire("client-a")
    budget.acquire("client-b")
    budget.release()
    budget.release()
