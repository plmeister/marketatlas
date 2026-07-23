# Strategy-Aware Backtester

**Epic:** strategy

## Problem

Current `Backtester` replays candles and stores frames but has no strategy evaluation. Need to integrate signals + risk layer so the backtester produces trade candidates alongside frames. Must support multiple strategies simultaneously, track balance through wins/losses, and produce comparable performance metrics.

## Goal

Backtester loads one or more strategies from config, compiles them into a single analysis graph, evaluates signals at each frame, runs risk engine, and produces a `TradeBook` that tracks all trades with their source strategy, running balance, and win/loss record. All starting from a nominal 1000 currency balance.

## Design

### 1. TradeBook

File: `src/marketatlas/strategy/tradebook.py`

```python
@dataclass(frozen=True)
class TradeOutcome:
    entry_timestamp: datetime
    exit_timestamp: datetime | None    # None if still open at backtest end
    candidate: TradeCandidate
    signal: TradeSignal
    source_strategy: str               # name of strategy that produced this
    pnl: float | None                  # realized P&L (None if open)
    result: str | None                 # "win" / "loss" / "breakeven" / None

class TradeBook:
    def __init__(self, initial_balance: float = 1000.0) -> None:
        self._initial_balance = initial_balance
        self._balance = initial_balance
        self._trades: list[TradeOutcome] = []
        self._open_trade: TradeOutcome | None = None
        self._pending_order: TradeCandidate | None = None  # order awaiting fill

    @property
    def balance(self) -> float: ...
    @property
    def initial_balance(self) -> float: ...
    @property
    def trades(self) -> tuple[TradeOutcome, ...]: ...
    @property
    def win_count(self) -> int: ...
    @property
    def loss_count(self) -> int: ...
    @property
    def win_rate(self) -> float: ...        # wins / (wins + losses)
    @property
    def total_pnl(self) -> float: ...       # balance - initial_balance
    @property
    def max_drawdown(self) -> float: ...    # worst peak-to-trough
    @property
    def has_no_open_trade(self) -> bool: ...
    @property
    def has_pending_order(self) -> bool: ...

    def submit_order(self, candidate: TradeCandidate, signal: TradeSignal,
                     source: str, signal_timestamp: datetime) -> None:
        """Signal fired. Order placed after close. Pending fill at next open."""

    def fill_order(self, open_price: float, timestamp: datetime) -> None:
        """Fill pending order at the open of this candle.
        Updates entry to actual fill price. Recomputes stop/target if needed."""

    def close_trade(self, exit_price: float, timestamp: datetime) -> None:
        """Close the open trade at exit_price. Update balance."""

    def resolve_at_cursor(self, candle: Candle) -> None:
        """Check if open trade hit stop or target on this candle.
        Only checks candle.high and candle.low."""
```

### 2. Trade Resolution Logic

**Swing trading model:** Orders placed after market close. Entry fills at the open of the next candle.

**Per-frame lifecycle:**

```
Cursor N:
  1. Run analysis graph → facts
  2. Store frame
  3. Fill any pending order at candle.open (this becomes the entry)
  4. Resolve open trade — check candle.high/low against stop/target
  5. If no open trade: evaluate signals, submit pending order
```

**Fill logic (step 3):**
```python
def fill_order(self, open_price: float, timestamp: datetime) -> None:
    if self._pending_order is None:
        return
    candidate = self._pending_order
    # Actual entry is the open of this candle
    self._open_trade = TradeOutcome(
        entry_timestamp=timestamp,
        exit_timestamp=None,
        candidate=candidate,  # entry = open_price (overridden from signal)
        signal=..., source=..., pnl=None, result=None,
    )
    self._pending_order = None
```

**Resolution logic (step 4):**
```python
def resolve_at_cursor(self, candle: Candle, max_hold_days: int = 10) -> None:
    if self._open_trade is None:
        return
    c = self._open_trade.candidate

    # Check max hold period
    days_held = (candle.timestamp - self._open_trade.entry_timestamp).days
    if days_held >= max_hold_days:
        self.close_trade(candle.close, candle.timestamp)
        return

    # Check stop/target
    if c.direction == TrendDirection.BULLISH:
        if candle.low <= c.stop:
            self.close_trade(c.stop, candle.timestamp)
        elif candle.high >= c.target:
            self.close_trade(c.target, candle.timestamp)
    else:  # bearish
        if candle.high >= c.stop:
            self.close_trade(c.stop, candle.timestamp)
        elif candle.low <= c.target:
            self.close_trade(c.target, candle.timestamp)
```

**Critical constraint:** Signal fires at cursor N (based on close of N). Order fills at open of N+1. Resolution starts at N+1. No same-candle resolution possible.

### 3. Multi-Strategy Support

File: `src/marketatlas/strategy/strategy.py`

```python
class Strategy:
    def __init__(self, name: str, config: StrategyConfig) -> None:
        self._name = name
        self._config = config
        self._graph = self._build_graph()
        self._signals = self._build_signals()
        self._risk = self._build_risk()

    @property
    def name(self) -> str: ...

    def evaluate(self, view: MarketView, facts: dict[FactKey, Fact]) -> list[TradeSignal]:
        """Evaluate all signals, return any that fire."""
```

**Multi-strategy compilation:**

