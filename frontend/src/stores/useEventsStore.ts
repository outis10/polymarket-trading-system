import { create } from "zustand";
import type { EventData, SettingsData } from "../types/events";

interface EventsState {
    events: Record<string, EventData>;
    settings: SettingsData;
    setEvents: (events: Record<string, EventData>) => void;
    updateEvent: (eventId: string, data: Partial<EventData>) => void;
    setSettings: (settings: SettingsData) => void;
    updateSettings: (partial: Partial<SettingsData>) => void;
}

export const useEventsStore = create<EventsState>((set) => ({
    events: {},
    settings: {
        mode: "live",
        refresh_rate: 1,
        chart_options: ["show_chart"],
        timeframe_filter: "15m",
        trading_mode: "bot",
        kelly_enabled: true,
        kelly_fraction: 0.25,
        kelly_bankroll: 100,
        kelly_min_edge_pct: 0.5,
        kelly_max_bet_pct: 25,
        kelly_max_event_exposure_pct: 25,
        quant_gate_enabled: true,
        quant_gate_min_sample: 120,
        quant_gate_min_edge_pct: 4,
        quant_gate_use_percentile: true,
        quant_gate_percentile_low: 15,
        quant_gate_percentile_high: 85,
        quant_gate_min_price_c: 10,
        quant_gate_max_price_c: 90,
        monitored_tickers: ["BTC", "ETH", "SOL", "XRP"],
    },

    setEvents: (events) => set({ events }),

    updateEvent: (eventId, data) =>
        set((state) => ({
            events: {
                ...state.events,
                [eventId]: { ...state.events[eventId], ...data },
            },
        })),

    setSettings: (settings) => set({ settings }),

    updateSettings: (partial) =>
        set((state) => ({
            settings: { ...state.settings, ...partial },
        })),
}));
