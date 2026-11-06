# xfr-engine — deterministic financial engine for *The Shadow Price of Credit*

Python implementation of the mathematical core of the manuscript *The Shadow Price of Credit: An
Explainable-AI Decision-Support System for Corporate Recapitalization under Credit-Line Withdrawal*
(M. de Alencar Netto, 2026, manuscript for submission): cash and debt identities, instrument
eligibility, minimum cash reserve, the minimum-equity problem, the credit-to-equity substitution index
(CES; *ISC* in the Portuguese version) and the shadow price of credit capacity, including its
directional form A(q) = A_base − q·h. No AI and no stochastic scenarios — this is the "transparent unit
test" of Section 9 of the paper (Appendix A describes the implementation).

## What is implemented

| Manuscript | Code |
|---|---|
| Eq. (1) cash identity; (2) debt evolution; (3) eligibility `D ≤ A`, `B ≤ H` | `solver._build` |
| Eq. (4) minimum reserve, deterministic version `C_t ≥ L_t` | rows `floor[t]` |
| Eq. (6) minimum equity `E* = min E0` | `solve_min_equity` |
| Eq. (7) CES, with "undefined/infeasible" states | `metrics.isc` (single limit) · `directional.ces` (direction h) |
| Eq. (8) domain of q, `q_max` | `directional.q_max` |
| Eq. (9) cost stage, deterministic version | `solve_min_cost` |
| Eq. (10) shadow price of credit (LP dual) and directional subgradient Σ h·λ | `Solution.pi_credit` · `directional.pi_directional` |
| One-sided derivatives of E* (Proposition 2) | `metrics.shadow_price_fd` · `directional.derivatives_q` |
| Propositions 1–2, numerical verification on a grid | `metrics.estar_curve`/`proposition_checks` · `directional.estar_curve_q`/`proposition_checks_q` |
| Section 6.9 terminality and infeasibility diagnosis (minimum relaxation) | `Firm.terminal_repay`, `solver.diagnose_infeasibility` |
| Section 9.2 closed form `1 − charges/q` | `metrics.closed_form_isc` |
| Tests of Section 9, Appendix A.1 and the directional form | `tests/` (26 automated cases; 36 with the institutional layer; 54 with the Stage 2 panel) |
| Explanation layer (binding constraints, blocked instruments) | `Solution.binding` |

Solver: linear programming with HiGHS (`scipy.optimize.linprog`). Dependencies: `numpy`, `scipy`;
`pytest` for the tests; `pandas` and `matplotlib` for the Stage 2 scripts and the figures (`pip install -e ".[etapa2]"`).
Without pandas, the two tests of the Stage 2 panel builder are skipped.

## Usage

```bash
pip install -e .
python -m xfr_engine.example_section9                 # reproduces Section 9 and the variants
python -m xfr_engine.example_section9 --json results/section9.json
pip install pytest                                    # only needed for the tests
pytest -q                                             # 54 tests (2 skipped without pandas)
```

```python
from xfr_engine import Firm, Instrument, solve_min_equity, ces, estar_curve_q, proposition_checks_q

line = Instrument("line", A=[0, 0.70, 0, 0, 0, 0], rate=0.02/0.70, interest_on="end")
firm = Firm(T=6, C0=0.80, FCO=[-0.25, -0.25, 0.05, 0.05, 0.05, 0.05], S=0.20, L=0.30, instruments=[line])

sol = solve_min_equity(firm)          # sol.E0 = 0.40 ; sol.pi_credit[0][1] = 0.857 (dual of D ≤ A in month 2)
h = {("line", 2): 1.0}                # withdrawal direction: the month-2 limit
r = ces(firm, h, q=0.70)              # r.ces = 0.857 ; r.E_shock = 1.00 ; bounds r.pi_0_right ≤ r.ces ≤ r.pi_q_left
curve = estar_curve_q(firm, h, [0.05 * k for k in range(15)])
proposition_checks_q(curve)           # P1 nondecreasing & convex, P2 holds
```

## Results of the Section 9 example

| Quantity | Manuscript | Engine |
|---|---|---|
| E*(base) | 0.40 | 0.4000 |
| E*(shock) | 1.00 | 1.0000 |
| CES = ΔE*/q | 0.857 | 0.857143 |
| Closed form 1 − 0.10/0.70 | 0.857 | 0.857143 |
| Shadow price π(line, month 2) | — | 0.857143 (LP dual and finite differences) |
| Cash paths (Table 8) | idem | idem |
| Propositions 1–2 on the grid q ∈ [0, 0.70] | — | satisfied |

Variants reported in Section 9.2 of the paper:

