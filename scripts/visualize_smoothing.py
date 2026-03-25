"""Visualización de suavizado de curvas prob_up/prob_down por slot.

Compara:
  - Curva raw (promedio ponderado por n)
  - Rolling average (ventana configurable)
  - Isotonic regression (fuerza monotonicidad)

Uso:
    python3 scripts/visualize_smoothing.py
    python3 scripts/visualize_smoothing.py --ticker BTC --timeframe 5m --day-type workday
    python3 scripts/visualize_smoothing.py --ticker ETH --timeframe 15m --min-count 20

    # Generar PDF con todos los rangos de un ticker:
    python3 scripts/visualize_smoothing.py --ticker BTC --pdf backtest_output/BTC_report.pdf
    python3 scripts/visualize_smoothing.py --ticker ETH --pdf backtest_output/ETH_report.pdf
"""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # sin display (WSL/servidor) — genera PNG directamente
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "backtest_output"


def load_data(ticker: str, timeframe: str, min_count: int) -> pd.DataFrame:
    suffix = f"_mincount_{min_count}" if min_count > 0 else ""
    fname = DATA_DIR / f"merged_pm_slot_ranges_4cryptos{suffix}.csv"
    if not fname.exists():
        # fallback a archivo individual
        fname = DATA_DIR / f"{ticker.lower()}_pm_{timeframe}_slot_ranges{suffix}.csv"
    if not fname.exists():
        print(f"ERROR: No se encontró {fname}")
        sys.exit(1)
    df = pd.read_csv(fname)
    print(f"Cargado: {fname.name}  ({len(df)} filas)")
    return df


def weighted_mean_by_slot(df: pd.DataFrame) -> pd.DataFrame:
    """Promedio ponderado de prob_up/prob_down por slot usando count como peso."""
    rows = []
    for slot, grp in df.groupby("slot"):
        total_n = grp["count_of_klines_inside_range"].sum()
        if total_n == 0:
            continue
        prob_up = (grp["prob_up"] * grp["count_of_klines_inside_range"]).sum() / total_n
        prob_down = (grp["prob_down"] * grp["count_of_klines_inside_range"]).sum() / total_n
        rows.append({"slot": slot, "prob_up": prob_up, "prob_down": prob_down, "n": total_n})
    return pd.DataFrame(rows).sort_values("slot").reset_index(drop=True)


def apply_rolling(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, center=True, min_periods=1).mean()


def apply_isotonic(slots: np.ndarray, values: np.ndarray, increasing: bool) -> np.ndarray:
    ir = IsotonicRegression(increasing=increasing, out_of_bounds="clip")
    return ir.fit_transform(slots, values)


