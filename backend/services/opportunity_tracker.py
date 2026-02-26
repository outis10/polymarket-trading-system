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

    BLOCKED_HEADERS = [
        "blocked_id",
        "detected_at_utc",
        "event_id",
        "ticker",
        "timeframe_minutes",
        "side",
        "blocked_reason",
        "estimated_stake_usd",
        "estimated_shares",
        "side_price",
        "event_end_utc",
        "price_to_beat",
        "current_price",
        "quant_prob_side",
        "edge_pct",
        "sample_size",
        "percentile",
    ]

    def __init__(
        self,
        base_dir: str,
        stake_usd: float = 100.0,
        close_guard_seconds: int = 5,
        signal_cooldown_seconds: int = 60,
    ):
        self.base_dir = base_dir
        self.signals_path = os.path.join(base_dir, "opportunities_log.csv")
        self.outcomes_path = os.path.join(base_dir, "opportunity_outcomes.csv")
        self.blocked_path = os.path.join(base_dir, "opportunity_blocked.csv")
        self.stake_usd = float(stake_usd)
        self.close_guard_seconds = max(0, int(close_guard_seconds))
        self.signal_cooldown_seconds = max(0, int(signal_cooldown_seconds))
        self._prev_gate_enabled: dict[tuple[str, str], bool] = {}
        self._open_signals: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._resolved_signal_ids: set[str] = set()
        self._last_signal_at: dict[tuple[str, str], datetime] = {}
        self._last_blocked_at: dict[tuple[str, str], datetime] = {}
        self._last_reconcile_at: datetime | None = None
        self._event_cache: dict[str, dict[str, Any]] = {}
        os.makedirs(self.base_dir, exist_ok=True)
        self._ensure_csv(self.signals_path, self.SIGNAL_HEADERS)
        self._ensure_csv(self.outcomes_path, self.OUTCOME_HEADERS)
        self._ensure_csv(self.blocked_path, self.BLOCKED_HEADERS)
        self._hydrate_runtime_state_from_csv()

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
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return float(text)
            except Exception:
                return None
        return None

    @staticmethod
    def _to_int(value: Any) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return int(float(text))
            except Exception:
                return None
        return None

    @staticmethod
    def _parse_iso(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None

    @staticmethod
    def _normalize_ticker(raw: Any) -> str:
        text = str(raw or "").strip().upper()
        if text.endswith("USDT") and len(text) > 4:
            text = text[:-4]
        return text

    @staticmethod
    def _load_csv_rows(path: str) -> list[dict[str, Any]]:
        if not os.path.exists(path):
            return []
        with open(path, newline="") as f:
            return list(csv.DictReader(f))

    def _hydrate_runtime_state_from_csv(self) -> None:
        self._resolved_signal_ids = {
            str(row.get("signal_id", "")).strip()
            for row in self._load_csv_rows(self.outcomes_path)
            if str(row.get("signal_id", "")).strip()
        }
        self._open_signals.clear()
        self._last_signal_at.clear()
        self._last_blocked_at.clear()
        for row in self._load_csv_rows(self.signals_path):
            signal_id = str(row.get("signal_id", "")).strip()
            event_id = str(row.get("event_id", "")).strip()
            side = str(row.get("side", "")).strip().lower()
            if not signal_id or not event_id or side not in {"up", "down"}:
                continue
            detected_at = self._parse_iso(row.get("detected_at_utc"))
            key = (event_id, side)
            if detected_at:
                prev = self._last_signal_at.get(key)
                if prev is None or detected_at > prev:
                    self._last_signal_at[key] = detected_at
            if signal_id in self._resolved_signal_ids:
                continue
            self._open_signals.setdefault(key, []).append(row)

        for row in self._load_csv_rows(self.blocked_path):
            event_id = str(row.get("event_id", "")).strip()
            side = str(row.get("side", "")).strip().lower()
            if not event_id or side not in {"up", "down"}:
                continue
            blocked_at = self._parse_iso(row.get("detected_at_utc"))
            if not blocked_at:
                continue
            key = (event_id, side)
            prev = self._last_blocked_at.get(key)
            if prev is None or blocked_at > prev:
                self._last_blocked_at[key] = blocked_at

    def _build_outcome_row(
        self,
        *,
        signal: dict[str, Any],
        event_id: str,
        side: str,
        event_end_utc: str,
        price_to_beat: float,
        close_price: float,
        now_utc: datetime,
    ) -> dict[str, Any]:
        actual_up = close_price >= price_to_beat
        won = actual_up if side == "up" else not actual_up
        actual_outcome = "up" if actual_up else "down"
        stake = self._to_float(signal.get("stake_usd")) or self.stake_usd
        entry_side_price = self._to_float(signal.get("side_price")) or 0.5
        if won:
            pnl = stake * (1.0 / max(0.0001, entry_side_price) - 1.0)
        else:
            pnl = -stake

        minutes_to_close = None
        detected_at = self._parse_iso(signal.get("detected_at_utc"))
        end_dt = self._parse_iso(event_end_utc)
        if detected_at and end_dt:
            minutes_to_close = max(0.0, (end_dt - detected_at).total_seconds() / 60.0)

        return {
            "signal_id": signal.get("signal_id"),
            "closed_at_utc": now_utc.isoformat(),
            "event_id": event_id,
            "ticker": signal.get("ticker"),
            "timeframe_minutes": signal.get("timeframe_minutes"),
            "side": side,
            "event_end_utc": event_end_utc,
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

    def _refresh_event_cache(
        self, events: dict[str, dict[str, Any]], now_utc: datetime
    ) -> None:
        for event_id, event in events.items():
            self._event_cache[event_id] = {
                "event_end_utc": event.get("event_end_utc"),
                "price_to_beat": self._to_float(event.get("price_to_beat")),
                "close_price": self._to_float(event.get("current_price")),
                "cached_at_utc": now_utc.isoformat(),
            }

    def _derive_resolution_context_from_signals(
        self, pending: list[dict[str, Any]]
    ) -> tuple[str, float | None, float | None]:
        event_end_utc = ""
        latest_detected: datetime | None = None
        fallback_close_price: float | None = None
        fallback_price_to_beat: float | None = None

        for signal in pending:
            raw_end = str(signal.get("event_end_utc", "")).strip()
            if raw_end:
                event_end_utc = raw_end
            ptb = self._to_float(signal.get("price_to_beat"))
            if ptb is not None:
                fallback_price_to_beat = ptb
            cp = self._to_float(signal.get("current_price"))
            detected = self._parse_iso(signal.get("detected_at_utc"))
            if cp is not None:
                if latest_detected is None:
                    latest_detected = detected
                    fallback_close_price = cp
                elif detected and latest_detected and detected >= latest_detected:
                    latest_detected = detected
                    fallback_close_price = cp

        return event_end_utc, fallback_price_to_beat, fallback_close_price

    def _resolve_pending_for_key(
        self,
        *,
        event_id: str,
        side: str,
        pending: list[dict[str, Any]],
        event: dict[str, Any] | None,
        now_utc: datetime,
    ) -> bool:
        event_end_utc = ""
        price_to_beat: float | None = None
        close_price: float | None = None

        if event is not None:
            event_end_utc = str(event.get("event_end_utc", "")).strip()
            price_to_beat = self._to_float(event.get("price_to_beat"))
            close_price = self._to_float(event.get("current_price"))
        else:
            cached = self._event_cache.get(event_id, {})
            event_end_utc = str(cached.get("event_end_utc", "")).strip()
            price_to_beat = self._to_float(cached.get("price_to_beat"))
            close_price = self._to_float(cached.get("close_price"))

            s_end, s_ptb, s_cp = self._derive_resolution_context_from_signals(pending)
            if not event_end_utc:
                event_end_utc = s_end
            if price_to_beat is None:
                price_to_beat = s_ptb
            if close_price is None:
                close_price = s_cp

        end_dt = self._parse_iso(event_end_utc)
        if not end_dt or now_utc < end_dt:
            return False
        if price_to_beat is None or close_price is None:
            return False

        outcome_rows: list[dict[str, Any]] = []
        resolved_ids: list[str] = []
        for signal in pending:
            signal_id = str(signal.get("signal_id", "")).strip()
            if not signal_id or signal_id in self._resolved_signal_ids:
                continue
            outcome_rows.append(
                self._build_outcome_row(
                    signal=signal,
                    event_id=event_id,
                    side=side,
                    event_end_utc=event_end_utc,
                    price_to_beat=price_to_beat,
                    close_price=close_price,
                    now_utc=now_utc,
                )
            )
            resolved_ids.append(signal_id)

        if not outcome_rows:
            return True

        with open(self.outcomes_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.OUTCOME_HEADERS)
            for row in outcome_rows:
                writer.writerow(row)
        self._resolved_signal_ids.update(resolved_ids)
        return True

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
        stake_usd_override: float | None = None,
        blocked_reason: str | None = None,
        estimated_shares: float | None = None,
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
        if self._open_signals.get(key):
            return

        event_end = self._parse_iso(event_dict.get("event_end_utc"))
        if event_end and now_utc >= (
            event_end - timedelta(seconds=self.close_guard_seconds)
        ):
            return
        last_signal = self._last_signal_at.get(key)
        last_blocked = self._last_blocked_at.get(key)
        last_emission = last_signal
        if last_emission is None or (
            last_blocked is not None and last_blocked > last_emission
        ):
            last_emission = last_blocked
        if (
            last_emission is not None
            and self.signal_cooldown_seconds > 0
            and now_utc
            < (last_emission + timedelta(seconds=self.signal_cooldown_seconds))
        ):
            return

        histogram = event_dict.get("quant_range_histogram")
        ticker = ""
        if isinstance(histogram, dict):
            ticker = self._normalize_ticker(histogram.get("ticker"))
        if not ticker:
            ticker = self._normalize_ticker(event_dict.get("chainlink_symbol"))
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
            "stake_usd": (
                float(stake_usd_override)
                if isinstance(stake_usd_override, (int, float))
                and float(stake_usd_override) > 0
                else self.stake_usd
            ),
            "quant_gate_min_sample": settings.get("quant_gate_min_sample"),
            "quant_gate_min_edge_pct": settings.get("quant_gate_min_edge_pct"),
            "quant_gate_use_percentile": settings.get("quant_gate_use_percentile"),
            "quant_gate_percentile_low": settings.get("quant_gate_percentile_low"),
            "quant_gate_percentile_high": settings.get("quant_gate_percentile_high"),
            "quant_gate_min_price_c": settings.get("quant_gate_min_price_c"),
            "quant_gate_max_price_c": settings.get("quant_gate_max_price_c"),
        }

        if blocked_reason:
            estimated_stake_usd = (
                float(stake_usd_override)
                if isinstance(stake_usd_override, (int, float))
                and float(stake_usd_override) > 0
                else ""
            )
            blocked_row = {
                "blocked_id": str(uuid.uuid4()),
                "detected_at_utc": now_utc.isoformat(),
                "event_id": event_id,
                "ticker": ticker,
                "timeframe_minutes": int(event_dict.get("timeframe_minutes", 15) or 15),
                "side": side,
                "blocked_reason": str(blocked_reason),
                "estimated_stake_usd": estimated_stake_usd,
                "estimated_shares": (
                    float(estimated_shares)
                    if isinstance(estimated_shares, (float, int))
                    else None
                ),
                "side_price": side_price,
                "event_end_utc": event_dict.get("event_end_utc", ""),
                "price_to_beat": self._to_float(event_dict.get("price_to_beat")),
                "current_price": self._to_float(event_dict.get("current_price")),
                "quant_prob_side": quant_prob_side,
                "edge_pct": edge_pct,
                "sample_size": sample_size,
                "percentile": percentile,
            }
            with open(self.blocked_path, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.BLOCKED_HEADERS)
                writer.writerow(blocked_row)
            self._last_blocked_at[key] = now_utc
            return

        with open(self.signals_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.SIGNAL_HEADERS)
            writer.writerow(signal)

        self._open_signals.setdefault(key, []).append(signal)
        self._last_signal_at[key] = now_utc

    def resolve_closed_events(
        self, events: dict[str, dict[str, Any]], now_utc: datetime
    ) -> None:
        """Resolve open signals when event is closed and persist outcomes."""
        self._refresh_event_cache(events, now_utc)
        keys = list(self._open_signals.keys())
        for key in keys:
            event_id, side = key
            pending = self._open_signals.get(key, [])
            if not pending:
                continue
            resolved = self._resolve_pending_for_key(
                event_id=event_id,
                side=side,
                pending=pending,
                event=events.get(event_id),
                now_utc=now_utc,
            )
            if resolved:
                self._open_signals.pop(key, None)

        # Backfill unresolved signals from CSV to avoid missed outcomes after restarts.
        should_reconcile = self._last_reconcile_at is None or now_utc >= (
            self._last_reconcile_at + timedelta(seconds=30)
        )
        if should_reconcile:
            self._reconcile_unresolved_from_csv(events=events, now_utc=now_utc)
            self._last_reconcile_at = now_utc

    def _reconcile_unresolved_from_csv(
        self, *, events: dict[str, dict[str, Any]], now_utc: datetime
    ) -> None:
        newly_resolved_ids: set[str] = set()
        unresolved_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._resolved_signal_ids = {
            str(row.get("signal_id", "")).strip()
            for row in self._load_csv_rows(self.outcomes_path)
            if str(row.get("signal_id", "")).strip()
        }

        for signal in self._load_csv_rows(self.signals_path):
            signal_id = str(signal.get("signal_id", "")).strip()
            event_id = str(signal.get("event_id", "")).strip()
            side = str(signal.get("side", "")).strip().lower()
            if (
                not signal_id
                or not event_id
                or side not in {"up", "down"}
                or signal_id in self._resolved_signal_ids
            ):
                continue
            unresolved_by_key.setdefault((event_id, side), []).append(signal)

        for (event_id, side), pending in unresolved_by_key.items():
            before = len(self._resolved_signal_ids)
            self._resolve_pending_for_key(
                event_id=event_id,
                side=side,
                pending=pending,
                event=events.get(event_id),
                now_utc=now_utc,
            )
            after = len(self._resolved_signal_ids)
            if after > before:
                newly_resolved_ids.update(
                    {
                        str(signal.get("signal_id", "")).strip()
                        for signal in pending
                        if str(signal.get("signal_id", "")).strip()
                        in self._resolved_signal_ids
                    }
                )

        if newly_resolved_ids:
            self._hydrate_runtime_state_from_csv()

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
