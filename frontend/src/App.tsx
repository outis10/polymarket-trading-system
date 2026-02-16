import { useWebSocket } from "./hooks/useWebSocket";
import { useEventsStore } from "./stores/useEventsStore";
import Header from "./components/layout/Header";
import Sidebar from "./components/layout/Sidebar";
import EventCard from "./components/EventCard";
import { inferTicker } from "./utils/ticker";

export default function App() {
    const { send } = useWebSocket();
    const events = useEventsStore((s) => s.events);
    const settings = useEventsStore((s) => s.settings);
    const nowMs = Date.now();
    const rawTimeframe =
        typeof settings.timeframe_filter === "string"
            ? settings.timeframe_filter
            : "15m";
    const selectedTimeframe = ["5m", "15m", "1h"].includes(rawTimeframe)
        ? (rawTimeframe as "5m" | "15m" | "1h")
        : "15m";
    const selectedMinutes =
        selectedTimeframe === "1h"
            ? 60
            : Number.parseInt(selectedTimeframe.replace("m", ""), 10);
    const monitoredTickers = (
        settings.monitored_tickers || ["BTC", "ETH", "SOL", "XRP"]
    ).map((t) => t.toUpperCase());
    const monitoredTickerSet = new Set(monitoredTickers);

    const visibleLiveEvents = Object.entries(events).filter(
        ([eventId, eventData]) => {
            if (settings.mode !== "live") return false;
            if ((eventData.timeframe_minutes || 15) !== selectedMinutes)
                return false;
            const ticker = inferTicker(eventId, eventData);
            if (!monitoredTickerSet.has(ticker)) {
                return false;
            }
            if (eventData.event_start_utc) {
                const startMs = Date.parse(eventData.event_start_utc);
                if (!Number.isNaN(startMs) && nowMs < startMs) return false;
            }
            if (!eventData.event_end_utc) return true;
            const endMs = Date.parse(eventData.event_end_utc);
            if (Number.isNaN(endMs)) return true;
            return endMs > nowMs;
        },
    );

    const getTickerPriority = (
        eventId: string,
        eventData: (typeof visibleLiveEvents)[number][1],
    ) => {
        const ticker = inferTicker(eventId, eventData);
        if (ticker === "BTC") return 0;
        if (ticker === "ETH") return 1;
        if (ticker === "SOL") return 2;
        if (ticker === "XRP") return 3;
        return 99;
    };

    const orderedVisibleLiveEvents = visibleLiveEvents
        .map((entry, index) => ({ entry, index }))
        .sort((a, b) => {
            const [aId, aData] = a.entry;
            const [bId, bData] = b.entry;
            const aPriority = getTickerPriority(aId, aData);
            const bPriority = getTickerPriority(bId, bData);
            if (aPriority !== bPriority) return aPriority - bPriority;
            return a.index - b.index;
        })
        .map(({ entry }) => entry);

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
                {visibleLiveEvents.length === 0 ? (
                    <div className="events-empty-state">
                        No live {selectedTimeframe} events at this moment.
                    </div>
                ) : (
                    orderedVisibleLiveEvents.map(([eventId, eventData]) => (
                        <EventCard
                            key={eventId}
                            eventId={eventId}
                            event={eventData}
                        />
                    ))
                )}
            </div>
        </>
    );
}
