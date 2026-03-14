"""
Execution Engine — Fill Simulator (v1.1-b)

Estimates the cost of filling an order by walking the order book depth.
Purely read-only: works in paper mode and live mode identically.

Order book level format (from event_manager._parse_book_levels):
    {"price": float, "shares": float, "total": float}  # total = cumulative notional USD
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FillEstimate:
    """Result of a fill simulation against an order book snapshot."""

    # Core estimates
    avg_fill_price: float | None = None       # notional-weighted avg price across levels
    worst_fill_price: float | None = None     # price of the deepest level touched
    best_ask: float | None = None             # top-of-book ask price

    # Fill coverage
    fillable_notional_usd: float = 0.0        # USD we can actually fill (≤ requested)
    fillable_shares: float = 0.0              # shares receivable
    requested_notional_usd: float = 0.0       # what was requested
    levels_consumed: int = 0                  # how many book levels we walked

    # Slippage metrics (in basis points)
    slippage_vs_best_ask_bps: float | None = None  # (avg_fill - best_ask) / best_ask * 10000
    slippage_vs_mid_bps: float | None = None       # (avg_fill - mid) / mid * 10000

    # Book consumption
    total_ask_notional_usd: float = 0.0       # total visible ask-side notional in book
    book_consumption_pct: float | None = None  # fillable_notional / total_ask_notional

    # Human-readable verdict
    fully_fillable: bool = False              # True if book can absorb the full notional
    insufficient_liquidity: bool = False      # True if book is completely empty


def estimate_fill(
    asks: list[dict],
    notional_usd: float,
    mid: float | None = None,
) -> FillEstimate:
    """
    Simulate filling `notional_usd` worth of shares by walking the ask side.

    Args:
        asks:         Ask levels [{"price": float, "shares": float, "total": float}, ...]
                      Must be sorted ascending (best ask first).
        notional_usd: USD amount to fill.
        mid:          Current mid price for IS calculation (optional).

    Returns:
        FillEstimate with all metrics populated.
    """
    est = FillEstimate(requested_notional_usd=notional_usd)

    if not asks or notional_usd <= 0:
        est.insufficient_liquidity = not asks
        return est

    est.best_ask = float(asks[0]["price"])

    # Total visible ask-side notional (last level has cumulative total)
    last_total = asks[-1].get("total")
    if isinstance(last_total, (int, float)) and last_total > 0:
        est.total_ask_notional_usd = float(last_total)
    else:
        est.total_ask_notional_usd = sum(
            float(lv["price"]) * float(lv["shares"]) for lv in asks
        )

    remaining = notional_usd
    total_shares = 0.0
    total_notional_spent = 0.0

    for lv in asks:
        try:
            price = float(lv["price"])
            available_shares = float(lv["shares"])
        except (KeyError, TypeError, ValueError):
            continue

        if price <= 0 or available_shares <= 0:
            continue

        level_max_notional = price * available_shares

        if remaining <= level_max_notional:
            # This level can fully absorb remaining notional
            shares_bought = remaining / price
            total_shares += shares_bought
            total_notional_spent += remaining
            est.worst_fill_price = price
            est.levels_consumed += 1
            remaining = 0.0
            break
        else:
            # Consume entire level, continue to next
            total_shares += available_shares
            total_notional_spent += level_max_notional
            est.worst_fill_price = price
            est.levels_consumed += 1
            remaining -= level_max_notional

    est.fillable_notional_usd = round(total_notional_spent, 6)
    est.fillable_shares = round(total_shares, 6)
    est.fully_fillable = remaining <= 1e-9

    if total_shares > 0:
        est.avg_fill_price = round(total_notional_spent / total_shares, 6)
    else:
        return est

    if est.best_ask and est.best_ask > 0:
        est.slippage_vs_best_ask_bps = round(
            (est.avg_fill_price - est.best_ask) / est.best_ask * 10000, 2
        )

    if mid and mid > 0:
        est.slippage_vs_mid_bps = round(
            (est.avg_fill_price - mid) / mid * 10000, 2
        )

    if est.total_ask_notional_usd > 0:
        est.book_consumption_pct = round(
            est.fillable_notional_usd / est.total_ask_notional_usd * 100, 2
        )

    return est


def estimate_fill_from_event(
    event_dict: dict,
    side: str,
    notional_usd: float,
    mid: float | None = None,
) -> FillEstimate:
    """
    Convenience wrapper: reads order book from event_dict and calls estimate_fill.

    Args:
        event_dict:   Event dict as maintained by EventManager.
        side:         "up" or "down" (maps to yes/no).
        notional_usd: USD amount to fill.
        mid:          Current mid price (optional).
    """
    ob_key = "order_book_yes" if side == "up" else "order_book_no"
    ob = event_dict.get(ob_key) or {}
    asks: list[dict] = ob.get("asks", []) if isinstance(ob, dict) else []
    return estimate_fill(asks, notional_usd, mid=mid)


def fill_estimate_to_log(est: FillEstimate) -> dict:
    """
    Convert a FillEstimate to a flat dict suitable for CSV logging.
    All values are strings to match the CSV pattern.
    """
    def _fmt(v: float | None, decimals: int = 6) -> str:
        return str(round(v, decimals)) if v is not None else ""

    return {
        "expected_avg_fill_price": _fmt(est.avg_fill_price),
        "fill_sim_worst_price": _fmt(est.worst_fill_price),
        "fill_sim_fillable_notional": _fmt(est.fillable_notional_usd, 4),
        "fill_sim_fillable_shares": _fmt(est.fillable_shares, 4),
        "fill_sim_levels_consumed": str(est.levels_consumed) if est.levels_consumed else "",
        "fill_sim_slippage_vs_ask_bps": _fmt(est.slippage_vs_best_ask_bps, 2),
        "fill_sim_slippage_vs_mid_bps": _fmt(est.slippage_vs_mid_bps, 2),
        "fill_sim_book_consumption_pct": _fmt(est.book_consumption_pct, 2),
        "fill_sim_fully_fillable": "1" if est.fully_fillable else "0",
    }
