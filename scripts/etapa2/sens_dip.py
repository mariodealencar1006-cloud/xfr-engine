"""Etapa 2: sensibilidade da H2 ao acesso a DIP, na mesma firma, com a configuração all_on.

Varre o acesso sob as regras dos EUA com o Brasil fixo em 30%, como o dip_sweep de experiment_I.py, e acrescenta o caso
de acesso igual a 100% nas duas jurisdições (Artigo 2, seção 7.3, cenário d). Só muda o acesso; o resto segue o caso-base.

Uso:  python scripts/etapa2/sens_dip.py [--jobs N]
Saída: data/panel/sens_dip_{BR|US}_<acesso>.csv
"""
from __future__ import annotations

import argparse
import csv
from multiprocessing import Pool

import pandas as pd

from xfr_engine.panel import run_panel

ACESSO_US = (0.0, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0)
ACESSO_BR = (0.0, 1.0)      # 0 confere com no_dip; 1 é o cenário de acesso igual


def _bloco(rows):
    return run_panel(rows, c_E=0.10, only=["all_on"])


def roda(painel: pd.DataFrame, acesso: float, regras: str, jobs: int) -> None:
    rows = painel.assign(dip_access=acesso).astype(str).to_dict("records")
    with Pool(jobs) as p:
        res = [r for parte in p.imap(_bloco, [rows[i:i + 50] for i in range(0, len(rows), 50)]) for r in parte]
    arq = f"data/panel/sens_dip_{regras}_{str(acesso).replace('.', '_')}.csv"
    with open(arq, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(res[0].keys())); w.writeheader(); w.writerows(res)
    print(arq, len(res), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=9)
    a = ap.parse_args()
    P = pd.read_csv("data/panel/painel_BR_US.csv"); T = pd.read_csv("data/panel/painel_BR_US_troca.csv")
    k = ["firm_id", "period_end"]
    base = P.merge(T[k], on=k)                     # só os pontos da comparação da mesma firma
    sob_us = pd.concat([base[base["country"] == "US"], T[T["country"] == "US"]], ignore_index=True)
    sob_br = pd.concat([base[base["country"] == "BR"], T[T["country"] == "BR"]], ignore_index=True)
    for x in ACESSO_US:
        roda(sob_us, x, "US", a.jobs)
    for x in ACESSO_BR:
        roda(sob_br, x, "BR", a.jobs)


if __name__ == "__main__":
    main()
