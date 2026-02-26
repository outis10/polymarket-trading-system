import { useEffect, useMemo, useRef } from "react";
import {
    createChart,
    IChartApi,
    ISeriesApi,
    LineData,
    Time,
} from "lightweight-charts";

export interface TradingEquityPoint {
    ts: string;
    equity: number;
}

interface Props {
    points: TradingEquityPoint[];
    color?: string;
}

export default function TradingEquityCurveChart({
    points,
    color = "#58a6ff",
}: Props) {
    const containerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const equityRef = useRef<ISeriesApi<"Line"> | null>(null);

    const normalized = useMemo(() => {
        const sorted = points
            .map((p) => ({ ...p, t: new Date(p.ts).getTime() }))
            .filter((p) => Number.isFinite(p.t))
            .sort((a, b) => a.t - b.t);

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
            timeScale: {
                borderColor: "#2b3542",
                timeVisible: true,
                secondsVisible: false,
                rightOffset: 8,
            },
            crosshair: { mode: 1 },
            handleScale: true,
            handleScroll: true,
        });

        const equity = chart.addLineSeries({
            color,
            lineWidth: 2,
            priceScaleId: "right",
            title: "Equity",
        });

        chartRef.current = chart;
        equityRef.current = equity;

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
    }, [color]);

    useEffect(() => {
        if (!equityRef.current) return;
        const equityData: LineData[] = normalized.map((p) => ({
            time: (p.t / 1000) as Time,
            value: p.equity,
        }));
        equityRef.current.setData(equityData);
        chartRef.current?.timeScale().fitContent();
    }, [normalized]);

    return <div ref={containerRef} className="analytics-chart-canvas" />;
}
