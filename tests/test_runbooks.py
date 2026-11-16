from pathlib import Path

from src.tools.runbooks import RUNBOOK_DIR, RunbookStore


def test_exact_category_keyword_and_unknown_retrieval():
    store = RunbookStore()
    assert store.retrieve("webhook-evidence")[0].id == "webhook-evidence"
    assert store.retrieve("authorization")[0].id == "payment-state"
    assert store.retrieve("timestamp missing")[0].id == "evidence-gaps"
    assert store.retrieve("zzzzzzzz") == []
    assert len(store.retrieve("payment webhook support missing", limit=1)) == 1


def test_content_hash_invalidates_parsed_runbook_cache(tmp_path: Path):
    target = tmp_path / "payment-state.yaml"
    original = (RUNBOOK_DIR / target.name).read_text()
    target.write_text(original)
    store = RunbookStore(tmp_path)
    initial_version = store.retrieve("payment-state")[0].version
    updated_version = initial_version + "-cache-test"
    changed = original.replace(f"version: '{initial_version}'", f"version: '{updated_version}'")
    assert changed != original
    target.write_text(changed)
    assert store.retrieve("payment-state")[0].version == updated_version
    assert store.retrieve("payment-state")[0].version == updated_version
    assert store.cache_hits >= 1


def test_all_runbooks_have_operational_fields_and_sources():
    books = RunbookStore().retrieve("payment webhook missing support", limit=4)
    assert len(books) == 4
    for book in books:
        assert book.applicability and book.steps and book.required_evidence
        assert book.supported_conclusions and book.escalation and book.version
        assert any(source.startswith("https://docs.stripe.com/") for source in book.sources)
        assert any(source.startswith("Demo policy") for source in book.sources)
