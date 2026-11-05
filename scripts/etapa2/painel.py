"""Etapa 2, seção 3 do roteiro: painel firma–trimestre BR (CVM) e US (SEC) no formato de docs/painel_exemplo.csv.

Regras: as do roteiro docs/etapa2_claude_code.md e do Artigo 2 (seções 6–7, Apêndice A). Onde o roteiro não
decide, a escolha está em ESCOLHAS abaixo e é repetida em data/panel/dicionario.md e em results/panel/tabelas.md.

Uso:  python scripts/etapa2/painel.py [--limite_us N]
Saídas (em data/panel/):
    painel_BR_US.csv            caso-base: regras e taxa da própria jurisdição
    painel_BR_US_cf_taxa.csv    regras próprias, taxa mediana da outra jurisdição no trimestre (canal de juros)
    painel_BR_US_troca.csv      mesma firma sob as regras e a taxa da outra jurisdição
    painel_BR_US_troca_taxa.csv mesma firma sob as regras da outra jurisdição, com a própria taxa
    atrito.json                 contagens de exclusão e escolhas
"""
from __future__ import annotations

import argparse
import glob
import gzip
import json
import math
import os
import re
import unicodedata
import zipfile
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

RAW = "data/raw"
OUT = "data/panel"
ANOS = range(2016, 2026)
T = 4
TAU_US = 0.25            # τ da Tabela 4 / default_jurisdictions, usado em NOL/τ
LIMITE_RAZAO = 25.0      # metade de BIG = 50 do motor: acima disso a razão é tratada como erro de dado
TRI_MIN, TRI_MAX = 75, 125   # dias de um trimestre; 112–119 cobre os trimestres de 16–17 semanas do varejo
ESCOLHAS = """
1. Decisão: data de publicação do trimestre t (DT_RECEB / filed); taxas e estoques "as-of" nessa data.
2. Juros pagos em S: último exercício encerrado e publicado na data de decisão, dividido por 4; mais velho que isso, não é usado.
3. FCO antes de tributos: caixa operacional + tributos pagos, como no roteiro, com sinal (restituição reduz). Sem tributo
   trimestral, usa-se o valor anual/4 (classe D); sem nenhum, 0 (classe P).
4. Dívida de curto prazo ou juros não localizados: 0, classe P.
5. Regime: tercis de EBIT do trimestre/ativo dentro de país × trimestre-calendário (fim do trimestre − 16 dias, para calendários 52–53 semanas).
6. US antes de 03/04/2018: SOFR não existe; a observação é excluída (nenhum substituto é inventado).
7. PL0 limitado a ≥ 0: a base do JCP não pode ser negativa; negativa, ela forçaria E0 ≥ −PL0 no motor.
8. BR: PF0 = 0, classe P (saldo só em notas não estruturadas); sensibilidade reportada (Apêndice A.2).
9. Razões com |valor| ≥ 25 vezes o ativo são excluídas como erro de dado (big-M do motor = 50).
10. CVM: quando a bandeira ESCALA_MOEDA muda entre documentos sem o número mudar de ordem de grandeza, vale a bandeira
    predominante da firma; saltos do ativo acima de 200× que restem no horizonte excluem o ponto.
11. CVM: consolidado com ativo > 0, senão individual, escolhido uma vez por firma–data; fluxo trimestral só entre datas do mesmo nível.
12. SEC: entre versões de um mesmo fato vale a primeira publicada; versão posterior só corrige erro de escala (potência de 10, fica a menor)
    ou de sinal (exatamente oposto, fica a posterior). Tags alternativas preenchem apenas as datas que a tag principal não tem.
13. line_A: capacidade remanescente reportada (LineOfCreditFacilityRemainingBorrowingCapacity) ou 10% do ativo. A capacidade máxima
    contratada não é usada, porque não é disponibilidade (Apêndice A). Remanescente = 0 é observado: q = 0 e o ISC fica indefinido.
14. dei:EntityCommonStockSharesOutstanding é exigido, como no roteiro; isso retira firmas com mais de uma classe de ações
    (por exemplo Meta e Tyson). Regra de seleção, não de qualidade.
"""


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s)


RE_PAG = re.compile(r"(pag[oa]s?\b|pagamentos?\b|pagto|pgto|pagato|recolhid|recolhimento)")
RE_TRIB = re.compile(r"(imposto|\bir\b|irpj|csll|cssl|contribuicao social|tributos?\b)")
RE_TRIB_PURO = re.compile(r"(tributos? sobre o lucro|impostos? (de|sobre a?) renda|irpj|csll|cssl|\bir\b.*\bcs\b)")
RE_EXC_TRIB = re.compile(r"(a pagar|a recolher|diferid|parcelament|\bpis\b|cofins|\biss\b|icms|outros impostos|outros tributos|"
                         r"capital proprio|jcp|jscp|dividend|refinanc|nao pagos|provisao)")
