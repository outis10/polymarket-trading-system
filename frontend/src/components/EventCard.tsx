import { memo } from "react";
import type { EventData } from "../types/events";
import { useEventsStore } from "../stores/useEventsStore";
import Countdown from "./Countdown";
import PriceChart from "./PriceChart";
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
    const currentPrice = event.current_price || 0;
    const priceToBeat = event.price_to_beat || 0;
    const yesPrice = event.yes_price || 0.5;
    const noPrice = event.no_price || 0.5;
    const priceDiff = currentPrice - priceToBeat;
    const isAboveTarget = priceDiff >= 0;
    const priceDiffRoundedUp = Math.ceil(Math.abs(priceDiff));
    const priceDiffPct =
        priceToBeat > 0 ? Math.abs((priceDiff / priceToBeat) * 100) : 0;

    const formatUsd = (v: number) =>
        v.toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    const formatCents = (v: number) => `${Math.round(v * 100)}¢`;

    return (
        <article className="event-card compact-card">
            <div className="event-header">
                <div className={iconInfo.className}>{iconInfo.symbol}</div>
                <div>
                    <div className="event-title">{event.name}</div>
                    <div className="event-subtitle">{event.description}</div>
                </div>
            </div>

            <section className="compact-metrics">
                <div className="metric-card">
                    <span className="metric-label">Price To Beat</span>
                    <span className="metric-value">
                        ${formatUsd(priceToBeat)}
                    </span>
                </div>
                <div className="metric-card">
                    <span className="metric-label">Current Price</span>
                    <span className="metric-value">
                        ${formatUsd(currentPrice)}
                    </span>
                    <span
                        className={`metric-change ${isAboveTarget ? "metric-change-up" : "metric-change-down"}`}
                    >
                        {isAboveTarget ? "▲" : "▼"} ${priceDiffRoundedUp} (
                        {priceDiffPct.toFixed(2)}%)
                    </span>
                </div>
                <div className="metric-card metric-card-countdown">
                    <span className="metric-label">Time Left</span>
                    <Countdown eventEndUtc={event.event_end_utc} />
                </div>
            </section>

            <section className="probability-strip">
                <div className="probability-title-row">
                    <span>Probabilities</span>
                    <span className="probability-inline-values">
                        UP {formatCents(yesPrice)} / DOWN {formatCents(noPrice)}
                    </span>
                </div>
                <div className="probability-bar">
                    <div
                        className="probability-fill-up"
                        style={{
                            width: `${Math.max(0, Math.min(100, yesPrice * 100))}%`,
                        }}
                    />
                    <div
                        className="probability-fill-down"
                        style={{
                            width: `${Math.max(0, Math.min(100, noPrice * 100))}%`,
                        }}
                    />
                </div>
                <div className="probability-values">
                    <span className="prob-up">
                        {(yesPrice * 100).toFixed(1)}% up
                    </span>
                    <span className="prob-down">
                        {(noPrice * 100).toFixed(1)}% down
                    </span>
                </div>
            </section>

            <div className="compact-panels-grid">
                <div className="compact-panel">
                    <div className="compact-panel-title">Quick Trade</div>
                    <TradingPanel eventId={eventId} event={event} />
                </div>

                <div className="compact-panel">
                    <div className="compact-panel-title">Order Flow</div>
                    <OrderBook
                        orderBookYes={event.order_book_yes}
                        orderBookNo={event.order_book_no}
                    />
                </div>
            </div>

            {showChart && (
                <div className="compact-chart-wrap">
                    <PriceChart
                        priceHistory={event.price_history}
                        showProbability={showProbability}
                        showPriceChange={showPriceChange}
                    />
                </div>
            )}
        </article>
    );
}

export default memo(EventCard);
