#!/usr/bin/env python3
"""
Polymarket Event Loader
=======================
Fetches event data from Polymarket URLs and updates config/events.yaml
with real token IDs, condition IDs, and market metadata.

Usage:
    python update_events.py URL1 [URL2 ...]

Example:
    python update_events.py https://polymarket.com/event/bitcoin-up-or-down-february-3-10am-et
    python update_events.py URL1 URL2 URL3
"""

import json
import os
import re
import sys

import requests
import yaml

GAMMA_API = "https://gamma-api.polymarket.com"
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "config", "events.yaml"
)


def extract_slug(url: str) -> str:
    """Extract the event slug from a Polymarket URL.

    Supports formats:
        https://polymarket.com/event/some-event-slug
        https://polymarket.com/event/some-event-slug?tid=123
        polymarket.com/event/some-event-slug
    """
    match = re.search(r"polymarket\.com/event/([a-zA-Z0-9_-]+)", url)
    if not match:
        raise ValueError(f"Could not extract event slug from URL: {url}")
    return match.group(1)


def fetch_event(slug: str) -> dict:
    """Fetch event data from the Gamma API."""
    response = requests.get(f"{GAMMA_API}/events", params={"slug": slug}, timeout=15)
    response.raise_for_status()
    data = response.json()
    if not data:
        raise ValueError(f"No event found for slug: {slug}")
    return data[0]


def detect_icon(title: str) -> str:
    """Detect the appropriate icon based on the event title."""
    title_lower = title.lower()
    if "bitcoin" in title_lower or "btc" in title_lower:
        return "btc"
    if "ethereum" in title_lower or "eth" in title_lower:
        return "eth"
    if "solana" in title_lower or "sol " in title_lower:
        return "sol"
    return "generic"


def detect_binance_symbol(title: str, resolution_source: str) -> str:
    """Detect the Binance trading pair from the event metadata."""
    # Try to extract from resolution source URL (e.g. binance.com/en/trade/BTC_USDT)
    match = re.search(r"binance\.com/\w+/trade/(\w+)", resolution_source)
    if match:
        return match.group(1).replace("_", "")
    # Fallback: guess from title
    title_lower = title.lower()
    if "bitcoin" in title_lower or "btc" in title_lower:
        return "BTCUSDT"
    if "ethereum" in title_lower or "eth" in title_lower:
        return "ETHUSDT"
    if "solana" in title_lower or "sol" in title_lower:
        return "SOLUSDT"
    return ""


def build_event_entries(event_data: dict) -> list:
    """Build one YAML entry per market inside the event.

    A single Polymarket event can contain multiple markets (e.g. neg-risk
    events with several outcomes). Each market becomes its own entry in
    events.yaml so the monitor can track them independently.
    """
    markets = event_data.get("markets", [])
    if not markets:
        raise ValueError(f"Event '{event_data.get('title')}' has no markets")

    entries = []
    for market in markets:
        token_ids = json.loads(market.get("clobTokenIds", "[]"))
        outcomes = json.loads(market.get("outcomes", "[]"))
        prices = json.loads(market.get("outcomePrices", "[]"))

        if len(token_ids) < 2:
            continue

        # Map first outcome to yes, second to no
        yes_label = outcomes[0] if outcomes else "Yes"
        no_label = outcomes[1] if len(outcomes) > 1 else "No"
        yes_price = float(prices[0]) if prices else 0.50
        no_price = float(prices[1]) if len(prices) > 1 else 0.50

        title = market.get("question", event_data.get("title", "Unknown"))
        description = (event_data.get("description") or "")[:120]
        # Use first sentence as short description
        first_sentence = description.split(".")[0].strip()
        if not first_sentence:
            first_sentence = title

        resolution_source = market.get("resolutionSource", "")
        event_start_time = market.get("eventStartTime", "")
        binance_symbol = detect_binance_symbol(title, resolution_source)

        entry = {
            "name": title,
            "description": first_sentence,
            "icon": detect_icon(title),
            "condition_id": market.get("conditionId", ""),
            "tokens": {
                "yes": token_ids[0],
                "no": token_ids[1],
            },
            "resolution_source": resolution_source,
            "event_start_time": event_start_time,
            "binance_symbol": binance_symbol,
            "settings": {
                "refresh_interval": 5,
                "price_to_beat": None,
            },
        }
        entries.append(entry)

        # Print summary
        print(f"  Market: {title}")
        print(
            f"    {yes_label}: {yes_price * 100:.1f}c  |  {no_label}: {no_price * 100:.1f}c"
        )
        print(f"    condition_id: {market.get('conditionId', 'N/A')[:20]}...")
        print(f"    tokens yes: ...{token_ids[0][-12:]}")
        print(f"    tokens no:  ...{token_ids[1][-12:]}")
        if binance_symbol:
            print(f"    binance: {binance_symbol}")
        if event_start_time:
            print(f"    event start: {event_start_time}")
        print()

    return entries


def update_events_yaml(entries: list) -> None:
    """Update config/events.yaml with the new event entries.

    Replaces the ``events`` list and sets ``demo_mode`` to false while
    preserving every other section (demo_events, trading, ui).
    """
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)

    config["events"] = entries
    config["demo_mode"] = False

    with open(CONFIG_PATH, "w") as f:
        yaml.dump(
            config, f, default_flow_style=False, sort_keys=False, allow_unicode=True
        )

    print(f"Config written to {CONFIG_PATH}")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    urls = sys.argv[1:]
    all_entries = []

    for url in urls:
        try:
            slug = extract_slug(url)
            print(f"Fetching event: {slug} ...")
            event_data = fetch_event(slug)
            title = event_data.get("title", slug)
            print(f"  Event: {title}")
            print(f"  Volume: ${event_data.get('volume', 0):,.2f}")
            print(f"  Liquidity: ${event_data.get('liquidity', 0):,.2f}")
            print()
            entries = build_event_entries(event_data)
            all_entries.extend(entries)
        except Exception as e:
            print(f"ERROR processing {url}: {e}", file=sys.stderr)

    if not all_entries:
        print("No events were loaded. Check the URLs and try again.", file=sys.stderr)
        sys.exit(1)

    update_events_yaml(all_entries)
    print(f"Loaded {len(all_entries)} market(s) from {len(urls)} event URL(s).")
    print("demo_mode set to false.")


if __name__ == "__main__":
    main()
