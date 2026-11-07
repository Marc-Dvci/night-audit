"""Make a Linux or macOS machine write files as Windows does, so a byte-for-byte test needs no Windows machine.

Inside ``as_windows()``, two things behave as they do on Windows and changed the bytes of files this project writes:

* a text file opened for writing without ``newline=`` gets ``\\r\\n`` for each ``\\n`` (``Path.write_text``, ``open``);
* a ``zipfile.ZipInfo`` records ``create_system = 0`` (Windows) instead of 3 (Unix).

On Windows itself the context manager changes nothing, because both already hold.
"""

from __future__ import annotations

import builtins
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

#: The "created by" value Python writes into a zip entry on Windows.
WINDOWS_CREATE_SYSTEM = 0


def _is_text_write(mode: str) -> bool:
    return "b" not in mode and any(flag in mode for flag in "wax")


@contextmanager
def as_windows() -> Iterator[None]:
    """Inside this block, text files and zip entries are written the way Windows writes them."""
    real_path_open: Any = Path.open
    real_open: Any = builtins.open
    real_zipinfo_init: Any = zipfile.ZipInfo.__init__

    def path_open(self: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if _is_text_write(mode) and len(args) < 4 and kwargs.get("newline") is None:
            kwargs["newline"] = "\r\n"
        return real_path_open(self, mode, *args, **kwargs)

    def open_(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if _is_text_write(mode) and len(args) < 4 and kwargs.get("newline") is None:
            kwargs["newline"] = "\r\n"
        return real_open(file, mode, *args, **kwargs)

    def zipinfo_init(self: zipfile.ZipInfo, *args: Any, **kwargs: Any) -> None:
        real_zipinfo_init(self, *args, **kwargs)
        self.create_system = WINDOWS_CREATE_SYSTEM

    Path.open = path_open  # type: ignore[method-assign]
    builtins.open = open_
    zipfile.ZipInfo.__init__ = zipinfo_init  # type: ignore[method-assign]
    try:
        yield
    finally:
        Path.open = real_path_open  # type: ignore[method-assign]
        builtins.open = real_open
        zipfile.ZipInfo.__init__ = real_zipinfo_init  # type: ignore[method-assign]
