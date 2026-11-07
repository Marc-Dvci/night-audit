import NightAudit.Partition

/-!
# What each proof rests on

`lake env lean NightAudit/Audit.lean` prints, for each theorem, the axioms it depends on. CI accepts only `propext`,
`Classical.choice` and `Quot.sound`, and fails on `sorryAx` (an unfinished proof) and on `Lean.ofReduceBool` or
`Lean.trustCompiler` (a proof that trusts compiled code).
-/

#print axioms NightAudit.every_key_has_a_region
#print axioms NightAudit.no_key_outside_has_a_region
#print axioms NightAudit.region_is_exact
#print axioms NightAudit.two_regions_cannot_hold_one_key
#print axioms NightAudit.order_independent
#print axioms NightAudit.duplicates_do_not_matter
#print axioms NightAudit.partition_counts
#print axioms NightAudit.partition_counts_of_cover
#print axioms NightAudit.region_depends_only_on_membership
#print axioms NightAudit.regionOfFlags_eq_some_iff
