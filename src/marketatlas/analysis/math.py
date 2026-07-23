def compute_ema(prices: tuple[float, ...], period: int) -> float:
    if not prices:
        return 0.0
    period = min(period, len(prices))
    if period < 2:
        return prices[-1]
    k = 2.0 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = price * k + ema * (1 - k)
    return ema
