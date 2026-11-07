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
  checkout. The agent it starts is the checkout's `.kiro/agents/night-investigator.json`, with the servers of
  `.kiro/settings/mcp.json` (`includeMcpJson`), not the Crew app's agent.
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

**The two investigators.** Both mount `aws-api` with `READ_OPERATIONS_ONLY=true` and `aws-cloudtrail` with
`lake_query` disabled; the checkout's agent also denies `aws-cloudtrail/lake_query` in its permissions. **Both
investigators are read-only.** Neither may call the billing server: the checkout's agent, the one the notes job runs,
lists only `read`, `@aws-api` and `@aws-cloudtrail` in `tools` and allows only `aws-api/*` and `aws-cloudtrail/*` in its
MCP rules. The workspace settings still mount `aws-billing` (`awslabs.billing-cost-management-mcp-server@0.0.44`) for
the default Kiro agent, with the three tools that can start work in the account disabled, read from the server's
source: `storage-lens` (Athena `StartQueryExecution`, after `CREATE DATABASE` and `CREATE EXTERNAL TABLE`),
`sp-purchase-analyzer` (`StartCommitmentPurchaseAnalysis`) and `sp-recommendation`
(`StartSavingsPlansPurchaseRecommendationGeneration`).

How it is tested: `skeleton/tests/test_investigator_read_only.py` reads each agent together with the settings it
loads (`includeMcpJson`), works out every `server/tool` it can call (named in `tools`, server not disabled, tool not in
`disabledTools`, no deny rule), and maps each tool to the AWS operations it calls, recorded per pinned server version
from that server's source. It fails if any callable tool calls an operation that is not `Describe*`, `List*`, `Get*`,
`BatchGet*` or `LookupEvents`, if `call_aws` runs without `READ_OPERATIONS_ONLY=true`, or if a server is unpinned or a
version it has no record for. Its own cases show it catches `lake_query`, `call_aws` without read-only mode and the
three billing tools. All 15 tests pass.

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

**`app update` cannot run from the CLI on Windows.** `kirocrew app update night-shift --source "<checkout>\crew\night-shift"`
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
  ⏸ e7757f1f  night-shift/night-audit  (At 2:00 AM UTC)  {"checkout": "<checkout>"}
  ⏸ 771fc3b9  night-shift/night-notes  (At 2:30 AM UTC)  {"checkout": "<checkout>"}
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

**The notes job**, `kirocrew cron trigger 771fc3b9` at 11:12:44, with the earlier code. It wrote 5 accepted notes on
`1e9e38e57a33f5c4` (`akiawcfihw3qdcdeagee`, `lab-debug`, `eni-085d97a8b514d1ce7`, `i-0c8b3995db6d57788`,
`vol-042dd68de0b61a0dd`); the current record of the notes job is the 13:07 run below.

After both runs both jobs show `enabled: false, user_paused: true` (a trigger does not resume a job), and
`kirocrew cron pause` was run on both again so nothing fires at 02:00 until the owner resumes them.

## Run again with the final code, 7 November 2026, 12:52 to 13:07 local time

`crew/night-shift/crons/night_jobs.py` changed (its docstring example became `<checkout>`), so the bundle was
reinstalled: `kirocrew app disable night-shift`, `uninstall`, `install <checkout>\crew\night-shift`, then
`agent.apps_trusted` and `agent.apps_trusted_local` set back to exactly `["night-shift"]` (both read back as that),
then `enable`, which printed `Agents registered: 1`, `Skills registered: 1`, `registered 2 cron job(s) with
scheduler`. The new job ids are `0af6390d` (night-audit) and `9d342b56` (night-notes); the ids above are gone.

**A failed run, observed.** The first trigger of `0af6390d` ran before the message was set (PowerShell 5.1 had dropped
the quotes from the JSON). Crew recorded `last_status: error` and `last_error: "checkout
'REPLACE_WITH_NIGHT_AUDIT_CHECKOUT' is not an absolute path"`; no run was written.

**The audit job**, `kirocrew cron trigger 0af6390d` at 12:53:53 after `kirocrew cron update 0af6390d --message
'{"checkout": "<checkout>"}'`. Crew recorded `last_status: ok`, `last_error: null`. Its `last_result` names four runs:

