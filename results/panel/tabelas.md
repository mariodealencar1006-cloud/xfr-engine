# Experimento I em dados reais — painel CVM/SEC (Etapa 2)

Gerado por `scripts/etapa2/agrega.py`. T = 4 trimestres; q_frac = 1; c_E = 0,10. E* em proporção do ativo de t; ISC e CLS por unidade de q. IC de 95% por bootstrap em blocos de firma, estratificado pela amostra de origem, 1000 reamostragens, semente 20261104.

## Como ler estes números

- **Trilha A (pública).** Linhas, covenants e renovações não são observados, e `line_A` é parâmetro na maioria das linhas. Os números medem a sensibilidade do solver a cenários parametrizados e **não** validam a retirada real de crédito (Artigo 2, seção 6.4).
- **Regras.** As de 2026 (Tabela 4 do Artigo 2) valem para toda a janela, inclusive θ = 17,5%, como estática comparativa. FCO e EBIT futuros são os realizados; não há previsão.
- **DIP é cenário parametrizado (classe P).** BR 30% e EUA 100% da capacidade retirada, a 1,5 vez a taxa da linha, oferecido a toda firma no choque. O Apêndice A pede A > 0 só em recuperação, mas o painel não tem `recovery_status`. Por isso, `all_on` é um limite superior do papel do DIP; a sensibilidade ao acesso está na seção de hipóteses.
- **BR e EUA têm firmas diferentes.** Comparar as duas amostras mistura regras com perfil das firmas. H2, H3 e a Tabela 6A usam a mesma firma sob as duas jurisdições, como `experiment_I.py`. A Tabela 6B mostra a diferença entre as amostras apenas como dado descritivo.
- **Prejuízo é tercil de EBIT/ativo no país e no trimestre, não estado de perda.** A tabela de composição mostra a proporção de perdas efetivas.
- **As médias de E* são puxadas por poucas firmas muito pequenas.** Prefira as medianas.

## Amostra

| País | Firmas | Pontos de decisão | Primeiro t | Último t |
|---|---|---|---|---|
| BR | 746 | 16899 | 2016-06-30 | 2024-12-31 |
| US | 953 | 23817 | 2017-12-31 | 2024-12-31 |

Na comparação da mesma firma entram 38902 pontos: os demais são brasileiros de trimestres sem SOFR. Solver: 325728 de 325728 linhas com status ok; 1 com etapa 2 sem solução e 360 com q = 0 (linha remanescente observada igual a zero) entram como indefinidas.

Atrito (pontos brutos → painel):

- **BR:** datas_com_bandeira_de_escala_corrigida = 235; falta_LA = 1458; falta_caixa = 1; falta_ebit_futuro = 1; falta_fco_futuro = 3544; falta_receita_t = 441; firma_data_com_valores_conflitantes = 10; firmas_brutas = 1034; firmas_nao_financeiras = 824; fora_do_cadastro = 21; no_painel = 16899; pontos_brutos = 22469; quebra_de_escala_no_horizonte = 95; razao_extrema = 30
- **US:** ciks = 1489; falta_LA = 139; falta_PL = 308; falta_caixa = 440; falta_ebit_futuro = 139; falta_ebit_t = 2460; falta_fco_futuro = 50; falta_receita_t = 224; financeiras_ou_sem_SIC = 346; firmas_elegiveis = 1056; line_remanescente_zero_observado = 45; no_painel = 23817; pontos_brutos = 34841; razao_extrema = 3; sem_4_trimestres_a_frente = 4310; sem_SOFR_antes_de_2018-04 = 7261; sem_datas = 6; sem_dei_shares = 81

## Composição por classe de dados (Apêndice A do Artigo 2)

`data_class` é P em 100% das linhas, porque L e q_frac são parâmetros e a pior classe domina. A composição coluna a coluna, abaixo, descreve a amostra de todas as tabelas; os subconjuntos das hipóteses e a comparação da mesma firma usam parte destes pontos. DIP é P em toda linha com DIP ligado.

