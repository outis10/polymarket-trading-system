import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "../auth/apiFetch";
import type { Position } from "../types/events";

interface PositionDisplayProps {
    eventId: string;
}

export default function PositionDisplay({ eventId }: PositionDisplayProps) {
    const [positions, setPositions] = useState<Position[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [sellSubmitting, setSellSubmitting] = useState<string | null>(null);
    const [sellResult, setSellResult] = useState<{
        type: "success" | "error";
        message: string;
    } | null>(null);

    const fetchPositions = useCallback(async () => {
        try {
            const res = await apiFetch(`/api/positions/${eventId}`);
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

    const submitSell = useCallback(
        async (pos: Position) => {
            const outcome = pos.outcome.toLowerCase() as "up" | "down";
            if (sellSubmitting === outcome) return;
            if (pos.qty <= 0) return;

            setSellSubmitting(outcome);
            setSellResult(null);
            try {
                const res = await apiFetch("/api/orders", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        event_id: eventId,
                        side: "Sell",
                        outcome,
                        order_type: "market",
                        price: pos.current_price,
                        shares: pos.qty,
                    }),
                });

                let data: { detail?: string; message?: string } = {};
                try {
                    data = await res.json();
                } catch {
                    data = {};
                }

                if (res.ok) {
                    setSellResult({
                        type: "success",
                        message:
                            data.message ||
                            `Sell sent (${pos.outcome} ${pos.qty} sh)`,
                    });
                    setTimeout(() => {
                        fetchPositions();
                        window.dispatchEvent(
                            new CustomEvent("positions_refresh", {
                                detail: { eventId },
                            }),
                        );
                    }, 1500);
                } else {
                    setSellResult({
                        type: "error",
                        message:
                            data.detail ||
                            data.message ||
                            `Sell failed (${res.status})`,
                    });
                }
            } catch {
                setSellResult({ type: "error", message: "Network error" });
            } finally {
                setSellSubmitting(null);
            }
        },
        [eventId, sellSubmitting, fetchPositions],
    );

    useEffect(() => {
        if (!sellResult) return;
        const t = setTimeout(() => setSellResult(null), 5000);
        return () => clearTimeout(t);
    }, [sellResult]);

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
                        {positions.map((pos) => {
                            const outcome = pos.outcome.toLowerCase() as
                                | "up"
                                | "down";
                            const isSelling = sellSubmitting === outcome;
                            return (
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
                                        <button
                                            className="position-sell-btn"
                                            disabled={isSelling}
                                            title={`Market sell ${pos.qty} ${pos.outcome} shares`}
                                            onClick={() => submitSell(pos)}
                                        >
                                            {isSelling ? "..." : "Sell"}
                                        </button>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            {sellResult && (
                <div
                    className={`trade-toast trade-toast-${sellResult.type}`}
                >
                    {sellResult.message}
                </div>
            )}
        </div>
    );
}
