#!/usr/bin/env python3
"""
Backtest GUI - Interactive interface for Polymarket backtesting

Run with: streamlit run backtest_gui.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import asyncio
from datetime import datetime, timedelta
import sys
import os

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest.config import BacktestConfig
from backtest.engine import BacktestEngine
from strategy.arbitrage import SimpleArbitrageStrategy
from strategy.momentum import MomentumStrategy


# Page config
st.set_page_config(
    page_title="Polymarket Backtest",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background-color: #1E1E1E;
        border-radius: 10px;
        padding: 15px;
        margin: 5px;
    }
    .positive { color: #00C853; }
    .negative { color: #FF5252; }
    .stMetric { background-color: #262730; border-radius: 5px; padding: 10px; }
</style>
""", unsafe_allow_html=True)


def create_equity_chart(equity_curve: pd.Series, title: str = "Equity Curve") -> go.Figure:
    """Create equity curve chart"""
    fig = go.Figure()

    # Equity line
    fig.add_trace(go.Scatter(
        x=equity_curve.index,
        y=equity_curve.values,
        mode='lines',
        name='Equity',
        line=dict(color='#00C853', width=2),
        fill='tozeroy',
        fillcolor='rgba(0, 200, 83, 0.1)'
    ))

    # Starting capital line
    initial = equity_curve.iloc[0] if len(equity_curve) > 0 else 10000
    fig.add_hline(y=initial, line_dash="dash", line_color="gray",
                  annotation_text=f"Initial: ${initial:,.0f}")

    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title="Equity ($)",
        template="plotly_dark",
        height=400,
        showlegend=False,
        hovermode='x unified'
    )

    return fig


def create_price_chart(price_data: pd.DataFrame) -> go.Figure:
    """Create price chart with candlesticks"""
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=price_data['timestamp'],
        open=price_data['open'],
        high=price_data['high'],
        low=price_data['low'],
        close=price_data['close'],
        name='SOL Price'
    ))

    fig.update_layout(
        title="SOL/USDT Price",
        xaxis_title="Time",
        yaxis_title="Price ($)",
        template="plotly_dark",
        height=350,
        xaxis_rangeslider_visible=False
    )

    return fig


def create_drawdown_chart(equity_curve: pd.Series) -> go.Figure:
    """Create drawdown chart"""
    # Calculate drawdown
    cummax = equity_curve.cummax()
    drawdown = (equity_curve - cummax) / cummax * 100

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=drawdown.index,
        y=drawdown.values,
        mode='lines',
        name='Drawdown',
        line=dict(color='#FF5252', width=2),
        fill='tozeroy',
        fillcolor='rgba(255, 82, 82, 0.3)'
    ))

    fig.update_layout(
        title="Drawdown",
        xaxis_title="Time",
        yaxis_title="Drawdown (%)",
        template="plotly_dark",
        height=250,
        showlegend=False
    )

    return fig


def create_trades_chart(trades_df: pd.DataFrame, equity_curve: pd.Series) -> go.Figure:
    """Create chart showing trades on equity curve"""
    fig = go.Figure()

    # Equity line
    fig.add_trace(go.Scatter(
        x=equity_curve.index,
        y=equity_curve.values,
        mode='lines',
        name='Equity',
        line=dict(color='#00C853', width=1.5)
    ))

    if not trades_df.empty:
        # Entry points
        entries = trades_df[['entry_time', 'entry_price']].dropna()
        if not entries.empty:
            fig.add_trace(go.Scatter(
                x=trades_df['entry_time'],
                y=[equity_curve.loc[equity_curve.index <= t].iloc[-1]
                   for t in trades_df['entry_time'] if t in equity_curve.index or True],
                mode='markers',
                name='Entry',
                marker=dict(color='#2196F3', size=10, symbol='triangle-up')
            ))

        # Exit points
        exits = trades_df[['exit_time', 'exit_price']].dropna()
        if not exits.empty:
            fig.add_trace(go.Scatter(
                x=trades_df['exit_time'],
                y=[equity_curve.loc[equity_curve.index <= t].iloc[-1]
                   for t in trades_df['exit_time'] if t is not None],
                mode='markers',
                name='Exit',
                marker=dict(color='#FF9800', size=10, symbol='triangle-down')
            ))

    fig.update_layout(
        title="Equity with Trade Markers",
        xaxis_title="Time",
        yaxis_title="Equity ($)",
        template="plotly_dark",
        height=350
    )

    return fig


