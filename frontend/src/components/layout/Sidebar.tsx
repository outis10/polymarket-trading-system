import { useSettingsStore } from "../../stores/useSettingsStore";
import { useEventsStore } from "../../stores/useEventsStore";
import { useState } from "react";
import { apiFetch } from "../../auth/apiFetch";
import { inferTicker } from "../../utils/ticker";

interface SidebarProps {
    send: (msg: Record<string, unknown>) => void;
}

export default function Sidebar({ send }: SidebarProps) {
    const sidebarOpen = useSettingsStore((s) => s.sidebarOpen);
    const setSidebarOpen = useSettingsStore((s) => s.setSidebarOpen);
    const settings = useEventsStore((s) => s.settings);
    const events = useEventsStore((s) => s.events);
    const updateSettings = useEventsStore((s) => s.updateSettings);
    const [refreshingLiveEvents, setRefreshingLiveEvents] = useState(false);
    const [refreshLiveMessage, setRefreshLiveMessage] = useState("");
    const [blockedHoursRaw, setBlockedHoursRaw] = useState<string | null>(null);
    const [enabledSlotsRaw, setEnabledSlotsRaw] = useState<string | null>(null);
    const [disabledTickerSidesRaw, setDisabledTickerSidesRaw] = useState<string | null>(null);

    const handleModeChange = (mode: string) => {
        send({ type: "switch_mode", mode });
    };

    const handleChartOptionToggle = (option: string) => {
        const current = settings.chart_options || [];
        const updated = current.includes(option)
            ? current.filter((o) => o !== option)
            : [...current, option];
        updateSettings({ chart_options: updated });
        send({ type: "update_settings", settings: { chart_options: updated } });
    };

    const handleProbabilitiesCardToggle = () => {
        const current = settings.chart_options || [];
        const hideKey = "hide_probabilities_card";
        const updated = current.includes(hideKey)
            ? current.filter((o) => o !== hideKey)
            : [...current, hideKey];
        updateSettings({ chart_options: updated });
        send({ type: "update_settings", settings: { chart_options: updated } });
    };

    const handleRangeHistogramCardToggle = () => {
        const current = settings.chart_options || [];
        const hideKey = "hide_range_histogram_card";
        const updated = current.includes(hideKey)
            ? current.filter((o) => o !== hideKey)
            : [...current, hideKey];
        updateSettings({ chart_options: updated });
        send({ type: "update_settings", settings: { chart_options: updated } });
    };

    const handleOrderBookCardToggle = () => {
        const current = settings.chart_options || [];
        const hideKey = "hide_order_book_card";
        const updated = current.includes(hideKey)
            ? current.filter((o) => o !== hideKey)
            : [...current, hideKey];
        updateSettings({ chart_options: updated });
        send({ type: "update_settings", settings: { chart_options: updated } });
    };

    const handlePositionsCardToggle = () => {
        const current = settings.chart_options || [];
        const hideKey = "hide_positions_card";
        const updated = current.includes(hideKey)
            ? current.filter((o) => o !== hideKey)
            : [...current, hideKey];
        updateSettings({ chart_options: updated });
        send({ type: "update_settings", settings: { chart_options: updated } });
    };

    const handleRefreshRateChange = (rate: number) => {
        send({ type: "update_settings", settings: { refresh_rate: rate } });
    };

    const handleTimeframeChange = (timeframe: "5m" | "15m" | "1h") => {
        send({
            type: "update_settings",
            settings: { timeframe_filter: timeframe },
        });
    };

    const handleTradingModeChange = (modeValue: "manual" | "bot") => {
        send({
            type: "update_settings",
            settings: { trading_mode: modeValue },
        });
    };

    const handleKellySettingChange = (partial: Record<string, unknown>) => {
        updateSettings(partial);
        send({ type: "update_settings", settings: partial });
    };
    const monitoredTickers = settings.monitored_tickers || [
        "BTC",
        "ETH",
        "SOL",
        "XRP",
    ];
    const tickerOptions = Array.from(
        new Set(
            Object.entries(events).map(([eventId, event]) =>
                inferTicker(eventId, event),
            ),
        ),
    )
        .filter((t) => t !== "OTHER")
        .sort((a, b) => a.localeCompare(b));
    const visibleTickerOptions =
        tickerOptions.length > 0 ? tickerOptions : ["BTC", "ETH", "SOL", "XRP"];
    const handleTickerToggle = (ticker: string) => {
        const next = monitoredTickers.includes(ticker)
            ? monitoredTickers.filter((t) => t !== ticker)
            : [...monitoredTickers, ticker];
        handleKellySettingChange({ monitored_tickers: next });
    };

    const handleRefreshLiveEvents = async () => {
        setRefreshingLiveEvents(true);
        setRefreshLiveMessage("");
        try {
            const res = await apiFetch("/api/events/refresh-live", {
                method: "POST",
            });
            let data: Record<string, unknown> = {};
            try {
                data = await res.json();
            } catch {
                data = {};
            }
            if (!res.ok) {
                const detail =
                    (typeof data.detail === "string" && data.detail) ||
                    `Live refresh failed (${res.status})`;
                setRefreshLiveMessage(detail);
                return;
            }
            setRefreshLiveMessage(
                `Live refreshed: ${String(data.events_count ?? 0)} events (${String(data.added ?? 0)} added, ${String(data.removed ?? 0)} removed)`,
            );
        } catch (e) {
            setRefreshLiveMessage("Network error during live refresh");
        } finally {
            setRefreshingLiveEvents(false);
        }
    };

    const handleSaveSettings = async () => {
        const { mode, ...persistable } = settings;
        try {
            const res = await apiFetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ settings: persistable }),
            });
            if (!res.ok) {
                throw new Error(`save failed ${res.status}`);
            }
            setRefreshLiveMessage("Settings saved");
        } catch {
            // Fallback to WS path if REST save is unavailable.
            send({ type: "update_settings", settings: persistable });
            setRefreshLiveMessage(
                "Settings sent via WebSocket (REST save unavailable)",
            );
        }
    };

    return (
        <>
            {sidebarOpen && (
                <div
                    className="sidebar-overlay"
                    onClick={() => setSidebarOpen(false)}
                />
            )}
            <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
                <div className="sidebar-header">
                    <span className="sidebar-title">Settings</span>
                    <button
                        className="sidebar-close"
                        onClick={() => setSidebarOpen(false)}
                    >
                        &times;
                    </button>
                </div>

                <div className="sidebar-section">
                    <div className="sidebar-section-title">Mode</div>
                    <label className="mode-option">
                        <input
                            type="radio"
                            name="mode"
                            checked={settings.mode === "demo"}
                            onChange={() => handleModeChange("demo")}
                        />
                        Demo
                    </label>
                    <label className="mode-option">
                        <input
                            type="radio"
                            name="mode"
                            checked={settings.mode === "live"}
                            onChange={() => handleModeChange("live")}
                        />
                        Live
                    </label>
                    <div style={{ marginTop: 8, fontSize: 13 }}>
                        <span
                            className={`status-dot ${settings.mode === "demo" ? "status-demo" : "status-live"}`}
                        />
                        {settings.mode === "demo"
                            ? "Demo Mode"
                            : "Connected to Polymarket"}
                    </div>
                </div>

                <hr className="sidebar-divider" />

                <div className="sidebar-section">
                    <div className="sidebar-section-title">Refresh Rate</div>
                    <input
                        type="range"
                        min={1}
                        max={30}
                        value={settings.refresh_rate}
                        onChange={(e) =>
                            handleRefreshRateChange(Number(e.target.value))
                        }
                        style={{ width: "100%" }}
                    />
                    <div
                        style={{ fontSize: 12, color: "#8b949e", marginTop: 4 }}
                    >
                        {settings.refresh_rate}s
                    </div>
                </div>

                <hr className="sidebar-divider" />

                <div className="sidebar-section">
                    <div className="sidebar-section-title">Timeframe</div>
                    <label className="mode-option">
                        <input
                            type="radio"
                            name="timeframe"
                            checked={
                                (settings.timeframe_filter || "5m") === "5m"
                            }
                            onChange={() => handleTimeframeChange("5m")}
                        />
                        5m
                    </label>
                    <label className="mode-option">
                        <input
                            type="radio"
                            name="timeframe"
                            checked={
                                (settings.timeframe_filter || "5m") === "15m"
                            }
                            onChange={() => handleTimeframeChange("15m")}
                        />
                        15m
                    </label>
                    <label className="mode-option">
                        <input
                            type="radio"
                            name="timeframe"
                            checked={
                                (settings.timeframe_filter || "5m") === "1h"
                            }
                            onChange={() => handleTimeframeChange("1h")}
                        />
                        1h
                    </label>
                </div>

                <hr className="sidebar-divider" />

                <div className="sidebar-section">
                    <div className="sidebar-section-title">Trading Mode</div>
                    <div className="trading-mode-slider">
                        <span
                            className={`trading-mode-label ${(settings.trading_mode || "manual") === "manual" ? "trading-mode-label-active" : ""}`}
                        >
                            Manual
                        </span>
                        <input
                            type="range"
                            min={0}
                            max={1}
                            step={1}
                            value={
                                (settings.trading_mode || "manual") === "bot"
                                    ? 1
                                    : 0
                            }
                            onChange={(e) =>
                                handleTradingModeChange(
                                    Number(e.target.value) === 1
                                        ? "bot"
                                        : "manual",
                                )
                            }
                            className="trading-mode-range"
                        />
                        <span
                            className={`trading-mode-label ${(settings.trading_mode || "manual") === "bot" ? "trading-mode-label-active" : ""}`}
                        >
                            Bot
                        </span>
                    </div>
                </div>

                <hr className="sidebar-divider" />

                <div className="sidebar-section">
                    <div className="sidebar-section-title">Chart Options</div>
                    <label className="chart-option">
                        <input
                            type="checkbox"
                            checked={
                                settings.chart_options?.includes(
                                    "show_chart",
                                ) ?? true
                            }
                            onChange={() =>
                                handleChartOptionToggle("show_chart")
                            }
                        />
                        Show Chart
                    </label>
                    <label className="chart-option">
                        <input
                            type="checkbox"
                            checked={
                                !(
                                    settings.chart_options?.includes(
                                        "hide_probabilities_card",
                                    ) ?? false
                                )
                            }
                            onChange={handleProbabilitiesCardToggle}
                        />
                        Show Probabilities Card
                    </label>
                    <label className="chart-option">
                        <input
                            type="checkbox"
                            checked={
                                !(
                                    settings.chart_options?.includes(
                                        "hide_range_histogram_card",
                                    ) ?? false
                                )
                            }
                            onChange={handleRangeHistogramCardToggle}
                        />
                        Show Range Histogram Card
                    </label>
                    <label className="chart-option">
                        <input
                            type="checkbox"
                            checked={
                                !(
                                    settings.chart_options?.includes(
                                        "hide_order_book_card",
                                    ) ?? false
                                )
                            }
                            onChange={handleOrderBookCardToggle}
                        />
                        Show Order Book Card
                    </label>
                    <label className="chart-option">
                        <input
                            type="checkbox"
                            checked={
                                !(
                                    settings.chart_options?.includes(
                                        "hide_positions_card",
                                    ) ?? false
                                )
                            }
                            onChange={handlePositionsCardToggle}
                        />
                        Show Positions Card
                    </label>
                </div>

                <hr className="sidebar-divider" />

                <div className="sidebar-section">
                    <div className="sidebar-section-title">Kelly Settings</div>
                    <label className="chart-option">
                        <input
                            type="checkbox"
                            checked={settings.kelly_enabled ?? true}
                            onChange={(e) =>
                                handleKellySettingChange({
                                    kelly_enabled: e.target.checked,
                                })
                            }
                        />
                        Enable Kelly
                    </label>

                    <label className="field-label">
                        Live Manual Bankroll ($)
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={1}
                        step={1}
                        value={
                            settings.kelly_live_bankroll_usd ??
                            settings.kelly_bankroll ??
                            100
                        }
                        onChange={(e) =>
                            handleKellySettingChange({
                                kelly_live_bankroll_usd: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />

                    <label className="field-label">Paper Bankroll ($)</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={1}
                        step={1}
                        value={
                            settings.kelly_paper_bankroll_usd ??
                            settings.kelly_live_bankroll_usd ??
                            settings.kelly_bankroll ??
                            100
                        }
                        onChange={(e) =>
                            handleKellySettingChange({
                                kelly_paper_bankroll_usd: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />

                    <label
                        className="chart-option"
                        title="Si está activo, el bankroll paper se actualiza con el pnl simulado de cada trade resuelto."
                    >
                        <input
                            type="checkbox"
                            checked={settings.paper_compound_enabled ?? true}
                            onChange={(e) =>
                                handleKellySettingChange({
                                    paper_compound_enabled: e.target.checked,
                                })
                            }
                        />
                        Paper Compound Bankroll
                    </label>

                    <label className="field-label">
                        Paper Current Bankroll ($)
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        step={1}
                        value={
                            settings.paper_current_bankroll_usd ??
                            settings.kelly_paper_bankroll_usd ??
                            settings.kelly_live_bankroll_usd ??
                            settings.kelly_bankroll ??
                            100
                        }
                        onChange={(e) =>
                            handleKellySettingChange({
                                paper_current_bankroll_usd: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />

                    <label className="field-label">Kelly Fraction</label>
                    <input
                        type="range"
                        min={0.05}
                        max={1}
                        step={0.05}
                        value={settings.kelly_fraction ?? 0.25}
                        onChange={(e) =>
                            handleKellySettingChange({
                                kelly_fraction: Number(e.target.value),
                            })
                        }
                        style={{ width: "100%" }}
                    />
                    <div className="field-hint">
                        {(settings.kelly_fraction ?? 0.25).toFixed(2)}x
                    </div>

                    <label className="field-label">Min Edge (%)</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        max={100}
                        step={0.1}
                        value={settings.kelly_min_edge_pct ?? 0.5}
                        onChange={(e) =>
                            handleKellySettingChange({
                                kelly_min_edge_pct: Number(e.target.value || 0),
                            })
                        }
                    />

                    <label className="field-label">Max Bet (%)</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        max={100}
                        step={0.5}
                        value={settings.kelly_max_bet_pct ?? 25}
                        onChange={(e) =>
                            handleKellySettingChange({
                                kelly_max_bet_pct: Number(e.target.value || 0),
                            })
                        }
                    />

                    <label className="field-label">
                        Max Event Exposure (%)
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        max={100}
                        step={0.5}
                        value={settings.kelly_max_event_exposure_pct ?? 25}
                        onChange={(e) =>
                            handleKellySettingChange({
                                kelly_max_event_exposure_pct: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />
                </div>

                <hr className="sidebar-divider" />

                <div className="sidebar-section">
                    <div className="sidebar-section-title">
                        Bot Risk Guardrails
                    </div>
                    <label className="chart-option">
                        <input
                            type="checkbox"
                            checked={settings.bot_risk_enabled ?? true}
                            onChange={(e) =>
                                handleKellySettingChange({
                                    bot_risk_enabled: e.target.checked,
                                })
                            }
                        />
                        Enable Risk Guards
                    </label>

                    <label
                        className="chart-option"
                        title="Si está activo, el bot solo ejecuta órdenes en eventos del timeframe seleccionado (5m, 15m, 1h)."
                    >
                        <input
                            type="checkbox"
                            checked={
                                settings.bot_enforce_timeframe_filter ?? true
                            }
                            onChange={(e) =>
                                handleKellySettingChange({
                                    bot_enforce_timeframe_filter:
                                        e.target.checked,
                                })
                            }
                        />
                        Enforce Timeframe Filter (Bot)
                    </label>

                    <label
                        className="chart-option"
                        title="Paper mode: el bot no manda orden real; solo registra decision, outcome y pnl simulado en paper_trades.csv."
                    >
                        <input
                            type="checkbox"
                            checked={settings.bot_paper_mode ?? false}
                            onChange={(e) =>
                                handleKellySettingChange({
                                    bot_paper_mode: e.target.checked,
                                })
                            }
                        />
                        Paper Mode (No Real Orders)
                    </label>

                    <label
                        className="chart-option"
                        title="Permite una sola segunda entrada por evento, solo del lado contrario al primero. Usa ask max y edge mínimo propios."
                    >
                        <input
                            type="checkbox"
                            checked={
                                settings.bot_second_entry_opposite_enabled ??
                                false
                            }
                            onChange={(e) =>
                                handleKellySettingChange({
                                    bot_second_entry_opposite_enabled:
                                        e.target.checked,
                                })
                            }
                        />
                        Enable 2nd Entry Opposite
                    </label>

                    <label
                        className="field-label"
                        title="Para la segunda entrada contraria, solo permite operar si el ask real del libro es menor o igual a este valor. 0 = off."
                    >
                        2nd Entry Max Ask
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        max={0.99}
                        step={0.01}
                        value={settings.bot_second_entry_max_ask_price ?? 0}
                        onChange={(e) =>
                            handleKellySettingChange({
                                bot_second_entry_max_ask_price: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />

                    <label
                        className="field-label"
                        title="Para la segunda entrada contraria, edge mínimo requerido contra ask."
                    >
                        2nd Entry Min Edge (%)
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        step={0.1}
                        value={settings.bot_second_entry_min_edge_pct ?? 5}
                        onChange={(e) =>
                            handleKellySettingChange({
                                bot_second_entry_min_edge_pct: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />

                    <label
                        className="field-label"
                        title="Bloquea compras cuando quedan menos de N segundos para que termine el evento. 0 = desactivado."
                    >
                        Min Seconds Before End
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        step={5}
                        value={settings.bot_min_seconds_before_end ?? 30}
                        onChange={(e) =>
                            handleKellySettingChange({
                                bot_min_seconds_before_end: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />

                    <label className="field-label">
                        Max Buys / Event (day)
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        step={1}
                        value={settings.bot_max_buys_per_event_side ?? 1}
                        onChange={(e) =>
                            handleKellySettingChange({
                                bot_max_buys_per_event_side: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />

                    <label className="field-label">Cooldown Event (s)</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        step={1}
                        value={
                            settings.bot_cooldown_seconds_per_event_side ?? 60
                        }
                        onChange={(e) =>
                            handleKellySettingChange({
                                bot_cooldown_seconds_per_event_side: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />

                    <label className="field-label">
                        Global Min Gap Orders (s)
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        step={1}
                        value={
                            settings.bot_global_min_seconds_between_orders ?? 2
                        }
                        onChange={(e) =>
                            handleKellySettingChange({
                                bot_global_min_seconds_between_orders: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />

                    <label className="field-label">
                        Max Event Exposure (% bankroll)
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        max={100}
                        step={0.5}
                        value={settings.bot_max_event_exposure_pct ?? 15}
                        onChange={(e) =>
                            handleKellySettingChange({
                                bot_max_event_exposure_pct: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />

                    <label className="field-label">
                        Drawdown Circuit Breaker
                    </label>
                    <label className="toggle-label">
                        <input
                            type="checkbox"
                            checked={settings.bot_drawdown_enabled ?? true}
                            onChange={(e) =>
                                handleKellySettingChange({
                                    bot_drawdown_enabled: e.target.checked,
                                })
                            }
                        />
                        Enabled
                    </label>
                    <label className="field-label">
                        Drawdown Stop (% of start bankroll)
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={1}
                        max={100}
                        step={1}
                        value={settings.bot_drawdown_stop_pct ?? 50}
                        onChange={(e) =>
                            handleKellySettingChange({
                                bot_drawdown_stop_pct: Number(
                                    e.target.value || 50,
                                ),
                            })
                        }
                    />

                    <label className="field-label">
                        Max Order Notional USD (legacy/no ladder)
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        step={0.1}
                        value={settings.bot_order_notional_cap_usd ?? 5}
                        onChange={(e) =>
                            handleKellySettingChange({
                                bot_order_notional_cap_usd: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />

                    <label
                        className="field-label"
                        title="Bloquea combinaciones ticker+side para el bot. Formato: ETH:up,BTC:down. Vacío = sin bloqueo."
                    >
                        Disabled Ticker Sides{" "}
                        <span style={{ fontSize: "0.75em", opacity: 0.6 }}>
                            vacío=off
                        </span>
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="text"
                        placeholder="ej: ETH:up,BTC:down"
                        value={
                            disabledTickerSidesRaw ??
                            (settings.bot_disabled_ticker_sides ?? []).join(",")
                        }
                        onChange={(e) => setDisabledTickerSidesRaw(e.target.value)}
                        onBlur={(e) => {
                            const pairs = e.target.value
                                .split(",")
                                .map((s) => s.trim().toUpperCase())
                                .filter((s) =>
                                    /^(BTC|ETH|SOL|XRP):(UP|DOWN)$/.test(s),
                                );
                            handleKellySettingChange({
                                bot_disabled_ticker_sides: pairs,
                            });
                            setDisabledTickerSidesRaw(null);
                        }}
                    />

                    <label className="field-label">
                        Min Shares (Polymarket)
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        step={0.1}
                        value={settings.pm_min_shares ?? 5}
                        onChange={(e) =>
                            handleKellySettingChange({
                                pm_min_shares: Number(e.target.value || 0),
                            })
                        }
                    />

                    <label className="field-label">
                        Min Notional USD (Polymarket)
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        step={0.1}
                        value={settings.pm_min_notional_usd ?? 1}
                        onChange={(e) =>
                            handleKellySettingChange({
                                pm_min_notional_usd: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />
                </div>

                <hr className="sidebar-divider" />

                <div className="sidebar-section">
                    <div className="sidebar-section-title">
                        Monitored Tickers
                    </div>
                    {visibleTickerOptions.map((ticker) => (
                        <label className="chart-option" key={ticker}>
                            <input
                                type="checkbox"
                                checked={monitoredTickers.includes(ticker)}
                                onChange={() => handleTickerToggle(ticker)}
                            />
                            {ticker}
                        </label>
                    ))}
                </div>

                <hr className="sidebar-divider" />

                <div className="sidebar-section">
                    <div className="sidebar-section-title">Quant Buy Gate</div>
                    <label className="chart-option">
                        <input
                            type="checkbox"
                            checked={settings.quant_gate_enabled ?? true}
                            onChange={(e) =>
                                handleKellySettingChange({
                                    quant_gate_enabled: e.target.checked,
                                })
                            }
                        />
                        Enable Quant Gate
                    </label>

                    <label className="field-label">Min Sample (n)</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={1}
                        step={1}
                        value={settings.quant_gate_min_sample ?? 120}
                        onChange={(e) =>
                            handleKellySettingChange({
                                quant_gate_min_sample: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />

                    <label className="field-label">
                        Min Model Prob (% 0=off, 50=50%)
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        max={100}
                        step={1}
                        value={Math.round(
                            (settings.quant_gate_min_prob ?? 0) * 100,
                        )}
                        onChange={(e) =>
                            handleKellySettingChange({
                                quant_gate_min_prob:
                                    Number(e.target.value || 0) / 100,
                            })
                        }
                    />

                    <label className="field-label">
                        Max Ask Price{" "}
                        <span style={{ fontSize: "0.75em", opacity: 0.6 }}>
                            0=off
                        </span>
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        max={0.99}
                        step={0.05}
                        value={settings.quant_gate_max_ask_price ?? 0}
                        onChange={(e) =>
                            handleKellySettingChange({
                                quant_gate_max_ask_price: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />

                    <label
                        className="field-label"
                        title="Sample mínimo requerido cuando la señal es fuerte (prob ≥ threshold). Permite operar en bins extremos con pocos datos históricos pero señal consistente."
                    >
                        Strong Signal Min Sample
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={1}
                        step={1}
                        value={
                            settings.quant_gate_min_sample_strong_signal ?? 20
                        }
                        onChange={(e) =>
                            handleKellySettingChange({
                                quant_gate_min_sample_strong_signal: Number(
                                    e.target.value || 20,
                                ),
                            })
                        }
                    />

                    <label
                        className="field-label"
                        title="Prob mínima para considerar una señal 'fuerte' y aplicar el sample mínimo reducido."
                    >
                        Strong Signal Threshold (%)
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={50}
                        max={100}
                        step={1}
                        defaultValue={Math.round(
                            (settings.quant_gate_strong_signal_threshold ??
                                0.72) * 100,
                        )}
                        key={Math.round(
                            (settings.quant_gate_strong_signal_threshold ??
                                0.72) * 100,
                        )}
                        onBlur={(e) =>
                            handleKellySettingChange({
                                quant_gate_strong_signal_threshold:
                                    Number(e.target.value || 72) / 100,
                            })
                        }
                    />

                    <label
                        className="field-label"
                        title="Movimiento mínimo del precio actual vs price-to-beat, como porcentaje del PTB. 0 = desactivado. Se aplica en la ventana base (ni early ni late)."
                    >
                        Base Min Diff (%)
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        step={0.1}
                        value={settings.quant_gate_min_diff_pct ?? 0}
                        onChange={(e) =>
                            handleKellySettingChange({
                                quant_gate_min_diff_pct: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />

                    <label className="field-label">
                        Max Spread (%){" "}
                        <span style={{ fontSize: "0.75em", opacity: 0.6 }}>
                            0=off
                        </span>
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        max={100}
                        step={0.5}
                        value={
                            settings.quant_gate_max_spread_pct != null
                                ? +(
                                      settings.quant_gate_max_spread_pct * 100
                                  ).toFixed(1)
                                : 0
                        }
                        onChange={(e) =>
                            handleKellySettingChange({
                                quant_gate_max_spread_pct:
                                    Number(e.target.value || 0) / 100,
                            })
                        }
                    />

                    <label className="field-label">
                        Min Ask Price{" "}
                        <span style={{ fontSize: "0.75em", opacity: 0.6 }}>
                            0=off
                        </span>
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        max={0.99}
                        step={0.05}
                        value={settings.quant_gate_min_ask_price ?? 0}
                        onChange={(e) =>
                            handleKellySettingChange({
                                quant_gate_min_ask_price: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />

                    <label
                        className="field-label"
                        title="Horas PST en las que el bot NO opera (ej: 10,11,21,22). Vacío = sin bloqueo."
                    >
                        Blocked Hours PST{" "}
                        <span style={{ fontSize: "0.75em", opacity: 0.6 }}>
                            vacío=off
                        </span>
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="text"
                        placeholder="ej: 10,11,21,22"
                        value={
                            blockedHoursRaw ??
                            (settings.quant_gate_blocked_hours_pst ?? []).join(
                                ",",
                            )
                        }
                        onChange={(e) => setBlockedHoursRaw(e.target.value)}
                        onBlur={(e) => {
                            const hours = e.target.value
                                .split(",")
                                .map((s) => parseInt(s.trim(), 10))
                                .filter((n) => !isNaN(n) && n >= 0 && n <= 23);
                            handleKellySettingChange({
                                quant_gate_blocked_hours_pst: hours,
                            });
                            setBlockedHoursRaw(null);
                        }}
                    />

                    <label
                        className="field-label"
                        title="Slots habilitados para operar (1–30). Solo estos slots pasan el gate. Vacío = sin filtro."
                    >
                        Enabled Slots{" "}
                        <span style={{ fontSize: "0.75em", opacity: 0.6 }}>
                            vacío=todos
                        </span>
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="text"
                        placeholder="ej: 3,4,5,6"
                        value={
                            enabledSlotsRaw ??
                            (settings.quant_gate_enabled_slots ?? []).join(",")
                        }
                        onChange={(e) => setEnabledSlotsRaw(e.target.value)}
                        onBlur={(e) => {
                            const slots = e.target.value
                                .split(",")
                                .map((s) => parseInt(s.trim(), 10))
                                .filter((n) => !isNaN(n) && n >= 1 && n <= 30);
                            handleKellySettingChange({
                                quant_gate_enabled_slots: slots,
                            });
                            setEnabledSlotsRaw(null);
                        }}
                    />

                    <label className="field-label">Min Edge (%)</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        step={0.1}
                        value={settings.quant_gate_min_edge_pct ?? 4}
                        onChange={(e) =>
                            handleKellySettingChange({
                                quant_gate_min_edge_pct: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />

                    <label className="field-label">Min Price (c)</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        max={100}
                        step={0.5}
                        value={settings.quant_gate_min_price_c ?? 10}
                        onChange={(e) =>
                            handleKellySettingChange({
                                quant_gate_min_price_c: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />

                    <label className="field-label">Max Price (c)</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        max={100}
                        step={0.5}
                        value={settings.quant_gate_max_price_c ?? 90}
                        onChange={(e) =>
                            handleKellySettingChange({
                                quant_gate_max_price_c: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />

                    <label className="chart-option">
                        <input
                            type="checkbox"
                            checked={
                                settings.quant_gate_edge_vs_ask_enabled ?? false
                            }
                            onChange={(e) =>
                                handleKellySettingChange({
                                    quant_gate_edge_vs_ask_enabled:
                                        e.target.checked,
                                })
                            }
                        />
                        Enable Edge vs Ask Filter
                    </label>

                    <label className="field-label">Min Edge vs Ask (%)</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        step={0.1}
                        value={settings.quant_gate_min_edge_vs_ask_pct ?? 2}
                        onChange={(e) =>
                            handleKellySettingChange({
                                quant_gate_min_edge_vs_ask_pct: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />
                </div>

                <hr className="sidebar-divider" />

                <label className="chart-option">
                    <input
                        type="checkbox"
                        checked={settings.keyboard_shortcuts_enabled ?? false}
                        onChange={(e) => {
                            localStorage.setItem(
                                "keyboard_shortcuts_enabled",
                                String(e.target.checked),
                            );
                            handleKellySettingChange({
                                keyboard_shortcuts_enabled: e.target.checked,
                            });
                        }}
                    />
                    Enable Keyboard Shortcuts (Z=UP, X=DOWN)
                </label>

                <hr className="sidebar-divider" />

                <button className="refresh-btn" onClick={handleSaveSettings}>
                    Save Settings
                </button>
                <button
                    className="refresh-btn refresh-live-btn"
                    onClick={handleRefreshLiveEvents}
                    disabled={settings.mode !== "live" || refreshingLiveEvents}
                >
                    {refreshingLiveEvents
                        ? "Refreshing Live..."
                        : "Refresh Live Events"}
                </button>
                {refreshLiveMessage && (
                    <div className="last-update">{refreshLiveMessage}</div>
                )}
                <div className="last-update">
                    Last update: {new Date().toLocaleTimeString()}
                </div>
            </aside>
        </>
    );
}
