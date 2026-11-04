"""ISC (eq. 7), forma fechada (seção 9.2), curva E*(A), checagens de identidade (Apêndice B.1),
simulação direta de caixa (teste 9.3-iii) e verificação numérica das Proposições 1–2 (seção 6.10)."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

from .model import Firm, Instrument
from .solver import Solution, solve_min_equity, EPS


@dataclass
class ISCResult:
    status: str                     # 'defined' | 'undefined_infeasible' | 'undefined_zero_delta'
    isc: Optional[float]
    E_base: Optional[float]
    E_shock: Optional[float]
    delta_A: float
    pi_base: Optional[float] = None      # preço-sombra no caso-base (derivada lateral esquerda de −E*)
    pi_shock: Optional[float] = None     # preço-sombra no caso-choque (derivada lateral direita)
    note: str = ""


def delta_A_of(base: Firm, shock: Firm, instrument: str) -> float:
    """ΔA operacional (seção 6.6): redução máxima, ao longo do horizonte, da capacidade A do instrumento."""
    fb, fs = base.resolved(), shock.resolved()
    ib = next(i for i in fb.instruments if i.name == instrument)
    is_ = next(i for i in fs.instruments if i.name == instrument)
    return max(ab - as_ for ab, as_ in zip(ib.A, is_.A))


def isc(base: Firm, shock: Firm, instrument: str, delta_A: Optional[float] = None) -> ISCResult:
    """ISC = [E*(A choque) − E*(A base)] / ΔA (eq. 7). Retorna 'indefinido' quando um dos problemas é
    inviável ou ΔA ≤ 0 — nunca um número arbitrário (seção 4.2)."""
    dA = delta_A_of(base, shock, instrument) if delta_A is None else float(delta_A)
    sb, ss = solve_min_equity(base), solve_min_equity(shock)
    if not (sb.ok() and ss.ok()):
        return ISCResult("undefined_infeasible", None, sb.E0, ss.E0, dA,
                         note=f"base={sb.status}, choque={ss.status}")
    if dA <= EPS:
        return ISCResult("undefined_zero_delta", None, sb.E0, ss.E0, dA, note="ΔA ≤ 0")
    fb = base.resolved(); j = [i.name for i in fb.instruments].index(instrument)
    t_star = int(np.argmax([ab - as_ for ab, as_ in zip(fb.instruments[j].A, shock.resolved().instruments[j].A)]))
    return ISCResult("defined", (ss.E0 - sb.E0) / dA, sb.E0, ss.E0, dA,
                     pi_base=sb.pi_credit[j][t_star], pi_shock=ss.pi_credit[j][t_star])


def closed_form_isc(sol_base: Solution, delta_A: float, instrument_index: int = 0) -> float:
    """Caso determinístico com reserva ativa apenas no período terminal (seção 9.2):
    ISC = 1 − (encargos evitados)/ΔA, onde os encargos evitados são os juros pagos sobre a linha no horizonte."""
    juros = sum(sol_base.I[instrument_index])
    return 1.0 - juros / delta_A


def _estar_at(firm: Firm, j: int, period: int, a: float) -> float:
    g = copy.deepcopy(firm.resolved())
    g.instruments[j].A[period - 1] = float(a)
    s = solve_min_equity(g)
    return s.E0 if s.ok() else float("nan")


def shadow_price_fd(firm: Firm, instrument: str, period: int, h: float = 1e-4) -> Dict[str, float]:
    """Preço-sombra do crédito por diferenças finitas laterais: π = −dE*/dA (eq. 10).
    'right' usa A+h (sempre definido); 'left' usa A−h (indefinido se A < h). Em vértices degenerados
    do LP as duas podem diferir entre si e do multiplicador devolvido pelo solver."""
    f = firm.resolved(); j = [i.name for i in f.instruments].index(instrument)
    a = f.instruments[j].A[period - 1]
    e0 = _estar_at(f, j, period, a)
    right = -(_estar_at(f, j, period, a + h) - e0) / h
    left = -(e0 - _estar_at(f, j, period, a - h)) / h if a - h >= 0 else float("nan")
    return {"A": a, "pi_right": right, "pi_left": left}


def estar_curve(firm: Firm, instrument: str, A_values: Sequence[float], period: int, h: float = 1e-4) -> Dict[str, List[float]]:
    """E*(A) para uma grade de capacidades do instrumento no período dado (1-indexado), com o
    multiplicador do LP (pi_lp) e as derivadas laterais por diferença finita (pi_left, pi_right)."""
    f = firm.resolved(); j = [i.name for i in f.instruments].index(instrument)
    E, PI, PL, PR, ST = [], [], [], [], []
    for a in A_values:
        g = copy.deepcopy(f)
        g.instruments[j].A[period - 1] = float(a)
        s = solve_min_equity(g)
        ST.append(s.status)
        E.append(s.E0 if s.ok() else float("nan"))
        PI.append(s.pi_credit[j][period - 1] if s.ok() else float("nan"))
        fd = shadow_price_fd(g, instrument, period, h)
        PL.append(fd["pi_left"]); PR.append(fd["pi_right"])
    return {"A": [float(a) for a in A_values], "E_star": E, "pi_lp": PI, "pi_left": PL, "pi_right": PR, "status": ST}


def proposition_checks(curve: Dict[str, List[float]], tol: float = 1e-7) -> Dict[str, object]:
    """Verificação numérica das Proposições 1–2 (seção 6.10) sobre uma grade de A.
    P1: E*(A) não crescente e convexa (segundas diferenças ≥ 0).
    P2: para cada par (A_base − ΔA, A_base): π(A_base) ≤ ISC ≤ π(A_base − ΔA)."""
    A = np.array(curve["A"]); E = np.array(curve["E_star"])
    PL = np.array(curve["pi_left"]); PR = np.array(curve["pi_right"])
    ok = ~np.isnan(E)
    A, E, PL, PR = A[ok], E[ok], PL[ok], PR[ok]
    order = np.argsort(A); A, E, PL, PR = A[order], E[order], PL[order], PR[order]
    d1 = np.diff(E) / np.diff(A)
    nonincreasing = bool(np.all(d1 <= tol))
    convex = bool(np.all(np.diff(d1) >= -tol)) if len(d1) > 1 else True
    p2_viol = []
    tol2 = max(tol, 1e-6)
    for k in range(len(A)):
        for m in range(k + 1, len(A)):
            dA = A[m] - A[k]
            isc_km = (E[k] - E[m]) / dA           # A_k = A_base − ΔA (choque); A_m = A_base
            lo = PL[m] if not np.isnan(PL[m]) else -np.inf     # π(A_base), derivada lateral esquerda
            hi = PR[k]                                          # π(A_base − ΔA), derivada lateral direita
            if not (lo - tol2 <= isc_km <= hi + tol2):
                p2_viol.append((float(A[k]), float(A[m]), float(isc_km), float(lo), float(hi)))
    return {"P1_nonincreasing": nonincreasing, "P1_convex": convex, "P2_holds": len(p2_viol) == 0,
            "P2_violations": p2_viol[:10], "n_points": int(len(A))}


def simulate_forward(firm: Firm, E0: float, D: List[List[float]]) -> Dict[str, List]:
    """Balanço de caixa direto (sem otimizador) a partir das decisões E0 e D — teste 9.3-iii."""
    f = firm.resolved(); T = f.T
    C_prev = f.C0 + (1.0 - f.issuance_cost) * E0
    C, B, I = [], [[0.0] * T for _ in f.instruments], [[0.0] * T for _ in f.instruments]
    Bprev = [ins.B0 for ins in f.instruments]
    for t in range(T):
        cash = C_prev + f.FCO[t] - f.K[t] - f.S[t] - f.Q[t] + f.E_future[t]
        for j, ins in enumerate(f.instruments):
            B[j][t] = Bprev[j] + D[j][t] - ins.P[t]
            I[j][t] = ins.rate * (B[j][t] if ins.interest_on == "end" else Bprev[j])
            cash += (1.0 - ins.fee) * D[j][t] - ins.P[t] - I[j][t]
            Bprev[j] = B[j][t]
        C.append(cash); C_prev = cash
    return {"C": C, "B": B, "I": I}


def check_identities(firm: Firm, sol: Solution, tol: float = 1e-7) -> Dict[str, object]:
    """Apêndice B.1: identidades de caixa e dívida fechadas; D ≤ A; B ≤ H; C ≥ L; nada sacado de
    instrumento bloqueado (A = 0)."""
    f = firm.resolved(); T = f.T
    sim = simulate_forward(f, sol.E0, sol.D)
    cash_gap = max(abs(a - b) for a, b in zip(sim["C"], sol.C))
    debt_gap = max(abs(sim["B"][j][t] - sol.B[j][t]) for j in range(len(f.instruments)) for t in range(T))
    viol = []
    for j, ins in enumerate(f.instruments):
        for t in range(T):
            if sol.D[j][t] > ins.A[t] + tol:
                viol.append(f"D>A [{ins.name},{t+1}]")
            if ins.A[t] <= EPS and sol.D[j][t] > tol:
                viol.append(f"saque em instrumento bloqueado [{ins.name},{t+1}]")
            if ins.H is not None and sol.B[j][t] > ins.H[t] + tol:
                viol.append(f"B>H [{ins.name},{t+1}]")
    for t in range(T):
        if sol.C[t] < f.L[t] - tol:
            viol.append(f"C<L [{t+1}]")
    return {"cash_identity_max_gap": cash_gap, "debt_identity_max_gap": debt_gap,
            "violations": viol, "passed": cash_gap <= tol and debt_gap <= tol and not viol}
