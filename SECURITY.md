# Security

## Reporting a problem

Use GitHub's private vulnerability reporting on this repository (**Security → Report a vulnerability**). Please do not
open a public issue for a security problem.

Reports that matter most:

- the live endpoint (`https://o7hhjtbm3mydyatsvlz7t3teli0fqski.lambda-url.us-east-1.on.aws/`): anything that reads
  more than the published nights, writes anything, or runs code;
- the evidence chain: a page or a pack that differs from its evidence and still passes `nightaudit verify` or the
  page's own Verify this night;
- the explanation guard: a model explanation or an investigator's note that shows a number absent from the finding's
  evidence;
- the read-only claims: any call from a connector, the investigator or the deployed roles that changes an account.

## What the deployed roles can do

From [`deploy/stack.yaml`](deploy/stack.yaml):

| Role | Can | Cannot |
|---|---|---|
| `NightlyRole` (the nightly audit) | `ReadOnlyAccess`; read Cost Explorer and Data Exports; `s3:PutObject` under `nights/` in its own runs bucket; write its own log group | Write to any other bucket, or create, change or delete any resource |
| `WebRole` (the page and the API) | List the runs bucket; read objects under `nights/`; write its own log group | Read anything outside `nights/`, or write to S3 |
| `SchedulerRole` (EventBridge Scheduler) | Invoke the nightly function | Anything else |

The page is served with a Content Security Policy that allows only its own scripts, and ledger text (tags, names,
descriptions) is shown as text, never as markup.
