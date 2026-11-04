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
| Tests of Section 9, Appendix A.1 and the directional form | `tests/` (26 automated cases; 36 with the institutional layer) |
| Explanation layer (binding constraints, blocked instruments) | `Solution.binding` |

Solver: linear programming with HiGHS (`scipy.optimize.linprog`). Dependencies: `numpy`, `scipy`;
`pytest` for the tests.

## Usage

```bash
pip install -e .
python -m xfr_engine.example_section9                 # reproduces Section 9 and the variants
python -m xfr_engine.example_section9 --json results/section9.json
pip install pytest                                    # only needed for the tests
pytest -q                                             # 26 tests
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
pytest -q                                           # 36 tests
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

## Citation

See `CITATION.cff`. Please cite the software release together with the manuscript:

* **v0.2.0**: [10.5281/zenodo.23955232](https://doi.org/10.5281/zenodo.23955232)
* **All versions** (resolves to the latest): [10.5281/zenodo.23955231](https://doi.org/10.5281/zenodo.23955231)

## License

MIT — see `LICENSE`.
