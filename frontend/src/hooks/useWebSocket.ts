import { useEffect, useRef, useCallback } from "react";
import { useEventsStore } from "../stores/useEventsStore";
import { useAccountStore } from "../stores/useAccountStore";
import type { WSMessage, EventData, SettingsData } from "../types/events";

const WS_URL = import.meta.env.DEV
    ? "ws://localhost:8000/ws/events"
    : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/events`;
const RECONNECT_DELAY = 2000;

export function useWebSocket() {
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const shouldReconnectRef = useRef(true);
    const { setEvents, setSettings, updateEvent } = useEventsStore();
    const setBankrollReal = useAccountStore((s) => s.setBankrollReal);

    const connect = useCallback(() => {
        if (!shouldReconnectRef.current) return;
        if (wsRef.current?.readyState === WebSocket.OPEN) return;

        const ws = new WebSocket(WS_URL);
        wsRef.current = ws;

        ws.onopen = () => {
            console.log("WebSocket connected");
        };

        ws.onmessage = (event) => {
            try {
                const msg: WSMessage = JSON.parse(event.data);

                switch (msg.type) {
                    case "full_snapshot": {
                        const data = msg.data as {
                            events: Record<string, EventData>;
                            settings: SettingsData;
                        };
                        if (data.events) setEvents(data.events);
                        if (data.settings) setSettings(data.settings);
                        break;
                    }
                    case "price_update": {
                        if (msg.event_id) {
                            updateEvent(
                                msg.event_id,
                                msg.data as Partial<EventData>,
                            );
                        }
                        break;
                    }
                    case "orderbook_update": {
                        if (msg.event_id) {
                            updateEvent(
                                msg.event_id,
                                msg.data as Partial<EventData>,
                            );
                        }
                        break;
                    }
                    case "quant_metrics_update": {
                        if (msg.event_id) {
                            updateEvent(
                                msg.event_id,
                                msg.data as Partial<EventData>,
                            );
                        }
                        break;
                    }
                    case "settings_update": {
                        setSettings(msg.data as unknown as SettingsData);
                        break;
                    }
                    case "balance_update": {
                        const raw = (msg.data as Record<string, unknown>)
                            ?.balance;
                        const n = Number(raw);
                        setBankrollReal(Number.isFinite(n) ? n : null);
                        break;
                    }
                    case "bot_order_placed": {
                        // Inject bot order result into event state so EventCard can show toast
                        const d = msg.data as Record<string, unknown>;
                        const bal = Number(d?.balance);
                        if (Number.isFinite(bal) && bal > 0) {
                            setBankrollReal(bal);
                        }
                        if (msg.event_id) {
                            updateEvent(msg.event_id, { _bot_last_order: d } as Partial<EventData>);
                        }
                        break;
                    }
                }
            } catch {
                // ignore parse errors
            }
        };

        ws.onclose = () => {
            if (!shouldReconnectRef.current) return;
            console.log("WebSocket disconnected, reconnecting...");
            reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY);
        };

        ws.onerror = () => {
            ws.close();
        };
    }, [setEvents, setSettings, setBankrollReal, updateEvent]);

    const send = useCallback((msg: Record<string, unknown>) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify(msg));
        }
    }, []);

    useEffect(() => {
        shouldReconnectRef.current = true;
        connect();
        return () => {
            shouldReconnectRef.current = false;
            if (reconnectTimer.current) {
                clearTimeout(reconnectTimer.current);
                reconnectTimer.current = null;
            }
            if (wsRef.current) {
                wsRef.current.onclose = null;
                wsRef.current.onerror = null;
                wsRef.current.close();
                wsRef.current = null;
            }
        };
    }, [connect]);

    return { send };
}
