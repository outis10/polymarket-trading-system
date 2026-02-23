import { create } from "zustand";
import type { EventData, SettingsData } from "../types/events";

export interface SystemToast {
    message: string;
    type: "success" | "warning" | "error";
    id: number;
}

interface EventsState {
    events: Record<string, EventData>;
    settings: SettingsData;
    systemToast: SystemToast | null;
    setEvents: (events: Record<string, EventData>) => void;
    updateEvent: (eventId: string, data: Partial<EventData>) => void;
    setSettings: (settings: SettingsData) => void;
    updateSettings: (partial: Partial<SettingsData>) => void;
    showSystemToast: (message: string, type: SystemToast["type"]) => void;
    clearSystemToast: () => void;
}

export const useEventsStore = create<EventsState>((set) => ({
    events: {},
    systemToast: null,
    settings: {
        mode: "live",
        refresh_rate: 1,
        chart_options: ["show_chart"],
        timeframe_filter: "5m",
        trading_mode: "bot",
        kelly_enabled: true,
        kelly_fraction: 0.25,
        kelly_bankroll: 100,
        kelly_min_edge_pct: 0.5,
        kelly_max_bet_pct: 25,
        kelly_max_event_exposure_pct: 25,
        quant_gate_enabled: true,
        quant_gate_min_sample: 120,
        quant_gate_min_sample_strong_signal: 20,
        quant_gate_strong_signal_threshold: 0.72,
        quant_gate_min_edge_pct: 4,
        quant_gate_min_diff_pct: 0,
        quant_gate_use_percentile: true,
        quant_gate_percentile_low: 15,
        quant_gate_percentile_high: 85,
        quant_gate_min_price_c: 10,
        quant_gate_max_price_c: 90,
        quant_gate_edge_vs_ask_enabled: false,
        quant_gate_min_edge_vs_ask_pct: 2,
        quant_gate_min_prob: 0.0,
        early_window_enabled: true,
        early_window_start: 20,
        early_window_end: 120,
        early_quant_gate_min_sample: 90,
        early_quant_gate_min_edge_pct: 4,
        early_quant_gate_edge_vs_ask_enabled: false,
        early_quant_gate_min_edge_vs_ask_pct: 2,
        early_quant_gate_min_prob: 0,
        early_quant_gate_min_diff_pct: 0,
        late_window_enabled: true,
        late_window_start: 180,
        late_window_end: 280,
        late_quant_gate_min_sample: 70,
        late_quant_gate_min_edge_pct: 3,
        late_quant_gate_edge_vs_ask_enabled: false,
        late_quant_gate_min_edge_vs_ask_pct: 1,
        late_quant_gate_min_prob: 0,
        late_quant_gate_min_diff_pct: 0,
        monitored_tickers: ["BTC", "ETH", "SOL", "XRP"],
        bot_risk_enabled: true,
        bot_max_buys_per_event_side: 1,
        bot_cooldown_seconds_per_event_side: 60,
        bot_global_min_seconds_between_orders: 2,
        bot_max_event_exposure_pct: 15,
        bot_max_ticker_exposure_pct: 25,
        bot_order_notional_cap_usd: 5,
        pm_min_shares: 5,
        pm_min_notional_usd: 1,
        order_book_max_levels: 8,
        order_book_min_broadcast_ms: 120,
        bot_enforce_timeframe_filter: true,
        bot_min_seconds_before_end: 30,
        bot_block_opposite_side: true,
        keyboard_shortcuts_enabled:
            localStorage.getItem("keyboard_shortcuts_enabled") === "true",
    },

    setEvents: (events) => set({ events }),

    updateEvent: (eventId, data) =>
        set((state) => ({
            events: {
                ...state.events,
                [eventId]: { ...state.events[eventId], ...data },
            },
        })),

    setSettings: (settings) =>
        set({
            settings: {
                ...settings,
                keyboard_shortcuts_enabled:
                    localStorage.getItem("keyboard_shortcuts_enabled") ===
                    "true",
            },
        }),

    updateSettings: (partial) =>
        set((state) => ({
            settings: { ...state.settings, ...partial },
        })),

    showSystemToast: (message, type) =>
        set({ systemToast: { message, type, id: Date.now() } }),

    clearSystemToast: () => set({ systemToast: null }),
}));