def plot_to_ax(agg: pd.DataFrame, title: str, rolling_window: int, fig: plt.Figure, gs_row) -> None:
    """Dibuja una página de suavizado en un gridspec row dado (reutilizable para PDF)."""
    slots = agg["slot"].values
    raw_up = agg["prob_up"].values
    raw_down = agg["prob_down"].values
    ns = agg["n"].values

    roll_up   = apply_rolling(agg["prob_up"], rolling_window).values
    roll_down = apply_rolling(agg["prob_down"], rolling_window).values
    iso_up    = apply_isotonic(slots, raw_up,   increasing=True)
    iso_down  = apply_isotonic(slots, raw_down, increasing=False)

    ax  = fig.add_subplot(gs_row[0])
    ax2 = fig.add_subplot(gs_row[1], sharex=ax)

    ax.set_title(title, fontsize=10, fontweight="bold")
    ax.plot(slots, raw_up,   "b-o", ms=3, alpha=0.35, label="prob_up raw")
    ax.plot(slots, raw_down, "r-o", ms=3, alpha=0.35, label="prob_down raw")
    ax.plot(slots, roll_up,   "b--", lw=1.5, alpha=0.65, label=f"rolling({rolling_window})")
    ax.plot(slots, roll_down, "r--", lw=1.5, alpha=0.65)
    ax.plot(slots, iso_up,   "b-",  lw=2.2, label="isotonic")
    ax.plot(slots, iso_down, "r-",  lw=2.2)
    ax.axhline(0.5, color="gray", lw=0.7, linestyle=":")
    ax.set_ylabel("Prob", fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.legend(fontsize=7, ncol=2)
    ax.grid(True, alpha=0.25)
    ax.tick_params(labelsize=7)

    ax2.bar(slots, ns, color="steelblue", alpha=0.55, width=0.7)
    low = slots[ns < 30]
    if len(low):
        ax2.bar(low, ns[ns < 30], color="tomato", alpha=0.8, width=0.7, label="n<30")
        ax2.legend(fontsize=7)
    ax2.set_ylabel("n", fontsize=8)
    ax2.set_xticks(slots[::2])
    ax2.tick_params(labelsize=7)
    ax2.grid(True, alpha=0.25, axis="y")


def generate_pdf(df_ticker: pd.DataFrame, ticker: str, rolling_window: int, pdf_path: Path) -> None:
    """Genera un PDF multi-página con todos los rangos del ticker.

    Portada con tabla resumen + 2 rangos por página (UP y DOWN juntos cuando son simétricos).
    """
    ranges = (
        df_ticker.groupby(["inf_range", "sup_range"])["count_of_klines_inside_range"]
        .sum()
        .reset_index()
        .sort_values("inf_range")
    )

    # Separar UP (inf >= 0) y DOWN (sup <= 0)
    up_ranges   = ranges[ranges["inf_range"] >= 0].values.tolist()
    down_ranges = ranges[ranges["sup_range"] <= 0].sort_values("inf_range", ascending=False).values.tolist() \
        if hasattr(ranges[ranges["sup_range"] <= 0], "values") \
        else ranges[ranges["sup_range"] <= 0].values.tolist()

    # Portada con tabla resumen
    with PdfPages(pdf_path) as pdf:
        # --- Portada ---
        fig_cover, ax_c = plt.subplots(figsize=(11, 8.5))
        ax_c.axis("off")
        ax_c.set_title(f"Smoothing Report — {ticker} 5m [workday]  rolling={rolling_window}",
                       fontsize=14, fontweight="bold", pad=20)

        prob_up_agg   = df_ticker.groupby(["inf_range", "sup_range"])["prob_up"].agg(["min", "max", "mean"])
        prob_down_agg = df_ticker.groupby(["inf_range", "sup_range"])["prob_down"].agg(["mean"])
        summary = ranges.merge(prob_up_agg.reset_index(), on=["inf_range", "sup_range"])
        summary = summary.merge(prob_down_agg.reset_index().rename(columns={"mean": "prob_down_mean"}),
                                on=["inf_range", "sup_range"])
        summary["n_slots"] = df_ticker.groupby(["inf_range", "sup_range"])["slot"].nunique().values
        summary["signal"] = (summary["max"] - summary["min"]).round(3)

        col_labels = ["inf", "sup", "n total", "n slots", "prob_up min", "prob_up max", "signal (max-min)"]
        cell_text = [
            [f"{r.inf_range:.2f}", f"{r.sup_range:.2f}", int(r.count_of_klines_inside_range),
             int(r.n_slots), f"{r['min']:.3f}", f"{r['max']:.3f}", f"{r.signal:.3f}"]
            for _, r in summary.iterrows()
        ]

        table = ax_c.table(cellText=cell_text, colLabels=col_labels,
                           loc="center", cellLoc="center")
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1.2, 1.8)

        # Colorear filas UP (verde) y DOWN (rojo) en la tabla
        for i, (_, r) in enumerate(summary.iterrows()):
            color = "#d4edda" if r.inf_range >= 0 else "#f8d7da"
            for j in range(len(col_labels)):
                table[i + 1, j].set_facecolor(color)

        plt.tight_layout()
        pdf.savefig(fig_cover, bbox_inches="tight")
        plt.close(fig_cover)

        # --- Páginas de rangos: 2 rangos por página ---
        all_ranges = down_ranges + up_ranges  # DOWN primero, luego UP

        for i in range(0, len(all_ranges), 2):
            batch = all_ranges[i:i + 2]
            fig = plt.figure(figsize=(11, 8.5))
            outer = gridspec.GridSpec(len(batch), 1, figure=fig, hspace=0.55)

            for j, (inf_r, sup_r, n_total) in enumerate(batch):
                sub = df_ticker[(df_ticker["inf_range"] == inf_r) & (df_ticker["sup_range"] == sup_r)]
                agg = weighted_mean_by_slot(sub)
                if agg.empty:
                    continue
                inner = gridspec.GridSpecFromSubplotSpec(2, 1, subplot_spec=outer[j],
                                                         height_ratios=[3, 1], hspace=0.15)
                direction = "UP" if inf_r >= 0 else "DOWN"
                title = (f"{ticker} 5m  range=[{inf_r:.3g}, {sup_r:.3g}]  "
                         f"{direction}  n_total={int(n_total)}  rolling={rolling_window}")
                plot_to_ax(agg, title, rolling_window, fig, inner)

            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

    print(f"PDF guardado: {pdf_path}  ({len(all_ranges)} rangos, {1 + (len(all_ranges) + 1) // 2} páginas)")


