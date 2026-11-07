# Night Audit, a Kiro power

Night Audit is a three-way match for things an organisation pays for. It compares three lists of the same reality:
what you **approved**, what **exists**, and what you are **billed** for. A thing that appears in all three is fine.
Every other combination is a finding with one fixed meaning, for example "an account is active and has a paid seat, but
nobody approved it".

This power gives Kiro two skills.

| Skill | Ask Kiro something like | What it does |
|---|---|---|
| `add-control` | "Reconcile our HR list against Okta users and the Slack invoice." | Asks you what the three sources are and what identifies the same thing in each. Then writes a control file, connectors, fixtures, contract tests and a casebook of at least five cases, one of them healthy. Nothing is matched until you have confirmed the expected results. |
| `read-a-night` | "What did last night's audit find? What should I check first?" | Explains a run's findings in plain words, quoting only values from the evidence, as conditions and never accusations. |

## You need

- [Kiro](https://kiro.dev) with `kiro-cli`, and [uv](https://docs.astral.sh/uv/) on your path.
- Read access to the `Marc-Dvci/night-audit` repository while it is private.
- For AWS sources only: a **read-only** AWS profile of your own, named in `AWS_PROFILE`.

## Install

1. Clone the repository: `git clone https://github.com/Marc-Dvci/night-audit`.
2. Install the power from the folder: `kiro-cli powers install <path-to-clone>/power/night-audit`.
3. The skills install the `nightaudit` Python package into **your** project with `uv add`. While the repository is
   private, `uv add` from GitHub fails unless you are signed in to it, so point the skills at your clone:

   ```bash
   export NIGHTAUDIT_SOURCE=/path/to/night-audit/skeleton        # PowerShell: $env:NIGHTAUDIT_SOURCE = "C:\path\to\night-audit\skeleton"
   ```

   Set it before you start Kiro. When it is not set, the skill uses
   `uv add "nightaudit @ git+https://github.com/Marc-Dvci/night-audit#subdirectory=skeleton"`.
4. AWS sources only: export `AWS_PROFILE` before you start Kiro. Kiro reads it when it launches, so restart Kiro after
   you set it. The bundled `aws-api` server reads it, runs with `READ_OPERATIONS_ONLY=true` and sends no secret
   anywhere. If `AWS_PROFILE` is unset, the server fails to start and nothing is called. On Windows, if `uvx` cannot
   start the server, see the server's own install notes at
   [awslabs/mcp](https://github.com/awslabs/mcp/tree/main/src/aws-api-mcp-server).

## Try it in an empty folder

1. Make an empty folder and open it in Kiro. It needs no Night Audit files.
2. Ask: "Set up a three-way match for our chat seats. I have an HR roster CSV, a list of active accounts and the
   vendor invoice CSV." Answer Kiro's questions about the key and the region names.
3. Kiro writes `controls/`, `fixtures/`, `casebook/` and `tests/`, shows you the casebook as a table, and waits. Check
   each expected result, then say yes.
4. Kiro runs `uv run pytest -q` and `uv run nightaudit run controls/<id>.yaml`.
5. Ask: "What did that run find? What should I check first?"

A worked example (control, fixtures, casebook) is in `skills/add-control/references/`.

## What it will not do

- It does not decide findings. Code assigns every region from which ledgers hold a key; Kiro only writes files and
  explains the result.
- It does not write to your systems. Connectors read only; the AWS server is limited to read operations.
- It does not store credentials, account ids or real email addresses. Fixtures must be synthetic or redacted, and the
  generated tests fail if they find a real-looking value.
- A record younger than the control's grace window is reported as pending, because billing data arrives late.

## Files

```
plugin.json      manifest (Agent Plugins 1.0.0)
mcp.json         the read-only AWS server, profile from ${AWS_PROFILE}
skills/add-control/    SKILL.md, references/ (region table, audit rules, example), assets/ (test templates)
skills/read-a-night/   SKILL.md, references/ (region table, audit rules, how to read a finding)
```
