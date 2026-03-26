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
        kelly_live_bankroll_usd: 100,
        kelly_paper_bankroll_usd: 100,
        paper_compound_enabled: true,
        paper_current_bankroll_usd: 100,
        live_equity_start_bankroll_usd: 0,
        live_equity_start_at_utc: "",
        kelly_min_edge_pct: 0.5,
        kelly_max_bet_pct: 25,
        kelly_max_event_exposure_pct: 25,
        quant_gate_enabled: true,
        quant_gate_min_sample: 120,
        quant_gate_min_sample_strong_signal: 20,
        quant_gate_strong_signal_threshold: 0.72,
        quant_gate_min_edge_pct: 4,
        quant_gate_min_diff_pct: 0,
        quant_gate_min_price_c: 10,
        quant_gate_max_price_c: 90,
        quant_gate_edge_vs_ask_enabled: false,
        quant_gate_min_edge_vs_ask_pct: 2,
        quant_gate_min_ask_price: 0,
        quant_gate_max_ask_price: 0,
        quant_gate_min_prob: 0.0,
        quant_gate_blocked_hours_pst: [] as number[],
        quant_gate_enabled_slots: [] as number[],
        vol_gate_enabled: false,
        vol_gate_lookback_n: 20,
        vol_gate_min_pct_of_avg: 0.8,
        monitored_tickers: ["BTC", "ETH", "SOL", "XRP"],
        bot_risk_enabled: true,
        bot_max_buys_per_event_side: 1,
        bot_cooldown_seconds_per_event_side: 60,
        bot_global_min_seconds_between_orders: 2,
        bot_max_event_exposure_pct: 15,
        bot_drawdown_enabled: true,
        bot_drawdown_stop_pct: 50,
        bot_order_notional_cap_usd: 5,
        bot_paper_mode: false,
        bot_second_entry_opposite_enabled: false,
        bot_second_entry_max_ask_price: 0,
        bot_second_entry_min_edge_pct: 5,
        bot_trade_ladder: [],
        pm_min_shares: 5,
        pm_min_notional_usd: 1,
        order_book_max_levels: 8,
        order_book_min_broadcast_ms: 120,
        bot_enforce_timeframe_filter: true,
        bot_min_seconds_before_end: 30,
        take_profit_enabled: false,
        take_profit_trigger_price: 0.95,
        take_profit_min_price: 0.9,
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
