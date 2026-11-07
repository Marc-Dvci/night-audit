import NightAudit.Region

/-!
# The partition law of region assignment

For any three finite ledgers of keys:

1. `every_key_has_a_region`: a key in any ledger has a region.
2. `no_key_outside_has_a_region`: a key in no ledger has none.
3. `region_is_exact`: a key's region names exactly the ledgers that contain it, so two different regions cannot hold
   one key (`two_regions_cannot_hold_one_key`).
4. `order_independent`: permuting the records of any ledger changes no key's region.
5. `duplicates_do_not_matter`: repeating a record in a ledger changes no key's region.
6. `partition_counts`: for a duplicate-free list of the keys in the union, the per-region key counts add up to the
   number of keys.

The proofs use `cases`, `by_cases`, `decide` on closed goals, `rw`, `simp`, `induction` and `omega`.
`NightAudit/Audit.lean` prints what each theorem depends on.
-/

namespace NightAudit

/-! ## The region function on three flags -/

/-- With at least one flag set, the flags name a region. -/
theorem regionOfFlags_some (x y z : Bool) (h : x = true ∨ y = true ∨ z = true) :
    ∃ r, regionOfFlags x y z = some r := by
  cases x <;> cases y <;> cases z
  all_goals first | exact ⟨_, rfl⟩ | exact absurd h (by decide)

/-- With no flag set, there is no region. -/
theorem regionOfFlags_none : regionOfFlags false false false = none := rfl

/-- The flags name region `r` exactly when they are `r`'s three ledgers. -/
theorem regionOfFlags_eq_some_iff (x y z : Bool) (r : Region) :
    regionOfFlags x y z = some r ↔ (x = r.inIntended ∧ y = r.inObserved ∧ z = r.inBilled) := by
  cases x <;> cases y <;> cases z <;> cases r <;> decide

/-- A decided proposition equals a flag exactly when the proposition holds just when the flag is `true`. -/
theorem decide_eq_iff_iff (p : Prop) [Decidable p] (c : Bool) : decide p = c ↔ (p ↔ c = true) := by
  by_cases hp : p
  · rw [decide_eq_true hp]
    cases c <;> simp [hp]
  · rw [decide_eq_false hp]
    cases c <;> simp [hp]

/-! ## 1-3: one region per key -/

/-- A key that is in at least one ledger has a region. -/
theorem every_key_has_a_region (i o b : List String) (k : String) (h : k ∈ i ∨ k ∈ o ∨ k ∈ b) :
    ∃ r, regionOf i o b k = some r :=
  regionOfFlags_some (decide (k ∈ i)) (decide (k ∈ o)) (decide (k ∈ b))
    (Or.imp decide_eq_true (Or.imp decide_eq_true decide_eq_true) h)

/-- A key that is in none of the three ledgers has no region. -/
theorem no_key_outside_has_a_region (i o b : List String) (k : String)
    (hi : k ∉ i) (ho : k ∉ o) (hb : k ∉ b) : regionOf i o b k = none := by
  show regionOfFlags (decide (k ∈ i)) (decide (k ∈ o)) (decide (k ∈ b)) = none
  rw [decide_eq_false hi, decide_eq_false ho, decide_eq_false hb, regionOfFlags_none]

/-- A key is in region `r` exactly when, for each ledger, the key is in that ledger just when `r` names it. -/
theorem region_is_exact (i o b : List String) (k : String) (r : Region) :
    regionOf i o b k = some r ↔
      ((k ∈ i ↔ r.inIntended = true) ∧ (k ∈ o ↔ r.inObserved = true) ∧ (k ∈ b ↔ r.inBilled = true)) := by
  unfold regionOf
  rw [regionOfFlags_eq_some_iff, decide_eq_iff_iff (k ∈ i), decide_eq_iff_iff (k ∈ o),
    decide_eq_iff_iff (k ∈ b)]

/-- Two different regions cannot both hold the same key. -/
theorem two_regions_cannot_hold_one_key (i o b : List String) (k : String) (r₁ r₂ : Region)
    (hne : r₁ ≠ r₂) : ¬(regionOf i o b k = some r₁ ∧ regionOf i o b k = some r₂) :=
  fun ⟨h₁, h₂⟩ => hne (Option.some.inj (h₁.symm.trans h₂))

/-! ## 4-5: record order and repeated records -/

