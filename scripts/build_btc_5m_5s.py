"""
Build BTC 5m pipeline with 5-second slots (60 slots per event).
================================================================
Carga btc_1s_60d.csv, resamplea a 5s y construye el dataset de slots
en formato compatible con validate_oos_btc_5m.py.

Uso:
    python3 scripts/build_btc_5m_5s.py
    python3 scripts/build_btc_5m_5s.py --input backtest_output/btc_1s_60d.csv

Output:
    backtest_output/btc_subminute_5m_5s.csv
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT  = ROOT / "backtest_output" / "btc_1s_60d.csv"
DEFAULT_OUTPUT = ROOT / "backtest_output" / "btc_subminute_5m_5s.csv"

SLOT_SECONDS  = 5
EVENT_SECONDS = 300   # 5 minutos
N_SLOTS       = EVENT_SECONDS // SLOT_SECONDS   # 60


def main() -> None:
    parser = argparse.ArgumentParser(description="Build BTC 5m 5s-slot dataset")
    parser.add_argument("--input",  default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    input_path  = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERROR: no encontrado: {input_path}", file=sys.stderr)
        sys.exit(1)

    # ── 1. Cargar 1s klines ──────────────────────────────────────────────────
    print(f"Cargando {input_path} ...")
    df1s = pd.read_csv(
        input_path,
        usecols=["open_time", "open", "high", "low", "close",
                 "volume", "quote_asset_volume", "number_of_trades",
                 "taker_buy_base_volume", "taker_buy_quote_volume"],
    )
    print(f"  {len(df1s):,} klines de 1s cargados.")

    # open_time está en milisegundos
    df1s["open_time"] = df1s["open_time"].astype("int64")

    # ── 2. Resamplear 1s → 5s ───────────────────────────────────────────────
    # Alinear al inicio del bucket de 5s (ms)
    slot_ms = SLOT_SECONDS * 1000
    df1s["slot_open_ms"] = (df1s["open_time"] // slot_ms) * slot_ms

    agg = {
        "open":                    "first",
        "high":                    "max",
        "low":                     "min",
        "close":                   "last",
        "volume":                  "sum",
        "quote_asset_volume":      "sum",
        "number_of_trades":        "sum",
        "taker_buy_base_volume":   "sum",
        "taker_buy_quote_volume":  "sum",
    }

    df5s = (
        df1s.groupby("slot_open_ms", sort=True)
        .agg(agg)
        .reset_index()
        .rename(columns={"slot_open_ms": "open_time"})
    )

    close_time = df5s["open_time"] + slot_ms - 1
    df5s["close_time"] = close_time
    df5s["open_time_utc"] = pd.to_datetime(df5s["open_time"], unit="ms", utc=True) \
                              .dt.tz_localize(None)

    print(f"  {len(df5s):,} klines de 5s generados.")

    # ── 3. Asignar bloques de 5m ─────────────────────────────────────────────
    block_ms = EVENT_SECONDS * 1000
    df5s["ts_5m_block"]    = (df5s["open_time"] // block_ms) * block_ms
    df5s["slot_in_block"]  = ((df5s["open_time"] - df5s["ts_5m_block"]) // slot_ms + 1).astype(int)
    df5s["block_ts"]       = pd.to_datetime(df5s["ts_5m_block"], unit="ms", utc=True) \
                               .dt.tz_localize(None).astype(str)

    # ── 4. Filtrar bloques completos (exactamente N_SLOTS slots) ─────────────
    slot_counts = df5s.groupby("ts_5m_block")["slot_in_block"].count()
    complete_blocks = slot_counts[slot_counts == N_SLOTS].index
    n_before = df5s["ts_5m_block"].nunique()
    df5s = df5s[df5s["ts_5m_block"].isin(complete_blocks)].copy()
    n_after = df5s["ts_5m_block"].nunique()
    print(f"  Bloques: {n_before} total → {n_after} completos (descartados {n_before - n_after})")

    # ── 5. Columnas derivadas simples ────────────────────────────────────────
    # roi_interval y log_return respecto al open del slot
    df5s["roi_interval"] = (df5s["close"] - df5s["open"]) / df5s["open"]
    df5s["log_return"]   = np.log(df5s["close"] / df5s["open"].replace(0, np.nan))
    df5s["volatility"]   = df5s["log_return"].abs()

    df5s["direction"]    = np.where(df5s["close"] > df5s["open"], "up",
                           np.where(df5s["close"] < df5s["open"], "down", "flat"))
    df5s["up_move"]      = (df5s["close"] > df5s["open"]).astype(int)
    df5s["down_move"]    = (df5s["close"] < df5s["open"]).astype(int)

    # prob_up / prob_down: running mean dentro del bloque (informativo, no usado en OOS)
    df5s = df5s.sort_values(["ts_5m_block", "slot_in_block"])
    df5s["cum_up"]    = df5s.groupby("ts_5m_block")["up_move"].cumsum()
    df5s["cum_total"] = df5s.groupby("ts_5m_block").cumcount() + 1
    df5s["prob_up"]   = df5s["cum_up"] / df5s["cum_total"]
    df5s["prob_down"] = 1 - df5s["prob_up"]

    df5s["slot_seconds"] = SLOT_SECONDS

    # ── 6. Guardar ───────────────────────────────────────────────────────────
    cols = [
        "open_time", "open_time_utc", "open", "high", "low", "close",
        "volume", "close_time", "quote_asset_volume", "number_of_trades",
        "taker_buy_base_volume", "taker_buy_quote_volume",
        "roi_interval", "volatility", "log_return", "direction",
        "up_move", "down_move", "prob_up", "prob_down",
        "block_ts", "ts_5m_block", "slot_in_block", "slot_seconds",
    ]
    df5s[cols].to_csv(output_path, index=False)
    print(f"\nGuardado: {output_path}")
    print(f"  Filas: {len(df5s):,}")
    print(f"  Bloques completos: {n_after:,}")
    print(f"  Slots por bloque: {N_SLOTS} (5s cada uno)")
    print(f"  Rango: {df5s['open_time_utc'].min()} → {df5s['open_time_utc'].max()}")


if __name__ == "__main__":
    main()
