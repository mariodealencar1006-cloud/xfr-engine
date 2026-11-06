"""XFR-IA — motor financeiro determinístico (Apêndice A do manuscrito).

Implementa as identidades (1)–(3), a reserva mínima (4) em versão determinística,
o problema de aporte mínimo (6), o ISC (7) e o preço-sombra do crédito (10)
por programação linear (HiGHS via scipy). Sem IA, sem cenários estocásticos:
é o teste unitário transparente descrito na seção 9 do artigo.
"""
from .model import Instrument, Firm
from .solver import solve_min_equity, solve_min_cost, Solution
from .metrics import (isc, closed_form_isc, estar_curve, check_identities,
                      simulate_forward, proposition_checks, shadow_price_fd)
from .institutional import (Jurisdiction, Regime, substitution, SubstitutionResult, solve_min_equity_inst,
                            solve_min_cost_inst, default_jurisdictions, default_regimes, rules_all_on, apply_rules)
from .directional import (Direction, q_max, firm_at_q, pi_directional, ces, CESResult,
                          derivatives_q, estar_curve_q, proposition_checks_q)

__all__ = ["Instrument", "Firm", "solve_min_equity", "solve_min_cost", "Solution",
           "isc", "closed_form_isc", "estar_curve", "check_identities",
           "simulate_forward", "proposition_checks", "shadow_price_fd",
           "Direction", "q_max", "firm_at_q", "pi_directional", "ces", "CESResult",
           "derivatives_q", "estar_curve_q", "proposition_checks_q",
           "Jurisdiction", "Regime", "substitution", "SubstitutionResult", "solve_min_equity_inst",
           "solve_min_cost_inst", "default_jurisdictions", "default_regimes", "rules_all_on", "apply_rules"]
__version__ = "0.4.1"
