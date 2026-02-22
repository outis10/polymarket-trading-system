import { useState, useEffect, useCallback } from "react";
import type { Position } from "../types/events";

interface PositionDisplayProps {
    eventId: string;
}

export default function PositionDisplay({ eventId }: PositionDisplayProps) {
    const [positions, setPositions] = useState<Position[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchPositions = useCallback(async () => {
        try {
            const res = await fetch(`/api/positions/${eventId}`);
            if (!res.ok) {
                throw new Error("Failed to fetch positions");
            }
            const data = await res.json();
            setPositions(data.positions || []);
            setError(null);
        } catch (err) {
            setError("Could not load positions");
            setPositions([]);
        } finally {
            setLoading(false);
        }
    }, [eventId]);

    useEffect(() => {
        fetchPositions();
        const onPositionsRefresh = (evt: Event) => {
            const custom = evt as CustomEvent<{ eventId?: string }>;
            const targetEventId = custom.detail?.eventId;
            if (!targetEventId || targetEventId === eventId) {
                fetchPositions();
            }
        };
        window.addEventListener("positions_refresh", onPositionsRefresh);

        // Fallback reconciliation only: primary refresh is event-driven after fills.
        const interval = setInterval(fetchPositions, 90000);
        return () => {
            window.removeEventListener("positions_refresh", onPositionsRefresh);
            clearInterval(interval);
        };
    }, [fetchPositions]);

    if (loading) {
        return (
            <div className="positions-panel">
                <div className="positions-header">
                    <span className="positions-title">Positions</span>
                </div>
                <div className="positions-loading">Loading...</div>
            </div>
        );
    }

    if (error || positions.length === 0) {
        return (
            <div className="positions-panel">
                <div className="positions-header">
                    <span className="positions-title">Positions</span>
                </div>
                <div className="positions-empty">
                    {error ? "Could not load positions" : "No open positions"}
                </div>
            </div>
        );
    }

    return (
        <div className="positions-panel">
            <div className="positions-header">
                <span className="positions-title">Positions</span>
            </div>

            <div className="positions-table-wrap">
                <table className="positions-table">
                    <thead>
                        <tr>
                            <th>OUTCOME</th>
                            <th>QTY</th>
                            <th>PRICE</th>
                            <th>VALUE</th>
                            <th>RETURN</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        {positions.map((pos) => (
                            <tr key={pos.outcome}>
                                <td>
                                    <span
                                        className={`position-outcome ${pos.outcome === "Up" ? "outcome-up-text" : "outcome-down-text"}`}
                                    >
                                        {pos.outcome}
                                    </span>
                                </td>
                                <td className="position-qty">{pos.qty}</td>
                                <td className="position-avg">
                                    {pos.avg_price.toFixed(3)}
                                </td>
                                <td className="position-value">
                                    <div>${pos.value.toFixed(2)}</div>
                                    <div className="position-cost">
                                        Cost ${pos.cost.toFixed(2)}
                                    </div>
                                </td>
                                <td
                                    className={`position-return ${pos.return_value >= 0 ? "return-positive" : "return-negative"}`}
                                >
                                    {pos.return_value >= 0 ? "+" : ""}$
                                    {pos.return_value.toFixed(2)}
                                    <span className="return-pct">
                                        {" "}
                                        ({pos.return_pct.toFixed(2)}%)
                                    </span>
                                </td>
                                <td>
                                    <button className="position-sell-btn">
                                        Sell
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
