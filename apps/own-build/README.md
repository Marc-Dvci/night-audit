# own-build

Night Audit audits its own build. A new reconciliation is one control file away: `controls/own-build.yaml` is the control,
and this folder holds the three small connectors it names. The skeleton is unchanged.

| Ledger | Question | Source |
|---|---|---|
| Intended | What did the specs promise? | File paths and folders in backticks in `.kiro/specs/*/design.md`, `tasks.md` and `requirements.md`, resolved against the tracked files, from `data/spec-files.csv` |
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

Two steps, both fixed in `src/own_build/paths.py` and checked by the casebook (`parser`, `folders` and `resolve` sections).

**Reading a spec.** A backticked span in a spec names a file when it is one path of `/`-separated segments (letters,
digits, `.`, `_`, `-`), with at least one `/`, whose last segment ends in a dot and a letter-led extension. It names a
folder when it is the same kind of path and ends in `/` (`apps/ghosts/`). Reading never looks at the repository.

**Resolving a span.** The snapshot holds the specs and the tracked list of one commit, so it resolves each span there:

1. A file span that is a tracked file names that file.
2. Otherwise a file span that ends exactly one tracked path, at a `/`, names that path (`tests/test_x.py` names
   `skeleton/tests/test_x.py` when no other tracked path ends in `/tests/test_x.py`).
3. Otherwise the span stays as written. With no match, or with two or more, it names no single file, and it shows as
   promised and never built.
4. A folder span intends every tracked file under it, read from the repository root. A folder that holds no tracked file
   intends nothing.
5. A path with a `dist` or `node_modules` segment is build output, not a promise. Two paths in the night-shift design
   (`tests/test_contracts.py`, `tests/test_casebook.py`) are files the Kiro power writes into the user's own project, so
   they are not promises either (`NOT_PROMISES`).

So these are **not** files: a glob (`.kiro/hooks/*.json`), a template (`runs/<id>/run.json`), a bare name (`report.py`,
`pyproject.toml`), a dotted identifier (`ghosts.review`), a command, and anything in a fenced block. A bare name has no
directory to resolve, so the files a spec names only that way are not promised.

**Why the rules are in two steps.** The first recorded night read paths as written and reported 32 files promised and
never built. Reading those 32 showed that 26 were relative paths, folders or build output. The rules above resolve
them, and the same night recorded again gives 6. Three of the 6 are paths that no longer exist (the spec text has been
corrected since the recorded commit); three are not resolved: `assets/verify.js` is a path inside the build output,
`demo/build.py` ends three tracked files and `references/region-table.md` ends two.

## Regions

| Code | Name | Meaning |
|---|---|---|
| `IOB` | Spec'd and built with Kiro | Matched |
| `OB` | Built with Kiro, no spec names it | A spec gap: no spec names the file, a path that ends in it, or a folder that holds it |
| `O` | Written by hand or generated | No spec, no Kiro session in the export. Specs, hooks, steering and generated data land here, which is right |
| `I` | Promised by a spec, never built | A spec names a path that ends no tracked file or more than one, and no Kiro session touched it |
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
documents are read from the same commit and resolved against that list. It runs only `rev-parse`, `ls-tree` and `cat-file`.
Untracked and staged work is not in it: a file or a spec edit written after the recorded commit is not audited until the
snapshot is taken again. The recorded commit is named in both files (`commit` column).

Kiro's two files come from Kiro's own session store and are not produced by this repository.

## Tests

`uv run pytest apps/own-build -q`. The casebook is `casebook/cases.yaml`: nine tiny repositories (one healthy), nine
parser cases, six folder cases and thirteen resolution cases.
