# 094: Parallel instrument analysis in PortfolioBacktester

**Status:** pending
**Epic:** performance
**Priority:** high

## Description

`PortfolioBacktester.run_with_progress` evaluates instruments sequentially (`portfolio.py:130`). Each instrument's `graph.run_with_evidence(view)` is independent — it reads only from its own `MarketStore` and produces its own `facts` dict. The only shared state is the `TradeBook` during position resolution (`_fill_and_resolve`, `_try_submit`), which is serial by design.

With 30 instruments, this means 30 sequential analysis passes per frame. Using `concurrent.futures.ProcessPoolExecutor` (or `ThreadPoolExecutor` — the work is CPU-bound but the GIL is released during tuple/dict operations) we can analyze all instruments in parallel.

Key constraint: `AnalysisGraph` instances are per-bundle (shared), but analyzers are stateless between frames (they read from `view`, not from mutable state). So each worker can hold its own `AnalysisGraph` clone or the same graph reference is safe if analyzers don't mutate.

## Design

1. At `PortfolioBacktester.__init__`, create a worker pool (size = `min(len(instruments), os.cpu_count())`)
2. In the inner loop (`portfolio.py:130-155`), collect `(instrument, store, aligned)` tuples for instruments that need re-evaluation
3. Submit a batch: `executor.map(_analyze_one, tasks)` where `_analyze_one(instrument, store, aligned, window_size, bundle_graph)` returns a lightweight result (facts dict, evidence, emitted signals)
4. Collect results back in the main loop, build `_CursorEvaluation` objects as before
5. Position resolution (`_fill_and_resolve`, `_try_submit`) stays serial in the main thread
6. Pool shutdown on completion or error

The `_analyze_one` function must be picklable (module-level, not a closure). `AnalysisGraph` and its analyzers are plain Python objects — safe to serialize or reference-share via `cloudpickle` if needed, but `concurrent.futures.ProcessPoolExecutor` uses pickle by default.

Simpler first step: use `ThreadPoolExecutor` — avoids pickle issues entirely since threads share memory. The GIL contention is minimal because the hot path is dict/tuple operations that release the GIL intermittently, and the actual numerical work (EMA/ATR computation) is pure Python that benefits from thread interleaving.

## Files

- `backtesting/portfolio.py` — add pool creation, `_analyze_one` free function, parallel map in inner loop

## Testing

**IMPORTANT:** Run `poetry run pytest` (full suite, NO `-x`). Collect ALL failures
in one pass, fix them all, then run again to verify. Do NOT use `pytest -x` —
it wastes time fixing one failure at a time and risks timeout.

## Acceptance Criteria

- [ ] `PortfolioBacktester` uses a thread/process pool for per-instrument analysis
- [ ] Output is identical to serial execution (same trades, same facts, same frames) — deterministic ordering preserved
- [ ] Pool size configurable via constructor param (default: `min(instruments, cpu_count)`)
- [ ] Pool cleanup on completion (no resource leak)
- [ ] Single-instrument backtests unaffected (no pool overhead for 1 instrument)
- [ ] `poetry run pytest` — full suite green

## Related

- `backtesting/portfolio.py:130-155` — serial instrument evaluation loop
- `analysis/graph.py:89-112` — `run_with_evidence` (stateless, safe to parallelize)
- `backtesting/portfolio.py:157-171` — position resolution (stays serial)
