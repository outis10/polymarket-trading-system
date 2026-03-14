import { useEffect } from "react";

// ── Types ──────────────────────────────────────────────────────────────────────

export interface RawBotOrderFull {
    placed_at_utc: string;
    event_id: string;
    ticker: string;
    slot?: string;
    range?: string;
    side: string;
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
    slippage_pct?: string;
    filled_notional_usd_real?: string;
    filled_shares_real?: string;
    fill_count?: string;
    fills_detail_json?: string;
    edge_at_fill_pct?: string;
    kelly_pct?: string;
    bankroll_usd?: string;
    percentile_at_signal?: string;
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
    fill_sim_levels_consumed?: string;
    fill_sim_slippage_vs_ask_bps?: string;
    fill_sim_slippage_vs_mid_bps?: string;
    fill_sim_book_consumption_pct?: string;
    fill_sim_fully_fillable?: string;
    close_price_at_resolution?: string;
    event_outcome_real?: string;
    won?: string;
    pnl_simulated?: string;
    resolution_status?: string;
    status: string;
}

export interface RawBlockedFull {
    blocked_id: string;
    detected_at_utc: string;
    event_id: string;
    ticker: string;
    timeframe_minutes: string;
    side: string;
    blocked_reason: string;
    estimated_stake_usd: string;
    estimated_shares?: string;
    side_price?: string;
    event_end_utc?: string;
    price_to_beat?: string;
    current_price?: string;
    quant_prob_side?: string;
    edge_pct?: string;
    sample_size?: string;
    percentile?: string;
}

export type DiagnosticTarget =
    | { kind: "bot_order"; row: RawBotOrderFull }
    | { kind: "blocked"; row: RawBlockedFull };