| País | Regime | N | EBIT<0 em t | Σπ futuro<0 | PL<0 (limitado a 0) | C0 O/D | FCO O/D/P | S D/P | line_A O/P | PF0 O/P |
|---|---|---|---|---|---|---|---|---|---|---|
| BR | equilibrio | 5635 | 0% | 6% | 6% | 100/0% | 69/8/23% | 78/22% | 0/100% | 0/100% |
| BR | lucro | 5646 | 0% | 4% | 8% | 100/0% | 68/9/23% | 73/27% | 0/100% | 0/100% |
| BR | prejuizo | 5618 | 71% | 54% | 26% | 100/0% | 43/8/49% | 53/47% | 0/100% | 0/100% |
| US | equilibrio | 7941 | 0% | 4% | 2% | 94/6% | 50/48/2% | 51/49% | 12/88% | 60/40% |
| US | lucro | 7948 | 0% | 2% | 9% | 95/5% | 51/47/1% | 42/58% | 8/92% | 52/48% |
| US | prejuizo | 7928 | 41% | 31% | 4% | 95/5% | 48/47/5% | 44/56% | 10/90% | 66/34% |

## Tabela 5 — ISC e CLS por país, regime e configuração (amostra própria)

`ISC>0` = proporção de pontos em que a retirada exige aporte adicional. `Indefinido` inclui q = 0 e etapa 2 sem solução. Classes de dados: ver a seção de composição; `data_class` é P em todas as linhas.

