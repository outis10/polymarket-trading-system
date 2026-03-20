import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../../auth/apiFetch";
import { useEventsStore } from "../../stores/useEventsStore";
import OrderDiagnosticModal, {
    type DiagnosticTarget,
    type RawBotOrderFull,
    type RawBlockedFull,
} from "./OrderDiagnosticModal";
import EquityDrawdownChart, {
    EquityDrawdownPoint,
} from "./EquityDrawdownChart";
import TradingEquityCurveChart, {
    TradingEquityPoint,
} from "./TradingEquityCurveChart";

type Ticker = "ALL" | "BTC" | "ETH" | "SOL" | "XRP";
type RegimeFilter = "all" | "weekday" | "weekend";
type ChartScope = "selected" | "all";

interface RawOutcome {
    signal_id: string;
    closed_at_utc: string;
    event_id: string;
    ticker: string;
    timeframe_minutes: string;
    side: "up" | "down";
    won: string;
    pnl_usd: string;
    actual_outcome?: string;
    percentile_at_signal?: string;
    edge_pct_at_signal?: string;
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
    quant_prob_side?: string;
    edge_pct?: string;
    sample_size?: string;
}

interface RawSignalResponse {
    count: number;
    ticker_filter: string | null;
    rows: RawSignal[];
}

interface RawBlocked extends RawBlockedFull {
    side: "up" | "down";
}

interface RawBlockedResponse {
    count: number;
    ticker_filter: string | null;
    rows: RawBlocked[];
}

interface RawPaperTrade {
    decision_id: string;
    decision_time: string;
    event_id: string;
    ticker: string;
    timeframe?: string;
    event_end_utc: string;
    price_to_beat_at_decision?: string;
    current_price_at_decision?: string;
    diff_vs_ptb_at_decision?: string;
    stake_usd: string;
    shares_simulated?: string;
    slot: string;
    range: string;
    prob_up: string;
    marketProb_at_decision: string;
    QuantumEdge: string;
    side_taken: "up" | "down";
    event_outcome_real: "up" | "down" | "";
    pnl_simulated: string;
    pnl_sim_adjusted?: string;
    spread_pct_at_decision?: string;
    friction_cost_usd?: string;
    edge_at_fill_pct?: string;
    status: "pending" | "resolved";
    ladder_entry?: string;
}

interface RawPaperTradeResponse {
    count: number;
    ticker_filter: string | null;
    rows: RawPaperTrade[];
}

interface RawBotOrder {
    placed_at_utc: string;
    event_id: string;
    ticker: string;
    timeframe?: string;
    slot?: string;
    range?: string;
    side: "up" | "down";
    event_end_utc_at_send?: string;
    token_id: string;
    shares: string;
    price: string;
    notional_usd: string;
    order_id: string;
    quant_prob: string;
    edge_pct: string;
    price_source_at_send?: string;
    price_to_beat_at_send?: string;
    current_price_at_send?: string;
    diff_vs_ptb_at_send?: string;
    best_bid_at_send?: string;
    best_ask_at_send?: string;
    mid_at_send?: string;
    spread_at_send?: string;
    spread_pct_at_send?: string;
    fill_price_real?: string;
    filled_at_utc?: string;
    fill_latency_ms?: string;
    slippage_pct?: string;
    filled_notional_usd_real?: string;
    filled_shares_real?: string;
    fill_count?: string;
    fills_detail_json?: string;
    edge_at_fill_pct?: string;
    kelly_pct?: string;
    bankroll_usd?: string;
    percentile_at_signal?: string;
    ladder_entry?: string;
    // execution observability (v1.1-a)
    realized_slippage_bps?: string;
    implementation_shortfall_bps?: string;
    implementation_shortfall_usd?: string;
    fill_ratio?: string;
    maker_vs_taker_mode?: string;
    // fill simulator (v1.1-b)
    expected_avg_fill_price?: string;
    fill_sim_worst_price?: string;
    fill_sim_fillable_notional?: string;
    fill_sim_fillable_shares?: string;
    fill_sim_levels_consumed?: string;
    fill_sim_slippage_vs_ask_bps?: string;
    fill_sim_slippage_vs_mid_bps?: string;
    fill_sim_book_consumption_pct?: string;
    fill_sim_fully_fillable?: string;
    close_price_at_resolution?: string;
    event_outcome_real?: "up" | "down" | "";
    won?: string;
    pnl_simulated?: string;
    resolution_status?: "pending" | "resolved" | "";
    status: string;
}

interface RawBotOrderResponse {
    count: number;
    ticker_filter: string | null;
    days: number;
    rows: RawBotOrder[];
}

interface CalibrationBucket {
    key: string;
    rangeLabel: string;
    n: number;
    expectedPct: number;
    actualPct: number;
}

interface EdgeBucket {
    key: string;
    label: string;
    n: number;
    wins: number;
    pnl: number;
}

const DAYS_OPTIONS = [1, 3, 7, 14, 30];
const TICKERS: Ticker[] = ["ALL", "BTC", "ETH", "SOL", "XRP"];
const REGIME_OPTIONS: Array<{ value: RegimeFilter; label: string }> = [
    { value: "all", label: "All" },
    { value: "weekday", label: "Weekday" },
    { value: "weekend", label: "Weekend" },
];
const CHART_SCOPE_OPTIONS: Array<{ value: ChartScope; label: string }> = [
    { value: "selected", label: "Selected Ticker" },
    { value: "all", label: "All Tickers" },
];

const asNumber = (value: unknown) => {
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
};

const fmtPst = (isoStr: string | undefined | null): string => {
    if (!isoStr) return "";
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    return d.toLocaleString("en-US", {
        timeZone: "America/Los_Angeles",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
    }) + " PST";
};

const isWeekendUtc = (timestamp: string) => {
    const dt = new Date(timestamp);
    const day = dt.getUTCDay();
    return day === 0 || day === 6;
};

const inLastDays = (timestamp: string, days: number) => {
    const ts = new Date(timestamp).getTime();
    if (!Number.isFinite(ts)) return false;
    const now = Date.now();
    const horizonMs = Math.max(1, days) * 24 * 60 * 60 * 1000;
    return ts >= now - horizonMs;
};

const calibrationRangeLabel = (idx: number) => {
    const low = idx * 10;
    const high = (idx + 1) * 10;
    return `${low}-${high}%`;
};

const EDGE_BUCKETS: Array<{
    key: string;
    label: string;
    min: number;
    max: number;
}> = [
    { key: "lt0", label: "< 0%", min: Number.NEGATIVE_INFINITY, max: 0 },
    { key: "0_2", label: "0% - 2%", min: 0, max: 2 },
    { key: "2_5", label: "2% - 5%", min: 2, max: 5 },
    { key: "5_10", label: "5% - 10%", min: 5, max: 10 },
    { key: "gte10", label: ">= 10%", min: 10, max: Number.POSITIVE_INFINITY },
];

