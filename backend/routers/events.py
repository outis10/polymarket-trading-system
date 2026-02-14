"""REST endpoints for events data."""

from fastapi import APIRouter, HTTPException

from ..config import get_trading_config, get_ui_config, load_events_config
from ..services.event_manager import event_manager

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events")
async def get_events():
    """Get all current events with their data."""
    return {"events": event_manager.events, "settings": event_manager.settings}


@router.get("/events/{event_id}")
async def get_event(event_id: str):
    """Get a single event by ID."""
    event = event_manager.events.get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")
    return event


@router.get("/config")
async def get_config():
    """Get application configuration (trading + UI)."""
    config = load_events_config()
    return {
        "trading": get_trading_config(config),
        "ui": get_ui_config(config),
    }


@router.post("/events/refresh-live")
async def refresh_live_events(force: bool = True):
    """Force refresh of live-discovered events and broadcast to all clients."""
    result = await event_manager.refresh_live_events(force=force)

    if not result.get("ok"):
        reason = result.get("reason", "refresh_failed")
        if reason == "mode_not_live":
            raise HTTPException(
                status_code=409,
                detail="Live refresh is only available when mode is 'live'",
            )
        if reason == "live_discovery_disabled":
            raise HTTPException(
                status_code=409,
                detail="live_discovery.enabled is false in config/events.yaml",
            )
        raise HTTPException(status_code=500, detail=f"Live refresh failed: {reason}")

    return result
