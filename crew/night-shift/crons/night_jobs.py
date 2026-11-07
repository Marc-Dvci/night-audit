"""The night shift's two Crew script crons.

Crew imports this file in a subprocess and calls one function with a ``ctx``. ``ctx.job.message`` is the job's
message, and here it holds the operator's settings as JSON:

    {"checkout": "<absolute path of the checkout>"}

The operator changes it without editing the bundle: ``kirocrew cron update <job-id> --message '<json>'``.

A function that returns, or raises ``Report``, is a successful run; Crew records the ``Report`` text as the run's
result. Any other exception is a failed run, and Crew records its text as the run's error. ``Done`` is never raised:
Crew removes the job after it.

Each job runs ``uv run --directory <checkout> python scripts/<job>.py`` as an argument list, never through a shell,
with its own time limit inside the one Crew enforces, so a slow run ends with a clear line instead of Crew's kill.
The child inherits the gateway's environment; ``AWS_PROFILE`` comes from there.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

try:  # inside Crew's launcher
    from kiro_crew.cron_script import Report
except ImportError:  # unit tests, where Crew is not installed

    class Report(Exception):  # type: ignore[no-redef]  # noqa: N818 - Crew's name
        """Stand-in for ``kiro_crew.cron_script.Report``: a successful run that carries a message."""

        def __init__(self, message: str = "") -> None:
            super().__init__(message)
            self.message = message


#: Seconds the audit subprocess may run. The manifest gives Crew 1500 s for the script and 1560 s for the run.
NIGHTLY_TIMEOUT = 1440
#: Seconds the notes subprocess may run. The manifest gives Crew 3600 s for the script and 3660 s for the run.
NOTES_TIMEOUT = 3540
#: The notes job asks at most this many findings, each within this many seconds: 12 x 240 s = 2880 s < 3540 s.
NOTES_LIMIT = 12
NOTES_PER_FINDING = 240
#: Characters of the child's output kept in the recorded result or error.
TAIL = 1500

Run = Callable[..., Any]


class JobFailed(Exception):
    """A run that failed. The text is one line that says why."""


def checkout_from(message: str) -> Path:
    """The Night Audit checkout named in the job's message, or ``JobFailed`` with one line."""
    try:
        settings = json.loads(message or "")
    except json.JSONDecodeError:
        settings = None
    if not isinstance(settings, dict) or not isinstance(settings.get("checkout"), str):
        raise JobFailed(
            'the job message must be JSON like {"checkout": "<absolute path of the Night Audit checkout>"}; '
            "set it with: kirocrew cron update <job-id> --message '<json>'"
        )
    checkout = Path(settings["checkout"])
    if not checkout.is_absolute():
        raise JobFailed(f"checkout {str(checkout)!r} is not an absolute path")
    if not (checkout / "scripts" / "nightly.py").is_file() or not (checkout / "pyproject.toml").is_file():
        raise JobFailed(f"checkout {str(checkout)!r} is not a Night Audit checkout (no scripts/nightly.py)")
    return checkout


def tail(text: str) -> str:
    text = (text or "").strip()
    return text if len(text) <= TAIL else "..." + text[-TAIL:]


def run_uv(checkout: Path, script: Sequence[str], timeout: int, run: Run = subprocess.run) -> str:
    """Run ``uv run --directory <checkout> python <script...>``; return its output, or raise ``JobFailed``."""
    uv = shutil.which("uv")
    if uv is None:
        raise JobFailed("uv is not on the gateway's PATH")
    argv = [uv, "run", "--directory", str(checkout), "python", *script]
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}  # the gateway's own venv, not the checkout's
    try:
        done = run(  # noqa: S603 - an argument list, no shell
            argv,
            cwd=str(checkout),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise JobFailed(f"{script[0]} did not finish within {timeout} s") from exc
    except OSError as exc:
        raise JobFailed(f"cannot start uv: {exc}") from exc
    output = (done.stdout or "") + (("\n" + done.stderr) if done.stderr else "")
    if done.returncode != 0:
        raise JobFailed(f"{script[0]} exited with code {done.returncode}: {tail(output)}")
    return tail(output)


def profile_args() -> list[str]:
    profile = os.environ.get("AWS_PROFILE")
    return ["--profile", profile] if profile else []


def nightly(ctx: Any, run: Run = subprocess.run) -> None:
    """The 02:00 job: ``scripts/nightly.py`` runs ``nightaudit run`` for each control."""
    checkout = checkout_from(ctx.job.message)
    output = run_uv(checkout, ["scripts/nightly.py", "--runs", "runs"], NIGHTLY_TIMEOUT, run)
    raise Report(f"nightly.py finished in {checkout}:\n{output}")


def notes(ctx: Any, run: Run = subprocess.run) -> None:
    """The 02:30 job: ``scripts/night_shift.py`` asks the investigator about the newest run and records checked notes.

    Exit code 2 from night_shift.py means Kiro was unavailable for at least one finding. Nothing was written for those
    findings, the run is unchanged, and the job reports it as a failed run so the operator sees it.
    """
    checkout = checkout_from(ctx.job.message)
    script = [
        "scripts/night_shift.py",
        "--runs",
        "runs",
        "--limit",
        str(NOTES_LIMIT),
        "--timeout",
        str(NOTES_PER_FINDING),
        *profile_args(),
    ]
    output = run_uv(checkout, script, NOTES_TIMEOUT, run)
    raise Report(f"night_shift.py finished in {checkout}:\n{output}")
