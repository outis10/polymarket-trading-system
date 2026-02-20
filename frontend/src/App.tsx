import { useEffect, useRef, useState } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { useEventsStore } from "./stores/useEventsStore";
import Header from "./components/layout/Header";
import Sidebar from "./components/layout/Sidebar";
import EventCard from "./components/EventCard";
import OpportunitiesDashboard from "./components/analytics/OpportunitiesDashboard";
import { inferTicker } from "./utils/ticker";

type AppRoute = "live" | "analytics";

const getRouteFromPath = (): AppRoute =>
    window.location.pathname === "/analytics/opportunities"
        ? "analytics"
        : "live";

export default function App() {
    const { send } = useWebSocket();
    const events = useEventsStore((s) => s.events);
    const settings = useEventsStore((s) => s.settings);
    const [route, setRoute] = useState<AppRoute>(getRouteFromPath());
    const lastAutoRefreshAtRef = useRef(0);

    useEffect(() => {
        const onPopState = () => setRoute(getRouteFromPath());
        window.addEventListener("popstate", onPopState);
        return () => window.removeEventListener("popstate", onPopState);
    }, []);

    const handleNavigate = (nextRoute: AppRoute) => {
        const nextPath =
            nextRoute === "analytics" ? "/analytics/opportunities" : "/";
        if (window.location.pathname !== nextPath) {
            window.history.pushState({}, "", nextPath);
        }
        setRoute(nextRoute);
    };
    const nowMs = Date.now();
    const rawTimeframe =
        typeof settings.timeframe_filter === "string"
            ? settings.timeframe_filter
            : "5m";
    const selectedTimeframe = ["5m", "15m", "1h"].includes(rawTimeframe)
        ? (rawTimeframe as "5m" | "15m" | "1h")
        : "5m";
    const selectedMinutes =
        selectedTimeframe === "1h"
            ? 60
            : Number.parseInt(selectedTimeframe.replace("m", ""), 10);
    const monitoredTickers = (
        settings.monitored_tickers || ["BTC", "ETH", "SOL", "XRP"]
    ).map((t) => t.toUpperCase());
    const monitoredTickerSet = new Set(monitoredTickers);

    const visibleEvents = Object.entries(events).filter(
        ([eventId, eventData]) => {
            if ((eventData.timeframe_minutes || 15) !== selectedMinutes)
                return false;
            const ticker = inferTicker(eventId, eventData);
            if (!monitoredTickerSet.has(ticker)) {
                return false;
            }
            if (settings.mode !== "live") return true;
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
        eventData: (typeof visibleEvents)[number][1],
    ) => {
        const ticker = inferTicker(eventId, eventData);
        if (ticker === "BTC") return 0;
        if (ticker === "ETH") return 1;
        if (ticker === "SOL") return 2;
        if (ticker === "XRP") return 3;
        return 99;
    };

    const orderedVisibleEvents = visibleEvents
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

    useEffect(() => {
        if (route !== "live") return;
        if (settings.mode !== "live") return;
        if (visibleEvents.length > 0) return;
        const now = Date.now();
        // Throttle auto-discovery refresh when UI is empty between event windows.
        if (now - lastAutoRefreshAtRef.current < 20000) return;
        lastAutoRefreshAtRef.current = now;
        fetch("/api/events/refresh-live", { method: "POST" }).catch(() => {
            // no-op: UI already displays empty state
        });
    }, [route, settings.mode, visibleEvents.length]);

    return (
        <>
            <Header route={route} onNavigate={handleNavigate} />
            <Sidebar send={send} />

            {route === "analytics" ? (
                <OpportunitiesDashboard />
            ) : (
                <>
                    {settings.mode === "demo" && (
                        <div className="demo-banner">
                            Demo Mode - Showing demo cards.
                        </div>
                    )}

                    <div className="event-grid">
                        {visibleEvents.length === 0 ? (
                            <div className="events-empty-state">
                                {settings.mode === "live"
                                    ? `No live ${selectedTimeframe} events right now (tickers: ${Array.from(monitoredTickerSet).join(", ")}).`
                                    : `No demo ${selectedTimeframe} events available.`}
                            </div>
                        ) : (
                            orderedVisibleEvents.map(([eventId, eventData]) => (
                                <EventCard
                                    key={eventId}
                                    eventId={eventId}
                                    event={eventData}
                                />
                            ))
                        )}
                    </div>
                </>
            )}
        </>
    );
}
