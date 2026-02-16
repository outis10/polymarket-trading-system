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
    const showProbabilitiesCard = !chartOptions.includes(
        "hide_probabilities_card",
    );
    const showRangeHistogramCard = !chartOptions.includes(
        "hide_range_histogram_card",
    );
    const currentPrice = event.current_price || 0;
    const priceToBeat = event.price_to_beat || 0;
    const yesPrice = event.yes_price || 0.5;
    const noPrice = event.no_price || 0.5;
    const priceDiff = currentPrice - priceToBeat;
    const isAboveTarget = priceDiff >= 0;
    const priceDiffRoundedUp = Math.ceil(Math.abs(priceDiff));
    const priceDiffPct =
        priceToBeat > 0 ? Math.abs((priceDiff / priceToBeat) * 100) : 0;
    const tradingMode = settings.trading_mode || "manual";
    const kellyEnabled = settings.kelly_enabled ?? true;
    const kellyFraction = Math.max(0, settings.kelly_fraction ?? 0.25);
    const bankroll = Math.max(0, settings.kelly_bankroll ?? 100);
    const minEdgePct = Math.max(0, settings.kelly_min_edge_pct ?? 0.5);
    const maxBetPct = Math.max(0, settings.kelly_max_bet_pct ?? 25) / 100;
    const maxEventExposurePct =
        Math.max(0, settings.kelly_max_event_exposure_pct ?? 25) / 100;

    const formatUsd = (v: number) =>
        v.toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    const formatCents = (v: number) => `${Math.round(v * 100)}¢`;
    const clamp = (v: number, min: number, max: number) =>
        Math.max(min, Math.min(max, v));

    // Lightweight event-level model probability for visible Kelly movement.
    const directionalBias = Math.tanh(
        priceDiff / Math.max(1, priceToBeat * 0.01),
    );
    const pUpModel = clamp(yesPrice + 0.1 * directionalBias, 0.01, 0.99);
    const pDownModel = clamp(1 - pUpModel, 0.01, 0.99);

    const calcKelly = (modelProb: number, marketProb: number) => {
        const edge = modelProb - marketProb;
        const edgePct = edge * 100;
        if (!kellyEnabled || edgePct < minEdgePct) {
            return { pct: 0, usd: 0, edgePct };
        }
        const denom = Math.max(0.0001, 1 - marketProb);
        const raw = Math.max(0, edge / denom);
        const adjusted = raw * kellyFraction;
        const capped = Math.min(adjusted, maxBetPct, maxEventExposurePct);
        return { pct: capped * 100, usd: capped * bankroll, edgePct };
    };

    const quantProbUp = event.quant_prob_up ?? null;
    const quantProbDown = event.quant_prob_down ?? null;
    const quantSampleSize = event.quant_sample_size ?? null;
    const hasQuantData = quantProbUp !== null && quantProbDown !== null;
    const kellyModelUp = hasQuantData ? quantProbUp! : pUpModel;
    const kellyModelDown = hasQuantData ? quantProbDown! : pDownModel;
    const kellyUp = calcKelly(kellyModelUp, yesPrice);
    const kellyDown = calcKelly(kellyModelDown, noPrice);
    const quantBuyGate = event.quant_buy_gate ?? null;
    const gateUp = quantBuyGate?.up ?? null;
    const gateDown = quantBuyGate?.down ?? null;
    const quantHistogram = event.quant_range_histogram ?? null;
    const histogramBins = quantHistogram?.bins || [];
    const currentDiff = quantHistogram?.current_diff ?? 0;
    const isHistogramUp = currentDiff >= 0;
    const histogramMaxCount = histogramBins.reduce(
        (acc, bin) => Math.max(acc, bin.count || 0),
        0,
    );
    const currentBinIndex = quantHistogram?.current_bin_index ?? null;
    const currentMarkerLeftPct =
        currentBinIndex !== null && histogramBins.length > 0
            ? ((currentBinIndex + 0.5) / histogramBins.length) * 100
            : null;

    const ksTooltip = (edgePct: number) =>
        `Kelly por evento. Source=${hasQuantData ? "quant" : "model"} | edge=${edgePct.toFixed(2)}% | frac=${kellyFraction.toFixed(2)}x`;

    const formatGateReason = (reason: string) => {
        if (reason === "no_quant_data") return "No quant data";
        if (reason === "no_percentile") return "No percentile";
        if (reason.startsWith("sample<")) {
            return `Sample too low (${reason.replace("sample<", "min ")})`;
        }
        if (reason.startsWith("edge<")) {
            return `Edge below ${reason.replace("edge<", "")}`;
        }
        if (reason.startsWith("price_outside_")) {
            return `Price outside ${reason.replace("price_outside_", "")}c`;
        }
        if (reason.startsWith("percentile_inside_")) {
            return `Percentile inside ${reason.replace("percentile_inside_", "")}`;
        }
        return reason;
    };
    const gateTooltip = (gate: typeof gateUp) => {
        if (!gate) return "Gate data unavailable";
        if (gate.enabled) return "Quant gate: enabled";
        const reasons = (gate.reasons || []).map(formatGateReason).join(" | ");
        return `Quant gate blocked: ${reasons || "rule not met"}`;
    };

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

            {showProbabilitiesCard && (
                <section className="probability-strip">
                    <div className="probability-title-row">
                        <span>Probabilities</span>
                        <span className="probability-inline-values">
                            UP {formatCents(yesPrice)} / DOWN{" "}
                            {formatCents(noPrice)}
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
            )}

            {hasQuantData && (
                <section className="quant-edge-strip">
                    <div className="probability-title-row">
                        <span>Quant Edge</span>
                        <span className="quant-edge-sample">
                            n={quantSampleSize}
                        </span>
                    </div>
                    <div className="probability-bar">
                        <div
                            className="probability-fill-up"
                            style={{
                                width: `${Math.round(quantProbUp! * 100)}%`,
                            }}
                        />
                        <div
                            className="probability-fill-down"
                            style={{
                                width: `${Math.round(quantProbDown! * 100)}%`,
                            }}
                        />
                    </div>
                    <div className="probability-values">
                        <span className="prob-up">
                            {(quantProbUp! * 100).toFixed(1)}% up (quant)
                        </span>
                        <span className="prob-down">
                            {(quantProbDown! * 100).toFixed(1)}% down (quant)
                        </span>
                    </div>
                </section>
            )}

            {showRangeHistogramCard &&
                quantHistogram &&
                histogramBins.length > 0 && (
                    <section className="range-histogram-strip">
                        <div className="probability-title-row">
                            <span>
                                Range Histogram {quantHistogram.ticker} m
                                {quantHistogram.minute}{" "}
                                <span
                                    className={
                                        isHistogramUp
                                            ? "range-direction-up"
                                            : "range-direction-down"
                                    }
                                >
                                    {isHistogramUp ? "UP" : "DOWN"}
                                </span>
                            </span>
                            <span className="quant-edge-sample">
                                n={quantHistogram.total_count}
                            </span>
                        </div>
                        <div className="range-histogram-headline">
                            <span
                                className={
                                    isHistogramUp
                                        ? "range-delta-up"
                                        : "range-delta-down"
                                }
                            >
                                {isHistogramUp ? "▲ +" : "▼ -"}$
                                {Math.abs(currentDiff).toFixed(2)}
                            </span>
                            <span>
                                pctl{" "}
                                {quantHistogram.current_percentile !== null
                                    ? `${quantHistogram.current_percentile.toFixed(1)}%`
                                    : "n/a"}
                            </span>
                        </div>
                        <div className="range-histogram-track">
                            <div className="range-histogram-bars">
                                {histogramBins.map((bin, idx) => {
                                    const heightPct =
                                        histogramMaxCount > 0
                                            ? Math.max(
                                                  8,
                                                  Math.round(
                                                      (bin.count /
                                                          histogramMaxCount) *
                                                          100,
                                                  ),
                                              )
                                            : 8;
                                    const isCurrent = idx === currentBinIndex;
                                    return (
                                        <div
                                            key={`${bin.inf_range}-${bin.sup_range}-${idx}`}
                                            className={`range-histogram-bar ${
                                                isCurrent
                                                    ? isHistogramUp
                                                        ? "range-histogram-bar-current-up"
                                                        : "range-histogram-bar-current-down"
                                                    : ""
                                            }`}
                                            style={{ height: `${heightPct}%` }}
                                            title={`[${bin.inf_range.toFixed(2)}, ${bin.sup_range.toFixed(2)}) n=${bin.count}`}
                                        />
                                    );
                                })}
                            </div>
                            {currentMarkerLeftPct !== null && (
                                <div
                                    className="range-histogram-marker"
                                    style={{ left: `${currentMarkerLeftPct}%` }}
                                />
                            )}
                        </div>
                    </section>
                )}

            <div className="compact-panels-grid">
                <div className="compact-panel">
                    <div className="compact-panel-title">
                        {tradingMode === "bot" ? "Bot Trade" : "Manual Trade"}
                    </div>
                    {tradingMode === "bot" ? (
                        <div className="bot-trade-subcards">
                            <div className="bot-trade-subcard bot-trade-subcard-up">
                                <div className="bot-trade-subcard-head">
                                    <div className="bot-trade-subcard-title">
                                        <span className="bot-trade-side-label">
                                            UP
                                        </span>
                                        <span className="bot-trade-side-pct">
                                            {(yesPrice * 100).toFixed(0)}%
                                        </span>
                                    </div>
                                    <div className="bot-trade-ks-inline">
                                        <span
                                            title={ksTooltip(kellyUp.edgePct)}
                                        >
                                            KS {kellyUp.pct.toFixed(2)}% ($
                                            {formatUsd(kellyUp.usd)})
                                        </span>
                                    </div>
                                </div>
                                <button
                                    type="button"
                                    className="bot-trade-buy-btn bot-trade-buy-btn-up"
                                    disabled={gateUp ? !gateUp.enabled : false}
                                    title={gateTooltip(gateUp)}
                                >
                                    Buy At {formatCents(yesPrice)}
                                </button>
                            </div>
                            <div className="bot-trade-subcard bot-trade-subcard-down">
                                <div className="bot-trade-subcard-head">
                                    <div className="bot-trade-subcard-title">
                                        <span className="bot-trade-side-label">
                                            DOWN
                                        </span>
                                        <span className="bot-trade-side-pct">
                                            {(noPrice * 100).toFixed(0)}%
                                        </span>
                                    </div>
                                    <div className="bot-trade-ks-inline">
                                        <span
                                            title={ksTooltip(kellyDown.edgePct)}
                                        >
                                            KS {kellyDown.pct.toFixed(2)}% ($
                                            {formatUsd(kellyDown.usd)})
                                        </span>
                                    </div>
                                </div>
                                <button
                                    type="button"
                                    className="bot-trade-buy-btn bot-trade-buy-btn-down"
                                    disabled={
                                        gateDown ? !gateDown.enabled : false
                                    }
                                    title={gateTooltip(gateDown)}
                                >
                                    Buy At {formatCents(noPrice)}
                                </button>
                            </div>
                        </div>
                    ) : (
                        <TradingPanel eventId={eventId} event={event} />
                    )}
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
                    <PriceChart priceHistory={event.price_history} />
                </div>
            )}
        </article>
    );
}

export default memo(EventCard);
