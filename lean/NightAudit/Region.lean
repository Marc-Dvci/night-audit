/-!
# Region assignment, as a pure model

This file models the region computation in `skeleton/src/nightaudit/matcher.py`:

* lines 35-44, `_region_code(present)`: the ledger initials present, joined in I-O-B order;
* lines 174-188, step 3: `keys_in_ledger[ledger]` is the set of normalised keys that ledger's records carry;
* lines 209-216, step 5: for each key, `present` is the set of ledgers whose key set contains it, and
  `regions[key] = _region_code(present)`.

Here a ledger is the list of its records' keys, already normalised and non-empty, in record order and with repeats.
`regionOf` asks only whether the key is a member of each list, as step 5 asks `key in keys_in_ledger[ledger]`.

Not modelled: normalisation (step 1), scope and exclusion (step 2), unkeyed records (an empty normalised key, which
step 3 drops), the grace window (step 4, which removes pending keys before step 5), findings, amounts and summaries.
-/

namespace NightAudit

/-- The seven regions. Each name lists the ledgers that hold the key, in I-O-B order. -/
inductive Region where
  | I
  | O
  | B
  | IO
  | IB
  | OB
  | IOB
  deriving DecidableEq, Repr

/-- The region code as `_region_code` writes it. -/
def Region.code : Region → String
  | .I => "I"
  | .O => "O"
  | .B => "B"
  | .IO => "IO"
  | .IB => "IB"
  | .OB => "OB"
  | .IOB => "IOB"

/-- Whether the region includes the intended ledger. -/
def Region.inIntended : Region → Bool
  | .I | .IO | .IB | .IOB => true
  | .O | .B | .OB => false

/-- Whether the region includes the observed ledger. -/
def Region.inObserved : Region → Bool
  | .O | .IO | .OB | .IOB => true
  | .I | .B | .IB => false

/-- Whether the region includes the billed ledger. -/
def Region.inBilled : Region → Bool
  | .B | .IB | .OB | .IOB => true
  | .I | .O | .IO => false

/-- The region named by three membership flags (intended, observed, billed), or `none` when no flag is set. -/
def regionOfFlags : Bool → Bool → Bool → Option Region
  | true, true, true => some .IOB
  | true, true, false => some .IO
  | true, false, true => some .IB
  | true, false, false => some .I
  | false, true, true => some .OB
  | false, true, false => some .O
  | false, false, true => some .B
  | false, false, false => none

/-- The region of `key`, given the keys of the three ledgers. A key in none of them has no region. -/
def regionOf (intended observed billed : List String) (key : String) : Option Region :=
  regionOfFlags (decide (key ∈ intended)) (decide (key ∈ observed)) (decide (key ∈ billed))

/-- What the executable prints: the region code, or `none`. -/
def regionCode : Option Region → String
  | some r => r.code
  | none => "none"

end NightAudit