```python
class StrategyBundle:
    """Combines multiple strategies into a single analysis graph."""

    def __init__(self, strategies: list[Strategy]) -> None:
        self._strategies = strategies
        self._graph = self._merge_graphs()  # single AnalysisGraph, deduped
        self._tradebook = TradeBook()

    def _merge_graphs(self) -> AnalysisGraph:
        """Merge all analyzer lists, deduplicate by FactKey.
        Two strategies requesting the same EMA(20) → only one EMAAnalyzer runs."""

    @property
    def tradebook(self) -> TradeBook: ...

    def evaluate_all(self, view: MarketView, facts: dict[FactKey, Fact]) -> list[tuple[str, TradeSignal]]:
        """Evaluate all strategies, return (strategy_name, signal) pairs."""
```

### 4. Refactored Backtester

File: `src/marketatlas/backtesting/backtester.py` (modify)

```python
class Backtester:
    def __init__(
        self,
        store: MarketStore,
        bundle: StrategyBundle,
        window_size: int = 100,
        max_hold_days: int = 10,
    ) -> None: ...

    def run(self) -> tuple[FrameStore, TradeBook]:
        frame_store = FrameStore()
        tradebook = self._bundle.tradebook

        for cursor in range(self._window_size, len(self._store)):
            view = MarketView(self._store, cursor, self._window_size)
            facts = self._bundle._graph.run(view)
            evidence = self._collect_evidence(facts)
            frame = AnalysisFrame(
                timestamp=view.current.timestamp,
                candle=view.current,
                facts=dict(facts),
                evidence=evidence,
            )
            frame_store.append(frame)

            # Step 3: Fill pending order at this candle's open
            tradebook.fill_order(view.current.open, view.current.timestamp)

            # Step 4: Resolve open trade (check stop/target on this candle)
            tradebook.resolve_at_cursor(view.current, self._max_hold_days)

            # Step 5: If no open trade and no pending, evaluate signals
            if tradebook.has_no_open_trade and not tradebook.has_pending_order:
                for name, signal in self._bundle.evaluate_all(view, facts):
                    candidate = self._bundle._strategies[name]._risk.evaluate(
                        signal, facts, view,
                    )
                    if candidate is not None:
                        tradebook.submit_order(
                            candidate, signal, name, view.current.timestamp,
                        )
                        break  # one pending order at a time

        # Close any open trade at backtest end
        if tradebook.has_no_open_trade is False:
            tradebook.close_trade(
                self._store[self._window_size + len(frame_store) - 1].close,
                self._store[self._window_size + len(frame_store) - 1].timestamp,
            )

        return frame_store, tradebook
```

### 5. Trade Evaluation Order (No Look-Ahead)

Per frame, strict order:
1. Run analysis graph → facts
2. Store frame
3. **Fill pending order** — entry price = this candle's open (order was placed after previous close)
4. **Resolve open trade** — check if this candle's high/low hit stop or target
5. **Evaluate signals** — only if no open trade and no pending order
6. **Submit pending order** — signal fires, order will fill at next candle's open

This models real swing trading:
- Signal fires at close of candle N
- Order placed after close
- Fills at open of candle N+1
- Can only resolve from candle N+1 onward

### 6. Read-Ahead Safety

- Analysis graph runs on single frame only
- Signals evaluate single-frame facts only
- Risk engine uses single-frame S/R + ATR
- TradeBook.resolve_at_cursor only checks `candle` (current frame)
- Trade opened at cursor N → first checked for resolution at cursor N+1
- No trade can be opened retroactively

### 7. Performance Metrics

```python
@property
def summary(self) -> dict:
    return {
        "initial_balance": self.initial_balance,
        "final_balance": self.balance,
        "total_pnl": self.total_pnl,
        "total_return_pct": (self.total_pnl / self.initial_balance) * 100,
        "total_trades": self.win_count + self.loss_count,
        "wins": self.win_count,
        "losses": self.loss_count,
        "win_rate": self.win_rate,
        "max_drawdown": self.max_drawdown,
        "by_strategy": self._strategy_breakdown(),
    }

def _strategy_breakdown(self) -> dict[str, dict]:
    """Per-strategy win/loss/pnl stats."""
```

### 8. CLI Integration

```
marketatlas run --strategy strategies/pullback_4swing.yaml --symbol BTC-USD --timeframe 1d
marketatlas run --strategy strategies/a.yaml --strategy strategies/b.yaml --symbol BTC-USD
```

### 9. Tests

**Single strategy:**
- Backtest produces FrameStore + TradeBook
- TradeBook starts at 1000 balance
- Winning trade increases balance
- Losing trade decreases balance
- Win/loss counts correct

**Multi-strategy:**
- Two strategies compiled into single graph
- Duplicate analyzers deduped (one EMA(20), not two)
- Trades annotated with source strategy name
- Per-strategy breakdown available

**Trade resolution:**
- Trade opened, next candle hits stop → closed at stop, loss recorded
- Trade opened, next candle hits target → closed at target, win recorded
- Trade open at backtest end → recorded as open (no P&L)
- Only one trade open at a time

**Balance tracking:**
- Balance starts at 1000
- After win: balance increases by reward
- After loss: balance decreases by risk
- New trades sized based on current balance (not initial)

**No look-ahead:**
- Trade at cursor N opened based on candle N data
- Resolution only checks candles at cursor N+1 onward
- Adding future candles does not change past trade decisions

## Evidence

- TradeBook correctly tracks balance through sequence of trades
- Multi-strategy deduplication works
- Trade resolution only uses current candle's high/low
- One trade at a time enforced
- Per-strategy performance breakdown available
