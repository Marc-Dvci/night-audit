# own-build

Night Audit audits its own build. A new reconciliation is one control file away: `controls/own-build.yaml` is the control,
and this folder holds the three small connectors it names. The skeleton is unchanged.

| Ledger | Question | Source |
|---|---|---|
| Intended | What did the specs promise? | File paths in backticks in `.kiro/specs/*/design.md`, `tasks.md` and `requirements.md`, from `data/spec-files.csv` |
| Observed | What exists? | The files git tracks at one commit, `data/tracked-files.csv` |
| Billed | What did Kiro work on? | `data/kiro-files.csv` (one row per file and session), `data/kiro-sessions.csv` |

The key is the repository file path. The noun is file and files.

## The credits are an allocation, not a measurement

A Kiro session reports one credit figure for the whole session. `kiro-files.csv` gives each file the session touched an
equal share of it (`credit_share`). **That equal split is an allocation chosen for this audit. It does not measure what any
one file cost.** A large session that touched 64 files gives each file the same share as it gives a file it worked on for
an hour. Read the credit column as "how much of the credit of the sessions that touched this file it carries", not as
"what this file cost".

- The amount is **Kiro credits, not money**. The page prints every amount with a dollar sign because the skeleton's money
  format has no other unit; read `$679.1619` as 679.1619 credits.
- A session stopped before it reported credits has a blank share. A blank share counts as zero and the line is kept, so
  the file is still on the billed ledger.
- Credits spent in a session that touched no file belong to no file, so the file totals are lower than the sessions' total.
  The run's notes say so.
- The export holds no prompt and no reply: file paths, session ids, model names, times and credits only.

## What "the spec promises a file" means

A backticked span in a spec names a file when it is one path of `/`-separated segments (letters, digits, `.`, `_`, `-`),
with at least one `/`, whose last segment ends in a dot and a letter-led extension. The rule was fixed before any data was
read and is in `src/own_build/paths.py`. The parser never looks at the repository.

So these are **not** files, and are not read: a directory (`lean/`), a glob (`.kiro/hooks/*.json`), a template
(`runs/<id>/run.json`), a bare name (`report.py`, `pyproject.toml`), a dotted identifier (`ghosts.review`), a command, and
anything in a fenced block. A path written relative to another folder (`tests/test_x.py` meaning `skeleton/tests/...`) is read
as written, so it can show as promised and never built. That is the cost of not letting the repository decide what a spec
meant, and the run's notes say it.

## Regions

| Code | Name | Meaning |
|---|---|---|
| `IOB` | Spec'd and built with Kiro | Matched |
| `OB` | Built with Kiro, no spec names it | A spec gap, or a spec that names a folder and not the file |
| `O` | Written by hand or generated | No spec, no Kiro session in the export. Specs, hooks, steering and generated data land here, which is right |
| `I` | Promised by a spec, never built | See the reading rules above before believing it |
| `IB` | Built, spec'd, gone | Kiro worked on it, a spec names it, git does not track it |
| `B` | Kiro worked on it, no spec, it is gone | Renamed, deleted or never committed |
| `IO` | Spec'd, no Kiro | A spec names it and it exists, but no Kiro session in the export touched it. Informational |

`IB` and `IO` have short names because the Venn prints a region's name inside the region, and the two lens regions are
narrow. Their full sentences are the regions' `meaning` in the control.

## Run it again

```text
uv run python apps/own-build/snapshot.py           # record HEAD: tracked-files.csv and spec-files.csv
uv run python scripts/build_demos.py own-build     # run the night and write the demo
```

The snapshot is `git ls-tree -r` at the commit, which is the list `git ls-files` gives in a clean checkout of it, and the spec
documents are read from the same commit. It runs only `rev-parse`, `ls-tree` and `cat-file`. Untracked and staged work is not
in it, so a file written after the recorded commit is not audited until the snapshot is taken again.

Kiro's two files come from Kiro's own session store and are not produced by this repository.

## Tests

`uv run pytest apps/own-build -q`. The casebook is `casebook/cases.yaml`: eight tiny repositories (one healthy) and nine
parser cases, written before the connectors existed.
