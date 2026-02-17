import { useEffect, useMemo, useState } from "react";

type Ticker = "ALL" | "BTC" | "ETH" | "SOL" | "XRP";

interface SummaryRow {
    ticker: string;
    signals: number;
    wins: number;
    hit_rate_pct: number;
    total_pnl_usd: number;
    avg_edge_pct: number;
    avg_minutes_to_close: number;
}

interface SummaryResponse {
    days: number;
    ticker_filter: string | null;
    summary: SummaryRow[];
}

interface RawOutcome {
    signal_id: string;
    closed_at_utc: string;
    event_id: string;
    ticker: string;
    timeframe_minutes: string;
    side: "up" | "down";
    won: string;
    pnl_usd: string;
    entry_side_price: string;
    actual_outcome: "up" | "down";
}

interface RawResponse {
    count: number;
    ticker_filter: string | null;
    rows: RawOutcome[];
}

const DAYS_OPTIONS = [1, 3, 7, 14, 30];
const TICKERS: Ticker[] = ["ALL", "BTC", "ETH", "SOL", "XRP"];

const asNumber = (value: unknown) => {
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
};

export default function OpportunitiesDashboard() {
    const [days, setDays] = useState(7);
    const [ticker, setTicker] = useState<Ticker>("ALL");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [summary, setSummary] = useState<SummaryRow[]>([]);
    const [rawRows, setRawRows] = useState<RawOutcome[]>([]);

    const tickerQuery = ticker === "ALL" ? "" : `&ticker=${ticker}`;

    const loadData = async () => {
        setLoading(true);
        setError("");
        try {
            const [summaryRes, rawRes] = await Promise.all([
                fetch(`/api/stats/opportunities?days=${days}${tickerQuery}`),
                fetch(`/api/stats/opportunities/raw?limit=200${tickerQuery}`),
            ]);
            if (!summaryRes.ok || !rawRes.ok) {
                throw new Error(
                    `Failed to load analytics (${summaryRes.status}/${rawRes.status})`,
                );
            }
            const summaryJson = (await summaryRes.json()) as SummaryResponse;
            const rawJson = (await rawRes.json()) as RawResponse;
            setSummary(Array.isArray(summaryJson.summary) ? summaryJson.summary : []);
            setRawRows(Array.isArray(rawJson.rows) ? rawJson.rows : []);
        } catch (e) {
            setError(e instanceof Error ? e.message : "Failed to load analytics");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadData();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [days, ticker]);

    const totals = useMemo(() => {
        let signals = 0;
        let wins = 0;
        let pnl = 0;
        for (const row of rawRows) {
            signals += 1;
            wins += asNumber(row.won);
            pnl += asNumber(row.pnl_usd);
        }
        return {
            signals,
            wins,
            pnl,
            hitRate: signals > 0 ? (wins / signals) * 100 : 0,
            avgPnl: signals > 0 ? pnl / signals : 0,
        };
    }, [rawRows]);

    const bySide = useMemo(() => {
        const acc: Record<string, { n: number; wins: number; pnl: number }> = {
            up: { n: 0, wins: 0, pnl: 0 },
            down: { n: 0, wins: 0, pnl: 0 },
        };
        for (const row of rawRows) {
            const side = row.side === "down" ? "down" : "up";
            acc[side].n += 1;
            acc[side].wins += asNumber(row.won);
            acc[side].pnl += asNumber(row.pnl_usd);
        }
        return acc;
    }, [rawRows]);

    const byTimeframe = useMemo(() => {
        const acc: Record<string, { n: number; wins: number; pnl: number }> = {};
        for (const row of rawRows) {
            const tf = `${asNumber(row.timeframe_minutes)}m`;
            if (!acc[tf]) acc[tf] = { n: 0, wins: 0, pnl: 0 };
            acc[tf].n += 1;
            acc[tf].wins += asNumber(row.won);
            acc[tf].pnl += asNumber(row.pnl_usd);
        }
        return Object.entries(acc).sort((a, b) => a[0].localeCompare(b[0]));
    }, [rawRows]);

    return (
        <main className="analytics-page">
            <section className="analytics-controls">
                <label>
                    Window
                    <select
                        value={days}
                        onChange={(e) => setDays(Number(e.target.value))}
                    >
                        {DAYS_OPTIONS.map((value) => (
                            <option key={value} value={value}>
                                {value}d
                            </option>
                        ))}
                    </select>
                </label>
                <label>
                    Ticker
                    <select
                        value={ticker}
                        onChange={(e) => setTicker(e.target.value as Ticker)}
                    >
                        {TICKERS.map((value) => (
                            <option key={value} value={value}>
                                {value}
                            </option>
                        ))}
                    </select>
                </label>
                <button onClick={loadData} disabled={loading}>
                    {loading ? "Refreshing..." : "Refresh"}
                </button>
            </section>

            {error && <div className="analytics-error">{error}</div>}

            <section className="analytics-kpis">
                <article className="analytics-kpi-card">
                    <div className="kpi-label">Signals</div>
                    <div className="kpi-value">{totals.signals}</div>
                </article>
                <article className="analytics-kpi-card">
                    <div className="kpi-label">Hit Rate</div>
                    <div className="kpi-value">{totals.hitRate.toFixed(2)}%</div>
                </article>
                <article className="analytics-kpi-card">
                    <div className="kpi-label">Total PnL</div>
                    <div className="kpi-value">${totals.pnl.toFixed(2)}</div>
                </article>
                <article className="analytics-kpi-card">
                    <div className="kpi-label">Avg PnL / Signal</div>
                    <div className="kpi-value">${totals.avgPnl.toFixed(2)}</div>
                </article>
            </section>

            <section className="analytics-panels">
                <article className="analytics-panel">
                    <h3>By Ticker</h3>
                    <table className="analytics-table">
                        <thead>
                            <tr>
                                <th>Ticker</th>
                                <th>Signals</th>
                                <th>Hit Rate</th>
                                <th>PnL</th>
                            </tr>
                        </thead>
                        <tbody>
                            {summary.map((row) => (
                                <tr key={row.ticker}>
                                    <td>{row.ticker}</td>
                                    <td>{row.signals}</td>
                                    <td>{row.hit_rate_pct.toFixed(2)}%</td>
                                    <td>${row.total_pnl_usd.toFixed(2)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </article>

                <article className="analytics-panel">
                    <h3>By Side</h3>
                    <table className="analytics-table">
                        <thead>
                            <tr>
                                <th>Side</th>
                                <th>Signals</th>
                                <th>Hit Rate</th>
                                <th>PnL</th>
                            </tr>
                        </thead>
                        <tbody>
                            {(["up", "down"] as const).map((side) => {
                                const item = bySide[side];
                                const hitRate =
                                    item.n > 0 ? (item.wins / item.n) * 100 : 0;
                                return (
                                    <tr key={side}>
                                        <td>{side.toUpperCase()}</td>
                                        <td>{item.n}</td>
                                        <td>{hitRate.toFixed(2)}%</td>
                                        <td>${item.pnl.toFixed(2)}</td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </article>

                <article className="analytics-panel">
                    <h3>By Timeframe</h3>
                    <table className="analytics-table">
                        <thead>
                            <tr>
                                <th>TF</th>
                                <th>Signals</th>
                                <th>Hit Rate</th>
                                <th>PnL</th>
                            </tr>
                        </thead>
                        <tbody>
                            {byTimeframe.map(([tf, item]) => {
                                const hitRate =
                                    item.n > 0 ? (item.wins / item.n) * 100 : 0;
                                return (
                                    <tr key={tf}>
                                        <td>{tf}</td>
                                        <td>{item.n}</td>
                                        <td>{hitRate.toFixed(2)}%</td>
                                        <td>${item.pnl.toFixed(2)}</td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </article>
            </section>

            <section className="analytics-panel">
                <h3>Recent Outcomes</h3>
                <table className="analytics-table">
                    <thead>
                        <tr>
                            <th>Closed (UTC)</th>
                            <th>Ticker</th>
                            <th>TF</th>
                            <th>Side</th>
                            <th>Won</th>
                            <th>PnL</th>
                            <th>Event</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rawRows
                            .slice()
                            .reverse()
                            .slice(0, 50)
                            .map((row) => (
                                <tr key={row.signal_id}>
                                    <td>{row.closed_at_utc.replace("T", " ").slice(0, 19)}</td>
                                    <td>{row.ticker}</td>
                                    <td>{row.timeframe_minutes}m</td>
                                    <td>{row.side.toUpperCase()}</td>
                                    <td>{row.won === "1" ? "YES" : "NO"}</td>
                                    <td>${asNumber(row.pnl_usd).toFixed(2)}</td>
                                    <td className="analytics-event-id">{row.event_id}</td>
                                </tr>
                            ))}
                    </tbody>
                </table>
            </section>
        </main>
    );
}