| País | Regime | Config. | N | Firmas | ISC mediana | ISC média | ISC>0 | CLS mediana | CLS média | E*(0) mediana | E*(q) mediana | E*(0) média | E*(q) média | Indefinido |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BR | equilibrio | all_off | 5635 | 614 | 0.000 | 0.207 | 37.6% | 0.0000 | -0.0008 | 0.000 | 0.000 | 0.038 | 0.059 | 0.0% |
| BR | equilibrio | all_on | 5635 | 614 | 0.000 | 0.153 | 33.3% | 0.0000 | 0.0072 | 0.000 | 0.000 | 0.043 | 0.058 | 0.0% |
| BR | equilibrio | no_dip | 5635 | 614 | 0.000 | 0.259 | 45.5% | 0.0000 | 0.0049 | 0.000 | 0.000 | 0.043 | 0.069 | 0.0% |
| BR | equilibrio | no_interest_cap | 5635 | 614 | 0.000 | 0.153 | 33.3% | 0.0000 | 0.0072 | 0.000 | 0.000 | 0.043 | 0.058 | 0.0% |
| BR | equilibrio | no_jcp | 5635 | 614 | 0.000 | 0.159 | 34.4% | 0.0000 | 0.0089 | 0.000 | 0.000 | 0.043 | 0.059 | 0.0% |
| BR | equilibrio | no_loss_cap | 5635 | 614 | 0.000 | 0.153 | 33.2% | 0.0000 | 0.0072 | 0.000 | 0.000 | 0.043 | 0.058 | 0.0% |
| BR | equilibrio | no_rate | 5635 | 614 | 0.000 | 0.153 | 33.3% | 0.0000 | 0.0072 | 0.000 | 0.000 | 0.043 | 0.058 | 0.0% |
| BR | equilibrio | no_tax | 5635 | 614 | 0.000 | 0.124 | 26.9% | 0.0000 | 0.0045 | 0.000 | 0.000 | 0.038 | 0.050 | 0.0% |
| BR | lucro | all_off | 5646 | 592 | 0.000 | 0.151 | 26.4% | 0.0000 | -0.0006 | 0.000 | 0.000 | 0.054 | 0.069 | 0.0% |
| BR | lucro | all_on | 5646 | 592 | 0.000 | 0.134 | 27.8% | 0.0000 | 0.0059 | 0.000 | 0.000 | 0.063 | 0.077 | 0.0% |
| BR | lucro | no_dip | 5646 | 592 | 0.000 | 0.221 | 37.9% | 0.0000 | 0.0043 | 0.000 | 0.000 | 0.063 | 0.085 | 0.0% |
| BR | lucro | no_interest_cap | 5646 | 592 | 0.000 | 0.134 | 27.8% | 0.0000 | 0.0059 | 0.000 | 0.000 | 0.063 | 0.077 | 0.0% |
| BR | lucro | no_jcp | 5646 | 592 | 0.000 | 0.138 | 28.4% | 0.0000 | 0.0074 | 0.000 | 0.000 | 0.064 | 0.078 | 0.0% |
| BR | lucro | no_loss_cap | 5646 | 592 | 0.000 | 0.133 | 27.6% | 0.0000 | 0.0060 | 0.000 | 0.000 | 0.063 | 0.076 | 0.0% |
| BR | lucro | no_rate | 5646 | 592 | 0.000 | 0.134 | 27.8% | 0.0000 | 0.0059 | 0.000 | 0.000 | 0.063 | 0.077 | 0.0% |
| BR | lucro | no_tax | 5646 | 592 | 0.000 | 0.093 | 18.8% | 0.0000 | 0.0030 | 0.000 | 0.000 | 0.054 | 0.064 | 0.0% |
| BR | prejuizo | all_off | 5618 | 582 | 0.057 | 0.357 | 54.3% | 0.0000 | -0.0014 | 0.000 | 0.013 | 0.255 | 0.290 | 0.0% |
| BR | prejuizo | all_on | 5618 | 582 | 0.000 | 0.248 | 45.7% | 0.0003 | 0.0081 | 0.000 | 0.006 | 0.263 | 0.288 | 0.0% |
| BR | prejuizo | no_dip | 5618 | 582 | 0.141 | 0.382 | 58.5% | 0.0000 | 0.0021 | 0.000 | 0.022 | 0.263 | 0.301 | 0.0% |
| BR | prejuizo | no_interest_cap | 5618 | 582 | 0.000 | 0.248 | 45.7% | 0.0003 | 0.0081 | 0.000 | 0.006 | 0.263 | 0.288 | 0.0% |
| BR | prejuizo | no_jcp | 5618 | 582 | 0.000 | 0.250 | 46.0% | 0.0008 | 0.0090 | 0.000 | 0.006 | 0.264 | 0.289 | 0.0% |
| BR | prejuizo | no_loss_cap | 5618 | 582 | 0.000 | 0.247 | 45.6% | 0.0001 | 0.0080 | 0.000 | 0.005 | 0.263 | 0.287 | 0.0% |
| BR | prejuizo | no_rate | 5618 | 582 | 0.000 | 0.248 | 45.7% | 0.0003 | 0.0081 | 0.000 | 0.006 | 0.263 | 0.288 | 0.0% |
| BR | prejuizo | no_tax | 5618 | 582 | 0.000 | 0.234 | 43.1% | 0.0000 | 0.0064 | 0.000 | 0.001 | 0.255 | 0.278 | 0.0% |
| US | equilibrio | all_off | 7941 | 830 | 0.000 | 0.010 | 3.7% | 0.0000 | 0.0006 | 0.000 | 0.000 | 0.001 | 0.002 | 0.2% |
| US | equilibrio | all_on | 7941 | 830 | 0.000 | 0.000 | 0.2% | 0.0000 | 0.0003 | 0.000 | 0.000 | 0.001 | 0.001 | 0.2% |
| US | equilibrio | no_dip | 7941 | 830 | 0.000 | 0.014 | 5.0% | 0.0000 | 0.0009 | 0.000 | 0.000 | 0.001 | 0.002 | 0.2% |
| US | equilibrio | no_interest_cap | 7941 | 830 | 0.000 | 0.000 | 0.2% | 0.0000 | 0.0002 | 0.000 | 0.000 | 0.001 | 0.001 | 0.2% |
| US | equilibrio | no_jcp | 7941 | 830 | 0.000 | 0.000 | 0.2% | 0.0000 | 0.0003 | 0.000 | 0.000 | 0.001 | 0.001 | 0.2% |
| US | equilibrio | no_loss_cap | 7941 | 830 | 0.000 | 0.000 | 0.2% | 0.0000 | 0.0002 | 0.000 | 0.000 | 0.001 | 0.001 | 0.2% |
| US | equilibrio | no_rate | 7941 | 830 | 0.000 | 0.000 | 0.2% | 0.0000 | 0.0003 | 0.000 | 0.000 | 0.001 | 0.001 | 0.2% |
| US | equilibrio | no_tax | 7941 | 830 | 0.000 | 0.000 | 0.1% | 0.0000 | 0.0002 | 0.000 | 0.000 | 0.001 | 0.001 | 0.2% |
| US | lucro | all_off | 7948 | 700 | 0.000 | 0.005 | 1.4% | 0.0000 | 0.0003 | 0.000 | 0.000 | 0.000 | 0.001 | 0.2% |
| US | lucro | all_on | 7948 | 700 | 0.000 | 0.000 | 0.3% | 0.0000 | 0.0001 | 0.000 | 0.000 | 0.001 | 0.001 | 0.2% |
| US | lucro | no_dip | 7948 | 700 | 0.000 | 0.007 | 2.0% | 0.0000 | 0.0005 | 0.000 | 0.000 | 0.001 | 0.001 | 0.2% |
| US | lucro | no_interest_cap | 7948 | 700 | 0.000 | 0.000 | 0.3% | 0.0000 | 0.0001 | 0.000 | 0.000 | 0.001 | 0.001 | 0.2% |
| US | lucro | no_jcp | 7948 | 700 | 0.000 | 0.000 | 0.3% | 0.0000 | 0.0001 | 0.000 | 0.000 | 0.001 | 0.001 | 0.2% |
| US | lucro | no_loss_cap | 7948 | 700 | 0.000 | 0.000 | 0.3% | 0.0000 | 0.0001 | 0.000 | 0.000 | 0.001 | 0.001 | 0.2% |
| US | lucro | no_rate | 7948 | 700 | 0.000 | 0.000 | 0.3% | 0.0000 | 0.0001 | 0.000 | 0.000 | 0.001 | 0.001 | 0.2% |
| US | lucro | no_tax | 7948 | 700 | 0.000 | 0.000 | 0.2% | 0.0000 | 0.0001 | 0.000 | 0.000 | 0.000 | 0.000 | 0.2% |
| US | prejuizo | all_off | 7928 | 765 | 0.000 | 0.035 | 8.0% | 0.0000 | 0.0021 | 0.000 | 0.000 | 0.004 | 0.007 | 0.2% |
| US | prejuizo | all_on | 7928 | 765 | 0.000 | 0.000 | 2.1% | 0.0000 | 0.0008 | 0.000 | 0.000 | 0.004 | 0.004 | 0.2% |
| US | prejuizo | no_dip | 7928 | 765 | 0.000 | 0.039 | 9.3% | 0.0000 | 0.0024 | 0.000 | 0.000 | 0.004 | 0.008 | 0.2% |
| US | prejuizo | no_interest_cap | 7928 | 765 | 0.000 | 0.000 | 2.1% | 0.0000 | 0.0008 | 0.000 | 0.000 | 0.004 | 0.004 | 0.2% |
| US | prejuizo | no_jcp | 7928 | 765 | 0.000 | 0.000 | 2.1% | 0.0000 | 0.0008 | 0.000 | 0.000 | 0.004 | 0.004 | 0.2% |
| US | prejuizo | no_loss_cap | 7928 | 765 | 0.000 | 0.000 | 2.1% | 0.0000 | 0.0008 | 0.000 | 0.000 | 0.004 | 0.004 | 0.2% |
| US | prejuizo | no_rate | 7928 | 765 | 0.000 | 0.000 | 2.1% | 0.0000 | 0.0008 | 0.000 | 0.000 | 0.004 | 0.004 | 0.2% |
| US | prejuizo | no_tax | 7928 | 765 | 0.000 | 0.000 | 1.9% | 0.0000 | 0.0008 | 0.000 | 0.000 | 0.004 | 0.004 | 0.2% |

