import { useState, useCallback, useMemo } from "react";
import type { EventData, OrderRequest, OrderResponse } from "../types/events";

interface TradingPanelProps {
    eventId: string;
    event: EventData;
}

export default function TradingPanel({ eventId, event }: TradingPanelProps) {
    const [side, setSide] = useState<"Buy" | "Sell">("Buy");
    const [orderType, setOrderType] = useState<"limit" | "market">("limit");
    const [limitPrice, setLimitPrice] = useState(event.yes_price || 0.5);
    const [shares, setShares] = useState(0);
    const [tradeResult, setTradeResult] = useState<{
        type: string;
        message: string;
    } | null>(null);
    const [isSubmitting, setIsSubmitting] = useState(false);

    const yesPrice = event.yes_price || 0.5;
    const noPrice = event.no_price || 0.5;
    const normalizedLimitPrice = useMemo(
        () => Math.min(0.99, Math.max(0.01, limitPrice)),
        [limitPrice],
    );

    const handleQuickAmount = (amount: number) => {
        setShares(Math.max(0, shares + amount));
    };

    const handleTrade = useCallback(
        async (outcome: "up" | "down") => {
            if (shares <= 0 || isSubmitting) return;

            setIsSubmitting(true);
            setTradeResult(null);
            const referencePrice = outcome === "up" ? yesPrice : noPrice;
            const effectivePrice =
                orderType === "market" ? referencePrice : normalizedLimitPrice;

            const order: OrderRequest = {
                event_id: eventId,
                side,
                outcome,
                order_type: orderType,
                price: effectivePrice,
                shares,
            };

            try {
                const res = await fetch("/api/orders", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(order),
                });

                let data: Partial<OrderResponse> & { detail?: string } = {};
                try {
                    data = await res.json();
                } catch {
                    data = {};
                }

                if (res.ok) {
                    setTradeResult({
                        type: side === "Buy" ? "success" : "warning",
                        message:
                            data.message ||
                            `Order ${data.status}: ${data.order_id}`,
                    });
                    setShares(0);
                } else {
                    setTradeResult({
                        type: "error",
                        message:
                            data.message ||
                            data.detail ||
                            `Order failed (${res.status})`,
                    });
                }
            } catch (err) {
                setTradeResult({
                    type: "error",
                    message: "Network error",
                });
            } finally {
                setIsSubmitting(false);
            }
        },
        [
            eventId,
            side,
            orderType,
            normalizedLimitPrice,
            yesPrice,
            noPrice,
            shares,
            isSubmitting,
        ],
    );

    const estimatedCostUp =
        shares * (orderType === "market" ? yesPrice : normalizedLimitPrice);
    const estimatedCostDown =
        shares * (orderType === "market" ? noPrice : normalizedLimitPrice);

    return (
        <div className="trading-panel trading-panel-compact">
            <div className="trading-panel-header trading-panel-header-compact">
                <div className="buy-sell-tabs">
                    <button
                        className={`buy-sell-tab ${side === "Buy" ? "buy-tab-active" : ""}`}
                        onClick={() => setSide("Buy")}
                    >
                        Buy
                    </button>
                    <button
                        className={`buy-sell-tab ${side === "Sell" ? "sell-tab-active" : ""}`}
                        onClick={() => setSide("Sell")}
                    >
                        Sell
                    </button>
                </div>
                <select
                    className="order-type-select"
                    value={orderType}
                    onChange={(e) =>
                        setOrderType(e.target.value as "limit" | "market")
                    }
                >
                    <option value="market">Market</option>
                    <option value="limit">Limit</option>
                </select>
            </div>

            {orderType === "limit" && (
                <div className="input-group">
                    <label className="input-label">Limit Price</label>
                    <input
                        type="number"
                        className="trading-input"
                        min={0.01}
                        max={0.99}
                        step={0.01}
                        value={normalizedLimitPrice}
                        onChange={(e) => setLimitPrice(Number(e.target.value))}
                    />
                </div>
            )}

            <div className="input-group">
                <label className="input-label">Shares</label>
                <input
                    type="number"
                    className="trading-input"
                    min={0}
                    max={10000}
                    step={1}
                    value={shares}
                    onChange={(e) =>
                        setShares(Math.max(0, Number(e.target.value)))
                    }
                />
            </div>

            <div className="quick-amounts">
                <button
                    className="quick-btn"
                    onClick={() => handleQuickAmount(-100)}
                >
                    -100
                </button>
                <button
                    className="quick-btn"
                    onClick={() => handleQuickAmount(-10)}
                >
                    -10
                </button>
                <button
                    className="quick-btn"
                    onClick={() => handleQuickAmount(10)}
                >
                    +10
                </button>
                <button
                    className="quick-btn"
                    onClick={() => handleQuickAmount(100)}
                >
                    +100
                </button>
            </div>

            <div className="trading-panel-footer trading-panel-footer-compact">
                <div className="summary-row">
                    <span className="summary-label">Up est. cost</span>
                    <span className="summary-value">
                        ${estimatedCostUp.toFixed(2)}
                    </span>
                </div>
                <div className="summary-row">
                    <span className="summary-label">Down est. cost</span>
                    <span className="summary-value">
                        ${estimatedCostDown.toFixed(2)}
                    </span>
                </div>

                <div className="compact-cta-grid">
                    <button
                        className="trade-btn trade-btn-up"
                        disabled={shares === 0 || isSubmitting}
                        onClick={() => handleTrade("up")}
                    >
                        {isSubmitting
                            ? "Submitting..."
                            : `${side} Up ${Math.round(yesPrice * 100)}¢`}
                    </button>
                    <button
                        className="trade-btn trade-btn-down"
                        disabled={shares === 0 || isSubmitting}
                        onClick={() => handleTrade("down")}
                    >
                        {isSubmitting
                            ? "Submitting..."
                            : `${side} Down ${Math.round(noPrice * 100)}¢`}
                    </button>
                </div>

                {tradeResult && (
                    <div
                        className={`trade-toast trade-toast-${tradeResult.type}`}
                    >
                        {tradeResult.message}
                    </div>
                )}
            </div>
        </div>
    );
}