def create_metrics_chart(metrics) -> go.Figure:
    """Create metrics comparison chart"""
    metrics_data = {
        'Metric': ['Sharpe', 'Sortino', 'Win Rate %', 'Profit Factor'],
        'Value': [
            metrics.sharpe_ratio,
            min(metrics.sortino_ratio, 5),  # Cap for display
            metrics.win_rate,
            min(metrics.profit_factor, 5)  # Cap for display
        ]
    }

    fig = px.bar(
        metrics_data,
        x='Metric',
        y='Value',
        color='Value',
        color_continuous_scale=['#FF5252', '#FFEB3B', '#00C853'],
        template='plotly_dark',
        height=250
    )

    fig.update_layout(
        title="Key Metrics",
        showlegend=False,
        coloraxis_showscale=False
    )

    return fig


async def run_backtest_async(config, strategy):
    """Run backtest asynchronously"""
    engine = BacktestEngine(strategy=strategy, config=config)
    return await engine.run()


def main():
    # Header
    st.title("📊 Polymarket Backtest GUI")
    st.markdown("*Backtest trading strategies on simulated Polymarket UpDown markets*")

    # Sidebar - Configuration
    st.sidebar.header("⚙️ Configuration")

    # Strategy selection
    st.sidebar.subheader("Strategy")
    strategy_type = st.sidebar.selectbox(
        "Select Strategy",
        ["Momentum", "Simple Arbitrage"],
        help="Choose which trading strategy to backtest"
    )

    # Date range
    st.sidebar.subheader("Time Period")

    col1, col2 = st.sidebar.columns(2)
    with col1:
        start_date = st.date_input(
            "Start Date",
            value=datetime(2026, 1, 10),
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2026, 1, 18)
        )
    with col2:
        end_date = st.date_input(
            "End Date",
            value=datetime(2026, 1, 17),
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2026, 1, 18)
        )

    # Market parameters
    st.sidebar.subheader("Market Simulation")

    symbol = st.sidebar.selectbox(
        "Symbol",
        ["SOLUSDT", "BTCUSDT", "ETHUSDT"],
        help="Cryptocurrency to simulate"
    )

    timeframe = st.sidebar.selectbox(
        "Timeframe",
        ["1m", "5m", "15m", "30m", "1h", "4h"],
        help="Data granularity (1m = 1 minute candles)"
    )

    updown_threshold = st.sidebar.slider(
        "UpDown Threshold (%)",
        min_value=1.0,
        max_value=10.0,
        value=5.0,
        step=0.5,
        help="Price change threshold for market resolution"
    )

    updown_duration = st.sidebar.slider(
        "Market Duration (min)",
        min_value=5,
        max_value=60,
        value=15,
        step=5,
        help="Duration of each simulated market"
    )

    # Capital & Risk
    st.sidebar.subheader("Capital & Risk")

    initial_capital = st.sidebar.number_input(
        "Initial Capital ($)",
        min_value=1000,
        max_value=100000,
        value=10000,
        step=1000
    )

    position_size = st.sidebar.number_input(
        "Position Size ($)",
        min_value=10,
        max_value=1000,
        value=100,
        step=10
    )

    stop_loss = st.sidebar.slider(
        "Stop Loss (%)",
        min_value=1.0,
        max_value=20.0,
        value=5.0,
        step=1.0
    )

    take_profit = st.sidebar.slider(
        "Take Profit (%)",
        min_value=5.0,
        max_value=50.0,
        value=15.0,
        step=5.0
    )

    # Strategy-specific parameters
    st.sidebar.subheader("Strategy Parameters")

    if strategy_type == "Momentum":
        min_confidence = st.sidebar.slider(
            "Min Confidence",
            min_value=0.3,
            max_value=0.9,
            value=0.5,
            step=0.1
        )
        price_threshold_buy = st.sidebar.slider(
            "Buy Threshold (YES price <)",
            min_value=0.2,
            max_value=0.5,
            value=0.35,
            step=0.05
        )
        price_threshold_sell = st.sidebar.slider(
            "Sell Threshold (YES price >)",
            min_value=0.5,
            max_value=0.8,
            value=0.65,
            step=0.05
        )
    else:
        min_spread = st.sidebar.slider(
            "Min Spread",
            min_value=0.01,
            max_value=0.10,
            value=0.02,
            step=0.01
        )
        max_spread = st.sidebar.slider(
            "Max Spread",
            min_value=0.05,
            max_value=0.20,
            value=0.10,
            step=0.01
        )

    # Run button
    st.sidebar.markdown("---")
    run_button = st.sidebar.button("🚀 Run Backtest", type="primary", use_container_width=True)

    # Main content area
    if run_button:
        # Validate dates
        if start_date >= end_date:
            st.error("Start date must be before end date!")
            return

        # Create config
        config = BacktestConfig(
            start_date=datetime.combine(start_date, datetime.min.time()),
            end_date=datetime.combine(end_date, datetime.min.time()),
            initial_capital=float(initial_capital),
            updown_threshold_pct=updown_threshold,
            updown_duration_minutes=updown_duration,
            data_source='binance',
            symbol=symbol,
            timeframe=timeframe,
            stop_loss_pct=stop_loss / 100,
            take_profit_pct=take_profit / 100,
        )

        # Create strategy
        if strategy_type == "Momentum":
            strategy = MomentumStrategy({
                'position_size': float(position_size),
                'min_confidence': min_confidence,
                'price_threshold_buy': price_threshold_buy,
                'price_threshold_sell': price_threshold_sell,
            })
        else:
            strategy = SimpleArbitrageStrategy({
                'min_spread': min_spread,
                'max_spread': max_spread,
                'position_size': float(position_size),
                'min_confidence': 0.6,
            })

        # Run backtest with progress
        with st.spinner("Running backtest... Fetching data from Binance..."):
            try:
                results = asyncio.run(run_backtest_async(config, strategy))
            except Exception as e:
                st.error(f"Error running backtest: {str(e)}")
                return

        st.success("Backtest completed!")

        # Store results in session state
        st.session_state['results'] = results
        st.session_state['config'] = config

    # Display results if available
    if 'results' in st.session_state:
        results = st.session_state['results']
        config = st.session_state['config']
        metrics = results.metrics

        # Summary metrics row
        st.markdown("### 📈 Performance Summary")

        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            color = "normal" if metrics.total_return >= 0 else "inverse"
            st.metric(
                "Total Return",
                f"{metrics.total_return:+.2f}%",
                delta=f"${metrics.total_pnl:+,.2f}",
                delta_color=color
            )

        with col2:
            st.metric(
                "Sharpe Ratio",
                f"{metrics.sharpe_ratio:.3f}",
                delta="Good" if metrics.sharpe_ratio > 1 else "Low"
            )

        with col3:
            st.metric(
                "Max Drawdown",
                f"{metrics.max_drawdown:.2f}%",
                delta=f"{metrics.max_drawdown_duration}d",
                delta_color="inverse"
            )

        with col4:
            st.metric(
                "Win Rate",
                f"{metrics.win_rate:.1f}%",
                delta=f"{metrics.winning_trades}/{metrics.total_trades} trades"
            )

        with col5:
            st.metric(
                "Profit Factor",
                f"{metrics.profit_factor:.2f}" if metrics.profit_factor < 100 else "∞",
                delta="Profitable" if metrics.profit_factor > 1 else "Loss"
            )

        # Charts row
        st.markdown("### 📊 Charts")

        tab1, tab2, tab3, tab4 = st.tabs(["Equity Curve", "Price Data", "Drawdown", "Trades"])

        with tab1:
            if not results.equity_curve.empty:
                fig = create_equity_chart(results.equity_curve)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("No equity data available")

        with tab2:
            if not results.price_data.empty:
                fig = create_price_chart(results.price_data)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("No price data available")

        with tab3:
            if not results.equity_curve.empty:
                fig = create_drawdown_chart(results.equity_curve)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("No drawdown data available")

        with tab4:
            trades_df = pd.DataFrame(results.get_trade_list()) if results.trades else pd.DataFrame()
            if not trades_df.empty:
                fig = create_trades_chart(trades_df, results.equity_curve)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No trades executed")

        # Detailed metrics
        st.markdown("### 📋 Detailed Metrics")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Returns**")
            returns_data = {
                "Metric": ["Total Return", "Annualized Return", "Initial Capital", "Final Capital", "Total P&L"],
                "Value": [
                    f"{metrics.total_return:+.2f}%",
                    f"{metrics.annualized_return:+.2f}%",
                    f"${metrics.initial_capital:,.2f}",
                    f"${metrics.final_capital:,.2f}",
                    f"${metrics.total_pnl:+,.2f}"
                ]
            }
            st.dataframe(pd.DataFrame(returns_data), hide_index=True, use_container_width=True)

            st.markdown("**Risk**")
            risk_data = {
                "Metric": ["Volatility (Ann.)", "Max Drawdown", "Drawdown Duration"],
                "Value": [
                    f"{metrics.volatility:.2f}%",
                    f"{metrics.max_drawdown:.2f}%",
                    f"{metrics.max_drawdown_duration} days"
                ]
            }
            st.dataframe(pd.DataFrame(risk_data), hide_index=True, use_container_width=True)

        with col2:
            st.markdown("**Trading Statistics**")
            trading_data = {
                "Metric": ["Total Trades", "Winning Trades", "Losing Trades", "Win Rate",
                          "Profit Factor", "Avg Win", "Avg Loss", "Largest Win", "Largest Loss"],
                "Value": [
                    str(metrics.total_trades),
                    str(metrics.winning_trades),
                    str(metrics.losing_trades),
                    f"{metrics.win_rate:.1f}%",
                    f"{metrics.profit_factor:.2f}" if metrics.profit_factor < 100 else "∞",
                    f"${metrics.avg_win:,.2f}",
                    f"${metrics.avg_loss:,.2f}",
                    f"${metrics.largest_win:+,.2f}",
                    f"${metrics.largest_loss:+,.2f}"
                ]
            }
            st.dataframe(pd.DataFrame(trading_data), hide_index=True, use_container_width=True)

        # Trade list
        if results.trades:
            st.markdown("### 📝 Trade History")
            trades_df = pd.DataFrame(results.get_trade_list())
            if not trades_df.empty:
                trades_df['pnl'] = trades_df['pnl'].apply(lambda x: f"${x:+,.2f}" if x else "N/A")
                trades_df['entry_price'] = trades_df['entry_price'].apply(lambda x: f"{x:.4f}")
                trades_df['exit_price'] = trades_df['exit_price'].apply(lambda x: f"{x:.4f}" if x else "N/A")
                st.dataframe(trades_df, hide_index=True, use_container_width=True)

        # Export options
        st.markdown("### 💾 Export Data")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Individual Files**")

            # Price data
            if not results.price_data.empty:
                csv = results.price_data.to_csv(index=False)
                st.download_button(
                    "📈 Price Data (CSV)",
                    csv,
                    file_name="price_data.csv",
                    mime="text/csv",
                    use_container_width=True
                )

            # Simulated market
            if results.simulated_market:
                market_df = pd.DataFrame(results.simulated_market)
                csv = market_df.to_csv(index=False)
                st.download_button(
                    "🎯 Simulated Market YES/NO (CSV)",
                    csv,
                    file_name="simulated_market.csv",
                    mime="text/csv",
                    use_container_width=True
                )

            # Equity curve
            if not results.equity_curve.empty:
                equity_df = pd.DataFrame({
                    'timestamp': results.equity_curve.index,
                    'equity': results.equity_curve.values
                })
                csv = equity_df.to_csv(index=False)
                st.download_button(
                    "💰 Equity Curve (CSV)",
                    csv,
                    file_name="equity_curve.csv",
                    mime="text/csv",
                    use_container_width=True
                )

        with col2:
            st.markdown("**Additional Data**")

            # Signals
            if results.signals:
                signals_df = pd.DataFrame(results.signals)
                csv = signals_df.to_csv(index=False)
                st.download_button(
                    "📊 All Signals (CSV)",
                    csv,
                    file_name="signals.csv",
                    mime="text/csv",
                    use_container_width=True
                )

            # Trades
            if results.trades:
                trades_df = pd.DataFrame(results.get_trade_list())
                csv = trades_df.to_csv(index=False)
                st.download_button(
                    "📝 Trades (CSV)",
                    csv,
                    file_name="trades.csv",
                    mime="text/csv",
                    use_container_width=True
                )

            # Summary JSON
            import json
            json_str = json.dumps(results.to_dict(), indent=2, default=str)
            st.download_button(
                "📄 Full Summary (JSON)",
                json_str,
                file_name="backtest_summary.json",
                mime="application/json",
                use_container_width=True
            )

    else:
        # Show instructions when no results
        st.markdown("""
        ### 🎯 How to Use

        1. **Configure your backtest** using the sidebar options:
           - Select a trading strategy
           - Choose date range (use historical dates like Dec 2024)
           - Set market simulation parameters
           - Adjust capital and risk settings

        2. **Click "Run Backtest"** to execute

        3. **Analyze results** through interactive charts and metrics

        ---

        ### 📖 Understanding the Market Simulation

        This backtester simulates **Polymarket UpDown markets** using historical crypto price data:

        - **UpDown Market**: "Will SOL go up/down X% in Y minutes?"
        - **YES Token**: Pays $1 if condition is met
        - **NO Token**: Pays $1 if condition is NOT met
        - **Prices**: Represent probability (0.65 = 65% chance)

        The simulator:
        1. Fetches real historical SOL prices from Binance
        2. Simulates how YES/NO prices would evolve based on price movements
        3. Runs your strategy against this simulated market
        4. Tracks trades, P&L, and calculates performance metrics

        ---

        ### 🎲 Available Strategies

        **Momentum Strategy**
        - Buys YES when price momentum is positive and YES price is high
        - Buys NO when price momentum is negative and YES price is low
        - Good for trending markets

        **Simple Arbitrage Strategy**
        - Looks for price inefficiencies where YES + NO ≠ 1.0
        - Rarely triggers in simulated markets (prices are efficient)
        """)

    # Footer
    st.sidebar.markdown("---")
    st.sidebar.markdown("*Polymarket Backtest GUI v1.0*")


if __name__ == "__main__":
    main()
