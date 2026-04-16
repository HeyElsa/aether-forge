"""Tests for DeFi safety helpers."""

from unittest.mock import MagicMock, patch

from aether_forge.defi_safety import (
    ExposureTracker,
    SwapQuote,
    check_position_health,
    check_slippage,
    simulate_tx,
)

# ---------------------------------------------------------------------------
# Slippage
# ---------------------------------------------------------------------------


def test_slippage_safe_quote_passes():
    quote = SwapQuote(
        token_in="ETH", token_out="USDC",
        amount_in=10**18, amount_out=2300_000_000,
        min_amount_out=2277_000_000,  # 1% slippage
        price_impact_pct=0.5,
    )
    result = check_slippage(quote, max_slippage_pct=1.0, max_price_impact_pct=3.0)
    assert result.safe


def test_slippage_excessive_min_out_rejected():
    quote = SwapQuote(
        token_in="ETH", token_out="USDC",
        amount_in=10**18, amount_out=2300_000_000,
        min_amount_out=2000_000_000,  # 13% slippage tolerance — too loose
        price_impact_pct=0.5,
    )
    result = check_slippage(quote, max_slippage_pct=1.0)
    assert not result.safe
    assert "slippage" in result.reason


def test_slippage_high_price_impact_rejected():
    quote = SwapQuote(
        token_in="ETH", token_out="LOW_LIQ",
        amount_in=10**18, amount_out=1000_000,
        min_amount_out=990_000,
        price_impact_pct=8.0,  # 8% price impact
    )
    result = check_slippage(quote, max_price_impact_pct=3.0)
    assert not result.safe
    assert "price impact" in result.reason


def test_slippage_zero_amount_rejected():
    quote = SwapQuote(
        token_in="ETH", token_out="USDC",
        amount_in=10**18, amount_out=0, min_amount_out=0,
        price_impact_pct=0.0,
    )
    result = check_slippage(quote)
    assert not result.safe


# ---------------------------------------------------------------------------
# Exposure
# ---------------------------------------------------------------------------


def test_exposure_tracker_concentration():
    tracker = ExposureTracker(max_per_protocol_pct=30.0, max_per_token_pct=50.0)
    tracker.record_position("aave", 5000)
    tracker.record_position("compound", 3000)
    tracker.record_position("uniswap", 2000)

    assert tracker.total_value() == 10000
    assert tracker.concentration_pct("aave") == 50.0


def test_exposure_check_allowed_protocol():
    tracker = ExposureTracker(max_per_protocol_pct=30.0)
    tracker.record_position("aave", 1000)
    tracker.record_position("compound", 1000)
    # Adding $500 to aave: future = 1500 / 2500 = 60% — over limit
    allowed, reason = tracker.check_concentration("aave", 500, is_protocol=True)
    assert not allowed
    assert "30.0%" in reason


def test_exposure_check_token_limit():
    tracker = ExposureTracker(max_per_token_pct=50.0)
    tracker.record_position("ETH", 4000)
    tracker.record_position("USDC", 6000)
    # Adding $1000 to ETH: future = 5000 / 11000 = 45.5% — ok
    allowed, _ = tracker.check_concentration("ETH", 1000)
    assert allowed
    # Adding $10000 to ETH: future = 14000 / 20000 = 70% — over
    allowed, _ = tracker.check_concentration("ETH", 10000)
    assert not allowed


# ---------------------------------------------------------------------------
# Position health
# ---------------------------------------------------------------------------


def test_position_health_no_debt():
    h = check_position_health(collateral_usd=10000, debt_usd=0)
    assert h.health_factor == float("inf")
    assert not h.at_risk


def test_position_health_safe():
    h = check_position_health(collateral_usd=10000, debt_usd=4000, liquidation_threshold=0.83)
    # 10000 * 0.83 / 4000 = 2.075
    assert h.health_factor > 2.0
    assert not h.at_risk


def test_position_health_at_risk():
    h = check_position_health(collateral_usd=10000, debt_usd=7500, liquidation_threshold=0.83)
    # 10000 * 0.83 / 7500 = 1.107
    assert h.at_risk
    assert not h.critical


def test_position_health_critical():
    h = check_position_health(collateral_usd=10000, debt_usd=8000, liquidation_threshold=0.83)
    # 10000 * 0.83 / 8000 = 1.0375
    assert h.critical
    assert h.at_risk


# ---------------------------------------------------------------------------
# Tx simulation (mock RPC)
# ---------------------------------------------------------------------------


def test_simulate_tx_success():
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"jsonrpc":"2.0","id":1,"result":"0x1234"}'
    mock_response.__enter__ = lambda self: self
    mock_response.__exit__ = lambda *args: None
    with patch("urllib.request.urlopen", return_value=mock_response):
        result = simulate_tx(
            "https://example.com/rpc",
            from_address="0x1234",
            to_address="0x5678",
            data="0xabcd",
        )
    assert result.success
    assert result.return_data == "0x1234"


def test_simulate_tx_revert():
    mock_response = MagicMock()
    mock_response.read.return_value = (
        b'{"jsonrpc":"2.0","id":1,'
        b'"error":{"code":-32000,"message":"execution reverted: insufficient balance"}}'
    )
    mock_response.__enter__ = lambda self: self
    mock_response.__exit__ = lambda *args: None
    with patch("urllib.request.urlopen", return_value=mock_response):
        result = simulate_tx(
            "https://example.com/rpc",
            from_address="0x1234",
            to_address="0x5678",
            data="0xabcd",
        )
    assert not result.success
    assert "insufficient balance" in result.revert_reason
