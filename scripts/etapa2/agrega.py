"""Etapa 2, seções 5–6 do roteiro: Tabelas 5–6 em dados reais, H1–H3 com bootstrap por firma, composição por classe.

BR e EUA têm firmas diferentes. A comparação institucional (H2, H3, Tabela 6A) usa, como experiment_I.py, a mesma firma sob as
regras das duas jurisdições; a diferença entre as amostras aparece à parte, como dado descritivo (Tabela 6B).

Uso:  python scripts/etapa2/agrega.py
Saídas: results/panel/tabelas.md, results/panel/figura.png, results/panel/agregados_*.csv.
"""
from __future__ import annotations

import glob
import json
import os

import numpy as np
import pandas as pd

SEMENTE = 20261104
B = 1000
OUT = "results/panel"
REG = ["lucro", "equilibrio", "prejuizo"]
COLS = ["firm_id", "country", "period_end", "regime", "config", "status", "status_custo", "folga_custo", "q", "E_base", "E_shock", "ISC", "CLS", "DIP_shock", "JCP_shock"]
RODAPE_CLASSE = "Classes de dados: ver a seção de composição; `data_class` é P em todas as linhas."


def f(v, n=3):
    return "—" if v is None or (isinstance(v, (float, np.floating)) and not np.isfinite(v)) else f"{v:.{n}f}"


def ler(arq: str) -> pd.DataFrame:
    d = pd.read_csv(arq, usecols=lambda c: c in COLS)
    d["origem"] = d["firm_id"].str[:2]
    return d


class Boot:
    """Blocos por firma, estratificados pela amostra de origem, com pesos multinomiais e semente fixa."""

    def __init__(self, df: pd.DataFrame):
        self.firmas = {c: sorted(g["firm_id"].unique()) for c, g in df.groupby("origem")}
        rng = np.random.default_rng(SEMENTE)
        self.w = {c: rng.multinomial(len(fs), [1 / len(fs)] * len(fs), size=B) for c, fs in self.firmas.items()}

    def media(self, df: pd.DataFrame, valor: str) -> np.ndarray:
        d = df[df[valor].notna()]
        c = d["origem"].iloc[0]
        agr = d.groupby("firm_id")[valor].agg(["sum", "size"]).reindex(self.firmas[c]).fillna(0.0)
        W = self.w[c]
        return (W @ agr["sum"].values) / np.maximum(W @ agr["size"].values, 1)

    def mediana(self, df: pd.DataFrame, valor: str) -> np.ndarray:
        d = df[df[valor].notna()]
        c = d["origem"].iloc[0]
        pos = {x: i for i, x in enumerate(self.firmas[c])}
        idx = d["firm_id"].map(pos).values
        v = d[valor].values
        o = np.argsort(v); v = v[o]; idx = idx[o]
        W = self.w[c]
        out = np.empty(B)
        for b in range(B):
            cw = np.cumsum(W[b, idx])
            out[b] = v[np.searchsorted(cw, cw[-1] / 2.0)] if cw[-1] > 0 else np.nan
        return out


def ic(v):
    v = v[np.isfinite(v)]
    return np.percentile(v, 2.5), np.percentile(v, 97.5)


def veredito(est, c, esp):
    """Compara o IC de 95% com a direção pré-especificada; não confunde 'não confirmou' com 'contrariou'."""
    lo, hi = c
    if abs(lo) < 1e-12 and abs(hi) < 1e-12:
        return "sem variação: estatística igual a 0"
    if esp == "<0":
        return "confirma" if hi < 0 else ("contraria" if lo > 0 else "inconclusivo (IC inclui 0)")
    if esp == "<=0":
        return "confirma" if hi <= 0 else ("contraria" if lo > 0 else "inconclusivo (IC inclui 0)")
    return "confirma" if lo > 0 else ("contraria" if hi < 0 else "inconclusivo (IC inclui 0)")


def linha(am, nome, est, vet, esp):
    c = ic(vet)
    return f"| {am} | {nome} | {f(est, 4)} | [{f(c[0], 4)}; {f(c[1], 4)}] | {esp.replace('<=', '≤ ').replace('<', '< ').replace('>', '> ')} | {veredito(est, c, esp)} |"


def mesma_firma(R, CF, TR, TX) -> pd.DataFrame:
    """Para cada ponto de decisão: BRr = regras BR e taxa BR; BRu = regras BR e taxa US; USr = regras US e taxa BR; USu = regras US e taxa US."""
    k = ["firm_id", "period_end", "config"]
    M = R[k + ["origem", "regime", "ISC", "CLS"]]
    for nome, d in (("cf", CF), ("tr", TR), ("tx", TX)):
        M = M.merge(d[k + ["ISC", "CLS"]].rename(columns={"ISC": "ISC_" + nome, "CLS": "CLS_" + nome}), on=k, validate="one_to_one")
    br = M["origem"] == "BR"
    for m in ("ISC", "CLS"):
        BRr = np.where(br, M[m], M[m + "_tr"]); USu = np.where(br, M[m + "_tr"], M[m])
        BRu = np.where(br, M[m + "_cf"], M[m + "_tx"]); USr = np.where(br, M[m + "_tx"], M[m + "_cf"])
        M["g" + m] = BRr - USu
        M["r" + m] = 0.5 * ((BRr - BRu) + (USr - USu))
    return M


def gap(M, bt, val, regime, cfg):
    """Média e vetor bootstrap por amostra e na média simples das duas amostras."""
    d = M[(M["regime"] == regime) & (M["config"] == cfg)]
    out = {}
    for c in ("BR", "US"):
        g = d[d["origem"] == c]
        out[c] = (g[val].mean(), bt.media(g, val))
    out["media"] = (0.5 * (out["BR"][0] + out["US"][0]), 0.5 * (out["BR"][1] + out["US"][1]))
    return out


