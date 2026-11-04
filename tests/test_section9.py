"""Testes unitários das seções 9.3 e A.1 do manuscrito, executados no motor determinístico.
Rodar:  pytest -q
"""
import copy
import hashlib
import json
import math

import pytest

from xfr_engine import (Firm, Instrument, solve_min_equity, solve_min_cost, isc, closed_form_isc,
                        estar_curve, proposition_checks, check_identities, simulate_forward, shadow_price_fd)
from xfr_engine.solver import diagnose_infeasibility
from xfr_engine.example_section9 import firm_base, firm_shock

TOL = 1e-6


@pytest.fixture
def base():
    return firm_base()


@pytest.fixture
def shock():
    return firm_shock()


# ---------------------------------------------------------------- reprodução da seção 9.2
def test_reproduces_minimum_equity(base, shock):
    sb, ss = solve_min_equity(base), solve_min_equity(shock)
    assert sb.ok() and ss.ok()
    assert abs(sb.E0 - 0.40) < TOL
    assert abs(ss.E0 - 1.00) < TOL


def test_reproduces_isc_0857(base, shock):
    r = isc(base, shock, "linha_rotativa")
    assert r.status == "defined"
    assert abs(r.delta_A - 0.70) < TOL
    assert abs(r.isc - 0.6 / 0.7) < TOL          # 0,857142...


def test_reproduces_table8_cash_trajectories(base, shock):
    sb, ss = solve_min_equity(base), solve_min_equity(shock)
    assert [round(c, 2) for c in sb.C] == [0.75, 0.98, 0.81, 0.64, 0.47, 0.30]
    assert [round(c, 2) for c in ss.C] == [1.35, 0.90, 0.75, 0.60, 0.45, 0.30]
    assert [round(d, 2) for d in sb.D[0]] == [0.0, 0.70, 0.0, 0.0, 0.0, 0.0]
    assert [round(i, 2) for i in sb.I[0]] == [0.0, 0.02, 0.02, 0.02, 0.02, 0.02]


def test_closed_form_matches_isc(base, shock):
    sb = solve_min_equity(base)
    r = isc(base, shock, "linha_rotativa")
    assert abs(closed_form_isc(sb, r.delta_A) - r.isc) < TOL      # 1 − 0,10/0,70


def test_shadow_price_equals_isc_in_linear_region(base):
    """Eq. (10): no trecho linear de E*(A) o preço-sombra coincide com a diferença finita."""
    sb = solve_min_equity(base)
    fd = shadow_price_fd(base, "linha_rotativa", 2)
    assert abs(sb.pi_credit[0][1] - 0.6 / 0.7) < 1e-6
    assert abs(fd["pi_left"] - 0.6 / 0.7) < 1e-5
    assert abs(fd["pi_right"] - 0.6 / 0.7) < 1e-5


def test_shadow_price_of_cash_floor_binds_only_at_horizon(base):
    sb = solve_min_equity(base)
    assert [round(v, 6) for v in sb.pi_floor] == [0, 0, 0, 0, 0, 1.0]
    assert sb.binding["floor"] == ["floor[6]"]


# ---------------------------------------------------------------- seção 9.3 — testes derivados
def test_93_i_cash_reduction_raises_equity_one_to_one(base, shock):
    for f in (base, shock):
        s0 = solve_min_equity(f)
        g = copy.deepcopy(f); g.C0 -= 0.10
        s1 = solve_min_equity(g)
        assert abs((s1.E0 - s0.E0) - 0.10) < TOL


def test_93_ii_no_usage_of_unavailable_line(shock):
    s = solve_min_equity(shock)
    assert max(s.D[0]) < TOL
    assert check_identities(shock, s)["violations"] == []


def test_93_iii_scenario_formulation_equals_direct_cash_balance(base):
    s = solve_min_equity(base)
    sim = simulate_forward(base, s.E0, s.D)
    assert max(abs(a - b) for a, b in zip(sim["C"], s.C)) < TOL
    assert max(abs(a - b) for a, b in zip(sim["B"][0], s.B[0])) < TOL


