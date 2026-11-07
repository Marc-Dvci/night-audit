# Design: the night shift

This document covers Requirement 2 (the Kiro power). Requirements 1 (Crew job) and 3 (partition proof) get their own
sections here when they are taken up.

## 1. The power

`power/night-audit/` is an Agent Plugins 1.0.0 plugin that Kiro installs as a power
(`kiro-cli powers install <path>`, which takes a catalog name or a local path).

```
power/night-audit/
  plugin.json                 $schema, name, version, description, author, keywords
  mcp.json                    one read-only AWS server, profile from ${AWS_PROFILE}
  README.md                   for a stranger: install, first use, what it will and will not do
  skills/
    add-control/
      SKILL.md
      references/             region-table.md, audit-rules.md, casebook-format.md,
                              example-control.yaml, example-casebook.yaml, example-fixtures/
      assets/                 contract_tests.py, casebook_runner.py, connector_template.py
    read-a-night/
      SKILL.md
      references/             region-table.md, audit-rules.md, reading-a-finding.md
```

### Decisions

| Decision | Choice | Why |
|---|---|---|
| Where shared text lives | Each skill has its own copy of `region-table.md` and `audit-rules.md` | A skill must work when read alone, and a relative path out of the skill folder is not guaranteed to be installed. Tests keep the copies identical and keep them equal to their sources (`DEFAULT_REGION_NAMES`, `.kiro/steering/audit-rules.md`). |
| How `nightaudit` reaches a stranger's project | `uv add` from the git URL, or from `NIGHTAUDIT_SOURCE` when it is set | The repository is private. `NIGHTAUDIT_SOURCE` is the path of the `skeleton/` folder (or of a checkout that contains it). The skill never asks for or stores a token. |
| How the casebook is checked in a stranger's project | `assets/casebook_runner.py`, a pytest module copied into the project | `nightaudit score` runs this repository's `scripts/score_casebook.py`, which a stranger does not have. The runner uses the public package API (`load_control_file`, `match`) and the project's own control file, so the casebook and the control cannot drift apart. |
| Order of work | Connectors, fixtures and contract tests, then the casebook, then the user confirms the expectations, then the first matcher run | Requirement 2.2. Contract tests only read fixtures, so they do not run the matcher. |
| Healthy case | The runner refuses a casebook that has no case flagged `healthy: true`, or whose healthy case expects anything but all-`IOB` | A healthy account must produce zero findings (product rule). |
| MCP servers | Only `aws-api` (`awslabs.aws-api-mcp-server`, version pinned, `READ_OPERATIONS_ONLY=true`) | `add-control` uses it to look at the shape of an AWS source (`list-exports`, `describe-stacks`). The billing server is left out: no skill uses it, and `read-a-night` must not pull in numbers that are not evidence rows. |
| Secrets | `mcp.json` holds `${AWS_PROFILE}` and fixed flags only | A test rejects any literal that looks like a key, and any non-reference value outside an allow-list. |

## 2. `add-control` flow

1. Ask: the three sources in plain words, the key and how each source spells it, the region names, the grace window,
   any scope. Explain the seven regions first (`references/region-table.md`). Do not write files until answered.
2. Make `nightaudit` importable (`uv init --bare` when there is no `pyproject.toml`, then `uv add`).
3. Write `controls/<id>.yaml`, `fixtures/<id>/*` (example values or redacted), connectors, and
   `tests/test_contracts.py` from `assets/contract_tests.py`. Run the contract tests.
4. Write `casebook/<id>.yaml` (at least five labelled cases, one `healthy: true`, expectations worked out by hand from
   the region table) and `tests/test_casebook.py` from `assets/casebook_runner.py`.
5. Show the casebook to the user and get a yes. Only then run `uv run pytest -q`, then `nightaudit run`.
6. A failing case is information: decide whether the control, the case or the expectation is wrong, say which, and
   change the expectation only with the user's agreement.

## 3. `read-a-night` flow

1. Find the run (`runs/<run_id>/result.json`, newest `run_time`) and, if the reader will rely on it, run
   `nightaudit verify runs/<run_id>/evidence`.
2. Start with the run's state: incomplete (a ledger is missing) beats everything; then pending keys (too new to judge).
3. For each finding, state the condition from the region's meaning and quote evidence values exactly as stored. Prefer
   the finding's own `explanation`, which already passed the explanation guard.
4. Say what to check first, using `references/reading-a-finding.md`.
5. Never add, average, round or convert. Totals are quoted from the run's own fields or left out.

## 4. Checks (`skeleton/tests/test_power.py`)

These are example-based tests over a finite set of files, so none is a hypothesis property.

| Check | What fails it |
|---|---|
| Manifest | `plugin.json` has a key the schema does not allow, a bad `name`, no `author.name`, or too few of the required keywords |
| MCP config | A server without `type` and `command`, an `@latest` or unpinned package, no `${AWS_PROFILE}`, `READ_OPERATIONS_ONLY` not `"true"`, a literal that looks like a secret, a server no skill mentions |
| Skills | Missing or malformed frontmatter, a `name` that differs from the folder, a description over 1024 characters or not written as a trigger |
| References | A file a skill names that does not exist, or a file in `references/` or `assets/` that no skill names |
| Copies | The two copies of a shared reference differ, the region table disagrees with `DEFAULT_REGION_NAMES`, the audit rules differ from the steering file |
| Worked example | `example-control.yaml` does not load, its fixtures do not read through the connectors, or its casebook fails through `casebook_runner.py` |
| Templates | `connector_template.py` is not a read-only `Connector`, or the runner accepts a casebook with no healthy case |

## 5. Not done here

- Installing the power into Kiro and running it in an empty project: the owner does this by hand.
- `kiro-cli powers install` has no validate command, so Kiro's own loader is not exercised by the tests.
