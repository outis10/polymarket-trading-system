"""WebSocket endpoint: /ws/events."""

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..middleware.auth import verify_ws_api_key
from ..services.event_manager import event_manager
from .manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """WebSocket endpoint for real-time event data streaming."""
    if not verify_ws_api_key(websocket):
        await websocket.close(code=4401, reason="Invalid or missing API key")
        return
    await manager.connect(websocket)

    # Send initial snapshot immediately
    try:
        snapshot = {
            "type": "full_snapshot",
            "event_id": "",
            "data": {
                "events": event_manager.events,
                "settings": event_manager.settings,
            },
        }
        await websocket.send_text(json.dumps(snapshot))
    except Exception as e:
        logger.error("Error sending initial snapshot: %s", e)

    try:
        while True:
            # Listen for client messages (settings changes, mode switch, etc.)
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")

                if msg_type == "switch_mode":
                    new_mode = msg.get("mode", "demo")
                    await event_manager.switch_mode(new_mode)

                elif msg_type == "update_settings":
                    settings = msg.get("settings", {})
                    changed_keys: set[str] = set()
                    if isinstance(settings, dict):
                        changed_keys = {
                            key
                            for key in settings.keys()
                            if key in event_manager._persisted_setting_keys
                            and key != "mode"
                        }
                        # Generic merge first so newly added persisted keys do not get
                        # dropped when frontend/backend evolve at different times.
                        for key, value in settings.items():
                            if (
                                key in event_manager._persisted_setting_keys
                                and key != "mode"
                            ):
                                event_manager.settings[key] = value
                    if "refresh_rate" in settings:
                        event_manager.settings["refresh_rate"] = settings[
                            "refresh_rate"
                        ]
                    if "timeframe_filter" in settings:
                        event_manager.settings["timeframe_filter"] = settings[
                            "timeframe_filter"
                        ]
                    if "trading_mode" in settings:
                        event_manager.settings["trading_mode"] = settings[
                            "trading_mode"
                        ]
                    if "chart_options" in settings:
                        event_manager.settings["chart_options"] = settings[
                            "chart_options"
                        ]
                    if "kelly_enabled" in settings:
                        event_manager.settings["kelly_enabled"] = bool(
                            settings["kelly_enabled"]
                        )
                    if "kelly_fraction" in settings:
                        event_manager.settings["kelly_fraction"] = float(
                            settings["kelly_fraction"]
                        )
                    if "kelly_bankroll" in settings:
                        event_manager.settings["kelly_bankroll"] = float(
                            settings["kelly_bankroll"]
                        )
                    if "kelly_live_bankroll_usd" in settings:
                        event_manager.settings["kelly_live_bankroll_usd"] = float(
                            settings["kelly_live_bankroll_usd"]
                        )
                    if "kelly_paper_bankroll_usd" in settings:
                        event_manager.settings["kelly_paper_bankroll_usd"] = float(
                            settings["kelly_paper_bankroll_usd"]
                        )
                    if "paper_compound_enabled" in settings:
                        event_manager.settings["paper_compound_enabled"] = bool(
                            settings["paper_compound_enabled"]
                        )
                    if "paper_current_bankroll_usd" in settings:
                        event_manager.settings["paper_current_bankroll_usd"] = float(
                            settings["paper_current_bankroll_usd"]
                        )
                    if "kelly_min_edge_pct" in settings:
                        event_manager.settings["kelly_min_edge_pct"] = float(
                            settings["kelly_min_edge_pct"]
                        )
                    if "kelly_max_bet_pct" in settings:
                        event_manager.settings["kelly_max_bet_pct"] = float(
                            settings["kelly_max_bet_pct"]
                        )
                    if "kelly_max_event_exposure_pct" in settings:
                        event_manager.settings["kelly_max_event_exposure_pct"] = float(
                            settings["kelly_max_event_exposure_pct"]
                        )
                    if "quant_gate_enabled" in settings:
                        event_manager.settings["quant_gate_enabled"] = bool(
                            settings["quant_gate_enabled"]
                        )
                    if "quant_gate_min_sample" in settings:
                        event_manager.settings["quant_gate_min_sample"] = int(
                            settings["quant_gate_min_sample"]
                        )
                    if "quant_gate_min_edge_pct" in settings:
                        event_manager.settings["quant_gate_min_edge_pct"] = float(
                            settings["quant_gate_min_edge_pct"]
                        )
                    if "quant_gate_min_price_c" in settings:
                        event_manager.settings["quant_gate_min_price_c"] = float(
                            settings["quant_gate_min_price_c"]
                        )
                    if "quant_gate_max_price_c" in settings:
                        event_manager.settings["quant_gate_max_price_c"] = float(
                            settings["quant_gate_max_price_c"]
                        )
                    if "quant_gate_edge_vs_ask_enabled" in settings:
                        event_manager.settings["quant_gate_edge_vs_ask_enabled"] = bool(
                            settings["quant_gate_edge_vs_ask_enabled"]
                        )
                    if "quant_gate_min_edge_vs_ask_pct" in settings:
                        event_manager.settings["quant_gate_min_edge_vs_ask_pct"] = (
                            float(settings["quant_gate_min_edge_vs_ask_pct"])
                        )
                    if "quant_gate_min_ask_price" in settings:
                        event_manager.settings["quant_gate_min_ask_price"] = float(
                            settings["quant_gate_min_ask_price"]
                        )
                    if "quant_gate_max_ask_price" in settings:
                        event_manager.settings["quant_gate_max_ask_price"] = float(
                            settings["quant_gate_max_ask_price"]
                        )
                    if "quant_gate_min_prob" in settings:
                        event_manager.settings["quant_gate_min_prob"] = float(
                            settings["quant_gate_min_prob"]
                        )
                    if "quant_gate_blocked_hours_pst" in settings:
                        raw = settings["quant_gate_blocked_hours_pst"]
                        if isinstance(raw, list):
                            event_manager.settings["quant_gate_blocked_hours_pst"] = [
                                int(h) for h in raw if 0 <= int(h) <= 23
                            ]
                    if "quant_gate_enabled_slots" in settings:
                        raw = settings["quant_gate_enabled_slots"]
                        if isinstance(raw, list):
                            event_manager.settings["quant_gate_enabled_slots"] = [
                                int(s)
                                for s in raw
                                if isinstance(s, (int, float)) and 1 <= int(s) <= 30
                            ]
                    if "monitored_tickers" in settings:
                        raw_tickers = settings["monitored_tickers"]
                        if isinstance(raw_tickers, list):
                            event_manager.settings["monitored_tickers"] = [
                                str(t).upper().strip()
                                for t in raw_tickers
                                if str(t).strip()
                            ]
                    if "bot_risk_enabled" in settings:
                        event_manager.settings["bot_risk_enabled"] = bool(
                            settings["bot_risk_enabled"]
                        )
                    if "bot_max_buys_per_event_side" in settings:
                        event_manager.settings["bot_max_buys_per_event_side"] = int(
                            settings["bot_max_buys_per_event_side"]
                        )
                    if "bot_cooldown_seconds_per_event_side" in settings:
                        event_manager.settings[
                            "bot_cooldown_seconds_per_event_side"
                        ] = int(settings["bot_cooldown_seconds_per_event_side"])
                    if "bot_global_min_seconds_between_orders" in settings:
                        event_manager.settings[
                            "bot_global_min_seconds_between_orders"
                        ] = int(settings["bot_global_min_seconds_between_orders"])
                    if "bot_max_event_exposure_pct" in settings:
                        event_manager.settings["bot_max_event_exposure_pct"] = float(
                            settings["bot_max_event_exposure_pct"]
                        )
                    if "bot_drawdown_enabled" in settings:
                        event_manager.settings["bot_drawdown_enabled"] = bool(
                            settings["bot_drawdown_enabled"]
                        )
                    if "bot_drawdown_stop_pct" in settings:
                        event_manager.settings["bot_drawdown_stop_pct"] = float(
                            settings["bot_drawdown_stop_pct"]
                        )
                    if "bot_order_notional_cap_usd" in settings:
                        event_manager.settings["bot_order_notional_cap_usd"] = float(
                            settings["bot_order_notional_cap_usd"]
                        )
                    if "bot_paper_mode" in settings:
                        event_manager.settings["bot_paper_mode"] = bool(
                            settings["bot_paper_mode"]
                        )
                    if "bot_second_entry_opposite_enabled" in settings:
                        event_manager.settings["bot_second_entry_opposite_enabled"] = (
                            bool(settings["bot_second_entry_opposite_enabled"])
                        )
                    if "bot_second_entry_max_ask_price" in settings:
                        event_manager.settings["bot_second_entry_max_ask_price"] = (
                            float(settings["bot_second_entry_max_ask_price"])
                        )
                    if "bot_second_entry_min_edge_pct" in settings:
                        event_manager.settings["bot_second_entry_min_edge_pct"] = float(
                            settings["bot_second_entry_min_edge_pct"]
                        )
                    if "pm_min_shares" in settings:
                        event_manager.settings["pm_min_shares"] = float(
                            settings["pm_min_shares"]
                        )
                    if "pm_min_notional_usd" in settings:
                        event_manager.settings["pm_min_notional_usd"] = float(
                            settings["pm_min_notional_usd"]
                        )
                    if "vol_gate_enabled" in settings:
                        event_manager.settings["vol_gate_enabled"] = bool(
                            settings["vol_gate_enabled"]
                        )
                    if "vol_gate_lookback_n" in settings:
                        event_manager.settings["vol_gate_lookback_n"] = int(
                            settings["vol_gate_lookback_n"]
                        )
                    if "vol_gate_min_pct_of_avg" in settings:
                        event_manager.settings["vol_gate_min_pct_of_avg"] = float(
                            settings["vol_gate_min_pct_of_avg"]
                        )
                    event_manager.handle_runtime_settings_side_effects(changed_keys)
                    event_manager.persist_runtime_settings()
                    await manager.broadcast(
                        {
                            "type": "settings_update",
                            "event_id": "",
                            "data": event_manager.settings,
                        }
                    )

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
