import { memo } from "react";
import type { EventData } from "../types/events";
import { useEventsStore } from "../stores/useEventsStore";
import PriceDisplay from "./PriceDisplay";
import Countdown from "./Countdown";
import PriceChart from "./PriceChart";
import PositionDisplay from "./PositionDisplay";
import OrderBook from "./OrderBook";
import TradingPanel from "./TradingPanel";

const ICON_MAP: Record<string, { className: string; symbol: string }> = {
    btc: { className: "event-icon event-icon-btc", symbol: "\u20bf" },
    eth: { className: "event-icon event-icon-eth", symbol: "\u039e" },
    sol: { className: "event-icon event-icon-sol", symbol: "\u25ce" },
    generic: {
        className: "event-icon event-icon-generic",
        symbol: "\ud83d\udcca",
    },
};

interface EventCardProps {
    eventId: string;
    event: EventData;
}

function EventCard({ eventId, event }: EventCardProps) {
    const settings = useEventsStore((s) => s.settings);
    const chartOptions = settings.chart_options || [];

    const iconInfo = ICON_MAP[event.icon] || ICON_MAP.generic;

    const showChart = chartOptions.includes("show_chart");
    const showProbability = chartOptions.includes("show_probability");
    const showPriceChange = chartOptions.includes("show_price_change");

    return (
        <div className="event-card">
            <div className="event-header">
                <div className={iconInfo.className}>{iconInfo.symbol}</div>
                <div>
                    <div className="event-title">{event.name}</div>
                    <div className="event-subtitle">{event.description}</div>
                </div>
            </div>

            <div className="event-panels-grid">
                <div className="market-stats-panel">
                    <div className="panel-header">
                        <span className="panel-title">Market Snapshot</span>
                        <Countdown eventEndUtc={event.event_end_utc} />
                    </div>
                    <PriceDisplay event={event} />
                </div>

                <TradingPanel eventId={eventId} event={event} />

                <OrderBook
                    orderBookYes={event.order_book_yes}
                    orderBookNo={event.order_book_no}
                />

                <PositionDisplay eventId={eventId} />
            </div>

            {showChart && (
                <PriceChart
                    priceHistory={event.price_history}
                    showProbability={showProbability}
                    showPriceChange={showPriceChange}
                />
            )}
        </div>
    );
}

export default memo(EventCard);
