from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from src.agent.budget import BudgetExceeded, RequestBudget
from src.config import Settings


def test_budget_survives_clients_and_counts_failed_requests(tmp_path: Path):
    budget = RequestBudget(tmp_path / "ledger.sqlite", 2)
    first = budget.reserve()
    budget.finish(first, "infrastructure_error", 12, {})
    second_client = RequestBudget(tmp_path / "ledger.sqlite", 2)
    second_client.reserve()
    assert second_client.count() == 2
    with pytest.raises(BudgetExceeded):
        budget.reserve()


def test_parallel_reservations_never_exceed_limit(tmp_path: Path):
    path = tmp_path / "ledger.sqlite"
    budget = RequestBudget(path, 4)

    def reserve():
        try:
            return RequestBudget(path, 4).reserve()
        except BudgetExceeded:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: reserve(), range(12)))
    assert len([x for x in results if x is not None]) == budget.count() == 4


@pytest.mark.parametrize("url", ["https://api.example.com", "http://user:secret@localhost:8765", "http://localhost:8765/path", "file:///tmp/anything", "http://localhost:8765?key=oops"])
def test_external_provider_and_embedded_credentials_rejected(url):
    with pytest.raises(ValueError):
        Settings(bridge_url=url)


def test_live_requires_discovered_model_and_secret_is_not_repr():
    with pytest.raises(ValueError):
        Settings(mode="live")
    assert "credential-test-value" not in repr(Settings(bridge_token="credential-test-value"))
    with pytest.raises(ValueError):
        Settings(request_limit=151)
