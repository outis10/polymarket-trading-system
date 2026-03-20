"""Localhost-only control API for Telegram and private automation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..services.control_service import control_service

router = APIRouter(prefix="/api/control", tags=["control"])


def _assert_local_request(request: Request) -> None:
    host = (request.client.host if request.client else "") or ""
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="Control API is localhost-only")


def _actor_from_request(request: Request) -> dict[str, Any]:
    return {
        "source": request.headers.get("X-Control-Source", "control-api"),
        "actor": request.headers.get("X-Control-Actor", ""),
        "chat_id": request.headers.get("X-Control-Chat-Id", ""),
        "user_id": request.headers.get("X-Control-User-Id", ""),
    }


@router.get("/status")
async def control_status(request: Request):
    _assert_local_request(request)
    return await control_service.get_status()


@router.get("/instance")
async def control_instance(request: Request):
    _assert_local_request(request)
    return await control_service.get_instance_info()


@router.get("/health")
async def control_health(request: Request):
    _assert_local_request(request)
    return await control_service.get_health()


@router.get("/pnl-today")
async def control_pnl_today(request: Request):
    _assert_local_request(request)
    return await control_service.get_pnl_today()


@router.get("/positions")
async def control_positions(request: Request):
    _assert_local_request(request)
    return await control_service.get_positions()


@router.get("/orders")
async def control_orders(request: Request):
    _assert_local_request(request)
    return await control_service.get_orders()


@router.post("/pause")
async def control_pause(request: Request):
    _assert_local_request(request)
    return await control_service.pause(actor=_actor_from_request(request))


@router.post("/resume")
async def control_resume(request: Request):
    _assert_local_request(request)
    return await control_service.resume(actor=_actor_from_request(request))


@router.post("/mode")
async def control_mode(request: Request, payload: dict[str, Any]):
    _assert_local_request(request)
    try:
        return await control_service.set_trading_mode(
            payload.get("mode", ""),
            actor=_actor_from_request(request),
        )
    except ValueError as exc:
        control_service.audit(
            "mode",
            actor=_actor_from_request(request),
            ok=False,
            error=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        control_service.audit(
            "mode",
            actor=_actor_from_request(request),
            ok=False,
            error=str(exc),
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/restart")
async def control_restart(request: Request, payload: dict[str, Any] | None = None):
    _assert_local_request(request)
    payload = payload or {}
    return await control_service.request_restart(
        actor=_actor_from_request(request),
        reason=str(payload.get("reason", "remote_request")),
    )


@router.get("/logs")
async def control_logs(request: Request, lines: int = 50):
    _assert_local_request(request)
    return await control_service.get_logs(lines=lines)


@router.post("/freeze")
async def control_freeze(request: Request):
    _assert_local_request(request)
    return await control_service.freeze(actor=_actor_from_request(request))


@router.post("/unfreeze")
async def control_unfreeze(request: Request):
    _assert_local_request(request)
    return await control_service.unfreeze(actor=_actor_from_request(request))


@router.get("/volatility-state")
async def control_volatility_state(request: Request):
    _assert_local_request(request)
    return await control_service.get_volatility_state()
