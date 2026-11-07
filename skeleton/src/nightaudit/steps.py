"""What the runner gives an enricher or a summariser about the control it runs for (Req 10.3).

An enricher is ``func(findings, options)`` and a summariser ``func(result, options)``. Either may also take a keyword
parameter named ``control``; it then receives a ``ControlContext``, so an application stops repeating the control's
folder and alias table in ``options``. A step written before this module is called exactly as before.
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ControlContext:
    """The control a step runs for: where its file is, its alias domains, its id and the run's time."""

    folder: Path
    alias_domains: Mapping[str, str] = field(default_factory=dict)
    control_id: str = ""
    run_time: datetime | None = None

    def resolve(self, path: str | Path) -> Path:
        """A path from the control's options: relative paths are relative to the control file's folder."""
        candidate = Path(path)
        return candidate if candidate.is_absolute() else self.folder / candidate


def load_callable(entry: str) -> Any:
    """Import ``package.module:function``."""
    module_name, _, attr = entry.partition(":")
    if not module_name or not attr:
        raise ValueError(f"entry '{entry}' must look like 'package.module:function'")
    return getattr(importlib.import_module(module_name), attr)


def takes_control(func: Any) -> bool:
    """Whether *func* has a parameter named ``control``."""
    try:
        return "control" in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


def call_step(func: Any, subject: Any, options: dict[str, Any], control: ControlContext) -> Any:
    """Call an enricher or summariser, passing ``control`` only when it asks for it."""
    if takes_control(func):
        return func(subject, options, control=control)
    return func(subject, options)