## Tabela 6A — decomposição de BR − EUA na mesma firma (médias; regras uma de cada vez)

`Média` é a média simples das amostras de firmas brasileiras e americanas. `tributário` é o efeito de desligar o tributo (τ, θ), o que também zera o JCP e torna κ_P e κ_I inócuos; por isso JCP, κ_P e κ_I são componentes informativos e **não** entram na soma. `juros` compara as taxas das duas jurisdições sob cada conjunto de regras. `resíduo` = total − tributário − juros − instrumento. Classes de dados: ver a seção de composição; `data_class` é P em todas as linhas.

| Amostra | Regime | Métrica | Total BR−EUA | tributário | do qual JCP | do qual κ_P | do qual κ_I | juros | instrumento (DIP) | resíduo |
|---|---|---|---|---|---|---|---|---|---|---|
| Média | lucro | ISC | 0.0642 | 0.0204 | -0.0021 | 0.0003 | -0.0000 | 0.0005 | 0.0577 | -0.0143 |
| Média | lucro | CLS | 0.0012 | 0.0014 | -0.0007 | 0.0000 | -0.0000 | 0.0004 | 0.0057 | -0.0063 |
| Média | equilibrio | ISC | 0.0750 | 0.0152 | -0.0030 | 0.0004 | -0.0000 | 0.0009 | 0.0722 | -0.0133 |
| Média | equilibrio | CLS | 0.0014 | 0.0015 | -0.0009 | 0.0000 | -0.0000 | 0.0008 | 0.0074 | -0.0083 |
| Média | prejuizo | ISC | 0.1282 | 0.0085 | -0.0012 | 0.0009 | -0.0001 | 0.0008 | 0.1321 | -0.0132 |
| Média | prejuizo | CLS | 0.0001 | 0.0010 | -0.0005 | 0.0001 | -0.0001 | 0.0007 | 0.0112 | -0.0128 |
| Firmas BR | lucro | ISC | 0.1249 | 0.0393 | -0.0040 | 0.0004 | -0.0000 | 0.0009 | 0.1128 | -0.0281 |
| Firmas BR | lucro | CLS | 0.0022 | 0.0027 | -0.0014 | -0.0000 | -0.0001 | 0.0008 | 0.0110 | -0.0122 |
| Firmas BR | equilibrio | ISC | 0.1440 | 0.0283 | -0.0055 | 0.0004 | -0.0001 | 0.0016 | 0.1401 | -0.0259 |
| Firmas BR | equilibrio | CLS | 0.0026 | 0.0028 | -0.0016 | 0.0000 | -0.0001 | 0.0015 | 0.0139 | -0.0155 |
| Firmas BR | prejuizo | ISC | 0.2355 | 0.0152 | -0.0021 | 0.0012 | -0.0001 | 0.0014 | 0.2440 | -0.0251 |
| Firmas BR | prejuizo | CLS | -0.0000 | 0.0019 | -0.0009 | 0.0002 | -0.0002 | 0.0011 | 0.0202 | -0.0233 |
| Firmas EUA | lucro | ISC | 0.0036 | 0.0015 | -0.0002 | 0.0001 | -0.0000 | 0.0001 | 0.0025 | -0.0006 |
| Firmas EUA | lucro | CLS | 0.0001 | 0.0001 | -0.0000 | 0.0000 | -0.0000 | 0.0001 | 0.0004 | -0.0005 |
| Firmas EUA | equilibrio | ISC | 0.0059 | 0.0022 | -0.0004 | 0.0004 | -0.0000 | 0.0002 | 0.0043 | -0.0007 |
| Firmas EUA | equilibrio | CLS | 0.0002 | 0.0001 | -0.0001 | 0.0000 | -0.0000 | 0.0002 | 0.0009 | -0.0010 |
| Firmas EUA | prejuizo | ISC | 0.0209 | 0.0019 | -0.0003 | 0.0006 | -0.0000 | 0.0002 | 0.0202 | -0.0014 |
| Firmas EUA | prejuizo | CLS | 0.0003 | 0.0001 | -0.0001 | 0.0000 | -0.0000 | 0.0003 | 0.0023 | -0.0023 |

