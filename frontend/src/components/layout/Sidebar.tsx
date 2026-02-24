import { useSettingsStore } from "../../stores/useSettingsStore";
import { useEventsStore } from "../../stores/useEventsStore";
import { useState } from "react";
import { apiFetch } from "../../auth/apiFetch";
import { inferTicker } from "../../utils/ticker";

interface SidebarProps {
    send: (msg: Record<string, unknown>) => void;
}

type QuantProfile = "conservative" | "balanced" | "aggressive" | "custom";

const QUANT_PRESETS = {
    conservative: {
        quant_gate_enabled: true,
        quant_gate_min_sample: 120,
        quant_gate_min_edge_pct: 4,
        quant_gate_min_price_c: 10,
        quant_gate_max_price_c: 90,
        quant_gate_use_percentile: true,
        quant_gate_percentile_low: 15,
        quant_gate_percentile_high: 85,
        quant_gate_edge_vs_ask_enabled: false,
        quant_gate_min_edge_vs_ask_pct: 2,
    },
    balanced: {
        quant_gate_enabled: true,
        quant_gate_min_sample: 80,
        quant_gate_min_edge_pct: 2.5,
        quant_gate_min_price_c: 8,
        quant_gate_max_price_c: 92,
        quant_gate_use_percentile: true,
        quant_gate_percentile_low: 20,
        quant_gate_percentile_high: 80,
        quant_gate_edge_vs_ask_enabled: false,
        quant_gate_min_edge_vs_ask_pct: 2,
    },
    aggressive: {
        quant_gate_enabled: true,
        quant_gate_min_sample: 40,
        quant_gate_min_edge_pct: 1.5,
        quant_gate_min_price_c: 5,
        quant_gate_max_price_c: 95,
        quant_gate_use_percentile: false,
        quant_gate_percentile_low: 20,
        quant_gate_percentile_high: 80,
        quant_gate_edge_vs_ask_enabled: false,
        quant_gate_min_edge_vs_ask_pct: 2,
    },
} as const;

