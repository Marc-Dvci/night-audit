"""PreToolUse hook: AWS tools may only read (audit rule 3).

Blocks any MCP AWS call or shell `aws` command whose operation is not a read verb.
"""

import json
import re
import sys

READ_VERBS = ("describe", "list", "get", "lookup", "search", "batch-get", "batchget", "head", "select", "query")
AWS_CLI = re.compile(r"\baws(?:\.exe)?\s+([a-z0-9-]+)\s+([a-z0-9-]+)")


def is_read(operation: str) -> bool:
    op = operation.lower().replace("_", "-")
    return op.startswith(READ_VERBS)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    tool = str(event.get("tool_name", ""))
    tool_input = event.get("tool_input", {}) or {}
    blocked: list[str] = []

    if tool.startswith("mcp_") and "aws" in tool:
        text = json.dumps(tool_input)
        for match in AWS_CLI.finditer(text):
            if not is_read(match.group(2)):
                blocked.append(f"aws {match.group(1)} {match.group(2)}")
        operation = str(tool_input.get("operation_name") or tool_input.get("operation") or "")
        if operation and not is_read(operation):
            blocked.append(operation)
    else:
        command = str(tool_input.get("command", ""))
        for match in AWS_CLI.finditer(command):
            if not is_read(match.group(2)):
                blocked.append(f"aws {match.group(1)} {match.group(2)}")

    if blocked:
        print(
            "Blocked: Night Audit is read-only (audit rule 3). Refused: " + ", ".join(blocked),
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
