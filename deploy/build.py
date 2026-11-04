"""Package and deploy Night Audit to AWS Lambda.

    uv run python deploy/build.py --profile <admin-profile>            # package, upload, deploy
    uv run python deploy/build.py --package-only                        # just build build/night-audit.zip

Steps: install arm64 wheels for Python 3.12, copy the skeleton, the Vampires app, the controls (never *.local.yaml),
the built web UI and the handlers, zip, upload by content hash, deploy deploy/stack.yaml with the tag
night-audit:intended=true, and copy the local-only control files to the runs bucket's private config/ prefix.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
PKG = BUILD / "pkg"
ZIP = BUILD / "night-audit.zip"
DEPS = ["pydantic>=2", "pyyaml>=6", "fastapi>=0.115", "mangum>=0.19", "pyarrow>=17", "tzdata>=2024.1"]
TRIM = [
    "pyarrow/include",
    "pyarrow/tests",
    "pyarrow/src",
    "pyarrow/libarrow_flight.so*",
    "pyarrow/libarrow_substrait.so*",
    "pyarrow/libarrow_python_flight.so*",
    "pyarrow/_flight*.so",
    "pyarrow/_substrait*.so",
]
STACK = "night-audit"
REGION = "us-east-1"


def run(*cmd: str) -> str:
    print("+", " ".join(cmd))
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


def package() -> Path:
    shutil.rmtree(BUILD, ignore_errors=True)
    PKG.mkdir(parents=True)
    run(
        "uv", "pip", "install", "--quiet", "--python-platform", "aarch64-manylinux2014", "--python-version", "3.12",
        "--only-binary=:all:", "--target", str(PKG), *DEPS,
    )
    for pattern in TRIM:
        for path in PKG.glob(pattern):
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    shutil.copytree(ROOT / "skeleton" / "src" / "nightaudit", PKG / "nightaudit")
    shutil.copytree(ROOT / "apps" / "vampires" / "src" / "vampires", PKG / "vampires")
    shutil.copytree(
        ROOT / "apps" / "vampires" / "controls", PKG / "controls", ignore=shutil.ignore_patterns("*.local.yaml")
    )
    dist = ROOT / "skeleton" / "web" / "dist"
    if not (dist / "index.html").exists():
        sys.exit("build the UI first: (cd skeleton/web && npm run build)")
    shutil.copytree(dist, PKG / "web")
    shutil.copy(ROOT / "deploy" / "handlers.py", PKG / "handlers.py")
    for cache in PKG.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(PKG.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(PKG).as_posix())
    size = sum(p.stat().st_size for p in PKG.rglob("*") if p.is_file())
    print(f"{ZIP} {ZIP.stat().st_size / 1e6:.1f} MB zipped, {size / 1e6:.1f} MB unzipped")
    return ZIP


def deploy(profile: str, account: str) -> None:
    digest = hashlib.sha256(ZIP.read_bytes()).hexdigest()[:16]
    code_bucket = f"night-audit-artifacts-{account}"
    key = f"lambda/night-audit-{digest}.zip"
    base = ["--profile", profile, "--region", REGION]
    run("aws", "s3", "cp", str(ZIP), f"s3://{code_bucket}/{key}", *base)
    run(
        "aws", "cloudformation", "deploy", "--stack-name", STACK,
        "--template-file", str(ROOT / "deploy" / "stack.yaml"),
        "--capabilities", "CAPABILITY_IAM", "--parameter-overrides", f"CodeBucket={code_bucket}", f"CodeKey={key}",
        "--tags", "night-audit:intended=true", "project=night-audit", *base,
    )
    runs_bucket = f"night-audit-runs-{account}"
    for local in (ROOT / "apps" / "vampires" / "controls").glob("*.local.yaml"):
        run("aws", "s3", "cp", str(local), f"s3://{runs_bucket}/config/{local.name}", *base)
    url = run(
        "aws", "cloudformation", "describe-stacks", "--stack-name", STACK,
        "--query", "Stacks[0].Outputs[?OutputKey=='Url'].OutputValue", "--output", "text", *base,
    )
    print("live at", url)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="default")
    parser.add_argument("--account", default="416964654816")
    parser.add_argument("--package-only", action="store_true")
    args = parser.parse_args()
    package()
    if not args.package_only:
        deploy(args.profile, args.account)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
