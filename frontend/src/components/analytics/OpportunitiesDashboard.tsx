import { useEffect, useMemo, useState } from "react";

type Ticker = "ALL" | "BTC" | "ETH" | "SOL" | "XRP";
type RegimeFilter = "all" | "weekday" | "weekend";

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
    percentile_at_signal?: string;
}

interface RawResponse {
    count: number;
    ticker_filter: string | null;
    rows: RawOutcome[];
}

interface RawSignal {
    signal_id: string;
    detected_at_utc: string;
    event_id: string;
    ticker: string;
    timeframe_minutes: string;
    side: "up" | "down";
    stake_usd: string;
}

interface RawSignalResponse {
    count: number;
    ticker_filter: string | null;
    rows: RawSignal[];
}

interface RawBlocked {
    blocked_id: string;
    detected_at_utc: string;
    event_id: string;
    ticker: string;
    timeframe_minutes: string;
    side: "up" | "down";
    blocked_reason: string;
    estimated_stake_usd: string;
}

interface RawBlockedResponse {
    count: number;
    ticker_filter: string | null;
    rows: RawBlocked[];
}

const DAYS_OPTIONS = [1, 3, 7, 14, 30];
const TICKERS: Ticker[] = ["ALL", "BTC", "ETH", "SOL", "XRP"];
const REGIME_OPTIONS: Array<{ value: RegimeFilter; label: string }> = [
    { value: "all", label: "All" },
    { value: "weekday", label: "Weekday" },
    { value: "weekend", label: "Weekend" },
];

const asNumber = (value: unknown) => {
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
};

