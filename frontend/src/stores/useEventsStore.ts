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
        mode: "demo",
        refresh_rate: 1,
        chart_options: ["show_chart"],
        timeframe_filter: "15m",
        trading_mode: "manual",
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
