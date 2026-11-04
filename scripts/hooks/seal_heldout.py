"""PreToolUse hook: keep the agent out of the sealed held-out casebook.

Kiro sends the tool call as JSON on stdin. A non-zero exit blocks the call and stderr is shown to the agent.
The only command allowed to touch the held-out set is the release scorer.
"""

import json
import sys

ALLOWED_COMMANDS = ("scripts/score_heldout.py", "scripts\score_heldout.py")


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    tool_input = event.get("tool_input", {}) or {}
    # Only fields that point at files or run commands. Text being written (for example a README that mentions the
    # folder) is not a read of the folder.
    fields = [tool_input.get(k) for k in ("path", "paths", "file_path", "pattern", "glob", "include", "command", "cwd")]
    payload = json.dumps(fields).lower().replace("\\\\", "/")
    if "heldout" not in payload:
        return 0
    if any(cmd.lower() in payload for cmd in ALLOWED_COMMANDS):
        return 0
    print(
        "Blocked: casebook/heldout is sealed (audit rule 7). "
        "It is scored only by scripts/score_heldout.py on a tagged release.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