def testes(R, M, am, completo=False):
    """H1 na amostra própria; H2 e H3 na mesma firma sob as duas jurisdições."""
    L = []
    bt = Boot(R)

    def cel(c, r, cfg):
        return R[(R["origem"] == c) & (R["regime"] == r) & (R["config"] == cfg)]
    for c in ("BR", "US"):
        a, b = cel(c, "prejuizo", "no_dip"), cel(c, "lucro", "no_dip")
        L.append(linha(am, f"H1 {c}: ISC(prejuízo) − ISC(lucro), no_dip, média", a["ISC"].mean() - b["ISC"].mean(), bt.media(a, "ISC") - bt.media(b, "ISC"), "<0"))
        if completo:
            L.append(linha(am, f"H1 {c}: idem, mediana", a["ISC"].median() - b["ISC"].median(), bt.mediana(a, "ISC") - bt.mediana(b, "ISC"), "<0"))
    bm = Boot(M)
    for cfg, esp in (("no_dip", "<=0"), ("all_on", ">0")):
        g = gap(M, bm, "gISC", "prejuizo", cfg)
        L.append(linha(am, f"H2 mesma firma: ISC_BR − ISC_US, prejuízo, {cfg}", g["media"][0], g["media"][1], esp))
        if completo:
            for c in ("BR", "US"):
                L.append(linha(am, f"H2 mesma firma, só firmas {c}, {cfg}", g[c][0], g[c][1], esp))

    def did(cfg):
        a, b = gap(M, bm, "gCLS", "prejuizo", cfg), gap(M, bm, "gCLS", "lucro", cfg)
        return a["media"][0] - b["media"][0], a["media"][1] - b["media"][1]
    on, off = did("all_on"), did("no_jcp")
    L.append(linha(am, "H3 mesma firma: contribuição do JCP à DiD do CLS (all_on − no_jcp)", on[0] - off[0], on[1] - off[1], ">0"))
    return L


