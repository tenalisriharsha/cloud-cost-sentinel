"""Format anomalies and budget drift into Slack alerts, and post them.

Formatting (:func:`format_anomaly_alert`, :func:`format_budget_drift_alert`)
is pure and has no Slack dependency. Sending (:func:`send_alert`) is the only
piece that talks to Slack, and does so through `slack_sdk`'s
``WebhookClient``, imported lazily so the `alerts` extra stays optional for
callers that only need formatting or throttling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cloud_cost_sentinel.config import Settings, get_settings
from cloud_cost_sentinel.models import Anomaly, BudgetAlert, BudgetDrift

if TYPE_CHECKING:
    from slack_sdk.webhook import WebhookClient


def format_anomaly_alert(anomaly: Anomaly) -> BudgetAlert:
    """Build a :class:`BudgetAlert` message for a single flagged anomaly."""
    dedup_key = f"anomaly:{anomaly.service}:{anomaly.usage_date}:{anomaly.method}"
    message = (
        f":rotating_light: *Cost anomaly detected* — `{anomaly.service}` on {anomaly.usage_date}\n"
        f"Actual: ${anomaly.actual_cost:,.2f}  |  Expected: ${anomaly.expected_cost:,.2f}  |  "
        f"Score: {anomaly.score:.2f}  |  Method: `{anomaly.method}`"
    )
    return BudgetAlert(source="anomaly", dedup_key=dedup_key, message=message)


def format_budget_drift_alert(drift: BudgetDrift) -> BudgetAlert:
    """Build a :class:`BudgetAlert` message for a forecasted budget drift.

    Formats regardless of direction; callers should check
    ``drift.over_budget`` before calling this, since a routine under-budget
    forecast isn't a page-worthy event.
    """
    dedup_key = f"budget_drift:{drift.period_start}:{drift.period_end}"
    message = (
        f":rotating_light: *Budget drift forecast* — {drift.period_start} to {drift.period_end}\n"
        f"Forecasted spend: ${drift.forecast_total_usd:,.2f}  |  Budget: ${drift.budget_usd:,.2f}  |  "
        f"Over by {drift.drift_pct:.1f}% (${drift.drift_usd:,.2f})"
    )
    return BudgetAlert(source="budget_drift", dedup_key=dedup_key, message=message)


class AlertThrottle:
    """In-memory dedup store so the same alert condition isn't re-sent on
    every run.

    Keyed on :attr:`BudgetAlert.dedup_key` (service/date/method for
    anomalies, forecast period for budget drift). There's no persistence
    layer yet, so a throttle only lives as long as the process holding it.
    """

    def __init__(self) -> None:
        self._sent_keys: set[str] = set()

    def should_send(self, alert: BudgetAlert) -> bool:
        return alert.dedup_key not in self._sent_keys

    def mark_sent(self, alert: BudgetAlert) -> None:
        self._sent_keys.add(alert.dedup_key)


def send_alert(
    alert: BudgetAlert,
    *,
    throttle: AlertThrottle | None = None,
    settings: Settings | None = None,
    webhook_client: "WebhookClient | None" = None,
) -> bool:
    """Post ``alert`` to the configured Slack webhook.

    Returns ``False`` without making a network call if ``throttle`` says
    this ``dedup_key`` was already sent, or if no webhook is configured
    (neither ``webhook_client`` nor ``Settings.slack_webhook_url``).
    Returns ``True`` once the webhook call succeeds, and records the send
    with ``throttle`` if one was given.
    """
    if throttle is not None and not throttle.should_send(alert):
        return False

    if webhook_client is None:
        resolved_settings = settings or get_settings()
        if not resolved_settings.slack_webhook_url:
            return False
        from slack_sdk.webhook import WebhookClient as _WebhookClient

        webhook_client = _WebhookClient(resolved_settings.slack_webhook_url)

    response = webhook_client.send(text=alert.message)
    sent = response.status_code == 200
    if sent and throttle is not None:
        throttle.mark_sent(alert)
    return sent
