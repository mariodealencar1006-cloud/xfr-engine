# Dicionário do painel `painel_BR_US.csv` (Etapa 2)

Uma linha por firma–trimestre t, com horizonte T = 4 trimestres à frente. Valores monetários divididos pelo ativo total de t.
Classes do Apêndice A do Artigo 2: O observado, D derivado, P parametrizado, E estimado. Código: `scripts/etapa2/painel.py`.

| Coluna | Regra de cálculo | Origem BR (CVM) | Origem US (SEC, us-gaap) | Classe |
|---|---|---|---|---|
| firm_id | `BR-<CD_CVM>` ou `US-<CIK>` | cadastro | companyfacts | — |
| country | BR ou US | — | — | — |
| period_end | fim do trimestre t | DT_REFER | `end` do balanço | O |
| filing_date | primeira publicação do trimestre t; data "as-of" da decisão | menor DT_RECEB | menor `filed` | O |
| T | 4 | — | — | P |
| C0 | caixa e equivalentes em t | BPA 1.01.01 | CashAndCashEquivalentsAtCarryingValue (se ausente, CashCashEquivalentsRestrictedCash…, D) | O (D) |
| fco_1..fco_4 | caixa operacional + tributos pagos dos 4 trimestres seguintes, realizados, com sinal (restituição reduz) | DFC 6.01 + contas de tributo pago em 6.01 (texto) | NetCashProvidedByUsedInOperatingActivities + IncomeTaxesPaidNet ou IncomeTaxesPaid | O; D se tributo = anual/4; P se tributo não localizado (somou-se 0). Coluna `cls_fco` |
| pi_1..pi_4 | EBIT dos 4 trimestres seguintes, realizado | DRE 3.05 | OperatingIncomeLoss | D |
| S | dívida de curto prazo em t / 4 + juros pagos do último exercício publicado / 4 | BPP 2.01.04; DFC fora de 6.01.01, contas de juros e encargos pagos (texto; exclui JCP e linhas que somam principal) | DebtCurrent ou LongTermDebtCurrent; InterestPaidNet ou InterestPaid, em até 400 dias | D; P se um componente não foi localizado (usou-se 0). Coluna `cls_S` |
| S_sem_juros | só a parcela da dívida de curto prazo; usada na sensibilidade de dupla contagem | idem | idem | D ou P |
| L | 5% da receita do trimestre t | DRE 3.01 | Revenues e variantes | P |
| line_A | capacidade disponível em t: reportada ou 10% do ativo | não estruturada: 10% do ativo | LineOfCreditFacilityRemainingBorrowingCapacity, em até 400 dias; senão 10%. Zero reportado é observado (q = 0, ISC indefinido); abaixo de 0,001% do ativo é erro de escala e vira 10% | O ou P. Coluna `cls_line_A` |
| line_rate | taxa trimestral na data de decisão | (CDI, SGS 4389, + 4 p.p.)/4 | (SOFR, FRED, + 3 p.p.)/4 | D |
| r_tjlp | TJLP trimestral na data de decisão | SGS 256 / 4 | 0 (sem JCP) | D |
| q_frac | 1,0: retirada total | — | — | P |
| LA0 | lucros acumulados e reservas de lucros do último exercício publicado, ≥ 0 | BPP 2.03.04 + máx(2.03.05, 0) | RetainedEarningsAccumulatedDeficit | O |
| PF0 | saldo de prejuízos fiscais | não estruturado: 0 | DeferredTaxAssetsOperatingLossCarryforwards / 0,25 | O ou P. Coluna `cls_PF0` |
| PL0 | PL ajustado, limitado a ≥ 0 | BPP 2.03.01 + 2.03.02 + 2.03.04 + mín(2.03.05, 0); ações em tesouraria já estão com sinal negativo nas reservas | StockholdersEquity; informativo, sem JCP | D |
| pl_negativo | 1 se o PL antes do limite era negativo | — | — | D |
| ebit_ativo | EBIT do trimestre t / ativo | DRE 3.05 | OperatingIncomeLoss | D |
| tri | trimestre-calendário de (period_end − 16 dias), para calendários de 52–53 semanas | — | — | D |
| regime | tercil de `ebit_ativo` dentro de país × `tri`: lucro, equilibrio, prejuizo | — | — | D |
| data_class | pior classe entre as colunas usadas; P em todas as linhas, porque L e q_frac são P | — | — | — |

## Universo

- **BR:** companhias do cadastro com DFP/ITR 2016–2025, fora dos setores financeiros e de plano de contas financeiro. Emissores estrangeiros fora do cadastro saem. Deslistadas permanecem. Consolidado com ativo > 0, senão individual, escolhido uma vez por firma–data. A DMPL não foi necessária.
- **US:** lista **atual** do S&P 1500 (Wikipedia, ver manifesto), SIC fora de 6000–6799, com `dei:EntityCommonStockSharesOutstanding`, como pede o roteiro. Esse filtro retira firmas com mais de uma classe de ações (por exemplo Meta e Tyson). Por ser a composição atual, **há viés de sobrevivência nos EUA**, que não existe na amostra brasileira.

## Limitações de dados

- Os dados abertos da CVM trazem a versão vigente de cada documento; `filing_date` usa o menor DT_RECEB da primeira versão.
- CVM: a bandeira ESCALA_MOEDA varia entre documentos sem o número mudar; a correção usa a bandeira predominante da firma quando o ativo bruto é da mesma ordem das datas vizinhas (heurística; 235 datas). Saltos de ativo acima de 200× que restem no horizonte excluem o ponto.
- SEC: entre versões de um fato vale a primeira publicada; a posterior só corrige erro de escala ou de sinal. Tags alternativas preenchem só as datas que a principal não tem.
- Exercícios sem DFP anterior na janela ficam sem LA0: sem a DFP de 2015, o painel BR começa no 4º trimestre de 2016.
- `fco` e `pi` futuros são realizados, não previsões: o painel não usa IA nem previsão (Experimento I, estática comparativa).
- O FCO de muitas firmas já está líquido de juros pagos e S soma esses juros: é a regra do roteiro; `S_sem_juros` mede o efeito.

## Coluna opcional nas sensibilidades

- `I0`: juros da dívida pré-existente por trimestre, `S − S_sem_juros`, dedutíveis. Só em `scripts/etapa2/sens_extra.py`; o caso-base não a usa. Classe D, ou zero quando os juros não foram localizados.

## Painéis derivados

- `painel_BR_US_cf_taxa.csv`: regras da própria jurisdição, `line_rate` = taxa mediana da outra jurisdição no mesmo `tri` (canal de juros do roteiro).
- `painel_BR_US_troca.csv`: mesma firma sob as regras e a taxa da outra jurisdição; firmas americanas sob regras brasileiras usam a TJLP mediana do `tri`.
- `painel_BR_US_troca_taxa.csv`: mesma firma sob as regras da outra jurisdição, com a própria taxa.

`country`, nesses arquivos, é a jurisdição cujas regras se aplicam; a origem da firma está no prefixo de `firm_id`. Pontos de trimestres sem SOFR ficam fora.