export default function Sidebar({ send }: SidebarProps) {
    const sidebarOpen = useSettingsStore((s) => s.sidebarOpen);
    const setSidebarOpen = useSettingsStore((s) => s.setSidebarOpen);
    const settings = useEventsStore((s) => s.settings);
    const events = useEventsStore((s) => s.events);
    const updateSettings = useEventsStore((s) => s.updateSettings);
    const [refreshingLiveEvents, setRefreshingLiveEvents] = useState(false);
    const [refreshLiveMessage, setRefreshLiveMessage] = useState("");

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
    const approxEqual = (a: number, b: number) => Math.abs(a - b) < 0.0001;
    const matchesPreset = (
        preset: (typeof QUANT_PRESETS)[keyof typeof QUANT_PRESETS],
    ) =>
        (settings.quant_gate_enabled ?? true) === preset.quant_gate_enabled &&
        (settings.quant_gate_use_percentile ?? true) ===
            preset.quant_gate_use_percentile &&
        approxEqual(
            settings.quant_gate_min_sample ?? 120,
            preset.quant_gate_min_sample,
        ) &&
        approxEqual(
            settings.quant_gate_min_edge_pct ?? 4,
            preset.quant_gate_min_edge_pct,
        ) &&
        approxEqual(
            settings.quant_gate_min_price_c ?? 10,
            preset.quant_gate_min_price_c,
        ) &&
        approxEqual(
            settings.quant_gate_max_price_c ?? 90,
            preset.quant_gate_max_price_c,
        ) &&
        approxEqual(
            settings.quant_gate_percentile_low ?? 15,
            preset.quant_gate_percentile_low,
        ) &&
        approxEqual(
            settings.quant_gate_percentile_high ?? 85,
            preset.quant_gate_percentile_high,
        ) &&
        (settings.quant_gate_edge_vs_ask_enabled ?? false) ===
            preset.quant_gate_edge_vs_ask_enabled &&
        approxEqual(
            settings.quant_gate_min_edge_vs_ask_pct ?? 2,
            preset.quant_gate_min_edge_vs_ask_pct,
        );
    const quantProfile: QuantProfile = matchesPreset(QUANT_PRESETS.conservative)
        ? "conservative"
        : matchesPreset(QUANT_PRESETS.balanced)
          ? "balanced"
          : matchesPreset(QUANT_PRESETS.aggressive)
            ? "aggressive"
            : "custom";
    const applyQuantProfile = (profile: Exclude<QuantProfile, "custom">) => {
        handleKellySettingChange(QUANT_PRESETS[profile]);
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

                    <label className="field-label">Bankroll ($)</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={1}
                        step={1}
                        value={settings.kelly_bankroll ?? 100}
                        onChange={(e) =>
                            handleKellySettingChange({
                                kelly_bankroll: Number(e.target.value || 0),
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
                            checked={settings.bot_enforce_timeframe_filter ?? true}
                            onChange={(e) =>
                                handleKellySettingChange({
                                    bot_enforce_timeframe_filter: e.target.checked,
                                })
                            }
                        />
                        Enforce Timeframe Filter (Bot)
                    </label>

                    <label
                        className="chart-option"
                        title="Si está activo, bloquea comprar el lado contrario si ya compraste UP o DOWN en ese evento hoy."
                    >
                        <input
                            type="checkbox"
                            checked={settings.bot_block_opposite_side ?? true}
                            onChange={(e) =>
                                handleKellySettingChange({
                                    bot_block_opposite_side: e.target.checked,
                                })
                            }
                        />
                        Block Opposite Side (Bot)
                    </label>

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

                    <label className="field-label">
                        Cooldown Event (s)
                    </label>
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
                        Max Ticker Exposure (% bankroll)
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        max={100}
                        step={0.5}
                        value={settings.bot_max_ticker_exposure_pct ?? 25}
                        onChange={(e) =>
                            handleKellySettingChange({
                                bot_max_ticker_exposure_pct: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />

                    <label className="field-label">
                        Max Order Notional USD (cap)
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
                    <label className="mode-option">
                        <input
                            type="radio"
                            name="quant-profile"
                            checked={quantProfile === "conservative"}
                            onChange={() => applyQuantProfile("conservative")}
                        />
                        Conservative
                    </label>
                    <label className="mode-option">
                        <input
                            type="radio"
                            name="quant-profile"
                            checked={quantProfile === "balanced"}
                            onChange={() => applyQuantProfile("balanced")}
                        />
                        Balanced
                    </label>
                    <label className="mode-option">
                        <input
                            type="radio"
                            name="quant-profile"
                            checked={quantProfile === "aggressive"}
                            onChange={() => applyQuantProfile("aggressive")}
                        />
                        Aggressive
                    </label>
                    {quantProfile === "custom" && (
                        <div className="field-hint">
                            Current profile: Custom (edited manually)
                        </div>
                    )}

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
                        Min Prob (% 0=off, 50=50%)
                    </label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        max={100}
                        step={1}
                        defaultValue={Math.round(
                            (settings.quant_gate_min_prob ?? 0) * 100,
                        )}
                        key={Math.round((settings.quant_gate_min_prob ?? 0) * 100)}
                        onBlur={(e) =>
                            handleKellySettingChange({
                                quant_gate_min_prob:
                                    Number(e.target.value || 0) / 100,
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
                        value={settings.quant_gate_min_sample_strong_signal ?? 20}
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
                            (settings.quant_gate_strong_signal_threshold ?? 0.72) * 100,
                        )}
                        key={Math.round((settings.quant_gate_strong_signal_threshold ?? 0.72) * 100)}
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
                                quant_gate_min_diff_pct: Number(e.target.value || 0),
                            })
                        }
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
                            checked={settings.quant_gate_use_percentile ?? true}
                            onChange={(e) =>
                                handleKellySettingChange({
                                    quant_gate_use_percentile: e.target.checked,
                                })
                            }
                        />
                        Use Percentile Filter
                    </label>

                    <label className="field-label">Percentile Low</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        max={100}
                        step={1}
                        value={settings.quant_gate_percentile_low ?? 15}
                        onChange={(e) =>
                            handleKellySettingChange({
                                quant_gate_percentile_low: Number(
                                    e.target.value || 0,
                                ),
                            })
                        }
                    />

                    <label className="field-label">Percentile High</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        max={100}
                        step={1}
                        value={settings.quant_gate_percentile_high ?? 85}
                        onChange={(e) =>
                            handleKellySettingChange({
                                quant_gate_percentile_high: Number(
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

                    <hr className="sidebar-divider" />
                    <div className="field-hint">Early Window Override</div>
                    <label className="chart-option">
                        <input
                            type="checkbox"
                            checked={settings.early_window_enabled ?? true}
                            onChange={(e) =>
                                handleKellySettingChange({
                                    early_window_enabled: e.target.checked,
                                })
                            }
                        />
                        Enable Early Window
                    </label>
                    <label className="field-label" title="Segundo desde inicio del evento donde comienza la ventana Early. Antes de este segundo el gate se bloquea.">Early Start (s)</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        step={1}
                        value={settings.early_window_start ?? 20}
                        onChange={(e) =>
                            handleKellySettingChange({
                                early_window_start: Number(e.target.value || 0),
                            })
                        }
                    />
                    <label className="field-label" title="Segundo desde inicio del evento donde termina la ventana Early.">Early End (s)</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        step={1}
                        value={settings.early_window_end ?? 120}
                        onChange={(e) =>
                            handleKellySettingChange({
                                early_window_end: Number(e.target.value || 0),
                            })
                        }
                    />
                    <label className="field-label">Early Min Sample (n)</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={1}
                        step={1}
                        value={settings.early_quant_gate_min_sample ?? 90}
                        onChange={(e) =>
                            handleKellySettingChange({
                                early_quant_gate_min_sample: Number(e.target.value || 0),
                            })
                        }
                    />
                    <label className="field-label">Early Min Edge (%)</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        step={0.1}
                        value={settings.early_quant_gate_min_edge_pct ?? 4}
                        onChange={(e) =>
                            handleKellySettingChange({
                                early_quant_gate_min_edge_pct: Number(e.target.value || 0),
                            })
                        }
                    />
                    <label className="field-label" title="Diferencia mínima |precio - PTB| / PTB en %. 0 = desactivado.">Early Min Diff (%)</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        step={0.01}
                        value={settings.early_quant_gate_min_diff_pct ?? 0}
                        onChange={(e) =>
                            handleKellySettingChange({
                                early_quant_gate_min_diff_pct: Number(e.target.value || 0),
                            })
                        }
                    />

                    <hr className="sidebar-divider" />
                    <div className="field-hint">Late Window Override</div>
                    <label className="chart-option">
                        <input
                            type="checkbox"
                            checked={settings.late_window_enabled ?? true}
                            onChange={(e) =>
                                handleKellySettingChange({
                                    late_window_enabled: e.target.checked,
                                })
                            }
                        />
                        Enable Late Window
                    </label>
                    <label className="field-label" title="Segundo desde inicio del evento donde comienza la ventana Late.">Late Start (s)</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        step={1}
                        value={settings.late_window_start ?? 180}
                        onChange={(e) =>
                            handleKellySettingChange({
                                late_window_start: Number(e.target.value || 0),
                            })
                        }
                    />
                    <label className="field-label" title="Segundo desde inicio del evento donde termina la ventana Late. Después de este segundo el gate se bloquea.">Late End (s)</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        step={1}
                        value={settings.late_window_end ?? 280}
                        onChange={(e) =>
                            handleKellySettingChange({
                                late_window_end: Number(e.target.value || 0),
                            })
                        }
                    />
                    <label className="field-label">Late Min Sample (n)</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={1}
                        step={1}
                        value={settings.late_quant_gate_min_sample ?? 70}
                        onChange={(e) =>
                            handleKellySettingChange({
                                late_quant_gate_min_sample: Number(e.target.value || 0),
                            })
                        }
                    />
                    <label className="field-label">Late Min Edge (%)</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        step={0.1}
                        value={settings.late_quant_gate_min_edge_pct ?? 3}
                        onChange={(e) =>
                            handleKellySettingChange({
                                late_quant_gate_min_edge_pct: Number(e.target.value || 0),
                            })
                        }
                    />
                    <label className="field-label" title="Diferencia mínima |precio - PTB| / PTB en %. 0 = desactivado.">Late Min Diff (%)</label>
                    <input
                        className="sidebar-number-input"
                        type="number"
                        min={0}
                        step={0.01}
                        value={settings.late_quant_gate_min_diff_pct ?? 0}
                        onChange={(e) =>
                            handleKellySettingChange({
                                late_quant_gate_min_diff_pct: Number(e.target.value || 0),
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