def composicao(P: pd.DataFrame) -> list:
    L = ["| País | Regime | N | EBIT<0 em t | Σπ futuro<0 | PL<0 (limitado a 0) | C0 O/D | FCO O/D/P | S D/P | line_A O/P | PF0 O/P |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    soma_pi = P[[f"pi_{k}" for k in range(1, 5)]].sum(axis=1)
    for (c, r), g in P.groupby(["country", "regime"]):
        s = lambda col, cl: f"{100 * (g[col] == cl).mean():.0f}"
        L.append(f"| {c} | {r} | {len(g)} | {100 * (g['ebit_ativo'] < 0).mean():.0f}% | {100 * (soma_pi[g.index] < 0).mean():.0f}% | {100 * g['pl_negativo'].mean():.0f}% | "
                 f"{s('cls_C0', 'O')}/{s('cls_C0', 'D')}% | {s('cls_fco', 'O')}/{s('cls_fco', 'D')}/{s('cls_fco', 'P')}% | {s('cls_S', 'D')}/{s('cls_S', 'P')}% | {s('cls_line_A', 'O')}/{s('cls_line_A', 'P')}% | {s('cls_PF0', 'O')}/{s('cls_PF0', 'P')}% |")
    return L


def figura(R, M):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    bt = Boot(R); bm = Boot(M)
    fig, axs = plt.subplots(1, 2, figsize=(8.2, 3.5))
    COR = {"BR": "#2a78d6", "US": "#eb6834"}; MAR = {"BR": "o", "US": "s"}
    ax = axs[0]
    for i, c in enumerate(("BR", "US")):
        x = np.arange(3) + (i - 0.5) * 0.22
        y, lo, hi = [], [], []
        for r in REG:
            g = R[(R["origem"] == c) & (R["regime"] == r) & (R["config"] == "no_dip")]
            y.append(g["ISC"].mean()); a, b = ic(bt.media(g, "ISC")); lo.append(y[-1] - a); hi.append(b - y[-1])
        ax.errorbar(x, y, yerr=[lo, hi], fmt=MAR[c], ms=6, lw=1.5, color=COR[c], mec="white", mew=0.8, label={"BR": "Firmas brasileiras", "US": "Firmas americanas"}[c])
    ax.set_title("ISC médio na própria amostra, sem DIP", fontsize=10, loc="left", color="#333333"); ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    ax = axs[1]
    COR2 = {"no_dip": "#1baf7a", "all_on": "#6250d6"}; MAR2 = {"no_dip": "D", "all_on": "^"}
    for i, cfg in enumerate(("no_dip", "all_on")):
        x = np.arange(3) + (i - 0.5) * 0.22
        y, lo, hi = [], [], []
        for r in REG:
            g = gap(M, bm, "gISC", r, cfg)["media"]
            y.append(g[0]); a, b = ic(g[1]); lo.append(y[-1] - a); hi.append(b - y[-1])
        ax.errorbar(x, y, yerr=[lo, hi], fmt=MAR2[cfg], ms=6, lw=1.5, color=COR2[cfg], mec="white", mew=0.8, label={"no_dip": "Sem DIP", "all_on": "Com DIP"}[cfg])
    ax.axhline(0, color="#52514e", lw=0.9)
    ax.set_title("Mesma firma: ISC com regras BR − regras EUA", fontsize=10, loc="left", color="#333333")
    ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    for ax in axs:
        ax.set_xticks(range(3)); ax.set_xticklabels(["Lucro", "Equilíbrio", "Prejuízo"])
        ax.grid(axis="y", color="#E5E5E5", lw=0.7); ax.set_axisbelow(True)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.tick_params(axis="y", length=0, colors="#52514e"); ax.tick_params(axis="x", colors="#333333")
    fig.tight_layout(); fig.savefig(f"{OUT}/figura.png", dpi=300); plt.close(fig)


def tabela_dip(R, TR) -> list:
    """Mesma firma, all_on: ISC com regras BR (acesso a) − ISC com regras EUA (acesso b). Confere os cantos com no_dip e all_on."""
    k = ["firm_id", "period_end"]
    def sob(regras, acesso):
        if acesso is None:
            d = pd.concat([R[(R["origem"] == regras) & (R["config"] == "all_on")], TR[(TR["origem"] != regras) & (TR["config"] == "all_on")]])
        else:
            d = ler(f"data/panel/sens_dip_{regras}_{str(acesso).replace('.', '_')}.csv")
        return d[k + ["origem", "regime", "ISC", "CLS"]].dropna(subset=["ISC"])
    # controles: acesso default reproduz all_on; acesso 0 reproduz no_dip
    conf = {}
    for regras, acesso, cfg in (("US", 1.0, "all_on"), ("US", 0.0, "no_dip"), ("BR", 0.0, "no_dip")):
        x = sob(regras, acesso)
        y = pd.concat([R[(R["origem"] == regras) & (R["config"] == cfg)], TR[(TR["origem"] != regras) & (TR["config"] == cfg)]])
        z = x.merge(y[k + ["ISC"]], on=k, suffixes=("", "_ref"), validate="one_to_one")
        conf[(regras, acesso, cfg)] = float((z["ISC"] - z["ISC_ref"]).abs().max())
    print("controles DIP (máx |dif|):", conf)
    L = ["| Acesso BR | Acesso EUA | Prejuízo: BR−EUA | IC 95% | Só firmas BR | Só firmas EUA | Equilíbrio | Lucro |", "|---|---|---|---|---|---|---|---|"]
    res = []
    LC = ["", "O mesmo no CLS, em prejuízo:", "", "| Acesso BR | Acesso EUA | CLS: BR−EUA | IC 95% |", "|---|---|---|---|"]
    for a_, b_ in ((0.0, 0.0), (0.0, 1.0), (None, 0.0), (None, 0.1), (None, 0.2), (None, 0.3), (None, 0.5), (None, 0.75), (None, 1.0), (1.0, 1.0)):
        M = sob("BR", a_).merge(sob("US", b_)[k + ["ISC", "CLS"]], on=k, suffixes=("_br", "_us"), validate="one_to_one")
        M["g"] = M["ISC_br"] - M["ISC_us"]
        M["gc"] = M["CLS_br"] - M["CLS_us"]
        bt = Boot(M)
        v = {}
        for r in REG:
            d = M[M["regime"] == r]
            mb, mu = d[d["origem"] == "BR"], d[d["origem"] == "US"]
            v[r] = (0.5 * (mb["g"].mean() + mu["g"].mean()), 0.5 * (bt.media(mb, "g") + bt.media(mu, "g")), mb["g"].mean(), mu["g"].mean())
        c = ic(v["prejuizo"][1])
        dp = M[M["regime"] == "prejuizo"]
        mb, mu = dp[dp["origem"] == "BR"], dp[dp["origem"] == "US"]
        vc = 0.5 * (bt.media(mb, "gc") + bt.media(mu, "gc")); cc = ic(vc)
        rot = lambda x, pad: f"{int(round(100 * (pad if x is None else x)))}%"
        L.append(f"| {rot(a_, 0.3)} | {rot(b_, 1.0)} | {f(v['prejuizo'][0], 4)} | [{f(c[0], 4)}; {f(c[1], 4)}] | {f(v['prejuizo'][2], 4)} | {f(v['prejuizo'][3], 4)} | {f(v['equilibrio'][0], 4)} | {f(v['lucro'][0], 4)} |")
        LC.append(f"| {rot(a_, 0.3)} | {rot(b_, 1.0)} | {f(0.5 * (mb['gc'].mean() + mu['gc'].mean()), 4)} | [{f(cc[0], 4)}; {f(cc[1], 4)}] |")
        res.append((a_, b_, v["prejuizo"][0], c))
    fixo = [x for x in res if x[0] is None]
    pos = [x[1] for x in fixo if x[3][0] > 0]; neg = [x[1] for x in fixo if x[3][1] < 0]
    igual = next(x for x in fixo if x[1] == 0.3); cem = res[-1]
    txt = (f"Com o Brasil fixo em 30%, a diferença em prejuízo é positiva com IC acima de zero a partir de {int(100 * min(pos))}% de acesso nos EUA" if pos else "Com o Brasil fixo em 30%, nenhum nível de acesso nos EUA leva o IC inteiro acima de zero")
    txt += (f" e negativa com IC abaixo de zero até {int(100 * max(neg))}%. " if neg else ". ")
    txt += f"Com acesso igual, a diferença é {f(igual[2], 4)} [{f(igual[3][0], 4)}; {f(igual[3][1], 4)}] a 30% e {f(cem[2], 4)} [{f(cem[3][0], 4)}; {f(cem[3][1], 4)}] a 100%."
    return L + ["", txt] + LC


def canais_sem_dip(M) -> list:
    """Mesma firma, DIP desligado, onde H2 situa os canais. Tributário = no_dip − all_off, pois sem DIP as demais regras só agem pelo tributo."""
    bm = Boot(M)
    L = ["| Regime | Métrica | Total BR−EUA | IC 95% | Tributário | IC 95% | Juros | IC 95% | Resíduo |", "|---|---|---|---|---|---|---|---|---|"]
    for r in REG:
        for m in ("ISC", "CLS"):
            tot, off, jur = gap(M, bm, "g" + m, r, "no_dip")["media"], gap(M, bm, "g" + m, r, "all_off")["media"], gap(M, bm, "r" + m, r, "no_dip")["media"]
            tr = (tot[0] - off[0], tot[1] - off[1])
            ct, ctr, cj = ic(tot[1]), ic(tr[1]), ic(jur[1])
            L.append(f"| {r} | {m} | {f(tot[0], 4)} | [{f(ct[0], 4)}; {f(ct[1], 4)}] | {f(tr[0], 4)} | [{f(ctr[0], 4)}; {f(ctr[1], 4)}] | {f(jur[0], 4)} | [{f(cj[0], 4)}; {f(cj[1], 4)}] | {f(tot[0] - tr[0] - jur[0], 4)} |")
    return L


def escudo_h1(R, E) -> list:
    """Amostra própria: efeito do escudo dos juros da linha (κ_I = 0 como contrafactual) e de toda a camada tributária, por regime, sem DIP."""
    k = ["firm_id", "period_end"]
    B_ = R[R["config"] == "no_dip"][k + ["origem", "regime", "ISC"]]
    d = B_.merge(E[k + ["ISC"]].rename(columns={"ISC": "ISC_sem"}), on=k, validate="one_to_one").merge(
        R[R["config"] == "all_off"][k + ["ISC"]].rename(columns={"ISC": "ISC_off"}), on=k, validate="one_to_one")
    d["escudo"] = d["ISC"] - d["ISC_sem"]; d["camada"] = d["ISC"] - d["ISC_off"]
    bt = Boot(d)
    L = ["| País | Regime | Escudo dos juros da linha | IC 95% | Camada tributária inteira | IC 95% |", "|---|---|---|---|---|---|"]
    for c in ("BR", "US"):
        est = {}
        for r in ("lucro", "equilibrio", "prejuizo"):
            g = d[(d["origem"] == c) & (d["regime"] == r)]
            est[r] = {x: (g[x].mean(), bt.media(g, x)) for x in ("escudo", "camada")}
            a, b = ic(est[r]["escudo"][1]), ic(est[r]["camada"][1])
            L.append(f"| {c} | {r} | {f(est[r]['escudo'][0], 4)} | [{f(a[0], 4)}; {f(a[1], 4)}] | {f(est[r]['camada'][0], 4)} | [{f(b[0], 4)}; {f(b[1], 4)}] |")
        de, dc = [(est["prejuizo"][x][0] - est["lucro"][x][0], est["prejuizo"][x][1] - est["lucro"][x][1]) for x in ("escudo", "camada")]
        a, b = ic(de[1]), ic(dc[1])
        L.append(f"| {c} | prejuízo − lucro | {f(de[0], 4)} | [{f(a[0], 4)}; {f(a[1], 4)}] | {f(dc[0], 4)} | [{f(b[0], 4)}; {f(b[1], 4)}] |")
    return L


def jcp_por_estado(R, P) -> list:
    """Firmas brasileiras sob regras BR: efeito do JCP no CLS por tercil e, no de prejuízo, pelo sinal da soma do EBIT futuro."""
    k = ["firm_id", "period_end"]
    A = R[(R["origem"] == "BR") & (R["config"] == "all_on")][k + ["origem", "regime", "CLS"]]
    d = A.merge(R[R["config"] == "no_jcp"][k + ["CLS"]].rename(columns={"CLS": "CLS_sem"}), on=k, validate="one_to_one")
    pf = P.assign(soma=P[["pi_1", "pi_2", "pi_3", "pi_4"]].sum(axis=1))[k + ["soma"]]
    d = d.merge(pf, on=k, validate="one_to_one")
    d["ef"] = d["CLS"] - d["CLS_sem"]
    bt = Boot(d)
    grupos = [("lucro", d["regime"] == "lucro"), ("equilibrio", d["regime"] == "equilibrio"), ("prejuizo", d["regime"] == "prejuizo"),
              ("prejuizo, Σ EBIT futuro < 0", (d["regime"] == "prejuizo") & (d["soma"] < 0)), ("prejuizo, Σ EBIT futuro ≥ 0", (d["regime"] == "prejuizo") & (d["soma"] >= 0))]
    base = bt.media(d[grupos[0][1]], "ef"); m0 = d.loc[grupos[0][1], "ef"].mean()
    L = ["| Grupo | Pontos | Efeito do JCP no CLS | IC 95% | Razão ao efeito em lucro | IC 95% |", "|---|---|---|---|---|---|"]
    for nome, mask in grupos:
        g = d[mask & d["ef"].notna()]
        v = bt.media(g, "ef"); a = ic(v); r_ = ic(v / base)
        L.append(f"| {nome} | {len(g)} | {f(g['ef'].mean(), 5)} | [{f(a[0], 5)}; {f(a[1], 5)}] | {f(g['ef'].mean() / m0, 3)} | [{f(r_[0], 3)}; {f(r_[1], 3)}] |")
    return L


def mesma_firma_sens(Z, Zt):
    """Mesma firma numa sensibilidade rodada sob as regras próprias (Z) e as da outra jurisdição (Zt)."""
    k = ["firm_id", "period_end", "config"]
    Mz = Z[k + ["origem", "regime", "ISC", "CLS"]].merge(Zt[k + ["ISC", "CLS"]].rename(columns={"ISC": "ISC_tr", "CLS": "CLS_tr"}), on=k, validate="one_to_one")
    br = Mz["origem"] == "BR"
    for m_ in ("ISC", "CLS"):
        Mz["g" + m_] = np.where(br, Mz[m_] - Mz[m_ + "_tr"], Mz[m_ + "_tr"] - Mz[m_])
    return Mz


def janela(d, ini=None, fim=None):
    if ini:
        d = d[d["period_end"] >= ini]
    if fim:
        d = d[d["period_end"] <= fim]
    return d


def main():
    os.makedirs(OUT, exist_ok=True)
    P = pd.read_csv("data/panel/painel_BR_US.csv")
    R = ler(f"{OUT}/experimento_I_painel.csv")
    CF, TR, TX = ler("data/panel/experimento_I_cf_taxa.csv"), ler("data/panel/experimento_I_troca.csv"), ler("data/panel/experimento_I_troca_taxa.csv")
    M = mesma_firma(R, CF, TR, TX)
    atr = json.load(open("data/panel/atrito.json", encoding="utf-8"))

    # ---------------------------------------------------------------- Tabela 5
    F = R.assign(pos=(R["ISC"] > 1e-6).where(R["ISC"].notna()), indef=R["status"].ne("ok") | R["ISC"].isna() | R["CLS"].isna())
    t5 = F.groupby(["country", "regime", "config"]).agg(n=("ISC", "size"), firmas=("firm_id", "nunique"), ISC_mediana=("ISC", "median"), ISC_media=("ISC", "mean"), ISC_pos=("pos", "mean"),
                                                        CLS_mediana=("CLS", "median"), CLS_media=("CLS", "mean"), E0_mediana=("E_base", "median"), Eq_mediana=("E_shock", "median"),
                                                        E0_media=("E_base", "mean"), Eq_media=("E_shock", "mean"), indefinido=("indef", "mean")).reset_index()
    t5.to_csv(f"{OUT}/agregados_tabela5.csv", index=False)

    # ---------------------------------------------------------------- Tabela 6A: mesma firma
    regras = ["no_tax", "no_jcp", "no_loss_cap", "no_interest_cap", "no_dip"]
    me = M.groupby(["origem", "regime", "config"])[["gISC", "gCLS", "rISC", "rCLS"]].mean()

    def v(am, r, cfg, col):
        return 0.5 * (me.loc[("BR", r, cfg), col] + me.loc[("US", r, cfg), col]) if am == "media" else me.loc[(am, r, cfg), col]
    linhas6 = []
    for am in ("media", "BR", "US"):
        for r in REG:
            for m in ("ISC", "CLS"):
                tot = v(am, r, "all_on", "g" + m)
                ef = {c: tot - v(am, r, c, "g" + m) for c in regras}
                jur = v(am, r, "all_on", "r" + m)
                trib = ef["no_tax"]              # no_tax também zera JCP e torna κ_P e κ_I inócuos: estes são componentes, não parcelas somadas
                linhas6.append(dict(amostra=am, regime=r, metrica=m, total=tot, tributario=trib, JCP=ef["no_jcp"], kappa_P=ef["no_loss_cap"], kappa_I=ef["no_interest_cap"],
                                    juros=jur, instrumento=ef["no_dip"], residuo=tot - trib - jur - ef["no_dip"]))
    t6 = pd.DataFrame(linhas6); t6.to_csv(f"{OUT}/agregados_tabela6.csv", index=False)

    # ---------------------------------------------------------------- Tabela 6B: entre amostras
    pm = R.groupby(["country", "regime", "config"])[["ISC", "CLS"]].mean()
    t6b = []
    for r in REG:
        for m in ("ISC", "CLS"):
            tot = pm.loc[("BR", r, "all_on"), m] - pm.loc[("US", r, "all_on"), m]
            off = pm.loc[("BR", r, "all_off"), m] - pm.loc[("US", r, "all_off"), m]
            t6b.append((r, m, tot, off, tot - off))

    # ---------------------------------------------------------------- H1: margens
    h1 = []
    for c in ("BR", "US"):
        d = R[(R["origem"] == c) & (R["config"] == "no_dip")]
        a, b = d[d["regime"] == "prejuizo"], d[d["regime"] == "lucro"]
        pa, pb = (a["ISC"] > 1e-6).mean(), (b["ISC"] > 1e-6).mean()
        ia, ib = a[a["ISC"] > 1e-6]["ISC"].mean(), b[b["ISC"] > 1e-6]["ISC"].mean()
        ext, inte = (pa - pb) * (ia + ib) / 2, (ia - ib) * (pa + pb) / 2
        pf = d[d["regime"].isin(["prejuizo", "lucro"])].pivot_table(index="firm_id", columns="regime", values="ISC", aggfunc="mean").dropna()
        dif = (pf["prejuizo"] - pf["lucro"]).values
        rng = np.random.default_rng(SEMENTE)
        bv = np.array([dif[rng.integers(0, len(dif), len(dif))].mean() for _ in range(B)])
        cc = ic(bv)
        h1.append((c, pa, pb, ia, ib, a["ISC"].mean() - b["ISC"].mean(), ext, inte, len(dif), dif.mean(), cc))

    # ---------------------------------------------------------------- relatório
    b_, u_ = P[P.country == "BR"], P[P.country == "US"]
    n_ok = int((R["status"] == "ok").sum()); n_sem_cls = int(((R["status"] == "ok") & R["CLS"].isna() & (R["q"] > 1e-7)).sum()); n_q0 = int((R["q"] <= 1e-7).sum())
    n_folga = int((R["folga_custo"] > 1e-9).sum()) if "folga_custo" in R else 0
    L = ["# Experimento I em dados reais — painel CVM/SEC (Etapa 2)", ""]
    L += [f"Gerado por `scripts/etapa2/agrega.py`. T = 4 trimestres; q_frac = 1; c_E = 0,10. E* em proporção do ativo de t; ISC e CLS por unidade de q. "
          f"IC de 95% por bootstrap em blocos de firma, estratificado pela amostra de origem, {B} reamostragens, semente {SEMENTE}.", ""]
    L += ["## Como ler estes números", "",
          "- **Trilha A (pública).** Linhas, covenants e renovações não são observados, e `line_A` é parâmetro na maioria das linhas. Os números medem a sensibilidade do solver a cenários parametrizados e **não** validam a retirada real de crédito (Artigo 2, seção 6.4).",
          "- **Regras.** As de 2026 (Tabela 4 do Artigo 2) valem para toda a janela, inclusive θ = 17,5%, como estática comparativa. FCO e EBIT futuros são os realizados; não há previsão.",
          "- **DIP é cenário parametrizado (classe P).** BR 30% e EUA 100% da capacidade retirada, a 1,5 vez a taxa da linha, oferecido a toda firma no choque. O Apêndice A pede A > 0 só em recuperação, mas o painel não tem `recovery_status`. Por isso, `all_on` é um limite superior do papel do DIP; a sensibilidade ao acesso está na seção de hipóteses.",
          "- **BR e EUA têm firmas diferentes.** Comparar as duas amostras mistura regras com perfil das firmas. H2, H3 e a Tabela 6A usam a mesma firma sob as duas jurisdições, como `experiment_I.py`. A Tabela 6B mostra a diferença entre as amostras apenas como dado descritivo.",
          "- **Prejuízo é tercil de EBIT/ativo no país e no trimestre, não estado de perda.** A tabela de composição mostra a proporção de perdas efetivas.",
          "- **As médias de E* são puxadas por poucas firmas muito pequenas.** Prefira as medianas.", ""]
    L += ["## Amostra", "", "| País | Firmas | Pontos de decisão | Primeiro t | Último t |", "|---|---|---|---|---|",
          f"| BR | {b_.firm_id.nunique()} | {len(b_)} | {b_.period_end.min()} | {b_.period_end.max()} |", f"| US | {u_.firm_id.nunique()} | {len(u_)} | {u_.period_end.min()} | {u_.period_end.max()} |", ""]
    L += [f"Na comparação da mesma firma entram {M[M.config == 'all_on'].shape[0]} pontos: os demais são brasileiros de trimestres sem SOFR. Solver: {n_ok} de {len(R)} linhas com status ok, {n_folga} delas com etapa 2 fechada só com E0 até 1e-5 acima de E*; {n_sem_cls} com etapa 2 sem solução e {n_q0} com q = 0 (linha remanescente observada igual a zero) entram como indefinidas.", ""]
    L += ["Atrito (pontos brutos → painel):", ""]
    for c in ("BR", "US"):
        it = {k[3:]: v_ for k, v_ in atr.items() if k.startswith(c + "_") and isinstance(v_, int)}
        L.append(f"- **{c}:** " + "; ".join(f"{k} = {x}" for k, x in sorted(it.items())))
    L += ["", "## Composição por classe de dados (Apêndice A do Artigo 2)", "",
          "`data_class` é P em 100% das linhas, porque L e q_frac são parâmetros e a pior classe domina. A composição coluna a coluna, abaixo, descreve a amostra de todas as tabelas; os subconjuntos das hipóteses e a comparação da mesma firma usam parte destes pontos. DIP é P em toda linha com DIP ligado.", ""]
    L += composicao(P)
    L += ["", "## Tabela 5 — ISC e CLS por país, regime e configuração (amostra própria)", "", "`ISC>0` = proporção de pontos em que a retirada exige aporte adicional. `Indefinido` inclui q = 0 e etapa 2 sem solução. " + RODAPE_CLASSE, "",
          "| País | Regime | Config. | N | Firmas | ISC mediana | ISC média | ISC>0 | CLS mediana | CLS média | E*(0) mediana | E*(q) mediana | E*(0) média | E*(q) média | Indefinido |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in t5.itertuples():
        L.append(f"| {r.country} | {r.regime} | {r.config} | {r.n} | {r.firmas} | {f(r.ISC_mediana)} | {f(r.ISC_media)} | {100 * r.ISC_pos:.1f}% | {f(r.CLS_mediana, 4)} | {f(r.CLS_media, 4)} | {f(r.E0_mediana)} | {f(r.Eq_mediana)} | {f(r.E0_media)} | {f(r.Eq_media)} | {100 * r.indefinido:.1f}% |")
    L += ["", "## Tabela 6A — decomposição de BR − EUA na mesma firma (médias; regras uma de cada vez)", "",
          "`Média` é a média simples das amostras de firmas brasileiras e americanas. `tributário` é o efeito de desligar o tributo (τ, θ), o que também zera o JCP e torna κ_P e κ_I inócuos; por isso JCP, κ_P e κ_I são componentes informativos e **não** entram na soma. `juros` compara as taxas das duas jurisdições sob cada conjunto de regras. `resíduo` = total − tributário − juros − instrumento. " + RODAPE_CLASSE, "",
          "| Amostra | Regime | Métrica | Total BR−EUA | tributário | do qual JCP | do qual κ_P | do qual κ_I | juros | instrumento (DIP) | resíduo |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    nome = {"media": "Média", "BR": "Firmas BR", "US": "Firmas EUA"}
    for r in t6.itertuples():
        L.append(f"| {nome[r.amostra]} | {r.regime} | {r.metrica} | {f(r.total, 4)} | {f(r.tributario, 4)} | {f(r.JCP, 4)} | {f(r.kappa_P, 4)} | {f(r.kappa_I, 4)} | {f(r.juros, 4)} | {f(r.instrumento, 4)} | {f(r.residuo, 4)} |")
    L += ["", "## Tabela 6B — diferença entre as amostras (descritiva, não institucional)", "",
          "`Sem regras` é a diferença BR − EUA com todas as regras desligadas: reflete o perfil das firmas e a taxa de cada país. " + RODAPE_CLASSE, "",
          "| Regime | Métrica | BR−EUA, all_on | BR−EUA, sem regras (all_off) | Diferença |", "|---|---|---|---|---|"]
    for r, m, tot, off, d in t6b:
        L.append(f"| {r} | {m} | {f(tot, 4)} | {f(off, 4)} | {f(d, 4)} |")
    L += ["", "## Hipóteses H1–H3", "", "H1 usa a amostra própria. H2 e H3 usam a mesma firma sob as duas jurisdições. " + RODAPE_CLASSE, "", "| Amostra | Teste | Estimativa | IC 95% | Esperado | Resultado |", "|---|---|---|---|---|---|"]
    L += testes(R, M, "Completa", completo=True)
    L += testes(janela(R, "2018-06-30"), janela(M, "2018-06-30"), "Janela comum (t ≥ 2018-06)")
    L += testes(janela(R, "2019-03-31", "2020-09-30"), janela(M, "2019-03-31", "2020-09-30"), "Horizonte cruza 2020 (estresse)")
    fora = lambda d: d[(d["period_end"] < "2019-03-31") | (d["period_end"] > "2020-09-30")]
    L += testes(fora(R), fora(M), "Horizonte fora de 2020")
    # H2 conjunta
    bm = Boot(M)
    a, b = gap(M, bm, "gISC", "prejuizo", "no_dip"), gap(M, bm, "gISC", "prejuizo", "all_on")
    ca, cb = ic(a["media"][1]), ic(b["media"][1])
    inverte = ca[1] <= 0 and cb[0] > 0
    L += ["", f"**H2, leitura conjunta (mesma firma, prejuízo):** sem DIP, {f(a['media'][0], 4)} [{f(ca[0], 4)}; {f(ca[1], 4)}]; com DIP, {f(b['media'][0], 4)} [{f(cb[0], 4)}; {f(cb[1], 4)}]. "
          + ("O sinal se inverte com o DIP, como a H2 prevê, e os dois IC sustentam a inversão." if inverte else "Os dois IC, juntos, não sustentam a inversão de sinal prevista pela H2."), ""]
    L += ["### H2 — sensibilidade ao acesso a DIP (mesma firma, all_on)", "",
          "A inversão de sinal depende de uma suposição, não de um dado observado. A tabela varia só o acesso, como o `dip_sweep` de `experiment_I.py`: Brasil fixo em 30% e EUA de 0% a 100%, mais o caso de acesso igual a 100% (Artigo 2, seção 7.3, cenário d), o caso sem DIP e o caso de DIP só nos EUA, como H2 foi enunciada. As colunas de `Prejuízo` até `Só firmas EUA` são desse regime; `Prejuízo`, `Equilíbrio` e `Lucro` são médias simples das duas amostras. " + RODAPE_CLASSE, ""]
    L += tabela_dip(R, TR)
    L += [""]
    L += ["### H1 — margem extensiva e margem intensiva (no_dip)", "",
          "Comparar regimes muda também FCO, caixa e S, não só o tratamento tributário: o teste não é *ceteris paribus*. A decomposição separa a proporção de pontos em que a retirada exige aporte (extensiva) do tamanho do índice quando ela exige (intensiva). A estimativa dentro da firma usa firmas vistas nos dois regimes. Análise complementar, não pré-especificada.", "",
          "| País | ISC>0 prejuízo | ISC>0 lucro | ISC dado ISC>0, prejuízo | ISC dado ISC>0, lucro | Diferença | Extensiva | Intensiva | Firmas nos dois regimes | Dentro da firma | IC 95% |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for c, pa, pb, ia, ib, dif, ext, inte, nf, df, cc in h1:
        L.append(f"| {c} | {100 * pa:.1f}% | {100 * pb:.1f}% | {f(ia)} | {f(ib)} | {f(dif, 4)} | {f(ext, 4)} | {f(inte, 4)} | {nf} | {f(df, 4)} | [{f(cc[0], 4)}; {f(cc[1], 4)}] |")
    jc = R[R["origem"] == "BR"].groupby(["regime", "config"])["CLS"].mean()
    L += ["", "### H3 — efeito do JCP no CLS por regime (firmas brasileiras, regras BR)", "", "| Regime | CLS, all_on | CLS, no_jcp | Efeito do JCP |", "|---|---|---|---|"]
    for r in REG:
        L.append(f"| {r} | {f(jc[(r, 'all_on')], 4)} | {f(jc[(r, 'no_jcp')], 4)} | {f(jc[(r, 'all_on')] - jc[(r, 'no_jcp')], 4)} |")
    L += ["", "Na tabela seguinte, o tercil de prejuízo é separado pelo sinal da soma do EBIT dos quatro trimestres seguintes. Análise complementar, não pré-especificada.", ""] + jcp_por_estado(R, P)
    L += ["", "### H2 — canais sem DIP (mesma firma)", "", "Tributário é a diferença entre `no_dip` e `all_off`; juros usa a taxa mediana da outra jurisdição no trimestre, como na Tabela 6A. Análise complementar, não pré-especificada.", ""] + canais_sem_dip(M)
    if os.path.exists("data/panel/sens_escudo.csv"):
        L += ["", "### H1 — escudo dos juros da linha e camada tributária (sem DIP)", "",
              "O escudo é a diferença de ISC entre a configuração sem DIP e a mesma configuração sem dedução dos juros da linha (κ_I = 0), com o teto do JCP ainda sobre o lucro líquido desses juros. A camada inteira é `no_dip` − `all_off` e inclui o tributo pago, que consome caixa. Análise complementar, não pré-especificada.", ""] + escudo_h1(R, ler("data/panel/sens_escudo.csv"))
    # sensibilidades
    L += ["", "## Sensibilidades", ""]
    if os.path.exists("data/panel/sens_juros_ded.csv"):
        Z, Zt = ler("data/panel/sens_juros_ded.csv"), ler("data/panel/sens_juros_ded_troca.csv")
        Mz = mesma_firma_sens(Z, Zt)
        ip = (P["S"] - P["S_sem_juros"] > 1e-12).groupby(P["country"]).mean()
        L += ["### Com os juros da dívida pré-existente dedutíveis", "", f"No caso-base, esses juros saem do caixa em S, mas não são deduzidos. Aqui entram na dedução, sujeitos a κ_I, pelo valor localizado (BR {100 * ip['BR']:.0f}% e EUA {100 * ip['US']:.0f}% dos pontos; nos demais, zero).", "",
              "| Amostra | Teste | Estimativa | IC 95% | Esperado | Resultado |", "|---|---|---|---|---|---|"] + testes(Z, Mz, "Juros pré-existentes dedutíveis") + [""]
        a_ = R[R["config"].isin(["all_on", "no_dip"])].groupby(["country", "regime", "config"])["ISC"].mean(); z = Z.groupby(["country", "regime", "config"])["ISC"].mean()
        L += ["| País | Regime | Config. | ISC, base → sensibilidade |", "|---|---|---|---|"]
        for k_ in a_.index:
            L.append(f"| {k_[0]} | {k_[1]} | {k_[2]} | {f(a_[k_])} → {f(z[k_])} |")
        L.append("")
    if os.path.exists("data/panel/sens_sem_dupla_contagem.csv"):
        Z, Zt = ler("data/panel/sens_sem_dupla_contagem.csv"), ler("data/panel/sens_sem_dupla_troca.csv")
        Mz = mesma_firma_sens(Z, Zt)
        L += ["### Sem dupla contagem de juros (S sem juros pagos)", "", "O FCO do roteiro já vem líquido de juros em muitas firmas, e S os soma de novo. O Artigo 1 pede para evitar essa dupla contagem; aqui ela é retirada.", "",
              "| Amostra | Teste | Estimativa | IC 95% | Esperado | Resultado |", "|---|---|---|---|---|---|"] + testes(Z, Mz, "Sem dupla contagem") + [""]
    for x in sorted(glob.glob("data/panel/sens_PF0_*.csv")):
        Z = ler(x); val = os.path.basename(x)[9:-4].replace("_", ",")
        base = R[R["origem"] == "BR"]
        a_ = base.groupby(["regime", "config"])[["ISC", "CLS"]].mean(); z = Z.groupby(["regime", "config"])[["ISC", "CLS"]].mean()
        L += [f"### Firmas brasileiras com PF0 = {val} do ativo (Apêndice A.2)", "", "| Regime | Config. | ISC, base → sensibilidade | CLS, base → sensibilidade |", "|---|---|---|---|"]
        for k_ in z.index:
            if k_[1] in ("all_on", "no_dip"):
                L.append(f"| {k_[0]} | {k_[1]} | {f(a_.loc[k_, 'ISC'])} → {f(z.loc[k_, 'ISC'])} | {f(a_.loc[k_, 'CLS'], 4)} → {f(z.loc[k_, 'CLS'], 4)} |")
        L.append("")
    for x in sorted(glob.glob("data/panel/sens_PFUS_*.csv")):
        Z = ler(x); val = os.path.basename(x)[10:-4].replace("_", ",")
        k = ["firm_id", "period_end", "config"]
        J = Z.merge(R[k + ["ISC", "CLS"]], on=k, suffixes=("", "_base"), validate="one_to_one")
        t = J.groupby(["regime", "config"])[["ISC_base", "ISC", "CLS_base", "CLS"]].mean()
        L += [f"### Pontos americanos sem saldo observado, com PF0 = {val} do ativo (Apêndice A.2)", "", f"{len(J[J.config == 'all_on'])} pontos; médias só sobre eles.", "", "| Regime | Config. | ISC, base → sensibilidade | CLS, base → sensibilidade |", "|---|---|---|---|"]
        for k_ in t.index:
            if k_[1] in ("all_on", "no_dip"):
                L.append(f"| {k_[0]} | {k_[1]} | {f(t.loc[k_, 'ISC_base'])} → {f(t.loc[k_, 'ISC'])} | {f(t.loc[k_, 'CLS_base'], 4)} → {f(t.loc[k_, 'CLS'], 4)} |")
        L.append("")
    L += ["## Escolhas onde o roteiro não decide", "", "```", atr.get("escolhas", "").strip(), "```", ""]
    open(f"{OUT}/tabelas.md", "w", encoding="utf-8").write("\n".join(L))
    figura(R, M)
    print("ok", len(R), "mesma firma", len(M))


if __name__ == "__main__":
    main()
