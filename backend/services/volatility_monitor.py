"""Volatility signal detector based on direction flip density.

Detects when the bot sees multiple large diff_vs_ptb signals that rapidly
flip direction within a rolling time window — a sign that the underlying
asset is in a choppy, unpredictable regime where the quant model's edge
breaks down.

Usage:
    from .volatility_monitor import volatility_monitor

    # Call after computing diff_vs_ptb for each order candidate:
    triggered = volatility_monitor.record_signal(ticker, diff_vs_ptb)
    if triggered:
        logger.warning("High volatility detected for %s", ticker)

    # Control API watchdog checks for pending alerts:
    alert = volatility_monitor.consume_alert()

Configuration (runtime_settings.json):
    "volatility_flip_trigger": 3          # flips in window to trigger
    "volatility_window_seconds": 3600     # rolling window size
    "volatility_alert_cooldown": 1800     # min seconds between alerts per ticker
    "volatility_thresholds": {"BTC": 30, "ETH": 2}  # |diff_vs_ptb| min to count
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

# Defaults — overridable via runtime_settings
_DEFAULT_THRESHOLDS: dict[str, float] = {"BTC": 30.0, "ETH": 2.0}
_DEFAULT_WINDOW_SECONDS: float = 3600.0
_DEFAULT_FLIP_TRIGGER: int = 3
_DEFAULT_ALERT_COOLDOWN: float = 1800.0


class VolatilityMonitor:
    """Rolling-window direction-flip detector per ticker."""

    def __init__(self) -> None:
        # (timestamp, ticker, sign) — sign is +1 or -1
        self._signals: deque[tuple[float, str, int]] = deque()
        # ticker -> last alert timestamp (for cooldown)
        self._alerted_at: dict[str, float] = {}
        # Latest unread alert (consumed by control API watchdog)
        self._pending_alert: dict[str, Any] | None = None
        # Runtime-configurable parameters (updated by event_manager after settings load)
        self.thresholds: dict[str, float] = dict(_DEFAULT_THRESHOLDS)
        self.window_seconds: float = _DEFAULT_WINDOW_SECONDS
        self.flip_trigger: int = _DEFAULT_FLIP_TRIGGER
        self.alert_cooldown: float = _DEFAULT_ALERT_COOLDOWN

    def update_config(self, settings: dict[str, Any]) -> None:
        """Sync parameters from runtime_settings. Call after any settings change."""
        raw_thresholds = settings.get("volatility_thresholds")
        if isinstance(raw_thresholds, dict):
            self.thresholds = {k.upper(): float(v) for k, v in raw_thresholds.items()}
        else:
            self.thresholds = dict(_DEFAULT_THRESHOLDS)

        raw_window = settings.get("volatility_window_seconds")
        self.window_seconds = float(raw_window) if isinstance(raw_window, (int, float)) else _DEFAULT_WINDOW_SECONDS

        raw_trigger = settings.get("volatility_flip_trigger")
        self.flip_trigger = int(raw_trigger) if isinstance(raw_trigger, int) else _DEFAULT_FLIP_TRIGGER

        raw_cooldown = settings.get("volatility_alert_cooldown")
        self.alert_cooldown = float(raw_cooldown) if isinstance(raw_cooldown, (int, float)) else _DEFAULT_ALERT_COOLDOWN

    def record_signal(self, ticker: str, diff: float, ts: float | None = None) -> bool:
        """Record a large diff_vs_ptb signal. Returns True if volatility triggered.

        Args:
            ticker: Asset ticker (e.g. "BTC", "ETH")
            diff: diff_vs_ptb value (signed)
            ts: Unix timestamp; defaults to now

        Returns:
            True if a new volatility alert was triggered, False otherwise.
        """
        upper = ticker.upper()
        threshold = self.thresholds.get(upper, 30.0)
        if abs(diff) < threshold:
            return False

        now = ts if ts is not None else time.time()
        sign = 1 if diff > 0 else -1
        self._signals.append((now, upper, sign))

        # Prune signals outside the rolling window
        cutoff = now - self.window_seconds
        while self._signals and self._signals[0][0] < cutoff:
            self._signals.popleft()

        # Count direction flips for this ticker within window
        ticker_sigs = [(t, s) for t, tk, s in self._signals if tk == upper]
        if len(ticker_sigs) < 2:
            return False

        flips = sum(
            1
            for i in range(1, len(ticker_sigs))
            if ticker_sigs[i][1] != ticker_sigs[i - 1][1]
        )

        last_alerted = self._alerted_at.get(upper, 0.0)
        if flips >= self.flip_trigger and (now - last_alerted) > self.alert_cooldown:
            self._alerted_at[upper] = now
            # Build human-readable signal history (last 8 signals)
            direction_history = [
                "UP" if s == 1 else "DOWN" for _, s in ticker_sigs[-8:]
            ]
            self._pending_alert = {
                "ticker": upper,
                "flips": flips,
                "signals_in_window": len(ticker_sigs),
                "direction_history": direction_history,
                "triggered_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            }
            return True

        return False

    def consume_alert(self) -> dict[str, Any] | None:
        """Return the pending alert and clear it. Called by the watchdog endpoint."""
        alert = self._pending_alert
        self._pending_alert = None
        return alert

    def peek_alert(self) -> dict[str, Any] | None:
        """Return the pending alert without clearing it."""
        return self._pending_alert

    def get_state(self) -> dict[str, Any]:
        """Current monitor state for the /volatility-state endpoint."""
        now = time.time()
        cutoff = now - self.window_seconds

        # Group recent signals by ticker
        by_ticker: dict[str, list[tuple[float, int]]] = {}
        for t, tk, s in self._signals:
            if t >= cutoff:
                by_ticker.setdefault(tk, []).append((t, s))

        ticker_stats: dict[str, Any] = {}
        for tk, sigs in by_ticker.items():
            flips = sum(
                1 for i in range(1, len(sigs)) if sigs[i][1] != sigs[i - 1][1]
            )
            ticker_stats[tk] = {
                "signals_in_window": len(sigs),
                "flips": flips,
                "alert_active": flips >= self.flip_trigger,
                "last_alerted_at": (
                    datetime.fromtimestamp(self._alerted_at[tk], tz=timezone.utc).isoformat()
                    if tk in self._alerted_at
                    else None
                ),
            }

        return {
            "ticker_stats": ticker_stats,
            "has_pending_alert": self._pending_alert is not None,
            "config": {
                "flip_trigger": self.flip_trigger,
                "window_seconds": self.window_seconds,
                "alert_cooldown": self.alert_cooldown,
                "thresholds": self.thresholds,
            },
        }


# Module-level singleton used across the app
volatility_monitor = VolatilityMonitor()
