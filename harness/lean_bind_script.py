"""lean_bind_script.py -- the Lean program behind the task binding check.

harness/lean_binding.py writes this source to a temporary file and runs it
with `lean --run`. It is kept as a Python string so the frozen installer and
the wheel carry it with no package-data entry. It prints one JSON object:
`status` is `bound`, `refused`, `unsupported` or `error`; `refusals` lists
why a binding failed; `axioms` lists every axiom the candidate's theorem
depends on; `statement_canonical` is the challenge statement as the
toolchain elaborated it (`Expr` printed by the toolchain's own printer).
"""

SOURCE = r"""import Lean
open Lean

/-! Flywheel task binding check. It reads the candidate's compiled module as
data (`readModuleData`), so no candidate code runs in this process. It imports
the trusted challenge module and the candidate's own imports, then checks three
things: the pinned theorem exists in the candidate with the challenge's exact
type, every constant that type reaches means the same thing on both sides, and
the axioms the candidate's theorem depends on, walked from the artifact rather
than read from a precomputed table. Usage:
`lean --run Bind.lean <candidate.olean> <challenge module> <theorem name>` -/

abbrev Errs := StateM (Array String)

def err (msg : String) : Errs Unit := modify (·.push msg)

/-- Where a name resolves for one side: `some module` or `none`. The candidate's
own declarations resolve to `Candidate`; a challenge-module name is invisible
to the candidate side. -/
def originOf (env : Environment) (own : NameMap ConstantInfo) (chMod : Name)
    (cand : Bool) (n : Name) : Option Name :=
  if cand && own.contains n then some `Candidate
  else match env.getModuleIdxFor? n with
    | some i =>
      let m := env.header.moduleNames[i.toNat]!
      if cand && m == chMod then none else some m
    | none => none

def findOn (env : Environment) (own : NameMap ConstantInfo) (chMod : Name)
    (cand : Bool) (n : Name) : Option ConstantInfo :=
  if cand && own.contains n then own.find? n
  else if (originOf env own chMod cand n).isSome then env.find? n else none

/-- Exact declaration equality for a constant the challenge module declares.
A theorem compares by statement only: its proof does not change what the
pinned statement means. -/
def sameDecl : ConstantInfo → ConstantInfo → Bool
  | .defnInfo a, .defnInfo b => a.levelParams == b.levelParams && a.type == b.type
      && a.value == b.value && a.safety == b.safety
  | .thmInfo a, .thmInfo b => a.levelParams == b.levelParams && a.type == b.type
  | .opaqueInfo a, .opaqueInfo b => a == b
  | .axiomInfo a, .axiomInfo b => a == b
  | .inductInfo a, .inductInfo b => a.toConstantVal == b.toConstantVal
      && a.numParams == b.numParams && a.numIndices == b.numIndices
      && a.all == b.all && a.ctors == b.ctors && a.numNested == b.numNested
      && a.isRec == b.isRec && a.isUnsafe == b.isUnsafe && a.isReflexive == b.isReflexive
  | .ctorInfo a, .ctorInfo b => a == b
  | .recInfo a, .recInfo b => a.toConstantVal == b.toConstantVal && a.all == b.all
      && a.numParams == b.numParams && a.numIndices == b.numIndices
      && a.numMotives == b.numMotives && a.numMinors == b.numMinors
      && a.k == b.k && a.isUnsafe == b.isUnsafe
      && (a.rules.map (·.rhs)) == (b.rules.map (·.rhs))
  | .quotInfo a, .quotInfo b => a.toConstantVal == b.toConstantVal
  | _, _ => false

/-- The constants a challenge declaration's meaning depends on. -/
def meaningDeps : ConstantInfo → Array Name
  | .defnInfo v => v.type.getUsedConstants ++ v.value.getUsedConstants
  | .opaqueInfo v => v.type.getUsedConstants ++ v.value.getUsedConstants
  | .inductInfo v => v.type.getUsedConstants ++ v.ctors.toArray
  | .recInfo v => v.type.getUsedConstants
      ++ (v.rules.toArray.flatMap (·.rhs.getUsedConstants))
  | c => c.type.getUsedConstants

/-- Every constant the pinned statement reaches must mean the same thing on
both sides: an imported constant must come from the same module, and a
constant the challenge declares must be declared identically by the candidate. -/
partial def bindWalk (env : Environment) (own : NameMap ConstantInfo)
    (chMod : Name) : List Name → NameSet → Errs Unit
  | [], _ => pure ()
  | n :: rest, seen => do
    if seen.contains n then return (← bindWalk env own chMod rest seen)
    let seen := seen.insert n
    let some oc := originOf env own chMod false n
      | do err s!"the pinned statement uses {n}, which the challenge does not resolve"
           bindWalk env own chMod rest seen
    let os := originOf env own chMod true n
    let mut next := rest
    if oc == chMod then
      match env.find? n, own.find? n with
      | some cc, some sc =>
        unless sameDecl cc sc do
          err s!"{n} differs from the challenge's declaration (shadowed or altered)"
        next := (meaningDeps cc).toList ++ rest
      | _, _ => err s!"the pinned statement uses {n}, which the candidate does not declare"
    else if os != some oc then
      err s!"{n} resolves to {os.getD `none} in the candidate, not to {oc}"
    bindWalk env own chMod next seen

/-- Axioms the candidate's theorem depends on, read from the compiled
artifact and the imported environment, never from a precomputed table. An
unresolvable constant is reported, not skipped. -/
partial def axiomWalk (env : Environment) (own : NameMap ConstantInfo)
    (chMod : Name) : List Name → NameSet → Array Name → Array Name →
    (Array Name × Array Name)
  | [], _, axs, miss => (axs, miss)
  | n :: rest, seen, axs, miss =>
    if seen.contains n then axiomWalk env own chMod rest seen axs miss else
    let seen := seen.insert n
    match findOn env own chMod true n with
    | none => axiomWalk env own chMod rest seen axs (miss.push n)
    | some c =>
      let axs := if c matches .axiomInfo _ then axs.push n else axs
      let deps := match c with
        | .inductInfo v => v.type.getUsedConstants ++ v.ctors.toArray
        | _ => c.type.getUsedConstants ++ ((c.value? (allowOpaque := true)).map Expr.getUsedConstants).getD #[]
      axiomWalk env own chMod (deps.toList ++ rest) seen axs miss

def strs (xs : Array Name) : Json := Json.arr (xs.map (Json.str ·.toString))

def run (olean : String) (chMod thm : Name) : IO Json := do
  initSearchPath (← findSysroot)
  let (mod, _) ← readModuleData olean
  if mod.isModule then
    return Json.mkObj [("status", "unsupported"),
      ("detail", "the candidate is a `module` file; its proofs may sit in a "
        ++ "part this check does not read")]
  for i in mod.imports do
    if i.module == chMod || i.module == `Candidate then
      return Json.mkObj [("status", "refused"), ("refusals", Json.arr
        #[Json.str s!"the candidate imports {i.module}"])]
  let env ← importModules (#[{ module := chMod }] ++ mod.imports) {}
  let mut own : NameMap ConstantInfo := {}
  let mut clash : Array String := #[]
  for c in mod.constants do
    if env.contains c.name && (env.getModuleIdxFor? c.name).isSome then
      if !(originOf env {} chMod false c.name == some chMod) then
        clash := clash.push s!"the candidate redeclares imported {c.name}"
    own := own.insert c.name c
  let some chC := env.find? thm
    | return Json.mkObj [("status", "error"),
        ("detail", s!"the challenge declares no {thm}")]
  let canon := s!"{thm}.{chC.levelParams} : {chC.type}"
  let mut refusals := clash
  let mut candCanon := ""
  match own.find? thm with
  | some (.thmInfo v) =>
    candCanon := s!"{thm}.{v.levelParams} : {v.type}"
    unless v.levelParams == chC.levelParams && v.type == chC.type do
      refusals := refusals.push s!"{thm} states a different proposition than the challenge"
  | some _ => refusals := refusals.push s!"{thm} is not a theorem in the candidate"
  | none => refusals := refusals.push s!"the candidate declares no top-level {thm}"
  let ((), walkErrs) := (bindWalk env own chMod chC.type.getUsedConstants.toList {}).run #[]
  refusals := refusals ++ walkErrs
  let (axs, miss) := if own.contains thm
    then axiomWalk env own chMod [thm] {} #[] #[] else (#[], #[])
  for n in miss do
    refusals := refusals.push s!"the proof depends on {n}, which resolves nowhere"
  let sorted := axs.qsort Name.lt
  return Json.mkObj [
    ("status", if refusals.isEmpty then "bound" else "refused"),
    ("theorem", thm.toString), ("statement_canonical", canon),
    ("candidate_canonical", candCanon), ("axioms", strs sorted),
    ("refusals", Json.arr (refusals.map Json.str)),
    ("lean_version", Lean.versionString), ("lean_githash", Lean.githash)]

def main (args : List String) : IO UInt32 := do
  match args with
  | [olean, chMod, thm] =>
    try
      IO.println (← run olean chMod.toName thm.toName).compress
      return 0
    catch e =>
      IO.println (Json.mkObj [("status", "error"), ("detail", toString e)]).compress
      return 0
  | _ => IO.eprintln "usage: Bind <candidate.olean> <challenge module> <theorem>"; return 2
"""