def compare_timeframes(df_full: pd.DataFrame, ticker: str, inf_r: float, sup_r: float,
                       rolling_window: int, out_path: Path | None) -> None:
    """Muestra la isotonic de prob_up para los 4 time_frames en una sola gráfica."""
    tfs = sorted(df_full["time_frame"].unique()) if "time_frame" in df_full.columns else ["all"]
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]

    fig, axes = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
    fig.suptitle(
        f"Comparación time_frames — {ticker}  range=[{inf_r:.3g}, {sup_r:.3g}]  (isotonic, rolling={rolling_window})",
        fontsize=12, fontweight="bold"
    )

    ax_prob, ax_n = axes
    ax_prob.axhline(0.5, color="gray", lw=0.8, linestyle=":")
    ax_prob.set_ylabel("prob_up  (isotonic)")
    ax_prob.set_ylim(0, 1.05)
    ax_prob.grid(True, alpha=0.3)

    ax_n.set_ylabel("n por slot")
    ax_n.set_xlabel("Slot")
    ax_n.grid(True, alpha=0.3, axis="y")

    for tf, color in zip(tfs, colors):
        sub = df_full[df_full["time_frame"] == tf] if "time_frame" in df_full.columns else df_full
        sub = sub[(sub["inf_range"] == inf_r) & (sub["sup_range"] == sup_r)]
        if sub.empty:
            continue
        agg = weighted_mean_by_slot(sub)
        if agg.empty:
            continue
        slots = agg["slot"].values
        iso_up = apply_isotonic(slots, agg["prob_up"].values, increasing=True)
        roll_up = apply_rolling(agg["prob_up"], rolling_window).values

        ax_prob.plot(slots, iso_up,   color=color, lw=2.5,  label=f"{tf} isotonic  (n̄={int(agg['n'].mean())})")
        ax_prob.plot(slots, roll_up,  color=color, lw=1.2, linestyle="--", alpha=0.5)
        ax_n.plot(slots, agg["n"].values, color=color, lw=1.5, marker="o", ms=3, label=tf)

    ax_prob.legend(fontsize=9)
    ax_n.legend(fontsize=9)

    # Marcar la línea "all tf combinados" como referencia
    sub_all = df_full[(df_full["inf_range"] == inf_r) & (df_full["sup_range"] == sup_r)]
    if not sub_all.empty:
        agg_all = weighted_mean_by_slot(sub_all)
        if not agg_all.empty:
            iso_all = apply_isotonic(agg_all["slot"].values, agg_all["prob_up"].values, increasing=True)
            ax_prob.plot(agg_all["slot"].values, iso_all, color="black",
                         lw=1.5, linestyle=":", alpha=0.6, label="todos tf (ref)")
            ax_prob.legend(fontsize=9)

    plt.tight_layout()
    if out_path:
        plt.savefig(out_path, dpi=150)
        print(f"Guardado: {out_path}")
    else:
        plt.show()
    plt.close(fig)


