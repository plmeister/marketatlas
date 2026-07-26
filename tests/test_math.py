from marketatlas.analysis.math import compute_ema


class TestComputeEma:
    def test_empty_returns_zero(self) -> None:
        assert compute_ema((), 10) == 0.0

    def test_single_price_returns_last(self) -> None:
        assert compute_ema((42.0,), 10) == 42.0

    def test_period_one_returns_last(self) -> None:
        assert compute_ema((1.0, 2.0, 3.0), 1) == 3.0

    def test_period_equals_length(self) -> None:
        prices = (10.0, 20.0, 30.0)
        assert compute_ema(prices, 3) == 20.0

    def test_period_greater_than_length(self) -> None:
        prices = (10.0, 20.0)
        assert compute_ema(prices, 5) == 15.0

    def test_constant_prices(self) -> None:
        prices = (100.0,) * 20
        assert compute_ema(prices, 10) == 100.0

    def test_known_sequence(self) -> None:
        prices = (1.0, 2.0, 3.0, 4.0, 5.0)
        result = compute_ema(prices, 3)
        k = 2.0 / (3 + 1)
        sma = (1.0 + 2.0 + 3.0) / 3
        ema = sma
        for p in (4.0, 5.0):
            ema = p * k + ema * (1 - k)
        assert abs(result - ema) < 1e-10

    def test_two_prices(self) -> None:
        assert compute_ema((10.0, 20.0), 2) == 15.0

    def test_monotonic_increase(self) -> None:
        prices = tuple(float(i) for i in range(1, 51))
        ema = compute_ema(prices, 10)
        assert ema > prices[9]

    def test_negative_prices(self) -> None:
        prices = (-10.0, -5.0, 0.0)
        result = compute_ema(prices, 2)
        assert result < 0.0
