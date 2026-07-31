# Certificate-shaped open problems: candidate CC-1 oracle families

**Date:** 2026-07-26 | **Register:** internal.

Produced by a 17-agent survey (6 domain scouts, 10 adversarial screens, 1
synthesis) gated on seven hard requirements, the strictest being G3: two
genuinely different checking algorithms must be feasible, because without a
held-out scorer no selection comparison on the family is two-sided.

The cross-cutting prerequisite it identified, instance binding, was verified by
probe and fixed in commit 51122cd before this record was written.

---

# CC-1 oracle families: the operator's shortlist

Thirteen families scouted across extremal graph theory, coding theory, and RF. **Three clear every gate. One clears conditionally.** The failures below matter more than the list.

**Cross-cutting prerequisite (all four).** `CertificateOracle.verify(self, candidate, task=None)` in `C:\dev\local-model\harness\certificates\base.py:187` accepts `task` and never reads it. There is no instance-binding path today, so every declared parameter is candidate-supplied and only scope-bounded. All four families below need the checker to read instance parameters from the instance, never from the certificate. Confidence high (read the file). Budget 0.5 day plus regression on the incumbent.

## 1. The shortlist

### 1. Rectilinear crossing number
**Certificate.** `{graph:{n,edges}, coords:[[x,y],...] integers, crossings:int}`. Grid bounded (`0 <= x,y < 2^20`) as a scope bound. Zero floats anywhere.
**Checker A.** Collinearity rejection by 3x3 integer orientation determinant, then the four-orientation straddle test over vertex-disjoint edge pairs. O(n³ + m²).
**Checker B.** Enumerate C(n,4) vertex quadruples, decide convex position from orientations, identify the diagonal pairing, increment iff both diagonals are edges. Different index universe, no straddle test, O(n⁴). Mandatory: implement `orient` twice (2x2 cross product in A, 3x3 cofactor in B) plus a differential sign test, or the shared primitive is a common-mode failure on the accept path.
**Objective.** Minimise verified crossing **pairs**, not points. Pin this: three concurrent edges would otherwise let a candidate game the score down.
**Ground truth.** Free and table-free: Delaunay triangulations of random integer points give exact zero-crossing instances; the Euler bound cr >= m - 3n + 6 makes any accept below it a detectable false accept (verified by derivation, high). Published cr̄(K_n) for n <= 27 (moderate, citation unverified).
**Generator.** Reject planar instances (else a Schnyder embedder wins by recall). Cap n at 80 to 100: B is 3.9M quadruples at n=100.
**Cost.** 4 to 6 days.

### 2. Binary constant-weight codes A(n,d,w)
**Certificate.** `{n,d,w,size:M,codewords:[sorted w-subsets]}`. Bools rejected as ints, size validated before the predicate.
**Checker A.** Pack each codeword as one Python int; for all pairs, `popcount(A^B) >= d`. O(M² n/64).
**Checker B.** Constant weight gives d = 2(w - |A ∩ B|), so set t = w - ceil(d/2) + 1 and require every t-subset to lie in at most one codeword. Hash-set collision detection, no XOR, no popcount, no pair enumeration. At (24,6,10) that is 189,630 insertions versus 8.9M pair tests, roughly 47x cheaper.
This is the exact structural analogue of the existing `zarankiewicz.py` column-pair popcount versus `independent.py` row-pair collision map, which is why it is the cheapest strong pair available.
**Objective.** Maximise M, reported against the recursive Johnson bound, computable from parameters with no table lookup.
**Ground truth.** Brouwer's table (aeb.win.tue.nl/codes/Andw.html), proven-optimal entries marked. Contamination caveat: the (n,d,w) grid is published, so an `EXCLUDED_PAIRS`-style exclusion is mandatory (`generators.py:24` already has the mechanism). Second caveat: greedy lexicodes are a memorable deterministic construction that scores non-trivially, though not optimally, so gradient survives above them.
**Cost.** 3 days. Lowest of the four.

### 3. Exact rational spectral certificate for expanders
**Certificate.** `{n,d,edges,lambda2_bound:[p,q]}`. The naive framing (`numpy.linalg.eigvalsh`, check λ2 <= 0.9) fails G1 outright. The repair is the family.
**Checker A.** Verify simple/connected/d-regular over integers, then λ2 <= t iff `tI - A + ((d-t)/n)J` is PSD over Q, tested by symmetric LDLᵀ with pivoting over `fractions.Fraction`. Identity verified by direct computation (high).
**Checker B.** Exact characteristic polynomial over Z (Berkowitz), then Sturm sequence root counting above t over Q; accept iff exactly one root (the Perron root) exceeds t. No matrix decomposition anywhere. Largest algorithmic distance of any pair here.
**Objective.** Minimise rational t. Effectively continuous, so nearly every improvement is measurable. Best objective of the four.
**Ground truth.** Integer-spectrum calibration for free (K_n, Petersen, hypercubes, complete bipartite). Calibrate against λ2² <= 4(d-1), not the irrational Ramanujan surd. **Honest gap:** no published best-known λ2 per (n,d) table was found (confidence unknown whether one exists), so checker correctness is calibratable but search competitiveness against human state of the art is not reportable.
**Cost.** 1.5 to 2 weeks. Berkowitz plus subresultant Sturm over Q is the expensive item.