| Run | Control | Result | `uv run nightaudit verify runs/<run>/evidence` |
|---|---|---|---|
| `847b2b2514c14574` | `staff-access-github.yaml` | incomplete, `missing ledgers: observed`, 0 findings | `OK  verified 545 rows, 0 findings, header matches the manifest; the page matches the evidence` |
| `ebd45fd5644e4159` | `staff-access.yaml` | complete, 8 findings, 4 informational | `OK  verified 742 rows, 12 findings, header matches the manifest; the page matches the evidence` |
| `4c3e32bf3ef8c9ab` | `own-build.yaml` | complete, 92 findings, 119 informational | `OK  verified 1119 rows, 211 findings, header matches the manifest; the page matches the evidence` |
| `6ad680fc05a50128` | `aws-account.yaml` | complete, 6 findings, 2 informational | `OK  verified 226 rows, 8 findings, header matches the manifest; the page matches the evidence` |

`847b2b2514c14574` records `complete: false` in its chain header, so it replaces `41178d37bd0da182` as the documented
incomplete Crew night. `41178d37bd0da182` was written before the chain recorded completeness, is now taken as complete,
and fails (`complete: the page shows false, the evidence records no completeness, so the night is taken as complete;
billed total: the page shows $0.00, the evidence has $6,683.00; ...`). That is the intended verdict: it should go.

**The notes job**, `kirocrew cron trigger 9d342b56` at 13:07:02 local time, after the investigator was made read-only
(above), against the lab account through the gateway's read-only profile. The message was already
`{"checkout": "<checkout>"}`. The trigger returned at 13:07:06; Crew's history records
`"trigger": "manual"`, `"duration_ms": 1553`, `"status": "success"`, and the job `last_status: ok`, `last_error: null`,
at 12:07:08 UTC, with this `last_result`:

```
night_shift.py finished in <checkout>:
run 6ad680fc05a50128: 0 accepted, 0 rejected, 0 unavailable, 0 skipped; notes in runs\6ad680fc05a50128\evidence\notes.jsonl
```

`uv run nightaudit verify-notes runs/6ad680fc05a50128/evidence` printed `OK  no investigator's notes recorded`.

No finding was asked about, and that is the intended behaviour: `night_shift.py` opens only `new` findings in `OB`
and `O`, and all five on `6ad680fc05a50128` (`akiawcfihw3qdcdeagee`, `lab-debug`, `eni-085d97a8b514d1ce7`,
`i-0c8b3995db6d57788`, `vol-042dd68de0b61a0dd`) are `persisting` from the earlier lab night `1e9e38e57a33f5c4`. No
`notes.jsonl` was written, although the summary line names its path. The notes on those five findings are the ones
written on `1e9e38e57a33f5c4` by the 11:12 run (`771fc3b9`, gone since the reinstall); `uv run nightaudit verify-notes
runs/1e9e38e57a33f5c4/evidence` still prints `OK  evidence verifies; 5 notes verify (5 accepted)`.

Both jobs were paused again: `Paused job: 0af6390d`, `Paused job: 9d342b56`. `kirocrew cron list` then printed:

```
  ⏸ 0af6390d  night-shift/night-audit  (At 2:00 AM UTC)  {"checkout": "<checkout>"}
      owner: none (manage from CLI or the dashboard Schedule page)  created by: app:night-shift
  ⏸ 9d342b56  night-shift/night-notes  (At 2:30 AM UTC)  {"checkout": "<checkout>"}
      owner: none (manage from CLI or the dashboard Schedule page)  created by: app:night-shift
```

## Still not checked

* That the read-only investigator (without `aws-billing`) writes a note inside Crew: the 13:07 notes run had no new
  `OB` or `O` finding to ask about, so kiro-cli was not started. The 5 notes on `1e9e38e57a33f5c4` came from the
  agent while it still listed `@aws-billing`.
* That the Crew-registered `night-investigator` agent mounts its two servers in a Crew chat: no chat was opened. The
  notes job runs the checkout's own agent through kiro-cli, which reads `.kiro/settings/mcp.json`.
* A run that fires on its schedule at 02:00 or 02:30; both were started with `cron trigger`.
* A failed run inside Crew: only the missing-checkout path has failed inside Crew (above); the non-zero-exit and
  timeout paths are unit-tested only.
* That a timed-out `uv` subprocess on Windows also ends the Python process it started.
* `kirocrew app update` on a gateway that serves its Unix socket (Linux or macOS).
* The store icon (`iconPath`) and screenshots, which the manifest does not set.

The repository's hook `read-only-aws` and the agent permissions under `.kiro/agents/` apply to `kiro-cli`, which is how
`scripts/night_shift.py` runs the investigator. They are not Crew settings.
