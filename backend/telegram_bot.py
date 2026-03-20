"""Telegram long-polling bot for private remote control and alerting."""

from __future__ import annotations

import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(os.environ.get("ENV_FILE", ".env"))

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _parse_ids(raw: str) -> set[int]:
    result: set[int] = set()
    for chunk in str(raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            result.add(int(chunk))
        except ValueError:
            logger.warning("Ignoring invalid numeric ID in env: %s", chunk)
    return result


@dataclass
class PendingConfirmation:
    action: str
    params: dict[str, Any]
    expires_at: float


@dataclass(frozen=True)
class ControlInstance:
    instance_id: str
    base_url: str
    api_key: str
    label: str


class TelegramControlBot:
    def __init__(self) -> None:
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
        self.allowed_chat_ids = _parse_ids(
            os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "")
        )
        self.allowed_user_ids = _parse_ids(
            os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
        )
        self.control_api_host = (
            os.environ.get("CONTROL_API_HOST", "127.0.0.1").strip() or "127.0.0.1"
        )
        self.control_api_port = int(os.environ.get("CONTROL_API_PORT", "8010"))
        self.app_env = os.environ.get("APP_ENV", "dev")
        self.control_api_key = os.environ.get("API_KEY", "").strip()
        self.telegram_api_base = f"https://api.telegram.org/bot{self.token}"
        self.default_control_api_base = (
            f"http://{self.control_api_host}:{self.control_api_port}/api/control"
        )
        self.instances = self._load_instances()
        self.session = requests.Session()
        self.update_offset = 0
        self.min_command_interval = float(
            os.environ.get("TELEGRAM_MIN_COMMAND_INTERVAL_SECONDS", "1.5")
        )
        self.watchdog_interval = float(
            os.environ.get("TELEGRAM_WATCHDOG_INTERVAL_SECONDS", "20")
        )
        self.last_command_at: dict[tuple[int, int], float] = {}
        self.pending_confirms: dict[tuple[int, int], PendingConfirmation] = {}
        self.last_watchdog_at = 0.0
        self.last_watchdog_state: dict[str, Any] = {}

    def run(self) -> None:
        logger.info(
            "Starting Telegram control bot for %s against %s",
            self.app_env,
            ", ".join(
                f"{instance.instance_id}={instance.base_url}"
                for instance in self.instances.values()
            ),
        )
        while True:
            try:
                self._poll_once()
                self._watchdog_tick()
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                logger.exception("Telegram bot loop error: %s", exc)
                time.sleep(3)

    def _poll_once(self) -> None:
        response = self.session.get(
            f"{self.telegram_api_base}/getUpdates",
            params={
                "timeout": 20,
                "offset": self.update_offset,
                "allowed_updates": ["message"],
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram getUpdates failed: {payload}")
        for update in payload.get("result", []):
            self.update_offset = max(self.update_offset, int(update["update_id"]) + 1)
            message = update.get("message") or {}
            text = str(message.get("text") or "").strip()
            if not text.startswith("/"):
                continue
            self._handle_message(message, text)

    def _handle_message(self, message: dict[str, Any], text: str) -> None:
        chat = message.get("chat") or {}
        user = message.get("from") or {}
        chat_id = int(chat.get("id", 0) or 0)
        user_id = int(user.get("id", 0) or 0)
        if not self._is_authorized(chat_id, user_id):
            logger.warning(
                "Rejected unauthorized Telegram request chat=%s user=%s",
                chat_id,
                user_id,
            )
            self._send_message(chat_id, "Unauthorized.")
            return
        if not self._rate_limit(chat_id, user_id):
            self._send_message(chat_id, "Rate limit active. Retry in a moment.")
            return
        parts = text.split()
        command = parts[0].split("@", 1)[0].lower()
        args = parts[1:]
        try:
            if command in {"/start", "/help"}:
                self._send_message(chat_id, self._help_text())
            elif command == "/status":
                target = self._resolve_target_arg(args)
                self._send_message(chat_id, self._handle_status_command(target))
            elif command == "/health":
                target = self._resolve_target_arg(args)
                self._send_message(chat_id, self._handle_health_command(target))
            elif command == "/pnl_today":
                target = self._resolve_target_arg(args)
                self._send_message(chat_id, self._handle_pnl_today_command(target))
            elif command == "/instances":
                self._send_message(chat_id, self._handle_instances_command())
            elif command == "/positions":
                target = self._resolve_target_arg(args)
                self._send_message(chat_id, self._handle_positions_command(target))
            elif command == "/orders":
                target = self._resolve_target_arg(args)
                self._send_message(chat_id, self._handle_orders_command(target))
            elif command == "/pause":
                instance = self._resolve_single_instance(args)
                self._send_message(
                    chat_id,
                    self._format_action(
                        self._control_post(
                            "/pause", {}, chat_id, user_id, user, instance=instance
                        )
                    ),
                )
            elif command == "/resume":
                instance = self._resolve_single_instance(args)
                self._send_message(
                    chat_id,
                    self._format_action(
                        self._control_post(
                            "/resume", {}, chat_id, user_id, user, instance=instance
                        )
                    ),
                )
            elif command == "/freeze":
                instance = self._resolve_single_instance(args)
                self._send_message(
                    chat_id,
                    self._format_action(
                        self._control_post(
                            "/freeze", {}, chat_id, user_id, user, instance=instance
                        )
                    ),
                )
            elif command == "/unfreeze":
                instance = self._resolve_single_instance(args)
                self._send_message(
                    chat_id,
                    self._format_action(
                        self._control_post(
                            "/unfreeze", {}, chat_id, user_id, user, instance=instance
                        )
                    ),
                )
            elif command == "/mode":
                self._handle_mode_command(chat_id, user_id, user, args)
            elif command == "/restart":
                instance = self._resolve_single_instance(args)
                self._request_confirmation(
                    chat_id,
                    user_id,
                    "restart",
                    {"reason": "telegram_remote", "instance_id": instance.instance_id},
                )
            elif command == "/confirm":
                self._handle_confirm(chat_id, user_id, user, args)
            elif command == "/logs":
                lines = self._extract_log_lines(args)
                target = self._resolve_target_arg(
                    args[1:] if args and args[0].isdigit() else args
                )
                self._send_message(
                    chat_id,
                    self._handle_logs_command(target, lines),
                )
            else:
                self._send_message(chat_id, self._help_text())
        except Exception as exc:
            logger.exception("Telegram command failed: %s", exc)
            self._send_message(chat_id, f"Command failed: {exc}")

    def _handle_mode_command(
        self,
        chat_id: int,
        user_id: int,
        user: dict[str, Any],
        args: list[str],
    ) -> None:
        if not args or args[0].lower() not in {"paper", "live"}:
            self._send_message(
                chat_id, "Usage: /mode paper [instance] | /mode live [instance]"
            )
            return
        target = args[0].lower()
        instance = self._resolve_single_instance(args[1:])
        if target == "live":
            self._request_confirmation(
                chat_id,
                user_id,
                "mode_live",
                {"mode": "live", "instance_id": instance.instance_id},
            )
            return
        result = self._control_post(
            "/mode",
            {"mode": "paper"},
            chat_id,
            user_id,
            user,
            instance=instance,
        )
        self._send_message(chat_id, self._format_action(result))

    def _request_confirmation(
        self, chat_id: int, user_id: int, action: str, params: dict[str, Any]
    ) -> None:
        code = secrets.token_hex(3)
        self.pending_confirms[(chat_id, user_id)] = PendingConfirmation(
            action=action,
            params=params,
            expires_at=time.time() + 90.0,
        )
        self._send_message(
            chat_id,
            f"Confirmation required for {action}. Reply with /confirm {code} within 90s.",
        )
        self.pending_confirms[(chat_id, user_id)].params["code"] = code

    def _handle_confirm(
        self,
        chat_id: int,
        user_id: int,
        user: dict[str, Any],
        args: list[str],
    ) -> None:
        pending = self.pending_confirms.get((chat_id, user_id))
        if not pending:
            self._send_message(chat_id, "No pending confirmation.")
            return
        if time.time() > pending.expires_at:
            self.pending_confirms.pop((chat_id, user_id), None)
            self._send_message(chat_id, "Confirmation expired.")
            return
        provided = args[0].strip().lower() if args else ""
        expected = str(pending.params.get("code", "")).lower()
        if provided != expected:
            self._send_message(chat_id, "Invalid confirmation code.")
            return
        self.pending_confirms.pop((chat_id, user_id), None)
        instance = self._get_instance(str(pending.params.get("instance_id", "default")))
        if pending.action == "mode_live":
            result = self._control_post(
                "/mode",
                {"mode": "live"},
                chat_id,
                user_id,
                user,
                instance=instance,
            )
        elif pending.action == "restart":
            result = self._control_post(
                "/restart",
                pending.params,
                chat_id,
                user_id,
                user,
                instance=instance,
            )
        else:
            raise RuntimeError(f"Unsupported pending action: {pending.action}")
        self._send_message(chat_id, self._format_action(result))

    def _control_get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        instance: ControlInstance | None = None,
    ) -> dict[str, Any]:
        target = instance or self.instances["default"]
        response = self.session.get(
            f"{target.base_url}{path}",
            params=params,
            headers=self._control_headers(instance=target),
            timeout=10,
        )
        if response.status_code >= 400:
            raise RuntimeError(response.text)
        return response.json()

    def _control_post(
        self,
        path: str,
        payload: dict[str, Any],
        chat_id: int,
        user_id: int,
        user: dict[str, Any],
        *,
        instance: ControlInstance | None = None,
    ) -> dict[str, Any]:
        target = instance or self.instances["default"]
        headers = self._control_headers(
            chat_id=chat_id,
            user_id=user_id,
            actor=self._actor_label(user),
            instance=target,
        )
        response = self.session.post(
            f"{target.base_url}{path}",
            json=payload,
            headers=headers,
            timeout=10,
        )
        if response.status_code >= 400:
            raise RuntimeError(response.text)
        return response.json()

    def _control_headers(
        self,
        *,
        chat_id: int | None = None,
        user_id: int | None = None,
        actor: str | None = None,
        instance: ControlInstance | None = None,
    ) -> dict[str, str]:
        headers = {"X-Control-Source": "telegram"}
        api_key = instance.api_key if instance else self.control_api_key
        if api_key:
            headers["X-API-Key"] = api_key
        if chat_id is not None:
            headers["X-Control-Chat-Id"] = str(chat_id)
        if user_id is not None:
            headers["X-Control-User-Id"] = str(user_id)
        if actor:
            headers["X-Control-Actor"] = actor
        return headers

    def _watchdog_tick(self) -> None:
        now = time.time()
        if now - self.last_watchdog_at < self.watchdog_interval:
            return
        self.last_watchdog_at = now
        try:
            health = self._control_get("/health", instance=self.instances["default"])
            status = self._control_get("/status", instance=self.instances["default"])
        except Exception as exc:
            if self.last_watchdog_state.get("availability") != "down":
                self.last_watchdog_state = {"availability": "down"}
                self._broadcast(
                    f"ALERT: control-api unreachable in {self.app_env}: {exc}"
                )
            return

        previous = dict(self.last_watchdog_state)
        current = {
            "availability": "up",
            "health": health.get("health"),
            "execution_enabled": status.get("execution_enabled"),
            "trading_mode": status.get("trading_mode"),
        }
        self.last_watchdog_state = current
        if previous.get("availability") == "down":
            self._broadcast("RECOVERY: control-api reachable again.")
        if previous.get("health") and previous.get("health") != current["health"]:
            self._broadcast(
                f"ALERT: health changed {previous['health']} -> {current['health']}"
            )
        if (
            previous.get("execution_enabled") is not None
            and previous.get("execution_enabled") != current["execution_enabled"]
        ):
            state = "resumed" if current["execution_enabled"] else "paused"
            self._broadcast(f"ALERT: execution {state}.")
        if (
            previous.get("trading_mode")
            and previous.get("trading_mode") != current["trading_mode"]
        ):
            self._broadcast(
                f"ALERT: trading mode changed {previous['trading_mode']} -> {current['trading_mode']}"
            )

        # Volatility alert check
        try:
            vol = self._control_get(
                "/volatility-state", instance=self.instances["default"]
            )
            alert = vol.get("alert")
            if alert:
                ticker = alert.get("ticker", "?")
                flips = alert.get("flips", 0)
                signals = alert.get("signals_in_window", 0)
                history = " -> ".join(alert.get("direction_history", []))
                bot_mode = vol.get("bot_mode", "NRM")
                self._broadcast(
                    f"VOLATILITY ALERT: {ticker}\n"
                    f"{flips} direction flips in the last hour ({signals} large signals)\n"
                    f"Signals: {history}\n"
                    f"Bot mode: {bot_mode}\n"
                    f"Use /freeze to pause or continue if it's noise."
                )
        except Exception as exc:
            logger.debug("Volatility state check failed: %s", exc)

    def _broadcast(self, text: str) -> None:
        targets = self.allowed_chat_ids or set()
        for chat_id in targets:
            try:
                self._send_message(chat_id, text)
            except Exception as exc:
                logger.warning("Could not send Telegram alert to %s: %s", chat_id, exc)

    def _send_message(self, chat_id: int, text: str) -> None:
        response = self.session.post(
            f"{self.telegram_api_base}/sendMessage",
            json={"chat_id": chat_id, "text": text[:4000]},
            timeout=10,
        )
        response.raise_for_status()

    def _is_authorized(self, chat_id: int, user_id: int) -> bool:
        if self.allowed_chat_ids and chat_id not in self.allowed_chat_ids:
            return False
        if self.allowed_user_ids and user_id not in self.allowed_user_ids:
            return False
        return True

    def _rate_limit(self, chat_id: int, user_id: int) -> bool:
        key = (chat_id, user_id)
        now = time.time()
        last = self.last_command_at.get(key, 0.0)
        if now - last < self.min_command_interval:
            return False
        self.last_command_at[key] = now
        return True

    def _actor_label(self, user: dict[str, Any]) -> str:
        username = str(user.get("username") or "").strip()
        full_name = " ".join(
            part
            for part in [
                str(user.get("first_name") or "").strip(),
                str(user.get("last_name") or "").strip(),
            ]
            if part
        ).strip()
        return username or full_name or str(user.get("id", "telegram-user"))

    def _help_text(self) -> str:
        return (
            "Commands:\n"
            "/status [instance|all]\n"
            "/health [instance|all]\n"
            "/pnl_today [instance|all]\n"
            "/instances\n"
            "/positions [instance|all]\n"
            "/orders [instance|all]\n"
            "/pause [instance]\n"
            "/resume [instance]\n"
            "/freeze [instance]  — volatility mode (FRZ)\n"
            "/unfreeze [instance]  — exit volatility mode\n"
            "/mode paper [instance]\n"
            "/mode live [instance]\n"
            "/restart [instance]\n"
            "/logs 50 [instance|all]\n"
            "/confirm <code>"
        )

    def _format_status(self, payload: dict[str, Any]) -> str:
        return (
            f"Status [{payload.get('instance_id')}|{payload.get('app_env')}]\n"
            f"engine_running={payload.get('engine_running')}\n"
            f"engine_mode={payload.get('engine_mode')}\n"
            f"trading_mode={payload.get('trading_mode')}\n"
            f"execution_enabled={payload.get('execution_enabled')}\n"
            f"events={payload.get('events_count')}\n"
            f"last_tick_s={payload.get('seconds_since_last_tick')}"
        )

    def _format_health(self, payload: dict[str, Any]) -> str:
        checks = payload.get("checks") or {}
        return (
            f"Health [{payload.get('instance_id')}]={payload.get('health')}\n"
            f"engine_running={checks.get('engine_running')}\n"
            f"has_events={checks.get('has_events')}\n"
            f"price_stream_recent={checks.get('price_stream_recent')}"
        )

    def _format_pnl_today(self, payload: dict[str, Any]) -> str:
        return (
            f"PnL today [{payload.get('instance_id')}] ({payload.get('source')}): {payload.get('net_pnl_usd')} USD\n"
            f"rows={payload.get('rows')} resolved={payload.get('resolved_rows')}\n"
            f"wins={payload.get('wins')} losses={payload.get('losses')}"
        )

    def _format_positions(self, payload: dict[str, Any]) -> str:
        positions = payload.get("positions") or []
        if not positions:
            return f"No tracked positions for {payload.get('instance_id')}."
        lines = [
            f"Positions [{payload.get('instance_id')}]={payload.get('count')} pnl={payload.get('total_pnl_usd')} USD"
        ]
        for row in positions[:10]:
            lines.append(
                f"{row.get('ticker') or '?'} {row.get('outcome')} shares={row.get('shares')} pnl={row.get('pnl_usd')}"
            )
        return "\n".join(lines)

    def _format_orders(self, payload: dict[str, Any]) -> str:
        orders = payload.get("orders") or []
        if not orders:
            return f"Open orders [{payload.get('instance_id')}]: 0 ({payload.get('message', 'none')})"
        lines = [f"Open orders [{payload.get('instance_id')}]: {payload.get('count')}"]
        for order in orders[:10]:
            if isinstance(order, dict):
                lines.append(
                    f"{order.get('market', order.get('event_id', 'order'))} {order.get('side', '')} {order.get('size', order.get('original_size', ''))}"
                )
            else:
                lines.append(str(order))
        return "\n".join(lines)

    def _format_logs(self, payload: dict[str, Any]) -> str:
        lines = payload.get("lines") or []
        if not lines:
            return f"No log lines available for {payload.get('instance_id')} in {payload.get('path')}"
        text = "\n".join(lines[-20:])
        return (
            f"Logs [{payload.get('instance_id')}] from {payload.get('path')}:\n{text}"
        )

    def _format_action(self, payload: dict[str, Any]) -> str:
        return json_dumps(payload)

    def _load_instances(self) -> dict[str, ControlInstance]:
        instances: dict[str, ControlInstance] = {}
        default_id = (
            os.environ.get("ENGINE_INSTANCE_ID", "default").strip() or "default"
        )
        instances["default"] = ControlInstance(
            instance_id=default_id,
            base_url=self.default_control_api_base,
            api_key=self.control_api_key,
            label=os.environ.get("ENGINE_WALLET_LABEL", "").strip() or default_id,
        )
        raw = os.environ.get("TELEGRAM_CONTROL_INSTANCES", "").strip()
        for chunk in raw.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            parts = chunk.split("|")
            if len(parts) < 2:
                logger.warning(
                    "Ignoring invalid TELEGRAM_CONTROL_INSTANCES entry: %s", chunk
                )
                continue
            instance_id = parts[0].strip()
            base_url = parts[1].strip().rstrip("/")
            api_key = parts[2].strip() if len(parts) >= 3 else self.control_api_key
            label = parts[3].strip() if len(parts) >= 4 else instance_id
            if not instance_id or not base_url:
                continue
            instances[instance_id] = ControlInstance(
                instance_id=instance_id,
                base_url=base_url,
                api_key=api_key,
                label=label,
            )
        return instances

    def _get_instance(self, name: str) -> ControlInstance:
        normalized = (name or "default").strip()
        if normalized in {"", "default"}:
            return self.instances["default"]
        if normalized in self.instances:
            return self.instances[normalized]
        for instance in self.instances.values():
            if instance.instance_id == normalized:
                return instance
        raise RuntimeError(f"Unknown instance: {normalized}")

    def _resolve_target_arg(self, args: list[str]) -> str:
        return args[0].strip() if args else "default"

    def _resolve_single_instance(self, args: list[str]) -> ControlInstance:
        target = self._resolve_target_arg(args)
        if target.lower() == "all":
            raise RuntimeError("This command requires a single instance, not 'all'")
        return self._get_instance(target)

    def _extract_log_lines(self, args: list[str]) -> int:
        if args:
            try:
                return max(1, min(int(args[0]), 200))
            except ValueError:
                return 50
        return 50

    def _iter_instances(self, target: str) -> list[ControlInstance]:
        if target.lower() == "all":
            unique: dict[str, ControlInstance] = {}
            for instance in self.instances.values():
                unique.setdefault(instance.instance_id, instance)
            return [unique[key] for key in sorted(unique.keys())]
        return [self._get_instance(target)]

    def _handle_status_command(self, target: str) -> str:
        payloads = [
            self._control_get("/status", instance=i)
            for i in self._iter_instances(target)
        ]
        return "\n\n".join(self._format_status(payload) for payload in payloads)

    def _handle_health_command(self, target: str) -> str:
        payloads = [
            self._control_get("/health", instance=i)
            for i in self._iter_instances(target)
        ]
        return "\n\n".join(self._format_health(payload) for payload in payloads)

    def _handle_pnl_today_command(self, target: str) -> str:
        payloads = [
            self._control_get("/pnl-today", instance=i)
            for i in self._iter_instances(target)
        ]
        if target.lower() != "all":
            return self._format_pnl_today(payloads[0])
        total = round(
            sum(float(payload.get("net_pnl_usd") or 0.0) for payload in payloads), 4
        )
        lines = [f"PnL today [all]={total} USD"]
        for payload in payloads:
            lines.append(
                f"{payload.get('instance_id')}: {payload.get('net_pnl_usd')} USD rows={payload.get('rows')}"
            )
        return "\n".join(lines)

    def _handle_positions_command(self, target: str) -> str:
        payloads = [
            self._control_get("/positions", instance=i)
            for i in self._iter_instances(target)
        ]
        return "\n\n".join(self._format_positions(payload) for payload in payloads)

    def _handle_orders_command(self, target: str) -> str:
        payloads = [
            self._control_get("/orders", instance=i)
            for i in self._iter_instances(target)
        ]
        return "\n\n".join(self._format_orders(payload) for payload in payloads)

    def _handle_logs_command(self, target: str, lines: int) -> str:
        payloads = [
            self._control_get("/logs", params={"lines": lines}, instance=i)
            for i in self._iter_instances(target)
        ]
        return "\n\n".join(self._format_logs(payload) for payload in payloads)

    def _handle_instances_command(self) -> str:
        unique: dict[str, ControlInstance] = {}
        for instance in self.instances.values():
            unique.setdefault(instance.instance_id, instance)
        lines = [f"Instances: {len(unique)}"]
        for instance_id in sorted(unique.keys()):
            instance = unique[instance_id]
            try:
                info = self._control_get("/instance", instance=instance)
                health = self._control_get("/health", instance=instance)
                status = "up"
                detail = health.get("health", "unknown")
                wallet_label = info.get("wallet_label") or instance.label
            except Exception as exc:
                status = "down"
                detail = str(exc).strip().replace("\n", " ")[:120]
                wallet_label = instance.label
            lines.append(
                f"{instance_id}: {wallet_label} status={status} detail={detail} url={instance.base_url}"
            )
        return "\n".join(lines)


def json_dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)


def main() -> None:
    TelegramControlBot().run()


if __name__ == "__main__":
    main()
