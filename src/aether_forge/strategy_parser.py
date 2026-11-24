"""Parse strategy files (English/markdown/JSON) into structured parameters.

Extracts trading parameters from human-readable strategy descriptions.
Uses regex patterns for reliable extraction + optional LLM for deeper parsing.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def parse_strategy_file(content: str, *, llm_model: Any = None) -> dict[str, Any]:
    """Parse a strategy file into structured strategy.json parameters.

    Tries regex extraction first (always works), then optionally uses
    an LLM to extract anything the regex missed.

    Returns a dict matching the strategy.json schema.
    """
    # Start with defaults
    result = {
        "parameters": {},
        "entry_rules": [],
        "success_metrics": {},
    }

    # Phase 1: Regex extraction (fast, reliable)
    result["parameters"] = _extract_parameters(content)
    result["entry_rules"] = _extract_entry_rules(content)
    result["success_metrics"] = _extract_success_metrics(content)

    # Phase 2: LLM extraction (optional, fills gaps)
    llm_assist_used = False
    if llm_model is not None:
        try:
            llm_result = _llm_extract(content, llm_model)
            result = _merge_results(result, llm_result)
            llm_assist_used = True
        except Exception as error:
            logger.debug("LLM strategy parsing failed: %s", error)

    # Coverage report so callers can tell extraction from silent fallback.
    result["parse_report"] = {
        "parameters_extracted": len(result["parameters"]),
        "entry_rules_extracted": len(result["entry_rules"]),
        "success_metrics_extracted": len(result["success_metrics"]),
        "llm_assist_used": llm_assist_used,
    }

    logger.info(
        "Strategy parsed: %d parameters, %d entry rules, %d success metrics",
        len(result["parameters"]),
        len(result["entry_rules"]),
        len(result["success_metrics"]),
    )
    return result


# ---------------------------------------------------------------------------
# Regex-based extraction
# ---------------------------------------------------------------------------

def _extract_parameters(content: str) -> dict[str, Any]:
    """Extract numeric parameters from strategy text."""
    params: dict[str, Any] = {}
    lower = content.lower()

    # Spread
    m = re.search(r"(?:spread|spread_pct)[:\s]*(\d+\.?\d*)%?\s*(?:in\s+normal|default)?", lower)
    if m:
        params["spread_pct"] = float(m.group(1))

    # High volatility spread
    m = re.search(r"(\d+\.?\d*)%\s*(?:in\s+high\s+vol|high\s+volatility|volatile)", lower)
    if m:
        params["high_vol_spread_pct"] = float(m.group(1))

    # Position size (ETH)
    m = re.search(r"(?:position\s*(?:size)?|trade|order)[:\s]*(\d+\.?\d*)\s*(?:eth|btc|sol)", lower)
    if m:
        params["position_size"] = float(m.group(1))

    # Position size (%)
    m = re.search(r"(?:position\s*(?:size)?)[:\s]*(\d+\.?\d*)%", lower)
    if m:
        params["position_size_pct"] = float(m.group(1))

    # Max open orders — "Max 4 open orders" or "max_open_orders: 4"
    m = re.search(r"(?:max|maximum)\s+(\d+)\s+(?:open\s+)?orders?", lower)
    if not m:
        m = re.search(r"(?:max|maximum)\s*(?:open\s*)?orders?[:\s]+(\d+)", lower)
    if m:
        params["max_open_orders"] = int(m.group(1))

    # Momentum threshold
    m = re.search(r"momentum\s*(?:threshold|signal|strength)[:\s]*(\d+\.?\d*)", lower)
    if m:
        params["momentum_threshold"] = float(m.group(1))

    # Rebalance interval — "every 6 ticks" or "check positions every 6 ticks"
    m = re.search(r"(?:rebalance|check)\s*(?:positions?\s*)?(?:every|interval)[:\s]*(\d+)\s*(?:tick|period|interval)", lower)
    if m:
        params["rebalance_interval_ticks"] = int(m.group(1))

    # Max daily loss
    m = re.search(r"(?:max|maximum)\s*(?:daily\s*)?loss[:\s]*\$?(\d+\.?\d*)", lower)
    if m:
        params["max_daily_loss_usd"] = float(m.group(1))

    # Stop loss
    m = re.search(r"(?:stop\s*loss|drawdown\s*(?:exceeds|>|limit))[:\s]*(\d+\.?\d*)%", lower)
    if m:
        params["stop_loss_pct"] = float(m.group(1))

    # Tokens
    tokens = set()
    for token_match in re.finditer(r'\b(ETH|BTC|SOL|CBBTC|WBTC|AVAX|MATIC|LINK|UNI|AAVE)\b', content):
        tokens.add(token_match.group(1))
    if tokens:
        params["tokens"] = sorted(tokens)

    # Volatility multiplier
    m = re.search(r"volatility\s*(?:multiplier|factor)[:\s]*(\d+\.?\d*)", lower)
    if m:
        params["volatility_multiplier"] = float(m.group(1))

    # Stale order timeout
    m = re.search(r"(?:stale|cancel)\s*(?:orders?)?(?:\s*older\s*than)?[:\s]*(\d+)\s*(?:tick|period)", lower)
    if m:
        params["stale_order_ticks"] = int(m.group(1))

    return params


def _extract_entry_rules(content: str) -> list[dict[str, str]]:
    """Extract entry/exit rules from strategy text."""
    rules: list[dict[str, str]] = []

    # Match "BUY when: ..." or "- BUY: ..." or "BUY if ..."
    for m in re.finditer(
        r"^\s*[-*]?\s*(BUY|SELL|buy|sell|Buy|Sell)\s*(?:when|if|:)\s*[:.]?\s*(.+)$",
        content,
        re.MULTILINE,
    ):
        action = m.group(1).lower()
        condition = m.group(2).strip().rstrip(".")
        rules.append({"condition": condition, "action": action})

    return rules


def _extract_success_metrics(content: str) -> dict[str, float]:
    """Extract success criteria from strategy text."""
    metrics: dict[str, float] = {}
    lower = content.lower()

    # Win rate
    m = re.search(r"win\s*rate\s*(?:>|above|>=|at\s*least|minimum)[:\s]*(\d+\.?\d*)%?", lower)
    if m:
        val = float(m.group(1))
        metrics["min_win_rate"] = val / 100 if val > 1 else val

    # Max drawdown
    m = re.search(r"(?:max|maximum)\s*(?:draw\s*down|drawdown)\s*(?:<|below|<=|under|limit)[:\s]*(\d+\.?\d*)%?", lower)
    if m:
        metrics["max_drawdown_pct"] = float(m.group(1))

    # Profit target (avoid matching "24h" as a dollar amount)
    m = re.search(r"(?:min(?:imum)?)\s*(?:p&l|pnl|profit)\s*(?:per\s*tick|target)?[:\s]*\$(\d+\.?\d*)", lower)
    if m:
        metrics["min_profit_per_tick"] = float(m.group(1))
    elif "positive p&l" in lower or "positive pnl" in lower or "positive profit" in lower:
        metrics["min_profit_per_tick"] = 0.0

    return metrics


# ---------------------------------------------------------------------------
# LLM-based extraction (optional enhancer)
# ---------------------------------------------------------------------------

def _llm_extract(content: str, model: Any) -> dict[str, Any]:
    """Use an LLM to extract structured parameters from strategy text."""
    prompt = (
        "Extract trading strategy parameters from this text into JSON.\n"
        "Return ONLY a JSON object with these fields (omit any you can't find):\n"
        "{\n"
        '  "parameters": {\n'
        '    "spread_pct": number,\n'
        '    "position_size": number,\n'
        '    "max_open_orders": number,\n'
        '    "momentum_threshold": number,\n'
        '    "rebalance_interval_ticks": number,\n'
        '    "tokens": ["ETH", ...],\n'
        '    "stop_loss_pct": number,\n'
        '    "max_daily_loss_usd": number\n'
        "  },\n"
        '  "entry_rules": [\n'
        '    {"condition": "human-readable condition", "action": "buy|sell"}\n'
        "  ],\n"
        '  "success_metrics": {\n'
        '    "min_win_rate": 0.0-1.0,\n'
        '    "max_drawdown_pct": number,\n'
        '    "min_profit_per_tick": number\n'
        "  }\n"
        "}\n\n"
        "Strategy text:\n"
        f"{content}\n"
    )

    raw = model.complete(prompt)
    # Strip code fences
    clean = raw.strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        clean = "\n".join(lines[1:])
        if clean.rstrip().endswith("```"):
            clean = clean.rstrip()[:-3]

    return json.loads(clean)


def _merge_results(regex_result: dict, llm_result: dict) -> dict[str, Any]:
    """Merge LLM results into regex results — regex takes precedence for conflicts."""
    merged = {
        "parameters": {**llm_result.get("parameters", {}), **regex_result["parameters"]},
        "entry_rules": regex_result["entry_rules"] or llm_result.get("entry_rules", []),
        "success_metrics": {**llm_result.get("success_metrics", {}), **regex_result["success_metrics"]},
    }
    return merged