## Tabela 6B — diferença entre as amostras (descritiva, não institucional)

`Sem regras` é a diferença BR − EUA com todas as regras desligadas: reflete o perfil das firmas e a taxa de cada país. Classes de dados: ver a seção de composição; `data_class` é P em todas as linhas.

| Regime | Métrica | BR−EUA, all_on | BR−EUA, sem regras (all_off) | Diferença |
|---|---|---|---|---|
| lucro | ISC | 0.1336 | 0.1462 | -0.0126 |
| lucro | CLS | 0.0058 | -0.0009 | 0.0067 |
| equilibrio | ISC | 0.1533 | 0.1965 | -0.0432 |
| equilibrio | CLS | 0.0069 | -0.0014 | 0.0083 |
| prejuizo | ISC | 0.2479 | 0.3215 | -0.0735 |
| prejuizo | CLS | 0.0073 | -0.0035 | 0.0109 |

## Hipóteses H1–H3

H1 usa a amostra própria. H2 e H3 usam a mesma firma sob as duas jurisdições. Classes de dados: ver a seção de composição; `data_class` é P em todas as linhas.

| Amostra | Teste | Estimativa | IC 95% | Esperado | Resultado |
|---|---|---|---|---|---|
| Completa | H1 BR: ISC(prejuízo) − ISC(lucro), no_dip, média | 0.1606 | [0.1213; 0.1965] | < 0 | contraria |
| Completa | H1 BR: idem, mediana | 0.1408 | [0.0483; 0.2640] | < 0 | contraria |
| Completa | H1 US: ISC(prejuízo) − ISC(lucro), no_dip, média | 0.0316 | [0.0225; 0.0424] | < 0 | contraria |
| Completa | H1 US: idem, mediana | 0.0000 | [0.0000; 0.0000] | < 0 | sem variação: estatística igual a 0 |
| Completa | H2 mesma firma: ISC_BR − ISC_US, prejuízo, no_dip | -0.0039 | [-0.0052; -0.0025] | ≤ 0 | confirma |
| Completa | H2 mesma firma, só firmas BR, no_dip | -0.0085 | [-0.0110; -0.0059] | ≤ 0 | confirma |
| Completa | H2 mesma firma, só firmas US, no_dip | 0.0007 | [0.0000; 0.0014] | ≤ 0 | contraria |
| Completa | H2 mesma firma: ISC_BR − ISC_US, prejuízo, all_on | 0.1282 | [0.1151; 0.1411] | > 0 | confirma |
| Completa | H2 mesma firma, só firmas BR, all_on | 0.2355 | [0.2095; 0.2621] | > 0 | confirma |
| Completa | H2 mesma firma, só firmas US, all_on | 0.0209 | [0.0147; 0.0278] | > 0 | confirma |
| Completa | H3 mesma firma: contribuição do JCP à DiD do CLS (all_on − no_jcp) | 0.0002 | [0.0001; 0.0003] | > 0 | confirma |
| Janela comum (t ≥ 2018-06) | H1 BR: ISC(prejuízo) − ISC(lucro), no_dip, média | 0.1597 | [0.1184; 0.1987] | < 0 | contraria |
| Janela comum (t ≥ 2018-06) | H1 US: ISC(prejuízo) − ISC(lucro), no_dip, média | 0.0316 | [0.0217; 0.0423] | < 0 | contraria |
| Janela comum (t ≥ 2018-06) | H2 mesma firma: ISC_BR − ISC_US, prejuízo, no_dip | -0.0039 | [-0.0051; -0.0025] | ≤ 0 | confirma |
| Janela comum (t ≥ 2018-06) | H2 mesma firma: ISC_BR − ISC_US, prejuízo, all_on | 0.1270 | [0.1139; 0.1396] | > 0 | confirma |
| Janela comum (t ≥ 2018-06) | H3 mesma firma: contribuição do JCP à DiD do CLS (all_on − no_jcp) | 0.0002 | [0.0001; 0.0003] | > 0 | confirma |
| Horizonte cruza 2020 (estresse) | H1 BR: ISC(prejuízo) − ISC(lucro), no_dip, média | 0.1783 | [0.1212; 0.2344] | < 0 | contraria |
| Horizonte cruza 2020 (estresse) | H1 US: ISC(prejuízo) − ISC(lucro), no_dip, média | 0.0422 | [0.0280; 0.0554] | < 0 | contraria |
| Horizonte cruza 2020 (estresse) | H2 mesma firma: ISC_BR − ISC_US, prejuízo, no_dip | -0.0003 | [-0.0017; 0.0014] | ≤ 0 | inconclusivo (IC inclui 0) |
| Horizonte cruza 2020 (estresse) | H2 mesma firma: ISC_BR − ISC_US, prejuízo, all_on | 0.1395 | [0.1210; 0.1571] | > 0 | confirma |
| Horizonte cruza 2020 (estresse) | H3 mesma firma: contribuição do JCP à DiD do CLS (all_on − no_jcp) | 0.0002 | [0.0001; 0.0004] | > 0 | confirma |
| Horizonte fora de 2020 | H1 BR: ISC(prejuízo) − ISC(lucro), no_dip, média | 0.1563 | [0.1157; 0.1957] | < 0 | contraria |
| Horizonte fora de 2020 | H1 US: ISC(prejuízo) − ISC(lucro), no_dip, média | 0.0284 | [0.0185; 0.0389] | < 0 | contraria |
| Horizonte fora de 2020 | H2 mesma firma: ISC_BR − ISC_US, prejuízo, no_dip | -0.0049 | [-0.0064; -0.0033] | ≤ 0 | confirma |
| Horizonte fora de 2020 | H2 mesma firma: ISC_BR − ISC_US, prejuízo, all_on | 0.1250 | [0.1119; 0.1375] | > 0 | confirma |
| Horizonte fora de 2020 | H3 mesma firma: contribuição do JCP à DiD do CLS (all_on − no_jcp) | 0.0002 | [0.0001; 0.0003] | > 0 | confirma |

