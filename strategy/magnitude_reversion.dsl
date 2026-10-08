daily := timeframe { resolution: "1d" }
weekly := timeframe { resolution: "1w" }

atr_14_series := atr_series { period: 14, lookback: 150, timeframe: weekly }

swing1w := swings { lookback: 150, timeframe: weekly }
sr := sr { swing: swing1w, atr_14_series }

swing1d_mag := magnitudeswings { left_bars: 2, right_bars: 2, min_travel_atr: 3.5, atr_key: "atr_14_series", name: "magnitude_swings_3.5" }

rangepos := rangeposition {
  swing_key: swing1d_mag,
  higher_timeframe: weekly,
  range_bars: 12,
  confirmation_lag: 2
}

ema20 := ema { period: 20, timeframe: daily }
ema50 := ema { period: 50, timeframe: daily }
atr_14 := atr { period: 14 }
trend := trend { ema_20: ema20, ema_50: ema50, atr_14: atr_14 }

alternate := swingstructure { swing: swing1d_mag }
pullback := pullbackpattern { swing_structure: alternate, window_days: 1, retest: false }
signal := generate_signal { pullback_pattern: pullback, trend: trend, atr_14: atr_14, min_strength: 0.55 }

risk := manage_risk {
  atr_14: atr_14,
  sr: sr,
  swing: swing1d_mag,
  risk_pct: 1.0,
  min_rr: 1.0,
  max_rr: 6.0,
  max_stop_atr: 10.0,
  min_atr_pct: 0.4,
  max_atr_pct: 1.3,
  min_vol_ratio: 0.6,
  max_vol_ratio: 2.5,
  swing_buffer_atr: 0.5
}
