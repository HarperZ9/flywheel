import Mathlib.Data.ZMod.Basic

/-!
# Proof by reflection for RECEIPT column identities

One column `k` of a RECEIPT v1.0 identity reads, over `ZMod p`,

    sum_i lam_i * R_i[k]  =  [k = t]  -  c_k

where `c_k` is the certified coefficient on column `k` (zero when `k` is not a
key of `c`). `ColOK p ts pos neg` states exactly that, with `ts` the list of
`(lam_i, R_i[k])` pairs, `pos` the value of `[k = t]` and `neg` the value of
`c_k`. `colCheck` decides it with natural-number arithmetic, which the Lean
kernel evaluates with GMP-backed literals, and `colCheck_sound` proves that a
`true` answer implies `ColOK`. The kernel therefore checks every column by
evaluating `allCheck` once.

No `sorry`, no `native_decide`, no `implemented_by`, no new axioms.
-/

namespace ReceiptLean

/-- Sum of `l * v` over the list, reduced mod `p` after every step. -/
def colSumNat (p : ℕ) : List (ℕ × ℕ) → ℕ
  | [] => 0
  | x :: xs => (x.1 * x.2 + colSumNat p xs) % p

/-- The statement for one column, over `ZMod p`. -/
def ColOK (p : ℕ) (ts : List (ℕ × ℕ)) (pos neg : ℕ) : Prop :=
  (ts.map (fun x => (x.1 : ZMod p) * (x.2 : ZMod p))).sum = (pos : ZMod p) - (neg : ZMod p)

/-- The statement for every listed column of one witness. -/
def AllOK (p : ℕ) (cols : List (List (ℕ × ℕ) × ℕ × ℕ)) : Prop :=
  ∀ e ∈ cols, ColOK p e.1 e.2.1 e.2.2

def colCheck (p : ℕ) (ts : List (ℕ × ℕ)) (pos neg : ℕ) : Bool :=
  (colSumNat p ts + neg) % p == pos % p

def allCheck (p : ℕ) : List (List (ℕ × ℕ) × ℕ × ℕ) → Bool
  | [] => true
  | e :: es => colCheck p e.1 e.2.1 e.2.2 && allCheck p es

theorem colSumNat_cast (p : ℕ) (ts : List (ℕ × ℕ)) :
    ((colSumNat p ts : ℕ) : ZMod p) = (ts.map (fun x => (x.1 : ZMod p) * (x.2 : ZMod p))).sum := by
  induction ts with
  | nil => simp [colSumNat]
  | cons x xs ih =>
    simp only [colSumNat, ZMod.natCast_mod, Nat.cast_add, Nat.cast_mul, ih, List.map_cons,
      List.sum_cons]

theorem colCheck_sound (p : ℕ) (ts : List (ℕ × ℕ)) (pos neg : ℕ)
    (h : colCheck p ts pos neg = true) : ColOK p ts pos neg := by
  unfold colCheck at h
  have h' : (colSumNat p ts + neg) % p = pos % p := by simpa using h
  have hz : ((colSumNat p ts + neg : ℕ) : ZMod p) = (pos : ZMod p) :=
    (ZMod.natCast_eq_natCast_iff' _ _ _).mpr h'
  unfold ColOK
  rw [← colSumNat_cast]
  push_cast at hz
  exact eq_sub_of_add_eq hz

theorem allCheck_sound (p : ℕ) (cols : List (List (ℕ × ℕ) × ℕ × ℕ))
    (h : allCheck p cols = true) : AllOK p cols := by
  induction cols with
  | nil => intro e he; simp at he
  | cons c cs ih =>
    simp only [allCheck, Bool.and_eq_true] at h
    intro e he
    rcases List.mem_cons.mp he with rfl | he'
    · exact colCheck_sound p _ _ _ h.1
    · exact ih h.2 e he'

end ReceiptLean
