# REBASE REVIEW — epic/strategy onto main

Rebase completed 2026-09-07 (onto `ada90f5`). Decision record for human review.

## Commit 1 — `29ce16a` pullback strength gate → `1efcf4e`

### `backlog/done/105-pullback-strength-gate.md` — both added (add/add)
- **Conflict:** both branches independently created `backlog/done/105-*`.
  - main (`ada90f5`) = **completed** doc: `min_strength 0.55` via DSL, measured
    results, all requirement/test boxes checked.
  - `29ce16a` = planning doc: `min_strength 0.5→0.6` programmatic default, all
    boxes unchecked.
- **Resolution:** kept main's completed version. The planning doc is superseded
  by the measured/completed state recorded on main.
- **Note (intent preserved on the code side):** the epic commit's actual code
  change (`pullback_signal.py` default `min_strength 0.5→0.6`) applied cleanly
  on top of main and is preserved in the replayed commit. The two branches took
  different implementation paths for the same backlog (main: DSL `swing.dsl`
  floor 0.01→0.55, uncommitted; epic: programmatic default 0.5→0.6). Both now
  coexist; epic's code-level gate and main's doc tell slightly different
  stories (0.55 DSL vs 0.6 default). **Not reconciled — human check.**
- **Uncertainty:** whether `0.6` programmatic default + `0.55` DSL floor on
  main are consistent by design or a drift. I did not alter either.

## Commit 2 — `ecbbf2e` SR-anchored target sizing → `9f9596c`

main (`ada90f5`) and epic/strategy independently implemented backlog 106 with
**different designs**. Rebase replay conflicted on 3 files.

### `backlog/done/106-sr-anchored-target-sizing.md` — rename/delete + add/add
- main moved `available/106` → `done/106` with **completed** measured doc
  (A=13 trades +$4050.20, B=0 trades, root cause: weekly-cluster SR reach).
- epic's commit carried the same rename with the **planning** doc.
- **Resolution:** kept main's completed doc (same pattern as 105).

### `src/marketatlas/strategy/risk.py` — content conflict (diverge)
Two independent implementations of `anchor_sr`/`max_anchor_atr`:

| Aspect | main (`_find_anchor` + `_anchor_level_...`) | epic `_anchor_level` + `_anchor_failure_info` |
|---|---|---|
| Anchor lookup | nearest qualifying level in window | first qualifying level in window order |
| Buffer check (proximity) | kept in `_find_valid_rr` | lifted in anchor mode (target meant to hug level) |
| Rejection evidence | gate after RR found: "no S/R anchor within N ATR beyond target" | merged into no-valid-RR branch with zone + nearest-level info |
| Accepted evidence | "S/R anchor: {type} {price} (N ATR beyond target)" | "SR anchor: target sits below {type}@{price} (N ATR)" |

- **Resolution:** kept **main's** implementation. Defaults (`anchor_sr=False`)
  are behavior-identical on both sides, so the replay's code change becomes a
  no-op. main's version is the canonical committed state (tests + doc already
  landed). epic's design divergences (lifted buffer check, first-vs-nearest
  anchor) are **dropped**, not merged.
- **Uncertainty:** epic's design *may* be a deliberate refinement (hug-an-S/R
  target intent per backlog 106 wording). If so, the dropped buffer-lift is a
  lost behavior. Human decide whether to re-port it onto main's helper.

### `tests/test_risk_engine.py` — content conflict (diverge)
Each branch added `test_anchor_sr_*` tests pinning its own evidence strings and
helper behavior.
- **Resolution:** kept main's tests (match kept implementation). epic's 119
  test lines dropped.

### `WORKLOG.md` — non-conflicting, auto-merged, **reverted by me**
epic's WORKLOG entry described the **dropped** design ("buffer check is
lifted…nearest level"). I reverted `WORKLOG.md` to HEAD so the changelog does
not describe code that does not exist. Main has no 106 WORKLOG entry at all —
**human may want to add one reflecting the kept implementation.**

### STATUS.md, tests/test_ab.py, tests/test_ast_compiler.py,
### tests/test_ast_constructors.py, tests/test_ast_param_schema.py — kept
epic's DSL-wiring tests (`anchor_sr`/`max_anchor_atr` flow through
`manage_risk` → `RiskEngine` params, `--ab` toggle). They pass against main's
kept `RiskEngine.__init__` signature. STATUS entry wording is generic enough to
match either implementation. All kept.

## Verification
- `pytest -m tier1` after resolution: 287 passed.
- `test_ab.py test_ast_compiler.py test_ast_constructors.py test_ast_param_schema.py`: 114 passed.
- `git rebase --continue` succeeded; `git status` clean; no `uv.lock`.
- ruff/mypy not run on the (unchanged on both sides, post-resolution) risk.py —
  code is byte-identical to main's committed `ada90f5` risk.py, which raced
  clean upstream.

## Open items for the human
1. 105: 0.6 programmatic default (epic) vs 0.55 DSL floor (main doc) — reconcile intent.
2. 106: epic's buffer-lift + first-anchor design dropped in favor of main's
   nearest-anchor design — confirm that is acceptable or re-port.
3. WORKLOG.md has no 106 entry (dropped). Add one for the kept implementation if wanted.