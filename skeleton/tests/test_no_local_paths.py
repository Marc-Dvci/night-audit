"""No tracked text file names a folder on the machine it was written on: a Windows drive path or a home folder.

A checkout is written ``<checkout>``. A test may name such a path as an example input, and the container's own user
home (``/home/audit``, made by the Dockerfile) is not a local folder. ``casebook/heldout/`` is sealed and not read.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SEALED = "casebook/heldout/"
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".woff", ".woff2", ".ttf", ".ico", ".pdf", ".zip", ".gz", ".mp4"}

#: ``D:\Devpost``, ``C:/Users``, ``D:\...``: a drive letter not inside a word, a colon and a slash.
DRIVE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:(?:\\\\|\\|/)(?=[^\s\"'`)]|$)")
#: A home folder: ``/home/<name>``, ``/Users/<name>``, ``C:\Users\<name>``. Case matters: ``api.github.com/users/x`` is
#: a URL.
HOME = re.compile(r"(?<![\w.])/home/(?!audit/)\w|(?<![\w.])/Users/\w|\\Users\\\w")


def local_paths(text: str) -> list[str]:
    """Each line of *text* that names a drive path or a home folder, as ``<line>: <text>``."""
    return [
        f"{n}: {line.strip()[:120]}"
        for n, line in enumerate(text.splitlines(), start=1)
        if DRIVE.search(line) or HOME.search(line)
    ]


def _is_test(path: str) -> bool:
    parts = path.split("/")
    return "tests" in parts or "test" in parts or parts[-1].startswith("test_") or parts[-1].endswith(".test.ts")


def _tracked() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted(p for p in out.splitlines() if not p.startswith(SEALED) and Path(p).suffix.lower() not in BINARY)


@pytest.mark.integration
def test_no_tracked_text_file_names_a_drive_path_or_a_home_folder() -> None:
    found: dict[str, list[str]] = {}
    for path in _tracked():
        if _is_test(path):
            continue
        file = ROOT / path
        if not file.is_file():
            continue
        try:
            text = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lines = local_paths(text)
        if lines:
            found[path] = lines
    assert found == {}


@pytest.mark.parametrize(
    "line",
    [
        "night_shift.py finished in D:\\Devpost\\Kiroween 2026\\night-audit:",
        '{"checkout": "D:/Devpost/Kiroween 2026/night-audit"}',
        '--source "D:\\...\\crew\\night-shift"',
        "C:\\Users\\someone\\.aws",
        "/home/someone/night-audit",
        "/Users/someone/night-audit",
        '{"checkout": "D:\\\\path\\\\to\\\\night-audit"}',
    ],
)
def test_the_scan_sees_a_local_path(line: str) -> None:
    assert local_paths(line) != []


@pytest.mark.parametrize(
    "line",
    [
        '{"checkout": "<checkout>"}',
        "https://api.github.com/users/night-owl-42",
        "AWS_CONFIG_FILE: /home/audit/.aws/config",
        "a ratio of 4.5:1 for body text",
        "http://localhost:5476",
        "~/.kiro/settings/mcp.json",
    ],
)
def test_the_scan_passes_a_line_with_no_local_path(line: str) -> None:
    assert local_paths(line) == []
