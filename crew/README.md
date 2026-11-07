# Night shift: the Kiro Crew app

`crew/night-shift/` is a Kiro Crew app. Its manifest declares two daily crons, an investigator agent and a skill.

| Cron | When (UTC) | What it is declared to do | Time limit |
|---|---|---|---|
| `night-audit` | 02:00, exactly on the minute (`strict_schedule`) | Runs `scripts/nightly.py`, which runs `nightaudit run` for each control under `apps/*/controls/` (files there without a top-level `ledgers` key are settings, not controls, and are skipped). No model is called. | `timeout` 1200 s for the command, 1500 s for the whole run |
| `night-investigator` | 02:30, exactly on the minute | Starts the `night-investigator` agent and asks it to look at each new finding in region `OB` or `O`. | 3600 s for the whole run |

Both crons are declared with `"enabled": false`, so Crew registers them paused. The `night-audit` command contains the
placeholder `REPLACE_WITH_NIGHT_AUDIT_CHECKOUT`; it does nothing useful until you replace it.

The agent declares the tools `read`, `@aws-api` and `@aws-cloudtrail` and no tool that writes. The manifest asks Crew
for one permission, `"cron": true`, which Crew's documentation requires for any app that declares crons.

## Notes are recorded by the script, not by the agent

The agent cron and `scripts/night_shift.py` are two separate routes to an investigator's note.

* `scripts/night_shift.py` launches `kiro-cli chat --v3 ... --agent night-investigator` for each new `OB` and `O`
  finding, checks the note's numbers against the finding's evidence, and appends the verdict to
  `runs/<run_id>/evidence/notes.jsonl` as a hash chain bound to the run. Verify it with
  `uv run nightaudit verify-notes runs/<run_id>/evidence`. The page shows only notes recorded this way.
* The `night-investigator` cron runs the agent inside Crew. Its reply is kept by Crew. Nothing in this app takes that
  reply, checks it and writes it to `notes.jsonl`. To get checked notes onto the page, run `scripts/night_shift.py`
  after the cron, by hand or from your own scheduler.

## Install

These are the steps in the App Kit's *Getting Started*. Run them yourself; this repository has not run them.

1. Install Kiro Crew and start it: `kirocrew gateway`.
2. Install the app from its absolute path:

   ```bash
   kirocrew app install /absolute/path/to/night-audit/crew/night-shift
   ```

3. Trust the app. Enable refuses an app that is not built in until the operator trusts it. Either enable it from the
   App Store, which asks you to trust this app alone, or use Settings → Security → Third-party apps.
4. Enable it:

   ```bash
   kirocrew app enable night-shift
   ```

5. Open the Schedule page and set up the two crons:
   * Replace `REPLACE_WITH_NIGHT_AUDIT_CHECKOUT` in the `night-audit` command with the absolute path of your Night Audit
     checkout, then resume the cron. The checkout needs `uv sync` done once.
   * Check the approval mode of the `night-investigator` job. A job that waits for tool approvals nobody is present to
     give does not finish; the App Kit documents `approval_mode="auto"` for unattended agent jobs in the cron SDK, and
     the manifest's cron fields do not list it.
   * Resume the `night-investigator` cron.

Disabling the app deletes its registered crons; enabling it again registers them paused, from the manifest.

## Not checked

Kiro Crew is not installed on the machine this was written on. Nothing here has been installed, enabled or scheduled in
Crew. In particular, these are not confirmed:

* that Crew accepts the manifest (the repository's test checks it against the rules in the App Kit documents only);
* the working directory and shell of a `command` cron, which is why the checkout path is written into the command;
* that the tools `read`, `@aws-api` and `@aws-cloudtrail` resolve in Crew, and that Crew keeps the agent read-only;
* that the approval mode of an agent cron allows an unattended run;
* the store icon (`iconPath`) and screenshots, which the manifest does not set.

The repository's own hook `read-only-aws` and the agent permissions under `.kiro/agents/` apply to `kiro-cli`, which
is how `scripts/night_shift.py` runs the investigator. They are not Crew settings.
