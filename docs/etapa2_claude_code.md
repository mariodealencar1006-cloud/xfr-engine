# Etapa 2 — Experimento I em dados reais (roteiro para o Claude Code)

Objetivo: construir o painel firma–trimestre de companhias abertas não financeiras do Brasil (CVM) e dos
Estados Unidos (SEC), no formato de `docs/painel_exemplo.csv`, e rodar `python -m xfr_engine.panel` sobre ele.
Tudo o que está abaixo foi definido no Artigo 2 (seções 6 e 7); não inventar regras novas.

## 0. Preparação
- `git pull`; `pip install -e .`; `pytest -q` (36 testes devem passar).
- Criar `data/raw/`, `data/panel/` e `results/panel/` (ignorados pelo git, exceto `results/panel/*.csv` agregados).

## 1. Coleta — Brasil (CVM, dados abertos)
- DFP e ITR: https://dados.cvm.gov.br/dataset/cia_aberta-doc-dfp e https://dados.cvm.gov.br/dataset/cia_aberta-doc-itr
  (zips anuais `dfp_cia_aberta_AAAA.zip` / `itr_cia_aberta_AAAA.zip`, 2016–2025). Usar os arquivos `..._BPA_con`,
  `..._BPP_con`, `..._DRE_con`, `..._DFC_MI_con` (consolidado; se ausente, individual) e `..._DMPL_con`.
- Cadastro: https://dados.cvm.gov.br/dataset/cia_aberta-cad (setor, situação; excluir bancos, seguradoras,
  holdings financeiras). Manter companhias com registro ativo em qualquer trimestre da janela (sem viés de
  sobrevivência: deslistadas ficam, com `data_class` marcando lacunas).
- Registrar URL, data/hora da extração e md5 de cada zip em `data/raw/manifest.csv`.

## 2. Coleta — Estados Unidos (SEC)
- `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` por companhia (User-Agent com nome e e-mail;
  ≤10 req/s). Lista inicial: componentes do S&P 1500 não financeiros (SIC fora de 6000–6799) com `dei:EntityCommonStockSharesOutstanding`.
- Tags: `CashAndCashEquivalentsAtCarryingValue`, `NetCashProvidedByUsedInOperatingActivities`,
  `IncomeTaxesPaidNet`, `InterestPaidNet`, `LongTermDebtCurrent`, `DebtCurrent`, `LongTermDebtNoncurrent`,
  `OperatingIncomeLoss`, `RetainedEarningsAccumulatedDeficit`, `StockholdersEquity`,
  `DeferredTaxAssetsOperatingLossCarryforwards` (proxy de NOL), `LineOfCreditFacilityMaximumBorrowingCapacity`
  e `LineOfCreditFacilityRemainingBorrowingCapacity` quando existirem (classe O); do contrário, parametrizar (P).

## 3. Mapeamento para o painel (uma linha por firma–trimestre, horizonte T = 4 trimestres à frente)
| coluna | definição | fonte | classe |
|---|---|---|---|
| C0 | caixa e equivalentes no fim do trimestre t | BPA / CashAndCashEquivalents | O |
| fco_1..fco_4 | FCO antes de tributos sobre o lucro dos 4 trimestres seguintes (DFC: caixa operacional + tributos pagos) | DFC / NetCashOperating + IncomeTaxesPaid | O (histórico) — ou E se previsto |
| pi_1..pi_4 | lucro tributável antes de juros e JCP ≈ EBIT trimestral | DRE / OperatingIncomeLoss | D |
| S | serviço trimestral da dívida pré-existente = (dívida de curto prazo)/4 + juros pagos/4 | BPP, DFC | D |
| L | reserva mínima = 5% da receita trimestral (regra gerencial fixada ex ante) | DRE | P |
| line_A | capacidade de linha: LineOfCreditRemainingCapacity (O) ou 10% do ativo (P) | notas / parâmetro | O ou P |
| line_rate | taxa trimestral: BR = (CDI + 4 p.p.)/4; US = (SOFR + 3 p.p.)/4, séries BCB/FRED na data | BCB SGS / FRED | D |
| q_frac | 1,0 (retirada total) | — | P |
| LA0 | lucros acumulados + reservas de lucros do exercício anterior encerrado (BR); RetainedEarnings (US), ≥ 0 | BPP / RetainedEarnings | O |
| PF0 | prejuízo fiscal acumulado: nota de tributos (BR) ou DeferredTaxAssetsOperatingLossCarryforwards/τ (US) | notas | O ou P |
| PL0 | patrimônio líquido ajustado (BR: capital social + reservas de capital elegíveis + reservas de lucros − ações em tesouraria − prejuízos acumulados; US: StockholdersEquity, só informativo) | BPP | D |
| regime | lucro / equilíbrio / prejuízo por tercil de EBIT/ativo no trimestre t (definido antes de rodar) | DRE, BPA | D |
| data_class | pior classe entre as colunas usadas (O < D < P < E) | — | — |

Escalas: dividir todos os valores monetários pelo ativo total do trimestre t (razões adimensionais), como
na seção 6.2 do Artigo 2. Datas "as-of": usar a data de publicação (DFP/ITR `DT_RECEB`; SEC `filed`), não a
de competência.

## 4. Execução
```bash
python -m xfr_engine.panel data/panel/painel_BR_US.csv --out results/panel/experimento_I_painel.csv --c_E 0.10
```
(c_E = custo de oportunidade do capital próprio no horizonte de 4 trimestres; 0,10 ≈ 2,5% ao trimestre.)

## 5. Agregação (Tabelas 5–6 em dados reais)
- Por `country × regime × config`: mediana e média de ISC e CLS; proporção de `status == undefined/infeasible`.
- Decomposição por canal como em `xfr_engine/experiment_I.py` (uma regra de cada vez), por regime. No painel a
  taxa da linha é a observada da firma, então o canal de juros é medido por contrafactual: rodar cada firma
  também com a taxa mediana da outra jurisdição na mesma data (`line_rate` trocado) e tomar a diferença.
- Intervalos: bootstrap em blocos por firma (1.000 reamostragens), com semente fixa registrada.
- H1: ISC(prejuízo) − ISC(lucro) por país, `config = no_dip`.  H2: ISC_BR − ISC_US em prejuízo, `no_dip` e `all_on`.
  H3: DiD do CLS entre prejuízo e lucro, `all_on` menos `no_jcp`.
- Relatar a composição por classe de dados (O/D/P/E) em cada tabela, como exige o Apêndice A do Artigo 2.

## 6. Entrega
- `results/panel/experimento_I_painel.csv`, `results/panel/tabelas.md`, `results/panel/figura.png`,
  `data/panel/dicionario.md` (origem, regra de cálculo, classe de cada coluna) e `data/raw/manifest.csv`.
- Commit "Etapa 2 — painel CVM/SEC e Experimento I em dados reais" e tag `v0.4.0` (release no GitHub → DOI no Zenodo).
