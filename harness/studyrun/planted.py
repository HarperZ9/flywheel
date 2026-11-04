"""Planted-truth fitting (upgrade 2026-11-02, F675 and F132 `plantedlagsign`).

F675 planted a prior-summer term of +0.4a while 78 percent of its sites carry a negative one, so the
known-answer check tested a world unlike the data. Here the stage fits the structure (sign, lag and
relative size of each term) on a calibration split, or takes it from a prior study, records the fit in
the lock, and refuses the lock when a planted "truth" world contradicts it.

Spec field, frozen by the lock (ext_sha256):
  "planted": {
    "calibration": "calib.json",            panel kept out of the test inputs; or "prior" below
    "prior": {"source": "F675 posthoc_sign.txt", "terms": {"T_lag1": {"median": -0.127, "share_pos": 0.217}}},
    "terms": [{"name": "T_lag0", "x": "T", "lag": 0}, {"name": "T_lag1", "x": "T", "lag": 1}],
    "sign_share": 0.7,                      share of units needed to call a sign (default 0.7)
    "ratio_tol": 2.0,                       optional: planted ratio to the lead term within this factor
    "worlds": {"true_m": {"T_lag0": 0.4, "T_lag1": -0.3}}
  }
calib.json: {"units": [{"id": "s1", "y": [...], "x": {"T": [...]}}, ...]}; null marks a missing year.
Each unit is fitted by least squares, y_t = c + sum_k b_k x_k(t - lag_k). A term whose sign is unclear
may be planted with either sign, but then some listed world must plant each sign. List only worlds that
claim to sit at the measured structure; deliberate counterfactuals (reverse, null) are not listed.
Standard library only.
"""
import json
import math
from pathlib import Path

from .bounds import binom_sf
from .hashing import sha256_file


def solve(a, b):
    """Gaussian elimination with partial pivoting; a is k x k, b length k. None if singular."""
    k = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-12:
            return None
        m[c], m[p] = m[p], m[c]
        for r in range(k):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    return [m[i][k] / m[i][i] for i in range(k)]


def ols(y, cols):
    """Coefficients of y on an intercept plus cols (lists of equal length). None if singular."""
    xs = [[1.0] * len(y)] + cols
    a = [[math.fsum(u * v for u, v in zip(xi, xj)) for xj in xs] for xi in xs]
    b = [math.fsum(u * v for u, v in zip(xi, y)) for xi in xs]
    beta = solve(a, b)
    return None if beta is None else beta[1:]


def _series(unit, name):
    return unit["y"] if name == "y" else unit["x"][name]


def fit_unit(unit, terms):
    lag = max(t["lag"] for t in terms)
    y, cols = [], [[] for _ in terms]
    for t in range(lag, len(unit["y"])):
        vals = [_series(unit, term["x"])[t - term["lag"]] for term in terms]
        if unit["y"][t] is None or any(v is None for v in vals):
            continue
        y.append(float(unit["y"][t]))
        for c, v in zip(cols, vals):
            c.append(float(v))
    if len(y) < len(terms) + 3:
        return None
    return ols(y, cols)


def _median(v):
    s = sorted(v)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def summarise(coefs, sign_share):
    n = len(coefs)
    pos = sum(1 for c in coefs if c > 0)
    share = pos / n
    k = max(pos, n - pos)
    p = min(1.0, 2 * binom_sf(k, n, 0.5))
    sign = "+" if share >= sign_share and p < 0.05 else "-" if share <= 1 - sign_share and p < 0.05 else "unclear"
    return {"n_units": n, "median": _median(coefs), "share_pos": share, "sign_test_p": p, "sign": sign}


def fit(cfg, calib_path):
    units = json.loads(Path(calib_path).read_text(encoding="utf-8"))["units"]
    fits = [f for f in (fit_unit(u, cfg["terms"]) for u in units) if f is not None]
    if not fits:
        raise ValueError(f"no unit in {calib_path} has enough rows to fit {len(cfg['terms'])} terms")
    share = cfg.get("sign_share", 0.7)
    return {t["name"]: summarise([f[i] for f in fits], share) for i, t in enumerate(cfg["terms"])}, len(units)


def _prior_terms(prior, share):
    out = {}
    for name, row in prior["terms"].items():
        r = dict(row)
        if "sign" not in r:
            s = r.get("share_pos")
            if s is not None:
                r["sign"] = "+" if s >= share else "-" if s <= 1 - share else "unclear"
            else:
                m = r.get("median", 0)
                r["sign"] = "+" if m > 0 else "-" if m < 0 else "unclear"
        out[name] = r
    return out


