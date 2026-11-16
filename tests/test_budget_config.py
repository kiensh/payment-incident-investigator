import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from src.agent.budget import BudgetExceeded, RequestBudget
from src.config import Settings


@pytest.mark.parametrize("scope", ["persistent", "session"])
def test_budget_survives_clients_and_counts_failed_requests(tmp_path: Path, scope):
    budget = RequestBudget(tmp_path / "ledger.sqlite", 2, scope)
    first = budget.reserve()
    budget.finish(first, "infrastructure_error", 12, {})
    second_client = RequestBudget(tmp_path / "ledger.sqlite", 2, scope)
    second_client.reserve()
    assert second_client.count() == 2
    with pytest.raises(BudgetExceeded):
        budget.reserve()


@pytest.mark.parametrize("scope", ["persistent", "session"])
def test_parallel_reservations_never_exceed_limit(tmp_path: Path, scope):
    path = tmp_path / "ledger.sqlite"
    budget = RequestBudget(path, 4, scope)

    def reserve():
        try:
            return RequestBudget(path, 4, scope).reserve()
        except BudgetExceeded:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: reserve(), range(12)))
    assert len([x for x in results if x is not None]) == budget.count() == 4


@pytest.mark.parametrize("url", ["https://api.example.com", "http://user:secret@localhost:8765", "http://localhost:8765/path", "file:///tmp/anything", "http://localhost:8765?key=oops", "http://localhost:notaport", "http://localhost:999999", "http://localhost:0", "http://@localhost:8765", "http://localhost:8765\n"])
def test_external_provider_and_embedded_credentials_rejected(url):
    with pytest.raises(ValueError):
        Settings(model_base_url=url)


def test_live_defaults_to_sonnet_but_rejects_empty_model_and_hides_secrets():
    assert Settings(mode="live").model_name == "claude-sonnet-5.5"
    with pytest.raises(ValueError, match="ANTHROPIC_MODEL"):
        Settings(mode="live", model_name="")
    assert "credential-test-value" not in repr(Settings(model_api_key="credential-test-value"))
    with pytest.raises(ValueError):
        Settings(request_limit=151)


@pytest.fixture
def config_env(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "environ", os.environ.copy())
    monkeypatch.setattr("src.config.ROOT", tmp_path)
    for name in ("INVESTIGATOR_MODE", "INVESTIGATOR_DB", "ANTHROPIC_BASE_URL",
                 "ANTHROPIC_MODEL", "ANTHROPIC_API_KEY", "INVESTIGATOR_BUDGET_PATH",
                 "INVESTIGATOR_BUDGET_SCOPE", "INVESTIGATOR_REQUEST_LIMIT",
                 "INVESTIGATOR_TIMEOUT_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.mark.parametrize("model,expected", [
    (None, "claude-sonnet-5.5"),
    ("claude-opus-5.5", "claude-opus-5.5"),
])
def test_live_environment_defaults_to_sonnet_and_allows_opus(config_env, model, expected):
    config_env.setenv("INVESTIGATOR_MODE", "live")
    if model is not None:
        config_env.setenv("ANTHROPIC_MODEL", model)
    assert Settings.from_env().model_name == expected


@pytest.mark.parametrize("model", ["", "   "])
def test_live_environment_rejects_explicitly_blank_model(config_env, model):
    config_env.setenv("INVESTIGATOR_MODE", "live")
    config_env.setenv("ANTHROPIC_MODEL", model)
    with pytest.raises(ValueError, match="ANTHROPIC_MODEL"):
        Settings.from_env()


def test_standard_model_and_application_environment_variables(config_env, tmp_path):
    values = {
        "INVESTIGATOR_MODE": "live",
        "INVESTIGATOR_DB": str(tmp_path / "evidence.sqlite"),
        "ANTHROPIC_BASE_URL": "http://127.0.0.1:9000/cc",
        "ANTHROPIC_MODEL": "configured-model-id",
        "ANTHROPIC_API_KEY": "synthetic-config-key",
        "INVESTIGATOR_BUDGET_PATH": str(tmp_path / "requests.sqlite"),
        "INVESTIGATOR_BUDGET_SCOPE": "session",
        "INVESTIGATOR_REQUEST_LIMIT": "12",
        "INVESTIGATOR_TIMEOUT_SECONDS": "30.5",
    }
    for name, value in values.items():
        config_env.setenv(name, value)
    settings = Settings.from_env()
    assert settings.mode == "live"
    assert settings.database == tmp_path / "evidence.sqlite"
    assert settings.model_base_url == values["ANTHROPIC_BASE_URL"]
    assert settings.model_name == values["ANTHROPIC_MODEL"]
    assert settings.model_api_key == values["ANTHROPIC_API_KEY"]
    assert settings.budget_path == tmp_path / "requests.sqlite"
    assert settings.budget_scope == "session"
    assert settings.request_limit == 12
    assert settings.request_timeout == 30.5
    assert values["ANTHROPIC_API_KEY"] not in repr(settings)


def test_dotenv_uses_standard_names_and_exported_values_win(config_env, tmp_path):
    (tmp_path / ".env").write_text(
        "INVESTIGATOR_MODE=live\n"
        "ANTHROPIC_BASE_URL=http://localhost:9000/cc\n"
        "ANTHROPIC_MODEL=dotenv-model\n"
        "ANTHROPIC_API_KEY=synthetic-dotenv-key\n"
        "INVESTIGATOR_REQUEST_LIMIT=10\n"
    )
    config_env.setenv("ANTHROPIC_MODEL", "exported-model")
    settings = Settings.from_env()
    assert settings.mode == "live"
    assert settings.model_base_url == "http://localhost:9000/cc"
    assert settings.model_name == "exported-model"
    assert settings.model_api_key == "synthetic-dotenv-key"
    assert settings.request_limit == 10


def test_renamed_settings_reuse_existing_default_request_ledger(config_env, tmp_path):
    path = tmp_path / "artifacts/bridge-budget.sqlite"
    RequestBudget(path, 150).reserve()
    settings = Settings.from_env()
    assert settings.mode == "mock"
    assert settings.model_base_url == "http://localhost:8765/cc"
    assert settings.model_name == "claude-sonnet-5.5"
    assert settings.model_api_key == ""
    assert settings.request_limit == 150
    assert settings.request_timeout == 60
    assert settings.budget_path == path
    assert settings.budget_scope == "persistent"
    assert RequestBudget(settings.budget_path, settings.request_limit).count() == 1


@pytest.mark.parametrize("name,value", [
    ("ANTHROPIC_BASE_URL", "https://api.example.com"),
    ("INVESTIGATOR_REQUEST_LIMIT", "151"),
    ("INVESTIGATOR_TIMEOUT_SECONDS", "121"),
    ("INVESTIGATOR_TIMEOUT_SECONDS", "nan"),
    ("INVESTIGATOR_BUDGET_SCOPE", "disabled"),
    ("INVESTIGATOR_BUDGET_SCOPE", ""),
])
def test_standard_environment_names_preserve_configuration_boundaries(config_env, name, value):
    config_env.setenv(name, value)
    with pytest.raises(ValueError):
        Settings.from_env()