**H2, leitura conjunta (mesma firma, prejuízo):** sem DIP, -0.0039 [-0.0052; -0.0025]; com DIP, 0.1282 [0.1151; 0.1411]. O sinal se inverte com o DIP, como a H2 prevê, e os dois IC sustentam a inversão.

### H2 — sensibilidade ao acesso a DIP (mesma firma, all_on)

A inversão de sinal depende de uma suposição, não de um dado observado. A tabela varia só o acesso, como o `dip_sweep` de `experiment_I.py`: Brasil fixo em 30% e EUA de 0% a 100%, mais o caso de acesso igual a 100% (Artigo 2, seção 7.3, cenário d) e o caso sem DIP. As colunas de `Prejuízo` até `Só firmas EUA` são desse regime; `Prejuízo`, `Equilíbrio` e `Lucro` são médias simples das duas amostras. Classes de dados: ver a seção de composição; `data_class` é P em todas as linhas.

| Acesso BR | Acesso EUA | Prejuízo: BR−EUA | IC 95% | Só firmas BR | Só firmas EUA | Equilíbrio | Lucro |
|---|---|---|---|---|---|---|---|
| 0% | 0% | -0.0039 | [-0.0052; -0.0025] | -0.0085 | 0.0007 | 0.0028 | 0.0066 |
| 30% | 0% | -0.0784 | [-0.0847; -0.0718] | -0.1395 | -0.0174 | -0.0535 | -0.0378 |
| 30% | 10% | -0.0497 | [-0.0542; -0.0451] | -0.0896 | -0.0098 | -0.0321 | -0.0218 |
| 30% | 20% | -0.0240 | [-0.0266; -0.0212] | -0.0439 | -0.0040 | -0.0132 | -0.0077 |
| 30% | 30% | -0.0003 | [-0.0012; 0.0006] | -0.0014 | 0.0007 | 0.0031 | 0.0047 |
| 30% | 50% | 0.0421 | [0.0382; 0.0456] | 0.0760 | 0.0082 | 0.0300 | 0.0259 |
| 30% | 75% | 0.0881 | [0.0797; 0.0963] | 0.1610 | 0.0153 | 0.0557 | 0.0470 |
| 30% | 100% | 0.1282 | [0.1151; 0.1411] | 0.2355 | 0.0209 | 0.0750 | 0.0642 |
| 100% | 100% | 0.0039 | [0.0034; 0.0044] | 0.0072 | 0.0006 | 0.0014 | 0.0013 |

