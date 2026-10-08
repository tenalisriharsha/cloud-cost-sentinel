"""Regenerate the dashboard screenshots (docs/screenshots/01-05) from a live app.

Starts ``streamlit run src/cloud_cost_sentinel/dashboard/app.py`` from the
repository root with no Slack webhook configured, opens it in headless
Chromium via Playwright, and captures each view. Every pixel comes from the
running app; nothing is edited afterwards.

Usage (from the repository root, after ``pip install -e ".[dev]"``)::

    pip install playwright && playwright install chromium
    python scripts/capture_dashboard_screenshots.py

Set ``CHROMIUM_PATH`` to use an already-installed Chromium instead.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOT_DIR = REPO_ROOT / "docs" / "screenshots"
APP_PATH = "src/cloud_cost_sentinel/dashboard/app.py"
PORT = 8599
URL = f"http://localhost:{PORT}"
VIEWPORT = {"width": 1280, "height": 800}


def wait_for_server(timeout_s: float = 60.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{URL}/_stcore/health", timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.5)
    raise TimeoutError(f"streamlit did not become healthy on {URL}")


def scroll_to(page, selector: str, offset_px: int) -> None:
    """Scroll the app's main container so ``selector`` sits ``offset_px`` below the top."""
    page.evaluate(
        """([selector, offset]) => {
            const el = document.querySelector(selector);
            const main = document.querySelector('[data-testid="stMain"]') || document.scrollingElement;
            const top = el.getBoundingClientRect().top - main.getBoundingClientRect().top + main.scrollTop;
            main.scrollTo(0, top - offset);
            window.scrollTo(0, top - offset);
        }""",
        [selector, offset_px],
    )
    page.wait_for_timeout(500)


def capture(page) -> None:
    page.goto(URL)
    page.wait_for_selector('[data-testid="stMetric"]', timeout=120_000)
    page.wait_for_function("document.querySelectorAll('.js-plotly-plot .main-svg').length >= 4", timeout=60_000)
    page.wait_for_timeout(2000)

    page.screenshot(path=SCREENSHOT_DIR / "02-metrics-and-trend.png")

    # Streamlit scrolls an inner container, so full_page=True only captures
    # one viewport; grow the viewport to the content height instead.
    content_height = page.evaluate("document.querySelector('[data-testid=\"stMain\"]').scrollHeight")
    page.set_viewport_size({"width": VIEWPORT["width"], "height": content_height})
    page.wait_for_timeout(1500)
    page.screenshot(path=SCREENSHOT_DIR / "01-overview.png")
    page.set_viewport_size(VIEWPORT)
    page.wait_for_timeout(1500)

    scroll_to(page, '[data-testid="stDataFrame"]', 100)
    page.screenshot(path=SCREENSHOT_DIR / "03-anomaly-detail.png")

    forecast_heading = page.get_by_role("heading", name="Forecast vs. budget")
    forecast_heading.evaluate("el => el.setAttribute('data-capture', 'forecast')")
    scroll_to(page, '[data-capture="forecast"]', 80)
    page.screenshot(path=SCREENSHOT_DIR / "04-forecast-vs-budget.png")

    page.locator('[data-testid="stExpander"] summary').first.click()
    page.wait_for_timeout(500)
    alerts_heading = page.get_by_role("heading", name="Alerts")
    alerts_heading.evaluate("el => el.setAttribute('data-capture', 'alerts')")
    scroll_to(page, '[data-capture="alerts"]', 360)
    page.screenshot(path=SCREENSHOT_DIR / "05-alerts.png")


def main() -> int:
    env = {key: value for key, value in os.environ.items() if key != "CCS_SLACK_WEBHOOK_URL"}
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            APP_PATH,
            "--server.headless",
            "true",
            "--server.port",
            str(PORT),
            "--browser.gatherUsageStats",
            "false",
        ],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_server()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH"))
            page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1)
            capture(page)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    print(f"wrote 01-05 to {SCREENSHOT_DIR.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
