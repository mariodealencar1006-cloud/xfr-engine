"""Testes da camada institucional (Artigo 2) e do Experimento I."""
import numpy as np
import pytest
from scipy.optimize import Bounds, LinearConstraint

from xfr_engine import Firm, Instrument
from xfr_engine.institutional import (RULES, Jurisdiction, Regime, apply_rules, default_jurisdictions, default_regimes,
                                      rules_all_on, solve_min_cost_inst, solve_min_equity_inst, substitution)
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
    pytest.importorskip("pandas")   # o construtor do painel da Etapa 2 usa pandas
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


def _ponto_painel(**extra):
    base = dict(firm_id="X", country="BR", period_end="2024-12-31", regime="lucro", data_class="P", T="4", C0="0.02", L="0.02",
                S="0.03", S_sem_juros="0.01", line_A="0.10", line_rate="0.03", r_tjlp="0.0", q_frac="1", LA0="0", PF0="0", PL0="0",
                **{f"fco_{t}": "0.01" for t in range(1, 5)}, **{f"pi_{t}": "0.05" for t in range(1, 5)})
    return dict(base, **extra)


def test_channels_do_not_double_count():
    """Desligar o tributo já zera o JCP: o canal tributário é by_rule.tax, e o resíduo fecha com os três canais."""
    out = run()
    for d in out["decomposition"].values():
        for m in d.values():
            assert m["by_channel"]["tributário"] == pytest.approx(m["by_rule"]["tax"], abs=1e-12)
            soma = sum(m["by_channel"].values()) + m["interaction_residual"]
            assert soma == pytest.approx(m["total_BR_minus_US"], abs=1e-12)


def test_existing_interest_zero_is_neutral():
    """I0 = 0 reproduz o caso sem a coluna em todas as configurações."""
    from xfr_engine.panel import run_panel
    sem = run_panel([_ponto_painel()], c_E=0.10)
    com = run_panel([_ponto_painel(I0="0")], c_E=0.10)
    for a, b in zip(sem, com):
        assert a["config"] == b["config"]
        assert a["E_shock"] == pytest.approx(b["E_shock"], abs=1e-8)
        assert a["ISC"] == pytest.approx(b["ISC"], abs=1e-8)


def test_existing_interest_lowers_tax_and_equity():
    """Com lucro tributável, deduzir juros já pagos em S reduz o tributo: o aporte mínimo não sobe, e cai quando a reserva está ativa."""
    from xfr_engine.panel import run_panel
    sem = next(r for r in run_panel([_ponto_painel()], c_E=0.10, only=["no_dip"]))
    com = next(r for r in run_panel([_ponto_painel(I0="0.02")], c_E=0.10, only=["no_dip"]))
    assert com["E_base"] < sem["E_base"] - 1e-6
    assert com["E_shock"] < sem["E_shock"] - 1e-6


def test_existing_interest_respects_interest_cap():
    """Nos EUA, os juros pré-existentes dividem o limite κ_I com os da linha: acima do limite, mais juros não reduzem o tributo.
    Com κ_I·π = 0,015 < I0 < π, os dois valores só empatam por causa do limite; sem ele, o maior I0 baixa o aporte."""
    from xfr_engine.panel import run_panel
    def E(I0, cfg):
        return next(r for r in run_panel([_ponto_painel(country="US", I0=I0)], c_E=0.10, only=[cfg]))["E_shock"]
    assert E("0.02", "all_on") == pytest.approx(E("0.04", "all_on"), abs=1e-7)
    assert E("0.02", "no_interest_cap") > E("0.04", "no_interest_cap") + 1e-3


def test_shield_config_only_runs_on_request():
    """A configuração sem escudo fica fora do conjunto padrão e só pode elevar o aporte mínimo."""
    from xfr_engine.panel import configs, run_panel
    assert "no_dip_no_shield" not in configs()
    padrao = {r["config"] for r in run_panel([_ponto_painel()], c_E=0.10)}
    assert "no_dip_no_shield" not in padrao
    com = next(r for r in run_panel([_ponto_painel()], c_E=0.10, only=["no_dip"]))
    sem = next(r for r in run_panel([_ponto_painel()], c_E=0.10, only=["no_dip_no_shield"]))
    assert sem["status"] == "ok"
    assert sem["E_base"] >= com["E_base"] - 1e-7


