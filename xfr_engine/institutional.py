"""Camada institucional (Artigo 2, seção 5.3): tributo sobre o lucro, JCP, compensação de prejuízos,
limite à dedução de juros, indexação da dívida e financiamento DIP, sobre o núcleo do Artigo 1.

Formulação determinística de cenário único, resolvida como programa linear misto-inteiro (HiGHS via
scipy.optimize.milp). As variáveis binárias servem apenas ao sinal do lucro tributável (z_t) e ao ramo
do teto do JCP (w_t); com a camada desligada (τ = 0, JCP = 0) o problema reduz-se ao LP do Artigo 1
e reproduz seus valores (teste test_institutional.py::test_reduces_to_article1).

Layout do vetor de decisão x (T períodos, J instrumentos):
    E0 | C_t | D_{j,t} | B_{j,t} | Ided_t | LTp_t | LTn_t | z_t | COMP_t | PF_t | JCP_t | w_t | T_t
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence

import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds

from .model import Firm, Instrument

BIG = 50.0     # big-M (unidades monetárias); muito acima de qualquer fluxo do exemplo
EPS = 1e-7


@dataclass
class Jurisdiction:
    """Parâmetros institucionais por jurisdição (Tabela 4 do Artigo 2)."""
    name: str
    tau: float                       # alíquota combinada sobre o lucro
    kappa_P: float                   # limite à compensação de prejuízos (fração do lucro tributável positivo)
    kappa_I: Optional[float]         # limite à dedução de juros (fração de max(0, π_t)); None = sem limite
    jcp: bool                        # dedutibilidade do JCP
    r_tjlp: float = 0.0              # TJLP por período (base do JCP)
    theta: float = 0.0               # retenção na fonte sobre o JCP
    jcp_mode: str = "capitalized"    # 'capitalized' (crédito capitalizado) ou 'cash' (pagamento em caixa)
    line_rate: Optional[float] = None  # taxa da linha por período (canal de juros); None = taxa do instrumento
    dip_access: float = 0.0          # fração da capacidade retirada que o DIP repõe no estado de recuperação
    dip_rate_mult: float = 1.5       # custo do DIP em múltiplos da taxa da linha


@dataclass
class Regime:
    """Regime de lucratividade: lucro tributável antes de juros e JCP por período e estoques iniciais."""
    name: str
    pi: Sequence[float]              # π_t por período
    LA0: float                       # lucros acumulados e reservas de lucros do exercício anterior encerrado
    PF0: float                       # saldo inicial de prejuízos fiscais compensáveis
    PL0: float                       # patrimônio líquido ajustado (base do JCP) antes do aporte


RULES = ("tax", "jcp", "loss_cap", "interest_cap", "rate", "dip")


def rules_all_on() -> Dict[str, bool]:
    return {r: True for r in RULES}


def apply_rules(jur: Jurisdiction, rules: Dict[str, bool]) -> Jurisdiction:
    """Desliga regras por parâmetro (seção 4.2 do Artigo 2), preservando o núcleo."""
    j = replace(jur)
    if not rules.get("tax", True):
        j = replace(j, tau=0.0, theta=0.0, jcp=False)
    if not rules.get("jcp", True):
        j = replace(j, jcp=False)
    if not rules.get("loss_cap", True):
        j = replace(j, kappa_P=1.0)               # compensação integral
    if not rules.get("interest_cap", True):
        j = replace(j, kappa_I=None)
    if not rules.get("rate", True):
        j = replace(j, line_rate=None)            # taxa comum do instrumento
    if not rules.get("dip", True):
        j = replace(j, dip_access=0.0)
    return j


@dataclass
class InstSolution:
    status: str
    objective: Optional[float]
    E0: Optional[float]
    C: List[float] = field(default_factory=list)
    D: List[List[float]] = field(default_factory=list)
    B: List[List[float]] = field(default_factory=list)
    I: List[List[float]] = field(default_factory=list)
    Ided: List[float] = field(default_factory=list)
    LT: List[float] = field(default_factory=list)
    COMP: List[float] = field(default_factory=list)
    PF: List[float] = field(default_factory=list)
    JCP: List[float] = field(default_factory=list)
    TAX: List[float] = field(default_factory=list)
    cost: Optional[float] = None       # custo econômico (etapa 2) quando aplicável
    instruments: List[str] = field(default_factory=list)

    def ok(self) -> bool:
        return self.status == "optimal"


def _firm_with_dip(firm: Firm, jur: Jurisdiction, q: float, h_A: Sequence[float]) -> Firm:
    """Aplica a retirada q·h à linha e, se q > 0 e houver acesso, acrescenta o instrumento DIP."""
    f = firm.resolved()
    line = f.instruments[0]
    A_new = [max(0.0, a - q * hh) for a, hh in zip(line.A, h_A)]
    rate = jur.line_rate if jur.line_rate is not None else line.rate
    line2 = Instrument(line.name, A_new, rate, line.P, line.H, line.interest_on, line.fee, line.B0)
    insts = [line2]
    withdrawn = sum(q * hh for hh in h_A)
    if q > EPS and jur.dip_access > EPS and withdrawn > EPS:
        # O DIP repõe uma fração da capacidade retirada, nas mesmas datas da retirada (sem opção de momento
        # adicional em relação à linha original) e a custo maior; só existe no estado de recuperação (q > 0).
        A_dip = [jur.dip_access * q * hh for hh in h_A]
        cap = jur.dip_access * withdrawn
        insts.append(Instrument("dip", A_dip, rate * jur.dip_rate_mult, 0.0, cap, "end", 0.0, 0.0))
    return f.with_instruments(insts)


def _build(firm: Firm, jur: Jurisdiction, reg: Regime):
    f = firm.resolved()
    T, J = f.T, len(f.instruments)
    if any(i.interest_on != "end" for i in f.instruments):
        raise ValueError("camada institucional: apenas interest_on='end' (juros sobre o saldo ao fim do período)")
    # offsets
    oC = 1
    oD = oC + T
    oB = oD + J * T
    oId = oB + J * T
    oLp = oId + T
    oLn = oLp + T
    oZ = oLn + T
    oCo = oZ + T
    oPF = oCo + T
    oJ = oPF + T
    oW = oJ + T
    oT = oW + T
    n = oT + T
    rows, lo, hi, labels = [], [], [], []

    def add(row, l, u, lab):
        rows.append(row); lo.append(l); hi.append(u); labels.append(lab)

    pi = list(reg.pi)
    assert len(pi) == T, "Regime.pi deve ter comprimento T"
    for t in range(1, T + 1):
        k = t - 1
        # (1) caixa: C_t − C_{t−1} − Σ D + Σ r B + T_t + Qjcp_t = FCO − K − S − Q + E_future (+ C0 + E0 em t=1)
        row = np.zeros(n)
        rhs = f.FCO[k] - f.K[k] - f.S[k] - f.Q[k] + f.E_future[k]
        row[oC + k] = 1.0
        if t == 1:
            row[0] = -(1.0 - f.issuance_cost); rhs += f.C0
        else:
            row[oC + k - 1] = -1.0
        for j, ins in enumerate(f.instruments):
            row[oD + j * T + k] = -(1.0 - ins.fee)
            rhs -= ins.P[k]
            if ins.interest_on == "end":
                row[oB + j * T + k] += ins.rate
            else:
                if t == 1:
                    rhs -= ins.rate * ins.B0
                else:
                    row[oB + j * T + k - 1] += ins.rate
        row[oT + k] = 1.0                                   # tributo sai do caixa
        if jur.jcp and jur.jcp_mode == "cash":
            row[oJ + k] += (1.0 - jur.theta)                # parcela líquida paga aos acionistas
        add(row, rhs, rhs, f"cash[{t}]")
        # (2) dívida
        for j, ins in enumerate(f.instruments):
            row = np.zeros(n); row[oB + j * T + k] = 1.0; row[oD + j * T + k] = -1.0
            rhs = -ins.P[k] + (ins.B0 if t == 1 else 0.0)
            if t > 1:
                row[oB + j * T + k - 1] = -1.0
            add(row, rhs, rhs, f"debt[{ins.name},{t}]")
        # (3) elegibilidade
        for j, ins in enumerate(f.instruments):
            row = np.zeros(n); row[oD + j * T + k] = 1.0
            add(row, -np.inf, ins.A[k], f"credit[{ins.name},{t}]")
            if ins.H is not None:
                row = np.zeros(n); row[oB + j * T + k] = 1.0
                add(row, -np.inf, ins.H[k], f"ceiling[{ins.name},{t}]")
        # (4) reserva mínima
        row = np.zeros(n); row[oC + k] = 1.0
        add(row, f.L[k], np.inf, f"floor[{t}]")
        # juros dedutíveis: Ided_t ≤ I_t = Σ r_j B_{j,t}  (interest_on = 'end')
        row = np.zeros(n); row[oId + k] = 1.0
        for j, ins in enumerate(f.instruments):
            row[oB + j * T + k] -= ins.rate
        add(row, -np.inf, 0.0, f"ided_le_I[{t}]")
        # (10) limite à dedução de juros: Ided_t ≤ κ_I · max(0, π_t)
        if jur.kappa_I is not None:
            row = np.zeros(n); row[oId + k] = 1.0
            add(row, -np.inf, jur.kappa_I * max(0.0, pi[k]), f"interest_cap[{t}]")
        # (11) LT_t = π_t − Ided_t − JCP_t = LTp_t − LTn_t
        row = np.zeros(n); row[oLp + k] = 1.0; row[oLn + k] = -1.0; row[oId + k] = 1.0; row[oJ + k] = 1.0
        add(row, pi[k], pi[k], f"LT[{t}]")
        # sinal: LTp ≤ M z ; LTn ≤ M (1 − z)
        row = np.zeros(n); row[oLp + k] = 1.0; row[oZ + k] = -BIG
        add(row, -np.inf, 0.0, f"LTp_z[{t}]")
        row = np.zeros(n); row[oLn + k] = 1.0; row[oZ + k] = BIG
        add(row, -np.inf, BIG, f"LTn_z[{t}]")
        # (9) compensação: COMP ≤ PF_{t−1} ; COMP ≤ κ_P LTp ; PF_t = PF_{t−1} − COMP + LTn
        row = np.zeros(n); row[oCo + k] = 1.0
        if t == 1:
            add(row, -np.inf, reg.PF0, f"comp_le_PF[{t}]")
        else:
            row[oPF + k - 1] = -1.0; add(row, -np.inf, 0.0, f"comp_le_PF[{t}]")
        row = np.zeros(n); row[oCo + k] = 1.0; row[oLp + k] = -jur.kappa_P
        add(row, -np.inf, 0.0, f"comp_cap[{t}]")
        row = np.zeros(n); row[oPF + k] = 1.0; row[oCo + k] = 1.0; row[oLn + k] = -1.0
        if t == 1:
            add(row, reg.PF0, reg.PF0, f"PF[{t}]")
        else:
            row[oPF + k - 1] = -1.0; add(row, 0.0, 0.0, f"PF[{t}]")
        # (8) JCP: ≤ r_TJLP (PL0 + E0) ; ≤ 0,5 LAJ + M(1−w) ; ≤ 0,5 LA0 + M w ; LAJ = π − Ided
        if jur.jcp:
            row = np.zeros(n); row[oJ + k] = 1.0; row[0] = -jur.r_tjlp
            add(row, -np.inf, jur.r_tjlp * reg.PL0, f"jcp_base[{t}]")
            row = np.zeros(n); row[oJ + k] = 1.0; row[oId + k] = 0.5; row[oW + k] = BIG
            add(row, -np.inf, 0.5 * pi[k] + BIG, f"jcp_profit[{t}]")
            row = np.zeros(n); row[oJ + k] = 1.0; row[oW + k] = -BIG
            add(row, -np.inf, 0.5 * reg.LA0, f"jcp_reserves[{t}]")
        else:
            row = np.zeros(n); row[oJ + k] = 1.0
            add(row, 0.0, 0.0, f"jcp_off[{t}]")
        # (11) T_t = τ (LTp − COMP) + θ JCP
        row = np.zeros(n); row[oT + k] = 1.0; row[oLp + k] = -jur.tau; row[oCo + k] = jur.tau
        row[oJ + k] = -(jur.theta if jur.jcp else 0.0)
        add(row, 0.0, 0.0, f"tax[{t}]")
    if f.terminal_repay:
        row = np.zeros(n); row[oC + T - 1] = 1.0
        for j in range(J):
            row[oB + j * T + T - 1] = -1.0
        add(row, f.L[T - 1], np.inf, "terminal")
    if f.E0_max is not None:
        row = np.zeros(n); row[0] = 1.0
        add(row, -np.inf, float(f.E0_max), "E0_max")

    lb = np.zeros(n); ub = np.full(n, np.inf)
    lb[oC:oC + T] = -np.inf                       # caixa livre (a reserva mínima o limita)
    ub[oZ:oZ + T] = 1.0; ub[oW:oW + T] = 1.0
    integrality = np.zeros(n); integrality[oZ:oZ + T] = 1; integrality[oW:oW + T] = 1
    layout = dict(T=T, J=J, oC=oC, oD=oD, oB=oB, oId=oId, oLp=oLp, oLn=oLn, oZ=oZ, oCo=oCo, oPF=oPF, oJ=oJ, oW=oW, oT=oT, n=n)
    return f, layout, LinearConstraint(np.array(rows), np.array(lo), np.array(hi)), Bounds(lb, ub), integrality, labels


def _unpack(f: Firm, L: dict, res, cost_vec=None) -> InstSolution:
    if res.status != 0 or res.x is None:
        return InstSolution("infeasible" if res.status == 2 else "error", None, None)
    x = res.x; T, J = L["T"], L["J"]
    D = [[float(x[L["oD"] + j * T + t]) for t in range(T)] for j in range(J)]
    B = [[float(x[L["oB"] + j * T + t]) for t in range(T)] for j in range(J)]
    I = [[f.instruments[j].rate * B[j][t] for t in range(T)] for j in range(J)]
    sol = InstSolution("optimal", float(res.fun), float(x[0]),
                       C=[float(v) for v in x[L["oC"]:L["oC"] + T]], D=D, B=B, I=I,
                       Ided=[float(v) for v in x[L["oId"]:L["oId"] + T]],
                       LT=[float(x[L["oLp"] + t] - x[L["oLn"] + t]) for t in range(T)],
                       COMP=[float(v) for v in x[L["oCo"]:L["oCo"] + T]],
                       PF=[float(v) for v in x[L["oPF"]:L["oPF"] + T]],
                       JCP=[float(v) for v in x[L["oJ"]:L["oJ"] + T]],
                       TAX=[float(v) for v in x[L["oT"]:L["oT"] + T]],
                       instruments=[i.name for i in f.instruments])
    if cost_vec is not None:
        sol.cost = float(np.dot(cost_vec, x))
    return sol


def solve_min_equity_inst(firm: Firm, jur: Jurisdiction, reg: Regime) -> InstSolution:
    """Etapa 1 com camada institucional (eq. 5 do Artigo 2): E* = min E0."""
    f, L, cons, bounds, integ, _ = _build(firm, jur, reg)
    c = np.zeros(L["n"]); c[0] = 1.0
    res = milp(c, constraints=cons, bounds=bounds, integrality=integ)
    return _unpack(f, L, res)


def cost_vector(f: Firm, L: dict, jur: Jurisdiction, c_E: float) -> np.ndarray:
    """Custo econômico (eq. 7 do Artigo 2, versão determinística):
    Σ_t juros + Σ_t tributo (inclui retenção sobre o JCP) + c_E·E0 + encargos de contratação."""
    T, J = L["T"], L["J"]
    c = np.zeros(L["n"]); c[0] = c_E
    for j, ins in enumerate(f.instruments):
        for t in range(T):
            c[L["oD"] + j * T + t] += ins.fee
            if ins.interest_on == "end":
                c[L["oB"] + j * T + t] += ins.rate
            elif t + 1 < T:
                c[L["oB"] + j * T + t] += ins.rate
    c[L["oT"]:L["oT"] + T] += 1.0
    if jur.jcp and jur.jcp_mode == "cash":
        c[L["oJ"]:L["oJ"] + T] += (1.0 - jur.theta)       # saída de caixa aos acionistas
    return c


def solve_min_cost_inst(firm: Firm, jur: Jurisdiction, reg: Regime, E0_fixed: float, c_E: float) -> InstSolution:
    """Etapa 2 (eq. 7 do Artigo 2): C* = min custo econômico com E0 = E*(q)."""
    f, L, cons, bounds, integ, _ = _build(firm, jur, reg)
    c = cost_vector(f, L, jur, c_E)
    lb = bounds.lb.copy(); ub = bounds.ub.copy()
    lb[0] = E0_fixed - 1e-9; ub[0] = E0_fixed + 1e-9
    res = milp(c, constraints=cons, bounds=Bounds(lb, ub), integrality=integ)
    return _unpack(f, L, res, c)


@dataclass
class SubstitutionResult:
    jurisdiction: str
    regime: str
    rules: Dict[str, bool]
    q: float
    E_base: Optional[float]
    E_shock: Optional[float]
    ISC: Optional[float]
    C_base: Optional[float]
    C_shock: Optional[float]
    CLS: Optional[float]
    status: str
    detail: Dict[str, object] = field(default_factory=dict)


def substitution(firm: Firm, jur: Jurisdiction, reg: Regime, q: float, h_A: Sequence[float],
                 rules: Optional[Dict[str, bool]] = None, c_E: float = 0.15) -> SubstitutionResult:
    """ISC(q;h) e CLS(q;h) para uma jurisdição, um regime e um conjunto de regras ligadas."""
    rules = dict(rules_all_on(), **(rules or {}))
    j = apply_rules(jur, rules)
    f0 = _firm_with_dip(firm, j, 0.0, h_A)
    fq = _firm_with_dip(firm, j, q, h_A)
    s0 = solve_min_equity_inst(f0, j, reg)
    sq = solve_min_equity_inst(fq, j, reg)
    if not (s0.ok() and sq.ok()):
        return SubstitutionResult(jur.name, reg.name, rules, q, s0.E0, sq.E0, None, None, None, None,
                                  "undefined/infeasible", {"base": s0.status, "shock": sq.status})
    c0 = solve_min_cost_inst(f0, j, reg, s0.E0, c_E)
    cq = solve_min_cost_inst(fq, j, reg, sq.E0, c_E)
    isc = (sq.E0 - s0.E0) / q if q > EPS else None
    cls = (cq.cost - c0.cost) / q if (q > EPS and c0.ok() and cq.ok()) else None
    detail = {"base": s0, "shock": sq, "base_cost": c0, "shock_cost": cq,
              "JCP_base": sum(s0.JCP), "JCP_shock": sum(sq.JCP),
              "TAX_base": sum(s0.TAX), "TAX_shock": sum(sq.TAX),
              "DIP_shock": (sum(sq.D[1]) if len(sq.D) > 1 else 0.0)}
    return SubstitutionResult(jur.name, reg.name, rules, q, s0.E0, sq.E0, isc,
                              c0.cost if c0.ok() else None, cq.cost if cq.ok() else None, cls, "ok", detail)


# ---------------------------------------------------------------------------------------------
# Parametrização ilustrativa (Artigo 2, Tabela 4 e seção 7) — valores de 2026, horizonte mensal
# ---------------------------------------------------------------------------------------------
def default_jurisdictions(base_rate: float) -> Dict[str, Jurisdiction]:
    """BR: τ 34%, trava 30%, sem limite de juros, JCP (TJLP ≈ 7,3% a.a.), retenção 17,5%, CDI alto, DIP incipiente.
    US: τ 25% (21% federal + estadual), NOL 80%, §163(j) 30%, sem JCP, SOFR+spread, DIP consolidado."""
    return {
        "BR": Jurisdiction("BR", tau=0.34, kappa_P=0.30, kappa_I=None, jcp=True, r_tjlp=0.073 / 12, theta=0.175,
                           jcp_mode="capitalized", line_rate=base_rate, dip_access=0.3, dip_rate_mult=1.5),
        "US": Jurisdiction("US", tau=0.25, kappa_P=0.80, kappa_I=0.30, jcp=False, r_tjlp=0.0, theta=0.0,
                           jcp_mode="capitalized", line_rate=base_rate * 0.5, dip_access=1.0, dip_rate_mult=1.5),
    }


def default_regimes(T: int) -> Dict[str, Regime]:
    """Três regimes ex ante (seção 7.2): lucro, equilíbrio e prejuízo, com estoques coerentes."""
    return {
        "lucro":       Regime("lucro", [0.15] * T, LA0=1.0, PF0=0.0, PL0=1.0),
        "equilibrio":  Regime("equilibrio", [0.0] * T, LA0=0.2, PF0=0.0, PL0=1.0),
        "prejuizo":    Regime("prejuizo", [-0.15] * T, LA0=0.0, PF0=0.5, PL0=1.0),
    }
