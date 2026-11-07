"""AWS Lambda entry points for the deployed Night Audit.

* ``web``: the UI and the read API behind a public function URL. Runs are mirrored from S3 into /tmp.
* ``nightly``: runs the account control at 02:00 UTC under a read-only role and stores the run and its evidence in S3.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

import boto3
from mangum import Mangum
from nightaudit.api import create_app
from nightaudit.runner import run_control, run_summary
from nightaudit.wording import control_files, load_words

HERE = Path(__file__).resolve().parent
BUCKET = os.environ["RUNS_BUCKET"]
RUNS = Path("/tmp/runs")
CONTROLS = Path("/tmp/controls")
CONTROL_FILE = os.environ.get("CONTROL_FILE", "aws-account.yaml")
PREFIX = "nights/"
_s3 = boto3.client("s3")
_last_sync = 0.0


def _download_prefix(prefix: str, dest: Path) -> int:
    count = 0
    paginator = _s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            target = dest / obj["Key"][len(prefix) :]
            if target.exists() and target.stat().st_size == obj["Size"]:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            _s3.download_file(BUCKET, obj["Key"], str(target))
            count += 1
    return count


def _upload_dir(src: Path, prefix: str) -> None:
    for path in src.rglob("*"):
        if path.is_file():
            _s3.upload_file(str(path), BUCKET, f"{prefix}{path.relative_to(src).as_posix()}")


RUNS.mkdir(parents=True, exist_ok=True)
#: Nights stored before plain labels are shown in the packaged controls' current plain words (presentation only).
_app = create_app(RUNS, static_dir=HERE / "web", words=load_words(control_files(HERE / "controls")))
_mangum = Mangum(_app, lifespan="off")


def web(event: dict[str, Any], context: Any) -> dict[str, Any]:
    global _last_sync
    if time.time() - _last_sync > 60:
        _download_prefix(PREFIX, RUNS)
        _last_sync = time.time()
    return _mangum(event, context)


def nightly(event: dict[str, Any], context: Any) -> dict[str, Any]:
    _download_prefix(f"{PREFIX}_state/", RUNS / "_state")
    shutil.rmtree(CONTROLS, ignore_errors=True)
    shutil.copytree(HERE / "controls", CONTROLS)
    _download_prefix("config/", CONTROLS)  # local-only files: exclusions and approvals with live identifiers
    result = run_control(CONTROLS / CONTROL_FILE, RUNS)
    _upload_dir(RUNS / result.run_id, f"{PREFIX}{result.run_id}/")
    _upload_dir(RUNS / "_state", f"{PREFIX}_state/")
    summary = run_summary(result)
    print(summary)
    return summary