Com o Brasil fixo em 30%, a diferença em prejuízo é positiva com IC acima de zero a partir de 50% de acesso nos EUA e negativa com IC abaixo de zero até 20%. Com acesso igual, a diferença é -0.0003 [-0.0012; 0.0006] a 30% e 0.0039 [0.0034; 0.0044] a 100%.

### H1 — margem extensiva e margem intensiva (no_dip)

Comparar regimes muda também FCO, caixa e S, não só o tratamento tributário: o teste não é *ceteris paribus*. A decomposição separa a proporção de pontos em que a retirada exige aporte (extensiva) do tamanho do índice quando ela exige (intensiva). A estimativa dentro da firma usa firmas vistas nos dois regimes. Análise complementar, não pré-especificada.

| País | ISC>0 prejuízo | ISC>0 lucro | ISC dado ISC>0, prejuízo | ISC dado ISC>0, lucro | Diferença | Extensiva | Intensiva | Firmas nos dois regimes | Dentro da firma | IC 95% |
|---|---|---|---|---|---|---|---|---|---|---|
| BR | 58.5% | 37.9% | 0.653 | 0.585 | 0.1606 | 0.1275 | 0.0330 | 442 | 0.0140 | [-0.0087; 0.0369] |
| US | 9.3% | 2.0% | 0.416 | 0.348 | 0.0316 | 0.0277 | 0.0039 | 516 | 0.0122 | [0.0041; 0.0199] |

