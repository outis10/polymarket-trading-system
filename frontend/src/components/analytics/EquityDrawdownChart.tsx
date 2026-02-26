import { useEffect, useMemo, useRef } from "react";
import {
    createChart,
    IChartApi,
    ISeriesApi,
    LineData,
    Time,
} from "lightweight-charts";

export interface EquityDrawdownPoint {
    ts: string;
    equity: number;
    drawdownPct: number;
}

interface Props {
    points: EquityDrawdownPoint[];
}

export default function EquityDrawdownChart({ points }: Props) {
    const containerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const equityRef = useRef<ISeriesApi<"Line"> | null>(null);
    const drawdownRef = useRef<ISeriesApi<"Line"> | null>(null);

    const normalized = useMemo(() => {
        const sorted = points
            .map((p) => ({ ...p, t: new Date(p.ts).getTime() }))
            .filter((p) => Number.isFinite(p.t))
            .sort((a, b) => a.t - b.t);

        // lightweight-charts requires strictly ascending unique time values.
        // If multiple rows share the same timestamp, keep the latest payload.
        const deduped: Array<(typeof sorted)[number]> = [];
        for (const row of sorted) {
            const prev = deduped[deduped.length - 1];
            if (!prev) {
                deduped.push(row);
                continue;
            }
            if (row.t === prev.t) {
                deduped[deduped.length - 1] = row;
            } else if (row.t > prev.t) {
                deduped.push(row);
            }
        }
        return deduped;
    }, [points]);

    useEffect(() => {
        if (!containerRef.current) return;
        const chart = createChart(containerRef.current, {
            layout: {
                background: { color: "transparent" },
                textColor: "#98a6b8",
            },
            grid: {
                vertLines: { color: "rgba(43, 53, 66, 0.35)" },
                horzLines: { color: "rgba(43, 53, 66, 0.35)" },
            },
            rightPriceScale: {
                borderColor: "#2b3542",
                scaleMargins: { top: 0.12, bottom: 0.14 },
            },
            leftPriceScale: {
                visible: true,
                borderColor: "#2b3542",
                scaleMargins: { top: 0.12, bottom: 0.14 },
            },
            timeScale: {
                borderColor: "#2b3542",
                timeVisible: true,
                secondsVisible: false,
            },
            crosshair: { mode: 1 },
            handleScale: true,
            handleScroll: true,
        });

        const equity = chart.addLineSeries({
            color: "#3fb950",
            lineWidth: 2,
            priceScaleId: "right",
            title: "Equity",
        });
        const drawdown = chart.addLineSeries({
            color: "#f85149",
            lineWidth: 2,
            priceScaleId: "left",
            title: "Drawdown %",
        });

        chartRef.current = chart;
        equityRef.current = equity;
        drawdownRef.current = drawdown;

        const onResize = () => {
            if (!containerRef.current) return;
            chart.applyOptions({ width: containerRef.current.clientWidth });
        };

        window.addEventListener("resize", onResize);
        onResize();
        return () => {
            window.removeEventListener("resize", onResize);
            chart.remove();
        };
    }, []);

    useEffect(() => {
        if (!equityRef.current || !drawdownRef.current) return;
        const equityData: LineData[] = normalized.map((p) => ({
            time: (p.t / 1000) as Time,
            value: p.equity,
        }));
        const drawdownData: LineData[] = normalized.map((p) => ({
            time: (p.t / 1000) as Time,
            value: p.drawdownPct,
        }));

        equityRef.current.setData(equityData);
        drawdownRef.current.setData(drawdownData);
        chartRef.current?.timeScale().fitContent();
    }, [normalized]);

    return <div ref={containerRef} className="analytics-chart-canvas" />;
}