RE_JUROS = re.compile(r"juros")
RE_ENC = re.compile(r"encargos( financeiros| de dividas?| de debentures?| de emprestimos?| sobre)")
RE_AMORT = re.compile(r"(amortiz\w*|liquid\w*) (de )?juros|juros (amortiz|liquid)")
RE_EXC_JUROS = re.compile(r"(a pagar|capital proprio|capital propio|jcp|jscp|recebid|mutuo|apropriad|provisao|provisionad|principal|"
                          r"nao pagos|dividend|sobre (o )?capital|s/ ?capital|(emprestimos?|financiamentos?|debentures?|dividas?) e juros)")


def e_tributo_pago(ds: str, conta: str) -> bool:
    """Linha de tributo sobre o lucro efetivamente pago, na atividade operacional (6.01)."""
    if not conta.startswith("6.01") or RE_EXC_TRIB.search(ds):
        return False
    if RE_TRIB.search(ds) and RE_PAG.search(ds):
        return True
    return conta.startswith("6.01.03") and bool(RE_TRIB_PURO.search(ds))     # sem palavra de pagamento, só em "Outros"


def e_juros_pago(ds: str, conta: str) -> bool:
    """Linha de juros pagos em qualquer atividade, fora dos ajustes não caixa (6.01.01)."""
    if conta.startswith("6.01.01") or RE_EXC_JUROS.search(ds):
        return False
    return bool((RE_JUROS.search(ds) and RE_PAG.search(ds)) or (RE_ENC.search(ds) and RE_PAG.search(ds)) or RE_AMORT.search(ds))


def _folha(codigos: List[str]) -> List[str]:
    """Remove contas cujo ancestral também casou, para não somar pai e filho."""
    s = set(codigos)
    return [c for c in codigos if not any(c.startswith(p + ".") for p in s if p != c)]


# ------------------------------------------------------------------------------------------------- CVM
SETORES_FIN = re.compile(r"(banco|segurad|seguros|intermedia|securitiza|arrendamento mercantil|factoring|"
                         r"bolsas? de valores|emp\. adm\. part\. - (banc|seg|interm|securit|arrend)|"
                         r"cart[oa]o de credito|corretora|financ|credito imobiliario)")
FIN_POR_NOME = {"16772": "BNDESPAR", "27111": "XP Investimentos"}   # setor "sem setor principal", atividade financeira


def _le_zip(caminho: str, sufixo: str, usecols=None) -> Optional[pd.DataFrame]:
    with zipfile.ZipFile(caminho) as z:
        nomes = [n for n in z.namelist() if n.endswith(sufixo)]
        if not nomes:
            return None
        with z.open(nomes[0]) as fh:
            return pd.read_csv(fh, sep=";", encoding="latin1", dtype=str, usecols=usecols)


def _conta(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["ORDEM_EXERC"].str.startswith("ÚLTIMO", na=False) | df["ORDEM_EXERC"].str.upper().str.startswith("ULTIMO", na=False)].copy()
    df["VR"] = pd.to_numeric(df["VL_CONTA"], errors="coerce")
    df["ESC"] = df["ESCALA_MOEDA"].str.upper()
    return df


