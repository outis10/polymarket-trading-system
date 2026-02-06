"""REST endpoints for events data."""

from fastapi import APIRouter, HTTPException

from ..config import load_events_config, get_trading_config, get_ui_config
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
