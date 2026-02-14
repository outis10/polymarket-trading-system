"""Auto-discovery for live Polymarket crypto range events."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com/events"

SYMBOL_HINTS: dict[str, tuple[str, ...]] = {
    "BTC": ("bitcoin", "btc"),
    "ETH": ("ethereum", "eth"),
    "SOL": ("solana", "sol"),
    "XRP": ("xrp", "ripple"),
}

BINANCE_SYMBOLS: dict[str, str] = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "XRP": "XRPUSDT",
}

TIMEFRAME_KEYWORDS: dict[int, tuple[str, ...]] = {
    5: ("5m", "5 min", "5-minute"),
    15: ("15m", "15 min", "15-minute"),
    60: ("1h", "60m", "60 min", "60-minute", "1 hour", "hourly"),
}

SLUG_TIMEFRAME_RE = re.compile(
    r"(?P<symbol>btc|eth|sol|xrp)-updown-(?P<tf>5m|15m|1h)-(?P<epoch>\d+)"
)


def _parse_iso_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except Exception:
        return None


def _is_truthy(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return default


def _detect_symbol(text: str, symbols: set[str]) -> str | None:
    txt = text.lower()
    for symbol, hints in SYMBOL_HINTS.items():
        if symbol not in symbols:
            continue
        if any(h in txt for h in hints):
            return symbol
    return None


def _parse_json_list(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _detect_icon(name: str) -> str:
    lowered = name.lower()
    if "bitcoin" in lowered or "btc" in lowered:
        return "btc"
    if "ethereum" in lowered or "eth" in lowered:
        return "eth"
    if "solana" in lowered or "sol " in lowered:
        return "sol"
    return "generic"


def _is_15m_like(
    question: str,
    start_dt: datetime | None,
    end_dt: datetime | None,
    require_15m: bool,
    min_minutes: int,
    max_minutes: int,
) -> bool:
    if not require_15m:
        return True

    q = question.lower()
    if "15m" in q or "15 min" in q or "15-minute" in q:
        return True

    if not start_dt or not end_dt:
        return False

    duration_minutes = (end_dt - start_dt).total_seconds() / 60
    return min_minutes <= duration_minutes <= max_minutes


def _detect_timeframe_minutes(
    question: str,
    start_dt: datetime | None,
    end_dt: datetime | None,
    allowed_timeframes: set[int],
) -> int | None:
    q = question.lower()
    for minutes, keywords in TIMEFRAME_KEYWORDS.items():
        if minutes in allowed_timeframes and any(k in q for k in keywords):
            return minutes

    if start_dt and end_dt:
        duration_minutes = (end_dt - start_dt).total_seconds() / 60
        for minutes in sorted(allowed_timeframes):
            if abs(duration_minutes - minutes) <= 2:
                return minutes
    return None


def _detect_timeframe_from_slug(slug: str, allowed_timeframes: set[int]) -> int | None:
    if not slug:
        return None
    match = SLUG_TIMEFRAME_RE.search(slug.lower())
    if not match:
        return None
    tf_raw = match.group("tf")
    mapping = {"5m": 5, "15m": 15, "1h": 60}
    value = mapping.get(tf_raw)
    if value in allowed_timeframes:
        return value
    return None


def _extract_window_from_slug(slug: str) -> tuple[int, datetime, datetime] | None:
    if not slug:
        return None
    match = SLUG_TIMEFRAME_RE.search(slug.lower())
    if not match:
        return None

    tf_raw = match.group("tf")
    epoch = int(match.group("epoch"))
    timeframe_minutes = {"5m": 5, "15m": 15, "1h": 60}[tf_raw]

    start_dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    end_dt = start_dt + timedelta(minutes=timeframe_minutes)
    return timeframe_minutes, start_dt, end_dt


def discover_live_events(config: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Discover active crypto events from Gamma and convert to events.yaml schema.

    Expected config fields (all optional):
      enabled, symbols, lookahead_days, refresh_seconds, max_events,
      require_15m, min_minutes, max_minutes.
    """
    if not _is_truthy(config.get("enabled", False), default=False):
        return []

    symbols = set((config.get("symbols") or ["BTC", "ETH", "SOL", "XRP"]))
    lookahead_days = int(config.get("lookahead_days", 7))
    max_events = int(config.get("max_events", 80))
    require_15m = _is_truthy(config.get("require_15m", False), default=False)
    min_minutes = int(config.get("min_minutes", 10))
    max_minutes = int(config.get("max_minutes", 20))
    allowed_timeframes = {
        int(v) for v in (config.get("allowed_timeframes") or [5, 15, 60])
    }
    only_live_now = _is_truthy(config.get("only_live_now", True), default=True)

    now = datetime.now(tz=timezone.utc)
    horizon = now + timedelta(days=lookahead_days)
    discovered: list[dict[str, Any]] = []
    seen_conditions: set[str] = set()

    limit = 200
    offset = 0
    pages = 0
    max_pages = 8

    while pages < max_pages and len(discovered) < max_events:
        params = {
            "active": "true",
            "closed": "false",
            "archived": "false",
            "limit": limit,
            "offset": offset,
            "ascending": "true",
            "order": "endDate",
        }

        resp = requests.get(GAMMA_API, params=params, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list) or not payload:
            break

        for event in payload:
            if len(discovered) >= max_events:
                break

            title = str(event.get("title") or "")
            description = str(event.get("description") or "")
            symbol = _detect_symbol(title, symbols) or _detect_symbol(
                description, symbols
            )
            if not symbol:
                continue

            markets = event.get("markets") or []
            if not isinstance(markets, list):
                continue

            for market in markets:
                if len(discovered) >= max_events:
                    break

                if not _is_truthy(market.get("active"), default=True):
                    continue
                if _is_truthy(market.get("closed"), default=False):
                    continue
                if not _is_truthy(market.get("acceptingOrders"), default=True):
                    continue

                question = str(market.get("question") or title)
                market_slug = str(market.get("slug") or event.get("slug") or "")
                market_symbol = _detect_symbol(question, symbols) or symbol
                if not market_symbol:
                    continue

                start_dt = _parse_iso_utc(
                    market.get("eventStartTime") or event.get("startDate")
                )
                end_dt = _parse_iso_utc(
                    market.get("endDateIso") or event.get("endDate")
                )
                slug_window = _extract_window_from_slug(market_slug)
                if slug_window:
                    _, start_dt, end_dt = slug_window

                if end_dt and (end_dt < now or end_dt > horizon):
                    continue
                if (
                    only_live_now
                    and start_dt
                    and end_dt
                    and not (start_dt <= now < end_dt)
                ):
                    continue

                if not _is_15m_like(
                    question=question,
                    start_dt=start_dt,
                    end_dt=end_dt,
                    require_15m=require_15m,
                    min_minutes=min_minutes,
                    max_minutes=max_minutes,
                ):
                    continue

                timeframe_minutes = _detect_timeframe_from_slug(
                    slug=market_slug,
                    allowed_timeframes=allowed_timeframes,
                ) or _detect_timeframe_minutes(
                    question=question,
                    start_dt=start_dt,
                    end_dt=end_dt,
                    allowed_timeframes=allowed_timeframes,
                )
                if timeframe_minutes is None:
                    continue

                condition_id = str(market.get("conditionId") or "").strip()
                if not condition_id or condition_id in seen_conditions:
                    continue

                token_ids = _parse_json_list(market.get("clobTokenIds"))
                if len(token_ids) < 2:
                    continue

                desc_short = description.split(".")[0].strip() or question
                desc_short = re.sub(r"\s+", " ", desc_short)[:140]

                discovered.append(
                    {
                        "name": question,
                        "description": desc_short,
                        "icon": _detect_icon(question),
                        "condition_id": condition_id,
                        "tokens": {
                            "yes": str(token_ids[0]),
                            "no": str(token_ids[1]),
                        },
                        "resolution_source": str(market.get("resolutionSource") or ""),
                        "event_start_time": (
                            start_dt.isoformat().replace("+00:00", "Z")
                            if start_dt
                            else ""
                        ),
                        "event_end_time": (
                            end_dt.isoformat().replace("+00:00", "Z") if end_dt else ""
                        ),
                        "is_15m": timeframe_minutes == 15,
                        "timeframe_minutes": timeframe_minutes,
                        "timeframe_label": (
                            "1h" if timeframe_minutes == 60 else f"{timeframe_minutes}m"
                        ),
                        "chainlink_symbol": market_symbol,
                        "binance_symbol": BINANCE_SYMBOLS.get(market_symbol, ""),
                        "settings": {
                            "refresh_interval": 5,
                            "price_to_beat": None,
                        },
                    }
                )
                seen_conditions.add(condition_id)

        if len(payload) < limit:
            break
        offset += limit
        pages += 1

    logger.info(
        "Discovered %d live events (symbols=%s, lookahead_days=%s, require_15m=%s, only_live_now=%s)",
        len(discovered),
        sorted(symbols),
        lookahead_days,
        require_15m,
        only_live_now,
    )
    return discovered