/-- Two ledgers with the same members give every key the same membership answer. -/
theorem decide_mem_congr {l l' : List String} (h : ∀ x, x ∈ l ↔ x ∈ l') (k : String) :
    decide (k ∈ l) = decide (k ∈ l') := by
  by_cases hk : k ∈ l
  · have hk' : k ∈ l' := (h k).mp hk
    rw [decide_eq_true hk, decide_eq_true hk']
  · have hk' : k ∉ l' := fun hin => hk ((h k).mpr hin)
    rw [decide_eq_false hk, decide_eq_false hk']

/-- A key's region depends only on which keys each ledger holds, not on how the ledger lists them. -/
theorem region_depends_only_on_membership {i i' o o' b b' : List String}
    (hi : ∀ x, x ∈ i ↔ x ∈ i') (ho : ∀ x, x ∈ o ↔ x ∈ o') (hb : ∀ x, x ∈ b ↔ x ∈ b') (k : String) :
    regionOf i o b k = regionOf i' o' b' k := by
  unfold regionOf
  rw [decide_mem_congr hi k, decide_mem_congr ho k, decide_mem_congr hb k]

/-- Putting the records of any ledger, or of all three, in another order changes no key's region. -/
theorem order_independent {i i' o o' b b' : List String}
    (hi : List.Perm i i') (ho : List.Perm o o') (hb : List.Perm b b') (k : String) :
    regionOf i o b k = regionOf i' o' b' k :=
  region_depends_only_on_membership (fun _ => hi.mem_iff) (fun _ => ho.mem_iff) (fun _ => hb.mem_iff) k

/-- Inserting a copy of a record anywhere in a ledger leaves the ledger's members unchanged. -/
theorem mem_with_repeat_iff {l₁ l₂ : List String} {x : String} (hx : x ∈ l₁ ++ l₂) (k : String) :
    k ∈ l₁ ++ x :: l₂ ↔ k ∈ l₁ ++ l₂ := by
  simp only [List.mem_append, List.mem_cons]
  constructor
  · intro h
    rcases h with h | h | h
    · exact Or.inl h
    · subst h
      exact List.mem_append.mp hx
    · exact Or.inr h
  · intro h
    rcases h with h | h
    · exact Or.inl h
    · exact Or.inr (Or.inr h)

/-- Repeating a record that a ledger already holds, at any position in the intended, observed or billed ledger,
changes no key's region. -/
theorem duplicates_do_not_matter (i o b l₁ l₂ : List String) (x k : String) (hx : x ∈ l₁ ++ l₂) :
    regionOf (l₁ ++ x :: l₂) o b k = regionOf (l₁ ++ l₂) o b k ∧
      regionOf i (l₁ ++ x :: l₂) b k = regionOf i (l₁ ++ l₂) b k ∧
      regionOf i o (l₁ ++ x :: l₂) k = regionOf i o (l₁ ++ l₂) k :=
  ⟨region_depends_only_on_membership (mem_with_repeat_iff hx) (fun _ => Iff.rfl) (fun _ => Iff.rfl) k,
    region_depends_only_on_membership (fun _ => Iff.rfl) (mem_with_repeat_iff hx) (fun _ => Iff.rfl) k,
    region_depends_only_on_membership (fun _ => Iff.rfl) (fun _ => Iff.rfl) (mem_with_repeat_iff hx) k⟩

/-! ## 6: counting keys per region -/

/-- The keys of `ks` whose region is `r`. -/
def keysIn (i o b : List String) (r : Region) (ks : List String) : List String :=
  ks.filter (fun k => decide (regionOf i o b k = some r))

/-- Counting the keys of `k :: rest` in region `r`: one for `k` if its region is `r`, plus the count for `rest`. -/
theorem length_keysIn_cons (i o b : List String) (r : Region) (k : String) (rest : List String) :
    (keysIn i o b r (k :: rest)).length =
      (if regionOf i o b k = some r then 1 else 0) + (keysIn i o b r rest).length := by
  unfold keysIn
  by_cases h : regionOf i o b k = some r <;> simp [List.filter_cons, h] <;> omega

/-- A value that is some region is equal to exactly one of the seven regions. -/
theorem one_region (x : Option Region) (hx : ∃ r, x = some r) :
    (if x = some Region.I then 1 else 0) + (if x = some Region.O then 1 else 0) +
      (if x = some Region.B then 1 else 0) + (if x = some Region.IO then 1 else 0) +
      (if x = some Region.IB then 1 else 0) + (if x = some Region.OB then 1 else 0) +
      (if x = some Region.IOB then 1 else 0) = 1 := by
  obtain ⟨r, rfl⟩ := hx
  cases r <;> first | decide | simp

/-- For any list of keys that are each in some ledger, the per-region counts add up to the list's length. -/
theorem partition_counts_of_cover (i o b ks : List String)
    (hcover : ∀ k, k ∈ ks → k ∈ i ∨ k ∈ o ∨ k ∈ b) :
    (keysIn i o b .I ks).length + (keysIn i o b .O ks).length + (keysIn i o b .B ks).length +
      (keysIn i o b .IO ks).length + (keysIn i o b .IB ks).length +
      (keysIn i o b .OB ks).length + (keysIn i o b .IOB ks).length = ks.length := by
  induction ks with
  | nil => simp [keysIn]
  | cons key rest ih =>
    have hkey : key ∈ i ∨ key ∈ o ∨ key ∈ b := hcover key (by simp)
    have hrest : ∀ k, k ∈ rest → k ∈ i ∨ k ∈ o ∨ k ∈ b := fun k hk => hcover k (by simp [hk])
    have hone := one_region (regionOf i o b key) (every_key_has_a_region i o b key hkey)
    have hsum := ih hrest
    simp only [length_keysIn_cons, List.length_cons]
    omega

/-- Take the keys of the union of the three ledgers as a list `ks` with no repeats. Then the number of keys in each
region, added over the seven regions, is the number of keys in the union. The count equation holds for any list
whose keys are all in the union (`partition_counts_of_cover`); `ks.Nodup` is what makes `ks.length` the number of
distinct keys. -/
theorem partition_counts (i o b ks : List String) (_hnodup : ks.Nodup)
    (hunion : ∀ k, k ∈ ks ↔ k ∈ i ∨ k ∈ o ∨ k ∈ b) :
    (keysIn i o b .I ks).length + (keysIn i o b .O ks).length + (keysIn i o b .B ks).length +
      (keysIn i o b .IO ks).length + (keysIn i o b .IB ks).length +
      (keysIn i o b .OB ks).length + (keysIn i o b .IOB ks).length = ks.length :=
  partition_counts_of_cover i o b ks (fun k hk => (hunion k).mp hk)

end NightAudit
