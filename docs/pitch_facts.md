# Pitch facts — have these ready

## Estate format

We read **either** `estate.db` or `estate_csv.zip`; both give identical decisions. For the evaluation, hand us whichever form is easier. The company RFC is optional.

## Results slide (held-out, offline)

Tuning seeds: **101, 202, 303, 404, 505**. Reporting seeds: **812007, 823009, 834011, 845013, 856017**. The sets are disjoint and the code asserts it (`tools/official_evaluate.py`).

Records-only estates (prose contracts, company not in vendors):

| seed | schemes_planted | schemes_found | recall_pct | decoys_planted | decoys_accused | false_accusation_rate_pct | peso_claimed | peso_actual | peso_reconciles | llm_calls | mxn_cost | wall_clock_s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 812007 | 5 | 5 | 100.0 | 10 | 0 | 0.0 | 2282672.17 | 2282672.17 | True | 0 | 0.0 | 0.0375 |
| 823009 | 2 | 2 | 100.0 | 10 | 0 | 0.0 | 216700.0 | 216700.0 | True | 0 | 0.0 | 0.038 |
| 834011 | 3 | 3 | 100.0 | 10 | 0 | 0.0 | 713606.34 | 713606.34 | True | 0 | 0.0 | 0.0319 |
| 845013 | 4 | 4 | 100.0 | 10 | 0 | 0.0 | 433404.85 | 433404.85 | True | 0 | 0.0 | 0.0365 |
| 856017 | 5 | 5 | 100.0 | 10 | 0 | 0.0 | 421481.6 | 421481.6 | True | 0 | 0.0 | 0.0323 |
| TOTAL | 19 | 19 | 100.0 | 50 | 0 | 0.0 | 4067864.96 | 4067864.96 | True | 0 | 0.0 | 0.1762 |

Say this with it:
- Our first reporting set produced **one false accusation** (director-approved split orders). We fixed the defect, moved those seeds to development and froze a new set. Both runs are in `docs/verification.md`.
- The estates come from our own generator, so these numbers show the method works on the patterns we modeled. They are not a claim about your estates.

Regenerate: `python -m tools.official_evaluate --output tmp/official-evaluation` → `results.csv`, `results.md`.

## Three numbers

| | Offline (default) | AI scheduling mode |
|---|---|---|
| LLM calls | 0 | counted per run in `run_metadata.llm_calls` |
| MXN cost | 0.00 | provider-reported USD × supplied USD/MXN rate; export blocked if billing is missing |
| Wall-clock | ≈0.04 s per estate (investigation), shown in every case-file header | measured per run |

## Live proofs (each under ten seconds, from the record)

- **A constraint in code:** open `forensic_auditor/official/audit.py`. The top block lists every threshold (e.g. `KICKBACK_WINDOW_DAYS = 45`, `ROUND_TRIP_MIN_RETURN_PERCENT = 80`, `PESO_TOLERANCE_PERCENT = 2`). The same values appear in the case JSON under `detector_settings`.
- **A lead declined:** open the case file's *Leads not pursued* section. Each entry shows the signal, the reason, the tools called and who closed it (investigator, challenger or validator).
- **Why a finding survived:** each finding's *Adversarial review* table lists every challenger argument and the record check that defeated it.
- **"What if the employee just banks at the same institution?"** Kickback requires an exact 18-digit CLABE match. The challenger row shows the account holders on that CLABE and its bank code. There is a test for this case.
- **Determinism:** run twice with `--fresh`; the printed `decision_fingerprint` matches. The header shows the same fingerprint.

## Replay with the network off (rehearse)

1. `python -m forensic_auditor.official run ESTATE --seed N --output tmp/demo-case` (keep `tmp/demo-case.replay.zip`).
2. Disable Wi-Fi / unplug the network.
3. `python -m forensic_auditor.official replay tmp/demo-case.replay.zip --output tmp/replayed` → same JSON and HTML, zero network calls. In the UI, use *Replay completed run*.

## What we cut, and why

- **XML CFDI signature checks and live SAT lookups.** The judge estate supplies `efos_list`, and a network dependency would break offline replay.
- **Reading contract prose with an LLM.** Its interpretations are not deterministic or auditable; prose is kept as evidence but never treated as a rule.
- **LLM-written findings.** The model may only schedule review steps over aliases; accusations come from deterministic predicates so they validate and replay exactly.
- **Overbilling on real deliveries, cash kickbacks, relatives' accounts.** These are not visible in eight tables without speculative inference; they are listed as undetectable in every case file.
- **Durable multi-user storage.** It's a local prototype; the case is kept as JSON, HTML and a replay ZIP.
