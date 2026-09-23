from datetime import date

import pytest

from cloud_cost_sentinel.alerting.slack import (
    AlertThrottle,
    format_anomaly_alert,
    format_budget_drift_alert,
    send_alert,
)
from cloud_cost_sentinel.config import Settings
from cloud_cost_sentinel.models import Anomaly, BudgetDrift


class _FakeWebhookResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeWebhookClient:
    """Records every ``send`` call instead of hitting the network."""

    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.calls: list[str] = []

    def send(self, *, text: str) -> _FakeWebhookResponse:
        self.calls.append(text)
        return _FakeWebhookResponse(self.status_code)


def _anomaly() -> Anomaly:
    return Anomaly(
        service="AmazonEC2",
        usage_date=date(2026, 8, 6),
        actual_cost=187.44,
        expected_cost=42.10,
        score=4.2,
        method="rolling_iqr",
    )


def _budget_drift() -> BudgetDrift:
    return BudgetDrift(
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        forecast_total_usd=1200.0,
        budget_usd=1000.0,
        drift_usd=200.0,
        drift_pct=20.0,
        over_budget=True,
    )


def test_format_anomaly_alert_includes_key_fields():
    alert = format_anomaly_alert(_anomaly())
    assert alert.source == "anomaly"
    assert alert.dedup_key == "anomaly:AmazonEC2:2026-08-06:rolling_iqr"
    assert "AmazonEC2" in alert.message
    assert "187.44" in alert.message
    assert "42.10" in alert.message
    assert "rolling_iqr" in alert.message


def test_format_budget_drift_alert_includes_key_fields():
    alert = format_budget_drift_alert(_budget_drift())
    assert alert.source == "budget_drift"
    assert alert.dedup_key == "budget_drift:2026-09-01:2026-09-30"
    assert "1,200.00" in alert.message
    assert "1,000.00" in alert.message
    assert "20.0%" in alert.message


def test_alert_throttle_allows_first_send_and_blocks_repeat():
    throttle = AlertThrottle()
    alert = format_anomaly_alert(_anomaly())

    assert throttle.should_send(alert) is True
    throttle.mark_sent(alert)
    assert throttle.should_send(alert) is False


def test_alert_throttle_distinguishes_different_dedup_keys():
    throttle = AlertThrottle()
    anomaly_alert = format_anomaly_alert(_anomaly())
    drift_alert = format_budget_drift_alert(_budget_drift())

    throttle.mark_sent(anomaly_alert)

    assert throttle.should_send(drift_alert) is True


def test_send_alert_posts_message_and_returns_true_on_success():
    client = _FakeWebhookClient(status_code=200)
    alert = format_anomaly_alert(_anomaly())

    result = send_alert(alert, webhook_client=client)

    assert result is True
    assert client.calls == [alert.message]


def test_send_alert_returns_false_on_non_200_response():
    client = _FakeWebhookClient(status_code=500)
    alert = format_anomaly_alert(_anomaly())

    result = send_alert(alert, webhook_client=client)

    assert result is False


def test_send_alert_returns_false_without_network_call_when_no_webhook_configured():
    alert = format_anomaly_alert(_anomaly())
    settings = Settings(slack_webhook_url=None)

    result = send_alert(alert, settings=settings)

    assert result is False


def test_send_alert_respects_throttle_and_skips_network_call():
    client = _FakeWebhookClient(status_code=200)
    alert = format_anomaly_alert(_anomaly())
    throttle = AlertThrottle()
    throttle.mark_sent(alert)

    result = send_alert(alert, throttle=throttle, webhook_client=client)

    assert result is False
    assert client.calls == []


def test_send_alert_marks_throttle_only_after_successful_send():
    client = _FakeWebhookClient(status_code=200)
    alert = format_anomaly_alert(_anomaly())
    throttle = AlertThrottle()

    result = send_alert(alert, throttle=throttle, webhook_client=client)

    assert result is True
    assert throttle.should_send(alert) is False


def test_send_alert_does_not_mark_throttle_on_failed_send():
    client = _FakeWebhookClient(status_code=500)
    alert = format_anomaly_alert(_anomaly())
    throttle = AlertThrottle()

    result = send_alert(alert, throttle=throttle, webhook_client=client)

    assert result is False
    assert throttle.should_send(alert) is True


def test_send_alert_uses_real_webhook_client_when_configured(monkeypatch):
    """When no ``webhook_client`` is injected, ``send_alert`` should build a
    real ``slack_sdk`` ``WebhookClient`` from ``Settings.slack_webhook_url``.

    Patches the class inside the ``slack_sdk.webhook`` module (where
    ``send_alert`` imports it from), not inside this module's namespace.
    """
    created_with = {}

    class _PatchedClient:
        def __init__(self, url: str) -> None:
            created_with["url"] = url

        def send(self, *, text: str) -> _FakeWebhookResponse:
            created_with["text"] = text
            return _FakeWebhookResponse(200)

    monkeypatch.setattr("slack_sdk.webhook.WebhookClient", _PatchedClient)
    alert = format_anomaly_alert(_anomaly())
    settings = Settings(slack_webhook_url="https://hooks.slack.example/T000/B000/xyz")

    result = send_alert(alert, settings=settings)

    assert result is True
    assert created_with["url"] == "https://hooks.slack.example/T000/B000/xyz"
    assert created_with["text"] == alert.message


def test_alerting_package_exposes_public_api():
    import cloud_cost_sentinel.alerting as alerting

    assert alerting.format_anomaly_alert is format_anomaly_alert
    assert alerting.format_budget_drift_alert is format_budget_drift_alert
    assert alerting.send_alert is send_alert
    assert alerting.AlertThrottle is AlertThrottle


@pytest.mark.parametrize("over_budget", [True, False])
def test_format_budget_drift_alert_handles_both_directions(over_budget):
    drift = BudgetDrift(
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        forecast_total_usd=800.0 if not over_budget else 1200.0,
        budget_usd=1000.0,
        drift_usd=-200.0 if not over_budget else 200.0,
        drift_pct=-20.0 if not over_budget else 20.0,
        over_budget=over_budget,
    )
    alert = format_budget_drift_alert(drift)
    assert alert.source == "budget_drift"
