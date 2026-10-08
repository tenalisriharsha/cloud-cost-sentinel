from datetime import date

import pytest

from cloud_cost_sentinel.alerting.slack import AlertThrottle
from cloud_cost_sentinel.cli import (
    DEFAULT_ANOMALY_DATA_PATH,
    DEFAULT_FORECAST_DATA_PATH,
    build_arg_parser,
    format_report,
    main,
    run_pipeline,
)
from cloud_cost_sentinel.config import Settings


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


@pytest.fixture
def no_webhook_settings() -> Settings:
    return Settings(slack_webhook_url=None)


def test_default_fixtures_exist():
    assert DEFAULT_ANOMALY_DATA_PATH.exists()
    assert DEFAULT_FORECAST_DATA_PATH.exists()


def test_run_pipeline_end_to_end_against_sample_fixtures(no_webhook_settings):
    result = run_pipeline(settings=no_webhook_settings)

    assert any(a.service == "AmazonEC2" and a.usage_date == date(2026, 8, 6) for a in result.anomalies)
    assert len(result.forecast) == no_webhook_settings.forecast_horizon_days
    assert result.drift.forecast_total_usd > 0

    # No webhook configured, so every alert is skipped rather than sent.
    assert result.alerts_sent == []
    assert len(result.alerts_skipped) >= 1


def test_run_pipeline_sends_alerts_via_injected_webhook_client(no_webhook_settings):
    client = _FakeWebhookClient(status_code=200)
    result = run_pipeline(settings=no_webhook_settings, webhook_client=client)

    assert len(result.alerts_sent) >= 1
    assert result.alerts_skipped == []
    assert len(client.calls) == len(result.alerts_sent)


def test_run_pipeline_throttle_dedupes_across_repeated_runs(no_webhook_settings):
    client = _FakeWebhookClient(status_code=200)
    throttle = AlertThrottle()

    first = run_pipeline(settings=no_webhook_settings, webhook_client=client, throttle=throttle)
    second = run_pipeline(settings=no_webhook_settings, webhook_client=client, throttle=throttle)

    assert len(first.alerts_sent) >= 1
    assert second.alerts_sent == []
    assert len(second.alerts_skipped) == len(first.alerts_sent)


def test_format_report_includes_key_sections(no_webhook_settings):
    result = run_pipeline(settings=no_webhook_settings)
    report = format_report(result)

    assert "Anomalies detected:" in report
    assert "AmazonEC2" in report
    assert "Forecast:" in report
    assert "Budget:" in report
    assert "Alerts sent:" in report


def test_build_arg_parser_defaults_to_sample_fixtures():
    args = build_arg_parser().parse_args([])
    assert args.anomaly_data == DEFAULT_ANOMALY_DATA_PATH
    assert args.forecast_data == DEFAULT_FORECAST_DATA_PATH


def test_main_prints_report_and_returns_zero(capsys, monkeypatch):
    monkeypatch.delenv("CCS_SLACK_WEBHOOK_URL", raising=False)
    exit_code = main([])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Cloud Cost Sentinel" in captured.out


def test_main_reports_missing_file_without_traceback(capsys, tmp_path):
    missing = tmp_path / "nope.csv"
    exit_code = main(["--anomaly-data", str(missing)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"ccs: error: CUR file not found: {missing}" in captured.err
    assert "repository root" not in captured.err


def test_main_hints_at_repo_root_when_default_fixture_is_missing(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    exit_code = main([])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert f"CUR file not found: {DEFAULT_ANOMALY_DATA_PATH}" in captured.err
    assert "relative to the repository root" in captured.err


def test_main_reports_malformed_cur_file_without_traceback(capsys, tmp_path):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("a,b\n1,2\n")
    exit_code = main(["--anomaly-data", str(bad_csv)])

    assert exit_code == 1
    assert "ccs: error: CUR file is missing required columns" in capsys.readouterr().err


def test_main_reports_too_short_forecast_history_without_traceback(capsys):
    exit_code = main(["--forecast-data", str(DEFAULT_ANOMALY_DATA_PATH)])

    assert exit_code == 1
    assert "ccs: error: Need at least 14 days of cost history to forecast, got 10." in capsys.readouterr().err


def test_format_report_labels_unsent_alerts_accurately(no_webhook_settings):
    report = format_report(run_pipeline(settings=no_webhook_settings))
    assert "Alerts not sent (throttled, no webhook configured, or send failed): 2" in report