interface Props {
    target: DiagnosticTarget;
    settings: Record<string, unknown>;
    onClose: () => void;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

const n = (v: unknown): number => {
    const x = Number(v);
    return Number.isFinite(x) ? x : 0;
};

const fmt = (v: unknown, decimals = 4): string => {
    const x = Number(v);
    return Number.isFinite(x) ? x.toFixed(decimals) : "n/a";
};

const fmtUsd = (v: unknown, decimals = 2): string => {
    const x = Number(v);
    return Number.isFinite(x) && x !== 0 ? `$${x.toFixed(decimals)}` : "n/a";
};

const fmtPct = (v: unknown, decimals = 2): string => {
    const x = Number(v);
    return Number.isFinite(x) ? `${x.toFixed(decimals)}%` : "n/a";
};

const eventLabel = (eventId: string): string =>
    eventId.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

const BLOCKED_REASON_MAP: Record<string, string> = {
    event_exposure_cap_reached:
        "Event exposure cap reached — total spent on this event hit the limit.",
    drawdown_circuit_breaker:
        "Drawdown circuit breaker — effective equity fell below the stop threshold.",
    max_buys_per_event_reached:
        "Max buys per event reached — already placed the maximum number of orders for this event today.",
    event_cooldown_active:
        "Event cooldown active — too soon after the previous order on this event.",
    global_order_cooldown_active:
        "Global cooldown active — minimum time between any two orders not elapsed.",
    ticker_disabled_by_monitored_tickers:
        "Ticker is not in the monitored_tickers list.",
    invalid_shares: "Shares calculated were zero or negative.",
    invalid_notional: "Notional USD was zero or negative.",
};

const guardReasonLabel = (reason: string): string => {
    if (BLOCKED_REASON_MAP[reason]) return BLOCKED_REASON_MAP[reason];
    if (reason.startsWith("shares_below_min_")) {
        const min = reason.replace("shares_below_min_", "");
        return `Shares below minimum — calculated shares < ${min} (pm_min_shares).`;
    }
    if (reason.startsWith("notional_below_min_")) {
        const min = reason.replace("notional_below_min_", "");
        return `Notional below minimum — stake < $${min} (pm_min_notional_usd).`;
    }
    return reason;
};

// ── Sub-components ─────────────────────────────────────────────────────────────

function SectionTitle({ children }: { children: React.ReactNode }) {
    return <div className="order-diag-section-title">{children}</div>;
}

function CalcRow({
    label,
    value,
    sub,
}: {
    label: string;
    value: React.ReactNode;
    sub?: string;
}) {
    return (
        <div className="order-diag-calc-row">
            <span className="label">{label}</span>
            <span className="value">
                {value}
                {sub && (
                    <span
                        style={{ fontSize: "0.85em", opacity: 0.6, marginLeft: 6 }}
                    >
                        {sub}
                    </span>
                )}
            </span>
        </div>
    );
}

function GuardRow({
    label,
    formula,
    pass,
    highlight,
}: {
    label: string;
    formula: string;
    pass: boolean;
    highlight?: boolean;
}) {
    return (
        <div
            className={`order-diag-guard-row${highlight ? " guard-highlight" : ""}`}
        >
            <span className={pass ? "guard-pass" : "guard-fail"}>
                {pass ? "✓" : "✗"}
            </span>
            <span style={{ color: "#8b949e", minWidth: 160 }}>{label}</span>
            <span style={{ color: "#c9d1d9", flex: 1 }}>{formula}</span>
        </div>
    );
}

function Badge({ status }: { status: string }) {
    const s = status.toLowerCase().replace(/[^a-z_]/g, "");
    return (
        <span className={`order-diag-badge badge-${s}`}>{status.toUpperCase()}</span>
    );
}

// ── Bot Order Modal Content ────────────────────────────────────────────────────

function BotOrderContent({
    row,
    settings,
}: {
    row: RawBotOrderFull;
    settings: Record<string, unknown>;
}) {
    const statusLower = String(row.status || "").toLowerCase();
    const side = String(row.side || "").toLowerCase();
    const probSide = n(row.quant_prob);
    const probUp = side === "down" ? 1 - probSide : probSide;
    const askPrice = n(row.price);
    const edge = probSide - askPrice;
    const kellyRaw = askPrice > 0 && askPrice < 1 ? edge / (1 - askPrice) : 0;
    const kellyPctCsv = n(row.kelly_pct);
    const bankroll = n(row.bankroll_usd);
    const notional = n(row.notional_usd);
    const shares = n(row.shares);

    const hardCap = n(settings.bot_order_notional_cap_usd ?? 7);
    const eventExposurePct = n(settings.bot_max_event_exposure_pct ?? 15);
    const minShares = n(settings.pm_min_shares ?? 5);
    const minNotional = n(settings.pm_min_notional_usd ?? 1);
    const eventCapUsd = bankroll > 0 ? (bankroll * eventExposurePct) / 100 : 0;

    const fillPrice = n(row.fill_price_real);
    const filledNotional = n(row.filled_notional_usd_real);
    const filledShares = n(row.filled_shares_real);
    const slippage = n(row.slippage_pct);
    const edgeAtFill = n(row.edge_at_fill_pct);

    const isPlaced = statusLower === "placed";
    const isNoFill = statusLower === "no_fill";
    const isFailed = statusLower === "failed";
    const isResolved = row.resolution_status === "resolved";
    const won = String(row.won || "") === "1";
    const outcome = String(row.event_outcome_real || "").toLowerCase();

    const hasBid = row.best_bid_at_send !== undefined && row.best_bid_at_send !== "";
    const hasAsk = row.best_ask_at_send !== undefined && row.best_ask_at_send !== "";
    const hasSpread =
        row.spread_pct_at_send !== undefined && row.spread_pct_at_send !== "";

    return (
        <>
            {/* Header */}
            <div className="order-diag-header">
                <div
                    className="order-diag-title"
                    style={{ display: "flex", alignItems: "center", gap: 8 }}
                >
                    <Badge status={statusLower} />
                    <Badge status={side} />
                    <span style={{ marginLeft: 4 }}>{row.ticker}</span>
                </div>
                <div className="order-diag-meta" style={{ marginTop: 6 }}>
                    <span>{row.placed_at_utc.replace("T", " ").slice(0, 19)} UTC</span>
                    {row.slot && <span>Slot {row.slot}</span>}
                    {row.range && <span>Range {row.range}</span>}
                    <span
                        style={{
                            color: "#9bb0c2",
                            fontSize: "10px",
                            wordBreak: "break-all",
                        }}
                    >
                        {row.event_id}
                    </span>
                </div>
            </div>

            {/* 1. Kelly Sizing */}
            <div className="order-diag-section">
                <SectionTitle>1. Kelly Sizing</SectionTitle>
                <CalcRow label="Quant prob (side)" value={fmt(probSide)} />
                <CalcRow label="Prob UP" value={fmt(probUp)} />
                <CalcRow label="Ask price" value={fmt(askPrice)} />
                <CalcRow
                    label="Edge = prob − ask"
                    value={`${fmt(probSide)} − ${fmt(askPrice)} = ${fmt(edge)}`}
                />
                <CalcRow
                    label="Kelly raw = edge / (1 − ask)"
                    value={`${fmt(edge)} / ${fmt(1 - askPrice)} = ${fmtPct(kellyRaw * 100)}`}
                />
                <CalcRow
                    label="Kelly % applied (CSV)"
                    value={fmtPct(kellyPctCsv * 100)}
                    sub="← after fraction + caps"
                />
                {bankroll > 0 && (
                    <CalcRow
                        label="Stake = bankroll × kelly%"
                        value={`$${bankroll.toFixed(2)} × ${fmtPct(kellyPctCsv * 100)} = ${fmtUsd(bankroll * kellyPctCsv)}`}
                    />
                )}
                <CalcRow
                    label="Hard cap (bot_order_notional_cap_usd)"
                    value={fmtUsd(hardCap)}
                />
                <CalcRow
                    label="→ Notional sent"
                    value={fmtUsd(notional)}
                    sub={`shares = ${fmt(shares, 4)}`}
                />
            </div>

            {/* 2. Order Book Snapshot */}
            {(hasBid || hasAsk || hasSpread) && (
                <div className="order-diag-section">
                    <SectionTitle>2. Order Book (at send)</SectionTitle>
                    {hasBid && (
                        <CalcRow label="Best bid" value={fmt(n(row.best_bid_at_send))} />
                    )}
                    {hasAsk && (
                        <CalcRow label="Best ask" value={fmt(n(row.best_ask_at_send))} />
                    )}
                    {row.mid_at_send && row.mid_at_send !== "" && (
                        <CalcRow label="Mid" value={fmt(n(row.mid_at_send))} />
                    )}
                    {hasSpread && (
                        <CalcRow
                            label="Spread"
                            value={fmtPct(n(row.spread_pct_at_send) * 100)}
                        />
                    )}
                    {row.diff_vs_ptb_at_send !== undefined &&
                        row.diff_vs_ptb_at_send !== "" && (
                            <CalcRow
                                label="Diff vs price-to-beat"
                                value={`${fmt(n(row.diff_vs_ptb_at_send), 2)} pts`}
                            />
                        )}
                </div>
            )}

            {/* 3. Fill Simulator (v1.1-b) */}
            {row.expected_avg_fill_price !== undefined && row.expected_avg_fill_price !== "" && (
                <div className="order-diag-section">
                    <SectionTitle>3. Fill Simulator (pre-send estimate)</SectionTitle>
                    <CalcRow
                        label="Expected avg fill price"
                        value={fmt(n(row.expected_avg_fill_price))}
                        sub="← from order book depth"
                    />
                    {row.fill_sim_worst_price !== undefined && row.fill_sim_worst_price !== "" && (
                        <CalcRow label="Worst fill price" value={fmt(n(row.fill_sim_worst_price))} />
                    )}
                    {row.fill_sim_slippage_vs_ask_bps !== undefined && row.fill_sim_slippage_vs_ask_bps !== "" && (
                        <CalcRow
                            label="Predicted slippage vs ask"
                            value={`${fmt(n(row.fill_sim_slippage_vs_ask_bps), 1)} bps`}
                        />
                    )}
                    {row.fill_sim_slippage_vs_mid_bps !== undefined && row.fill_sim_slippage_vs_mid_bps !== "" && (
                        <CalcRow
                            label="Predicted IS vs mid"
                            value={`${fmt(n(row.fill_sim_slippage_vs_mid_bps), 1)} bps`}
                        />
                    )}
                    {row.fill_sim_levels_consumed !== undefined && row.fill_sim_levels_consumed !== "" && (
                        <CalcRow label="Book levels consumed" value={row.fill_sim_levels_consumed} />
                    )}
                    {row.fill_sim_book_consumption_pct !== undefined && row.fill_sim_book_consumption_pct !== "" && (
                        <CalcRow
                            label="Book consumption"
                            value={`${fmt(n(row.fill_sim_book_consumption_pct), 1)}%`}
                        />
                    )}
                    {row.fill_sim_fully_fillable !== undefined && row.fill_sim_fully_fillable !== "" && (
                        <CalcRow
                            label="Fully fillable"
                            value={
                                <span style={{ color: row.fill_sim_fully_fillable === "1" ? "#3fb950" : "#f85149" }}>
                                    {row.fill_sim_fully_fillable === "1" ? "Yes ✓" : "No — thin book ✗"}
                                </span>
                            }
                        />
                    )}
                </div>
            )}

            {/* 4. Risk Guards */}
            <div className="order-diag-section">
                <SectionTitle>4. Risk Guards</SectionTitle>
                <GuardRow
                    label="Min shares"
                    formula={`${fmt(shares, 2)} ≥ ${minShares} (pm_min_shares)`}
                    pass={shares >= minShares}
                />
                <GuardRow
                    label="Min notional"
                    formula={`${fmtUsd(notional)} ≥ ${fmtUsd(minNotional)} (pm_min_notional_usd)`}
                    pass={notional >= minNotional}
                />
                <GuardRow
                    label="Hard cap"
                    formula={`${fmtUsd(notional)} ≤ ${fmtUsd(hardCap)} (bot_order_notional_cap_usd)`}
                    pass={notional <= hardCap}
                />
                {bankroll > 0 && (
                    <GuardRow
                        label="Event exposure cap"
                        formula={`cap = ${fmtUsd(eventCapUsd)} (${fmtUsd(bankroll)} × ${eventExposurePct}%)`}
                        pass={notional <= eventCapUsd}
                    />
                )}
                <div
                    style={{
                        fontSize: 10,
                        color: "#8b949e",
                        marginTop: 4,
                        fontStyle: "italic",
                    }}
                >
                    Guards shown use current settings — bankroll is from CSV snapshot.
                </div>
            </div>

            {/* 5. CLOB Result */}
            <div className="order-diag-section">
                <SectionTitle>5. CLOB Result</SectionTitle>
                {isPlaced && (
                    <>
                        <CalcRow
                            label="Fill price"
                            value={fillPrice > 0 ? fmt(fillPrice) : "n/a"}
                        />
                        <CalcRow
                            label="Filled shares"
                            value={filledShares > 0 ? fmt(filledShares) : "n/a"}
                        />
                        <CalcRow
                            label="Filled notional"
                            value={filledNotional > 0 ? fmtUsd(filledNotional) : "n/a"}
                        />
                        {row.fill_count && row.fill_count !== "" && (
                            <CalcRow label="Fill count" value={row.fill_count} />
                        )}
                        <CalcRow
                            label="Slippage"
                            value={
                                row.slippage_pct !== undefined && row.slippage_pct !== ""
                                    ? fmtPct(slippage, 4)
                                    : "n/a"
                            }
                        />
                        <CalcRow
                            label="Edge at fill"
                            value={
                                row.edge_at_fill_pct !== undefined &&
                                row.edge_at_fill_pct !== ""
                                    ? fmtPct(edgeAtFill)
                                    : "n/a"
                            }
                        />
                        {row.realized_slippage_bps !== undefined && row.realized_slippage_bps !== "" && (
                            <CalcRow
                                label="Realized slippage"
                                value={
                                    <span style={{ color: n(row.realized_slippage_bps) > 10 ? "#f85149" : "#3fb950" }}>
                                        {fmt(n(row.realized_slippage_bps), 1)} bps
                                    </span>
                                }
                                sub="vs ask_price"
                            />
                        )}
                        {row.implementation_shortfall_bps !== undefined && row.implementation_shortfall_bps !== "" && (
                            <CalcRow
                                label="Implementation shortfall"
                                value={
                                    <span style={{ color: n(row.implementation_shortfall_bps) > 50 ? "#f85149" : "inherit" }}>
                                        {fmt(n(row.implementation_shortfall_bps), 1)} bps
                                    </span>
                                }
                                sub="vs mid_at_send"
                            />
                        )}
                        {row.implementation_shortfall_usd !== undefined && row.implementation_shortfall_usd !== "" && (
                            <CalcRow
                                label="IS cost (USD)"
                                value={fmtUsd(n(row.implementation_shortfall_usd), 4)}
                                sub="(fill − mid) × shares"
                            />
                        )}
                        {row.expected_avg_fill_price !== undefined && row.expected_avg_fill_price !== "" && fillPrice > 0 && (
                            <CalcRow
                                label="Sim error"
                                value={
                                    <span style={{ color: Math.abs(n(row.expected_avg_fill_price) - fillPrice) > 0.001 ? "#f85149" : "#3fb950" }}>
                                        {fmt((fillPrice - n(row.expected_avg_fill_price)) * 10000, 1)} bps
                                    </span>
                                }
                                sub="fill_real − expected"
                            />
                        )}
                    </>
                )}
                {isNoFill && (
                    <>
                        <div className="order-diag-error-box">
                            {(row.fills_detail_json || "no details")
                                .replace(/^error:/, "")
                                .trim()}
                        </div>
                        <div className="order-diag-error-explain">
                            El orderbook no tenía asks disponibles al momento del envío
                            (FAK order). No se gastó USDC. El bot desbloqueará el gate y
                            reintentará tras el cooldown.
                        </div>
                    </>
                )}
                {isFailed && (
                    <>
                        <div className="order-diag-error-box">
                            {(row.fills_detail_json || "no details")
                                .replace(/^error:/, "")
                                .trim()}
                        </div>
                        <div className="order-diag-error-explain">
                            Error inesperado durante el envío. El gate permanece
                            bloqueado para este evento/side.
                        </div>
                    </>
                )}
            </div>

            {/* 6. Outcome */}
            {isResolved && outcome && (
                <div className="order-diag-section">
                    <SectionTitle>6. Outcome</SectionTitle>
                    <CalcRow
                        label="Result"
                        value={
                            <span
                                style={{ color: won ? "#3fb950" : "#f85149" }}
                            >
                                {won ? "WIN ✓" : "LOSS ✗"}
                            </span>
                        }
                    />
                    <CalcRow
                        label="Event outcome"
                        value={outcome.toUpperCase()}
                    />
                    {row.close_price_at_resolution &&
                        row.close_price_at_resolution !== "" && (
                            <CalcRow
                                label="Close price"
                                value={fmt(n(row.close_price_at_resolution))}
                            />
                        )}
                    <CalcRow
                        label="PnL simulated"
                        value={
                            row.pnl_simulated !== undefined &&
                            row.pnl_simulated !== "" ? (
                                <span
                                    style={{
                                        color:
                                            n(row.pnl_simulated) >= 0
                                                ? "#3fb950"
                                                : "#f85149",
                                    }}
                                >
                                    {fmtUsd(n(row.pnl_simulated))}
                                </span>
                            ) : (
                                "n/a"
                            )
                        }
                    />
                </div>
            )}
            {!isResolved && (
                <div
                    style={{
                        fontSize: 11,
                        color: "#8b949e",
                        fontStyle: "italic",
                        marginTop: 8,
                    }}
                >
                    Event not yet resolved — outcome pending.
                </div>
            )}
        </>
    );
}

// ── Blocked Modal Content ──────────────────────────────────────────────────────

function BlockedContent({
    row,
    settings,
}: {
    row: RawBlockedFull;
    settings: Record<string, unknown>;
}) {
    const side = String(row.side || "").toLowerCase();
    const probSide = n(row.quant_prob_side);
    const edgePct = n(row.edge_pct);
    const sampleSize = n(row.sample_size);
    const sidePrice = n(row.side_price);
    const estimatedStake = n(row.estimated_stake_usd);
    const estimatedShares = n(row.estimated_shares);
    const priceToBeat = n(row.price_to_beat);
    const currentPrice = n(row.current_price);
    const percentile = row.percentile !== undefined && row.percentile !== "" ? n(row.percentile) : null;

    const reason = row.blocked_reason || "";

    // For event_exposure_cap_reached, show numbers from settings
    const bankroll = n(settings.kelly_live_bankroll_usd ?? settings.kelly_bankroll ?? 100);
    const eventExposurePct = n(settings.bot_max_event_exposure_pct ?? 15);
    const eventCapUsd = (bankroll * eventExposurePct) / 100;
    const minShares = n(settings.pm_min_shares ?? 5);
    const minNotional = n(settings.pm_min_notional_usd ?? 1);

    return (
        <>
            {/* Header */}
            <div className="order-diag-header">
                <div
                    className="order-diag-title"
                    style={{ display: "flex", alignItems: "center", gap: 8 }}
                >
                    <Badge status="blocked" />
                    <Badge status={side} />
                    <span style={{ marginLeft: 4 }}>{row.ticker}</span>
                </div>
                <div className="order-diag-meta" style={{ marginTop: 6 }}>
                    <span>
                        {row.detected_at_utc.replace("T", " ").slice(0, 19)} UTC
                    </span>
                    <span>{row.timeframe_minutes}m</span>
                    <span
                        style={{
                            color: "#9bb0c2",
                            fontSize: "10px",
                            wordBreak: "break-all",
                        }}
                    >
                        {row.event_id}
                    </span>
                </div>
            </div>

            {/* 1. Signal */}
            <div className="order-diag-section">
                <SectionTitle>1. Signal</SectionTitle>
                {probSide > 0 && (
                    <CalcRow label="Quant prob (side)" value={fmt(probSide)} />
                )}
                {edgePct !== 0 && (
                    <CalcRow label="Edge" value={fmtPct(edgePct)} />
                )}
                {sampleSize > 0 && (
                    <CalcRow label="Sample size" value={sampleSize} />
                )}
                {percentile !== null && (
                    <CalcRow label="Percentile" value={fmtPct(percentile)} />
                )}
            </div>

            {/* 2. Market Context */}
            <div className="order-diag-section">
                <SectionTitle>2. Market Context</SectionTitle>
                {sidePrice > 0 && (
                    <CalcRow label="Ask (side_price)" value={fmt(sidePrice)} />
                )}
                {priceToBeat !== 0 && (
                    <CalcRow
                        label="Price to beat"
                        value={fmt(priceToBeat, 2)}
                    />
                )}
                {currentPrice !== 0 && (
                    <CalcRow
                        label="Current price"
                        value={fmt(currentPrice, 2)}
                    />
                )}
                {priceToBeat !== 0 && currentPrice !== 0 && (
                    <CalcRow
                        label="Diff vs PTB"
                        value={`${(currentPrice - priceToBeat).toFixed(2)} pts`}
                    />
                )}
                {estimatedStake > 0 && (
                    <CalcRow
                        label="Estimated stake"
                        value={fmtUsd(estimatedStake)}
                    />
                )}
                {estimatedShares > 0 && (
                    <CalcRow
                        label="Estimated shares"
                        value={fmt(estimatedShares, 2)}
                    />
                )}
            </div>

            {/* 3. Guard that blocked */}
            <div className="order-diag-section">
                <SectionTitle>3. Guard que bloqueó</SectionTitle>
                <div className="guard-highlight" style={{ marginBottom: 8 }}>
                    <div
                        style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            marginBottom: 6,
                        }}
                    >
                        <span className="guard-fail">✗</span>
                        <span
                            style={{
                                fontFamily: "monospace",
                                fontSize: 12,
                                color: "#f85149",
                            }}
                        >
                            {reason}
                        </span>
                    </div>
                    <div
                        style={{
                            fontSize: 12,
                            color: "#c9d1d9",
                            lineHeight: 1.5,
                        }}
                    >
                        {guardReasonLabel(reason)}
                    </div>
                </div>

