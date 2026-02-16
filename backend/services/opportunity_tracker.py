"""Opportunity tracking for quant-gated signals and resolved outcomes."""

from __future__ import annotations

import csv
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any


class OpportunityTracker:
    """Track gate-open signals and resolve outcomes at event close."""

    SIGNAL_HEADERS = [
        "signal_id",
        "detected_at_utc",
        "event_id",
        "ticker",
        "timeframe_minutes",
        "side",
        "event_end_utc",
        "price_to_beat",
        "current_price",
        "side_price",
        "yes_price",
        "no_price",
        "quant_prob_side",
        "edge_pct",
        "sample_size",
        "percentile",
        "stake_usd",
        "quant_gate_min_sample",
        "quant_gate_min_edge_pct",
        "quant_gate_use_percentile",
        "quant_gate_percentile_low",
        "quant_gate_percentile_high",
        "quant_gate_min_price_c",
        "quant_gate_max_price_c",
    ]

    OUTCOME_HEADERS = [
        "signal_id",
        "closed_at_utc",
        "event_id",
        "ticker",
        "timeframe_minutes",
        "side",
        "event_end_utc",
        "price_to_beat",
        "close_price",
        "entry_side_price",
        "stake_usd",
        "won",
        "pnl_usd",
        "return_pct",
        "actual_outcome",
        "minutes_to_close",
        "edge_pct_at_signal",
        "sample_size_at_signal",
        "percentile_at_signal",
    ]

    def __init__(self, base_dir: str, stake_usd: float = 100.0):
        self.base_dir = base_dir
        self.signals_path = os.path.join(base_dir, "opportunities_log.csv")
        self.outcomes_path = os.path.join(base_dir, "opportunity_outcomes.csv")
        self.stake_usd = float(stake_usd)
        self._prev_gate_enabled: dict[tuple[str, str], bool] = {}
        self._open_signals: dict[tuple[str, str], list[dict[str, Any]]] = {}
        os.makedirs(self.base_dir, exist_ok=True)
        self._ensure_csv(self.signals_path, self.SIGNAL_HEADERS)
        self._ensure_csv(self.outcomes_path, self.OUTCOME_HEADERS)

    @staticmethod
    def _ensure_csv(path: str, headers: list[str]) -> None:
        if os.path.exists(path):
            return
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return None

    @staticmethod
    def _to_int(value: Any) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        return None

    @staticmethod
    def _parse_iso(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None

    def track_gate_transition(
        self,
        *,
        event_id: str,
        event_dict: dict[str, Any],
        side: str,
        gate_side: dict[str, Any] | None,
        settings: dict[str, Any],
        mode: str,
        now_utc: datetime,
    ) -> None:
        """Log opportunity when gate side transitions disabled -> enabled."""
        if mode != "live":
            return
        if str(settings.get("trading_mode", "manual")).lower() != "bot":
            return

        enabled = (
            bool(gate_side.get("enabled")) if isinstance(gate_side, dict) else False
        )
        key = (event_id, side)
        prev_enabled = self._prev_gate_enabled.get(key, False)
        self._prev_gate_enabled[key] = enabled
        if not enabled or prev_enabled:
            return

        histogram = event_dict.get("quant_range_histogram")
        ticker = ""
        if isinstance(histogram, dict):
            ticker = str(histogram.get("ticker", "")).upper()
        if not ticker:
            ticker = str(event_dict.get("chainlink_symbol", "")).upper()
        if not ticker:
            ticker = "UNKNOWN"

        yes_price = self._to_float(event_dict.get("yes_price")) or 0.5
        no_price = self._to_float(event_dict.get("no_price")) or 0.5
        side_price = yes_price if side == "up" else no_price
        quant_prob_side = self._to_float(
            event_dict.get("quant_prob_up")
            if side == "up"
            else event_dict.get("quant_prob_down")
        )
        edge_pct = (
            self._to_float(gate_side.get("edge_pct"))
            if isinstance(gate_side, dict)
            else None
        )
        sample_size = self._to_int(event_dict.get("quant_sample_size"))
        percentile = (
            self._to_float(histogram.get("current_percentile"))
            if isinstance(histogram, dict)
            else None
        )

        signal = {
            "signal_id": str(uuid.uuid4()),
            "detected_at_utc": now_utc.isoformat(),
            "event_id": event_id,
            "ticker": ticker,
            "timeframe_minutes": int(event_dict.get("timeframe_minutes", 15) or 15),
            "side": side,
            "event_end_utc": event_dict.get("event_end_utc", ""),
            "price_to_beat": self._to_float(event_dict.get("price_to_beat")),
            "current_price": self._to_float(event_dict.get("current_price")),
            "side_price": side_price,
            "yes_price": yes_price,
            "no_price": no_price,
            "quant_prob_side": quant_prob_side,
            "edge_pct": edge_pct,
            "sample_size": sample_size,
            "percentile": percentile,
            "stake_usd": self.stake_usd,
            "quant_gate_min_sample": settings.get("quant_gate_min_sample"),
            "quant_gate_min_edge_pct": settings.get("quant_gate_min_edge_pct"),
            "quant_gate_use_percentile": settings.get("quant_gate_use_percentile"),
            "quant_gate_percentile_low": settings.get("quant_gate_percentile_low"),
            "quant_gate_percentile_high": settings.get("quant_gate_percentile_high"),
            "quant_gate_min_price_c": settings.get("quant_gate_min_price_c"),
            "quant_gate_max_price_c": settings.get("quant_gate_max_price_c"),
        }

        with open(self.signals_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.SIGNAL_HEADERS)
            writer.writerow(signal)

        self._open_signals.setdefault(key, []).append(signal)

    def resolve_closed_events(
        self, events: dict[str, dict[str, Any]], now_utc: datetime
    ) -> None:
        """Resolve open signals when event is closed and persist outcomes."""
        keys = list(self._open_signals.keys())
        for key in keys:
            event_id, side = key
            event = events.get(event_id)
            if not event:
                continue
            end_dt = self._parse_iso(event.get("event_end_utc"))
            if not end_dt or now_utc < end_dt:
                continue

            price_to_beat = self._to_float(event.get("price_to_beat"))
            close_price = self._to_float(event.get("current_price"))
            if price_to_beat is None or close_price is None:
                continue

            actual_up = close_price >= price_to_beat
            won = actual_up if side == "up" else not actual_up
            actual_outcome = "up" if actual_up else "down"

            pending = self._open_signals.get(key, [])
            if not pending:
                continue

            with open(self.outcomes_path, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.OUTCOME_HEADERS)
                for signal in pending:
                    stake = self._to_float(signal.get("stake_usd")) or self.stake_usd
                    entry_side_price = self._to_float(signal.get("side_price")) or 0.5
                    if won:
                        pnl = stake * (1.0 / max(0.0001, entry_side_price) - 1.0)
                    else:
                        pnl = -stake
                    detected_at = self._parse_iso(signal.get("detected_at_utc"))
                    minutes_to_close = None
                    if detected_at:
                        minutes_to_close = (end_dt - detected_at).total_seconds() / 60.0

                    writer.writerow(
                        {
                            "signal_id": signal.get("signal_id"),
                            "closed_at_utc": now_utc.isoformat(),
                            "event_id": event_id,
                            "ticker": signal.get("ticker"),
                            "timeframe_minutes": signal.get("timeframe_minutes"),
                            "side": side,
                            "event_end_utc": event.get("event_end_utc", ""),
                            "price_to_beat": price_to_beat,
                            "close_price": close_price,
                            "entry_side_price": entry_side_price,
                            "stake_usd": stake,
                            "won": "1" if won else "0",
                            "pnl_usd": pnl,
                            "return_pct": (pnl / stake * 100.0) if stake > 0 else 0.0,
                            "actual_outcome": actual_outcome,
                            "minutes_to_close": minutes_to_close,
                            "edge_pct_at_signal": signal.get("edge_pct"),
                            "sample_size_at_signal": signal.get("sample_size"),
                            "percentile_at_signal": signal.get("percentile"),
                        }
                    )

            self._open_signals.pop(key, None)

    def summarize_outcomes(
        self, days: int = 7, ticker: str | None = None
    ) -> list[dict[str, Any]]:
        """Return per-ticker aggregated outcomes for recent days."""
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=max(1, int(days)))
        rows: list[dict[str, Any]] = []
        if not os.path.exists(self.outcomes_path):
            return rows

        with open(self.outcomes_path, newline="") as f:
            for row in csv.DictReader(f):
                closed = self._parse_iso(row.get("closed_at_utc"))
                if not closed or closed < cutoff:
                    continue
                row_ticker = str(row.get("ticker", "")).upper()
                if ticker and row_ticker != ticker.upper():
                    continue
                rows.append(row)

        grouped: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            tk = str(r.get("ticker", "")).upper() or "UNKNOWN"
            grouped.setdefault(tk, []).append(r)

        summary: list[dict[str, Any]] = []
        for tk, tk_rows in grouped.items():
            total = len(tk_rows)
            wins = sum(1 for r in tk_rows if str(r.get("won")) == "1")
            pnl = sum(float(r.get("pnl_usd") or 0.0) for r in tk_rows)
            avg_edge = (
                sum(float(r.get("edge_pct_at_signal") or 0.0) for r in tk_rows) / total
                if total > 0
                else 0.0
            )
            avg_minutes = (
                sum(float(r.get("minutes_to_close") or 0.0) for r in tk_rows) / total
                if total > 0
                else 0.0
            )
            summary.append(
                {
                    "ticker": tk,
                    "signals": total,
                    "wins": wins,
                    "hit_rate_pct": (wins / total * 100.0) if total > 0 else 0.0,
                    "total_pnl_usd": pnl,
                    "avg_edge_pct": avg_edge,
                    "avg_minutes_to_close": avg_minutes,
                }
            )

        summary.sort(key=lambda x: (-x["signals"], x["ticker"]))
        return summary