* **Revolving line with ceiling H = 0.70 available in months 2–6**: E* = 0.353; CES = 0.925 — the
  option to choose the drawdown timing lowers the required contribution and makes the line more valuable.
* **Terminality (repay principal in month 6)**: the optimizer does not draw; E* = 1.00 and CES = 0 (Section 6.9).
* **Contribution cap E0 ≤ 0.50 in the shock**: `infeasible`, with a minimum relaxation of 1.10 of cumulative
  shortfall in months 3–6 (0.05 + 0.20 + 0.35 + 0.50; maximum point shortfall 0.50 in month 6).
* **Degeneracy**: at q = q_max (A = 0) the multiplier returned by HiGHS (1.00) is an admissible subgradient
  but differs from the left-hand derivative (0.857); Proposition 2 is therefore stated in one-sided
  derivatives and the engine reports both.

## v0.3.0 — institutional layer (companion paper, Article 2)

`xfr_engine/institutional.py` adds, on top of the Article 1 core, the institutional layer of the companion
paper: corporate tax T_t on taxable income, deductible interest with an optional cap κ_I (IRC §163(j)),
loss-offset limit κ_P (Brazil 30% / U.S. 80%), interest on equity (JCP) with its TJLP base and the 50%
profit / 50% retained-earnings ceiling (Lei 9.249/1995 art. 9, as restricted in 2023–2025), withholding θ,
JCP paid in cash or credited-and-capitalized, the interest-rate process of the line (interest channel) and a
DIP instrument available only in the recovery state (q > 0). Deterministic single scenario, solved as a
mixed-integer LP (HiGHS via `scipy.optimize.milp`); binaries only for the sign of taxable income and the
JCP-ceiling branch. With the layer switched off the problem reduces to the Article 1 LP and reproduces its
values exactly (`tests/test_institutional.py`).

Two metrics are reported together and never added: the CES/ISC (quantity of equity per unit of credit
withdrawn) and the net cost of substitution CLS = [C*(q) − C*(0)]/q (economic cost per unit withdrawn).

```bash
python -m xfr_engine.experiment_I --out results     # Tables 5–6, hypothesis checks, DIP sweep, figure
pytest -q                                           # 54 tests
```

Experiment I on the Article 1 synthetic example (results/experiment_I.md): with instruments held fixed, the
CES is lower in the loss regime than in the profit regime in both jurisdictions (H1); without DIP the
Brazilian CES is below the U.S. one, because credit is dearer net of tax (H2a), and the sign flips once U.S.
DIP replaces more than about a third of the withdrawn capacity (H2b); the JCP contribution to the
profit-versus-loss difference-in-differences of CLS is positive but small over a six-month horizon (H3).

## Limits of this version

Deterministic, single scenario, no chance constraint (4), no non-anticipativity (6.8), no multistage
scenarios. Planned extensions: scenarios → block LP with shared first-stage variables;
CVaR → Rockafellar–Uryasev formulation (still an LP); chance constraint → mixed-integer version, for which
the LP dual is no longer the shadow price (Section 6.10).

## v0.4.0 — Stage 2: Experiment I on a CVM/SEC panel

`scripts/etapa2/` builds the firm-quarter panel of `docs/etapa2_claude_code.md` from public data and runs Experiment I on it.
Results are in [`results/panel/tabelas.md`](results/panel/tabelas.md), the data dictionary in `data/panel/dicionario.md`, and the
source URLs, timestamps and md5 in `data/raw/manifest.csv`.

```bash
python scripts/etapa2/coleta.py cvm
python scripts/etapa2/coleta.py macro
python scripts/etapa2/coleta.py lista
python scripts/etapa2/coleta.py sec
python scripts/etapa2/painel.py
python -m xfr_engine.panel data/panel/painel_BR_US.csv --out results/panel/experimento_I_painel.csv --c_E 0.10 --jobs 9
python -m xfr_engine.panel data/panel/painel_BR_US_cf_taxa.csv --out data/panel/experimento_I_cf_taxa.csv --c_E 0.10 --jobs 9
python -m xfr_engine.panel data/panel/painel_BR_US_troca.csv --out data/panel/experimento_I_troca.csv --c_E 0.10 --jobs 9
python -m xfr_engine.panel data/panel/painel_BR_US_troca_taxa.csv --out data/panel/experimento_I_troca_taxa.csv --c_E 0.10 --jobs 9
python scripts/etapa2/sens_dip.py --jobs 9
python scripts/etapa2/sens_extra.py --jobs 9
python scripts/etapa2/agrega.py
```