def check_worlds(cfg, terms):
    """Problems per world: a planted sign against a measured one, a measured term left out, a size off."""
    names = [t["name"] for t in cfg["terms"]]
    clear = [n for n in names if terms.get(n, {}).get("sign") in ("+", "-")]
    lead = clear[0] if clear else None
    tol = cfg.get("ratio_tol")
    out = {}
    for w, plant in (cfg.get("worlds") or {}).items():
        bad = []
        for n, v in plant.items():
            if n not in names:
                bad.append(f"{n}: not a fitted term")
                continue
            s = terms[n]["sign"]
            if s in ("+", "-") and v != 0 and (v > 0) != (s == "+"):
                bad.append(f"{n}: planted {v:+g}, measured sign {s} (median {terms[n]['median']:+.3g}, "
                           f"share positive {terms[n].get('share_pos', float('nan')):.2f})")
            if tol and lead and n != lead and plant.get(lead) and terms[lead]["median"] and s in ("+", "-"):
                want = terms[n]["median"] / terms[lead]["median"]
                got = v / plant[lead]
                if want and got and not (1 / tol <= got / want <= tol):
                    bad.append(f"{n}: planted ratio to {lead} {got:+.3g}, measured {want:+.3g}, outside a factor {tol}")
        for n in clear:
            if n not in plant:
                bad.append(f"{n}: measured sign {terms[n]['sign']} but the world leaves it out")
        out[w] = bad
    for n in names:
        if terms.get(n, {}).get("sign") == "unclear":
            signs = {v > 0 for p in (cfg.get("worlds") or {}).values() for k, v in p.items() if k == n and v != 0}
            if signs and signs != {True, False}:
                out.setdefault("_all", []).append(f"{n}: sign unclear in the fit; plant it with both signs")
    return out


def assess(spec, base):
    """At lock time: (record, problems). The record goes into the lock under 'planted'."""
    cfg = spec["planted"]
    share = cfg.get("sign_share", 0.7)
    if cfg.get("calibration"):
        p = (Path(base) / cfg["calibration"]).resolve() if not Path(cfg["calibration"]).is_absolute() \
            else Path(cfg["calibration"])
        bad = []
        digest = sha256_file(p)
        ins = {str(Path(i).resolve()): i for i in spec.get("_inputs", [])}
        if str(p) in ins or any(Path(i).is_file() and sha256_file(i) == digest for i in spec.get("_inputs", [])):
            bad.append(f"planted.calibration {p.name} is one of the test inputs; fit on a separate split")
        terms, n_units = fit(cfg, p)
        rec = {"source": "calibration", "path": str(p), "sha256": digest, "units": n_units, "terms": terms}
    else:
        terms = _prior_terms(cfg["prior"], share)
        bad = []
        rec = {"source": "prior", "cited": cfg["prior"].get("source"), "terms": terms}
    worlds = check_worlds(cfg, terms)
    rec["worlds"] = {w: {"ok": not b, "problems": b} for w, b in worlds.items()}
    bad += [f"planted world {w}: {x}" for w, b in worlds.items() for x in b]
    return rec, bad


def is_none(cfg):
    """{"none": "reason"}: the study plants no world that claims the measured structure, and says why."""
    return isinstance(cfg, dict) and set(cfg) == {"none"} and bool(str(cfg["none"]).strip())


def problems(cfg):
    out = []
    if not isinstance(cfg, dict):
        return ["planted: must be an object"]
    if is_none(cfg):
        return []
    if bool(cfg.get("calibration")) == bool(cfg.get("prior")):
        out.append("planted: give exactly one of calibration (a separate split) or prior (a cited study fit)")
    terms = cfg.get("terms") or []
    if not terms or any(not isinstance(t, dict) or not t.get("name") or "x" not in t or
                        not isinstance(t.get("lag"), int) or t["lag"] < 0 for t in terms):
        out.append("planted.terms: a list of {name, x, lag >= 0}")
    if cfg.get("prior") and not cfg["prior"].get("source"):
        out.append("planted.prior.source: cite where the fit comes from")
    if not cfg.get("worlds"):
        out.append("planted.worlds: at least one world that claims the measured structure")
    return out