def _deduplica(df: pd.DataFrame, chave: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Linhas repetidas com valores diferentes: fica o valor não nulo; dois valores não nulos excluem a firma–data."""
    df = df.assign(_nz=df["VR"].fillna(0) != 0)
    n = df[df["_nz"]].groupby(chave)["VR"].nunique()
    conf = n[n > 1].reset_index()[["CD_CVM", "DT_REFER"]].drop_duplicates()
    df = df.sort_values(chave + ["_nz"], ascending=[True] * len(chave) + [False], kind="stable").drop_duplicates(chave)
    return df.drop(columns="_nz"), conf


def _escala(E: pd.DataFrame, atrito: dict) -> pd.DataFrame:
    """Multiplicador por firma–data. Bandeira fora do padrão da firma, com ativo bruto da mesma ordem das datas vizinhas, é erro de bandeira."""
    A = E[E["CD_CONTA"] == "1"][["CD_CVM", "DT_REFER", "VR", "ESC"]].copy()
    linhas = []
    corrigidas = 0
    for c, g in A.groupby("CD_CVM"):
        g = g.sort_values("DT_REFER")
        moda = g["ESC"].mode()
        moda = moda.iloc[0] if len(moda) else "MIL"
        ref = g[g["ESC"] == moda]
        datas = pd.to_datetime(ref["DT_REFER"]).values
        vr = ref["VR"].values
        for d, v, f in zip(g["DT_REFER"], g["VR"], g["ESC"]):
            esc = f
            if f != moda and len(datas) and pd.notna(v) and v > 0:
                i = int(np.argmin(np.abs(datas - np.datetime64(d))))
                if vr[i] > 0 and 1 / 20 <= v / vr[i] <= 20:
                    esc = moda; corrigidas += 1
            linhas.append((c, d, 1e3 if esc == "MIL" else 1.0))
    atrito["BR_datas_com_bandeira_de_escala_corrigida"] = corrigidas
    return pd.DataFrame(linhas, columns=["CD_CVM", "DT_REFER", "mult"])


def carrega_cvm(atrito: dict) -> pd.DataFrame:
    cad = pd.read_csv(f"{RAW}/cvm/cad_cia_aberta.csv", sep=";", encoding="latin1", dtype=str)
    cad["setor"] = cad["SETOR_ATIV"].fillna("").map(_norm)
    cad["cd"] = cad["CD_CVM"].astype(str).str.lstrip("0")
    fin = {c for c, s in zip(cad["cd"], cad["setor"]) if SETORES_FIN.search(s)} | set(FIN_POR_NOME)
    no_cad = set(cad["cd"])
    atrito["BR_setores_excluidos"] = sorted(set(cad["SETOR_ATIV"].dropna()[cad["setor"].map(lambda s: bool(SETORES_FIN.search(s)))]))
    estoque, fluxo, recebe = [], [], []
    contas_est = {"1", "1.01.01", "2.01.04", "2.03", "2.03.01", "2.03.02", "2.03.04", "2.03.05"}
    contas_dre = {"3.01", "3.05"}
    for ano in ANOS:
        for doc in ("itr", "dfp"):
            z = f"{RAW}/cvm/{doc}_cia_aberta_{ano}.zip"
            idx = _le_zip(z, f"{doc}_cia_aberta_{ano}.csv")
            recebe.append(idx.assign(doc=doc)[["CD_CVM", "DT_REFER", "DT_RECEB", "doc"]])
            for est in ("BPA", "BPP"):
                for cons, prio in (("con", 0), ("ind", 1)):
                    d = _le_zip(z, f"{doc}_cia_aberta_{est}_{cons}_{ano}.csv")
                    if d is None:
                        continue
                    d = _conta(d[d["CD_CONTA"].isin(contas_est)])
                    estoque.append(d.assign(doc=doc, prio=prio)[["CD_CVM", "DT_REFER", "CD_CONTA", "DS_CONTA", "VR", "ESC", "doc", "prio"]])
            for est in ("DRE", "DFC_MI", "DFC_MD"):
                for cons, prio in (("con", 0), ("ind", 1)):
                    d = _le_zip(z, f"{doc}_cia_aberta_{est}_{cons}_{ano}.csv")
                    if d is None:
                        continue
                    d = _conta(d)
                    if est == "DRE":
                        d = d[d["CD_CONTA"].isin(contas_dre)].assign(item=lambda x: x["CD_CONTA"].map({"3.01": "rec", "3.05": "ebit"}))
                    else:
                        d = d[d["CD_CONTA"].str.startswith("6.", na=False)]
                        ds = d["DS_CONTA"].map(_norm)
                        trib = [e_tributo_pago(s, c) for s, c in zip(ds, d["CD_CONTA"])]
                        juros = [e_juros_pago(s, c) for s, c in zip(ds, d["CD_CONTA"])]
                        d = pd.concat([d[d["CD_CONTA"] == "6.01"].assign(item="cfo"), d[trib].assign(item="trib"), d[juros].assign(item="juros")])
                    d = d[d["DT_INI_EXERC"].notna()]
                    fluxo.append(d.assign(doc=doc, prio=prio, est=est)[["CD_CVM", "DT_REFER", "DT_INI_EXERC", "CD_CONTA", "DS_CONTA", "item", "VR", "ESC", "doc", "prio", "est"]])
        print("CVM", ano, flush=True)
    E = pd.concat(estoque); F = pd.concat(fluxo); R = pd.concat(recebe)
    for df in (E, F, R):
        df["CD_CVM"] = df["CD_CVM"].astype(str).str.lstrip("0")
    atrito["BR_firmas_brutas"] = int(E["CD_CVM"].nunique())
    fora = set(E["CD_CVM"]) - no_cad
    atrito["BR_fora_do_cadastro"] = len(fora)
    # plano de contas financeiro: 2.03 com rótulo de banco, ou receita de intermediação financeira
    plano = set(E[(E["CD_CONTA"] == "2.03") & E["DS_CONTA"].map(_norm).str.contains("passivos financeiros|provisoes", na=False)]["CD_CVM"])
    plano |= set(F[(F["item"] == "rec") & F["DS_CONTA"].map(_norm).str.contains("intermediacao financeira", na=False)]["CD_CVM"])
    atrito["BR_plano_de_contas_financeiro"] = sorted(plano)
    excl = fin | fora | plano
    E = E[~E["CD_CVM"].isin(excl)]; F = F[~F["CD_CVM"].isin(excl)]
    atrito["BR_firmas_nao_financeiras"] = int(E["CD_CVM"].nunique())
    return _monta_br(E, F, R, atrito)


def _monta_br(E: pd.DataFrame, F: pd.DataFrame, R: pd.DataFrame, atrito: dict) -> pd.DataFrame:
    E, c1 = _deduplica(E, ["CD_CVM", "DT_REFER", "CD_CONTA", "prio"])
    F, c2 = _deduplica(F, ["CD_CVM", "DT_REFER", "DT_INI_EXERC", "CD_CONTA", "item", "prio", "est"])
    conf = pd.concat([c1, c2]).drop_duplicates()
    atrito["BR_firma_data_com_valores_conflitantes"] = len(conf)
    if len(conf):
        chave = set(zip(conf["CD_CVM"], conf["DT_REFER"]))
        E = E[[k not in chave for k in zip(E["CD_CVM"], E["DT_REFER"])]]
        F = F[[k not in chave for k in zip(F["CD_CVM"], F["DT_REFER"])]]
    # nível (consolidado/individual) único por firma–data: consolidado com ativo > 0, senão individual
    A = E[(E["CD_CONTA"] == "1") & (E["VR"] > 0)].sort_values("prio").drop_duplicates(["CD_CVM", "DT_REFER"])[["CD_CVM", "DT_REFER", "prio"]].rename(columns={"prio": "nivel"})
    E = E.merge(A, on=["CD_CVM", "DT_REFER"]); E = E[E["prio"] == E["nivel"]]
    F = F.merge(A, on=["CD_CVM", "DT_REFER"]); F = F[F["prio"] == F["nivel"]]
    # escala
    M = _escala(E, atrito)
    E = E.merge(M, on=["CD_CVM", "DT_REFER"]); F = F.merge(M, on=["CD_CVM", "DT_REFER"])
    E["VL"] = E["VR"] * E["mult"]; F["VL"] = F["VR"] * F["mult"]
    B = E.pivot(index=["CD_CVM", "DT_REFER"], columns="CD_CONTA", values="VL")
    R["DT_RECEB"] = pd.to_datetime(R["DT_RECEB"], errors="coerce")
    rec = R.groupby(["CD_CVM", "DT_REFER"])["DT_RECEB"].min()
    dfp = {(c, d) for c, d in zip(R[R["doc"] == "dfp"]["CD_CVM"], R[R["doc"] == "dfp"]["DT_REFER"])}
    # fluxos: DFC_MI antes de DFC_MD, dentro do nível da data
    F = F.assign(pest=F["est"].map({"DRE": 0, "DFC_MI": 0, "DFC_MD": 1}))
    F = F.sort_values(["CD_CVM", "DT_REFER", "DT_INI_EXERC", "item", "pest"])
    chave = ["CD_CVM", "DT_REFER", "DT_INI_EXERC", "item"]
    F = F[F["pest"] == F.groupby(chave)["pest"].transform("first")]
    F = F.drop_duplicates(chave + ["CD_CONTA"])
    linhas = []
    for k, g in F.groupby(chave, sort=False):
        cods = list(g["CD_CONTA"])
        fo = _folha(cods) if k[3] in ("trib", "juros") else cods
        linhas.append((*k, g[g["CD_CONTA"].isin(fo)]["VL"].sum(min_count=1), g["nivel"].iloc[0]))
    Y = pd.DataFrame(linhas, columns=chave + ["VL", "nivel"])
    Y["ini"] = pd.to_datetime(Y["DT_INI_EXERC"], errors="coerce"); Y["fim"] = pd.to_datetime(Y["DT_REFER"], errors="coerce")
    Y = Y[Y["ini"].notna() & Y["fim"].notna()]
    Y["meses"] = ((Y["fim"] - Y["ini"]).dt.days / 30.4).round().astype(int)
    yt = Y[Y["meses"].isin([3, 6, 9, 12])].sort_values(["CD_CVM", "item", "fim", "meses"]).drop_duplicates(["CD_CVM", "item", "fim"], keep="last")
    q = {}
    anual = defaultdict(dict)
    for (c, it), g in yt.groupby(["CD_CVM", "item"]):
        d = {r.fim: (r.meses, r.VL, r.ini, r.nivel) for r in g.itertuples()}
        for fim, (m, v, ini, niv) in d.items():
            if m == 12:
                anual[(c, it)][fim] = v
            if m == 3:
                q[(c, it, fim)] = v
            else:
                ant = fim + pd.offsets.MonthEnd(-3)
                if ant in d and d[ant][0] == m - 3 and d[ant][2] == ini and d[ant][3] == niv:
                    q[(c, it, fim)] = v - d[ant][1]
    linhas = []
    firmas = sorted(B.index.get_level_values(0).unique())
    for c in firmas:
        bc = B.loc[c]
        ends = sorted(pd.to_datetime(bc.index))
        atv = {e: bc.loc[e.strftime("%Y-%m-%d")].get("1") for e in ends}
        fys = [e for e in ends if (c, e.strftime("%Y-%m-%d")) in dfp]
        for fim in ends:
            s = fim.strftime("%Y-%m-%d")
            b = bc.loc[s]
            ativo = b.get("1")
            if pd.isna(ativo) or ativo <= 0:
                continue
            filing = rec.get((c, s), pd.NaT)
            if pd.isna(filing):
                continue
            futs = [fim + pd.offsets.MonthEnd(3 * k) for k in range(1, T + 1)]
            # salto de escala que a correção de bandeira não resolveu: o horizonte não é confiável
            jan = [atv[e] for e in ends if fim <= e <= futs[-1] and pd.notna(atv[e]) and atv[e] > 0]
            quebra = any(max(a / b_, b_ / a) > 200 for a, b_ in zip(jan[:-1], jan[1:]))
            cfo = [q.get((c, "cfo", f)) for f in futs]; ebit = [q.get((c, "ebit", f)) for f in futs]
            tr = [q.get((c, "trib", f)) for f in futs]
            # último exercício encerrado e publicado até a data de decisão
            pub = [e for e in fys if e <= fim and pd.notna(rec.get((c, e.strftime("%Y-%m-%d")), pd.NaT)) and rec.get((c, e.strftime("%Y-%m-%d"))) <= filing]
            bf = bc.loc[pub[-1].strftime("%Y-%m-%d")] if pub else None
            la = None
            if bf is not None:
                la = max(0.0, np.nan_to_num(bf.get("2.03.04", np.nan)) + max(0.0, np.nan_to_num(bf.get("2.03.05", np.nan))))
            juros = None
            if pub:
                vj = anual[(c, "juros")].get(pub[-1])
                juros = -vj if (vj is not None and pd.notna(vj) and vj < 0) else None
            tr_an = anual[(c, "trib")]
            an_fut = []
            for f in futs:
                op = [e for e in tr_an if f <= e < f + pd.DateOffset(months=12)]
                an_fut.append(-tr_an[min(op)] if op and pd.notna(tr_an[min(op)]) else None)
            pl = None
            if pd.notna(b.get("2.03.01", np.nan)):
                pl = sum(np.nan_to_num(b.get(k, np.nan)) for k in ("2.03.01", "2.03.02", "2.03.04")) + min(0.0, np.nan_to_num(b.get("2.03.05", np.nan)))
            linhas.append(dict(firm_id=f"BR-{c}", country="BR", period_end=s, filing_date=filing.strftime("%Y-%m-%d"), ativo=ativo,
                               caixa=b.get("1.01.01"), dcp=b.get("2.01.04"), rec=q.get((c, "rec", fim)), ebit_t=q.get((c, "ebit", fim)),
                               cfo=cfo, ebit=ebit, trib=[-x if x is not None and pd.notna(x) else None for x in tr],
                               trib_anual=an_fut, juros_ano=juros, LA=la, PF=None, PL=pl, line_O=None, c_cls="O", quebra=quebra))
    return pd.DataFrame(linhas)


# ------------------------------------------------------------------------------------------------- SEC
FORMS = ("10-Q", "10-K", "10-Q/A", "10-K/A", "10-KT", "10-QT")


def _fatos(ug: dict, tags: List[str], unidade: str = "USD") -> List[dict]:
    """Une as tags na ordem dada: a tag seguinte só preenche datas (ou períodos) que as anteriores não têm."""
    vistos, out = set(), []
    for i, t in enumerate(tags):
        v = ug.get(t, {}).get("units", {}).get(unidade) or []
        chaves = set()
        for e in v:
            k = (e.get("start"), e["end"])
            chaves.add(k)
            if k not in vistos:
                out.append(dict(e, _i=i))
        vistos |= chaves
    return out


def _escolhe(versoes: List[Tuple[str, float]]) -> Tuple[float, str]:
    """Primeira versão publicada; versão posterior só corrige erro de escala (potência de 10) ou de sinal (exatamente oposto)."""
    versoes = sorted(versoes, key=lambda z: z[0])
    f0, v = versoes[0]
    for _, x in versoes[1:]:
        if v == 0 or x == 0 or x == v:
            continue
        if x == -v:
            v = x
            continue
        k = math.log10(abs(x / v))
        if round(k) != 0 and abs(k - round(k)) < 1e-6:
            v = x if abs(x) < abs(v) else v
    return v, f0


def _instantes(v: List[dict]) -> Dict[pd.Timestamp, Tuple[float, str, int]]:
    d = defaultdict(list); tag = {}
    for e in v:
        if e.get("form", "") not in FORMS or "start" in e or e.get("filed", "9999") <= e["end"]:
            continue
        d[e["end"]].append((e.get("filed", "9999"), float(e["val"])))
        tag[e["end"]] = e.get("_i", 0)
    return {pd.Timestamp(k): (*_escolhe(x), tag[k]) for k, x in d.items()}


def _duracoes(v: List[dict]) -> Dict[Tuple[pd.Timestamp, pd.Timestamp], Tuple[float, str]]:
    d = defaultdict(list)
    for e in v:
        if "start" not in e or e.get("form", "") not in FORMS or e.get("filed", "9999") <= e["end"]:
            continue
        d[(e["start"], e["end"])].append((e.get("filed", "9999"), float(e["val"])))
    return {(pd.Timestamp(a), pd.Timestamp(b)): _escolhe(x) for (a, b), x in d.items()}


def _trimestre(dur, fim, ant) -> Optional[float]:
    """Fluxo do trimestre: período direto publicado em até 150 dias; senão diferença de acumulados com o mesmo início;
    o período direto publicado tarde (reapresentação) fica como último recurso."""
    por_fim = [(s, x) for (s, e), x in dur.items() if e == fim]
    tarde = None
    limite = (fim + pd.Timedelta(days=150)).strftime("%Y-%m-%d")
    for s, x in por_fim:
        if TRI_MIN <= (fim - s).days <= TRI_MAX:
            if x[1] <= limite:
                return x[0]
            tarde = x[0]
    if ant is not None:
        for s, x in por_fim:
            if (fim - s).days > TRI_MAX:
                for (s2, e2), x2 in dur.items():
                    if s2 == s and abs((e2 - ant).days) <= 6:
                        return x[0] - x2[0]
    return tarde


def _anual(dur, fim_max: pd.Timestamp, filed_max: str, dias: int = 400) -> Optional[float]:
    op = [(e, x) for (s, e), x in dur.items() if 350 <= (e - s).days <= 380 and e <= fim_max and x[1] <= filed_max and (fim_max - e).days <= dias]
    return max(op, key=lambda z: z[0])[1][0] if op else None


def _ultimo(inst, data: pd.Timestamp, filed_max: str, dias: int) -> Optional[float]:
    op = [(e, x) for e, x in inst.items() if e <= data and x[1] <= filed_max and (data - e).days <= dias]
    return max(op, key=lambda z: z[0])[1][0] if op else None


TAGS_REC = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"]


def carrega_sec(atrito: dict, limite: Optional[int] = None) -> pd.DataFrame:
    arquivos = sorted(glob.glob(f"{RAW}/sec/facts/*.json.gz"))
    if limite:
        arquivos = arquivos[:limite]
    linhas = []
    cont = defaultdict(int)
    for a in arquivos:
        cik = os.path.basename(a).split(".")[0]
        cont["US_ciks"] += 1
        sp = f"{RAW}/sec/subm/{cik}.json.gz"
        if not os.path.exists(sp):
            cont["US_sem_submissions"] += 1; continue
        with gzip.open(sp, "rt", encoding="utf-8") as fh:
            sic = json.load(fh).get("sic") or ""
        if not sic or 6000 <= int(sic) <= 6799:
            cont["US_financeiras_ou_sem_SIC"] += 1; continue
        with gzip.open(a, "rt", encoding="utf-8") as fh:
            fatos_all = json.load(fh).get("facts", {})
        if "EntityCommonStockSharesOutstanding" not in fatos_all.get("dei", {}):
            cont["US_sem_dei_shares"] += 1; continue
        ug = fatos_all.get("us-gaap", {})
        A_ = _instantes(_fatos(ug, ["Assets"]))
        if not A_:
            cont["US_sem_assets"] += 1; continue
        CX = _instantes(_fatos(ug, ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]))
        CFO = _duracoes(_fatos(ug, ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]))
        EB = _duracoes(_fatos(ug, ["OperatingIncomeLoss"]))
        # o sinal do tributo pago varia entre versões e firmas: o acumulado é tomado em módulo; a diferença preserva a restituição
        TR = {k: (abs(x[0]), x[1]) for k, x in _duracoes(_fatos(ug, ["IncomeTaxesPaidNet", "IncomeTaxesPaid"])).items()}
        JU = _duracoes(_fatos(ug, ["InterestPaidNet", "InterestPaid"]))
        RECS = [_duracoes(ug.get(t_, {}).get("units", {}).get("USD", [])) for t_ in TAGS_REC]
        REC_U = _duracoes(_fatos(ug, TAGS_REC))
        DC = _instantes(_fatos(ug, ["DebtCurrent"])); LC = _instantes(_fatos(ug, ["LongTermDebtCurrent"]))
        RE_ = _instantes(_fatos(ug, ["RetainedEarningsAccumulatedDeficit"]))
        PL_ = _instantes(_fatos(ug, ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]))
        NOL = _instantes(_fatos(ug, ["DeferredTaxAssetsOperatingLossCarryforwards"]))
        LR = _instantes(_fatos(ug, ["LineOfCreditFacilityRemainingBorrowingCapacity"]))
        # fins de trimestre: balanços publicados em até 150 dias; data extra perto de outra sai (fica a que tem fluxo)
        ends0 = sorted(e for e, x in A_.items() if e.year in ANOS and x[1] <= (e + pd.Timedelta(days=150)).strftime("%Y-%m-%d"))
        fins_cfo = {e for (_, e) in CFO}
        ends = []
        for e in ends0:
            if ends and (e - ends[-1]).days < TRI_MIN:
                if e in fins_cfo or ends[-1] not in fins_cfo:
                    ends[-1] = e
                continue
            ends.append(e)
        if not ends:
            cont["US_sem_datas"] += 1; continue
        cont["US_firmas_elegiveis"] += 1
        ant = {e: p for p, e in zip(ends[:-1], ends[1:]) if TRI_MIN <= (e - p).days <= TRI_MAX}
        prox = {p: e for p, e in zip(ends[:-1], ends[1:]) if TRI_MIN <= (e - p).days <= TRI_MAX}
        flow = {nome: {e: _trimestre(dur, e, ant.get(e)) for e in ends} for nome, dur in (("cfo", CFO), ("ebit", EB), ("trib", TR))}
        rec_q = {}
        for e in ends:
            val = None
            for dur in RECS:
                x = _trimestre(dur, e, ant.get(e))
                if x is not None and x > 0:
                    val = x; break
            rec_q[e] = val if val is not None else _trimestre(REC_U, e, ant.get(e))
        for fim in ends:
            ativo, filed, _ = A_[fim]
            if ativo <= 0:
                continue
            futs = []; e = fim
            for _i in range(T):
                e = prox.get(e)
                if e is None:
                    break
                futs.append(e)
            if len(futs) < T:
                cont["US_sem_4_trimestres_a_frente"] += 1
                continue
            tr_an = []
            for f in futs:
                op = [(en, x) for (s, en), x in TR.items() if 350 <= (en - s).days <= 380 and en >= f and (en - f).days <= 300]
                tr_an.append(min(op, key=lambda z: z[0])[1][0] if op else None)

            def no_prazo(inst):      # estoque da data t, conhecido na data de decisão
                x = inst.get(fim)
                return x[0] if x is not None and x[1] <= filed else None
            lin = _ultimo(LR, fim, filed, 400)
            d = no_prazo(DC)
            if d is None:
                d = no_prazo(LC)
            nol = _ultimo(NOL, fim, filed, 400)
            re_ = _ultimo(RE_, fim, filed, 400)
            cx = no_prazo(CX)
            linhas.append(dict(firm_id=f"US-{int(cik)}", country="US", period_end=fim.strftime("%Y-%m-%d"), filing_date=filed, ativo=ativo,
                               caixa=cx, dcp=d, rec=rec_q.get(fim), ebit_t=flow["ebit"].get(fim),
                               cfo=[flow["cfo"].get(f) for f in futs], ebit=[flow["ebit"].get(f) for f in futs],
                               trib=[flow["trib"].get(f) for f in futs], trib_anual=tr_an,
                               juros_ano=(lambda j: None if j is None else abs(j))(_anual(JU, fim, filed)), LA=None if re_ is None else max(0.0, re_),
                               PF=None if nol is None else max(0.0, nol) / TAU_US, PL=no_prazo(PL_), line_O=lin,
                               c_cls="O" if (cx is not None and CX[fim][2] == 0) else "D", quebra=False))
        if cont["US_firmas_elegiveis"] % 200 == 0:
            print("SEC", cont["US_firmas_elegiveis"], flush=True)
    atrito.update(cont)
    return pd.DataFrame(linhas)


# ------------------------------------------------------------------------------------------------- macro
def macro() -> Dict[str, pd.Series]:
    def sgs(nome):
        reg = []
        for f in sorted(glob.glob(f"{RAW}/macro/sgs_{nome}_*.json")):
            with open(f, encoding="utf-8") as fh:
                reg += json.load(fh)
        s = pd.Series({pd.to_datetime(r["data"], dayfirst=True): float(r["valor"]) for r in reg}).sort_index()
        return s[~s.index.duplicated()]
    sofr = pd.read_csv(f"{RAW}/macro/fred_SOFR.csv", na_values=[".", ""])
    sofr = pd.Series(sofr["SOFR"].values, index=pd.to_datetime(sofr["observation_date"])).dropna().sort_index()
    return {"cdi": sgs("cdi_aa"), "tjlp": sgs("tjlp_aa"), "sofr": sofr}


def _na_data(s: pd.Series, d: pd.Timestamp) -> Optional[float]:
    if d < s.index[0]:
        return None
    return float(s.asof(d))


CLASSE = {"O": 0, "D": 1, "P": 2, "E": 3}


def finaliza(df: pd.DataFrame, atrito: dict) -> pd.DataFrame:
    M = macro()
    rows = []
    motivos = defaultdict(int)
    for r in df.to_dict("records"):
        ct = r["country"]
        tag = ct + "_"
        motivos[tag + "pontos_brutos"] += 1
        a = float(r["ativo"])
        fil = pd.Timestamp(r["filing_date"])
        if r.get("quebra"):
            motivos[tag + "quebra_de_escala_no_horizonte"] += 1; continue
        if ct == "US":
            s_ = _na_data(M["sofr"], fil)
            if s_ is None:
                motivos[tag + "sem_SOFR_antes_de_2018-04"] += 1; continue
            rate = (s_ + 3.0) / 100.0 / 4.0
            tj = 0.0
        else:
            c_ = _na_data(M["cdi"], fil); t_ = _na_data(M["tjlp"], fil)
            if c_ is None or t_ is None:
                motivos[tag + "sem_taxa"] += 1; continue
            rate = (c_ + 4.0) / 100.0 / 4.0
            tj = t_ / 100.0 / 4.0
        falta = None
        cfo = r["cfo"]; eb = r["ebit"]
        for nome, ok in (("caixa", pd.notna(r["caixa"])), ("receita_t", pd.notna(r["rec"])), ("ebit_t", pd.notna(r["ebit_t"])),
                         ("fco_futuro", isinstance(cfo, list) and all(x is not None and pd.notna(x) for x in cfo)),
                         ("ebit_futuro", isinstance(eb, list) and all(x is not None and pd.notna(x) for x in eb)),
                         ("PL", pd.notna(r["PL"])), ("LA", pd.notna(r["LA"]))):
            if not ok:
                falta = nome; break
        if falta:
            motivos[tag + "falta_" + falta] += 1; continue
        fco = []; cf = "O"
        for k in range(T):
            t_ = r["trib"][k]; an = r["trib_anual"][k]
            if t_ is not None and pd.notna(t_) and abs(t_) <= a:
                add = float(t_)
            elif an is not None and pd.notna(an) and abs(an) / 4.0 <= a:
                add = float(an) / 4.0; cf = "D" if cf == "O" else cf
            else:
                add = 0.0; cf = "P"
            fco.append((cfo[k] + add) / a)
        pi = [x / a for x in eb]
        d = r["dcp"]; dc = "D"
        if d is None or pd.isna(d):
            d = 0.0; dc = "P"
        j = r["juros_ano"]
        if j is None or pd.isna(j):
            j = 0.0; dc = "P"
        S_ = (max(0.0, float(d)) / 4.0 + abs(float(j)) / 4.0) / a
        L_ = 0.05 * max(0.0, float(r["rec"])) / a
        la, lc = 0.10, "P"
        if r["line_O"] is not None and pd.notna(r["line_O"]):
            v = max(0.0, float(r["line_O"])) / a
            if v == 0.0 or v >= 1e-5:      # abaixo disso é valor sem escala na XBRL (por exemplo 0,6 em milhões)
                la, lc = v, "O"
                if v == 0.0:
                    motivos[tag + "line_remanescente_zero_observado"] += 1
        if r["PF"] is not None and pd.notna(r["PF"]):
            pf, pc = max(0.0, float(r["PF"])) / a, "O"
        else:
            pf, pc = 0.0, "P"
        pl = max(0.0, float(r["PL"])) / a; pl_neg = float(r["PL"]) < 0
        ln = dict(firm_id=r["firm_id"], country=ct, period_end=r["period_end"], filing_date=r["filing_date"], T=T,
                  C0=float(r["caixa"]) / a, L=L_, S=S_, S_sem_juros=max(0.0, float(d)) / 4.0 / a, line_A=la, line_rate=rate, r_tjlp=tj, q_frac=1.0,
                  LA0=float(r["LA"]) / a, PF0=pf, PL0=pl, ebit_ativo=float(r["ebit_t"]) / a,
                  cls_C0=r["c_cls"], cls_fco=cf, cls_S=dc, cls_line_A=lc, cls_PF0=pc, pl_negativo=int(pl_neg))
        for k in range(T):
            ln[f"fco_{k+1}"] = fco[k]; ln[f"pi_{k+1}"] = pi[k]
        vals = [ln["C0"], ln["L"], ln["S"], ln["line_A"], ln["LA0"], ln["PF0"], ln["PL0"]] + fco + pi
        if not np.isfinite(vals).all() or max(abs(x) for x in vals) >= LIMITE_RAZAO:
            motivos[tag + "razao_extrema"] += 1; continue
        ln["data_class"] = max([ln["cls_C0"], cf, dc, lc, pc, "D", "P"], key=lambda c: CLASSE[c])   # L e q_frac são P por construção
        motivos[tag + "no_painel"] += 1
        rows.append(ln)
    P = pd.DataFrame(rows)
    P["tri"] = pd.PeriodIndex(pd.to_datetime(P["period_end"]) - pd.Timedelta(days=16), freq="Q").astype(str)

    def terc(g):
        o = g.rank(method="first", pct=True)
        return pd.Series(np.where(o <= 1 / 3, "prejuizo", np.where(o <= 2 / 3, "equilibrio", "lucro")), index=g.index)
    P["regime"] = P.groupby(["country", "tri"])["ebit_ativo"].transform(terc)
    atrito.update(motivos)
    return P


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite_us", type=int, default=None)
    a = ap.parse_args()
    atrito = {}
    us = carrega_sec(atrito, a.limite_us)
    br = carrega_cvm(atrito)
    P = finaliza(pd.concat([br, us], ignore_index=True), atrito)
    os.makedirs(OUT, exist_ok=True)
    P.to_csv(f"{OUT}/painel_BR_US.csv", index=False)
    # taxa mediana de cada jurisdição no trimestre e TJLP mediana (só o Brasil tem JCP)
    med = P.groupby(["country", "tri"])["line_rate"].median()
    tj = P[P["country"] == "BR"].groupby("tri")["r_tjlp"].median()
    outro = {"BR": "US", "US": "BR"}
    tx_outra = [med.get((outro[c], t), np.nan) for c, t in zip(P["country"], P["tri"])]
    tj_br = [tj.get(t, np.nan) for t in P["tri"]]
    base = P.assign(tx_outra=tx_outra, tj_br=tj_br)
    base = base[base["tx_outra"].notna() & base["tj_br"].notna()]
    atrito["pontos_sem_taxa_da_outra_jurisdicao"] = int(len(P) - len(base))
    cf = base.assign(line_rate=base["tx_outra"]).drop(columns=["tx_outra", "tj_br"])
    cf.to_csv(f"{OUT}/painel_BR_US_cf_taxa.csv", index=False)
    rt = base.assign(country=base["country"].map(outro), r_tjlp=np.where(base["country"] == "US", base["tj_br"], 0.0))
    rt.assign(line_rate=rt["tx_outra"]).drop(columns=["tx_outra", "tj_br"]).to_csv(f"{OUT}/painel_BR_US_troca.csv", index=False)
    rt.drop(columns=["tx_outra", "tj_br"]).to_csv(f"{OUT}/painel_BR_US_troca_taxa.csv", index=False)
    atrito["escolhas"] = ESCOLHAS
    with open(f"{OUT}/atrito.json", "w", encoding="utf-8") as fh:
        json.dump(atrito, fh, ensure_ascii=False, indent=1, default=str)
    print({k: v for k, v in atrito.items() if k not in ("escolhas", "BR_setores_excluidos", "BR_plano_de_contas_financeiro")})


if __name__ == "__main__":
    main()
