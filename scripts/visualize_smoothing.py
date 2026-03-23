"""Visualización de suavizado de curvas prob_up/prob_down por slot.

Compara:
  - Curva raw (promedio ponderado por n)
  - Rolling average (ventana configurable)
  - Isotonic regression (fuerza monotonicidad)

Uso:
    python3 scripts/visualize_smoothing.py
    python3 scripts/visualize_smoothing.py --ticker BTC --timeframe 5m --day-type workday
    python3 scripts/visualize_smoothing.py --ticker ETH --timeframe 15m --min-count 20
"""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # sin display (WSL/servidor) — genera PNG directamente
import matplotlib.pyplot as plt
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
    parser.add_argument("--save",       default=None,      help="Ruta PNG de salida (opcional)")
    args = parser.parse_args()

    df = load_data(args.ticker, args.timeframe, args.min_count)

    # Filtros
    if "ticker" in df.columns:
        df = df[df["ticker"].str.upper() == args.ticker.upper()]
    if "event_type" in df.columns:
        df = df[df["event_type"] == args.timeframe]
    if args.day_type != "all" and "day_type" in df.columns:
        df = df[df["day_type"] == args.day_type]

    # tf3 = timeframe 3 en tu gráfica (verificar nombre exacto)
    if "time_frame" in df.columns:
        tfs = df["time_frame"].unique()
        print(f"time_frames disponibles: {sorted(tfs)}")
        # usar tf3 si existe, si no el primero
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
