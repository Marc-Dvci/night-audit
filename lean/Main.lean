import Lean.Data.Json
import NightAudit.Region

/-!
# `regions`: the model's region function as a program

Reads JSON Lines on standard input, one object per line:

    {"intended": ["k1", ...], "observed": [...], "billed": [...], "key": "k1"}

and prints one line for each: the region code of `key` (`I`, `O`, `B`, `IO`, `IB`, `OB`, `IOB`) or `none`.
A line that is not such an object prints `error: <reason>`, and the exit code is then 1.
The answer is `NightAudit.regionOf`, the function the theorems in `NightAudit/Partition.lean` are about.
-/

open Lean (Json)

/-- The field `name` of `j`, which must be an array of strings. -/
def keysField (j : Json) (name : String) : Except String (List String) := do
  let field ← j.getObjVal? name
  let items ← field.getArr?
  items.toList.mapM (fun item => item.getStr?)

/-- The output line for one input line. -/
def answer (line : String) : Except String String := do
  let j ← Json.parse line
  let intended ← keysField j "intended"
  let observed ← keysField j "observed"
  let billed ← keysField j "billed"
  let key ← (← j.getObjVal? "key").getStr?
  return NightAudit.regionCode (NightAudit.regionOf intended observed billed key)

/-- Answer each line until the end of the input; the result says whether any line was rejected. -/
partial def answerAll (stdin stdout : IO.FS.Stream) (failed : Bool) : IO Bool := do
  let line ← stdin.getLine
  if line == "" then
    return failed
  match answer line with
  | .ok code =>
    stdout.putStrLn code
    answerAll stdin stdout failed
  | .error message =>
    stdout.putStrLn s!"error: {message}"
    answerAll stdin stdout true

def main : IO UInt32 := do
  let stdin ← IO.getStdin
  let stdout ← IO.getStdout
  let failed ← answerAll stdin stdout false
  stdout.flush
  return (if failed then 1 else 0)
