import { useEffect, useState } from "react";
import { useSettingsStore } from "../../stores/useSettingsStore";
import { useEventsStore } from "../../stores/useEventsStore";

interface HeaderProps {
    route: "live" | "analytics";
    onNavigate: (route: "live" | "analytics") => void;
}

function toFiniteNumber(value: unknown): number | null {
    if (value === null || value === undefined || value === "") return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
}

export default function Header({ route, onNavigate }: HeaderProps) {
    const toggleSidebar = useSettingsStore((s) => s.toggleSidebar);
    const mode = useEventsStore((s) => s.settings.mode);
    const [balanceText, setBalanceText] = useState("Bankroll: --");

    useEffect(() => {
        let mounted = true;

        const loadBalance = async () => {
            try {
                const res = await fetch("/api/balance");
                const data = await res.json();
                if (!mounted) return;
                const balance =
                    toFiniteNumber(data?.balance) ??
                    toFiniteNumber(data?.available) ??
                    toFiniteNumber(data?.usdc) ??
                    toFiniteNumber(data?.data?.balance);
                if (balance !== null) {
                    setBalanceText(
                        `Bankroll: $${balance.toLocaleString("en-US", {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                        })}`,
                    );
                } else {
                    setBalanceText(
                        mode === "demo"
                            ? "Bankroll: Demo"
                            : "Bankroll: unavailable",
                    );
                }
            } catch {
                if (mounted) {
                    setBalanceText(
                        mode === "demo"
                            ? "Bankroll: Demo"
                            : "Bankroll: unavailable",
                    );
                }
            }
        };

        loadBalance();
        const interval = setInterval(loadBalance, 15000);
        return () => {
            mounted = false;
            clearInterval(interval);
        };
    }, [mode]);

    return (
        <header className="app-header">
            <div className="app-header-left">
                <span className="app-header-title">Polymarket Monitor</span>
                <span className="app-header-subtitle">
                    Real-time Prediction Markets
                </span>
            </div>
            <div className="app-header-right">
                <button
                    className={`nav-btn ${route === "live" ? "nav-btn-active" : ""}`}
                    onClick={() => onNavigate("live")}
                >
                    Live
                </button>
                <button
                    className={`nav-btn ${route === "analytics" ? "nav-btn-active" : ""}`}
                    onClick={() => onNavigate("analytics")}
                >
                    Analytics
                </button>
                <span className="bankroll-chip">{balanceText}</span>
                <button className="settings-btn" onClick={toggleSidebar}>
                    Settings
                </button>
            </div>
        </header>
    );
}
