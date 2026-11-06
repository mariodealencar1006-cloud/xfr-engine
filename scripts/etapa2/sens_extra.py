"""Etapa 2: sensibilidades do relatório que não saem de sens_dip.py. Roda tudo com c_E = 0,10.

- sem dupla contagem: S sem os juros pagos, sob as regras próprias e as da outra jurisdição;
- PF0 de 0,05 e 0,10 do ativo nas firmas brasileiras e nos pontos americanos sem saldo observado (Apêndice A.2);
- juros da dívida pré-existente dedutíveis, S − S_sem_juros por trimestre, sob as regras próprias e as da outra jurisdição;
- configuração sem DIP e sem o escudo dos juros da linha, nas regras próprias, para isolar esse escudo em H1.

Uso:  python scripts/etapa2/sens_extra.py [--jobs N] [--somente nome,nome]
Saída: data/panel/sens_*.csv, lidos por agrega.py
"""
from __future__ import annotations

import argparse
import csv
from multiprocessing import Pool

import pandas as pd

from xfr_engine.panel import run_panel

C3 = ["all_on", "no_dip", "no_jcp"]


def _bloco(args):
    rows, only = args
    return run_panel(rows, c_E=0.10, only=only)


def roda(painel: pd.DataFrame, arq: str, only: list, jobs: int) -> None:
    rows = painel.astype(str).to_dict("records")
    with Pool(jobs) as p:
        res = [r for parte in p.imap(_bloco, [(rows[i:i + 50], only) for i in range(0, len(rows), 50)]) for r in parte]
    with open(f"data/panel/{arq}", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(res[0].keys())); w.writeheader(); w.writerows(res)
    print(arq, len(res), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=9)
    ap.add_argument("--somente", default="sem_dupla,pf0,pf0_us,juros,escudo")
    a = ap.parse_args()
    quero = a.somente.split(",")
    P = pd.read_csv("data/panel/painel_BR_US.csv"); T = pd.read_csv("data/panel/painel_BR_US_troca.csv")
    if "sem_dupla" in quero:
        roda(P.assign(S=P["S_sem_juros"]), "sens_sem_dupla_contagem.csv", C3, a.jobs)
        roda(T.assign(S=T["S_sem_juros"]), "sens_sem_dupla_troca.csv", C3, a.jobs)
    if "pf0" in quero:
        for v, nome in ((0.05, "0_05"), (0.10, "0_10")):
            roda(P[P["country"] == "BR"].assign(PF0=v), f"sens_PF0_{nome}.csv", C3, a.jobs)
    if "pf0_us" in quero:
        for v, nome in ((0.05, "0_05"), (0.10, "0_10")):
            roda(P[(P["country"] == "US") & (P["cls_PF0"] == "P")].assign(PF0=v), f"sens_PFUS_{nome}.csv", C3, a.jobs)
    if "juros" in quero:
        roda(P.assign(I0=(P["S"] - P["S_sem_juros"]).clip(lower=0.0)), "sens_juros_ded.csv", C3, a.jobs)
        roda(T.assign(I0=(T["S"] - T["S_sem_juros"]).clip(lower=0.0)), "sens_juros_ded_troca.csv", C3, a.jobs)
    if "escudo" in quero:
        roda(P, "sens_escudo.csv", ["no_dip_no_shield"], a.jobs)


if __name__ == "__main__":
    main()
