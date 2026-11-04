"""Command-line entry points for Night Audit (all).

``nightaudit run <control>``    run a control file end to end.
``nightaudit serve --app <name>`` serve the web UI and API.
``nightaudit verify <pack>``     verify an evidence pack.
``nightaudit score --set dev``   score the casebook.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from .api import create_app
from .evidence import verify_evidence_pack
from .runner import run_control


def _parse_run_time(text: str | None) -> datetime | None:
    """Parse an ISO-8601 run time; naive values are assumed UTC."""
    if text is None:
        return None
    value = text
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _web_dist() -> Path:
    """The skeleton's built static front end directory."""
    return Path(__file__).resolve().parents[2] / "web" / "dist"


def _repo_root() -> Path:
    """The repository root (parent of the skeleton package)."""
    return Path(__file__).resolve().parents[3]


def _cmd_run(args: argparse.Namespace) -> int:
    result = run_control(
        Path(args.control),
        Path(args.runs),
        run_time=_parse_run_time(args.at),
    )
    findings = sum(1 for f in result.findings if not f.informational)
    informational = sum(1 for f in result.findings if f.informational)
    print(f"run {result.run_id}")
    print(f"  complete: {result.complete}")
    if not result.complete:
        print(f"  missing ledgers: {', '.join(result.missing_ledgers)}")
    print(f"  findings: {findings}  informational: {informational}")
    print(f"  billed total: {result.billed_total}")
    print(f"  control hash: {result.control_hash}")
    print(f"  evidence chain: {result.evidence_chain_hash}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    app = create_app(Path(args.runs), static_dir=_web_dist())
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    result = verify_evidence_pack(Path(args.pack))
    print(f"{'OK' if result.ok else 'FAIL'}  {result.detail}")
    return 0 if result.ok else 1


def _cmd_score(args: argparse.Namespace) -> int:
    scorer = _repo_root() / "scripts" / "score_casebook.py"
    if not scorer.exists():
        print(f"Scorer not found: {scorer}", file=sys.stderr)
        return 1
    cmd = [sys.executable, str(scorer), "--set", args.set]
    if args.quiet:
        cmd.append("--quiet")
    completed = subprocess.run(cmd, cwd=str(_repo_root()))
    return completed.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nightaudit", description="Night Audit CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run a control file")
    run_p.add_argument("control", help="path to the control YAML file")
    run_p.add_argument("--runs", default="runs", help="runs directory (default: runs)")
    run_p.add_argument("--at", help="ISO-8601 run time in UTC (default: now)")
    run_p.set_defaults(func=_cmd_run)

    serve_p = sub.add_parser("serve", help="serve the web UI and API")
    serve_p.add_argument("--app", required=True, help="which application to serve")
    serve_p.add_argument("--runs", default="runs", help="runs directory (default: runs)")
    serve_p.add_argument("--host", default="127.0.0.1", help="bind host")
    serve_p.add_argument("--port", type=int, default=8000, help="bind port")
    serve_p.set_defaults(func=_cmd_serve)

    verify_p = sub.add_parser("verify", help="verify an evidence pack")
    verify_p.add_argument("pack", help="path to the evidence pack directory")
    verify_p.set_defaults(func=_cmd_verify)

    score_p = sub.add_parser("score", help="score the casebook")
    score_p.add_argument("--set", choices=["dev", "heldout"], default="dev")
    score_p.add_argument("--quiet", action="store_true")
    score_p.set_defaults(func=_cmd_score)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    code: int = args.func(args)
    return code


if __name__ == "__main__":
    sys.exit(main())
