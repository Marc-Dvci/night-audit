# Planting the lab findings

Run with an administrator profile, never with the read-only `night-audit` profile.

1. Deploy the declared workload:
   `aws cloudformation deploy --stack-name night-audit-lab --template-file lab/night-audit-lab.yaml --capabilities CAPABILITY_NAMED_IAM --tags night-audit:intended=true project=night-audit-lab`
2. Running and billed, never approved: launch an untagged `t4g.micro` in a region the account does not use (eu-north-1 here).
3. Exists, never approved, free: `aws iam create-user --user-name lab-debug`, then create an access key for it and set the key to
   `Inactive` straight away. The secret is never stored.
4. Approved, but gone: `aws iam delete-user --user-name night-audit-lab-deployer` (drift from the stack).
5. Write `lab/expected.yaml` before the first audit.
6. Wait for one full billing day plus the grace window (36 hours) before the night that should show the planted instance.
