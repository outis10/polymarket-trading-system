export interface OrderBookLevel {
    price: number;
    shares: number;
    total: number;
}

export interface OrderBookData {
    bids: OrderBookLevel[];
    asks: OrderBookLevel[];
    last_price: number;
    spread: number;
    volume: number;
}

export interface PriceHistoryPoint {
    timestamp: string;
    price: number;
    yes_price: number;
    no_price: number;
    percent_change: number;
    price_to_beat: number;
}

export interface EventData {
    name: string;
    description: string;
    icon: string;
    price_history: PriceHistoryPoint[];
    yes_price: number;
    no_price: number;
    current_price: number;
    price_to_beat: number;
    price_to_beat_source?: string | null;
    last_update: string;
    price_change: number;
    volume_24h: number;
    condition_id: string;
    chainlink_symbol?: string;
    yes_token_id: string;
    no_token_id: string;
    order_book_yes: OrderBookData | null;
    order_book_no: OrderBookData | null;
    event_start_utc?: string | null;
    event_end_utc: string | null;
    timeframe_minutes?: number;
    timeframe_label?: "5m" | "15m" | "1h";
    is_15m?: boolean;
    quant_prob_up?: number | null;
    quant_prob_down?: number | null;
    quant_sample_size?: number | null;
    quant_source?: string | null;
    quant_range_histogram?: QuantRangeHistogram | null;
    quant_buy_gate?: QuantBuyGate | null;
    _bot_last_order?: Record<string, unknown> | null;
    vol_rv_current?: number | null;
    vol_rv_avg?: number | null;
    vol_rv_pct_of_avg?: number | null;
    vol_noise_ratio?: number | null;
    vol_range_pct?: number | null;
    vol_gate_enabled?: boolean | null;
    vol_gate_blocked?: boolean | null;
    vol_gate_reason?: string | null;
    vol_gate_history_size?: number | null;
    vol_gate_avg_rv?: number | null;
    vol_gate_prev_rv?: number | null;
    vol_gate_threshold_rv?: number | null;
    vol_gate_prev_pct_of_avg?: number | null;
    vol_gate_min_pct_of_avg?: number | null;
}

export interface QuantRangeHistogramBin {
    inf_range: number;
    sup_range: number;
    prob_up: number;
    prob_down: number;
    count: number;
}

export interface QuantRangeHistogram {
    ticker: string;
    minute: number;
    slot?: number;
    slot_seconds?: number;
    bucket_type?: string;
    day_type?: string;
    time_frame?: string;
    current_diff: number;
    total_count: number;
    current_bin_index: number | null;
    current_percentile: number | null;
    bins: QuantRangeHistogramBin[];
}

export interface QuantBuyGateSide {
    enabled: boolean;
    reasons: string[];
    edge_pct: number | null;
    edge_vs_ask_pct?: number | null;
    sample_size: number | null;
    percentile: number | null;
    side: "up" | "down";
    window_profile?: "early" | "base" | "late" | string;
}

export interface QuantBuyGate {
    up: QuantBuyGateSide;
    down: QuantBuyGateSide;
}

export interface SettingsData {
    mode: string;
    refresh_rate: number;
    chart_options: string[];
    timeframe_filter?: "5m" | "15m" | "1h";
    trading_mode?: "manual" | "bot";
    kelly_enabled?: boolean;
    kelly_fraction?: number;
    kelly_bankroll?: number;
    kelly_live_bankroll_usd?: number;
    kelly_paper_bankroll_usd?: number;
    paper_compound_enabled?: boolean;
    paper_current_bankroll_usd?: number;
    live_equity_start_bankroll_usd?: number;
    live_equity_start_at_utc?: string;
    kelly_min_edge_pct?: number;
    kelly_max_bet_pct?: number;
    kelly_max_event_exposure_pct?: number;
    quant_gate_enabled?: boolean;
    quant_gate_min_sample?: number;
    quant_gate_min_sample_strong_signal?: number;
    quant_gate_strong_signal_threshold?: number;
    quant_gate_min_edge_pct?: number;
    quant_gate_min_diff_pct?: number;
    quant_gate_max_spread_pct?: number;
    quant_gate_min_ask_price?: number;
    quant_gate_max_ask_price?: number;
    quant_gate_min_price_c?: number;
    quant_gate_max_price_c?: number;
    quant_gate_edge_vs_ask_enabled?: boolean;
    quant_gate_min_edge_vs_ask_pct?: number;
    quant_gate_min_prob?: number;
    quant_gate_blocked_hours_pst?: number[];
    quant_gate_enabled_slots?: number[];
    vol_gate_enabled?: boolean;
    vol_gate_lookback_n?: number;
    vol_gate_min_pct_of_avg?: number;
    monitored_tickers?: string[];
    bot_risk_enabled?: boolean;
    bot_max_buys_per_event_side?: number;
    bot_cooldown_seconds_per_event_side?: number;
    bot_global_min_seconds_between_orders?: number;
    bot_max_event_exposure_pct?: number;
    bot_drawdown_enabled?: boolean;
    bot_drawdown_stop_pct?: number;
    bot_order_notional_cap_usd?: number;
    bot_paper_mode?: boolean;
    bot_second_entry_opposite_enabled?: boolean;
    bot_second_entry_max_ask_price?: number;
    bot_second_entry_min_edge_pct?: number;
    bot_trade_ladder?: Array<{
        min_ask?: number | { up?: number; down?: number };
        min_edge_pct?: number;
        stake_multiplier?: number;
        side_filter?: string;
    }>;
    pm_min_shares?: number;
    pm_min_notional_usd?: number;
    // Order book streaming controls
    order_book_max_levels?: number;
    order_book_min_broadcast_ms?: number;
    // Bot order controls
    bot_enforce_timeframe_filter?: boolean;
    bot_min_seconds_before_end?: number;
    take_profit_enabled?: boolean;
    take_profit_trigger_price?: number;
    take_profit_min_price?: number;
    keyboard_shortcuts_enabled?: boolean;
}

export interface WSMessage {
    type:
        | "full_snapshot"
        | "price_update"
        | "orderbook_update"
        | "quant_metrics_update"
        | "settings_update"
        | "balance_update"
        | "quant_reload"
        | "bot_order_placed";
    event_id: string;
    data: Record<string, unknown>;
}

export interface OrderRequest {
    event_id: string;
    side: "Buy" | "Sell";
    outcome: "up" | "down";
    order_type: "market" | "limit";
    price: number;
    shares: number;
}

export interface OrderResponse {
    order_id: string;
    status: string;
    message: string;
}

export interface Position {
    outcome: "Up" | "Down";
    qty: number;
    avg_price: number;
    current_price: number;
    cost: number;
    value: number;
    return_value: number;
    return_pct: number;
}
