"""Programa linear do problema de aporte mínimo (eq. 6) e da escolha de custo (eq. 9, versão
determinística), com extração dos multiplicadores (eq. 10) — HiGHS via scipy.optimize.linprog.

Layout do vetor de decisão x:
    x[0]                      = E0                (aporte firme na data da decisão)
    x[1 : 1+T]                = C_1..C_T          (caixa ao fim de cada período)
    x[oD + j*T + (t-1)]       = D_{j,t}           (desembolso do instrumento j no período t)
    x[oB + j*T + (t-1)]       = B_{j,t}           (saldo de principal ao fim do período t)
Juros I_{j,t} = r_j·B_{j,t} (interest_on='end') ou r_j·B_{j,t-1} ('begin'): lineares em x.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import linprog

from .model import Firm, Instrument

EPS = 1e-9


@dataclass
class Solution:
    status: str                       # 'optimal' | 'infeasible' | 'unbounded' | 'error'
    message: str
    objective: Optional[float]
    E0: Optional[float]
    C: List[float]                    # C_1..C_T
    D: List[List[float]]              # D[j][t-1]
    B: List[List[float]]              # B[j][t-1]
    I: List[List[float]]              # juros I[j][t-1]
    pi_credit: List[List[float]]      # multiplicador LP de D≤A: −∂obj/∂A_{j,t} (eq. 10). Em vértices degenerados
                                      # o dual é válido mas não único; use metrics.shadow_price_fd para derivadas laterais.
    pi_floor: List[float]             # preço-sombra da reserva mínima: ∂obj/∂L_t
    pi_ceiling: List[List[float]]     # −∂obj/∂H_{j,t} (0 se não há teto)
    binding: Dict[str, List[str]] = field(default_factory=dict)   # restrições ativas (camada de explicação)
    terminal_debt: Optional[float] = None
    extra: Dict[str, object] = field(default_factory=dict)

    def ok(self) -> bool:
        return self.status == "optimal"


def _layout(T: int, J: int) -> Tuple[int, int, int]:
    oD = 1 + T
    oB = oD + J * T
    n = oB + J * T
    return oD, oB, n


def _build(firm: Firm):
    """Monta A_eq, b_eq, A_ub, b_ub, bounds e os rótulos das linhas."""
    f = firm.resolved()
    T, J = f.T, len(f.instruments)
    oD, oB, n = _layout(T, J)
    A_eq, b_eq, eq_lab = [], [], []
    A_ub, b_ub, ub_lab = [], [], []

    # --- identidade de caixa (eq. 1), um por período
    for t in range(1, T + 1):
        row = np.zeros(n)
        rhs = f.FCO[t - 1] - f.K[t - 1] - f.S[t - 1] - f.Q[t - 1] + f.E_future[t - 1]
        row[1 + (t - 1)] = 1.0                      # C_t
        if t == 1:
            row[0] = -(1.0 - f.issuance_cost)       # E0 entra no caixa inicial
            rhs += f.C0
        else:
            row[1 + (t - 2)] = -1.0                 # −C_{t−1}
        for j, ins in enumerate(f.instruments):
            row[oD + j * T + (t - 1)] = -(1.0 - ins.fee)     # +D (líquido de encargo)
            rhs -= ins.P[t - 1]                              # −P exógeno
            if ins.interest_on == "end":
                row[oB + j * T + (t - 1)] += ins.rate        # +r·B_t  (sai do caixa)
            else:
                if t == 1:
                    rhs -= ins.rate * ins.B0
                else:
                    row[oB + j * T + (t - 2)] += ins.rate    # +r·B_{t−1}
        A_eq.append(row); b_eq.append(rhs); eq_lab.append(f"cash[{t}]")

    # --- evolução da dívida (eq. 2)
    for j, ins in enumerate(f.instruments):
        for t in range(1, T + 1):
            row = np.zeros(n)
            row[oB + j * T + (t - 1)] = 1.0
            row[oD + j * T + (t - 1)] = -1.0
            rhs = -ins.P[t - 1]
            if t == 1:
                rhs += ins.B0
            else:
                row[oB + j * T + (t - 2)] = -1.0
            A_eq.append(row); b_eq.append(rhs); eq_lab.append(f"debt[{ins.name},{t}]")

    # --- elegibilidade (eq. 3): D ≤ A ; B ≤ H
    for j, ins in enumerate(f.instruments):
        for t in range(1, T + 1):
            row = np.zeros(n); row[oD + j * T + (t - 1)] = 1.0
            A_ub.append(row); b_ub.append(ins.A[t - 1]); ub_lab.append(f"credit[{ins.name},{t}]")
    for j, ins in enumerate(f.instruments):
        if ins.H is None:
            continue
        for t in range(1, T + 1):
            row = np.zeros(n); row[oB + j * T + (t - 1)] = 1.0
            A_ub.append(row); b_ub.append(ins.H[t - 1]); ub_lab.append(f"ceiling[{ins.name},{t}]")

    # --- reserva mínima (eq. 4, determinística): C_t ≥ L_t  ->  −C_t ≤ −L_t
    for t in range(1, T + 1):
        row = np.zeros(n); row[1 + (t - 1)] = -1.0
        A_ub.append(row); b_ub.append(-f.L[t - 1]); ub_lab.append(f"floor[{t}]")

    # --- terminalidade (seção 6.9): C_T − Σ_j B_{j,T} ≥ L_T
    if f.terminal_repay:
        row = np.zeros(n); row[1 + (T - 1)] = -1.0
        for j in range(J):
            row[oB + j * T + (T - 1)] = 1.0
        A_ub.append(row); b_ub.append(-f.L[T - 1]); ub_lab.append("terminal")

    # --- teto do aporte
    if f.E0_max is not None:
        row = np.zeros(n); row[0] = 1.0
        A_ub.append(row); b_ub.append(float(f.E0_max)); ub_lab.append("E0_max")

    bounds = [(0, None)] + [(None, None)] * T + [(0, None)] * (2 * J * T)
    return f, T, J, oD, oB, n, (np.array(A_eq), np.array(b_eq), eq_lab), (np.array(A_ub), np.array(b_ub), ub_lab), bounds


def _unpack(f: Firm, T: int, J: int, oD: int, oB: int, res, ub_lab, c) -> Solution:
    status_map = {0: "optimal", 1: "error", 2: "infeasible", 3: "unbounded", 4: "error"}
    status = status_map.get(res.status, "error")
    if status != "optimal":
        return Solution(status, res.message, None, None, [], [], [], [], [], [], [], {}, None, {})
    x = res.x
    E0 = float(x[0])
    C = [float(v) for v in x[1:1 + T]]
    D = [[float(x[oD + j * T + t]) for t in range(T)] for j in range(J)]
    B = [[float(x[oB + j * T + t]) for t in range(T)] for j in range(J)]
    I = []
    for j, ins in enumerate(f.instruments):
        if ins.interest_on == "end":
            I.append([ins.rate * B[j][t] for t in range(T)])
        else:
            prev = [ins.B0] + B[j][:-1]
            I.append([ins.rate * prev[t] for t in range(T)])
    # duais: marginals = ∂obj/∂b_ub (≤ 0 em minimização)
    marg = np.array(res.ineqlin.marginals)
    pi_credit = [[0.0] * T for _ in range(J)]
    pi_ceiling = [[0.0] * T for _ in range(J)]
    pi_floor = [0.0] * T
    binding = {"credit": [], "blocked": [], "ceiling": [], "floor": [], "other": []}
    names = [ins.name for ins in f.instruments]
    for k, lab in enumerate(ub_lab):
        m = float(marg[k])
        if lab.startswith("credit["):
            nm, t = lab[7:-1].rsplit(",", 1); j = names.index(nm); t = int(t)
            pi_credit[j][t - 1] = -m
            a = f.instruments[j].A[t - 1]
            if a <= EPS:
                binding["blocked"].append(lab)              # instrumento sem capacidade no período
            elif D[j][t - 1] >= a - 1e-7:
                binding["credit"].append(lab)              # limite efetivamente usado (ativo)
        elif lab.startswith("ceiling["):
            nm, t = lab[8:-1].rsplit(",", 1); j = names.index(nm); t = int(t)
            pi_ceiling[j][t - 1] = -m
            if -m > EPS:
                binding["ceiling"].append(lab)
        elif lab.startswith("floor["):
            t = int(lab[6:-1])
            pi_floor[t - 1] = -m        # ∂obj/∂L_t = −∂obj/∂(−L_t)
            if -m > EPS:
                binding["floor"].append(lab)
        else:
            if abs(m) > EPS:
                binding["other"].append(lab)
    sol = Solution("optimal", res.message, float(res.fun), E0, C, D, B, I, pi_credit, pi_floor, pi_ceiling,
                   binding, float(sum(B[j][T - 1] for j in range(J))), {})
    return sol


def solve_min_equity(firm: Firm) -> Solution:
    """Etapa 1 (seção 5.5 / eq. 6): E* = min E0 sujeito a (1)–(4) e elegibilidade."""
    f, T, J, oD, oB, n, (A_eq, b_eq, _), (A_ub, b_ub, ub_lab), bounds = _build(firm)
    c = np.zeros(n); c[0] = 1.0
    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    sol = _unpack(f, T, J, oD, oB, res, ub_lab, c)
    sol.extra["problem"] = "min_equity"
    return sol


def solve_min_cost(firm: Firm, E0_budget: float, kappa_equity: float = 0.0) -> Solution:
    """Etapa 2 (seção 5.5 / eq. 9 determinística): dado um orçamento de aporte, minimiza
    juros totais + encargos de contratação + kappa_equity·E0 (custo de oportunidade do equity)."""
    f, T, J, oD, oB, n, (A_eq, b_eq, _), (A_ub, b_ub, ub_lab), bounds = _build(firm)
    c = np.zeros(n); c[0] = kappa_equity
    for j, ins in enumerate(f.instruments):
        for t in range(T):
            c[oD + j * T + t] += ins.fee
            if ins.interest_on == "end":
                c[oB + j * T + t] += ins.rate
            elif t + 1 < T:
                c[oB + j * T + t] += ins.rate     # B_t paga juros em t+1
    row = np.zeros(n); row[0] = 1.0
    A_ub2 = np.vstack([A_ub, row]); b_ub2 = np.append(b_ub, float(E0_budget)); lab2 = ub_lab + ["E0_budget"]
    res = linprog(c, A_ub=A_ub2, b_ub=b_ub2, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    sol = _unpack(f, T, J, oD, oB, res, lab2, c)
    sol.extra["problem"] = "min_cost"
    return sol


def diagnose_infeasibility(firm: Firm) -> Dict[str, object]:
    """Relaxamento mínimo (seção 6.9): adiciona folgas s_t ≥ 0 à reserva mínima e minimiza Σ s_t.
    Informa o menor déficit agregado e em quais períodos ele ocorre. Não é recomendação."""
    f, T, J, oD, oB, n, (A_eq, b_eq, _), (A_ub, b_ub, ub_lab), bounds = _build(firm)
    # acrescenta T variáveis de folga
    A_eq2 = np.hstack([A_eq, np.zeros((A_eq.shape[0], T))])
    A_ub2 = np.hstack([A_ub, np.zeros((A_ub.shape[0], T))])
    for k, lab in enumerate(ub_lab):
        if lab.startswith("floor["):
            t = int(lab[6:-1]); A_ub2[k, n + t - 1] = -1.0       # −C_t − s_t ≤ −L_t
    c = np.zeros(n + T); c[n:] = 1.0
    bounds2 = bounds + [(0, None)] * T
    res = linprog(c, A_ub=A_ub2, b_ub=b_ub, A_eq=A_eq2, b_eq=b_eq, bounds=bounds2, method="highs")
    if res.status != 0:
        return {"status": "no_relaxation_found", "message": res.message}
    s = [float(v) for v in res.x[n:]]
    return {"status": "relaxed", "min_total_shortfall": float(res.fun),
            "shortfall_by_period": {t + 1: v for t, v in enumerate(s) if v > EPS},
            "E0_used": float(res.x[0])}
