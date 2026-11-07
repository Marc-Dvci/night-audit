# Demo account

A demo account (111122223333) over three nights, used for the no-login demo and the film.

| Night | What changed |
|---|---|
| 1 (4 Nov, 02:00 UTC) | Baseline: a snapshot billed that nobody approved or can see (Phantom), two resources that exist with no approval and cost nothing (Poltergeist), a NAT gateway approved and billed but not seen (Wraith), a deleted deployer user |
| 2 (5 Nov) | The declared audit trail disappears: approved, but gone (Skeleton). An unknown g5.xlarge appears in eu-north-1 at 03:17 on 4 Nov; it is not billed yet, so it is pending |
| 3 (6 Nov) | The instance and its volume reach the bill: two new resources running and billed with no approval (Vampire) |

Rebuild: `python apps/vampires/demo/build.py`
