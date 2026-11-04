"""Estruturas de dados do problema de recapitalização (seção 6.1 do manuscrito).

Convenções
----------
* Períodos t = 1..T (índice 0 das listas = período 1). O instante 0 é a data da decisão.
* Unidades monetárias livres (no exemplo da seção 9: milhões de UM).
* Todos os vetores por período têm comprimento T.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence


def _vec(x, T: int, name: str) -> List[float]:
    if isinstance(x, (int, float)):
        return [float(x)] * T
    x = [float(v) for v in x]
    if len(x) != T:
        raise ValueError(f"{name}: esperado comprimento {T}, recebido {len(x)}")
    return x


@dataclass
class Instrument:
    """Instrumento de dívida j (seção 5.4 / 6.3).

    A        : capacidade de novo desembolso por período (eq. 3). 0 = bloqueado.
    H        : teto do saldo em aberto por período (None = sem teto).
    rate     : taxa por período sobre o saldo (juros = rate * saldo).
    P        : amortização contratual exógena por período (eq. 2). Pode ser 0.
    interest_on : 'end'   -> juros sobre o saldo ao FIM do período (B_t), pagos no período;
                  'begin' -> juros sobre o saldo no INÍCIO do período (B_{t-1}).
                  O exemplo da seção 9 cobra juros no próprio mês do saque -> 'end'.
    fee      : custo de contratação proporcional ao desembolso (encargo imediato), opcional.
    B0       : saldo inicial em aberto.
    """
    name: str
    A: Sequence[float] | float
    rate: float
    P: Sequence[float] | float = 0.0
    H: Optional[Sequence[float] | float] = None
    interest_on: str = "end"
    fee: float = 0.0
    B0: float = 0.0

    def resolved(self, T: int) -> "Instrument":
        A = _vec(self.A, T, f"{self.name}.A")
        P = _vec(self.P, T, f"{self.name}.P")
        H = None if self.H is None else _vec(self.H, T, f"{self.name}.H")
        if self.interest_on not in ("end", "begin"):
            raise ValueError("interest_on deve ser 'end' ou 'begin'")
        return Instrument(self.name, A, self.rate, P, H, self.interest_on, self.fee, self.B0)


@dataclass
class Firm:
    """Estado e fluxos exógenos da empresa focal (seções 6.1–6.2).

    C0            : caixa na data da decisão, antes do aporte (C(0−)).
    FCO           : fluxo de caixa operacional após impostos e capital de giro, por período.
    K             : investimento de capital por período.
    Q             : distribuições aos acionistas por período.
    S             : serviço da dívida PRÉ-EXISTENTE (amortização + encargos), exógeno, por período.
    L             : reserva mínima de caixa por período (eq. 4, versão determinística).
    E_future      : aportes contingentes já contratados por período (E(t,ω)); versão inicial = 0.
    issuance_cost : encargo proporcional sobre E0 (C(0+) = C(0−) + (1 − issuance_cost)·E0).
    E0_max        : teto do aporte firme (None = sem teto). Serve ao teste de inviabilidade.
    terminal_repay: se True, exige C_T − Σ_j B_{j,T} ≥ L_T (restrição de terminalidade, seção 6.9).
    """
    T: int
    C0: float
    FCO: Sequence[float] | float
    S: Sequence[float] | float = 0.0
    L: Sequence[float] | float = 0.0
    K: Sequence[float] | float = 0.0
    Q: Sequence[float] | float = 0.0
    E_future: Sequence[float] | float = 0.0
    issuance_cost: float = 0.0
    E0_max: Optional[float] = None
    terminal_repay: bool = False
    instruments: List[Instrument] = field(default_factory=list)

    def resolved(self) -> "Firm":
        T = self.T
        return Firm(T, float(self.C0), _vec(self.FCO, T, "FCO"), _vec(self.S, T, "S"), _vec(self.L, T, "L"),
                    _vec(self.K, T, "K"), _vec(self.Q, T, "Q"), _vec(self.E_future, T, "E_future"),
                    float(self.issuance_cost), self.E0_max, self.terminal_repay,
                    [i.resolved(T) for i in self.instruments])

    def with_instruments(self, instruments: List[Instrument]) -> "Firm":
        f = self.resolved()
        f.instruments = [i.resolved(self.T) for i in instruments]
        return f
