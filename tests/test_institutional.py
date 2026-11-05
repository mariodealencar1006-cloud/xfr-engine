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


def test_panel_runner_matches_experiment(tmp_path):
    """O executor em lote (painel CSV) reproduz o Experimento I para o painel sintético de exemplo."""
    import csv
    from xfr_engine.panel import run_panel
    rows = list(csv.DictReader(open("docs/painel_exemplo.csv", encoding="utf-8")))
    res = run_panel(rows, c_E=0.15)
    assert all(r["status"] == "ok" for r in res)
    br = next(r for r in res if r["firm_id"] == "SYN-BR-lucro" and r["config"] == "no_dip")
    assert br["ISC"] == pytest.approx(0.9, abs=1e-3)
    off = next(r for r in res if r["firm_id"] == "SYN-BR-prejuizo" and r["config"] == "all_off")
    assert off["ISC"] == pytest.approx(0.857142857, abs=1e-6)
    # no painel a taxa da linha é a observada da firma: desligar a regra "rate" não a altera
    us_off = next(r for r in res if r["firm_id"] == "SYN-US-prejuizo" and r["config"] == "all_off")
    assert us_off["ISC"] == pytest.approx(0.928571429, abs=1e-6)


def test_panel_uses_r_tjlp_column():
    """A coluna opcional r_tjlp substitui a TJLP mensal do default (painel trimestral) e só afeta o Brasil."""
    from xfr_engine.panel import run_panel
    base = dict(firm_id="X", period_end="2024-12-31", regime="lucro", data_class="P", T="4", C0="0.05", L="0.02", S="0.02",
                line_A="0.10", line_rate="0.03", q_frac="1", LA0="0.5", PF0="0", PL0="0.5",
                **{f"fco_{t}": "-0.01" for t in range(1, 5)}, **{f"pi_{t}": "0.05" for t in range(1, 5)})
    def jcp(country, r=None):
        row = dict(base, country=country, **({"r_tjlp": r} if r else {}))
        return next(x for x in run_panel([row], c_E=0.10) if x["config"] == "all_on")["JCP_shock"]
    assert jcp("BR", "0.03") > jcp("BR")          # TJLP trimestral > mensal default
    assert jcp("US", "0.03") == jcp("US") == 0    # sem JCP nos EUA


def test_negative_equity_base_forces_equity_so_panel_must_clamp():
    """Com PL0 < 0, a base do JCP força E0 ≥ −PL0 no motor: o painel deve entregar PL0 ≥ 0."""
    from xfr_engine.institutional import Regime, default_jurisdictions, solve_min_equity_inst
    from xfr_engine.model import Firm, Instrument
    line = Instrument("linha", A=[0, 0.1, 0, 0], rate=0.03, interest_on="end")
    firm = Firm(T=4, C0=1.0, FCO=[0.1] * 4, S=0.0, L=0.0, instruments=[line])
    J = default_jurisdictions(0.03)["BR"]
    neg = solve_min_equity_inst(firm, J, Regime("p", [-0.1] * 4, LA0=0.0, PF0=0.0, PL0=-0.5))
    zero = solve_min_equity_inst(firm, J, Regime("p", [-0.1] * 4, LA0=0.0, PF0=0.0, PL0=0.0))
    assert neg.E0 >= 0.5 - 1e-6 and zero.E0 <= 1e-6


def test_stage2_survives_presolve_failure():
    """Regressão: com E0 fixado em ±1e-9, o presolve do HiGHS declara inviável a etapa 2 em alguns pontos reais.
    O ponto abaixo (BR-10561, 2018-09-30, com fluxos do painel) tem de devolver CLS, sem converter a falha em zero."""
    from xfr_engine.panel import run_panel
    import csv
    linha = dict(next(csv.DictReader(open("tests/ponto_presolve.csv", encoding="utf-8"))))
    r = next(x for x in run_panel([linha], c_E=0.10) if x["config"] == "all_on")
    assert r["status"] == "ok" and r["CLS"] is not None and r["status_custo"] == "ok"


def _painel_mod():
    import importlib.util
    spec = importlib.util.spec_from_file_location("painel_etapa2", "scripts/etapa2/painel.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def test_rotulos_cvm_de_juros_e_tributos():
    """Regressão dos rótulos livres da DFC encontrados na auditoria da Etapa 2 (falsos negativos e falsos positivos)."""
    m = _painel_mod()
    n = m._norm
    for ds in ("Amortizações de juros - financiamentos", "Encargos de empréstimos e financiamentos pagos",
               "Pagamento de encargos financeiros", "Juros pagos"):
        assert m.e_juros_pago(n(ds), "6.03.02"), ds
    for ds in ("Empréstimos, financiamentos e debêntures (pagamentos de principal e juros)", "Juros Provisionados e não Pagos",
               "Juros sobre capital próprio pagos", "Juros a pagar", "Pagamento de empréstimos e juros"):
        assert not m.e_juros_pago(n(ds), "6.03.02"), ds
    assert not m.e_juros_pago(n("Juros pagos"), "6.01.01.05")
    for ds, c in (("Tributos sobre o lucro", "6.01.03.06"), ("Pagato. IR e CSSL", "6.01.02.09"), ("Imposto de renda e contribuição social pagos", "6.01.02.01")):
        assert m.e_tributo_pago(n(ds), c), ds
    for ds, c in (("Pagamento de refinanciamento de impostos e contribuição - principal", "6.03.01"), ("Pagamento de Outros Impostos e Contribuições", "6.01.02.01"),
                  ("Impostos pagos - PIS, COFINS e ISS", "6.01.02.01"), ("Imposto de renda e contribuição social", "6.01.01.03")):
        assert not m.e_tributo_pago(n(ds), c), ds


def test_escolha_de_versao_sec_corrige_so_escala_e_sinal():
    m = _painel_mod()
    assert m._escolhe([("2018-05", 554275000000.0), ("2019-05", 554275000.0)])[0] == 554275000.0   # erro de escala corrigido depois
    assert m._escolhe([("2021-08", 23539000.0), ("2022-08", 23539000000.0)])[0] == 23539000.0      # certo primeiro, errado depois
    assert m._escolhe([("2021-02", -1819.0), ("2022-02", 1819.0)])[0] == 1819.0                    # sinal corrigido
    assert m._escolhe([("2018-05", 100.0), ("2019-05", 130.0)]) == (100.0, "2018-05")              # reapresentação comum: vale a primeira


def test_panel_uses_dip_access_column():
    """A coluna opcional dip_access substitui o acesso default: 0 reproduz no_dip e o default reproduz all_on."""
    from xfr_engine.panel import run_panel
    base = dict(firm_id="X", country="US", period_end="2024-12-31", regime="prejuizo", data_class="P", T="4", C0="0.02", L="0.02", S="0.03",
                line_A="0.10", line_rate="0.02", q_frac="1", LA0="0", PF0="0", PL0="0.2",
                **{f"fco_{t}": "-0.01" for t in range(1, 5)}, **{f"pi_{t}": "-0.01" for t in range(1, 5)})
    res = {r["config"]: r for r in run_panel([base], c_E=0.10)}
    zero = next(r for r in run_panel([dict(base, dip_access="0")], c_E=0.10) if r["config"] == "all_on")
    assert zero["ISC"] == pytest.approx(res["no_dip"]["ISC"], abs=1e-7)
    meio = next(r for r in run_panel([dict(base, dip_access="0.5")], c_E=0.10) if r["config"] == "all_on")
    assert res["all_on"]["ISC"] - 1e-7 <= meio["ISC"] <= res["no_dip"]["ISC"] + 1e-7
