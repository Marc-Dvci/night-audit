"""The plain words a stored night is shown in when it was recorded before its control gave region labels.

Presentation only. A region whose stored run carries no plain label takes the label and the headline template of that
region code from the app's current control, read here from its control file, and from ``BUILT_IN_WORDS`` when the app
has no current control. Nothing stored is read differently: the run, its evidence and its hashes stay as written, and
every number of a rebuilt headline still comes from the run's own counts and amounts (audit rule 2).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from .control import DEFAULT_HEADLINES, ControlFile, region_labels, resolve_ui
from .models import DEFAULT_REGION_LABELS, HeadlineUi


class PlainWords(BaseModel):
    """An app's current plain words per region code: its short label and its headline template."""

    labels: dict[str, str]
    headlines: dict[str, HeadlineUi]


#: The built-in plain words, for a night whose app has no current control.
BUILT_IN_WORDS = PlainWords(
    labels=dict(DEFAULT_REGION_LABELS),
    headlines={code: HeadlineUi(one=one, other=other) for code, (one, other) in DEFAULT_HEADLINES.items()},
)

#: The current plain words of each app, by app name (``ControlFile.app``).
AppWords = Mapping[str, PlainWords]


def plain_words(control: ControlFile) -> PlainWords:
    """The plain words a control gives today: its resolved labels and headline templates."""
    return PlainWords(labels=region_labels(control.to_config()), headlines=dict(resolve_ui(control).headlines))


def load_words(paths: Iterable[Path]) -> dict[str, PlainWords]:
    """The current words of each app named by the control files at *paths*. The first file of an app, in sorted
    order, gives that app's words. A file that names no app gives none."""
    words: dict[str, PlainWords] = {}
    for path in sorted(paths):
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        control = ControlFile.model_validate(raw)
        if control.app and control.app not in words:
            words[control.app] = plain_words(control)
    return words


def control_files(folder: Path) -> list[Path]:
    """The control files of one ``controls/`` folder. Local, untracked ``*.local.yaml`` files hold no control."""
    return sorted(p for p in folder.glob("*.yaml") if not p.name.endswith(".local.yaml"))


def repo_app_words(root: Path) -> dict[str, PlainWords]:
    """The current words of every app in a repository checkout: ``apps/<app>/controls/*.yaml``."""
    return load_words(p for folder in sorted((root / "apps").glob("*/controls")) for p in control_files(folder))


def words_for(app: str, words: AppWords | None) -> PlainWords:
    """The current words of *app*, or the built-in words when it has none."""
    if words is not None and app in words:
        return words[app]
    return BUILT_IN_WORDS


__all__ = [
    "BUILT_IN_WORDS",
    "AppWords",
    "PlainWords",
    "control_files",
    "load_words",
    "plain_words",
    "repo_app_words",
    "words_for",
]
