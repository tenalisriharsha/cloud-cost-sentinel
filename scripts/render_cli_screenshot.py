"""Regenerate docs/screenshots/06-cli-pipeline.png from a real ``ccs`` run.

Runs ``ccs`` from the repository root with no Slack webhook configured,
captures its combined stdout/stderr, and draws the prompt line plus that
output, unedited, as a terminal-style image. Nothing in the image is typed
by hand: the command shown is the command that ran.

Usage (from the repository root, after ``pip install -e ".[dev]"``)::

    python scripts/render_cli_screenshot.py

Uses Pillow and matplotlib's bundled DejaVu Sans Mono, both already
installed by the ``forecast`` extra.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "docs" / "screenshots" / "06-cli-pipeline.png"
COMMAND = ["ccs"]
MAX_OUTPUT_LINES = 40

FONT_SIZE = 15
PADDING = 20
TITLE_BAR_HEIGHT = 34
BACKGROUND = "#1e1f22"
TITLE_BAR = "#2b2d31"
FOREGROUND = "#dcdcdc"
PROMPT = "#6cb6ff"
TITLE_TEXT = "#9a9a9a"


def run_command() -> tuple[list[str], int]:
    env = {key: value for key, value in os.environ.items() if key != "CCS_SLACK_WEBHOOK_URL"}
    completed = subprocess.run(
        COMMAND,
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    lines = completed.stdout.rstrip("\n").split("\n")
    if len(lines) > MAX_OUTPUT_LINES:
        lines = [*lines[:MAX_OUTPUT_LINES], "... (output truncated)"]
    return lines, completed.returncode


def render(output_lines: list[str]) -> Image.Image:
    font = ImageFont.truetype(font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans Mono")), FONT_SIZE)
    prompt_line = "$ " + " ".join(COMMAND)
    all_lines = [prompt_line, *output_lines]

    line_height = int(FONT_SIZE * 1.5)
    text_width = max(font.getlength(line) for line in all_lines)
    width = int(text_width) + 2 * PADDING
    height = TITLE_BAR_HEIGHT + 2 * PADDING + line_height * len(all_lines)

    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width, TITLE_BAR_HEIGHT], fill=TITLE_BAR)
    for i, color in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        x = PADDING + i * 20
        draw.ellipse([x, 11, x + 12, 23], fill=color)
    title = f"{REPO_ROOT.name} — {prompt_line}"
    draw.text(((width - font.getlength(title)) / 2, 9), title, font=font, fill=TITLE_TEXT)

    y = TITLE_BAR_HEIGHT + PADDING
    draw.text((PADDING, y), "$ ", font=font, fill=PROMPT)
    draw.text((PADDING + font.getlength("$ "), y), " ".join(COMMAND), font=font, fill=FOREGROUND)
    for line in output_lines:
        y += line_height
        draw.text((PADDING, y), line, font=font, fill=FOREGROUND)
    return image


def main() -> int:
    output_lines, returncode = run_command()
    if returncode != 0:
        print("\n".join(output_lines), file=sys.stderr)
        print(f"{' '.join(COMMAND)} exited {returncode}; not writing a screenshot", file=sys.stderr)
        return 1
    render(output_lines).save(OUTPUT_PATH)
    print(f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