### 4. Degree-diameter (conditional, build only if breadth is wanted)
BFS eccentricity versus boolean-semiring matrix powers B = (A OR I)^k. About as independent as the existing Zarankiewicz pair, which is the bar already set, but both compute "reachability within k steps" and a shared off-by-one in diameter <= k mirrors. Objective: maximise n against the Moore bound (free exact integer ceiling). Contamination is the weak point: the (d,k) grid is ~140 published cells, so recall gives the target number, though not the 70-vertex edge list. Cost 3 days.

## 2. Near misses, one gate each

| Family | Gate | Why |
|---|---|---|
| Turán ex(n;F), generated F | **G1** | For chi(F) >= 3 the Turán graph T(n,chi-1) is F-free by construction and extremal by Erdős-Stone. 95.1% of random F on 7 vertices are non-bipartite; a zero-search policy passed 12/12 against a real backtracking checker at n=60. Contamination by theorem, not by table, so no exclusion list can fix it. The repaired form (F connected bipartite with a cycle) leaves 47 forbidden graphs, a dozen of them named. That is Zarankiewicz with extra F, not a new domain. |
| Strongly regular graphs | **G7** | No scalar. Realisation is a decision problem; every accepted certificate is equally good. Patching it with isomorphism counting swaps in a heavier predicate. |
| Ramsey lower bounds | **G6** | The family *is* a famous fixed table with published extremal colourings (Paley on 17, etc.). Also the weakest G3 here: both checkers are clique search sharing the s-versus-(s-1) convention where the bugs live. |
| Costas arrays | **G7** | Existence, not optimisation. Orders <= 29 fully enumerated; only 32 and 33 open, so no difficulty range remains either. |
| LABS / merit factor | **G3** | One obvious O(n²) autocorrelation loop. Kronecker-substitution convolution is the same arithmetic reshaped, not an independent decision procedure. |
| Spherical codes / kissing numbers | **G1** | Continuous coordinates, floating point at the source. |

## 3. Smith charts and RF, straight answer

**No.** Not as Smith charts. A Smith chart displays Γ = (Z-Z₀)/(Z+Z₀) on the unit disc; the design target ("|Γ| < 0.2 from 2.1 to 2.7 GHz") quantifies over an uncountable set, component values are continuous, and real loads arrive as measured S-parameters, which are float from birth. Checking means sampling (fails G1) or interval arithmetic (a rigorous bound, still not exact arithmetic). G1 fails at the source, not in the checker. Confidence high.

There is exactly one exact repair, and I would still not build it. Restrict to a lumped ladder with rational component values against a rational load model, restate the target as |Γ(jω)|² <= p/q for all ω² in [a,b] with a,b rational. That is rational polynomial nonnegativity on an interval, decidable exactly by Sturm-Habicht root counting over Q (high confidence the procedure is exact and standard), and G3 even passes: root counting versus a Markov-Lukács weighted sum-of-squares certificate verified by exact rational identity are genuinely different. It dies on G5. The reference bound is Fano-Bode, ∫ln(1/|Γ|)dω <= π/RC, which is transcendental and cannot calibrate a rational checker (moderate confidence on the constant's exact form; verify before quoting). And once the load is a generated rational model, the family is real-algebraic polynomial optimisation wearing an RF label, with no RF ground truth left in it. Do not spend a month here.

## 4. The honest constraint

Three of thirteen scouted families clear the two-checker gate cleanly; a fourth clears conditionally. That is a hit rate near 1 in 4, and it will not improve with effort, because **G3 is not an engineering property**. It passes only where the predicate has two genuinely different mathematical characterisations: distance equals 2(w - intersection size); crossing equals diagonal pair of a convex quadrilateral; λ2 <= t equals PSD of a rank-one-corrected matrix. Those coincidences cannot be manufactured with developer time. The family count is bounded by mathematics, not by budget. Plan for five or six families total, not twenty, at roughly one per two to four weeks.

Second constraint, operational: in three of the four, checker B is asymptotically more expensive than checker A. Run B as a periodic held-out audit, not per rollout as `cross_check()` in `C:\dev\local-model\harness\certificates\independent.py:97` currently does.

Build rectilinear crossing number end to end first, including the mutation and false-accept battery. Every schedule above is an estimate against zero data on what the QA battery actually costs per family.