"""WebSocket endpoint: /ws/events."""

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services.event_manager import event_manager
from .manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """WebSocket endpoint for real-time event data streaming."""
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
                    if isinstance(settings, dict):
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
                    if "quant_gate_use_percentile" in settings:
                        event_manager.settings["quant_gate_use_percentile"] = bool(
                            settings["quant_gate_use_percentile"]
                        )
                    if "quant_gate_percentile_low" in settings:
                        event_manager.settings["quant_gate_percentile_low"] = float(
                            settings["quant_gate_percentile_low"]
                        )
                    if "quant_gate_percentile_high" in settings:
                        event_manager.settings["quant_gate_percentile_high"] = float(
                            settings["quant_gate_percentile_high"]
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
                    if "bot_max_ticker_exposure_pct" in settings:
                        event_manager.settings["bot_max_ticker_exposure_pct"] = float(
                            settings["bot_max_ticker_exposure_pct"]
                        )
                    if "bot_order_notional_cap_usd" in settings:
                        event_manager.settings["bot_order_notional_cap_usd"] = float(
                            settings["bot_order_notional_cap_usd"]
                        )
                    if "pm_min_shares" in settings:
                        event_manager.settings["pm_min_shares"] = float(
                            settings["pm_min_shares"]
                        )
                    if "pm_min_notional_usd" in settings:
                        event_manager.settings["pm_min_notional_usd"] = float(
                            settings["pm_min_notional_usd"]
                        )
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
