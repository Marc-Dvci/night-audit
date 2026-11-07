# Night shift: the Kiro Crew app

`crew/night-shift/` is a Kiro Crew app. Its manifest declares two daily script crons, an investigator agent with two
read-only MCP servers, and a skill.

| Cron | When (UTC) | What it runs | Time limits |
|---|---|---|---|
| `night-audit` | 02:00, exactly on the minute (`strict_schedule`) | `crons/night_jobs.py:nightly`, which runs `uv run --directory <checkout> python scripts/nightly.py --runs runs`. That runs `nightaudit run` for each control under `apps/*/controls/` (files there without a top-level `ledgers` key are settings and are skipped). No model is called. | the subprocess 1440 s, the script 1500 s (`timeout`), the run 1560 s (`timeout_secs`) |
| `night-notes` | 02:30, exactly on the minute | `crons/night_jobs.py:notes`, which runs `scripts/night_shift.py --runs runs --limit 12 --timeout 240 --profile $AWS_PROFILE` on the newest run. | the subprocess 3540 s, the script 3600 s, the run 3660 s |

Both crons are declared `"enabled": false`, so Crew registers them paused.

## How a script cron runs in Crew 0.13.0

Read from `build/crew-docs/src/cron_script.py`, `bridges_crons.py` and Crew's `slack/gateway_runtime/cron_exec.py`:

* Crew imports the file in a fresh Python subprocess and calls the function with one argument, `ctx`.
  `ctx.job.id` and `ctx.job.message` are the job's id and message.
* Returning, or raising `kiro_crew.cron_script.Report(text)`, is a successful run; Crew stores the `Report` text as the
  job's `last_result`. Any other exception is a failed run and its text becomes `last_error`. `Done` would delete the
  job, so these functions never raise it.
* The script's time limit is the job's `timeout`, 30 s when it is 0. `timeout_secs` must cover `timeout` plus 5 s.
  Each function gives its own subprocess a limit below `timeout`, so a slow run ends with a clear line, not a kill.
* The child gets the gateway's environment minus Crew's secret deny list. A job's `env` is never passed to a script
  child (`run_script_sandboxed` takes none), and `env`, `script` and `command` are create-only fields.
* The path is resolved inside the installed bundle, must be a `.py` file, and is stored as an absolute path. The body
  is scanned at registration for credential paths, protected secret variable names and URLs.

**Why the checkout path is in the message.** The message is passed to the script as `ctx.job.message`, and an
operator changes it with `kirocrew cron update <id> --message`. Crew keeps that edit on later registrations unless
the manifest's own message changes. `env` was the other option, but Crew never hands it to a script and it cannot be
changed after the job is created. The message is JSON: `{"checkout": "<absolute path>"}`. A message that is not that
JSON, a relative path, or a folder without `scripts/nightly.py` and `pyproject.toml` fails the run with one line, and
nothing is started.

## Notes reach the page only through `scripts/night_shift.py`

The 02:30 job used to be an agent cron. Its reply stayed in Crew, and nothing checked it or tied it to a run. Now the
02:30 job is a script cron that runs `scripts/night_shift.py`, which already does the checking:

* It launches `kiro-cli chat --v3 ... --agent night-investigator` for each new `OB` and `O` finding, from the
  checkout. The agent it starts is the checkout's `.kiro/agents/night-investigator.json`.
* It checks each note's numbers against the finding's evidence and appends the verdict to
  `runs/<run_id>/evidence/notes.jsonl`, a hash chain bound to the run. `uv run nightaudit verify-notes
  runs/<run_id>/evidence` checks it. The page shows only accepted notes from that chain.
* Exit code 2 (Kiro unavailable for a finding) is a failed Crew run, so it shows on the Schedule page. Nothing is
  written for that finding and the run is unchanged.

Crew still registers the app's own `night-investigator` agent with the `read-a-night` skill, so an operator can ask it
about a run in a Crew chat. What it says there is a chat reply, not a note, and never reaches the page.

