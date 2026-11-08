"""Regression tests for issue #6.

Dependencies in pyproject.toml are declared with lower bounds only
(e.g. ``pandas>=2.2``) and there is no lock/constraints file, so CI
installs whatever the newest compatible release is on any given day.
An upstream release can turn CI red with no code change, and the
floor versions the project claims to support are never actually
exercised. These tests check the two "done when" criteria from the
issue: CI installs are pinned/reproducible, and a job tests the
declared minimum versions.
"""

from __future__ import annotations

import pathlib
import re
import tomllib

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

_IGNORED_DIR_PARTS = {".git", ".venv", "node_modules", ".pytest_cache", ".ruff_cache", "__pycache__"}

_LOCKFILE_NAMES = {
    "uv.lock",
    "poetry.lock",
    "requirements.lock",
    "requirements-lock.txt",
    "constraints.txt",
    "constraints-ci.txt",
    "Pipfile.lock",
}


def _core_dependency_floors() -> dict[str, str]:
    data = tomllib.loads(PYPROJECT.read_text())
    floors = {}
    for spec in data["project"]["dependencies"]:
        match = re.match(r"^([A-Za-z0-9_.-]+)\s*>=\s*([0-9][0-9A-Za-z.]*)", spec)
        assert match, f"unexpected dependency spec format: {spec!r}"
        name, version = match.groups()
        floors[name.lower()] = version
    return floors


def _workflow_files() -> list[pathlib.Path]:
    if not WORKFLOWS_DIR.is_dir():
        return []
    return sorted(WORKFLOWS_DIR.glob("*.yml")) + sorted(WORKFLOWS_DIR.glob("*.yaml"))


def _repo_files_named(names: set[str]) -> list[pathlib.Path]:
    found = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if set(path.relative_to(REPO_ROOT).parts) & _IGNORED_DIR_PARTS:
            continue
        if path.name in names:
            found.append(path)
    return found


def _referenced_file_contents(run_text: str) -> str:
    contents = []
    for token in re.findall(r"[\w./-]+\.(?:txt|lock|cfg)", run_text):
        candidate = REPO_ROOT / token
        if candidate.is_file():
            contents.append(candidate.read_text())
    return "\n".join(contents)


def test_ci_installs_are_pinned_via_a_lock_or_constraints_file():
    lock_files = _repo_files_named(_LOCKFILE_NAMES)
    assert lock_files, (
        "expected a committed lock/constraints file (e.g. constraints.txt or "
        "uv.lock) pinning dependency versions, so CI installs are reproducible "
        "instead of picking up whatever is newest on the day the job runs"
    )

    workflows = _workflow_files()
    assert workflows, "expected at least one GitHub Actions workflow"

    referenced = any(
        lock.name in wf.read_text() for wf in workflows for lock in lock_files
    )
    assert referenced, (
        "a lock/constraints file exists but no CI workflow step installs "
        "against it, so dependency resolution in CI is still unpinned"
    )


def test_a_min_versions_job_installs_and_tests_the_declared_floors():
    floors = _core_dependency_floors()
    assert floors, "expected at least one core dependency with a '>=' floor"

    workflows = _workflow_files()
    assert workflows, "expected at least one GitHub Actions workflow"

    min_job_found = False
    for wf in workflows:
        workflow = yaml.safe_load(wf.read_text())
        for job in workflow.get("jobs", {}).values():
            steps = job.get("steps", [])
            run_text = "\n".join(
                step.get("run", "") for step in steps if isinstance(step, dict)
            )
            combined = run_text + "\n" + _referenced_file_contents(run_text)
            pins_all_floors = all(
                re.search(rf"{re.escape(name)}\s*==\s*{re.escape(version)}", combined, re.IGNORECASE)
                for name, version in floors.items()
            )
            runs_tests = "pytest" in combined
            if pins_all_floors and runs_tests:
                min_job_found = True

    assert min_job_found, (
        "expected a CI job that installs every core dependency pinned to its "
        "declared floor version (e.g. pandas==2.2) and then runs the test "
        "suite against those minimum versions"
    )
