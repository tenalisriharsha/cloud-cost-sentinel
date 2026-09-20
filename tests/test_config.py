import pytest

from cloud_cost_sentinel.config import get_settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in [
        "CCS_MONTHLY_BUDGET_USD",
        "CCS_ANOMALY_Z_THRESHOLD",
        "CCS_SLACK_WEBHOOK_URL",
        "CCS_SAMPLE_DATA_DIR",
    ]:
        monkeypatch.delenv(var, raising=False)


def test_default_settings_have_sane_values():
    settings = get_settings()
    assert settings.monthly_budget_usd == 1000.0
    assert settings.anomaly_z_threshold == 3.0
    assert settings.currency == "USD"
    assert settings.slack_webhook_url is None


def test_settings_read_from_environment(monkeypatch):
    monkeypatch.setenv("CCS_MONTHLY_BUDGET_USD", "5000")
    monkeypatch.setenv("CCS_SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T000/B000/XXXX")

    settings = get_settings()
    assert settings.monthly_budget_usd == 5000.0
    assert settings.slack_webhook_url == "https://hooks.slack.com/services/T000/B000/XXXX"


def test_monthly_budget_must_be_positive(monkeypatch):
    monkeypatch.setenv("CCS_MONTHLY_BUDGET_USD", "0")
    with pytest.raises(ValueError):
        get_settings()