Public-data track only: credit lines, covenants and renewal decisions are not observed, so these numbers measure solver sensitivity to
parameterized scenarios and do not validate actual credit withdrawals. Changes to the engine in this version: optional `r_tjlp` and `dip_access` columns
and `--jobs`/`--configs` in `xfr_engine.panel`; HiGHS is retried without presolve when presolve fails or returns E*(q) < E*(0), a case
the model cannot produce; JCP and DIP in the panel output come from the cost stage. The synthetic Experiment I is unchanged.

## v0.4.1 — channel fix and complete sensitivities

Solver fixes in `xfr_engine/institutional.py`, found by two independent reviews that enumerated the binary branches exactly: HiGHS with presolve could
return a false optimum (status 0, gap 0, objective above the minimum), the default MIP gap of 1e-4 could leave E* above its true value, and HiGHS accepts
binaries and bounds within 1e-6 of feasibility, which BIG = 50 turns into slack of up to 5e-5 in the big-M rows. Every MILP is now solved with and without
presolve, with zero relative gap; a candidate that is not integral or violates a bound by more than 1e-9 is polished (binaries fixed, the remaining LP
re-solved, near-fractional binaries tried at both values); if the polished LP ends above the HiGHS objective, the tolerance was hiding
another branch and all branches are enumerated (up to 12 binaries, T ≤ 6; above that, branches one or two flips away are tried and a
`RuntimeWarning` says the polish is not certified). The lower polished objective is kept. This replaces the v0.4.0 retry. The stage-1 solution
enters the cost stage as a candidate, and any E0 slack the cost stage needed is recorded in `folga_custo`. On 8,803 points enumerated exactly, E* and C*
are within 1e-6 of the exact values (a random draw of 2,500 final panel, shield and pre-existing-interest rows matches to 1e-9); HiGHS keeps an absolute gap of 1e-6, so that is the resolution of E*. The panel, the counterfactuals and every sensitivity were rerun with this solver (about 2.2 million rows): all have
status `ok`, the one v0.4.0 cost stage without a solution is now solved, one row of the regime-switch counterfactual closed the cost stage with E0 slack
of 1e-6, and E*(q) falls below E*(0) in 12 rows, by at most 9.2e-7, inside that resolution. In the tables published with v0.4.0, the changes are at most one
unit in the last printed digit: the share of Brazilian points with ISC > 0 drops by 0.1 point in some configurations of the three terciles
(for example 33.3% to 33.2% under `all_on`), the upper bound of the H1 interval goes from 0.1965 to 0.1966 in the full sample and from 0.2344
to 0.2345 in the 2020 stress subsample, the Brazilian break-even mean CLS under `no_loss_cap` in Table 5 goes from 0.0072 to 0.0071, the κ_I share of the break-even
CLS in Table 6A goes from −0.0000 to −0.0001, and no verdict changes. In the synthetic Experiment I, values move by at most 2e-9, and a few printed
cells at an exact half flip their last digit (0.5625 now prints as 0.562). The big-M guard covers taxable profit,
losses, deductible interest and JCP, and `substitution` returns status `erro_BIG` instead of aborting a run; no panel point reaches it. The
`no_dip_no_shield` counterfactual keeps the JCP ceiling on profit net of the line interest. In `experiment_I.py`, the tax channel is now the effect of switching the tax off: `by_channel` and
`interaction_residual` no longer count JCP on top of it, which changes them in the profit regime (CES tax channel 0.032, residual −0.105; NCS 0.037, −0.120).
`scripts/etapa2/sens_extra.py` regenerates, together with `sens_dip.py`, every panel sensitivity read by `agrega.py`, and these are new in `results/panel/tabelas.md`: pre-existing interest deductible
(`I0` column in `xfr_engine.panel`), the interest shield isolated by `no_dip_no_shield`, the channels without DIP, the JCP effect by loss state, the 0%/100% DIP row,
the DIP sweep in the NCS, and PF0 for the U.S. points without an observed balance. These analyses are complementary and were not pre-specified.

## Citation

See `CITATION.cff`. Please cite the software release together with the manuscript:

* **v0.4.1**: [10.5281/zenodo.24013092](https://doi.org/10.5281/zenodo.24013092)
* **v0.4.0**: [10.5281/zenodo.23979495](https://doi.org/10.5281/zenodo.23979495)
* **v0.3.0**: [10.5281/zenodo.23964137](https://doi.org/10.5281/zenodo.23964137)
* **v0.2.0**: [10.5281/zenodo.23955232](https://doi.org/10.5281/zenodo.23955232)
* **All versions** (resolves to the latest): [10.5281/zenodo.23955231](https://doi.org/10.5281/zenodo.23955231)

## License

MIT — see `LICENSE`.
