import { memo, useId, useMemo } from "react";
import type { PriceHistoryPoint } from "../types/events";

export interface OrderMarker {
    timestamp: number; // ms epoch
    side: "up" | "down";
    notional?: number;
}

interface Props {
    priceHistory: PriceHistoryPoint[];
    orders?: OrderMarker[];
}

const VB_W = 400;
const VB_H = 80;
const PAD_T = 12;
const PAD_B = 10;
const PAD_L = 4;
const PAD_R = 36; // leave room for end label
const PLOT_W = VB_W - PAD_L - PAD_R;
const PLOT_H = VB_H - PAD_T - PAD_B;

function toX(t: number, minT: number, tRange: number): number {
    return PAD_L + ((t - minT) / tRange) * PLOT_W;
}

function toY(v: number, yMin: number, yRange: number): number {
    // SVG Y axis is flipped
    return PAD_T + (1 - (v - yMin) / yRange) * PLOT_H;
}

function buildLinePath(pts: { x: number; y: number }[]): string {
    return pts
        .map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
        .join(" ");
}

function buildAreaPath(pts: { x: number; y: number }[], y50: number): string {
    const line = buildLinePath(pts);
    const last = pts[pts.length - 1];
    const first = pts[0];
    return `${line} L${last.x.toFixed(1)},${y50.toFixed(1)} L${first.x.toFixed(1)},${y50.toFixed(1)} Z`;
}

