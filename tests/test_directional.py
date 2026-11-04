"""Directional parameterization (Sections 6.6 / 6.10 of the manuscript)."""
import math
import pytest
from xfr_engine import q_max, firm_at_q, pi_directional, ces, estar_curve_q, proposition_checks_q, solve_min_equity
from xfr_engine.example_section9 import firm_base

H = {("linha_rotativa", 2): 1.0}          # single limit, month 2: h = unit vector
TOL = 1e-6


def test_q_max_equals_available_capacity():
    assert abs(q_max(firm_base(), H) - 0.70) < TOL


def test_ces_reproduces_section9():
    r = ces(firm_base(), H, 0.70)
    assert r.status == "defined"
    assert abs(r.E_base - 0.40) < TOL and abs(r.E_shock - 1.00) < TOL
    assert abs(r.ces - 0.6 / 0.7) < TOL


def test_directional_shadow_price_equals_lp_dual_single_limit():
    """For a unit direction, π(q;h) coincides with the multiplier on D ≤ A (eq. 10)."""
    s = solve_min_equity(firm_base())
    assert abs(pi_directional(firm_base(), H, 0.0) - s.pi_credit[0][1]) < TOL
    assert abs(pi_directional(firm_base(), H, 0.0) - 0.6 / 0.7) < TOL


def test_proposition_2_bounds_hold():
    r = ces(firm_base(), H, 0.70)
    assert r.pi_0_right - 1e-5 <= r.ces <= r.pi_q_left + 1e-5


def test_propositions_on_q_grid():
    grid = [0.05 * k for k in range(0, 15)]          # 0 .. 0.70
    curve = estar_curve_q(firm_base(), H, grid)
    chk = proposition_checks_q(curve)
    assert chk["P1_nondecreasing"] and chk["P1_convex"] and chk["P2_holds"], chk


def test_beyond_q_max_is_rejected():
    with pytest.raises(ValueError):
        firm_at_q(firm_base(), H, 0.71)


def test_two_period_direction_counts_capacity_once():
    """A line available in months 2 and 3 withdrawn along h = (1, 1): q is one committed capacity,
    q_max is the smaller of the two availabilities, and the CES stays well defined."""
    f = firm_base()
    f.instruments[0].A = [0, 0.70, 0.70, 0, 0, 0]
    f.instruments[0].H = 0.70                 # one commitment: the balance cannot exceed it across the two months
    h2 = {("linha_rotativa", 2): 1.0, ("linha_rotativa", 3): 1.0}
    assert abs(q_max(f, h2) - 0.70) < TOL
    assert max(solve_min_equity(f).B[0]) <= 0.70 + TOL
    r = ces(f, h2, 0.70)
    assert r.status == "defined" and abs(r.E_shock - 1.00) < TOL
    assert r.pi_0_right - 1e-5 <= r.ces <= r.pi_q_left + 1e-5