def _jcp_com_linha(jur, interest0=None):
    """Etapa de custo em firma que toma a linha: o JCP reduz o tributo, logo vai ao teto do lucro."""
    f = Firm(T=4, C0=0.0, FCO=[0.0, 0.0, 0.0, 0.0], S=[0.0, 0.1, 0.0, 0.0], L=0.0,
             instruments=[Instrument("linha", A=[0.0, 0.2, 0.0, 0.0], rate=0.1, interest_on="end")])
    reg = Regime("lucro", [0.1] * 4, LA0=0.0, PF0=0.0, PL0=10.0, interest0=interest0)
    s = solve_min_equity_inst(f, jur, reg)
    return solve_min_cost_inst(f, jur, reg, s.E0, 0.10)


def test_no_shield_does_not_raise_jcp_cap():
    """Sem o escudo, Ided = 0, mas o lucro contábil segue líquido dos juros: o teto do JCP é o mesmo de quando há dedução."""
    br = Jurisdiction("BR", tau=0.34, kappa_P=0.3, kappa_I=None, jcp=True, r_tjlp=0.5, theta=0.175)
    sem = apply_rules(br, dict(rules_all_on(), shield=False))
    for i0 in (None, [0.02] * 4):
        a, b = _jcp_com_linha(br, i0), _jcp_com_linha(sem, i0)
        assert sum(b.Ided) == pytest.approx(0.0, abs=1e-9)
        assert max(b.B[0]) > 0.05
        for t in range(4):
            juros = 0.1 * b.B[0][t] + (0.02 if i0 else 0.0)
            assert b.JCP[t] == pytest.approx(0.5 * (0.1 - juros), abs=1e-7)
            assert a.JCP[t] == pytest.approx(0.5 * (0.1 - 0.1 * a.B[0][t] - (0.02 if i0 else 0.0)), abs=1e-7)


def test_deduction_above_big_m_is_refused():
    """Prejuízo e juros dedutíveis acima de BIG cortariam o prejuízo fiscal sem aviso, com status optimal."""
    f = Firm(T=4, C0=100.0, FCO=[0.0] * 4, S=0.0, L=0.0, instruments=[Instrument("linha", A=[0.0] * 4, rate=0.1, interest_on="end")])
    br = Jurisdiction("BR", tau=0.34, kappa_P=1.0, kappa_I=None, jcp=False)
    ok = Regime("x", [0.0, 49.0, 49.0, 49.0], LA0=0.0, PF0=0.0, PL0=0.0, interest0=[49.0, 0.0, 0.0, 0.0])
    s = solve_min_cost_inst(f, br, ok, 0.0, 0.10)
    assert sum(s.TAX) == pytest.approx(0.34 * (147.0 - 49.0), abs=1e-6)
    with pytest.raises(ValueError, match="BIG"):
        solve_min_equity_inst(f, br, Regime("x", ok.pi, LA0=0.0, PF0=0.0, PL0=0.0, interest0=[100.0, 0.0, 0.0, 0.0]))


