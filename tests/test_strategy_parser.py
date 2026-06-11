"""Tests for strategy file parsing."""

from aether_forge.strategy_parser import parse_strategy_file

SAMPLE_STRATEGY = """
# ETH Momentum Swing Strategy

## Entry Rules
- BUY when: ETH 30m momentum turns bearish-to-neutral AND price is below 20-period SMA
- SELL when: ETH 30m momentum turns bullish-to-neutral AND price is above 20-period SMA
- Position size: 0.05 ETH per trade

## Risk Management
- Max spread: 1.5% in normal volatility, 2.5% in high volatility
- Max 4 open orders at any time
- Stop loss: close all if drawdown exceeds 5%
- Max daily loss: $500

## Rebalance
- Check positions every 6 ticks
- Cancel stale orders older than 12 ticks

## Success Criteria
- Win rate above 45%
- Maximum drawdown below 8%
- Positive P&L per 24h period
"""


def test_extracts_spread() -> None:
    result = parse_strategy_file(SAMPLE_STRATEGY)
    assert result["parameters"]["spread_pct"] == 1.5


def test_extracts_high_vol_spread() -> None:
    result = parse_strategy_file(SAMPLE_STRATEGY)
    assert result["parameters"]["high_vol_spread_pct"] == 2.5


def test_extracts_position_size() -> None:
    result = parse_strategy_file(SAMPLE_STRATEGY)
    assert result["parameters"]["position_size"] == 0.05


def test_extracts_max_open_orders() -> None:
    result = parse_strategy_file(SAMPLE_STRATEGY)
    assert result["parameters"]["max_open_orders"] == 4


def test_extracts_stop_loss() -> None:
    result = parse_strategy_file(SAMPLE_STRATEGY)
    assert result["parameters"]["stop_loss_pct"] == 5.0


def test_extracts_max_daily_loss() -> None:
    result = parse_strategy_file(SAMPLE_STRATEGY)
    assert result["parameters"]["max_daily_loss_usd"] == 500.0


def test_extracts_rebalance_interval() -> None:
    result = parse_strategy_file(SAMPLE_STRATEGY)
    assert result["parameters"]["rebalance_interval_ticks"] == 6


def test_extracts_stale_order_timeout() -> None:
    result = parse_strategy_file(SAMPLE_STRATEGY)
    assert result["parameters"]["stale_order_ticks"] == 12


def test_extracts_tokens() -> None:
    result = parse_strategy_file(SAMPLE_STRATEGY)
    assert "ETH" in result["parameters"]["tokens"]


def test_extracts_entry_rules() -> None:
    result = parse_strategy_file(SAMPLE_STRATEGY)
    assert len(result["entry_rules"]) == 2
    assert result["entry_rules"][0]["action"] == "buy"
    assert result["entry_rules"][1]["action"] == "sell"
    assert "bearish" in result["entry_rules"][0]["condition"].lower()
    assert "bullish" in result["entry_rules"][1]["condition"].lower()


def test_extracts_win_rate() -> None:
    result = parse_strategy_file(SAMPLE_STRATEGY)
    assert result["success_metrics"]["min_win_rate"] == 0.45


def test_extracts_max_drawdown() -> None:
    result = parse_strategy_file(SAMPLE_STRATEGY)
    assert result["success_metrics"]["max_drawdown_pct"] == 8.0


def test_extracts_positive_pnl() -> None:
    result = parse_strategy_file(SAMPLE_STRATEGY)
    assert result["success_metrics"]["min_profit_per_tick"] == 0.0


def test_handles_empty_input() -> None:
    result = parse_strategy_file("")
    assert result["parameters"] == {}
    assert result["entry_rules"] == []
    assert result["success_metrics"] == {}


def test_handles_json_input() -> None:
    json_strategy = '{"parameters": {"spread_pct": 2.0}, "entry_rules": [], "success_metrics": {}}'
    result = parse_strategy_file(json_strategy)
    # Regex won't find much in JSON, that's fine
    assert isinstance(result["parameters"], dict)


def test_multi_token_extraction() -> None:
    content = "Trade BTC and ETH pairs, also monitor SOL for opportunities"
    result = parse_strategy_file(content)
    tokens = result["parameters"].get("tokens", [])
    assert "BTC" in tokens
    assert "ETH" in tokens
    assert "SOL" in tokens


# ---------------------------------------------------------------------------
# Parse-report coverage
# ---------------------------------------------------------------------------

OUT_OF_VOCABULARY_STRATEGY = """
# Delta-Neutral BTC Basis Capture

If perp-spot basis > 20 bps and 1h realized volatility is low: open 0.5 BTC
spot long and 0.5 BTC perp short. Exit both legs when basis < 10 bps or
funding flips negative.
"""


def test_parse_report_counts_extracted_rules() -> None:
    result = parse_strategy_file(SAMPLE_STRATEGY)

    report = result["parse_report"]
    assert report["entry_rules_extracted"] == 2
    assert report["parameters_extracted"] == len(result["parameters"])
    assert report["llm_assist_used"] is False


def test_parse_report_flags_zero_rule_extraction() -> None:
    result = parse_strategy_file(OUT_OF_VOCABULARY_STRATEGY)

    assert result["entry_rules"] == []
    assert result["parse_report"]["entry_rules_extracted"] == 0
