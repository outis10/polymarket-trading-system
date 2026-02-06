"""Configuration loader: reads config/events.yaml and .env."""

import os
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Ensure project root is importable (for config.settings, core.client_wrapper)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

EVENTS_YAML = PROJECT_ROOT / "config" / "events.yaml"


def load_events_config() -> dict:
    """Load and return the full events.yaml dict."""
    try:
        with open(EVENTS_YAML, "r") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def get_trading_config(config: dict | None = None) -> dict:
    """Return the trading section from events.yaml."""
    if config is None:
        config = load_events_config()
    return config.get("trading", {})


def get_ui_config(config: dict | None = None) -> dict:
    """Return the UI section from events.yaml."""
    if config is None:
        config = load_events_config()
    return config.get("ui", {})
