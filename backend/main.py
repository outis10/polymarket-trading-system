"""FastAPI application entry point."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .middleware.auth import APIKeyMiddleware
from .routers import events, trading
from .services.event_manager import event_manager
from .ws.handlers import router as ws_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_AUTO_REDEEM_CHECK_INTERVAL = 30 * 60   # check every 30 min
_AUTO_REDEEM_COOLDOWN       = 2 * 60 * 60  # min 2h between executions


async def _auto_redeem_loop() -> None:
    """
    Background task: periodically redeem claimable positions when the
    accumulated value meets the configured threshold.

    Controlled via runtime_settings:
      auto_redeem_enabled        (bool)  – master switch, default False
      auto_redeem_threshold_usd  (float) – minimum fixed USD to trigger
      auto_redeem_bankroll_pct   (float) – minimum % of live bankroll to trigger
    Effective threshold = max(threshold_usd, bankroll * bankroll_pct)
    """
    from .routers.trading import _fetch_claimable_sync, _redeem_positions_sync
    from .services.polymarket import get_client

    last_redeem_ts: float = 0.0

    await asyncio.sleep(90)  # let the app finish starting up

    while True:
        try:
            settings = event_manager.settings

            # Master switch
            if not settings.get("auto_redeem_enabled", False):
                await asyncio.sleep(_AUTO_REDEEM_CHECK_INTERVAL)
                continue

            # Skip in demo / paper mode
            if event_manager.mode == "demo" or settings.get("bot_paper_mode", False):
                await asyncio.sleep(_AUTO_REDEEM_CHECK_INTERVAL)
                continue

            # Cooldown
            import time as _time
            now = _time.monotonic()
            if (now - last_redeem_ts) < _AUTO_REDEEM_COOLDOWN:
                await asyncio.sleep(_AUTO_REDEEM_CHECK_INTERVAL)
                continue

            client = get_client()
            if not client:
                await asyncio.sleep(_AUTO_REDEEM_CHECK_INTERVAL)
                continue

            wallet = getattr(client.config, "funder", None)
            private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
            chain_id = int(os.getenv("CHAIN_ID", "137"))

            if not wallet or not private_key:
                await asyncio.sleep(_AUTO_REDEEM_CHECK_INTERVAL)
                continue

            # Fetch claimable (bypasses cache)
            claimable = await asyncio.to_thread(_fetch_claimable_sync, wallet)
            claimable_usd = float(claimable.get("claimable_usd") or 0.0)

            # Keep event_manager informed so the drawdown circuit breaker can use it
            event_manager._last_claimable_usd = claimable_usd

            if claimable_usd <= 0:
                await asyncio.sleep(_AUTO_REDEEM_CHECK_INTERVAL)
                continue

            # Compute effective threshold
            threshold_usd = float(settings.get("auto_redeem_threshold_usd", 20.0))
            bankroll_pct  = float(settings.get("auto_redeem_bankroll_pct", 0.03))
            bankroll      = float(settings.get("kelly_live_bankroll_usd", 100.0))
            effective_threshold = max(threshold_usd, bankroll * bankroll_pct)

            if claimable_usd < effective_threshold:
                logger.debug(
                    "Auto-redeem: $%.2f claimable < $%.2f threshold — skipping",
                    claimable_usd, effective_threshold,
                )
                await asyncio.sleep(_AUTO_REDEEM_CHECK_INTERVAL)
                continue

            # Trigger redeem
            logger.info(
                "Auto-redeem triggered: $%.2f claimable >= $%.2f threshold",
                claimable_usd, effective_threshold,
            )
            positions = [p for p in claimable.get("positions", []) if p.get("condition_id")]
            if positions:
                results = await asyncio.to_thread(
                    _redeem_positions_sync, private_key, wallet, chain_id, positions
                )
                sent   = [r for r in results if r.get("status") == "sent"]
                failed = [r for r in results if r.get("status") == "failed"]
                total  = sum(r.get("value_usd", 0.0) for r in sent)
                logger.info(
                    "Auto-redeem complete: sent=%d failed=%d total_usd=%.2f",
                    len(sent), len(failed), total,
                )
                last_redeem_ts = now

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Auto-redeem loop error: %s", exc)

        await asyncio.sleep(_AUTO_REDEEM_CHECK_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Starting EventManager...")
    await event_manager.start()

    redeem_task = asyncio.create_task(_auto_redeem_loop(), name="auto_redeem")

    yield

    redeem_task.cancel()
    try:
        await redeem_task
    except asyncio.CancelledError:
        pass

    logger.info("Stopping EventManager...")
    await event_manager.stop()


app = FastAPI(title="Polymarket Monitor API", lifespan=lifespan)

# CORS — origins from env (comma-separated) or localhost defaults for dev
_cors_origins_env = os.getenv("ALLOWED_ORIGINS", "")
_cors_origins = (
    [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
    if _cors_origins_env
    else ["http://localhost:5173", "http://localhost:3000"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-API-Key"],
)

# API Key middleware — validates X-API-Key header on all REST requests
app.add_middleware(APIKeyMiddleware)

# REST routers
app.include_router(events.router)
app.include_router(trading.router)

# WebSocket router
app.include_router(ws_router)

# Serve frontend build if dist/ exists (production / ngrok mode)
_dist_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_dist_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(_dist_dir, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        index = os.path.join(_dist_dir, "index.html")
        return FileResponse(index)


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
