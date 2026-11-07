"""Write text files with exactly the bytes the program produced, on every platform.

``Path.write_text`` and ``open(..., "w")`` translate ``\\n`` to ``\\r\\n`` on Windows unless ``newline`` is given. A run's
files are evidence: the same inputs must give the same bytes, so a file written on one machine can be compared, hashed
and zipped on another. Every file a run, an export or a download writes goes through ``write_text_exact``.
"""

from __future__ import annotations

from pathlib import Path


def write_text_exact(path: Path, text: str) -> None:
    """Write *text* as UTF-8 with no newline translation: line endings reach the file exactly as they are in *text*."""
    path.write_bytes(text.encode("utf-8"))
