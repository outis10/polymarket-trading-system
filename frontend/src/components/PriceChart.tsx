import { useEffect, useRef } from "react";
import {
    createChart,
    IChartApi,
    ISeriesApi,
    LineData,
    Time,
} from "lightweight-charts";
import type { PriceHistoryPoint } from "../types/events";

interface PriceChartProps {
    priceHistory?: PriceHistoryPoint[] | null;
}

function normalizeHistory(points: PriceHistoryPoint[]): PriceHistoryPoint[] {
    // Lightweight Charts requires strictly ascending unique time values.
    const sorted = [...points]
        .map((p) => ({ p, ts: new Date(p.timestamp).getTime() }))
        .filter((x) => Number.isFinite(x.ts))
        .sort((a, b) => a.ts - b.ts);

    const deduped: Array<{ p: PriceHistoryPoint; ts: number }> = [];
    for (const row of sorted) {
        const prev = deduped[deduped.length - 1];
        if (!prev) {
            deduped.push(row);
            continue;
        }
        if (row.ts === prev.ts) {
            // Same timestamp: keep the newest point payload.
            deduped[deduped.length - 1] = row;
        } else if (row.ts > prev.ts) {
            deduped.push(row);
        }
    }
    return deduped.map((x) => x.p);
}

export default function PriceChart({ priceHistory }: PriceChartProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const priceSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
    const probSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
    const changeSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

    // Initialize chart
    useEffect(() => {
        if (!containerRef.current) return;

        const chart = createChart(containerRef.current, {
            layout: {
                background: { color: "transparent" },
                textColor: "#8b949e",
            },
            grid: {
                vertLines: { color: "rgba(48, 54, 61, 0.5)" },
                horzLines: { color: "rgba(48, 54, 61, 0.5)" },
            },
            crosshair: {
                mode: 1,
            },
            rightPriceScale: {
                borderColor: "#30363d",
                scaleMargins: { top: 0.1, bottom: 0.1 },
            },
            leftPriceScale: {
                visible: true,
                borderColor: "#30363d",
                scaleMargins: { top: 0.1, bottom: 0.1 },
            },
            timeScale: {
                borderColor: "#30363d",
                timeVisible: true,
                secondsVisible: false,
            },
            handleScale: false,
            handleScroll: false,
        });

        // BTC Price series (left scale, orange)
        const priceSeries = chart.addLineSeries({
            color: "#f7931a",
            lineWidth: 2,
            priceScaleId: "left",
            title: "BTC",
        });
        priceSeriesRef.current = priceSeries;

        // Probability series (right scale, green/red)
        const probSeries = chart.addLineSeries({
            color: "#3fb950",
            lineWidth: 2,
            priceScaleId: "right",
            title: "UP %",
        });
        probSeriesRef.current = probSeries;

        // Price change series (right scale, blue dotted)
        const changeSeries = chart.addLineSeries({
            color: "#58a6ff",
            lineWidth: 1,
            lineStyle: 2, // dotted
            priceScaleId: "right",
            title: "Change %",
        });
        changeSeriesRef.current = changeSeries;

        chartRef.current = chart;

        const handleResize = () => {
            if (containerRef.current) {
                chart.applyOptions({ width: containerRef.current.clientWidth });
            }
        };

        window.addEventListener("resize", handleResize);
        handleResize();

        return () => {
            window.removeEventListener("resize", handleResize);
            chart.remove();
        };
    }, []);

    // Update data
    useEffect(() => {
        if (!chartRef.current) return;
        const safeHistory = Array.isArray(priceHistory) ? priceHistory : [];
        if (!safeHistory.length) return;
        const cleanHistory = normalizeHistory(safeHistory);
        if (!cleanHistory.length) return;

        const priceData: LineData[] = cleanHistory.map((p) => ({
            time: (new Date(p.timestamp).getTime() / 1000) as Time,
            value: p.price,
        }));

        const probData: LineData[] = cleanHistory.map((p) => ({
            time: (new Date(p.timestamp).getTime() / 1000) as Time,
            value: p.yes_price * 100,
        }));

        const changeData: LineData[] = cleanHistory.map((p) => ({
            time: (new Date(p.timestamp).getTime() / 1000) as Time,
            value: p.percent_change,
        }));

        priceSeriesRef.current?.setData(priceData);

        probSeriesRef.current?.setData(probData);
        probSeriesRef.current?.applyOptions({ visible: true });

        changeSeriesRef.current?.setData(changeData);
        changeSeriesRef.current?.applyOptions({ visible: true });

        // Update probability line color based on average
        if (probData.length > 0) {
            const avg =
                probData.reduce((sum, p) => sum + p.value, 0) / probData.length;
            probSeriesRef.current?.applyOptions({
                color: avg >= 50 ? "#3fb950" : "#f85149",
            });
        }

        // Add price to beat horizontal line (dashed gray)
        if (cleanHistory.length > 0 && priceSeriesRef.current) {
            const ptb = cleanHistory[0].price_to_beat;
            if (ptb > 0) {
                // Remove existing price lines first
                const existingLines =
                    (priceSeriesRef.current as any)._priceLines || [];
                existingLines.forEach((line: any) => {
                    try {
                        priceSeriesRef.current?.removePriceLine(line);
                    } catch {}
                });

                // Create new price line
                const priceLine = priceSeriesRef.current.createPriceLine({
                    price: ptb,
                    color: "#8b949e",
                    lineWidth: 1,
                    lineStyle: 2, // Dashed
                    axisLabelVisible: true,
                    title: "Target",
                });
                (priceSeriesRef.current as any)._priceLines = [priceLine];
            }
        }

        // Add 50% reference line on probability scale
        if (probSeriesRef.current) {
            const existingLines =
                (probSeriesRef.current as any)._priceLines || [];
            existingLines.forEach((line: any) => {
                try {
                    probSeriesRef.current?.removePriceLine(line);
                } catch {}
            });

            const fiftyLine = probSeriesRef.current.createPriceLine({
                price: 50,
                color: "rgba(139, 148, 158, 0.3)",
                lineWidth: 1,
                lineStyle: 2, // Dashed
                axisLabelVisible: false,
                title: "",
            });
            (probSeriesRef.current as any)._priceLines = [fiftyLine];
        }

        // Auto-scale price to center on price_to_beat
        if (cleanHistory.length > 0) {
            const ptb = cleanHistory[0].price_to_beat || priceData[0].value;
            const prices = priceData.map((d) => d.value);
            const minP = Math.min(...prices);
            const maxP = Math.max(...prices);
            let halfWindow = 500;
            if (maxP - ptb > halfWindow || ptb - minP > halfWindow) {
                halfWindow = 1000;
            }
            chartRef.current?.priceScale("left").applyOptions({
                autoScale: false,
                scaleMargins: { top: 0.1, bottom: 0.1 },
            });
        }

        chartRef.current?.timeScale().fitContent();
    }, [priceHistory]);

    return <div ref={containerRef} className="chart-container" />;
}