### H3 — efeito do JCP no CLS por regime (firmas brasileiras, regras BR)

| Regime | CLS, all_on | CLS, no_jcp | Efeito do JCP |
|---|---|---|---|
| lucro | 0.0059 | 0.0074 | -0.0015 |
| equilibrio | 0.0072 | 0.0089 | -0.0017 |
| prejuizo | 0.0081 | 0.0090 | -0.0009 |

## Sensibilidades

### Sem dupla contagem de juros (S sem juros pagos)

O FCO do roteiro já vem líquido de juros em muitas firmas, e S os soma de novo. O Artigo 1 pede para evitar essa dupla contagem; aqui ela é retirada.

| Amostra | Teste | Estimativa | IC 95% | Esperado | Resultado |
|---|---|---|---|---|---|
| Sem dupla contagem | H1 BR: ISC(prejuízo) − ISC(lucro), no_dip, média | 0.1693 | [0.1296; 0.2043] | < 0 | contraria |
| Sem dupla contagem | H1 US: ISC(prejuízo) − ISC(lucro), no_dip, média | 0.0256 | [0.0172; 0.0357] | < 0 | contraria |
| Sem dupla contagem | H2 mesma firma: ISC_BR − ISC_US, prejuízo, no_dip | -0.0036 | [-0.0049; -0.0023] | ≤ 0 | confirma |
| Sem dupla contagem | H2 mesma firma: ISC_BR − ISC_US, prejuízo, all_on | 0.1166 | [0.1034; 0.1292] | > 0 | confirma |
| Sem dupla contagem | H3 mesma firma: contribuição do JCP à DiD do CLS (all_on − no_jcp) | 0.0002 | [0.0001; 0.0003] | > 0 | confirma |

### Firmas brasileiras com PF0 = 0,05 do ativo (Apêndice A.2)

| Regime | Config. | ISC, base → sensibilidade | CLS, base → sensibilidade |
|---|---|---|---|
| equilibrio | all_on | 0.153 → 0.146 | 0.0072 → 0.0068 |
| equilibrio | no_dip | 0.259 → 0.246 | 0.0049 → 0.0038 |
| lucro | all_on | 0.134 → 0.123 | 0.0059 → 0.0054 |
| lucro | no_dip | 0.221 → 0.203 | 0.0043 → 0.0034 |
| prejuizo | all_on | 0.248 → 0.246 | 0.0081 → 0.0080 |
| prejuizo | no_dip | 0.382 → 0.378 | 0.0021 → 0.0017 |

### Firmas brasileiras com PF0 = 0,10 do ativo (Apêndice A.2)

| Regime | Config. | ISC, base → sensibilidade | CLS, base → sensibilidade |
|---|---|---|---|
| equilibrio | all_on | 0.153 → 0.145 | 0.0072 → 0.0068 |
| equilibrio | no_dip | 0.259 → 0.245 | 0.0049 → 0.0038 |
| lucro | all_on | 0.134 → 0.122 | 0.0059 → 0.0054 |
| lucro | no_dip | 0.221 → 0.201 | 0.0043 → 0.0032 |
| prejuizo | all_on | 0.248 → 0.246 | 0.0081 → 0.0079 |
| prejuizo | no_dip | 0.382 → 0.377 | 0.0021 → 0.0016 |

## Escolhas onde o roteiro não decide

```
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
```