                {/* Contextual numbers for common guards */}
                {reason === "event_exposure_cap_reached" && (
                    <>
                        <CalcRow
                            label="Event cap"
                            value={`${fmtUsd(bankroll)} × ${eventExposurePct}% = ${fmtUsd(eventCapUsd)}`}
                        />
                        {estimatedStake > 0 && (
                            <CalcRow
                                label="Estimated stake"
                                value={fmtUsd(estimatedStake)}
                            />
                        )}
                        <div
                            style={{
                                fontSize: 10,
                                color: "#8b949e",
                                marginTop: 4,
                                fontStyle: "italic",
                            }}
                        >
                            Bankroll uses current setting (kelly_live_bankroll_usd).
                        </div>
                    </>
                )}
                {reason.startsWith("shares_below_min_") && (
                    <>
                        <CalcRow
                            label="Estimated shares"
                            value={estimatedShares > 0 ? fmt(estimatedShares, 2) : "n/a"}
                        />
                        <CalcRow
                            label="pm_min_shares"
                            value={minShares}
                        />
                        {sidePrice > 0 && estimatedStake > 0 && (
                            <CalcRow
                                label="Stake / ask"
                                value={`${fmtUsd(estimatedStake)} / ${fmt(sidePrice)} = ${fmt(estimatedStake / sidePrice, 2)} shares`}
                            />
                        )}
                    </>
                )}
                {reason.startsWith("notional_below_min_") && (
                    <CalcRow
                        label="pm_min_notional_usd"
                        value={fmtUsd(minNotional)}
                    />
                )}
                {reason === "max_buys_per_event_reached" && (
                    <CalcRow
                        label="bot_max_buys_per_event_side"
                        value={String(settings.bot_max_buys_per_event_side ?? "?")}
                    />
                )}
                {reason === "event_cooldown_active" && (
                    <CalcRow
                        label="bot_cooldown_seconds_per_event_side"
                        value={`${settings.bot_cooldown_seconds_per_event_side ?? "?"}s`}
                    />
                )}
                {reason === "global_order_cooldown_active" && (
                    <CalcRow
                        label="bot_global_min_seconds_between_orders"
                        value={`${settings.bot_global_min_seconds_between_orders ?? "?"}s`}
                    />
                )}
            </div>
        </>
    );
}

// ── Main Modal ─────────────────────────────────────────────────────────────────

export default function OrderDiagnosticModal({ target, settings, onClose }: Props) {
    // Close on Escape key
    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        };
        window.addEventListener("keydown", handler);
        return () => window.removeEventListener("keydown", handler);
    }, [onClose]);

    return (
        <div
            className="order-diag-overlay"
            onClick={(e) => {
                if (e.target === e.currentTarget) onClose();
            }}
        >
            <div className="order-diag-modal">
                <button
                    className="order-diag-close"
                    onClick={onClose}
                    aria-label="Close"
                >
                    ×
                </button>
                {target.kind === "bot_order" ? (
                    <BotOrderContent row={target.row} settings={settings} />
                ) : (
                    <BlockedContent row={target.row} settings={settings} />
                )}
            </div>
        </div>
    );
}