The agent declares its servers in its own `mcpServers`, which is where `bridges_agents.py` resolves `@server` tool refs
(the agent's own map, then the global `~/.kiro/settings/mcp.json`). A server declared in the manifest's `mcpServers`
would be registered as `night-shift:<server>` in Crew's own agent config instead.

| Server | Package | Read-only by |
|---|---|---|
| `aws-api` | `awslabs.aws-api-mcp-server@1.6.0` | `READ_OPERATIONS_ONLY=true` |
| `aws-cloudtrail` | `awslabs.cloudtrail-mcp-server@0.1.1` | `lake_query` disabled: it calls `StartQuery`; the other tools are `LookupEvents`, `List*`, `Get*` and `Describe*` calls |

Neither server names a profile. They inherit `AWS_PROFILE` from the process that starts them; the gateway was started
with `AWS_PROFILE=night-audit`. The power writes `"${AWS_PROFILE}"`, but Crew reads `{AWS_PROFILE}` inside it as a host
placeholder it does not know and refuses the whole agent (see below).

## Install

1. Install Kiro Crew and start it: `kirocrew gateway`.
2. Install the app from its absolute path: `kirocrew app install /absolute/path/to/night-audit/crew/night-shift`.
3. Trust this app alone (Settings → Security → Third-party apps, or `agent.apps_trusted`), then
   `kirocrew app enable night-shift`.
4. Set the checkout in both jobs' messages (`kirocrew cron list` shows the ids):

   ```bash
   kirocrew cron update <id> --message '{"checkout": "/absolute/path/to/night-audit"}'
   ```

   The checkout needs `uv sync` done once, and `uv` must be on the gateway's `PATH`.
5. Try a job once with `kirocrew cron trigger <id>`, then `kirocrew cron resume <id>` to schedule it, or
   `kirocrew cron pause <id>` to keep it off.

Disabling the app deletes its registered crons; enabling it again registers them paused, from the manifest, with the
placeholder message.

## Checked on Kiro Crew 0.13.0, Windows 11, 7 November 2026

Crew 0.13.0 from a source checkout, gateway on `http://localhost:5476` started with `AWS_PROFILE=night-audit`,
`--no-open --no-tunnel`. CLI only; the dashboard was not built.

**The two defects as Crew reported them at the first install** (gateway log, 10:49:56 and 10:49:57):

```
WARNING kiro_crew.apps.bridges: App night-shift: agent 'night-investigator' grants MCP tool ref(s) not found in this agent's merged mcpServers or the global mcp.json; kiro-cli will silently never mount them: @aws-api (server 'aws-api'), @aws-cloudtrail (server 'aws-cloudtrail')
WARNING kiro_crew.apps.bridges: App night-shift: cron 'night-shift/night-audit' command rejected: Error: No POSIX shell available to run this command cron. ...
```

**`app update` cannot run from the CLI on Windows.** `kirocrew app update night-shift --source "D:\...\crew\night-shift"`
printed `No running gateway answered, so nothing was updated` and exited 1, while the gateway answered `/api/health`
with 200. The CLI's lifecycle requests use the gateway's owner-only Unix socket (`app_lifecycle_client.py`), which this
Windows gateway does not serve; `cron trigger` uses loopback HTTP and works. What worked: `kirocrew app disable`,
`kirocrew app uninstall`, `kirocrew app install`, `kirocrew app enable`. Uninstall also removes the app's trust grant
(`manager_uninstall.py`), so it was restored to exactly `["night-shift"]` in `agent.apps_trusted` and
`agent.apps_trusted_local` with `kirocrew config set ... --value-base64` before the enable. The file-only enable writes
Crew's cron store, which the running gateway re-reads.

**A third defect, found by that install:** with the power's `"AWS_API_MCP_PROFILE_NAME": "${AWS_PROFILE}"` in the
agent, the enable printed

```
WARNING kiro_crew.apps.bridges: App night-shift: agent night-investigator.json has an unresolved placeholder {AWS_PROFILE} — not registered
```

The profile entries were removed and the app installed again. The enable then printed:

```
✅ Recorded night-shift as enabled. ...
   Agents registered: 1
   Skills registered: 1
  registered 2 cron job(s) with scheduler
```

`~/.kiro/agents/night-shift--night-investigator.json` holds both servers. The gateway log has no line after its own
start at 10:49:58, so no new warning about this app.

**`kirocrew cron list`** after setting the checkout in both messages:

```
  ⏸ e7757f1f  night-shift/night-audit  (At 2:00 AM UTC)  {"checkout": "D:/Devpost/Kiroween 2026/night-audit"}
  ⏸ 771fc3b9  night-shift/night-notes  (At 2:30 AM UTC)  {"checkout": "D:/Devpost/Kiroween 2026/night-audit"}
```

**The audit job**, `kirocrew cron trigger e7757f1f` at 11:02:37 (local time), against the lab account through the
gateway's read-only profile. Crew recorded `last_status: ok`, `last_error: null`, at 10:03:44 UTC. Its `last_result`
names four runs:

| Run | Control | Result | `uv run nightaudit verify runs/<run>/evidence` |
|---|---|---|---|
| `41178d37bd0da182` | `staff-access-github.yaml` | incomplete, `missing ledgers: observed`, 0 findings | first `FAIL  the page differs from the evidence: billed total: the page shows $0.00, the evidence has $6,683.00; ...`; after the verifier fix below, `OK  verified 545 rows, 0 findings, ...` |
| `c518e7f39e95c08e` | `staff-access.yaml` | complete, 8 findings, 4 informational | `OK  verified 742 rows, 12 findings, header matches the manifest; the page matches the evidence` |
| `910948837feacfbc` | `own-build.yaml` | complete, 90 findings, 118 informational | `OK  verified 1078 rows, 208 findings, ...` |
| `1e9e38e57a33f5c4` | `aws-account.yaml` | complete, 6 findings, 2 informational | `OK  verified 226 rows, 8 findings, ...` |

The verifier was wrong, not the run: an incomplete run matches nothing and states no amount, so its page carries
`billed_total` 0 while its chain holds the billed rows that were read. Both verifiers (Python and the browser's
`verify.ts`) now expect zero for an incomplete run. The regression test is
`test_regression_an_incomplete_run_whose_billed_ledger_was_read_verifies_against_its_page`.

**The notes job**, `kirocrew cron trigger 771fc3b9` at 11:12:44. Crew recorded `last_status: ok` at 10:14:17 UTC
with this `last_result`:

```
night_shift.py finished in D:\Devpost\Kiroween 2026\night-audit:
accepted     akiawcfihw3qdcdeagee
accepted     lab-debug
accepted     eni-085d97a8b514d1ce7
accepted     i-0c8b3995db6d57788
accepted     vol-042dd68de0b61a0dd
run 1e9e38e57a33f5c4: 5 accepted, 0 rejected, 0 unavailable, 0 skipped; notes in runs\1e9e38e57a33f5c4\evidence\notes.jsonl
```

`uv run nightaudit verify-notes runs/1e9e38e57a33f5c4/evidence` printed
`OK  evidence verifies; 5 notes verify (5 accepted)`. No model call and no MCP server failed in either run.

After both runs both jobs show `enabled: false, user_paused: true` (a trigger does not resume a job), and
`kirocrew cron pause` was run on both again so nothing fires at 02:00 until the owner resumes them.

## Still not checked

* That the Crew-registered `night-investigator` agent mounts its two servers in a Crew chat: no chat was opened. The
  notes job runs the checkout's own agent through kiro-cli, which reads `.kiro/settings/mcp.json`.
* A run that fires on its schedule at 02:00 or 02:30; both were started with `cron trigger`.
* A failed run inside Crew: the missing-checkout, non-zero-exit and timeout paths are unit-tested only.
* That a timed-out `uv` subprocess on Windows also ends the Python process it started.
* `kirocrew app update` on a gateway that serves its Unix socket (Linux or macOS).
* The store icon (`iconPath`) and screenshots, which the manifest does not set.

The repository's hook `read-only-aws` and the agent permissions under `.kiro/agents/` apply to `kiro-cli`, which is how
`scripts/night_shift.py` runs the investigator. They are not Crew settings.