def test_93_iv_infeasibility_is_declared_not_fabricated(shock):
    g = copy.deepcopy(shock); g.E0_max = 0.50
    s = solve_min_equity(g)
    assert s.status == "infeasible" and s.E0 is None
    d = diagnose_infeasibility(g)
    assert d["status"] == "relaxed"
    assert abs(d["min_total_shortfall"] - (0.05 + 0.20 + 0.35 + 0.50)) < 1e-6


def test_93_v_reproducibility(base):
    def h(f):
        s = solve_min_equity(f)
        return hashlib.sha256(json.dumps([s.E0, s.C, s.D, s.B], sort_keys=True).encode()).hexdigest()
    assert h(firm_base()) == h(firm_base())


# ---------------------------------------------------------------- Apêndice A.1 — testes automáticos
def test_a1_identities_hold_in_all_periods(base, shock):
    for f in (base, shock):
        s = solve_min_equity(f)
        chk = check_identities(f, s)
        assert chk["passed"], chk


def test_a1_draw_respects_capacity_and_balance_respects_ceiling(base):
    g = copy.deepcopy(base)
    g.instruments[0].A = [0, 0.70, 0.70, 0.70, 0.70, 0.70]
    g.instruments[0].H = 0.70
    s = solve_min_equity(g)
    assert s.ok()
    assert max(s.B[0]) <= 0.70 + TOL
    assert all(d <= a + TOL for d, a in zip(s.D[0], g.resolved().instruments[0].A))
    assert check_identities(g, s)["passed"]


def test_a1_monotonicity_and_convexity_propositions(base):
    grid = [0.05 * k for k in range(0, 15)]
    curve = estar_curve(base, "linha_rotativa", grid, period=2)
    chk = proposition_checks(curve)
    assert chk["P1_nonincreasing"] and chk["P1_convex"] and chk["P2_holds"], chk


def test_a1_terminality_changes_the_answer(base, shock):
    """Seção 6.9: exigir quitação no horizonte torna a linha inútil neste exemplo (ISC = 0)."""
    g = copy.deepcopy(base); g.terminal_repay = True
    s = solve_min_equity(g)
    assert s.ok() and abs(s.E0 - 1.00) < TOL and max(s.D[0]) < TOL


def test_a1_solver_states_are_distinct(shock):
    g = copy.deepcopy(shock); g.E0_max = 0.50
    assert solve_min_equity(g).status == "infeasible"
    assert solve_min_equity(shock).status == "optimal"


def test_a1_explanation_consistency_blocked_instrument_not_recommended(shock):
    s = solve_min_equity(shock)
    assert s.binding["credit"] == []                     # nenhum limite "usado"
    assert len(s.binding["blocked"]) == 6                # linha bloqueada em todos os meses
    assert max(s.D[0]) < TOL


# ---------------------------------------------------------------- etapa 2 (eq. 9 determinística)
def test_stage2_min_cost_prefers_equity_when_equity_is_free(base):
    sb = solve_min_equity(base)
    sc = solve_min_cost(base, E0_budget=sb.E0 + 0.30, kappa_equity=0.0)
    assert sc.ok() and abs(sc.E0 - (sb.E0 + 0.30)) < TOL
    assert sc.objective < sum(sb.I[0]) + TOL            # menos juros que a solução de aporte mínimo


def test_revolving_option_value_lowers_equity_need(base, shock):
    """Opção de escolher o momento do saque: E* cai e o ISC sobe (a linha vale mais)."""
    g = copy.deepcopy(base)
    g.instruments[0].A = [0, 0.70, 0.70, 0.70, 0.70, 0.70]; g.instruments[0].H = 0.70
    sr, sb, ss = solve_min_equity(g), solve_min_equity(base), solve_min_equity(shock)
    assert sr.E0 < sb.E0 - 1e-3
    assert (ss.E0 - sr.E0) / 0.70 > (ss.E0 - sb.E0) / 0.70
