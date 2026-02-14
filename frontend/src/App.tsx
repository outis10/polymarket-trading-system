import { useWebSocket } from "./hooks/useWebSocket";
import { useEventsStore } from "./stores/useEventsStore";
import Header from "./components/layout/Header";
import Sidebar from "./components/layout/Sidebar";
import EventCard from "./components/EventCard";

export default function App() {
    const { send } = useWebSocket();
    const events = useEventsStore((s) => s.events);
    const settings = useEventsStore((s) => s.settings);
    const nowMs = Date.now();
    const selectedTimeframe = settings.timeframe_filter || "15m";
    const selectedMinutes =
        selectedTimeframe === "1h"
            ? 60
            : Number(selectedTimeframe.replace("m", ""));

    const visibleLiveEvents = Object.entries(events).filter(([, eventData]) => {
        if (settings.mode !== "live") return false;
        if ((eventData.timeframe_minutes || 15) !== selectedMinutes)
            return false;
        if (eventData.event_start_utc) {
            const startMs = Date.parse(eventData.event_start_utc);
            if (!Number.isNaN(startMs) && nowMs < startMs) return false;
        }
        if (!eventData.event_end_utc) return true;
        const endMs = Date.parse(eventData.event_end_utc);
        if (Number.isNaN(endMs)) return true;
        return endMs > nowMs;
    });

    return (
        <>
            <Header />
            <Sidebar send={send} />

            {settings.mode === "demo" && (
                <div className="demo-banner">
                    Demo Mode - Live cards are hidden. Switch to Live mode to
                    see active markets.
                </div>
            )}

            <div className="event-grid">
                {visibleLiveEvents.map(([eventId, eventData]) => (
                    <EventCard
                        key={eventId}
                        eventId={eventId}
                        event={eventData}
                    />
                ))}
            </div>
        </>
    );
}
