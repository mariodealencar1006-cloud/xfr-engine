"""Directional withdrawal parameterization (manuscript Sections 6.6 and 6.10).

A(q) = A_base − q·h, with q ≥ 0 a scalar withdrawal magnitude and h ≥ 0 a fixed direction over
(instrument, period) pairs. CES(q;h) = [E*(q) − E*(0)] / q (eq. 7); the directional shadow price
π(q;h) = Σ h·λ is the subgradient of E*(q) obtained from the LP duals (eq. 10); one-sided finite
differences in q give the left/right derivatives used in Proposition 2. The single-limit case of
the paper's Section 9 is h = unit vector at (line, month 2).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .model import Firm
from .solver import solve_min_equity, EPS

Direction = Dict[Tuple[str, int], float]   # {(instrument name, period 1-indexed): weight h ≥ 0}


def _check_direction(firm: Firm, h: Direction) -> None:
    names = [i.name for i in firm.resolved().instruments]
    for (name, t), w in h.items():
        if name not in names:
            raise ValueError(f"direction refers to unknown instrument {name!r}")
        if not (1 <= t <= firm.T):
            raise ValueError(f"direction period {t} outside 1..{firm.T}")
        if w < 0:
            raise ValueError("direction weights must be non-negative")
    if sum(h.values()) <= 0:
        raise ValueError("direction must have at least one positive weight")


def q_max(firm: Firm, h: Direction) -> float:
    """Largest q such that A(q) = A_base − q·h stays non-negative (eq. 8)."""
    _check_direction(firm, h)
    f = firm.resolved(); names = [i.name for i in f.instruments]
    return min(f.instruments[names.index(n)].A[t - 1] / w for (n, t), w in h.items() if w > 0)


def firm_at_q(firm: Firm, h: Direction, q: float) -> Firm:
    """Firm with capacities A(q) = A_base − q·h (clipped at 0 only within EPS)."""
    _check_direction(firm, h)
    g = copy.deepcopy(firm.resolved()); names = [i.name for i in g.instruments]
    for (n, t), w in h.items():
        j = names.index(n)
        a = g.instruments[j].A[t - 1] - q * w
        if a < -EPS:
            raise ValueError(f"q = {q} exceeds q_max for ({n}, {t})")
        g.instruments[j].A[t - 1] = max(0.0, a)
    return g


def pi_directional(firm: Firm, h: Direction, q: float) -> Optional[float]:
    """π(q;h) = Σ h(j,t)·λ(j,t) from the LP duals at A(q) (eq. 10). None if infeasible."""
    s = solve_min_equity(firm_at_q(firm, h, q))
    if not s.ok():
        return None
    names = [i.name for i in firm.resolved().instruments]
    return float(sum(w * s.pi_credit[names.index(n)][t - 1] for (n, t), w in h.items()))


@dataclass
class CESResult:
    status: str              # 'defined' | 'undefined_infeasible' | 'undefined_zero_q'
    ces: Optional[float]
    E_base: Optional[float]
    E_shock: Optional[float]
    q: float
    pi_0_right: Optional[float] = None   # right derivative of E* at q = 0 (finite difference)
    pi_q_left: Optional[float] = None    # left derivative of E* at q (finite difference)
    note: str = ""


def ces(firm: Firm, h: Direction, q: float, step: float = 1e-4) -> CESResult:
    """CES(q;h) = [E*(q,α) − E*(0,α)] / q (eq. 7), with the one-sided derivatives that bound it
    (Proposition 2: π(0+;h) ≤ CES(q;h) ≤ π(q−;h)). Never returns an arbitrary number when one of
    the problems is infeasible (Section 4.2)."""
    sb, ss = solve_min_equity(firm_at_q(firm, h, 0.0)), None
    if q <= EPS:
        return CESResult("undefined_zero_q", None, sb.E0 if sb.ok() else None, None, q, note="q ≤ 0")
    ss = solve_min_equity(firm_at_q(firm, h, q))
    if not (sb.ok() and ss.ok()):
        return CESResult("undefined_infeasible", None, sb.E0, ss.E0, q, note=f"base={sb.status}, shock={ss.status}")
    fd = derivatives_q(firm, h, [0.0, q], step)
    return CESResult("defined", (ss.E0 - sb.E0) / q, sb.E0, ss.E0, q,
                     pi_0_right=fd["pi_right"][0], pi_q_left=fd["pi_left"][1])


def _estar_q(firm: Firm, h: Direction, q: float) -> float:
    s = solve_min_equity(firm_at_q(firm, h, q))
    return s.E0 if s.ok() else float("nan")


def derivatives_q(firm: Firm, h: Direction, q_values: Sequence[float], step: float = 1e-4) -> Dict[str, List[float]]:
    """One-sided finite-difference derivatives of E*(q) in direction h: dE*/dq from the right
    (q + step) and from the left (q − step; NaN when q < step)."""
    qm = q_max(firm, h); R, L = [], []
    for q in q_values:
        e0 = _estar_q(firm, h, q)
        R.append((_estar_q(firm, h, q + step) - e0) / step if q + step <= qm + EPS else float("nan"))
        L.append((e0 - _estar_q(firm, h, q - step)) / step if q - step >= -EPS else float("nan"))
    return {"q": [float(q) for q in q_values], "pi_right": R, "pi_left": L}


def estar_curve_q(firm: Firm, h: Direction, q_values: Sequence[float], step: float = 1e-4) -> Dict[str, List]:
    """E*(q,α) on a grid of withdrawal magnitudes, with π(q;h) from the LP duals and the one-sided
    finite-difference derivatives (Section 6.10)."""
    E, PI, ST = [], [], []
    for q in q_values:
        s = solve_min_equity(firm_at_q(firm, h, q))
        ST.append(s.status); E.append(s.E0 if s.ok() else float("nan"))
        PI.append(pi_directional(firm, h, q) if s.ok() else float("nan"))
    fd = derivatives_q(firm, h, q_values, step)
    return {"q": [float(q) for q in q_values], "E_star": E, "pi_lp": PI,
            "pi_right": fd["pi_right"], "pi_left": fd["pi_left"], "status": ST, "q_max": q_max(firm, h)}


def proposition_checks_q(curve: Dict[str, List], tol: float = 1e-7) -> Dict[str, object]:
    """Numerical check of Propositions 1–2 in the q-parameterization.
    P1: E*(q) nondecreasing and convex in q.  P2: for q1 < q2, the difference quotient
    [E*(q2) − E*(q1)]/(q2 − q1) lies between the right derivative at q1 and the left derivative at q2."""
    q = np.array(curve["q"]); E = np.array(curve["E_star"])
    PR = np.array(curve["pi_right"]); PL = np.array(curve["pi_left"])
    ok = ~np.isnan(E); q, E, PR, PL = q[ok], E[ok], PR[ok], PL[ok]
    order = np.argsort(q); q, E, PR, PL = q[order], E[order], PR[order], PL[order]
    d1 = np.diff(E) / np.diff(q)
    nondecreasing = bool(np.all(d1 >= -tol))
    convex = bool(np.all(np.diff(d1) >= -tol)) if len(d1) > 1 else True
    viol = []; tol2 = max(tol, 1e-6)
    for k in range(len(q)):
        for m in range(k + 1, len(q)):
            quot = (E[m] - E[k]) / (q[m] - q[k])
            lo = PR[k] if not np.isnan(PR[k]) else -np.inf
            hi = PL[m] if not np.isnan(PL[m]) else np.inf
            if not (lo - tol2 <= quot <= hi + tol2):
                viol.append((float(q[k]), float(q[m]), float(quot), float(lo), float(hi)))
    return {"P1_nondecreasing": nondecreasing, "P1_convex": convex, "P2_holds": len(viol) == 0,
            "P2_violations": viol[:10], "n_points": int(len(q))}
