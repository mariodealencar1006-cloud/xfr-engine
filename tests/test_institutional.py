"""Testes da camada institucional (Artigo 2) e do Experimento I."""
import pytest

from xfr_engine import Firm, Instrument
from xfr_engine.institutional import (RULES, Jurisdiction, default_jurisdictions, default_regimes,
                                      rules_all_on, substitution)
from xfr_engine.experiment_I import run, article1_firm


@pytest.fixture(scope="module")
def setup():
    firm, base_rate, q, h = article1_firm()
    return firm, base_rate, q, h, default_jurisdictions(base_rate), default_regimes(firm.T)


def test_reduces_to_article1(setup):
    """Com a camada desligada (τ = 0, JCP = 0, sem DIP, taxa comum) o problema reproduz a seção 9 do Artigo 1."""
    firm, _, q, h, J, R = setup
    off = {r: False for r in RULES}
    for jn in J:
        for rn in R:
            r = substitution(firm, J[jn], R[rn], q, h, off)
            assert r.status == "ok"
            assert r.E_base == pytest.approx(0.40, abs=1e-6)
            assert r.E_shock == pytest.approx(1.00, abs=1e-6)
            assert r.ISC == pytest.approx(0.857142857, abs=1e-6)


def test_all_feasible_and_defined(setup):
    firm, _, q, h, J, R = setup
    for jn in J:
        for rn in R:
            for rule in list(RULES) + [None]:
                rules = rules_all_on() if rule is None else dict(rules_all_on(), **{rule: False})
                r = substitution(firm, J[jn], R[rn], q, h, rules)
                assert r.status == "ok" and r.ISC is not None and r.CLS is not None


def test_jcp_only_with_taxable_income(setup):
    """JCP é usado em lucro (capitalizado, escudo τ − θ > 0) e é zero em prejuízo (sem lucro tributável)."""
    firm, _, q, h, J, R = setup
    lucro = substitution(firm, J["BR"], R["lucro"], q, h)
    prej = substitution(firm, J["BR"], R["prejuizo"], q, h)
    assert lucro.detail["JCP_shock"] > 1e-6 and lucro.detail["JCP_shock"] >= lucro.detail["JCP_base"] - 1e-9
    assert prej.detail["JCP_base"] < 1e-9 and prej.detail["JCP_shock"] < 1e-9


def test_jcp_base_grows_with_equity(setup):
    """A base do JCP inclui o aporte: o choque (E0 maior) admite JCP maior — canal descrito na seção 4.2."""
    firm, _, q, h, J, R = setup
    r = substitution(firm, J["BR"], R["lucro"], q, h)
    assert r.detail["JCP_shock"] > r.detail["JCP_base"]


def test_H1_direction_with_fixed_instruments(setup):
    """H1: com o conjunto de instrumentos fixo, ISC(prejuízo) ≤ ISC(lucro) em cada jurisdição."""
    firm, _, q, h, J, R = setup
    for jn in J:
        rules = dict(rules_all_on(), dip=False)
        lucro = substitution(firm, J[jn], R["lucro"], q, h, rules).ISC
        prej = substitution(firm, J[jn], R["prejuizo"], q, h, rules).ISC
        assert prej <= lucro + 1e-9


def test_interest_shield_raises_ISC(setup):
    """Juros dedutíveis baratean a linha em termos líquidos e elevam o ISC (lucro, sem DIP) em relação a τ = 0."""
    firm, _, q, h, J, R = setup
    with_tax = substitution(firm, J["BR"], R["lucro"], q, h, dict(rules_all_on(), dip=False)).ISC
    no_tax = substitution(firm, J["BR"], R["lucro"], q, h, dict(rules_all_on(), dip=False, tax=False)).ISC
    assert with_tax > no_tax + 1e-6


def test_dip_lowers_ISC_and_sign_flip(setup):
    """H2: sem DIP, ISC_BR ≤ ISC_US (crédito brasileiro mais caro); com DIP pleno nos EUA, o sinal inverte."""
    firm, _, q, h, J, R = setup
    no_dip = dict(rules_all_on(), dip=False)
    d_no = substitution(firm, J["BR"], R["prejuizo"], q, h, no_dip).ISC - substitution(firm, J["US"], R["prejuizo"], q, h, no_dip).ISC
    d_on = substitution(firm, J["BR"], R["prejuizo"], q, h).ISC - substitution(firm, J["US"], R["prejuizo"], q, h).ISC
    assert d_no <= 1e-9 and d_on > 1e-6


def test_dip_access_monotone(setup):
    """ISC_US é não crescente no acesso a DIP (mais substituto, menos capital próprio)."""
    firm, _, q, h, J, R = setup
    prev = None
    for acc in (0.0, 0.25, 0.5, 0.75, 1.0):
        jus = Jurisdiction(**dict(vars(J["US"]), dip_access=acc))
        v = substitution(firm, jus, R["prejuizo"], q, h).ISC
        assert prev is None or v <= prev + 1e-9
        prev = v


def test_CLS_identity_all_off(setup):
    """Com a camada desligada, CLS = (c_E·E*(q) − [juros + c_E·E*(0)]) / q."""
    firm, _, q, h, J, R = setup
    r = substitution(firm, J["BR"], R["prejuizo"], q, h, {k: False for k in RULES}, c_E=0.15)
    expected = (0.15 * 1.00 - (0.10 + 0.15 * 0.40)) / 0.70
    assert r.CLS == pytest.approx(expected, abs=1e-6)


def test_experiment_report_runs():
    out = run()
    assert out["checks"]["reduces_to_article1"] and out["checks"]["all_feasible"]
    assert out["H2"]["holds_part_a"] and out["H2"]["sign_flips_with_dip"]
    assert all(h["holds"] for h in out["H1"].values())
    assert out["H3"]["holds"]
