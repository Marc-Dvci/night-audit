"""Build every application's static demo and the ``apps.json`` the page reads (Req 10.8).

Each app's ``apps/<app>/demo/build.py`` exposes ``build(target, runs)`` and ``APP_ENTRIES``. This script calls each
build with its own folder, ``skeleton/web/public/demo/<app>/``, then writes ``skeleton/web/public/apps.json`` from the
entries in the order of ``APPS``: Vampires live, Vampires demo, Ghosts demo, Own build demo. A build only ever replaces its own
folder, so building one app never removes another app's demo.

    uv run python scripts/build_demos.py            # every app
    uv run python scripts/build_demos.py ghosts     # one app; apps.json still lists every app
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from nightaudit.textfile import write_text_exact

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "skeleton" / "web" / "public"
#: The apps with a demo, in the order the masthead lists them.
APPS = ("vampires", "ghosts", "own-build")


def builder(app: str) -> ModuleType:
    """Load ``apps/<app>/demo/build.py`` as a module."""
    path = ROOT / "apps" / app / "demo" / "build.py"
    spec = importlib.util.spec_from_file_location(f"{app}_demo_build", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def app_entries() -> list[dict[str, Any]]:
    """Every app's ``apps.json`` entries, live entries first, then the demos, each group in ``APPS`` order."""
    entries = [e for app in APPS for e in builder(app).APP_ENTRIES]
    return [e for e in entries if e["mode"] == "live"] + [e for e in entries if e["mode"] != "live"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("apps", nargs="*", help=f"apps to build: {', '.join(APPS)} (default: all)")
    args = parser.parse_args(argv)
    unknown = sorted(set(args.apps) - set(APPS))
    if unknown:
        parser.error(f"unknown app: {', '.join(unknown)}")
    for app in args.apps or APPS:
        module = builder(app)
        module.build(PUBLIC / "demo" / app)
    write_text_exact(PUBLIC / "apps.json", json.dumps(app_entries(), indent=2) + "\n")
    print(f"apps.json lists {', '.join(e['name'] for e in app_entries())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
