"""Format anomalies and budget drift into Slack alerts, and post them.

Formatting (:func:`format_anomaly_alert`, :func:`format_budget_drift_alert`)
is pure and has no Slack dependency. Sending (:func:`send_alert`) is the only
piece that talks to Slack, and does so through `slack_sdk`'s
``WebhookClient``, imported lazily so the `alerts` extra stays optional for
callers that only need formatting or throttling.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from cloud_cost_sentinel.config import Settings, get_settings
from cloud_cost_sentinel.models import Anomaly, BudgetAlert, BudgetDrift

if TYPE_CHECKING:
    from slack_sdk.webhook import WebhookClient

logger = logging.getLogger(__name__)

DEFAULT_THROTTLE_TTL_SECONDS = 86400.0


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

    There is one configured budget forecast, so its dedup key stays stable
    as the rolling window changes; the throttle TTL controls re-paging.
    """
    dedup_key = "budget_drift"
    message = (
        f":rotating_light: *Budget drift forecast* — {drift.period_start} to {drift.period_end}\n"
        f"Forecasted spend: ${drift.forecast_total_usd:,.2f}  |  Budget: ${drift.budget_usd:,.2f}  |  "
        f"Over by {drift.drift_pct:.1f}% (${drift.drift_usd:,.2f})"
    )
    return BudgetAlert(source="budget_drift", dedup_key=dedup_key, message=message)


class AlertThrottle:
    """Dedup store so the same alert condition isn't re-sent within a TTL
    window.

    Keyed on :attr:`BudgetAlert.dedup_key` (service/date/method for
    anomalies, the stable ``budget_drift`` key for the configured forecast).
    With no ``path``, state is in-memory only and lives as long as the
    process holding it — fine for tests and one-off scripts. Pass ``path``
    to persist the dedup keys and their last-sent timestamps as JSON, so a
    scheduled `ccs` run picks
    up where the previous one left off instead of re-paging on every
    invocation; a key stops being throttled once ``ttl_seconds`` have
    passed since it was last sent.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        ttl_seconds: float = DEFAULT_THROTTLE_TTL_SECONDS,
    ) -> None:
        self._path = Path(path) if path is not None else None
        self._ttl_seconds = ttl_seconds
        self._sent_at: dict[str, float] = self._load()

    def _load(self) -> dict[str, float]:
        if self._path is None or not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text())
        except (OSError, ValueError):
            logger.warning("Could not read throttle state from %s; starting fresh", self._path)
            return {}
        if not isinstance(raw, dict):
            return {}
        return {str(key): float(value) for key, value in raw.items() if isinstance(value, (int, float))}

    def _save(self) -> None:
        if self._path is None:
            return
        now = time.time()
        live = {key: sent_at for key, sent_at in self._sent_at.items() if now - sent_at < self._ttl_seconds}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(live))

    def should_send(self, alert: BudgetAlert) -> bool:
        sent_at = self._sent_at.get(alert.dedup_key)
        if sent_at is None:
            return True
        return time.time() - sent_at >= self._ttl_seconds

    def mark_sent(self, alert: BudgetAlert) -> None:
        self._sent_at[alert.dedup_key] = time.time()
        self._save()


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
    with ``throttle`` if one was given. A non-200 response, an unreachable
    webhook, or a malformed webhook URL logs a warning and returns
    ``False`` rather than raising, so one failed send doesn't abort the
    remaining alerts.
    """
    if throttle is not None and not throttle.should_send(alert):
        return False

    if webhook_client is None:
        resolved_settings = settings or get_settings()
        if not resolved_settings.slack_webhook_url:
            return False
        from slack_sdk.webhook import WebhookClient as _WebhookClient

        webhook_client = _WebhookClient(resolved_settings.slack_webhook_url)

    try:
        response = webhook_client.send(text=alert.message)
    except (OSError, ValueError) as exc:
        logger.warning("Slack alert %s failed to send: %s", alert.dedup_key, exc)
        return False
    sent = response.status_code == 200
    if not sent:
        logger.warning("Slack alert %s was rejected with HTTP %s", alert.dedup_key, response.status_code)
    if sent and throttle is not None:
        throttle.mark_sent(alert)
    return sent
