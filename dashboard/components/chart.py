"""Price chart component ported from monitor_gui.py."""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def create_price_chart(
    price_history,
    height=350,
    show_probability=True,
    show_price_change=True,
    chart_id="",
):
    """Create a Polymarket-style price chart with dual series."""
    if not price_history:
        fig = go.Figure()
        fig.update_layout(
            template="plotly_dark",
            height=height,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            title=dict(text=chart_id, font=dict(size=1, color="rgba(0,0,0,0)")),
        )
        return fig

    df = pd.DataFrame(price_history)

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Main price line - Orange (no fill-to-zero, range is tight around price_to_beat)
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["price"],
            mode="lines",
            name="BTC Price",
            line=dict(color="#f7931a", width=2),
            hovertemplate="$%{y:,.2f}<extra>BTC Price</extra>",
        ),
        secondary_y=False,
    )

    # Probability series
    if show_probability and "yes_price" in df.columns:
        df["yes_percent"] = df["yes_price"] * 100
        avg_yes = df["yes_percent"].mean()
        percent_color = "#3fb950" if avg_yes >= 50 else "#f85149"

        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["yes_percent"],
                mode="lines",
                name="UP Probability",
                line=dict(color=percent_color, width=2, dash="solid"),
                hovertemplate="%{y:.1f}%<extra>UP Probability</extra>",
            ),
            secondary_y=True,
        )

    # Price change percentage series
    if show_price_change and "percent_change" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["percent_change"],
                mode="lines",
                name="Price Change %",
                line=dict(color="#58a6ff", width=1.5, dash="dot"),
                hovertemplate="%{y:+.2f}%<extra>Price Change</extra>",
            ),
            secondary_y=True,
        )

    fig.update_layout(
        template="plotly_dark",
        height=height,
        margin=dict(l=0, r=0, t=30, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            showgrid=False,
            showticklabels=True,
            tickfont=dict(color="#8b949e", size=10),
            tickformat="%H:%M:%S",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=10, color="#8b949e"),
            bgcolor="rgba(0,0,0,0)",
        ),
        showlegend=True,
        hovermode="x unified",
    )

    # Compute y-axis range centered on price_to_beat so fluctuations are visible
    ptb = price_history[0].get("price_to_beat", df["price"].median()) if price_history else df["price"].median()
    # Use ±500 as default window; widen to ±1000 if actual data exceeds ±500
    price_min = df["price"].min()
    price_max = df["price"].max()
    half_window = 500
    if price_max - ptb > half_window or ptb - price_min > half_window:
        half_window = 1000
    y_lo = ptb - half_window
    y_hi = ptb + half_window

    fig.update_yaxes(
        title_text="BTC Price",
        title_font=dict(color="#f7931a", size=11),
        showgrid=True,
        gridcolor="rgba(48, 54, 61, 0.5)",
        tickfont=dict(color="#f7931a", size=10),
        tickprefix="$",
        tickformat=",.0f",
        range=[y_lo, y_hi],
        secondary_y=False,
    )

    fig.update_yaxes(
        title_text="Probability %",
        title_font=dict(color="#3fb950", size=11),
        showgrid=False,
        tickfont=dict(color="#3fb950", size=10),
        ticksuffix="%",
        range=[0, 100],
        secondary_y=True,
    )

    if price_history and "price_to_beat" in price_history[0]:
        fig.add_hline(
            y=price_history[0].get("price_to_beat", df["price"].iloc[0]),
            line_dash="dash",
            line_color="rgba(139, 148, 158, 0.5)",
            annotation_text="Target",
            annotation_position="bottom right",
            secondary_y=False,
        )

    if show_probability:
        fig.add_hline(
            y=50,
            line_dash="dash",
            line_color="rgba(139, 148, 158, 0.3)",
            annotation_text="50%",
            annotation_position="left",
            secondary_y=True,
        )

    return fig
