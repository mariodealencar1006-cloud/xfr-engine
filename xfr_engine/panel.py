"""Execução em lote do Experimento I sobre um painel firma–período (Artigo 2, Etapa 2).

Entrada: um CSV com uma linha por ponto de decisão (firma, data), nas colunas abaixo (unidades monetárias
livres, mas homogêneas dentro da linha; horizonte em períodos — meses ou trimestres — com T colunas de FCO
e de lucro tributável):

    firm_id, country (BR|US), period_end, T,
    C0, L, S, line_A, line_rate, q_frac,
    fco_1..fco_T, pi_1..pi_T,
    LA0, PF0, PL0, regime (lucro|equilibrio|prejuizo), data_class (O|D|P|E)

    line_A   : capacidade da linha, liberável no 2º período (A_2 = line_A; demais 0) — ou coluna A_1..A_T.
    q_frac   : fração da linha retirada no choque (1,0 = retirada total).
    S, L     : serviço da dívida pré-existente e reserva mínima por período (escalares).
    r_tjlp   : opcional; TJLP por período. Sem a coluna, vale o default mensal de default_jurisdictions.
    dip_access : opcional; fração da capacidade retirada que o DIP repõe. Sem a coluna, vale o default da jurisdição.

Saída: CSV com, por linha e por configuração de regras, E*(0), E*(q), ISC, C*(0), C*(q), CLS, JCP, DIP, status.

    python -m xfr_engine.panel painel.csv --out results/painel_experimento_I.csv [--c_E 0.15] [--jobs N]
"""
from __future__ import annotations

import argparse
import csv
import sys
from typing import Dict, List

from .institutional import (RULES, Jurisdiction, Regime, default_jurisdictions, rules_all_on, substitution)
from .model import Firm, Instrument


def row_to_problem(row: Dict[str, str]):
    T = int(row["T"])
    fco = [float(row[f"fco_{t}"]) for t in range(1, T + 1)]
    pi = [float(row[f"pi_{t}"]) for t in range(1, T + 1)]
    if "A_1" in row:
        A = [float(row[f"A_{t}"]) for t in range(1, T + 1)]
    else:
        A = [0.0] * T
        if T >= 2:
            A[1] = float(row["line_A"])
    rate = float(row["line_rate"])
    line = Instrument("linha", A=A, rate=rate, interest_on="end")
    firm = Firm(T=T, C0=float(row["C0"]), FCO=fco, S=float(row.get("S", 0) or 0), L=float(row.get("L", 0) or 0),
                instruments=[line])
    reg = Regime(row.get("regime", "na"), pi, LA0=float(row.get("LA0", 0) or 0), PF0=float(row.get("PF0", 0) or 0),
                 PL0=float(row.get("PL0", 0) or 0))
    q = float(row.get("q_frac", 1.0) or 1.0) * max(A)
    h = [1.0 if a == max(A) and a > 0 else 0.0 for a in A]
    return firm, reg, q, h, rate


def configs() -> Dict[str, Dict[str, bool]]:
    c = {"all_on": rules_all_on()}
    for r in RULES:
        c[f"no_{r}"] = dict(rules_all_on(), **{r: False})
    c["all_off"] = {r: False for r in RULES}
    return c


def run_panel(rows: List[Dict[str, str]], c_E: float = 0.15, jurisdictions: Dict[str, Jurisdiction] | None = None,
              only: List[str] | None = None) -> List[dict]:
    out = []
    todas = configs()
    escolhidas = {k: todas[k] for k in only} if only else todas
    for row in rows:
        firm, reg, q, h, rate = row_to_problem(row)
        J = jurisdictions or default_jurisdictions(rate)
        jur = J[row["country"]]
        # a taxa da linha vem do próprio painel (canal de juros observado), não do default
        jur = Jurisdiction(**dict(vars(jur), line_rate=rate))
        if row.get("r_tjlp") not in (None, ""):
            jur = Jurisdiction(**dict(vars(jur), r_tjlp=float(row["r_tjlp"])))
        if row.get("dip_access") not in (None, ""):
            jur = Jurisdiction(**dict(vars(jur), dip_access=float(row["dip_access"])))
        for cn, rules in escolhidas.items():
            r = substitution(firm, jur, reg, q, h, rules, c_E=c_E)
            out.append({"firm_id": row["firm_id"], "country": row["country"], "period_end": row["period_end"],
                        "regime": row.get("regime", ""), "data_class": row.get("data_class", ""), "config": cn,
                        "q": q, "status": r.status, "E_base": r.E_base, "E_shock": r.E_shock, "ISC": r.ISC,
                        "C_base": r.C_base, "C_shock": r.C_shock, "CLS": r.CLS,
                        "status_custo": r.detail.get("status_custo"),
                        "JCP_shock": r.detail.get("JCP_custo"), "DIP_shock": r.detail.get("DIP_custo")})
    return out


def _run_chunk(args):
    rows, c_E, only = args
    return run_panel(rows, c_E=c_E, only=only)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("panel_csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--c_E", type=float, default=0.15)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--configs", default=None, help="subconjunto de configurações, separadas por vírgula")
    a = ap.parse_args(argv)
    with open(a.panel_csv, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    only = a.configs.split(",") if a.configs else None
    if a.jobs > 1:
        from multiprocessing import Pool
        chunks = [(rows[i:i + 50], a.c_E, only) for i in range(0, len(rows), 50)]
        with Pool(a.jobs) as p:
            res = [r for part in p.imap(_run_chunk, chunks) for r in part]
    else:
        res = run_panel(rows, c_E=a.c_E, only=only)
    fields = list(res[0].keys()) if res else ["firm_id"]
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(res)
    ok = sum(1 for r in res if r["status"] == "ok")
    print(f"{len(rows)} pontos de decisão × {len(only or configs())} configurações = {len(res)} linhas; {ok} ok", file=sys.stderr)


if __name__ == "__main__":
    main()