function ProbabilitySparkline({ priceHistory, orders = [] }: Props) {
    const uid = useId();

    // All heavy geometry memoized — only recomputes when price history changes
    const geo = useMemo(() => {
        const parsed = priceHistory
            .map((p) => ({ t: new Date(p.timestamp).getTime(), v: p.yes_price }))
            .filter((p) => Number.isFinite(p.t) && Number.isFinite(p.v));

        if (parsed.length < 2) return null;

        const minT = parsed[0].t;
        const maxT = parsed[parsed.length - 1].t;
        const tRange = Math.max(maxT - minT, 1);

        // Avoid spread operator (stack-safe for large arrays)
        let dataMin = 0.5;
        let dataMax = 0.5;
        for (const p of parsed) {
            if (p.v < dataMin) dataMin = p.v;
            if (p.v > dataMax) dataMax = p.v;
        }
        const pad = Math.max((dataMax - dataMin) * 0.15, 0.03);
        const yMin = Math.max(0, dataMin - pad);
        const yMax = Math.min(1, dataMax + pad);
        const yRange = Math.max(yMax - yMin, 0.01);

        const pts = parsed.map((p) => ({
            x: toX(p.t, minT, tRange),
            y: toY(p.v, yMin, yRange),
        }));

        const y50 = toY(0.5, yMin, yRange);
        const linePath = buildLinePath(pts);
        const areaPath = buildAreaPath(pts, y50);
        const lastVal = parsed[parsed.length - 1].v;

        return { parsed, pts, y50, linePath, areaPath, lastVal, minT, maxT, tRange };
    }, [priceHistory]);

    // Order markers recomputed only when orders or geometry changes
    const orderPts = useMemo(() => {
        if (!geo) return [];
        const { pts, parsed, minT, maxT, tRange } = geo;
        return orders.map((o) => {
            const clampedT = Math.max(minT, Math.min(maxT, o.timestamp));
            const x = toX(clampedT, minT, tRange);
            let nearestIdx = 0;
            let minDiff = Infinity;
            parsed.forEach((p, i) => {
                const diff = Math.abs(p.t - o.timestamp);
                if (diff < minDiff) { minDiff = diff; nearestIdx = i; }
            });
            return { x, y: pts[nearestIdx].y, side: o.side, notional: o.notional };
        });
    }, [geo, orders]);

    if (!geo) return null;

    const { pts, y50, linePath, areaPath, lastVal } = geo;
    const lastPt = pts[pts.length - 1];
    const labelColor = lastVal >= 0.5 ? "#23d18b" : "#f85149";
    const yTop = PAD_T;
    const yBot = PAD_T + PLOT_H;

    const clipAbove = `${uid}-ca`;
    const clipBelow = `${uid}-cb`;

    return (
        <div className="prob-sparkline-wrap">
            <svg
                viewBox={`0 0 ${VB_W} ${VB_H}`}
                preserveAspectRatio="none"
                className="prob-sparkline-svg"
                aria-hidden="true"
            >
                <defs>
                    {/* Clip: everything above the 50% line */}
                    <clipPath id={clipAbove}>
                        <rect
                            x={PAD_L}
                            y={yTop}
                            width={PLOT_W}
                            height={Math.max(0, y50 - yTop)}
                        />
                    </clipPath>
                    {/* Clip: everything below the 50% line */}
                    <clipPath id={clipBelow}>
                        <rect
                            x={PAD_L}
                            y={y50}
                            width={PLOT_W}
                            height={Math.max(0, yBot - y50)}
                        />
                    </clipPath>
                </defs>

                {/* Green fill: area above 50% */}
                <path
                    d={areaPath}
                    fill="rgba(35, 209, 139, 0.13)"
                    stroke="none"
                    clipPath={`url(#${clipAbove})`}
                />

                {/* Red fill: area below 50% */}
                <path
                    d={areaPath}
                    fill="rgba(248, 81, 73, 0.13)"
                    stroke="none"
                    clipPath={`url(#${clipBelow})`}
                />

                {/* 50% reference line */}
                <line
                    x1={PAD_L}
                    y1={y50}
                    x2={VB_W - PAD_R}
                    y2={y50}
                    stroke="#8b949e"
                    strokeWidth="0.7"
                    strokeDasharray="4,3"
                    opacity={0.55}
                />
                <text
                    x={PAD_L + 2}
                    y={y50 - 2}
                    fontSize="7"
                    fill="#8b949e"
                    fontFamily="JetBrains Mono, monospace"
                    opacity={0.6}
                >
                    50%
                </text>

                {/* Probability curve */}
                <path
                    d={linePath}
                    fill="none"
                    stroke="#c9d1d9"
                    strokeWidth="1.5"
                    strokeLinejoin="round"
                    strokeLinecap="round"
                />

                {/* Current value label — right edge */}
                <text
                    x={lastPt.x + 4}
                    y={lastPt.y + 3.5}
                    fontSize="9"
                    fill={labelColor}
                    fontFamily="JetBrains Mono, monospace"
                    fontWeight="700"
                >
                    {(lastVal * 100).toFixed(0)}%
                </text>

                {/* Order markers */}
                {orderPts.map((o, i) =>
                    o.side === "up" ? (
                        // Triangle pointing UP — buy up order
                        <polygon
                            key={i}
                            points={`${o.x},${o.y - 7} ${o.x - 5},${o.y + 2} ${o.x + 5},${o.y + 2}`}
                            fill="#23d18b"
                            stroke="#0d1117"
                            strokeWidth="0.8"
                            opacity={0.92}
                        >
                            <title>
                                BUY UP
                                {o.notional ? ` $${o.notional.toFixed(2)}` : ""}
                            </title>
                        </polygon>
                    ) : (
                        // Triangle pointing DOWN — buy down order
                        <polygon
                            key={i}
                            points={`${o.x},${o.y + 7} ${o.x - 5},${o.y - 2} ${o.x + 5},${o.y - 2}`}
                            fill="#f85149"
                            stroke="#0d1117"
                            strokeWidth="0.8"
                            opacity={0.92}
                        >
                            <title>
                                BUY DOWN
                                {o.notional ? ` $${o.notional.toFixed(2)}` : ""}
                            </title>
                        </polygon>
                    ),
                )}
            </svg>
        </div>
    );
}

export default memo(ProbabilitySparkline);