export default function OpportunitiesDashboard() {
    const runtimeSettings = useEventsStore((s) => s.settings);
    const updateRuntimeSettings = useEventsStore((s) => s.updateSettings);
    const [days, setDays] = useState(7);
    const [ticker, setTicker] = useState<Ticker>("ALL");
    const [regimeFilter, setRegimeFilter] = useState<RegimeFilter>("all");
    const [chartScope, setChartScope] = useState<ChartScope>("selected");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [rawRows, setRawRows] = useState<RawOutcome[]>([]);
    const [signalRows, setSignalRows] = useState<RawSignal[]>([]);
    const [blockedRows, setBlockedRows] = useState<RawBlocked[]>([]);
    const [paperRows, setPaperRows] = useState<RawPaperTrade[]>([]);
    const [botOrderRows, setBotOrderRows] = useState<RawBotOrder[]>([]);
    const [resettingLiveBaseline, setResettingLiveBaseline] = useState(false);
    const [diagnosticTarget, setDiagnosticTarget] =
        useState<DiagnosticTarget | null>(null);

    interface VolatilityTickerStat {
        signals_in_window: number;
        flips: number;
        alert_active: boolean;
        last_alerted_at: string | null;
    }
    interface VolatilityAlert {
        ticker: string;
        flips: number;
        signals_in_window: number;
        direction_history: string[];
        triggered_at: string;
    }
    interface VolatilityState {
        bot_mode: string;
        execution_enabled: boolean;
        has_pending_alert: boolean;
        pending_alert: VolatilityAlert | null;
        ticker_stats: Record<string, VolatilityTickerStat>;
        config: {
            flip_trigger: number;
            window_seconds: number;
            thresholds: Record<string, number>;
        };
    }
    const [volatilityState, setVolatilityState] =
        useState<VolatilityState | null>(null);

    const loadData = async () => {
        setLoading(true);
        setError("");
        try {
            const [rawRes, signalsRes, blockedRes, paperRes, botOrdersRes] =
                await Promise.all([
                    apiFetch(`/api/stats/opportunities/raw?limit=5000`),
                    apiFetch(`/api/stats/opportunities/signals/raw?limit=5000`),
                    apiFetch(`/api/stats/opportunities/blocked/raw?limit=5000`),
                    apiFetch(`/api/stats/paper/raw?limit=5000`),
                    apiFetch(
                        `/api/stats/bot-orders/raw?limit=5000&days=${days}`,
                    ),
                ]);
            if (
                !rawRes.ok ||
                !signalsRes.ok ||
                !blockedRes.ok ||
                !paperRes.ok ||
                !botOrdersRes.ok
            ) {
                throw new Error(
                    `Failed to load analytics (${rawRes.status}/${signalsRes.status}/${blockedRes.status}/${paperRes.status}/${botOrdersRes.status})`,
                );
            }

            const rawJson = (await rawRes.json()) as RawResponse;
            const signalJson = (await signalsRes.json()) as RawSignalResponse;
            const blockedJson = (await blockedRes.json()) as RawBlockedResponse;
            const paperJson = (await paperRes.json()) as RawPaperTradeResponse;
            const botOrdersJson =
                (await botOrdersRes.json()) as RawBotOrderResponse;
            setRawRows(Array.isArray(rawJson.rows) ? rawJson.rows : []);
            setSignalRows(
                Array.isArray(signalJson.rows) ? signalJson.rows : [],
            );
            setBlockedRows(
                Array.isArray(blockedJson.rows) ? blockedJson.rows : [],
            );
            setPaperRows(Array.isArray(paperJson.rows) ? paperJson.rows : []);
            setBotOrderRows(
                Array.isArray(botOrdersJson.rows) ? botOrdersJson.rows : [],
            );
        } catch (e) {
            setError(
                e instanceof Error ? e.message : "Failed to load analytics",
            );
        } finally {
            setLoading(false);
        }
    };

    const handleResetLiveBaseline = async () => {
        if (resettingLiveBaseline) return;
        const ok = window.confirm(
            "Reset live equity baseline? This will set baseline bankroll to 0 until the next real live fill captures a new start point.",
        );
        if (!ok) return;
        setResettingLiveBaseline(true);
        try {
            const res = await apiFetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    settings: {
                        live_equity_start_bankroll_usd: 0,
                        live_equity_start_at_utc: "",
                    },
                }),
            });
            if (!res.ok) {
                throw new Error(`Failed to reset baseline (${res.status})`);
            }
            updateRuntimeSettings({
                live_equity_start_bankroll_usd: 0,
                live_equity_start_at_utc: "",
            });
            await loadData();
        } catch (e) {
            setError(
                e instanceof Error
                    ? e.message
                    : "Failed to reset live equity baseline",
            );
        } finally {
            setResettingLiveBaseline(false);
        }
    };

    useEffect(() => {
        loadData();
        const interval = setInterval(loadData, 60000); // 60s — analytics doesn't need 15s refresh
        return () => clearInterval(interval);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [days]);

    useEffect(() => {
        const loadVolatility = () => {
            apiFetch("/api/stats/volatility-state")
                .then((r) => r.json())
                .then((data: VolatilityState) => setVolatilityState(data))
                .catch(() => {/* silently ignore — not critical */});
        };
        loadVolatility();
        const interval = setInterval(loadVolatility, 20000); // 20s polling
        return () => clearInterval(interval);
    }, []);

    const rowsInWindow = useMemo(() => {
        return rawRows.filter((row) => {
            if (!inLastDays(row.closed_at_utc, days)) return false;
            if (regimeFilter === "weekday" && isWeekendUtc(row.closed_at_utc)) {
                return false;
            }
            if (
                regimeFilter === "weekend" &&
                !isWeekendUtc(row.closed_at_utc)
            ) {
                return false;
            }
            return true;
        });
    }, [rawRows, days, regimeFilter]);

    const signalRowsInWindow = useMemo(() => {
        return signalRows.filter((row) => {
            if (!inLastDays(row.detected_at_utc, days)) return false;
            if (
                regimeFilter === "weekday" &&
                isWeekendUtc(row.detected_at_utc)
            ) {
                return false;
            }
            if (
                regimeFilter === "weekend" &&
                !isWeekendUtc(row.detected_at_utc)
            ) {
                return false;
            }
            return true;
        });
    }, [signalRows, days, regimeFilter]);

    const blockedRowsInWindow = useMemo(() => {
        return blockedRows.filter((row) => {
            if (!inLastDays(row.detected_at_utc, days)) return false;
            if (
                regimeFilter === "weekday" &&
                isWeekendUtc(row.detected_at_utc)
            ) {
                return false;
            }
            if (
                regimeFilter === "weekend" &&
                !isWeekendUtc(row.detected_at_utc)
            ) {
                return false;
            }
            return true;
        });
    }, [blockedRows, days, regimeFilter]);

    const filteredRows = useMemo(() => {
        if (ticker === "ALL") return rowsInWindow;
        return rowsInWindow.filter(
            (row) => String(row.ticker || "").toUpperCase() === ticker,
        );
    }, [rowsInWindow, ticker]);

    const filteredSignalRows = useMemo(() => {
        if (ticker === "ALL") return signalRowsInWindow;
        return signalRowsInWindow.filter(
            (row) => String(row.ticker || "").toUpperCase() === ticker,
        );
    }, [signalRowsInWindow, ticker]);

    const filteredBlockedRows = useMemo(() => {
        if (ticker === "ALL") return blockedRowsInWindow;
        return blockedRowsInWindow.filter(
            (row) => String(row.ticker || "").toUpperCase() === ticker,
        );
    }, [blockedRowsInWindow, ticker]);

    const paperRowsInWindow = useMemo(() => {
        return paperRows.filter((row) => {
            if (!inLastDays(row.decision_time, days)) return false;
            if (regimeFilter === "weekday" && isWeekendUtc(row.decision_time)) {
                return false;
            }
            if (
                regimeFilter === "weekend" &&
                !isWeekendUtc(row.decision_time)
            ) {
                return false;
            }
            return true;
        });
    }, [paperRows, days, regimeFilter]);

    const filteredPaperRows = useMemo(() => {
        if (ticker === "ALL") return paperRowsInWindow;
        return paperRowsInWindow.filter(
            (row) => String(row.ticker || "").toUpperCase() === ticker,
        );
    }, [paperRowsInWindow, ticker]);

    const botOrderRowsInWindow = useMemo(() => {
        return botOrderRows.filter((row) => {
            if (!inLastDays(row.placed_at_utc, days)) return false;
            if (regimeFilter === "weekday" && isWeekendUtc(row.placed_at_utc)) {
                return false;
            }
            if (
                regimeFilter === "weekend" &&
                !isWeekendUtc(row.placed_at_utc)
            ) {
                return false;
            }
            return true;
        });
    }, [botOrderRows, days, regimeFilter]);

    const filteredBotOrderRows = useMemo(() => {
        if (ticker === "ALL") return botOrderRowsInWindow;
        return botOrderRowsInWindow.filter(
            (row) => String(row.ticker || "").toUpperCase() === ticker,
        );
    }, [botOrderRowsInWindow, ticker]);

    const chartRows = useMemo(() => {
        if (chartScope === "all") return rowsInWindow;
        return filteredRows;
    }, [chartScope, rowsInWindow, filteredRows]);

    const chartSignalRows = useMemo(() => {
        if (chartScope === "all") return signalRowsInWindow;
        return filteredSignalRows;
    }, [chartScope, signalRowsInWindow, filteredSignalRows]);

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
            }))
            .sort(
                (a, b) =>
                    b.signals - a.signals || a.ticker.localeCompare(b.ticker),
            );
    }, [filteredRows]);

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
        for (const row of filteredRows) {
            const regime = isWeekendUtc(row.closed_at_utc)
                ? "weekend"
                : "weekday";
            acc[regime].n += 1;
            acc[regime].wins += asNumber(row.won);
            acc[regime].pnl += asNumber(row.pnl_usd);
        }
        return acc;
    }, [filteredRows]);

    const signalProbById = useMemo(() => {
        const map = new Map<string, number>();
        for (const row of chartSignalRows) {
            const prob = asNumber(row.quant_prob_side);
            if (prob >= 0 && prob <= 1) {
                map.set(row.signal_id, prob);
            }
        }
        return map;
    }, [chartSignalRows]);

    const calibrationBuckets = useMemo(() => {
        const buckets = Array.from({ length: 10 }, (_, idx) => ({
            key: `bucket-${idx}`,
            rangeLabel: calibrationRangeLabel(idx),
            n: 0,
            wins: 0,
            probSum: 0,
        }));
        for (const row of chartRows) {
            const prob = signalProbById.get(row.signal_id);
            if (typeof prob !== "number" || !Number.isFinite(prob)) continue;
            const idx = Math.min(9, Math.floor(prob * 10));
            const bucket = buckets[idx];
            bucket.n += 1;
            bucket.wins += asNumber(row.won);
            bucket.probSum += prob;
        }
        return buckets
            .filter((b) => b.n > 0)
            .map(
                (b): CalibrationBucket => ({
                    key: b.key,
                    rangeLabel: b.rangeLabel,
                    n: b.n,
                    expectedPct: (b.probSum / b.n) * 100,
                    actualPct: (b.wins / b.n) * 100,
                }),
            );
    }, [chartRows, signalProbById]);

    const calibrationMae = useMemo(() => {
        if (!calibrationBuckets.length) return 0;
        const weightedError = calibrationBuckets.reduce(
            (acc, b) => acc + Math.abs(b.actualPct - b.expectedPct) * b.n,
            0,
        );
        const totalN = calibrationBuckets.reduce((acc, b) => acc + b.n, 0);
        return totalN > 0 ? weightedError / totalN : 0;
    }, [calibrationBuckets]);

    const edgeBuckets = useMemo(() => {
        const rows: EdgeBucket[] = EDGE_BUCKETS.map((b) => ({
            key: b.key,
            label: b.label,
            n: 0,
            wins: 0,
            pnl: 0,
        }));
        for (const row of chartRows) {
            const edge = asNumber(row.edge_pct_at_signal);
            const idx = EDGE_BUCKETS.findIndex(
                (b) => edge >= b.min && edge < b.max,
            );
            if (idx < 0) continue;
            rows[idx].n += 1;
            rows[idx].wins += asNumber(row.won);
            rows[idx].pnl += asNumber(row.pnl_usd);
        }
        return rows;
    }, [chartRows]);

    const paperMetrics = useMemo(() => {
        const resolvedRows = filteredPaperRows.filter(
            (r) => r.status === "resolved",
        );
        const pending = filteredPaperRows.length - resolvedRows.length;
        const wins = resolvedRows.filter(
            (r) =>
                String(r.event_outcome_real).toLowerCase() ===
                String(r.side_taken).toLowerCase(),
        ).length;
        const losses = Math.max(0, resolvedRows.length - wins);
        const winRate =
            resolvedRows.length > 0 ? (wins / resolvedRows.length) * 100 : 0;
        const totalPnl = resolvedRows.reduce(
            (acc, r) => acc + asNumber(r.pnl_simulated),
            0,
        );
        const avgPnlPerResolved =
            resolvedRows.length > 0 ? totalPnl / resolvedRows.length : 0;
        const avgQe = filteredPaperRows.length
            ? filteredPaperRows.reduce(
                  (acc, r) => acc + asNumber(r.QuantumEdge),
                  0,
              ) / filteredPaperRows.length
            : 0;
        return {
            total: filteredPaperRows.length,
            resolved: resolvedRows.length,
            pending,
            wins,
            losses,
            winRate,
            totalPnl,
            avgPnlPerResolved,
            avgQePct: avgQe * 100,
        };
    }, [filteredPaperRows]);

    const paperTradingCurve = useMemo<TradingEquityPoint[]>(() => {
        const baseEquity = asNumber(
            runtimeSettings.kelly_paper_bankroll_usd ?? 1000,
        );
        const rows = filteredPaperRows
            .slice()
            .sort(
                (a, b) =>
                    new Date(a.decision_time).getTime() -
                    new Date(b.decision_time).getTime(),
            );

        let equity = baseEquity;
        let lastTsMs = Number.NEGATIVE_INFINITY;
        return rows.map((row) => {
            if (String(row.status).toLowerCase() === "resolved") {
                equity += asNumber(row.pnl_simulated);
            }
            let tsMs = new Date(row.decision_time).getTime();
            if (!Number.isFinite(tsMs)) tsMs = Date.now();
            if (tsMs <= lastTsMs) tsMs = lastTsMs + 1;
            lastTsMs = tsMs;
            return { ts: new Date(tsMs).toISOString(), equity };
        });
    }, [filteredPaperRows, runtimeSettings.kelly_paper_bankroll_usd]);

    const paperTradingCurveMetrics = useMemo(() => {
        const first = paperTradingCurve[0];
        const last = paperTradingCurve[paperTradingCurve.length - 1];
        return {
            points: paperTradingCurve.length,
            startEquity:
                first?.equity ??
                asNumber(runtimeSettings.kelly_paper_bankroll_usd ?? 1000),
            finalEquity:
                last?.equity ??
                asNumber(runtimeSettings.kelly_paper_bankroll_usd ?? 1000),
        };
    }, [paperTradingCurve, runtimeSettings.kelly_paper_bankroll_usd]);

    const liveTradingCurve = useMemo<TradingEquityPoint[]>(() => {
        const baseEquity = asNumber(
            runtimeSettings.live_equity_start_bankroll_usd &&
                runtimeSettings.live_equity_start_bankroll_usd > 0
                ? runtimeSettings.live_equity_start_bankroll_usd
                : (runtimeSettings.kelly_live_bankroll_usd ?? 100),
        );
        const startAt =
            runtimeSettings.live_equity_start_at_utc
                ? new Date(runtimeSettings.live_equity_start_at_utc).getTime()
                : null;

        const placedOrders = filteredBotOrderRows
            .filter((r) => {
                if (String(r.status).toLowerCase() !== "placed") return false;
                if (
                    String(r.resolution_status || "").toLowerCase() !==
                    "resolved"
                )
                    return false;
                if (r.won === undefined || r.won === "") return false;
                if (startAt !== null) {
                    const ts = new Date(r.placed_at_utc).getTime();
                    if (ts < startAt) return false;
                }
                return true;
            })
            .slice()
            .sort(
                (a, b) =>
                    new Date(a.placed_at_utc).getTime() -
                    new Date(b.placed_at_utc).getTime(),
            );

        let equity = baseEquity;
        let lastTsMs = Number.NEGATIVE_INFINITY;
        const points: TradingEquityPoint[] = [];
        for (const row of placedOrders) {
            const won = String(row.won) === "1";
            const stake =
                asNumber(row.filled_notional_usd_real) > 0
                    ? asNumber(row.filled_notional_usd_real)
                    : asNumber(row.notional_usd);
            const q =
                asNumber(row.fill_price_real) > 0
                    ? asNumber(row.fill_price_real)
                    : asNumber(row.price);
            if (stake <= 0 || q <= 0) continue;
            const pnl = won ? stake * (1 / q - 1) : -stake;
            equity += pnl;

            let tsMs = new Date(row.placed_at_utc).getTime();
            if (!Number.isFinite(tsMs)) tsMs = Date.now();
            if (tsMs <= lastTsMs) tsMs = lastTsMs + 1;
            lastTsMs = tsMs;
            points.push({ ts: new Date(tsMs).toISOString(), equity });
        }
        return points;
    }, [
        filteredBotOrderRows,
        runtimeSettings.live_equity_start_bankroll_usd,
        runtimeSettings.kelly_live_bankroll_usd,
        runtimeSettings.live_equity_start_at_utc,
    ]);

    const liveTradingCurveMetrics = useMemo(() => {
        const first = liveTradingCurve[0];
        const last = liveTradingCurve[liveTradingCurve.length - 1];
        const configuredStart = asNumber(
            runtimeSettings.live_equity_start_bankroll_usd &&
                runtimeSettings.live_equity_start_bankroll_usd > 0
                ? runtimeSettings.live_equity_start_bankroll_usd
                : (runtimeSettings.kelly_live_bankroll_usd ?? 100),
        );
        return {
            points: liveTradingCurve.length,
            startEquity: first?.equity ?? configuredStart,
            finalEquity: last?.equity ?? configuredStart,
        };
    }, [
        liveTradingCurve,
        runtimeSettings.live_equity_start_bankroll_usd,
        runtimeSettings.kelly_live_bankroll_usd,
    ]);

    const botOrderMetrics = useMemo(() => {
        const total = filteredBotOrderRows.length;
        const placed = filteredBotOrderRows.filter(
            (r) => String(r.status).toLowerCase() === "placed",
        ).length;
        const failed = filteredBotOrderRows.filter(
            (r) =>
                String(r.status).toLowerCase() === "failed" ||
                String(r.status).toLowerCase() === "no_fill",
        ).length;
        const resolvedRows = filteredBotOrderRows.filter(
            (r) =>
                String(r.resolution_status || "").toLowerCase() === "resolved",
        );
        const resolved = resolvedRows.length;
        const wins = resolvedRows.filter(
            (r) => String(r.won || "") === "1",
        ).length;
        const losses = Math.max(0, resolved - wins);
        const winRate = resolved > 0 ? (wins / resolved) * 100 : 0;
        const totalPnlSim = resolvedRows.reduce(
            (acc, r) => acc + asNumber(r.pnl_simulated),
            0,
        );
        const avgPnlPerResolved = resolved > 0 ? totalPnlSim / resolved : 0;
        const withFill = filteredBotOrderRows.filter(
            (r) => asNumber(r.fill_price_real) > 0,
        ).length;
        const avgEdgeSend = total
            ? filteredBotOrderRows.reduce(
                  (acc, r) => acc + asNumber(r.edge_pct),
                  0,
              ) / total
            : 0;
        const avgEdgeFill =
            withFill > 0
                ? filteredBotOrderRows.reduce(
                      (acc, r) => acc + asNumber(r.edge_at_fill_pct),
                      0,
                  ) / withFill
                : 0;
        const placedRows = filteredBotOrderRows.filter(
            (r) => String(r.status).toLowerCase() === "placed",
        );
        const avgStake =
            placedRows.length > 0
                ? placedRows.reduce((acc, r) => {
                      const real = asNumber(r.filled_notional_usd_real);
                      return acc + (real > 0 ? real : asNumber(r.notional_usd));
                  }, 0) / placedRows.length
                : 0;
        const latencyRows = filteredBotOrderRows.filter(
            (r) => r.fill_latency_ms !== undefined && r.fill_latency_ms !== "" && asNumber(r.fill_latency_ms) > 0,
        );
        const avgLatency =
            latencyRows.length > 0
                ? latencyRows.reduce((acc, r) => acc + asNumber(r.fill_latency_ms), 0) / latencyRows.length
                : 0;
        // --- execution observability (v1.1-a) ---
        const slippageBpsRows = filteredBotOrderRows.filter(
            (r) => r.realized_slippage_bps !== undefined && r.realized_slippage_bps !== "",
        );
        const avgSlippageBps =
            slippageBpsRows.length > 0
                ? slippageBpsRows.reduce((acc, r) => acc + asNumber(r.realized_slippage_bps), 0) / slippageBpsRows.length
                : null;
        const isbpsRows = filteredBotOrderRows.filter(
            (r) => r.implementation_shortfall_bps !== undefined && r.implementation_shortfall_bps !== "",
        );
        const avgISBps =
            isbpsRows.length > 0
                ? isbpsRows.reduce((acc, r) => acc + asNumber(r.implementation_shortfall_bps), 0) / isbpsRows.length
                : null;
        const isUsdRows = filteredBotOrderRows.filter(
            (r) => r.implementation_shortfall_usd !== undefined && r.implementation_shortfall_usd !== "",
        );
        const totalISUsd =
            isUsdRows.length > 0
                ? isUsdRows.reduce((acc, r) => acc + asNumber(r.implementation_shortfall_usd), 0)
                : null;
        return {
            total,
            placed,
            failed,
            resolved,
            wins,
            losses,
            winRate,
            totalPnlSim,
            avgPnlPerResolved,
            withFill,
            avgEdgeSend,
            avgEdgeFill,
            avgStake,
            avgLatency,
            avgSlippageBps,
            avgISBps,
            totalISUsd,
            isUsdCount: isUsdRows.length,
        };
    }, [filteredBotOrderRows]);

    return (
        <>
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
                <label>
                    Charts
                    <select
                        value={chartScope}
                        onChange={(e) =>
                            setChartScope(e.target.value as ChartScope)
                        }
                    >
                        {CHART_SCOPE_OPTIONS.map((value) => (
                            <option key={value.value} value={value.value}>
                                {value.label}
                            </option>
                        ))}
                    </select>
                </label>
                <button
                    onClick={() => {
                        void loadData();
                    }}
                    disabled={loading}
                >
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

            {volatilityState && (
                <section className="analytics-volatility-card">
                    <div className="volatility-header">
                        <span className="volatility-title">Volatility Monitor</span>
                        <span className={`volatility-mode-badge volatility-mode-${volatilityState.bot_mode.toLowerCase()}`}>
                            {volatilityState.bot_mode}
                        </span>
                        {!volatilityState.execution_enabled && (
                            <span className="volatility-mode-badge volatility-mode-frz">PAUSED</span>
                        )}
                        {volatilityState.pending_alert && (
                            <span className="volatility-alert-badge">
                                ⚠ ALERT: {volatilityState.pending_alert.ticker}
                            </span>
                        )}
                        <span className="volatility-window-label">
                            window {Math.round((volatilityState.config?.window_seconds ?? 3600) / 60)}min
                            · trigger {volatilityState.config?.flip_trigger ?? 3} flips
                        </span>
                    </div>

                    {volatilityState.pending_alert && (
                        <div className="volatility-alert-banner">
                            <strong>{volatilityState.pending_alert.ticker}</strong>
                            {" — "}
                            {volatilityState.pending_alert.flips} direction flips
                            ({volatilityState.pending_alert.signals_in_window} large signals):
                            {" "}
                            <span className="volatility-direction-history">
                                {volatilityState.pending_alert.direction_history.join(" → ")}
                            </span>
                        </div>
                    )}

                    <div className="volatility-tickers">
                        {Object.keys(volatilityState.config?.thresholds ?? { BTC: 30, ETH: 2 }).map((tk) => {
                            const stat = volatilityState.ticker_stats?.[tk];
                            const isAlert = stat?.alert_active ?? false;
                            return (
                                <div key={tk} className={`volatility-ticker-card ${isAlert ? "volatility-ticker-alert" : ""}`}>
                                    <div className="volatility-ticker-name">{tk}</div>
                                    <div className="volatility-ticker-row">
                                        <span className="volatility-ticker-label">Signals</span>
                                        <span className="volatility-ticker-value">{stat?.signals_in_window ?? 0}</span>
                                    </div>
                                    <div className="volatility-ticker-row">
                                        <span className="volatility-ticker-label">Flips</span>
                                        <span className={`volatility-ticker-value ${isAlert ? "volatility-value-alert" : ""}`}>
                                            {stat?.flips ?? 0}
                                        </span>
                                    </div>
                                    <div className={`volatility-ticker-status ${isAlert ? "volatility-status-high" : "volatility-status-normal"}`}>
                                        {isAlert ? "HIGH CHOP" : "Normal"}
                                    </div>
                                </div>
                            );
                        })}
                        {Object.keys(volatilityState.ticker_stats ?? {})
                            .filter((tk) => !(tk in (volatilityState.config?.thresholds ?? {})))
                            .map((tk) => {
                                const stat = volatilityState.ticker_stats[tk];
                                const isAlert = stat.alert_active;
                                return (
                                    <div key={tk} className={`volatility-ticker-card ${isAlert ? "volatility-ticker-alert" : ""}`}>
                                        <div className="volatility-ticker-name">{tk}</div>
                                        <div className="volatility-ticker-row">
                                            <span className="volatility-ticker-label">Signals</span>
                                            <span className="volatility-ticker-value">{stat.signals_in_window}</span>
                                        </div>
                                        <div className="volatility-ticker-row">
                                            <span className="volatility-ticker-label">Flips</span>
                                            <span className={`volatility-ticker-value ${isAlert ? "volatility-value-alert" : ""}`}>
                                                {stat.flips}
                                            </span>
                                        </div>
                                        <div className={`volatility-ticker-status ${isAlert ? "volatility-status-high" : "volatility-status-normal"}`}>
                                            {isAlert ? "HIGH CHOP" : "Normal"}
                                        </div>
                                    </div>
                                );
                            })}
                    </div>
                </section>
            )}

            <section className="analytics-charts-grid">
                <article className="analytics-panel">
                    <h3>Calibration (Predicted vs Real)</h3>
                    <div className="analytics-chart-help">
                        <div>How to read</div>
                        <ul>
                            <li>
                                If real win rate is near predicted, the model is
                                calibrated.
                            </li>
                            <li>
                                Large gap means probabilities are
                                over/under-estimated.
                            </li>
                            <li>Bins with very low n are weak evidence.</li>
                        </ul>
                    </div>
                    <div className="analytics-mini-kpis">
                        <span>Bins: {calibrationBuckets.length}</span>
                        <span>
                            Weighted MAE: {calibrationMae.toFixed(2)} pts
                        </span>
                    </div>
                    <div className="analytics-calibration-list">
                        {calibrationBuckets.length === 0 && (
                            <div className="analytics-empty">
                                No data with `quant_prob_side` in selected
                                window.
                            </div>
                        )}
                        {calibrationBuckets.map((bucket) => (
                            <div className="cal-row" key={bucket.key}>
                                <div className="cal-meta">
                                    <span>{bucket.rangeLabel}</span>
                                    <span>n={bucket.n}</span>
                                </div>
                                <div className="cal-bars">
                                    <div
                                        className="cal-bar cal-bar-expected"
                                        style={{
                                            width: `${bucket.expectedPct}%`,
                                        }}
                                    />
                                    <div
                                        className="cal-bar cal-bar-actual"
                                        style={{
                                            width: `${bucket.actualPct}%`,
                                        }}
                                    />
                                </div>
                                <div className="cal-values">
                                    <span>
                                        E {bucket.expectedPct.toFixed(1)}%
                                    </span>
                                    <span>
                                        A {bucket.actualPct.toFixed(1)}%
                                    </span>
                                </div>
                            </div>
                        ))}
                    </div>
                </article>


                {runtimeSettings.bot_paper_mode && <article className="analytics-panel">
                    <h3>Paper Trading Equity Curve</h3>
                    <div className="analytics-mini-kpis">
                        <span>Points: {paperTradingCurveMetrics.points}</span>
                        <span>
                            Start: $
                            {paperTradingCurveMetrics.startEquity.toFixed(2)}
                        </span>
                        <span>
                            Final: $
                            {paperTradingCurveMetrics.finalEquity.toFixed(2)}
                        </span>
                    </div>
                    <TradingEquityCurveChart
                        points={paperTradingCurve}
                        color="#3fb950"
                    />
                </article>}

                <article className="analytics-panel analytics-panel-wide">
                    <h3>Live Trading Equity Curve</h3>
                    <div className="analytics-mini-kpis">
                        <span>
                            Resolved placed orders:{" "}
                            {liveTradingCurveMetrics.points}
                        </span>
                        <span>
                            Start: $
                            {liveTradingCurveMetrics.startEquity.toFixed(2)}
                        </span>
                        <span>
                            Final: $
                            {liveTradingCurveMetrics.finalEquity.toFixed(2)}
                        </span>
                        <span>
                            Baseline at:{" "}
                            {runtimeSettings.live_equity_start_at_utc
                                ? fmtPst(runtimeSettings.live_equity_start_at_utc)
                                : "not set"}
                        </span>
                    </div>
                    <button
                        className="analytics-danger-btn"
                        onClick={handleResetLiveBaseline}
                        disabled={resettingLiveBaseline}
                    >
                        {resettingLiveBaseline
                            ? "Resetting..."
                            : "Reset Live Baseline"}
                    </button>
                    <TradingEquityCurveChart
                        points={liveTradingCurve}
                        color="#58a6ff"
                        drawdownThresholdPnl={
                            runtimeSettings.bot_drawdown_enabled &&
                            (runtimeSettings.bot_drawdown_stop_pct ?? 0) > 0
                                ? -(
                                      asNumber(
                                          runtimeSettings.live_equity_start_bankroll_usd &&
                                              runtimeSettings.live_equity_start_bankroll_usd > 0
                                              ? runtimeSettings.live_equity_start_bankroll_usd
                                              : (runtimeSettings.kelly_live_bankroll_usd ?? 100),
                                      ) *
                                      (runtimeSettings.bot_drawdown_stop_pct ?? 50) /
                                      100
                                  )
                                : undefined
                        }
                    />
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

            {runtimeSettings.bot_paper_mode && <section className="analytics-panel">
                <h3>Paper Decisions (Raw)</h3>
                <div className="analytics-chart-help">
                    <div>How to extract</div>
                    <ul>
                        <li>
                            API: `GET
                            /api/stats/paper/raw?limit=5000&ticker=BTC`
                        </li>
                        <li>CSV file: `backtest_output/paper_trades.csv`</li>
                        <li>
                            `PnL Sim` is raw simulated PnL; `PnL Adj`
                            discounts spread + slippage buffer.
                        </li>
                        <li>
                            `WON` and `PnL` are populated after event close
                            (`status=resolved`); before that they show
                            `pending` / `n/a`.
                        </li>
                    </ul>
                </div>
                <div className="analytics-mini-kpis">
                    <span>Total: {paperMetrics.total}</span>
                    <span>Resolved: {paperMetrics.resolved}</span>
                    <span>Pending: {paperMetrics.pending}</span>
                    <span>Wins: {paperMetrics.wins}</span>
                    <span>Losses: {paperMetrics.losses}</span>
                    <span>
                        Win Rate: {paperMetrics.winRate.toFixed(2)}%
                    </span>
                    <span>
                        Total PnL Sim: ${paperMetrics.totalPnl.toFixed(2)}
                    </span>
                    <span>
                        Avg PnL/Resolved: $
                        {paperMetrics.avgPnlPerResolved.toFixed(2)}
                    </span>
                    <span>
                        Avg QE: {paperMetrics.avgQePct.toFixed(2)}%
                    </span>
                </div>
                <table className="analytics-table">
                    <thead>
                        <tr>
                            <th title="Timestamp de la decisión en UTC">Decision (UTC)</th>
                            <th title="Número de entrada del ladder (1=primera, 2=segunda, 3=tercera)">#</th>
                            <th title="Activo subyacente (ej. BTC, ETH, SOL)">Ticker</th>
                            <th title="Duración del evento (5m, 15m, 1h, 4h)">TF</th>
                            <th title="Sub-bloque temporal dentro del evento (en 5m/10s hay 30 slots)">Slot</th>
                            <th title="Bin de diferencia de precio vs PTB usado por el modelo quant">Range</th>
                            <th title="Probabilidad estimada por el modelo de que el evento cierre UP">Prob Up</th>
                            <th title="Probabilidad estimada por el modelo de que el evento cierre DOWN (= 1 − Prob Up)">Prob Down</th>
                            <th title="Probabilidad implícita de mercado, aproximada por el precio del contrato">Market Prob</th>
                            <th title="Monto en USD asignado a la orden (notional)">Stake $</th>
                            <th title="Cantidad de contratos/participaciones adquiridas">Shares</th>
                            <th title="Quantum Edge: ventaja del modelo frente al mercado en el momento de la decisión">QE</th>
                            <th title="Dirección tomada en la orden (UP o DOWN)">Side</th>
                            <th title="Diferencia entre precio actual del subyacente y Price To Beat (PTB)">Diff vs PTB</th>
                            <th title="Spread relativo en porcentaje: (ask − bid) / mid × 100">Spread %</th>
                            <th title="Resultado binario: 1 si el evento resolvió en el lado tomado, 0 si no">WON</th>
                            <th title="PnL simulado bruto (sin ajuste de fricción)">PnL Sim</th>
                            <th title="PnL simulado ajustado por fricción estimada (spread, slippage)">PnL Adj</th>
                            <th title="Estado de la decisión: pending, resolved">Status</th>
                            <th title="Identificador del evento de Polymarket">Event</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filteredPaperRows
                            .slice()
                            .reverse()
                            .slice(0, 50)
                            .map((row) => {
                                const probUp = asNumber(row.prob_up);
                                const side = String(
                                    row.side_taken,
                                ).toLowerCase();
                                const probSide =
                                    side === "down" ? 1 - probUp : probUp;
                                const outcome = String(
                                    row.event_outcome_real || "",
                                ).toLowerCase();
                                const won =
                                    row.status === "resolved" &&
                                    outcome !== "" &&
                                    outcome === side;
                                const spreadPct = asNumber(
                                    row.spread_pct_at_decision,
                                );
                                const pnlAdj = asNumber(row.pnl_sim_adjusted);
                                return (
                                    <tr key={row.decision_id}>
                                        <td>
                                            {fmtPst(row.decision_time)}
                                        </td>
                                        <td style={{ textAlign: "center", fontWeight: 600 }}>
                                            {row.ladder_entry || 1}
                                        </td>
                                        <td>{row.ticker}</td>
                                        <td>{row.timeframe || "5m"}</td>
                                        <td>{row.slot || "n/a"}</td>
                                        <td>{row.range || "n/a"}</td>
                                        <td>{probUp.toFixed(4)}</td>
                                        <td>{(1 - probUp).toFixed(4)}</td>
                                        <td>
                                            {asNumber(
                                                row.marketProb_at_decision,
                                            ).toFixed(4)}
                                        </td>
                                        <td>
                                            $
                                            {asNumber(row.stake_usd).toFixed(2)}
                                        </td>
                                        <td>
                                            {asNumber(row.shares_simulated) > 0
                                                ? asNumber(
                                                      row.shares_simulated,
                                                  ).toFixed(4)
                                                : "n/a"}
                                        </td>
                                        <td>
                                            {(
                                                asNumber(row.QuantumEdge) * 100
                                            ).toFixed(2)}
                                            %
                                        </td>
                                        <td>{side.toUpperCase()}</td>
                                        <td>
                                            {row.diff_vs_ptb_at_decision !==
                                                undefined &&
                                            row.diff_vs_ptb_at_decision !== ""
                                                ? asNumber(
                                                      row.diff_vs_ptb_at_decision,
                                                  ).toFixed(2)
                                                : "n/a"}
                                        </td>
                                        <td>
                                            {spreadPct > 0
                                                ? `${spreadPct.toFixed(2)}%`
                                                : "n/a"}
                                        </td>
                                        <td>
                                            {row.status !== "resolved" ? (
                                                <span className="outcome-pending">
                                                    pending
                                                </span>
                                            ) : won ? (
                                                <span className="outcome-won">
                                                    ✓
                                                </span>
                                            ) : (
                                                <span className="outcome-lost">
                                                    ✗
                                                </span>
                                            )}
                                        </td>
                                        <td>
                                            $
                                            {asNumber(
                                                row.pnl_simulated,
                                            ).toFixed(2)}
                                        </td>
                                        <td>
                                            {pnlAdj !== 0
                                                ? `$${pnlAdj.toFixed(2)}`
                                                : "n/a"}
                                        </td>
                                        <td>{row.status}</td>
                                        <td
                                            style={{
                                                fontSize: "0.7em",
                                                color: "var(--text-muted)",
                                            }}
                                        >
                                            {row.event_id
                                                ? row.event_id.slice(0, 8) +
                                                  "…"
                                                : "n/a"}
                                        </td>
                                    </tr>
                                );
                            })}
                    </tbody>
                </table>
            </section>}

            <section className="analytics-panel">
                <h3>Bot Orders (Execution Log)</h3>
                <div className="analytics-chart-help">
                    <div>How to read</div>
                    <ul>
                        <li>
                            Source: `backtest_output/bot_orders_YYYY-MM-DD.csv`.
                        </li>
                        <li>
                            Export CSV: `GET
                            /api/stats/bot-orders/export.csv?days=7&ticker=BTC`.
                        </li>
                        <li>
                            `edge_pct` is edge at send; `edge_at_fill_pct` is
                            edge versus actual fill price when available.
                        </li>
                        <li>
                            `WON` and `PnL` are populated after event close
                            (`resolution_status=resolved`); before that they
                            show `pending` / `n/a`.
                        </li>
                    </ul>
                </div>
                <div className="analytics-mini-kpis">
                    <span>Total rows: {botOrderMetrics.total}</span>
                    <span>Placed: {botOrderMetrics.placed}</span>
                    <span>Failed: {botOrderMetrics.failed}</span>
                    <span>Resolved: {botOrderMetrics.resolved}</span>
                    <span>Wins: {botOrderMetrics.wins}</span>
                    <span>Losses: {botOrderMetrics.losses}</span>
                    <span>Win Rate: {botOrderMetrics.winRate.toFixed(2)}%</span>
                    <span>
                        Total PnL Sim: ${botOrderMetrics.totalPnlSim.toFixed(2)}
                    </span>
                    <span>
                        Avg PnL/Resolved: $
                        {botOrderMetrics.avgPnlPerResolved.toFixed(2)}
                    </span>
                    <span>With fill price: {botOrderMetrics.withFill}</span>
                    <span>
                        Avg Edge@Send: {botOrderMetrics.avgEdgeSend.toFixed(2)}%
                    </span>
                    <span>
                        Avg Edge@Fill: {botOrderMetrics.avgEdgeFill.toFixed(2)}%
                    </span>
                    <span>
                        Avg Stake: ${botOrderMetrics.avgStake.toFixed(2)}
                    </span>
                    {botOrderMetrics.avgLatency > 0 && (
                        <span>
                            Avg Latency: {botOrderMetrics.avgLatency.toFixed(0)} ms
                        </span>
                    )}
                </div>
                {/* Execution Quality panel (v1.1-a) — only shown once data is available */}
                {botOrderMetrics.isUsdCount > 0 && (
                    <div className="analytics-mini-kpis" style={{ marginTop: "0.5rem", borderTop: "1px solid var(--border)", paddingTop: "0.5rem" }}>
                        <strong style={{ marginRight: "0.5rem" }}>Execution Quality:</strong>
                        {botOrderMetrics.avgSlippageBps !== null && (
                            <span title="Slippage realizado vs ask_price en bps. Positivo = pagaste más que el ask.">
                                Avg Slippage:{" "}
                                <span style={{ color: (botOrderMetrics.avgSlippageBps ?? 0) > 10 ? "var(--red)" : "inherit" }}>
                                    {(botOrderMetrics.avgSlippageBps ?? 0).toFixed(1)} bps
                                </span>
                            </span>
                        )}
                        {botOrderMetrics.avgISBps !== null && (
                            <span title="Implementation Shortfall vs mid_at_send en bps. Mide el costo real de ejecución desde el mid.">
                                Avg IS:{" "}
                                <span style={{ color: (botOrderMetrics.avgISBps ?? 0) > 50 ? "var(--red)" : "inherit" }}>
                                    {(botOrderMetrics.avgISBps ?? 0).toFixed(1)} bps
                                </span>
                            </span>
                        )}
                        {botOrderMetrics.totalISUsd !== null && (
                            <span title="Implementation Shortfall acumulado en USD. Cuánto dejaste de ganar por no ejecutar al mid.">
                                Total IS cost:{" "}
                                <span style={{ color: (botOrderMetrics.totalISUsd ?? 0) > 0 ? "var(--red)" : "var(--green)" }}>
                                    ${(botOrderMetrics.totalISUsd ?? 0).toFixed(2)}
                                </span>
                            </span>
                        )}
                        <span style={{ color: "var(--text-muted)", fontSize: "0.85em" }}>
                            n={botOrderMetrics.isUsdCount}
                        </span>
                    </div>
                )}
                <table className="analytics-table">
                    <thead>
                        <tr>
                            <th title="Timestamp de la orden en UTC">Decision (UTC)</th>
                            <th title="Número de entrada del ladder (1=primera, 2=segunda, 3=tercera)">#</th>
                            <th title="Activo subyacente (ej. BTC, ETH, SOL)">Ticker</th>
                            <th title="Duración del evento (5m, 15m, 1h, 4h)">TF</th>
                            <th title="Sub-bloque temporal dentro del evento (en 5m/10s hay 30 slots)">Slot</th>
                            <th title="Bin de diferencia de precio vs PTB usado por el modelo quant">Range</th>
                            <th title="Probabilidad estimada por el modelo de que el evento cierre UP">Prob Up</th>
                            <th title="Probabilidad estimada por el modelo de que el evento cierre DOWN (= 1 − Prob Up)">Prob Down</th>
                            <th title="Probabilidad implícita de mercado, aproximada por el precio ask del contrato al momento del envío">Market Prob</th>
                            <th title="Dirección tomada en la orden (UP o DOWN)">Side</th>
                            <th title="Monto real en USD enviado al CLOB (notional)">Stake $ (real)</th>
                            <th title="Cantidad de contratos/participaciones adquiridas">Shares</th>
                            <th title="Quantum Edge: ventaja del modelo frente al mercado en el momento de envío">QE</th>
                            <th title="ΔEdge = QE Real (edge vs fill price) − QE (edge vs ask al envío). Negativo = la ejecución erosionó el edge; positivo = fill mejor de lo esperado">ΔEdge</th>
                            <th title="Diferencia entre precio actual del subyacente y Price To Beat (PTB)">Diff vs PTB</th>
                            <th title="Spread relativo en porcentaje: (ask − bid) / mid × 100">Spread %</th>
                            <th title="Latencia total desde envío de orden hasta recepción del fill del CLOB, en milisegundos">Latency (ms)</th>
                            <th title="Slippage en porcentaje: (fill_price − arrival_price) / arrival_price × 100. Positivo = peor ejecución">Slippage %</th>
                            <th title="Resultado binario: 1 si el evento resolvió en el lado tomado, 0 si no">WON</th>
                            <th title="PnL neto de la orden (usando precio real de fill)">PnL</th>
                            <th title="Estado de la orden: placed, no_fill, failed, resolved">Status</th>
                            <th title="Identificador del evento de Polymarket">Event</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filteredBotOrderRows
                            .slice()
                            .reverse()
                            .slice(0, 50)
                            .map((row, idx) => {
                                const side = String(
                                    row.side || "",
                                ).toLowerCase();
                                const probSide = asNumber(row.quant_prob);
                                const probUp =
                                    side === "down" ? 1 - probSide : probSide;
                                const outcome = String(
                                    row.event_outcome_real || "",
                                ).toLowerCase();
                                const won = String(row.won || "") === "1";
                                const statusLower = String(
                                    row.status,
                                ).toLowerCase();
                                const resolutionStatus =
                                    statusLower === "failed"
                                        ? "failed"
                                        : statusLower === "no_fill"
                                          ? "no_fill"
                                          : row.resolution_status || "pending";
                                return (
                                    <tr
                                        key={`${row.placed_at_utc}-${row.event_id}-${idx}`}
                                        className="analytics-table-row-clickable"
                                        onClick={() =>
                                            setDiagnosticTarget({
                                                kind: "bot_order",
                                                row: row as RawBotOrderFull,
                                            })
                                        }
                                    >
                                        <td>
                                            {fmtPst(row.placed_at_utc)}
                                        </td>
                                        <td style={{ textAlign: "center", fontWeight: 600 }}>
                                            {row.ladder_entry || 1}
                                        </td>
                                        <td>{row.ticker}</td>
                                        <td>{row.timeframe || "5m"}</td>
                                        <td>{row.slot || "n/a"}</td>
                                        <td>{row.range || "n/a"}</td>
                                        <td>
                                            {Number.isFinite(probUp)
                                                ? probUp.toFixed(4)
                                                : "n/a"}
                                        </td>
                                        <td>
                                            {Number.isFinite(probUp)
                                                ? (1 - probUp).toFixed(4)
                                                : "n/a"}
                                        </td>
                                        <td>
                                            {asNumber(row.price).toFixed(4)}
                                        </td>
                                        <td>
                                            {String(
                                                row.side || "",
                                            ).toUpperCase()}
                                        </td>
                                        <td>
                                            {asNumber(
                                                row.filled_notional_usd_real,
                                            ) > 0
                                                ? `$${asNumber(row.filled_notional_usd_real).toFixed(2)}`
                                                : `$${asNumber(row.notional_usd).toFixed(2)}~`}
                                        </td>
                                        <td>
                                            {asNumber(row.shares).toFixed(4)}
                                        </td>
                                        <td>
                                            {asNumber(row.edge_pct).toFixed(2)}%
                                        </td>
                                        <td>
                                            {row.edge_at_fill_pct !== undefined &&
                                            row.edge_at_fill_pct !== ""
                                                ? (() => {
                                                      const delta =
                                                          asNumber(
                                                              row.edge_at_fill_pct,
                                                          ) -
                                                          asNumber(row.edge_pct);
                                                      return (
                                                          <span
                                                              style={{
                                                                  color:
                                                                      delta >= 0
                                                                          ? "#4caf50"
                                                                          : "#f44336",
                                                              }}
                                                          >
                                                              {delta >= 0
                                                                  ? "+"
                                                                  : ""}
                                                              {delta.toFixed(2)}%
                                                          </span>
                                                      );
                                                  })()
                                                : "n/a"}
                                        </td>
                                        <td>
                                            {row.diff_vs_ptb_at_send !==
                                                undefined &&
                                            row.diff_vs_ptb_at_send !== ""
                                                ? asNumber(
                                                      row.diff_vs_ptb_at_send,
                                                  ).toFixed(2)
                                                : "n/a"}
                                        </td>
                                        <td>
                                            {row.spread_pct_at_send !==
                                                undefined &&
                                            row.spread_pct_at_send !== ""
                                                ? `${(
                                                      asNumber(
                                                          row.spread_pct_at_send,
                                                      ) * 100
                                                  ).toFixed(2)}%`
                                                : "n/a"}
                                        </td>
                                        <td>
                                            {row.fill_latency_ms !== undefined &&
                                            row.fill_latency_ms !== ""
                                                ? `${row.fill_latency_ms} ms`
                                                : "n/a"}
                                        </td>
                                        <td>
                                            {row.slippage_pct !== undefined &&
                                            row.slippage_pct !== ""
                                                ? `${asNumber(row.slippage_pct).toFixed(4)}%`
                                                : "n/a"}
                                        </td>
                                        <td>
                                            {outcome
                                                ? won
                                                    ? "YES"
                                                    : "NO"
                                                : "pending"}
                                        </td>
                                        <td>
                                            {row.pnl_simulated !== undefined &&
                                            row.pnl_simulated !== ""
                                                ? `$${asNumber(row.pnl_simulated).toFixed(2)}`
                                                : "n/a"}
                                        </td>
                                        <td
                                            title={
                                                (resolutionStatus === "failed" ||
                                                    resolutionStatus ===
                                                        "no_fill") &&
                                                row.fills_detail_json
                                                    ? row.fills_detail_json
                                                    : undefined
                                            }
                                        >
                                            {resolutionStatus}
                                            {(resolutionStatus === "failed" ||
                                                resolutionStatus ===
                                                    "no_fill") &&
                                                row.fills_detail_json && (
                                                    <span
                                                        style={{
                                                            fontSize: "0.7em",
                                                            opacity: 0.7,
                                                            marginLeft: 4,
                                                            display: "block",
                                                        }}
                                                    >
                                                        {row.fills_detail_json
                                                            .replace(
                                                                /^error:/,
                                                                "",
                                                            )
                                                            .slice(0, 80)}
                                                    </span>
                                                )}
                                        </td>
                                        <td className="analytics-event-id">
                                            {row.event_id}
                                        </td>
                                    </tr>
                                );
                            })}
                    </tbody>
                </table>
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
                                        {fmtPst(row.closed_at_utc)}
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
                                <tr
                                    key={row.blocked_id}
                                    className="analytics-table-row-clickable"
                                    onClick={() =>
                                        setDiagnosticTarget({
                                            kind: "blocked",
                                            row: row as RawBlockedFull,
                                        })
                                    }
                                >
                                    <td>
                                        {fmtPst(row.detected_at_utc)}
                                    </td>
                                    <td>{row.ticker}</td>
                                    <td>{row.timeframe_minutes}m</td>
                                    <td>{row.side.toUpperCase()}</td>
                                    <td>{row.blocked_reason}</td>
                                    <td>
                                        {asNumber(row.estimated_stake_usd) > 0
                                            ? `$${asNumber(
                                                  row.estimated_stake_usd,
                                              ).toFixed(2)}`
                                            : "N/A"}
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

        {diagnosticTarget && (
            <OrderDiagnosticModal
                target={diagnosticTarget}
                settings={runtimeSettings as unknown as Record<string, unknown>}
                onClose={() => setDiagnosticTarget(null)}
            />
        )}
        </>
    );
}
