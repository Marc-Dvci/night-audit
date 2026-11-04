# Cleaning the lab

1. Terminate the vampire instance in eu-north-1.
2. Delete the access key of `lab-debug`, then delete the user.
3. Delete the stack: `aws cloudformation delete-stack --stack-name night-audit-lab`. Empty the lab bucket first.
4. Keep `lab/expected.yaml` in the repository as the record of what was planted.
