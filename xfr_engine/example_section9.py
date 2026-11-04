"""Exemplo sintético da seção 9 do manuscrito, executado no motor determinístico.

Uso:  python -m xfr_engine.example_section9 [--json saida.json]
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json

from .model import Firm, Instrument
from .solver import solve_min_equity, solve_min_cost, diagnose_infeasibility
from .metrics import (isc, closed_form_isc, estar_curve, proposition_checks,
                      check_identities, simulate_forward, shadow_price_fd)

T = 6
RATE = 0.02 / 0.70          # "juros simplificados de 0,02 milhão ao mês" sobre 0,70 sacado


def firm_base() -> Firm:
    line = Instrument("linha_rotativa", A=[0, 0.70, 0, 0, 0, 0], rate=RATE, P=0.0, interest_on="end")
    return Firm(T=T, C0=0.80, FCO=[-0.25, -0.25, 0.05, 0.05, 0.05, 0.05], S=0.20, L=0.30,
                instruments=[line])


def firm_shock() -> Firm:
    f = firm_base()
    f.instruments[0].A = [0, 0, 0, 0, 0, 0]       # linha cancelada antes de qualquer liberação
    return f


def fmt(v):
    return "—" if v is None else f"{v:.4f}"


def run(verbose: bool = True) -> dict:
    out = {}
    base, shock = firm_base(), firm_shock()
    sb, ss = solve_min_equity(base), solve_min_equity(shock)
    r = isc(base, shock, "linha_rotativa")
    cf = closed_form_isc(sb, r.delta_A)
    out["E_base"], out["E_shock"], out["ISC"], out["ISC_closed_form"] = sb.E0, ss.E0, r.isc, cf
    out["pi_credit_base_month2"] = sb.pi_credit[0][1]
    out["pi_fd_base_month2"] = shadow_price_fd(base, "linha_rotativa", 2)
    out["C_base"], out["C_shock"] = sb.C, ss.C
    out["D_base"], out["I_base"] = sb.D[0], sb.I[0]
    out["binding_base"], out["binding_shock"] = sb.binding, ss.binding
    out["pi_floor_base"], out["pi_floor_shock"] = sb.pi_floor, ss.pi_floor
    out["identities_base"] = check_identities(base, sb)
    out["identities_shock"] = check_identities(shock, ss)

    # Tabela 8 do manuscrito
    table = [[t + 1, base.resolved().FCO[t], 0.20, sb.D[0][t], sb.I[0][t], sb.C[t], ss.C[t]] for t in range(T)]
    out["tabela8"] = table

    # variantes
    rev = copy.deepcopy(base); rev.instruments[0].A = [0, 0.70, 0.70, 0.70, 0.70, 0.70]; rev.instruments[0].H = 0.70
    sr = solve_min_equity(rev)
    out["variant_revolving"] = {"E_star": sr.E0, "D": sr.D[0], "ISC": (ss.E0 - sr.E0) / 0.70 if sr.ok() else None}

    term = copy.deepcopy(base); term.terminal_repay = True
    st = solve_min_equity(term)
    out["variant_terminal_repay"] = {"E_star": st.E0, "D": st.D[0], "status": st.status,
                                     "ISC": (ss.E0 - st.E0) / 0.70 if st.ok() else None}

    inf = copy.deepcopy(shock); inf.E0_max = 0.50
    si = solve_min_equity(inf)
    out["variant_infeasible"] = {"status": si.status, "diagnosis": diagnose_infeasibility(inf)}

    low = copy.deepcopy(base); low.C0 = 0.70
    sl = solve_min_equity(low)
    out["variant_cash_minus_0.10"] = {"E_star": sl.E0, "delta_vs_base": sl.E0 - sb.E0}

    sc = solve_min_cost(base, E0_budget=sb.E0 + 0.30, kappa_equity=0.0)
    out["stage2_min_cost_with_extra_budget"] = {"status": sc.status, "E0": sc.E0, "D": sc.D[0],
                                                 "objective_interest_total": sc.objective}
    sc2 = solve_min_cost(base, E0_budget=sb.E0 + 0.30, kappa_equity=0.05)
    out["stage2_min_cost_kappa_0.05"] = {"status": sc2.status, "E0": sc2.E0, "D": sc2.D[0], "objective": sc2.objective}

    grid = [round(0.05 * k, 2) for k in range(0, 15)]       # 0 .. 0,70
    curve = estar_curve(base, "linha_rotativa", grid, period=2)
    out["curve_E_star_vs_A"] = curve
    out["propositions"] = proposition_checks(curve)

    # reprodutibilidade
    sb2 = solve_min_equity(firm_base())
    h1 = hashlib.sha256(json.dumps([sb.E0, sb.C, sb.D], sort_keys=True).encode()).hexdigest()
    h2 = hashlib.sha256(json.dumps([sb2.E0, sb2.C, sb2.D], sort_keys=True).encode()).hexdigest()
    out["reproducible"] = (h1 == h2)

    if verbose:
        print("=== XFR-IA — motor determinístico — exemplo da seção 9 ===")
        print(f"E*(base)   = {fmt(sb.E0)}   (manuscrito: 0,40)")
        print(f"E*(choque) = {fmt(ss.E0)}   (manuscrito: 1,00)")
        print(f"ΔA = {r.delta_A:.2f}  ->  ISC = {fmt(r.isc)}   (manuscrito: 0,857)")
        fd = out["pi_fd_base_month2"]
        print(f"forma fechada 1 − juros/ΔA = {cf:.4f}   | preço-sombra π(linha, mês 2): LP = {fmt(sb.pi_credit[0][1])}, esq. = {fmt(fd['pi_left'])}, dir. = {fmt(fd['pi_right'])}")
        print()
        print("Tabela 8 (mês | FCO | serviço | saque | juros | caixa base | caixa choque)")
        for row in table:
            print("  " + " | ".join(f"{v:>6.2f}" if isinstance(v, float) else f"{v:>3}" for v in row))
        print()
        print(f"restrições ativas (base):   {sb.binding}")
        print(f"restrições ativas (choque): {ss.binding}")
        print(f"preço-sombra da reserva L_t (base):   {[round(v, 3) for v in sb.pi_floor]}")
        print(f"identidades fechadas: base={out['identities_base']['passed']}  choque={out['identities_shock']['passed']}")
        print()
        print("--- variantes ---")
        v = out["variant_revolving"]
        print(f"linha rotativa (H = 0,70) meses 2–6:  E* = {fmt(v['E_star'])}, saque = {[round(x,2) for x in v['D']]}, ISC = {fmt(v['ISC'])}")
        v = out["variant_terminal_repay"]
        print(f"terminalidade (quitar no mês 6):     E* = {fmt(v['E_star'])}, saque = {[round(x,2) for x in v['D']]}, ISC = {fmt(v['ISC'])}")
        v = out["variant_infeasible"]
        print(f"choque com teto E0 ≤ 0,50:            status = {v['status']}; relaxamento mínimo = {v['diagnosis']}")
        v = out["variant_cash_minus_0.10"]
        print(f"caixa inicial −0,10:                  E* = {fmt(v['E_star'])} (Δ = {v['delta_vs_base']:+.4f})")
        v = out["stage2_min_cost_with_extra_budget"]
        print(f"etapa 2, orçamento E0 ≤ E*+0,30, κ=0: E0 = {fmt(v['E0'])}, saque = {[round(x,2) for x in v['D']]}, juros totais = {fmt(v['objective_interest_total'])}")
        v = out["stage2_min_cost_kappa_0.05"]
        print(f"etapa 2, idem, κ_equity = 0,05/u.m.:  E0 = {fmt(v['E0'])}, saque = {[round(x,2) for x in v['D']]}, objetivo = {fmt(v['objective'])}")
        print()
        print("--- curva E*(A) no mês 2 e Proposições 1–2 ---")
        for a, e, p, pl, pr in zip(curve["A"], curve["E_star"], curve["pi_lp"], curve["pi_left"], curve["pi_right"]):
            print(f"  A = {a:.2f}  E* = {e:.4f}  π_LP = {p:.4f}  π_esq = {pl:.4f}  π_dir = {pr:.4f}")
        print(f"  {out['propositions']}")
        print(f"reprodutível: {out['reproducible']}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="grava os resultados em JSON")
    a = ap.parse_args()
    out = run()
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
        print(f"\nresultados gravados em {a.json}")


if __name__ == "__main__":
    main()
