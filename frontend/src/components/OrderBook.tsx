import { memo, useMemo, useState } from "react";
import type { OrderBookData } from "../types/events";

interface OrderBookProps {
    orderBookYes: OrderBookData | null;
    orderBookNo: OrderBookData | null;
}

interface BookLevelsListProps {
    title: string;
    levels: Array<{ price: number; shares: number; total: number }>;
    tone: "up" | "down";
}

function BookLevelsList({ title, levels, tone }: BookLevelsListProps) {
    const maxShares = Math.max(1, ...levels.map((lvl) => lvl.shares));

    return (
        <div className="book-levels-block">
            <div className="book-levels-title">{title}</div>
            {levels.length === 0 ? (
                <div className="order-book-empty-inline">No levels</div>
            ) : (
                <div className="book-levels-list">
                    {levels.map((lvl, idx) => {
                        const depth = Math.max(
                            4,
                            (lvl.shares / maxShares) * 100,
                        );
                        return (
                            <div
                                key={`${title}-${lvl.price}-${idx}`}
                                className="book-level-item"
                            >
                                <div
                                    className={`book-level-depth ${tone === "up" ? "book-level-depth-up" : "book-level-depth-down"}`}
                                    style={{ width: `${depth}%` }}
                                />
                                <span className="book-level-price">
                                    {Math.round(lvl.price * 100)}¢
                                </span>
                                <span className="book-level-shares">
                                    {lvl.shares.toFixed(2)} sh
                                </span>
                                <span className="book-level-total">
                                    ${lvl.total.toFixed(2)}
                                </span>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

function OrderBook({ orderBookYes, orderBookNo }: OrderBookProps) {
    const [activeTab, setActiveTab] = useState<"up" | "down">("up");
    const activeBook = activeTab === "up" ? orderBookYes : orderBookNo;

    const stats = useMemo(() => {
        if (!activeBook) {
            return { lastPrice: 0, spread: 0, volume: 0 };
        }
        const bestAsk = activeBook.asks[0]?.price ?? 0.5;
        const bestBid = activeBook.bids[0]?.price ?? 0.49;
        const spread = Math.max(0, bestAsk - bestBid);
        return {
            lastPrice: activeBook.last_price ?? 0,
            spread,
            volume: activeBook.volume ?? 0,
        };
    }, [activeBook]);

    if (!activeBook) {
        return (
            <div className="order-book-empty">
                Waiting for order book data...
            </div>
        );
    }

    const asks = activeBook.asks.slice(0, 6);
    const bids = activeBook.bids.slice(0, 6);

    return (
        <div className="order-book-card order-book-card-compact">
            <div className="order-book-tabs">
                <button
                    className={`order-book-tab ${activeTab === "up" ? "order-book-tab-active" : ""}`}
                    onClick={() => setActiveTab("up")}
                >
                    Trade Up
                </button>
                <button
                    className={`order-book-tab ${activeTab === "down" ? "order-book-tab-active" : ""}`}
                    onClick={() => setActiveTab("down")}
                >
                    Trade Down
                </button>
            </div>

            <div className="order-book-stats-row">
                <span>Last {Math.round(stats.lastPrice * 100)}¢</span>
                <span>Spread {Math.round(stats.spread * 100)}¢</span>
                <span>Vol ${(stats.volume / 1000).toFixed(1)}k</span>
            </div>

            <div className="book-levels-grid">
                <BookLevelsList title="Latest asks" levels={asks} tone="down" />
                <BookLevelsList title="Latest bids" levels={bids} tone="up" />
            </div>
        </div>
    );
}

export default memo(OrderBook);
