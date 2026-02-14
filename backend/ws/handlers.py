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
                    if "refresh_rate" in settings:
                        event_manager.settings["refresh_rate"] = settings[
                            "refresh_rate"
                        ]
                    if "timeframe_filter" in settings:
                        event_manager.settings["timeframe_filter"] = settings[
                            "timeframe_filter"
                        ]
                    if "chart_options" in settings:
                        event_manager.settings["chart_options"] = settings[
                            "chart_options"
                        ]
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
