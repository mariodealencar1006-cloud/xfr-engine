"""Experimento I do Artigo 2 — estática comparativa institucional sobre o exemplo sintético do Artigo 1.

Para cada jurisdição (BR, US) e regime de lucratividade (lucro, equilíbrio, prejuízo), recalcula
E*(0), E*(q), ISC(q;h), C*(0), C*(q) e CLS(q;h) com todas as regras ligadas, com cada regra desligada
uma de cada vez e com todas desligadas; decompõe ISC_BR − ISC_US e CLS_BR − CLS_US por canal; e testa
as direções de H1–H3. Exemplo sintético: seção 9 do Artigo 1 (q = q_max = 0,70; h = limite do mês 2).

Uso:
    python -m xfr_engine.experiment_I                   # imprime o relatório
    python -m xfr_engine.experiment_I --out results     # grava experiment_I.{json,md,png}
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Dict, List

from .model import Firm, Instrument
from .institutional import (RULES, Jurisdiction, Regime, default_jurisdictions, default_regimes,
                            rules_all_on, substitution)

RULE_LABELS = {"tax": "tributo (τ, θ)", "jcp": "JCP", "loss_cap": "trava de prejuízos (κ_P)",
               "interest_cap": "limite à dedução de juros (κ_I)", "rate": "processo de juros (canal de juros)",
               "dip": "financiamento DIP"}
# desligar o tributo também zera o JCP e torna κ_P e κ_I inócuos: estes são componentes de by_rule, não parcelas do canal
CHANNELS = {"tributário": ["tax"], "juros": ["rate"], "instrumento": ["dip"]}


def article1_firm():
    base_rate = 0.02 / 0.70
    line = Instrument("linha_rotativa", A=[0, 0.70, 0, 0, 0, 0], rate=base_rate, interest_on="end")
    firm = Firm(T=6, C0=0.80, FCO=[-0.25, -0.25, 0.05, 0.05, 0.05, 0.05], S=0.20, L=0.30, instruments=[line])
    return firm, base_rate, 0.70, [0, 1, 0, 0, 0, 0]


def run(c_E: float = 0.15) -> Dict[str, object]:
    firm, base_rate, q, h = article1_firm()
    J = default_jurisdictions(base_rate)
    R = default_regimes(firm.T)
    configs = {"all_on": rules_all_on()}
    for r in RULES:
        configs[f"no_{r}"] = dict(rules_all_on(), **{r: False})
    configs["all_off"] = {r: False for r in RULES}

    table: List[dict] = []
    grid: Dict[str, Dict[str, Dict[str, object]]] = {}
    for jn, jur in J.items():
        for rn, reg in R.items():
            for cn, rules in configs.items():
                res = substitution(firm, jur, reg, q, h, rules, c_E=c_E)
                row = dict(jurisdiction=jn, regime=rn, config=cn, status=res.status, E_base=res.E_base,
                           E_shock=res.E_shock, ISC=res.ISC, C_base=res.C_base, C_shock=res.C_shock, CLS=res.CLS,
                           JCP_base=res.detail.get("JCP_base"), JCP_shock=res.detail.get("JCP_shock"),
                           TAX_base=res.detail.get("TAX_base"), TAX_shock=res.detail.get("TAX_shock"),
                           DIP_shock=res.detail.get("DIP_shock"))
                table.append(row); grid.setdefault(jn, {}).setdefault(rn, {})[cn] = row

    def diff(metric, rn, cn):
        a, b = grid["BR"][rn][cn][metric], grid["US"][rn][cn][metric]
        return None if a is None or b is None else a - b

    # decomposição por regra e por canal (uma de cada vez, desligando nas duas jurisdições)
    decomposition = {}
    for rn in R:
        d = {}
        for metric in ("ISC", "CLS"):
            total = diff(metric, rn, "all_on")
            per_rule = {r: (total - diff(metric, rn, f"no_{r}")) if total is not None and diff(metric, rn, f"no_{r}") is not None else None
                        for r in RULES}
            per_channel = {ch: sum(per_rule[r] for r in rs if per_rule[r] is not None) for ch, rs in CHANNELS.items()}
            d[metric] = {"total_BR_minus_US": total, "by_rule": per_rule, "by_channel": per_channel,
                         "interaction_residual": None if total is None else total - sum(per_channel.values())}
        decomposition[rn] = d

    # H1: ISC(prejuízo) ≤ ISC(lucro) em cada jurisdição — teste primário com o conjunto de instrumentos fixo
    # (DIP desligado: canais tributário e de juros isolados); secundário com todas as regras ligadas
    h1 = {jn: {"ISC_lucro_no_dip": grid[jn]["lucro"]["no_dip"]["ISC"], "ISC_prejuizo_no_dip": grid[jn]["prejuizo"]["no_dip"]["ISC"],
               "holds": grid[jn]["prejuizo"]["no_dip"]["ISC"] <= grid[jn]["lucro"]["no_dip"]["ISC"] + 1e-9,
               "ISC_lucro_all_on": grid[jn]["lucro"]["all_on"]["ISC"], "ISC_prejuizo_all_on": grid[jn]["prejuizo"]["all_on"]["ISC"],
               "holds_all_on": grid[jn]["prejuizo"]["all_on"]["ISC"] <= grid[jn]["lucro"]["all_on"]["ISC"] + 1e-9} for jn in J}
    # H2: sem DIP nas duas, ISC_BR ≤ ISC_US em prejuízo; com DIP, sinal da diferença
    h2 = {"no_dip_BR_minus_US_prejuizo": diff("ISC", "prejuizo", "no_dip"),
          "all_on_BR_minus_US_prejuizo": diff("ISC", "prejuizo", "all_on"),
          "holds_part_a": diff("ISC", "prejuizo", "no_dip") <= 1e-9,
          "sign_flips_with_dip": (diff("ISC", "prejuizo", "no_dip") <= 1e-9) and (diff("ISC", "prejuizo", "all_on") > 1e-9)}
    # H3: DiD do CLS entre prejuízo e lucro, com JCP ligado vs desligado
    did_on = diff("CLS", "prejuizo", "all_on") - diff("CLS", "lucro", "all_on")
    did_off = diff("CLS", "prejuizo", "no_jcp") - diff("CLS", "lucro", "no_jcp")
    # H3 (forma testável): a contribuição do JCP à DiD é positiva — a vantagem de custo que o JCP dá ao Brasil em
    # lucro desaparece em prejuízo. A DiD total inclui também o diferencial de alíquota sobre o escudo dos juros.
    h3 = {"CLS_diff_lucro_all_on": diff("CLS", "lucro", "all_on"), "CLS_diff_prejuizo_all_on": diff("CLS", "prejuizo", "all_on"),
          "DiD_with_jcp": did_on, "DiD_without_jcp": did_off, "jcp_contribution_to_DiD": did_on - did_off,
          "holds": (did_on - did_off) > 1e-9, "total_DiD_positive": did_on > 1e-9}
    # sensibilidade ao acesso a DIP nos EUA (BR fixo): onde ISC_BR − ISC_US muda de sinal em prejuízo
    dip_sweep = []
    for acc in (0.0, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0):
        jus = Jurisdiction(**dict(vars(J["US"]), dip_access=acc))
        r_us = substitution(firm, jus, R["prejuizo"], q, h, rules_all_on(), c_E=c_E)
        r_br = grid["BR"]["prejuizo"]["all_on"]
        dip_sweep.append({"dip_access_US": acc, "ISC_US": r_us.ISC, "ISC_BR": r_br["ISC"],
                          "diff": None if r_us.ISC is None else r_br["ISC"] - r_us.ISC,
                          "CLS_US": r_us.CLS, "CLS_BR": r_br["CLS"]})
    # verificação: camada desligada reproduz o Artigo 1
    a1 = grid["BR"]["prejuizo"]["all_off"]
    checks = {"reduces_to_article1": abs(a1["E_base"] - 0.40) < 1e-6 and abs(a1["E_shock"] - 1.00) < 1e-6 and abs(a1["ISC"] - 0.857142857) < 1e-6,
              "all_feasible": all(r["status"] == "ok" for r in table),
              "jcp_zero_in_loss_BR": grid["BR"]["prejuizo"]["all_on"]["JCP_base"] < 1e-9 and grid["BR"]["prejuizo"]["all_on"]["JCP_shock"] < 1e-9,
              "jcp_used_in_profit_BR": grid["BR"]["lucro"]["all_on"]["JCP_shock"] > 1e-6,
              "dip_lowers_ISC_US": grid["US"]["prejuizo"]["all_on"]["ISC"] < grid["US"]["prejuizo"]["no_dip"]["ISC"] - 1e-9}
    params = {"c_E": c_E, "q": q, "h": h, "base_rate": base_rate,
              "jurisdictions": {k: vars(v) for k, v in J.items()},
              "regimes": {k: {"pi": list(v.pi), "LA0": v.LA0, "PF0": v.PF0, "PL0": v.PL0} for k, v in R.items()}}
    return {"params": params, "table": table, "decomposition": decomposition, "H1": h1, "H2": h2, "H3": h3,
            "dip_sweep": dip_sweep, "checks": checks}


def fmt(v, nd=3):
    return "—" if v is None else f"{v:.{nd}f}"


def to_markdown(out: Dict[str, object]) -> str:
    L = []
    L.append("# Experimento I — estática comparativa institucional (exemplo sintético do Artigo 1)\n")
    p = out["params"]
    L.append(f"Retirada q = {p['q']} na direção h = {p['h']} (limite do mês 2); c_E = {p['c_E']} por unidade de E0 no horizonte; "
             f"taxa-base da linha {p['base_rate']:.4f}/mês (BR), metade nos EUA.\n")
    L.append("## Tabela 5 — ISC e CLS por jurisdição, regime e configuração de regras\n")
    L.append("| Jurisdição | Regime | Configuração | E*(0) | E*(q) | ISC | C*(0) | C*(q) | CLS | JCP (q) | DIP (q) |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in out["table"]:
        L.append(f"| {r['jurisdiction']} | {r['regime']} | {r['config']} | {fmt(r['E_base'])} | {fmt(r['E_shock'])} | {fmt(r['ISC'])} | "
                 f"{fmt(r['C_base'])} | {fmt(r['C_shock'])} | {fmt(r['CLS'])} | {fmt(r['JCP_shock'])} | {fmt(r['DIP_shock'])} |")
    L.append("\n## Tabela 6 — decomposição de ISC_BR − ISC_US e CLS_BR − CLS_US por regra e por canal\n")
    L.append("| Regime | Métrica | Total BR−US | " + " | ".join(RULE_LABELS[r] for r in RULES) + " | tributário | juros | instrumento | resíduo de interação |")
    L.append("|---|---|---|" + "---|" * len(RULES) + "---|---|---|---|")
    for rn, d in out["decomposition"].items():
        for metric in ("ISC", "CLS"):
            m = d[metric]
            L.append(f"| {rn} | {metric} | {fmt(m['total_BR_minus_US'])} | " + " | ".join(fmt(m['by_rule'][r]) for r in RULES) +
                     f" | {fmt(m['by_channel']['tributário'])} | {fmt(m['by_channel']['juros'])} | {fmt(m['by_channel']['instrumento'])} | {fmt(m['interaction_residual'])} |")
    L.append("\n## Hipóteses\n")
    for jn, h in out["H1"].items():
        L.append(f"- H1 ({jn}, instrumentos fixos/sem DIP): ISC(lucro) = {fmt(h['ISC_lucro_no_dip'])}, ISC(prejuízo) = {fmt(h['ISC_prejuizo_no_dip'])} → "
                 f"{'confirmada' if h['holds'] else 'NÃO confirmada'}; com DIP: {fmt(h['ISC_lucro_all_on'])} vs {fmt(h['ISC_prejuizo_all_on'])} "
                 f"({'mantida' if h['holds_all_on'] else 'invertida pelo custo líquido do substituto'})")
    h2 = out["H2"]
    L.append(f"- H2(a) sem DIP: ISC_BR − ISC_US (prejuízo) = {fmt(h2['no_dip_BR_minus_US_prejuizo'])} → {'≤ 0, confirmada' if h2['holds_part_a'] else 'NÃO confirmada'}")
    L.append(f"- H2(b) com DIP: ISC_BR − ISC_US (prejuízo) = {fmt(h2['all_on_BR_minus_US_prejuizo'])} → {'sinal inverte: canal de instrumento domina' if h2['sign_flips_with_dip'] else 'sinal não inverte'}")
    h3 = out["H3"]
    L.append(f"- H3: CLS_BR − CLS_US = {fmt(h3['CLS_diff_lucro_all_on'])} (lucro) e {fmt(h3['CLS_diff_prejuizo_all_on'])} (prejuízo); "
             f"DiD = {fmt(h3['DiD_with_jcp'])} com JCP, {fmt(h3['DiD_without_jcp'])} sem JCP; contribuição do JCP = {fmt(h3['jcp_contribution_to_DiD'])} → "
             f"{'confirmada (contribuição do JCP > 0)' if h3['holds'] else 'NÃO confirmada'}; DiD total {'positiva' if h3['total_DiD_positive'] else 'negativa (dominada pelo diferencial de alíquota sobre o escudo dos juros)'}")
    L.append("\n## Sensibilidade — acesso a DIP nos EUA (regime de prejuízo; BR com acesso 0,3)\n")
    L.append("| acesso DIP (US) | ISC_US | ISC_BR | ISC_BR − ISC_US | CLS_US | CLS_BR |")
    L.append("|---|---|---|---|---|---|")
    for r in out["dip_sweep"]:
        L.append(f"| {r['dip_access_US']:.2f} | {fmt(r['ISC_US'])} | {fmt(r['ISC_BR'])} | {fmt(r['diff'])} | {fmt(r['CLS_US'])} | {fmt(r['CLS_BR'])} |")
    L.append("\n## Verificações\n")
    for k, v in out["checks"].items():
        L.append(f"- {k}: {'ok' if v else 'FALHA'}")
    return "\n".join(L) + "\n"


def plot(out: Dict[str, object], path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    regimes = list(out["decomposition"].keys())
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.6))
    for ax, metric in zip(axes[:2], ("ISC", "CLS")):
        for jn, mk in (("BR", "o-"), ("US", "s--")):
            ys = [next(r[metric] for r in out["table"] if r["jurisdiction"] == jn and r["regime"] == rn and r["config"] == "all_on") for rn in regimes]
            ax.plot(regimes, ys, mk, label=f"{jn} (regras ligadas)", color="black" if jn == "BR" else "gray")
            ys2 = [next(r[metric] for r in out["table"] if r["jurisdiction"] == jn and r["regime"] == rn and r["config"] == "no_dip") for rn in regimes]
            ax.plot(regimes, ys2, mk[0] + ":", label=f"{jn} (sem DIP)", color="black" if jn == "BR" else "gray", alpha=0.5)
        ax.set_title(metric); ax.grid(alpha=0.3)
    axes[0].set_ylabel("unidades de aporte por unidade de crédito"); axes[1].set_ylabel("custo por unidade de crédito")
    axes[0].legend(fontsize=7)
    sw = out["dip_sweep"]
    axes[2].plot([r["dip_access_US"] for r in sw], [r["diff"] for r in sw], "o-", color="black")
    axes[2].axhline(0, color="gray", lw=0.8); axes[2].set_title("ISC_BR − ISC_US (prejuízo)")
    axes[2].set_xlabel("acesso a DIP nos EUA (fração da capacidade retirada)"); axes[2].grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(path, dpi=200); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="pasta de saída (experiment_I.json/.md/.png)")
    ap.add_argument("--c_E", type=float, default=0.15)
    a = ap.parse_args()
    out = run(c_E=a.c_E)
    md = to_markdown(out)
    print(md)
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        with open(os.path.join(a.out, "experiment_I.json"), "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1, default=lambda o: str(o))
        with open(os.path.join(a.out, "experiment_I.md"), "w", encoding="utf-8") as fh:
            fh.write(md)
        plot(out, os.path.join(a.out, "experiment_I.png"))


if __name__ == "__main__":
    main()
