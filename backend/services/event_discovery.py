"""Auto-discovery for live Polymarket crypto range events."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com/events"
GAMMA_MARKETS_API = "https://gamma-api.polymarket.com/markets"

_GAMMA_TIMEOUT = 20
_GAMMA_SESSION: requests.Session | None = None

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


def _gamma_session() -> requests.Session:
    global _GAMMA_SESSION
    if _GAMMA_SESSION is not None:
        return _GAMMA_SESSION

    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=8)

    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    _GAMMA_SESSION = session
    return session


def _gamma_get_json(url: str, *, params: dict[str, Any]) -> Any:
    resp = _gamma_session().get(url, params=params, timeout=_GAMMA_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


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
        # Use word boundaries to avoid false positives like "eth" inside
        # unrelated words (e.g. "whether").
        if any(re.search(rf"\b{re.escape(h)}\b", txt) for h in hints):
            return symbol
    return None


def _symbol_matches_text(symbol: str, *texts: str) -> bool:
    patterns = {
        "BTC": r"\b(bitcoin|btc)\b",
        "ETH": r"\b(ethereum|eth)\b",
        "SOL": r"\b(sol|solana)\b",
        "XRP": r"\b(xrp|ripple)\b",
    }
    pattern = patterns.get(symbol.upper())
    if not pattern:
        return False
    blob = " ".join(str(t or "") for t in texts).lower()
    return bool(re.search(pattern, blob))


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


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        txt = value.strip().replace(",", "")
        if not txt:
            return None
        try:
            return float(txt)
        except ValueError:
            return None
    return None


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


def _extract_window_from_slug(
    slug: str,
    start_hint: datetime | None = None,
    end_hint: datetime | None = None,
) -> tuple[int, datetime, datetime] | None:
    if not slug:
        return None
    match = SLUG_TIMEFRAME_RE.search(slug.lower())
    if not match:
        return None

    tf_raw = match.group("tf")
    epoch = int(match.group("epoch"))
    timeframe_minutes = {"5m": 5, "15m": 15, "1h": 60}[tf_raw]

    epoch_dt = datetime.fromtimestamp(epoch, tz=timezone.utc)

    # Candidate A: epoch is window start.
    start_as_start = epoch_dt
    end_as_start = start_as_start + timedelta(minutes=timeframe_minutes)

    # Candidate B: epoch is window end.
    end_as_end = epoch_dt
    start_as_end = end_as_end - timedelta(minutes=timeframe_minutes)

    def _score(start_dt: datetime, end_dt: datetime) -> float:
        score = 0.0
        if start_hint:
            score += abs((start_dt - start_hint).total_seconds())
        if end_hint:
            score += abs((end_dt - end_hint).total_seconds())
        return score

    # If Gamma provides hints, pick the interpretation that best matches them.
    if start_hint or end_hint:
        score_start = _score(start_as_start, end_as_start)
        score_end = _score(start_as_end, end_as_end)
        if score_start <= score_end:
            return timeframe_minutes, start_as_start, end_as_start
        return timeframe_minutes, start_as_end, end_as_end

    # Fallback when hints are missing: default to epoch as end.
    return timeframe_minutes, start_as_end, end_as_end


def _load_markets_fallback_by_slug(
    *,
    symbols: set[str],
    now: datetime,
    horizon: datetime,
) -> dict[str, dict[str, Any]]:
    """Best-effort fallback index from Gamma /markets keyed by slug."""
    out: dict[str, dict[str, Any]] = {}
    limit = 500
    offset = 0
    pages = 0
    max_pages = 6

    while pages < max_pages:
        params = {
            "active": "true",
            "closed": "false",
            "archived": "false",
            "limit": limit,
            "offset": offset,
            "ascending": "true",
            "order": "endDate",
        }
        payload = _gamma_get_json(GAMMA_MARKETS_API, params=params)
        if not isinstance(payload, list) or not payload:
            break

        for market in payload:
            if not isinstance(market, dict):
                continue
            slug = str(market.get("slug") or "").strip()
            if not slug:
                continue
            question = str(market.get("question") or "")
            symbol = _detect_symbol(question, symbols) or _detect_symbol(slug, symbols)
            if not symbol:
                continue
            if not _symbol_matches_text(
                symbol, question, slug, market.get("description", "")
            ):
                continue
            end_dt = _parse_iso_utc(market.get("endDateIso") or market.get("endDate"))
            if end_dt and (end_dt < now or end_dt > horizon):
                continue
            out[slug] = market

        if len(payload) < limit:
            break
        offset += limit
        pages += 1

    logger.info("Gamma markets fallback index loaded: %d slugs", len(out))
    return out


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
    markets_fallback_by_slug: dict[str, dict[str, Any]] | None = None

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

        payload = _gamma_get_json(GAMMA_API, params=params)
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
                market_symbol = _detect_symbol(question, symbols) or _detect_symbol(
                    market_slug, symbols
                )
                if not market_symbol:
                    continue
                # Extra guard: do not inherit event-level symbol blindly.
                # Market text itself must explicitly match the selected symbol.
                if not _symbol_matches_text(
                    market_symbol, question, market_slug, market.get("description", "")
                ):
                    continue

                start_dt = _parse_iso_utc(
                    market.get("eventStartTime") or event.get("startDate")
                )
                end_dt = _parse_iso_utc(
                    market.get("endDateIso") or event.get("endDate")
                )
                slug_window = _extract_window_from_slug(
                    market_slug,
                    start_hint=start_dt,
                    end_hint=end_dt,
                )
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

                condition_id_raw = str(market.get("conditionId") or "").strip()
                axis_price_raw = _parse_float(market.get("xAxisValue"))
                condition_id = condition_id_raw
                axis_price = axis_price_raw
                token_ids = _parse_json_list(market.get("clobTokenIds"))
                fallback_market: dict[str, Any] | None = None

                if (
                    not condition_id or axis_price is None or len(token_ids) < 2
                ) and market_slug:
                    if markets_fallback_by_slug is None:
                        try:
                            markets_fallback_by_slug = _load_markets_fallback_by_slug(
                                symbols=symbols, now=now, horizon=horizon
                            )
                        except Exception as exc:
                            logger.warning(
                                "Could not load Gamma markets fallback: %s", exc
                            )
                            markets_fallback_by_slug = {}
                    fallback_market = markets_fallback_by_slug.get(market_slug)
                    if fallback_market:
                        if not condition_id:
                            condition_id = str(
                                fallback_market.get("conditionId") or ""
                            ).strip()
                        if axis_price is None:
                            axis_price = _parse_float(fallback_market.get("xAxisValue"))
                        if len(token_ids) < 2:
                            token_ids = _parse_json_list(
                                fallback_market.get("clobTokenIds")
                            )

                if not condition_id or condition_id in seen_conditions:
                    continue
                if len(token_ids) < 2:
                    continue

                desc_short = description.split(".")[0].strip() or question
                desc_short = re.sub(r"\s+", " ", desc_short)[:140]
                resolution_source = str(
                    market.get("resolutionSource")
                    or (fallback_market or {}).get("resolutionSource")
                    or ""
                )
                axis_from = (
                    "events"
                    if axis_price_raw is not None
                    else ("markets_fallback" if axis_price is not None else "missing")
                )
                cid_from = (
                    "events"
                    if condition_id_raw
                    else ("markets_fallback" if condition_id else "missing")
                )
                logger.info(
                    "Gamma resolve market slug=%s symbol=%s tf=%sm cid=%s(%s) axis=%s(%s)",
                    market_slug,
                    market_symbol,
                    timeframe_minutes,
                    "yes" if condition_id else "no",
                    cid_from,
                    "yes" if axis_price is not None else "no",
                    axis_from,
                )

                discovered.append(
                    {
                        "name": question,
                        "description": desc_short,
                        "icon": _detect_icon(question),
                        "condition_id": condition_id,
                        "slug": market_slug,
                        "tokens": {
                            "yes": str(token_ids[0]),
                            "no": str(token_ids[1]),
                        },
                        "resolution_source": resolution_source,
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
                            "price_to_beat": axis_price,
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
