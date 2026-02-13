import { useSettingsStore } from "../../stores/useSettingsStore";
import { useEventsStore } from "../../stores/useEventsStore";

interface SidebarProps {
    send: (msg: Record<string, unknown>) => void;
}

export default function Sidebar({ send }: SidebarProps) {
    const sidebarOpen = useSettingsStore((s) => s.sidebarOpen);
    const setSidebarOpen = useSettingsStore((s) => s.setSidebarOpen);
    const settings = useEventsStore((s) => s.settings);

    const handleModeChange = (mode: string) => {
        send({ type: "switch_mode", mode });
    };

    const handleChartOptionToggle = (option: string) => {
        const current = settings.chart_options || [];
        const updated = current.includes(option)
            ? current.filter((o) => o !== option)
            : [...current, option];
        send({ type: "update_settings", settings: { chart_options: updated } });
    };

    const handleRefreshRateChange = (rate: number) => {
        send({ type: "update_settings", settings: { refresh_rate: rate } });
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
                                settings.chart_options?.includes(
                                    "show_probability",
                                ) ?? true
                            }
                            onChange={() =>
                                handleChartOptionToggle("show_probability")
                            }
                        />
                        Show Probability %
                    </label>
                    <label className="chart-option">
                        <input
                            type="checkbox"
                            checked={
                                settings.chart_options?.includes(
                                    "show_price_change",
                                ) ?? true
                            }
                            onChange={() =>
                                handleChartOptionToggle("show_price_change")
                            }
                        />
                        Show Price Change %
                    </label>
                </div>

                <hr className="sidebar-divider" />

                <button
                    className="refresh-btn"
                    onClick={() => send({ type: "refresh" })}
                >
                    Refresh Now
                </button>
                <div className="last-update">
                    Last update: {new Date().toLocaleTimeString()}
                </div>
            </aside>
        </>
    );
}