export default function OpportunitiesDashboard() {
    const [days, setDays] = useState(7);
    const [ticker, setTicker] = useState<Ticker>("ALL");
    const [regimeFilter, setRegimeFilter] = useState<RegimeFilter>("all");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [summary, setSummary] = useState<SummaryRow[]>([]);
    const [rawRows, setRawRows] = useState<RawOutcome[]>([]);
    const [signalRows, setSignalRows] = useState<RawSignal[]>([]);
    const [blockedRows, setBlockedRows] = useState<RawBlocked[]>([]);

    const tickerQuery = ticker === "ALL" ? "" : `&ticker=${ticker}`;

    const loadData = async () => {
        setLoading(true);
        setError("");
        try {
            const [summaryRes, rawRes, signalsRes, blockedRes] =
                await Promise.all([
                    fetch(
                        `/api/stats/opportunities?days=${days}${tickerQuery}`,
                    ),
                    fetch(
                        `/api/stats/opportunities/raw?limit=5000${tickerQuery}`,
                    ),
                    fetch(
                        `/api/stats/opportunities/signals/raw?limit=5000${tickerQuery}`,
                    ),
                    fetch(
                        `/api/stats/opportunities/blocked/raw?limit=5000${tickerQuery}`,
                    ),
                ]);
            if (
                !summaryRes.ok ||
                !rawRes.ok ||
                !signalsRes.ok ||
                !blockedRes.ok
            ) {
                throw new Error(
                    `Failed to load analytics (${summaryRes.status}/${rawRes.status}/${signalsRes.status}/${blockedRes.status})`,
                );
            }
            const summaryJson = (await summaryRes.json()) as SummaryResponse;
            const rawJson = (await rawRes.json()) as RawResponse;
            const signalJson = (await signalsRes.json()) as RawSignalResponse;
            const blockedJson = (await blockedRes.json()) as RawBlockedResponse;
            setSummary(
                Array.isArray(summaryJson.summary) ? summaryJson.summary : [],
            );
            setRawRows(Array.isArray(rawJson.rows) ? rawJson.rows : []);
            setSignalRows(
                Array.isArray(signalJson.rows) ? signalJson.rows : [],
            );
            setBlockedRows(
                Array.isArray(blockedJson.rows) ? blockedJson.rows : [],
            );
        } catch (e) {
            setError(
                e instanceof Error ? e.message : "Failed to load analytics",
            );
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadData();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [days, ticker]);

    const filteredRows = useMemo(() => {
        if (regimeFilter === "all") return rawRows;
        return rawRows.filter((row) => {
            const dt = new Date(row.closed_at_utc);
            const day = dt.getUTCDay();
            const regime = day === 0 || day === 6 ? "weekend" : "weekday";
            return regime === regimeFilter;
        });
    }, [rawRows, regimeFilter]);

    const filteredBlockedRows = useMemo(() => {
        if (regimeFilter === "all") return blockedRows;
        return blockedRows.filter((row) => {
            const dt = new Date(row.detected_at_utc);
            const day = dt.getUTCDay();
            const regime = day === 0 || day === 6 ? "weekend" : "weekday";
            return regime === regimeFilter;
        });
    }, [blockedRows, regimeFilter]);

    const filteredSignalRows = useMemo(() => {
        if (regimeFilter === "all") return signalRows;
        return signalRows.filter((row) => {
            const dt = new Date(row.detected_at_utc);
            const day = dt.getUTCDay();
            const regime = day === 0 || day === 6 ? "weekend" : "weekday";
            return regime === regimeFilter;
        });
    }, [signalRows, regimeFilter]);

    const totals = useMemo(() => {
        let signals = 0;
        let wins = 0;
        let pnl = 0;
        for (const row of filteredRows) {
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
    }, [filteredRows]);

    const opportunityFunnel = useMemo(() => {
        const registered = filteredSignalRows.length;
        const blocked = filteredBlockedRows.length;
        const detected = registered + blocked;
        const executablePct = detected > 0 ? (registered / detected) * 100 : 0;
        return { detected, registered, blocked, executablePct };
    }, [filteredSignalRows, filteredBlockedRows]);

    const summaryForView = useMemo(() => {
        if (regimeFilter === "all") return summary;
        const acc: Record<
            string,
            { ticker: string; signals: number; wins: number; pnl: number }
        > = {};
        for (const row of filteredRows) {
            const tk = String(row.ticker || "UNKNOWN").toUpperCase();
            if (!acc[tk]) {
                acc[tk] = { ticker: tk, signals: 0, wins: 0, pnl: 0 };
            }
            acc[tk].signals += 1;
            acc[tk].wins += asNumber(row.won);
            acc[tk].pnl += asNumber(row.pnl_usd);
        }
        return Object.values(acc)
            .map((r) => ({
                ticker: r.ticker,
                signals: r.signals,
                wins: r.wins,
                hit_rate_pct: r.signals > 0 ? (r.wins / r.signals) * 100 : 0,
                total_pnl_usd: r.pnl,
                avg_edge_pct: 0,
                avg_minutes_to_close: 0,
            }))
            .sort(
                (a, b) =>
                    b.signals - a.signals || a.ticker.localeCompare(b.ticker),
            );
    }, [summary, filteredRows, regimeFilter]);

    const bySide = useMemo(() => {
        const acc: Record<string, { n: number; wins: number; pnl: number }> = {
            up: { n: 0, wins: 0, pnl: 0 },
            down: { n: 0, wins: 0, pnl: 0 },
        };
        for (const row of filteredRows) {
            const side = row.side === "down" ? "down" : "up";
            acc[side].n += 1;
            acc[side].wins += asNumber(row.won);
            acc[side].pnl += asNumber(row.pnl_usd);
        }
        return acc;
    }, [filteredRows]);

    const byTimeframe = useMemo(() => {
        const acc: Record<string, { n: number; wins: number; pnl: number }> =
            {};
        for (const row of filteredRows) {
            const tf = `${asNumber(row.timeframe_minutes)}m`;
            if (!acc[tf]) acc[tf] = { n: 0, wins: 0, pnl: 0 };
            acc[tf].n += 1;
            acc[tf].wins += asNumber(row.won);
            acc[tf].pnl += asNumber(row.pnl_usd);
        }
        return Object.entries(acc).sort((a, b) => a[0].localeCompare(b[0]));
    }, [filteredRows]);

    const byRegime = useMemo(() => {
        const acc: Record<
            "weekday" | "weekend",
            { n: number; wins: number; pnl: number }
        > = {
            weekday: { n: 0, wins: 0, pnl: 0 },
            weekend: { n: 0, wins: 0, pnl: 0 },
        };
        for (const row of rawRows) {
            const dt = new Date(row.closed_at_utc);
            const day = dt.getUTCDay();
            const regime = day === 0 || day === 6 ? "weekend" : "weekday";
            acc[regime].n += 1;
            acc[regime].wins += asNumber(row.won);
            acc[regime].pnl += asNumber(row.pnl_usd);
        }
        return acc;
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
                <label>
                    Regime
                    <select
                        value={regimeFilter}
                        onChange={(e) =>
                            setRegimeFilter(e.target.value as RegimeFilter)
                        }
                    >
                        {REGIME_OPTIONS.map((value) => (
                            <option key={value.value} value={value.value}>
                                {value.label}
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
                    <div className="kpi-value">
                        {totals.hitRate.toFixed(2)}%
                    </div>
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

            <section className="analytics-kpis">
                <article className="analytics-kpi-card">
                    <div className="kpi-label">Detected</div>
                    <div className="kpi-value">
                        {opportunityFunnel.detected}
                    </div>
                </article>
                <article className="analytics-kpi-card">
                    <div className="kpi-label">Registered</div>
                    <div className="kpi-value">
                        {opportunityFunnel.registered}
                    </div>
                </article>
                <article className="analytics-kpi-card">
                    <div className="kpi-label">Blocked</div>
                    <div className="kpi-value">{opportunityFunnel.blocked}</div>
                </article>
                <article className="analytics-kpi-card">
                    <div className="kpi-label">% Executable</div>
                    <div className="kpi-value">
                        {opportunityFunnel.executablePct.toFixed(2)}%
                    </div>
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
                            {summaryForView.map((row) => (
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

                <article className="analytics-panel">
                    <h3>Weekday vs Weekend (UTC)</h3>
                    <table className="analytics-table">
                        <thead>
                            <tr>
                                <th>Regime</th>
                                <th>Signals</th>
                                <th>Hit Rate</th>
                                <th>PnL</th>
                            </tr>
                        </thead>
                        <tbody>
                            {(["weekday", "weekend"] as const).map((regime) => {
                                const item = byRegime[regime];
                                const hitRate =
                                    item.n > 0 ? (item.wins / item.n) * 100 : 0;
                                return (
                                    <tr key={regime}>
                                        <td>
                                            {regime === "weekday"
                                                ? "Mon-Fri"
                                                : "Sat-Sun"}
                                        </td>
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
                            <th>Percentile @ Signal</th>
                            <th>Won</th>
                            <th>PnL</th>
                            <th>Event</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filteredRows
                            .slice()
                            .reverse()
                            .slice(0, 50)
                            .map((row) => (
                                <tr key={row.signal_id}>
                                    <td>
                                        {row.closed_at_utc
                                            .replace("T", " ")
                                            .slice(0, 19)}
                                    </td>
                                    <td>{row.ticker}</td>
                                    <td>{row.timeframe_minutes}m</td>
                                    <td>{row.side.toUpperCase()}</td>
                                    <td>
                                        {Number.isFinite(
                                            Number(row.percentile_at_signal),
                                        )
                                            ? `${asNumber(row.percentile_at_signal).toFixed(1)}%`
                                            : "n/a"}
                                    </td>
                                    <td>{row.won === "1" ? "YES" : "NO"}</td>
                                    <td>${asNumber(row.pnl_usd).toFixed(2)}</td>
                                    <td className="analytics-event-id">
                                        {row.event_id}
                                    </td>
                                </tr>
                            ))}
                    </tbody>
                </table>
            </section>

            <section className="analytics-panel">
                <h3>Blocked Opportunities (Not Registered)</h3>
                <table className="analytics-table">
                    <thead>
                        <tr>
                            <th>Detected (UTC)</th>
                            <th>Ticker</th>
                            <th>TF</th>
                            <th>Side</th>
                            <th>Reason</th>
                            <th>Est. Stake</th>
                            <th>Event</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filteredBlockedRows
                            .slice()
                            .reverse()
                            .slice(0, 50)
                            .map((row) => (
                                <tr key={row.blocked_id}>
                                    <td>
                                        {row.detected_at_utc
                                            .replace("T", " ")
                                            .slice(0, 19)}
                                    </td>
                                    <td>{row.ticker}</td>
                                    <td>{row.timeframe_minutes}m</td>
                                    <td>{row.side.toUpperCase()}</td>
                                    <td>{row.blocked_reason}</td>
                                    <td>
                                        $
                                        {asNumber(
                                            row.estimated_stake_usd,
                                        ).toFixed(2)}
                                    </td>
                                    <td className="analytics-event-id">
                                        {row.event_id}
                                    </td>
                                </tr>
                            ))}
                    </tbody>
                </table>
            </section>
        </main>
    );
}
