import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
    createChart,
    IChartApi,
    ISeriesApi,
    LineData,
    LineStyle,
    Time,
} from "lightweight-charts";

export interface TradingEquityPoint {
    ts: string;
    equity: number;
}

interface Props {
    points: TradingEquityPoint[];
    color?: string;
    drawdownThresholdPnl?: number; // línea roja de circuit breaker (-startBankroll * stopPct/100)
}

interface Snapshot {
    time: Time;
    price: number;
    priceLine: ReturnType<ISeriesApi<"Line">["createPriceLine"]>;
    divEl: HTMLDivElement;
}

const SNAP_COLOR = "rgba(255, 184, 0, 0.75)";
const HIT_RADIUS = 6; // px — proximidad para eliminar snapshot al hacer click

export default function TradingEquityCurveChart({
    points,
    color = "#58a6ff",
    drawdownThresholdPnl,
}: Props) {
    const containerRef = useRef<HTMLDivElement>(null);
    const overlayRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const equityRef = useRef<ISeriesApi<"Line"> | null>(null);
    const drawdownRef = useRef<ISeriesApi<"Line"> | null>(null);
    const snapshotsRef = useRef<Snapshot[]>([]);
    const thresholdLineRef = useRef<ReturnType<ISeriesApi<"Line">["createPriceLine"]> | null>(null);
    const [hasSnapshots, setHasSnapshots] = useState(false);
    const [showDrawdown, setShowDrawdown] = useState(true);

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
        if (!containerRef.current || !overlayRef.current) return;

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
        const drawdown = chart.addLineSeries({
            color: "#f85149",
            lineWidth: 2,
            priceScaleId: "left",
            title: "Drawdown %",
        });

        chartRef.current = chart;
        equityRef.current = equity;
        drawdownRef.current = drawdown;

        // Reposiciona las líneas verticales de todos los snapshots
        const syncVerticalLines = () => {
            for (const snap of snapshotsRef.current) {
                const x = chart.timeScale().timeToCoordinate(snap.time);
                if (x === null || x === undefined) {
                    snap.divEl.style.display = "none";
                } else {
                    snap.divEl.style.display = "block";
                    snap.divEl.style.left = `${Math.round(x)}px`;
                }
            }
        };

        // Actualizar posiciones al hacer scroll / zoom
        chart.timeScale().subscribeVisibleTimeRangeChange(syncVerticalLines);

        // Click: añadir snapshot o eliminar si está cerca de uno existente
        chart.subscribeClick((param) => {
            if (!param.time || !param.point) return;

            const clickX = param.point.x;

            // ¿Cerca de un snapshot existente? → eliminarlo
            const hit = snapshotsRef.current.find((s) => {
                const sx = chart.timeScale().timeToCoordinate(s.time);
                return sx !== null && Math.abs(sx - clickX) <= HIT_RADIUS;
            });

            if (hit) {
                equity.removePriceLine(hit.priceLine);
                hit.divEl.remove();
                snapshotsRef.current = snapshotsRef.current.filter(
                    (s) => s !== hit
                );
                setHasSnapshots(snapshotsRef.current.length > 0);
                return;
            }

            // Precio en el punto Y del click
            const price = equity.coordinateToPrice(param.point.y);
            if (price === null || price === undefined) return;

            // Línea horizontal (price line nativa)
            const priceLine = equity.createPriceLine({
                price,
                color: SNAP_COLOR,
                lineWidth: 1,
                lineStyle: LineStyle.Dashed,
                axisLabelVisible: true,
                title: "",
            });

            // Línea vertical (div sobre el canvas)
            const divEl = document.createElement("div");
            divEl.style.cssText = [
                "position:absolute",
                "top:0",
                "height:100%",
                "width:1px",
                `border-left:1px dashed ${SNAP_COLOR}`,
                "pointer-events:none",
                "display:block",
            ].join(";");
            overlayRef.current!.appendChild(divEl);

            const snap: Snapshot = {
                time: param.time as Time,
                price,
                priceLine,
                divEl,
            };
            snapshotsRef.current.push(snap);
            setHasSnapshots(true);

            // Posición inicial
            const x = chart.timeScale().timeToCoordinate(param.time as Time);
            if (x !== null && x !== undefined) divEl.style.left = `${Math.round(x)}px`;
        });

        const onResize = () => {
            if (!containerRef.current) return;
            chart.applyOptions({ width: containerRef.current.clientWidth });
            syncVerticalLines();
        };

        window.addEventListener("resize", onResize);
        onResize();

        return () => {
            window.removeEventListener("resize", onResize);
            snapshotsRef.current.forEach((s) => s.divEl.remove());
            snapshotsRef.current = [];
            chart.remove();
        };
    }, [color]);

    useEffect(() => {
        if (!equityRef.current || !drawdownRef.current) return;

        let peak = 0;
        const equityData: LineData[] = [];
        const drawdownData: LineData[] = [];

        for (const p of normalized) {
            const t = (p.t / 1000) as Time;
            peak = Math.max(peak, p.equity);
            const ddPct = peak > 0 ? ((p.equity - peak) / peak) * 100 : 0;
            equityData.push({ time: t, value: p.equity });
            drawdownData.push({ time: t, value: ddPct });
        }

        equityRef.current.setData(equityData);
        drawdownRef.current.setData(drawdownData);
        chartRef.current?.timeScale().fitContent();
    }, [normalized]);

    useEffect(() => {
        if (!drawdownRef.current) return;
        drawdownRef.current.applyOptions({ visible: showDrawdown });
        chartRef.current?.applyOptions({
            leftPriceScale: { visible: showDrawdown },
        });
    }, [showDrawdown]);

    useEffect(() => {
        const equity = equityRef.current;
        if (!equity) return;

        // Eliminar línea anterior si existe
        if (thresholdLineRef.current) {
            equity.removePriceLine(thresholdLineRef.current);
            thresholdLineRef.current = null;
        }

        if (drawdownThresholdPnl !== undefined) {
            thresholdLineRef.current = equity.createPriceLine({
                price: drawdownThresholdPnl,
                color: "#f85149",
                lineWidth: 1,
                lineStyle: LineStyle.Dashed,
                axisLabelVisible: true,
                title: "DD stop",
            });
        }
    }, [drawdownThresholdPnl]);

    const clearSnapshots = useCallback(() => {
        const equity = equityRef.current;
        if (!equity) return;
        for (const snap of snapshotsRef.current) {
            equity.removePriceLine(snap.priceLine);
            snap.divEl.remove();
        }
        snapshotsRef.current = [];
        setHasSnapshots(false);
    }, []);

    return (
        <div style={{ position: "relative" }}>
            <div
                style={{
                    position: "absolute",
                    top: 6,
                    right: 6,
                    zIndex: 10,
                    display: "flex",
                    gap: 8,
                    alignItems: "center",
                }}
            >
                <label
                    style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                        fontSize: 11,
                        color: "#98a6b8",
                        cursor: "pointer",
                        background: "rgba(22,27,34,0.85)",
                        border: "1px solid #30363d",
                        borderRadius: 6,
                        padding: "2px 8px",
                    }}
                >
                    <input
                        type="checkbox"
                        checked={showDrawdown}
                        onChange={(e) => setShowDrawdown(e.target.checked)}
                        style={{ accentColor: "#f85149", cursor: "pointer" }}
                    />
                    Drawdown
                </label>
                {hasSnapshots && (
                    <button
                        onClick={clearSnapshots}
                        style={{
                            padding: "2px 10px",
                            fontSize: 11,
                            background: "rgba(22,27,34,0.85)",
                            color: "#98a6b8",
                            border: "1px solid #30363d",
                            borderRadius: 6,
                            cursor: "pointer",
                        }}
                    >
                        Clear snapshots
                    </button>
                )}
            </div>
            <div ref={containerRef} className="analytics-chart-canvas" />
            <div
                ref={overlayRef}
                style={{
                    position: "absolute",
                    inset: 0,
                    pointerEvents: "none",
                    overflow: "hidden",
                }}
            />
        </div>
    );
}
