// magnitude mean-reversion — detector + range filter + fixed-ATR bracket
//
// Signal source: daily magnitude swings (2/2 fractal, >=3.5 ATR travel). The
// 2026-10-04 detector study found the swing-structure/pullback pattern machinery
// adds nothing over the magnitude threshold, so those nodes are gone. Direction
// is emitted by MagnitudeReversionSignal (fade the freshly-confirmed pivot) and
// risk is the study geometry via AtrBracketRisk (a fixed 1.5 / 3.0 ATR bracket),
// not the structural RiskEngine.
//
// Fact-name convention: a reference field is named after the fact the consumer
// requires, so the `atr_14` on `manage_risk`/`atr_risk` feeds the `atr_14` fact.
// The magnitude producer and range filter pin stable (dot-free) `fact_name`s so
// the signal's default fact keys resolve without any reference plumbing.

daily := timeframe { resolution: "1d" }
weekly := timeframe { resolution: "1w" }

// weekly ATR series: the detector measures pivot travel in ATRs of this series.
atr_14_series := atr_series { period: 14, lookback: 150, timeframe: weekly }

// daily magnitude swings: 2/2 fractal, >=3.5 ATR travel.
swing1d_mag := magnitudeswings {
  left_bars: 2,
  right_bars: 2,
  min_travel_atr: 3.5,
  atr_14_series: atr_14_series,
  fact_name: "magnitude_swings"
}

// where the latest daily swing sits in the trailing 12-week range; shorts above
// the range high are the losing case the study isolated
rangepos := rangeposition {
  swing_key: "magnitude_swings",
  higher_timeframe: "1w",
  range_bars: 12,
  confirmation_lag: 2,
  fact_name: "range_position"
}

// daily ATR for the fixed bracket
atr_14 := atr { period: 14 }

// fade the freshly-confirmed daily magnitude pivot, gating shorts at/above the
// trailing range high (w_pos >= short_range_max)
signal := magnitude_reversion {
  confirm_lag: 2,
  enable_short_filter: true,
  short_range_max: 0.8
}

// study geometry: symmetrical ATR bracket off the signal close, stop 1.5 ATR,
// target 3.0 ATR (RR 2.0), sized at risk_pct
risk := atr_risk {
  atr_14: atr_14,
  stop_atr: 1.5,
  target_atr: 3.0,
  risk_pct: 1.0,
  max_hold_days: 15
}
