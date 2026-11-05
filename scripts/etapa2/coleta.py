"""Etapa 2, seções 1 e 2 do roteiro: coleta CVM, BCB, FRED e SEC, com manifesto (URL, data/hora, md5).

Uso:  python scripts/etapa2/coleta.py {cvm|macro|lista|sec} [--ua "Nome email"]
Retoma de onde parou: arquivos já baixados e registrados no manifesto não são baixados de novo.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

RAW = "data/raw"
MAN = f"{RAW}/manifest.csv"
ANOS = range(2016, 2026)


def registra(url: str, caminho: str, md5: str) -> None:
    novo = not os.path.exists(MAN)
    with open(MAN, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if novo:
            w.writerow(["url", "arquivo", "extraido_em_utc", "md5", "bytes"])
        w.writerow([url, caminho, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), md5,
                    os.path.getsize(caminho)])


def baixa(url: str, ua: str, tentativas: int = 5, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*", "Accept-Encoding": "identity"})
    for k in range(tentativas):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            time.sleep(2 ** k)
        except Exception:
            time.sleep(2 ** k)
    raise RuntimeError(f"falhou: {url}")


def salva(url: str, caminho: str, ua: str) -> None:
    if os.path.exists(caminho) and os.path.getsize(caminho) > 0:
        return
    b = baixa(url, ua)
    tmp = caminho + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(b)
    os.replace(tmp, caminho)
    registra(url, caminho, hashlib.md5(b).hexdigest())
    print(f"ok {caminho} {len(b)}", flush=True)


def cvm(ua: str) -> None:
    base = "https://dados.cvm.gov.br/dados/CIA_ABERTA"
    salva(f"{base}/CAD/DADOS/cad_cia_aberta.csv", f"{RAW}/cvm/cad_cia_aberta.csv", ua)
    for a in ANOS:
        salva(f"{base}/DOC/DFP/DADOS/dfp_cia_aberta_{a}.zip", f"{RAW}/cvm/dfp_cia_aberta_{a}.zip", ua)
        salva(f"{base}/DOC/ITR/DADOS/itr_cia_aberta_{a}.zip", f"{RAW}/cvm/itr_cia_aberta_{a}.zip", ua)


def macro(ua: str) -> None:
    # SGS limita séries diárias a 10 anos por consulta; a janela 2015–2025 é pedida em dois blocos
    for sid, nome in ((4389, "cdi_aa"), (256, "tjlp_aa")):
        for ini, fim in (("01/01/2015", "31/12/2020"), ("01/01/2021", "31/12/2026")):
            caminho = f"{RAW}/macro/sgs_{nome}_{ini[-4:]}_{fim[-4:]}.json"
            salva(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{sid}/dados?formato=json&dataInicial={ini}&dataFinal={fim}", caminho, ua)
    salva("https://fred.stlouisfed.org/graph/fredgraph.csv?id=SOFR", f"{RAW}/macro/fred_SOFR.csv", ua)


def lista(ua: str) -> None:
    import pandas as pd
    salva("https://www.sec.gov/files/company_tickers.json", f"{RAW}/sec/company_tickers.json", ua)
    with open(f"{RAW}/sec/company_tickers.json", encoding="utf-8") as fh:
        tick = {v["ticker"].upper(): int(v["cik_str"]) for v in json.load(fh).values()}
    linhas = []
    for idx, pag in (("500", "List_of_S%26P_500_companies"), ("400", "List_of_S%26P_400_companies"), ("600", "List_of_S%26P_600_companies")):
        caminho = f"{RAW}/sec/wiki_sp{idx}.html"
        salva(f"https://en.wikipedia.org/wiki/{pag}", caminho, "Mozilla/5.0 (research script; " + ua + ")")
        for t in pd.read_html(caminho):
            col = [c for c in t.columns if str(c).lower() in ("symbol", "ticker symbol", "ticker")]
            if col and len(t) > 300:
                for s in t[col[0]].astype(str):
                    s = s.strip().upper().replace(".", "-")
                    linhas.append((idx, s, tick.get(s)))
                break
    with open(f"{RAW}/sec/sp1500_atual.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["indice", "ticker", "cik"]); w.writerows(linhas)
    print(len(linhas), "tickers;", sum(1 for x in linhas if x[2] is None), "sem CIK")


def sec(ua: str) -> None:
    import threading
    from concurrent.futures import ThreadPoolExecutor
    with open(f"{RAW}/sec/sp1500_atual.csv", encoding="utf-8") as fh:
        ciks = sorted({int(r["cik"]) for r in csv.DictReader(fh) if r["cik"]})
    trava_taxa, trava_man = threading.Lock(), threading.Lock()
    ult = [0.0]
    falhas = []
    cont = [0]

    def um(par):
        url, cam = par
        if os.path.exists(cam) and os.path.getsize(cam) > 0:
            return
        with trava_taxa:                       # no máximo 8 pedidos por segundo, somando as threads
            espera = 0.125 - (time.time() - ult[0])
            if espera > 0:
                time.sleep(espera)
            ult[0] = time.time()
        try:
            b = baixa(url, ua, timeout=120)
        except Exception as e:
            falhas.append((url, str(e))); return
        tmp = cam + ".tmp"
        with gzip.open(tmp, "wb", compresslevel=3) as fh:
            fh.write(b)
        os.replace(tmp, cam)
        with trava_man:
            registra(url, cam, hashlib.md5(b).hexdigest())
            cont[0] += 1
            if cont[0] % 200 == 0:
                print(cont[0], "baixados", flush=True)

    tarefas = []
    for c in ciks:
        tarefas.append((f"https://data.sec.gov/submissions/CIK{c:010d}.json", f"{RAW}/sec/subm/{c:010d}.json.gz"))
        tarefas.append((f"https://data.sec.gov/api/xbrl/companyfacts/CIK{c:010d}.json", f"{RAW}/sec/facts/{c:010d}.json.gz"))
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(um, tarefas))
    with open(f"{RAW}/sec/falhas.csv", "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(falhas)
    print(f"fim: {cont[0]} novos, {len(falhas)} falhas, {len(ciks)} CIKs")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("etapa", choices=["cvm", "macro", "lista", "sec"])
    ap.add_argument("--ua", default="Mario de Alencar Netto contato@mariodealencar.com.br")
    a = ap.parse_args()
    {"cvm": cvm, "macro": macro, "lista": lista, "sec": sec}[a.etapa](a.ua)