def test_false_optimum_of_presolve_is_not_accepted():
    """Pontos do painel em que o HiGHS com presolve dava status 0 e gap 0 com objetivo acima do mínimo (valores por enumeração de z e w)."""
    from xfr_engine.panel import run_panel
    comum = dict(country="BR", T="4", q_frac="1", line_A="0.1", data_class="P")
    a = dict(comum, firm_id="BR-25577", period_end="2023-12-31", regime="prejuizo", C0="0.01936123490670455", L="0.005889543330399888",
             S="0.01651252070387459", S_sem_juros="0.004170703235911113", line_rate="0.036625", r_tjlp="0.016325", LA0="0", PF0="0",
             PL0="0.19981906309463063", I0=str(0.01651252070387459 - 0.004170703235911113),
             fco_1="-0.012925582134351814", fco_2="0.005693439457287887", fco_3="-0.007639105050299967", fco_4="0.0021795793183335428",
             pi_1="0.013538670053239015", pi_2="0.012601715382258906", pi_3="0.020555723255725876", pi_4="0.013882347088258171")
    r = run_panel([a], c_E=0.10, only=["all_on"])[0]
    assert r["C_base"] == pytest.approx(0.009444, abs=1e-5)
    assert r["CLS"] == pytest.approx(0.0135, abs=1e-3)
    b = dict(comum, firm_id="BR-6815", period_end="2020-12-31", regime="prejuizo", C0="0.1469064080203772", L="0.0005514636686449929",
             S="1.6596986084796166", S_sem_juros="1.6596986084796166", line_rate="0.020375", r_tjlp="0.0122", LA0="0.005495815400830646",
             PF0="0", PL0="0", fco_1="-1.1530170520847711", fco_2="0.6832628580749589", fco_3="0.5286271754269295", fco_4="-0.8725673488337077",
             pi_1="-0.32703865892066203", pi_2="-0.10152201463041269", pi_3="-0.10962771497045058", pi_4="0.015872617538928692")
    r = run_panel([b], c_E=0.10, only=["no_dip"])[0]
    assert r["E_base"] == pytest.approx(7.215103, abs=1e-5)


def test_polishing_keeps_binaries_integral():
    """Sem polimento, ficar com o menor objetivo escolhia a candidata que usa a tolerância de integralidade: E* negativo,
    E*(q) < E*(0) e C* abaixo do mínimo exato (valores por enumeração de z e w)."""
    from xfr_engine.panel import run_panel
    comum = dict(country="BR", T="4", q_frac="1", line_A="0.1", data_class="P", LA0="0", PF0="0")
    a = dict(comum, firm_id="BR-26280", period_end="2022-09-30", regime="prejuizo", C0="0.140337374049131", L="0.000477071503845636",
             S="0.003128976745864184", S_sem_juros="0.0031227367523537775", line_rate="0.044125", r_tjlp="0.018", PL0="0.2752578737318113",
             fco_1="0.006238393512070748", fco_2="0.001575518361460904", fco_3="0.0029183169649503564", fco_4="0.0075763921205521945",
             pi_1="0.012862466623034712", pi_2="0.014901184502768117", pi_3="0.008381191283561065", pi_4="0.0011004788555019902")
    r = run_panel([a], c_E=0.10, only=["no_dip"])[0]
    assert r["E_base"] >= -1e-9 and r["E_shock"] >= -1e-9 and r["E_shock"] >= r["E_base"] - 1e-9
    b = dict(comum, firm_id="BR-22225", period_end="2017-12-31", regime="lucro", C0="0.004344620308620137", L="0.003649695975770641",
             S="0.01455480867469242", S_sem_juros="0.01455480867469242", line_rate="0.025975", r_tjlp="0.0165", PL0="0.4929606570494275",
             fco_1="0.027712659906164137", fco_2="0.011407108116240084", fco_3="0.007692358560125379", fco_4="0.028878168778910408",
             pi_1="0.012728018172019191", pi_2="0.0068426116656692335", pi_3="0.006933537889784191", pi_4="0.012855314885780131")
    r = run_panel([b], c_E=0.10, only=["no_dip_no_shield"])[0]
    assert r["C_base"] == pytest.approx(0.0104016, abs=1e-6)


