import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "../../auth/apiFetch";
import { useSettingsStore } from "../../stores/useSettingsStore";
import { useEventsStore } from "../../stores/useEventsStore";
import { useAccountStore } from "../../stores/useAccountStore";

interface HeaderProps {
    route: "live" | "analytics" | "about";
    onNavigate: (route: "live" | "analytics" | "about") => void;
}

function toFiniteNumber(value: unknown): number | null {
    if (value === null || value === undefined || value === "") return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
}

export default function Header({ route, onNavigate }: HeaderProps) {
    const toggleSidebar = useSettingsStore((s) => s.toggleSidebar);
    const mode = useEventsStore((s) => s.settings.mode);
    const tradingMode = useEventsStore((s) => s.settings.trading_mode);
    const paperMode = useEventsStore((s) => s.settings.bot_paper_mode);
    const paperCurrentBankrollUsd = useEventsStore(
        (s) => s.settings.paper_current_bankroll_usd,
    );
    const bankrollReal = useAccountStore((s) => s.bankrollReal);
    const setBankrollReal = useAccountStore((s) => s.setBankrollReal);
    const [balanceText, setBalanceText] = useState("Bankroll: unavailable");
    const [refreshing, setRefreshing] = useState(false);
    const [claimableUsd, setClaimableUsd] = useState<number | null>(null);
    const [positionsValueUsd, setPositionsValueUsd] = useState<number | null>(null);

    const loadBalance = useCallback(async () => {
        try {
            const res = await apiFetch("/api/balance");
            const data = await res.json();
            const balance =
                toFiniteNumber(data?.balance) ??
                toFiniteNumber(data?.available) ??
                toFiniteNumber(data?.usdc) ??
                toFiniteNumber(data?.data?.balance);
            if (balance !== null) {
                setBankrollReal(balance);
            } else {
                setBankrollReal(null);
            }
        } catch {
            setBankrollReal(null);
        }
    }, [setBankrollReal]);

    const loadClaimable = useCallback(async () => {
        try {
            const res = await apiFetch("/api/claimable");
            const data = await res.json();
            const v = toFiniteNumber(data?.claimable_usd);
            setClaimableUsd(v !== null && v > 0 ? v : null);
        } catch {
            setClaimableUsd(null);
        }
    }, []);

    const loadPositionsValue = useCallback(async () => {
        try {
            const res = await apiFetch("/api/positions_value");
            const data = await res.json();
            const v = toFiniteNumber(data?.positions_value_usd);
            setPositionsValueUsd(v !== null && v > 0 ? v : null);
        } catch {
            setPositionsValueUsd(null);
        }
    }, []);

    const handleRefresh = useCallback(async () => {
        if (refreshing) return;
        setRefreshing(true);
        await Promise.all([loadBalance(), loadClaimable(), loadPositionsValue()]);
        setRefreshing(false);
    }, [refreshing, loadBalance, loadClaimable, loadPositionsValue]);

    useEffect(() => {
        let mounted = true;

        const load = async () => {
            try {
                const res = await apiFetch("/api/balance");
                const data = await res.json();
                if (!mounted) return;
                const balance =
                    toFiniteNumber(data?.balance) ??
                    toFiniteNumber(data?.available) ??
                    toFiniteNumber(data?.usdc) ??
                    toFiniteNumber(data?.data?.balance);
                if (balance !== null) {
                    setBankrollReal(balance);
                } else {
                    setBankrollReal(null);
                }
            } catch {
                if (mounted) setBankrollReal(null);
            }
        };

        load();
        // Defer claimable fetch so it doesn't block initial page render
        const claimableDelay = setTimeout(() => {
            if (mounted) loadClaimable();
        }, 3000);
        const positionsDelay = setTimeout(() => {
            if (mounted) loadPositionsValue();
        }, 5000);
        // Fallback reconciliation only: primary updates come from order fills / WS.
        const interval = setInterval(load, 90000);
        const claimableInterval = setInterval(loadClaimable, 300000);
        const positionsInterval = setInterval(loadPositionsValue, 120000);
        return () => {
            mounted = false;
            clearTimeout(claimableDelay);
            clearTimeout(positionsDelay);
            clearInterval(interval);
            clearInterval(claimableInterval);
            clearInterval(positionsInterval);
        };
    }, [mode, setBankrollReal, loadClaimable, loadPositionsValue]);

    useEffect(() => {
        if (bankrollReal !== null) {
            setBalanceText(
                `Bankroll: $${bankrollReal.toLocaleString("en-US", {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                })}`,
            );
            return;
        }
        setBalanceText(
            mode === "demo" ? "Bankroll: Demo" : "Bankroll: unavailable",
        );
    }, [bankrollReal, mode]);

    const portfolioUsd =
        bankrollReal !== null && positionsValueUsd !== null
            ? bankrollReal + positionsValueUsd + (claimableUsd ?? 0)
            : null;

    const showPaperBadge = tradingMode === "bot" && paperMode === true;
    const paperCurrentBankroll = toFiniteNumber(paperCurrentBankrollUsd);
    const paperBankrollText =
        paperCurrentBankroll !== null
            ? `Paper $${paperCurrentBankroll.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
              })}`
            : "Paper $N/A";

    return (
        <header className="app-header">
            <div className="app-header-left">
                <span className="app-header-title">Kalitron Edge</span>
                <span className="app-header-subtitle">
                    Quantitative Engine for Event Markets
                </span>
            </div>
            <div className="app-header-center">
                {portfolioUsd !== null && (
                    <span
                        className="portfolio-chip"
                        title="Portfolio = Bankroll + Positions Value + Claimable"
                    >
                        Portfolio: $
                        {portfolioUsd.toLocaleString("en-US", {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                        })}
                    </span>
                )}
                <span className="bankroll-chip">{balanceText}</span>
                {positionsValueUsd !== null && (
                    <span
                        className="positions-value-chip"
                        title="Current market value of open positions"
                    >
                        Pos: $
                        {positionsValueUsd.toLocaleString("en-US", {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                        })}
                    </span>
                )}
                {showPaperBadge && (
                    <span
                        className="paper-bankroll-chip"
                        title="Paper Current Bankroll ($)"
                    >
                        {paperBankrollText}
                    </span>
                )}
                {showPaperBadge && (
                    <span
                        className="paper-mode-chip"
                        title="Bot is running in paper mode (no real orders)"
                    >
                        PAPER MODE
                    </span>
                )}
                {claimableUsd !== null && (
                    <span
                        className="claimable-chip"
                        title="Redeemable from resolved markets"
                    >
                        +$
                        {claimableUsd.toLocaleString("en-US", {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                        })}{" "}
                        claimable
                    </span>
                )}
                <button
                    className={`bankroll-refresh-btn${refreshing ? " bankroll-refresh-btn--spinning" : ""}`}
                    onClick={handleRefresh}
                    disabled={refreshing}
                    title="Refresh balance & claimable"
                    aria-label="Refresh balance"
                >
                    ↻
                </button>
            </div>
            <div className="app-header-right">
                <button
                    className={`nav-btn ${route === "live" ? "nav-btn-active" : ""}`}
                    onClick={() => onNavigate("live")}
                >
                    <span
                        className="nav-btn-icon nav-icon-live"
                        aria-hidden="true"
                    >
                        <span className="nav-icon-live-dot" />
                    </span>
                    <span className="nav-btn-label">Live</span>
                </button>
                <button
                    className={`nav-btn ${route === "analytics" ? "nav-btn-active" : ""}`}
                    onClick={() => onNavigate("analytics")}
                >
                    <span
                        className="nav-btn-icon nav-icon-analytics"
                        aria-hidden="true"
                    >
                        <span className="nav-icon-bar nav-icon-bar-1" />
                        <span className="nav-icon-bar nav-icon-bar-2" />
                        <span className="nav-icon-bar nav-icon-bar-3" />
                    </span>
                    <span className="nav-btn-label">Analytics</span>
                </button>
                <button
                    className={`nav-btn ${route === "about" ? "nav-btn-active" : ""}`}
                    onClick={() => onNavigate("about")}
                >
                    <span className="nav-btn-label">About</span>
                </button>
                <button className="settings-btn" onClick={toggleSidebar}>
                    <span className="settings-btn-text">Settings</span>
                    <span className="settings-btn-gear" aria-hidden="true">
                        ⚙
                    </span>
                </button>
            </div>
        </header>
    );
}