def plot(agg: pd.DataFrame, title: str, rolling_window: int, out_path: Path | None) -> None:
    slots = agg["slot"].values
    raw_up = agg["prob_up"].values
    raw_down = agg["prob_down"].values
    ns = agg["n"].values

    roll_up   = apply_rolling(agg["prob_up"], rolling_window).values
    roll_down = apply_rolling(agg["prob_down"], rolling_window).values

    iso_up   = apply_isotonic(slots, raw_up,   increasing=True)
    iso_down = apply_isotonic(slots, raw_down, increasing=False)

    fig, axes = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
    fig.suptitle(title, fontsize=13, fontweight="bold")

    # --- Panel superior: curvas de probabilidad ---
    ax = axes[0]
    ax.plot(slots, raw_up,   "b-o", ms=4, alpha=0.4, label="prob_up raw")
    ax.plot(slots, raw_down, "r-o", ms=4, alpha=0.4, label="prob_down raw")

    ax.plot(slots, roll_up,   "b--", lw=1.8, alpha=0.7, label=f"prob_up rolling({rolling_window})")
    ax.plot(slots, roll_down, "r--", lw=1.8, alpha=0.7, label=f"prob_down rolling({rolling_window})")

    ax.plot(slots, iso_up,   "b-",  lw=2.5, label="prob_up isotonic")
    ax.plot(slots, iso_down, "r-",  lw=2.5, label="prob_down isotonic")

    ax.axhline(0.5, color="gray", lw=0.8, linestyle=":")
    ax.set_ylabel("Probabilidad")
    ax.set_ylim(0, 1.05)
    ax.legend(fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)

    # --- Panel inferior: conteo de observaciones por slot ---
    ax2 = axes[1]
    ax2.bar(slots, ns, color="steelblue", alpha=0.6, width=0.7)
    ax2.set_xlabel("Slot")
    ax2.set_ylabel("n (observaciones)")
    ax2.set_xticks(slots)
    ax2.grid(True, alpha=0.3, axis="y")

    # Marcar slots con n bajo (< 30) en rojo
    low_n_slots = slots[ns < 30]
    if len(low_n_slots) > 0:
        ax2.bar(low_n_slots, ns[ns < 30], color="tomato", alpha=0.8, width=0.7, label="n < 30")
        ax2.legend(fontsize=8)

    plt.tight_layout()

    if out_path:
        plt.savefig(out_path, dpi=150)
        print(f"Guardado: {out_path}")
    else:
        plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualiza suavizado de prob_up/prob_down por slot")
    parser.add_argument("--ticker",     default="BTC",     help="BTC, ETH, SOL, XRP")
    parser.add_argument("--timeframe",  default="5m",      help="5m, 15m, 60m, 240m")
    parser.add_argument("--day-type",   default="workday", help="workday, weekend, all")
    parser.add_argument("--min-count",  type=int, default=0, help="Usar archivo mincount_N (0=sin filtro)")
    parser.add_argument("--rolling",    type=int, default=3, help="Ventana rolling average (default: 3)")
    parser.add_argument("--inf-range",  type=float, default=None, help="Filtro inf_range exacto (ej. 0.0)")
    parser.add_argument("--sup-range",  type=float, default=None, help="Filtro sup_range exacto (ej. 10.0)")
    parser.add_argument("--list-ranges", action="store_true", help="Mostrar rangos disponibles y salir")
    parser.add_argument("--save",        default=None,      help="Ruta PNG de salida (opcional)")
    parser.add_argument("--pdf",         default=None,      help="Generar PDF con todos los rangos del ticker")
    parser.add_argument("--compare-tf",  action="store_true", help="Comparar los 4 time_frames en una sola gráfica (requiere --inf-range y --sup-range)")
    args = parser.parse_args()

    df = load_data(args.ticker, args.timeframe, args.min_count)

    # Filtros
    if "ticker" in df.columns:
        df = df[df["ticker"].str.upper() == args.ticker.upper()]
    if "event_type" in df.columns:
        df = df[df["event_type"] == args.timeframe]
    if args.day_type != "all" and "day_type" in df.columns:
        df = df[df["day_type"] == args.day_type]

    # Modo compare-tf y PDF: necesitan todos los time_frames, NO filtrar aquí
    if args.compare_tf:
        if args.inf_range is None or args.sup_range is None:
            print("ERROR: --compare-tf requiere --inf-range y --sup-range")
            sys.exit(1)
        out = Path(args.save) if args.save else None
        compare_timeframes(df, args.ticker.upper(), args.inf_range, args.sup_range, args.rolling, out)
        sys.exit(0)

    if args.pdf:
        generate_pdf(df, args.ticker.upper(), args.rolling, Path(args.pdf))
        sys.exit(0)

    # Flujo normal: filtrar por un solo time_frame
    if "time_frame" in df.columns:
        tfs = df["time_frame"].unique()
        print(f"time_frames disponibles: {sorted(tfs)}")
        tf_target = "tf3" if "tf3" in tfs else tfs[0]
        df = df[df["time_frame"] == tf_target]
        print(f"Usando time_frame: {tf_target}")

    if df.empty:
        print("ERROR: Sin datos con los filtros aplicados.")
        sys.exit(1)

    # Mostrar rangos disponibles
    if args.list_ranges:
        rng = df.groupby(["inf_range", "sup_range"])["count_of_klines_inside_range"].sum().reset_index()
        rng["prob_up_min"] = df.groupby(["inf_range", "sup_range"])["prob_up"].min().values
        rng["prob_up_max"] = df.groupby(["inf_range", "sup_range"])["prob_up"].max().values
        print("\nRangos disponibles:")
        print(f"  {'inf':>6} {'sup':>6}  {'n':>6}  prob_up_min  prob_up_max")
        for _, r in rng.iterrows():
            print(f"  {r.inf_range:6.0f} {r.sup_range:6.0f}  {r.count_of_klines_inside_range:6.0f}  "
                  f"{r.prob_up_min:.3f}        {r.prob_up_max:.3f}")
        sys.exit(0)

    # Filtro de rango
    if args.inf_range is not None:
        df = df[df["inf_range"] == args.inf_range]
    if args.sup_range is not None:
        df = df[df["sup_range"] == args.sup_range]

    range_label = ""
    if args.inf_range is not None or args.sup_range is not None:
        range_label = f"  range=[{args.inf_range},{args.sup_range}]"

    if df.empty:
        print("ERROR: Sin datos con el filtro de rango aplicado. Usa --list-ranges para ver opciones.")
        sys.exit(1)

    agg = weighted_mean_by_slot(df)
    print(f"\nSlots disponibles: {agg['slot'].min()} – {agg['slot'].max()}  ({len(agg)} slots)")
    print(f"n por slot (min/max): {agg['n'].min()} / {agg['n'].max()}")
    print(f"Slots con n < 30: {agg[agg['n'] < 30]['slot'].tolist()}")

    title = (
        f"Suavizado prob_up/prob_down — {args.ticker} {args.timeframe} "
        f"[{args.day_type}]{range_label}  rolling={args.rolling}"
    )
    out = Path(args.save) if args.save else None
    plot(agg, title, args.rolling, out)


if __name__ == "__main__":
    main()
