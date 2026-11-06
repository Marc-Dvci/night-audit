"""PreToolUse hook: the builder may run any command, except one that deletes files or could harm the computer.

An allow-list of commands fails on every pipe when nobody is there to answer a prompt, so the agent gets a shell and this hook
states what is off limits. A non-zero exit blocks the call and stderr goes back to the agent.
"""

import json
import re
import sys
from pathlib import Path

RULES = [
    (r"(^|[\s;&|(\"'`])(rm|rmdir|rd|del|erase|ri|unlink|shred)(\.exe)?(\s|$)", "deletes files"),
    (r"remove-item|clear-content|clear-item", "deletes files"),
    (r"\bfind\b[^\n]*\s-delete\b|\brsync\b[^\n]*--delete|\bcmake\b[^\n]*-e\s+(rm|remove)", "deletes files"),
    (r"os\.(remove|unlink|rmdir)|shutil\.rmtree|\.unlink\(|\.rmdir\(", "deletes files"),
    (r"\bgit\s+(rm|clean|rebase|filter-branch)\b", "deletes files or rewrites history"),
    (r"\bgit\s+reset\s+--hard\b|\bgit\s+checkout\s+(--|\.)|\bgit\s+restore\b", "discards work"),
    (r"\bgit\s+push\b|\bgit\s+commit\b|\bgit\s+remote\s+(add|set-url)\b", "publishing and commits stay with the owner"),
    (r"\bgh\s+(repo|release|gist|pr|issue)\s+\w+|--visibility|--public\b", "changes GitHub, which stays with the owner"),
    (r"\b(shutdown|reboot|restart-computer|stop-computer|diskpart|mkfs|bcdedit|reg\s+delete)\b", "could harm the computer"),
    (r"\bwsl(\.exe)?\s+--\w+|\bset-mppreference\b|\bset-executionpolicy\b|\bnetsh\b", "changes system settings"),
    (r"\btaskkill\b[^\n]*/im\b|\bstop-process\b[^\n]*-name\b|\bget-process\b[^\n]*\|\s*stop-process\b|\b(killall|pkill)\b", "kills processes by name"),
    (r"-verb\s+runas|\brunas\b|\bwinget\b|\bchoco(latey)?\b|\bmsiexec\b|\binvoke-expression\b|\biex\b", "opens a window or a system prompt"),
    (r"[\\/]\.aws[\\/]|[\\/]\.git-credentials|[\\/]\.ssh[\\/]|--profile\s+otl", "reads a credential"),
]


def reason_for(tool: str, tool_input: dict[str, object]) -> str | None:
    if tool == "delete_file":
        return "deletes files"
    command = str(tool_input.get("command", "") or "").lower()
    for pattern, reason in RULES:
        if command and re.search(pattern, command):
            return reason
    path = str(tool_input.get("path") or tool_input.get("file_path") or "")
    if tool in {"fs_write", "fs_append", "str_replace"} and path:
        root = Path.cwd().resolve()
        target = (root / path).resolve()
        if target != root and root not in target.parents:
            return "writes outside this repository"
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    reason = reason_for(str(event.get("tool_name", "")), event.get("tool_input", {}) or {})
    if reason:
        print(f"Blocked ({reason}). Do not work around it; report it instead.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