def test_polishing_recovers_branch_hidden_by_tolerance(monkeypatch):
    """O HiGHS achava o mínimo exato com uma binária do lado errado e um limite violado em 5e-7; fixar as binárias arredondadas
    dava E* 3e-5 acima do mínimo (valor por enumeração de z e w). Com 5 binárias mudas a mais (13, acima do limite da
    enumeração completa), a busca a uma ou duas trocas recupera o mesmo mínimo."""
    from xfr_engine import institutional
    from xfr_engine.panel import run_panel
    a = dict(country="BR", T="4", q_frac="1", line_A="0.1", data_class="P", firm_id="BR-23426", period_end="2023-12-31",
             regime="lucro", C0="0.004246186823387042", L="0.004037985834511705", S="0.024528956476677074",
             S_sem_juros="0.012834782405468332", I0=str(0.024528956476677074 - 0.012834782405468332), line_rate="0.036625",
             r_tjlp="0.016325", LA0="0.07401272567873844", PF0="0", PL0="0.4449347374666271",
             fco_1="0.028946447328807308", fco_2="-0.007535813054420532", fco_3="0.0032765604745777182", fco_4="0.022532725119303237",
             pi_1="0.0475461957301844", pi_2="0.009595785980700957", pi_3="0.022724386884777695", pi_4="0.051704510740787905")
    r = run_panel([a], c_E=0.10, only=["all_on"])[0]
    assert r["E_base"] == pytest.approx(0.006348408, abs=1e-8)
    build = institutional._build

    def com_mudas(*args, **kw):
        f, L, cons, bnd, integ, lab = build(*args, **kw)
        n = 5
        cons = LinearConstraint(np.hstack([cons.A, np.zeros((cons.A.shape[0], n))]), cons.lb, cons.ub)
        bnd = Bounds(np.r_[bnd.lb, np.zeros(n)], np.r_[bnd.ub, np.ones(n)])
        return f, dict(L, n=L["n"] + n), cons, bnd, np.r_[integ, np.ones(n)], lab
    monkeypatch.setattr(institutional, "_build", com_mudas)
    r = run_panel([a], c_E=0.10, only=["all_on"])[0]
    assert r["E_base"] == pytest.approx(0.006348408, abs=1e-8)


def test_big_m_guard_covers_profit_and_jcp():
    """Lucro tributável, JCP e juros com cotas acima de BIG são recusados; o teto H aperta a cota de juros e evita recusa
    indevida; em substitution, a recusa vira status erro_BIG em vez de derrubar a rodada."""
    def firma(A, H=None):
        return Firm(T=4, C0=0.0, FCO=[0.0] * 4, S=0.0, L=0.0, instruments=[Instrument("linha", A=A, rate=0.05, H=H, interest_on="end")])
    us = Jurisdiction("US", tau=0.25, kappa_P=0.8, kappa_I=None, jcp=False)
    br = Jurisdiction("BR", tau=0.34, kappa_P=0.3, kappa_I=None, jcp=True, r_tjlp=0.01, theta=0.175)
    with pytest.raises(ValueError, match="lucro tributável"):
        solve_min_equity_inst(firma([0.0] * 4), us, Regime("x", [70.0, 0.0, 0.0, 0.0], LA0=0.0, PF0=0.0, PL0=0.0))
    with pytest.raises(ValueError, match="prejuízo fiscal"):
        solve_min_equity_inst(firma([0.0] * 4), br, Regime("x", [-45.0, 40.0, 40.0, 40.0], LA0=20.0, PF0=0.0, PL0=100.0))
    with pytest.raises(ValueError, match="atinge BIG"):
        solve_min_equity_inst(firma([0.0] * 4), br, Regime("x", [20.0, 49.0, 49.0, 49.0], LA0=200.0, PF0=0.0, PL0=160.0))
    pi_baixo = Regime("x", [0.1] * 4, LA0=0.0, PF0=0.0, PL0=0.0)
    assert solve_min_equity_inst(firma([0.0, 1003.0, 0.0, 0.0], H=10.0), us, pi_baixo).ok()
    with pytest.raises(ValueError, match="prejuízo fiscal"):
        solve_min_equity_inst(firma([0.0, 1003.0, 0.0, 0.0]), us, pi_baixo)
    r = substitution(firma([0.0, 1.0, 0.0, 0.0]), us, Regime("x", [70.0, 0.0, 0.0, 0.0], LA0=0.0, PF0=0.0, PL0=0.0), 1.0, [0, 1, 0, 0])
    assert r.status == "erro_BIG"
