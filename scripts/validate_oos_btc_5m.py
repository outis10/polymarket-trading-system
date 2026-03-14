"""
Walk-forward OOS Validation — BTC 5m Pipeline
==============================================
Evalua la calibracion del modelo de probabilidad usando walk-forward
temporal (train=14d, test=1d, rolling diario).

Uso:
    python3 scripts/validate_oos_btc_5m.py
    python3 scripts/validate_oos_btc_5m.py --train-days 21 --min-count 10
    python3 scripts/validate_oos_btc_5m.py --input backtest_output/btc_subminute_5m.csv

Outputs:
    backtest_output/oos_predictions_btc_5m.csv  — predicciones por fila
    backtest_output/oos_report_btc_5m.json      — metricas agregadas

Metricas:
    Brier score   — lower = better (random toss = 0.25)
    Log-loss      — lower = better (random toss = 0.693)
    Calibracion   — mean(pred) vs mean(actual) por decil
"""

import argparse
import json
import math
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "backtest_output" / "btc_subminute_5m.csv"
DEFAULT_TIME_WINDOWS = ROOT / "config" / "time_windows.csv"
OUTPUT_PREDS = ROOT / "backtest_output" / "oos_predictions_btc_5m.csv"
OUTPUT_REPORT = ROOT / "backtest_output" / "oos_report_btc_5m.json"

RANGE_STEP = 10.0   # $10 bins para BTC 5m
SLOT_SECONDS = 10
TOTAL_SLOTS = 30


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_time_windows(path: Path) -> list[dict]:
    return pd.read_csv(path).to_dict("records")


def classify_window(dt: pd.Timestamp, windows: list[dict]) -> tuple[str, str]:
    """Clasifica un timestamp UTC a (day_type, time_frame)."""
    tz = ZoneInfo(windows[0]["zone"])
    local = dt.tz_localize("UTC").astimezone(tz) if dt.tzinfo is None else dt.astimezone(tz)
    day_type = "weekend" if local.weekday() >= 5 else "workday"
    local_hour = local.hour + local.minute / 60 + local.second / 3600
    for w in windows:
        if w["day_type"] != day_type:
            continue
        if w["start_hour"] <= local_hour < w["end_hour"]:
            return (day_type, w["time_frame"])
    return (day_type, "tf4")  # fallback: ultima ventana


def make_bin(price_diff: float, step: float) -> float:
    """Devuelve el inf_range del bin que contiene price_diff."""
    return math.floor(price_diff / step) * step


def build_prob_table(df: pd.DataFrame) -> dict:
    """
    Construye tabla de probabilidad desde un DataFrame de entrenamiento.
    Retorna dict: (day_type, time_frame, slot, inf_range) -> (prob_up, count)
    """
    table = {}
    grp = df.groupby(["day_type", "time_frame", "slot", "inf_range"], sort=False)
    for key, sub in grp:
        count = len(sub)
        prob_up = float(sub["event_outcome"].mean())
        table[key] = (prob_up, count)
    return table


def lookup_prob(
    table: dict,
    day_type: str,
    time_frame: str,
    slot: int,
    price_diff: float,
    step: float,
) -> tuple[float | None, int | None]:
    """Busca probabilidad en tabla. Retorna (prob_up, count) o (None, None) si no hay bin."""
    inf_range = make_bin(price_diff, step)
    key = (day_type, time_frame, int(slot), float(inf_range))
    result = table.get(key)
    if result is None:
        return None, None
    return result


# ── Metricas ───────────────────────────────────────────────────────────────────

def brier_score(preds: list[float], actuals: list[float]) -> float:
    p = np.array(preds)
    y = np.array(actuals)
    return float(np.mean((p - y) ** 2))


def log_loss_score(preds: list[float], actuals: list[float], eps: float = 1e-7) -> float:
    p = np.clip(np.array(preds), eps, 1 - eps)
    y = np.array(actuals)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def calibration_by_decile(preds: list[float], actuals: list[float]) -> list[dict]:
    """Agrupa predicciones en 10 deciles y compara mean(pred) vs mean(actual)."""
    p = np.array(preds)
    y = np.array(actuals)
    edges = np.percentile(p, np.linspace(0, 100, 11))
    edges = np.unique(np.round(edges, 4))
    cal = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p <= hi) if i == len(edges) - 2 else (p >= lo) & (p < hi)
        n = int(mask.sum())
        if n == 0:
            continue
        cal.append({
            "bin_low": round(lo, 4),
            "bin_high": round(hi, 4),
            "n": n,
            "mean_pred": round(float(p[mask].mean()), 4),
            "mean_actual": round(float(y[mask].mean()), 4),
            "error": round(float(p[mask].mean() - y[mask].mean()), 4),
        })
    return cal


def metrics_summary(preds: list[float], actuals: list[float], label: str = "") -> dict:
    if not preds:
        return {"label": label, "n": 0}
    bs = brier_score(preds, actuals)
    ll = log_loss_score(preds, actuals)
    acc = float(np.mean((np.array(preds) > 0.5) == (np.array(actuals) > 0.5)))
    mean_edge = float(np.mean(np.abs(np.array(preds) - 0.5)))
    return {
        "label": label,
        "n": len(preds),
        "brier_score": round(bs, 5),
        "log_loss": round(ll, 5),
        "accuracy_50pct_threshold": round(acc, 4),
        "mean_abs_edge_from_50": round(mean_edge, 4),
        # baseline comparison
        "brier_random": 0.25,
        "log_loss_random": round(-math.log(0.5), 5),
        "brier_vs_random": round(bs - 0.25, 5),
    }


# ── Pipeline principal ─────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward OOS validation BTC 5m")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--time-windows", default=str(DEFAULT_TIME_WINDOWS))
    parser.add_argument("--train-days", type=int, default=14)
    parser.add_argument("--min-count", type=int, default=5,
                        help="Minimo de muestras en el bin para usar la prediccion (default 5)")
    parser.add_argument("--range-step", type=float, default=RANGE_STEP)
    parser.add_argument("--skip-slots", type=int, nargs="*", default=[],
                        help="Slots a excluir del analisis (ej. --skip-slots 30)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: archivo no encontrado: {input_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Cargando {input_path} ...")
    df = pd.read_csv(input_path, parse_dates=["open_time_utc"])
    print(f"  {len(df):,} filas cargadas.")

    windows = load_time_windows(Path(args.time_windows))

    # ── Preparar columnas base ─────────────────────────────────────────────────

    # Fecha del bloque (para split temporal)
    df["block_date"] = pd.to_datetime(df["block_ts"]).dt.normalize()

    # ref_price = open del primer slot de cada bloque
    ref_prices = df.groupby("block_ts")["open"].first().rename("ref_price")
    df = df.join(ref_prices, on="block_ts")

    # final_close = close del ultimo slot de cada bloque
    final_closes = df.groupby("block_ts")["close"].last().rename("final_close")
    df = df.join(final_closes, on="block_ts")

    # Outcome del evento (para el label de cada slot)
    df["event_outcome"] = np.where(
        df["final_close"] > df["ref_price"], 1.0,
        np.where(df["final_close"] < df["ref_price"], 0.0, 0.5),
    )

    # price_diff = precio actual del slot vs ref_price del bloque
    df["price_diff"] = df["close"] - df["ref_price"]

    # Bin del price_diff
    df["inf_range"] = df["price_diff"].apply(lambda x: make_bin(x, args.range_step))

    # slot normalizado
    df["slot"] = df["slot_in_block"].astype(int)

    # Clasificar ventana temporal usando block_ts
    print("Clasificando ventanas temporales ...")
    block_times = df.drop_duplicates("block_ts")[["block_ts"]].copy()
    block_times["block_ts_dt"] = pd.to_datetime(block_times["block_ts"])
    block_times["day_type"], block_times["time_frame"] = zip(
        *block_times["block_ts_dt"].apply(lambda t: classify_window(t, windows))
    )
    block_times = block_times[["block_ts", "day_type", "time_frame"]]
    df = df.merge(block_times, on="block_ts", how="left")

    # Excluir slots configurados
    if args.skip_slots:
        df = df[~df["slot"].isin(args.skip_slots)]
        print(f"  Slots excluidos: {args.skip_slots}")

    # ── Walk-forward ───────────────────────────────────────────────────────────

    all_dates = sorted(df["block_date"].unique())
    if len(all_dates) <= args.train_days:
        print(f"ERROR: no hay suficientes dias ({len(all_dates)}) para train={args.train_days}", file=sys.stderr)
        sys.exit(1)

    test_dates = all_dates[args.train_days:]
    print(f"Walk-forward: {len(test_dates)} dias de test (train={args.train_days}d, test=1d)")

    predictions = []   # (date, slot, day_type, time_frame, pred, actual, count, price_diff, bin)
    coverage_total = 0
    coverage_hit = 0

    for i, test_date in enumerate(test_dates):
        # Ventana de entrenamiento: los N dias anteriores
        train_end = test_date
        train_start = all_dates[max(0, i)]  # i = index en all_dates de train_days atrás
        train_start = all_dates[i]          # el primer dia del rolling window

        train_mask = (df["block_date"] >= train_start) & (df["block_date"] < train_end)
        test_mask = df["block_date"] == test_date

        train_df = df[train_mask]
        test_df = df[test_mask]

        if train_df.empty or test_df.empty:
            continue

        table = build_prob_table(train_df)

        for _, row in test_df.iterrows():
            coverage_total += 1
            pred, count = lookup_prob(
                table,
                row["day_type"],
                row["time_frame"],
                int(row["slot"]),
                float(row["price_diff"]),
                args.range_step,
            )
            if pred is None or count is None or count < args.min_count:
                continue
            coverage_hit += 1
            predictions.append({
                "date": str(test_date.date()),
                "slot": int(row["slot"]),
                "day_type": row["day_type"],
                "time_frame": row["time_frame"],
                "price_diff": round(float(row["price_diff"]), 2),
                "inf_range": float(row["inf_range"]),
                "pred_prob_up": round(pred, 6),
                "actual_outcome": float(row["event_outcome"]),
                "train_bin_count": count,
            })

        if (i + 1) % 5 == 0:
            print(f"  Procesados {i + 1}/{len(test_dates)} dias de test ...")

    print(f"\nCobertura: {coverage_hit}/{coverage_total} "
          f"({100 * coverage_hit / coverage_total:.1f}%) con min_count>={args.min_count}")

    if not predictions:
        print("ERROR: sin predicciones. Revisa min_count o rango de fechas.", file=sys.stderr)
        sys.exit(1)

    preds_df = pd.DataFrame(predictions)
    preds_df.to_csv(OUTPUT_PREDS, index=False)
    print(f"Predicciones guardadas: {OUTPUT_PREDS}")

    # ── Metricas globales ──────────────────────────────────────────────────────

    all_preds = preds_df["pred_prob_up"].tolist()
    all_actuals = preds_df["actual_outcome"].tolist()

    report: dict = {}
    report["overall"] = metrics_summary(all_preds, all_actuals, "overall")
    report["overall"]["coverage_pct"] = round(100 * coverage_hit / coverage_total, 2)
    report["calibration"] = calibration_by_decile(all_preds, all_actuals)

    # ── Metricas por slot ──────────────────────────────────────────────────────

    slot_metrics = []
    for slot in sorted(preds_df["slot"].unique()):
        sub = preds_df[preds_df["slot"] == slot]
        m = metrics_summary(sub["pred_prob_up"].tolist(), sub["actual_outcome"].tolist(), f"slot_{slot}")
        slot_metrics.append(m)
    report["by_slot"] = slot_metrics

    # ── Metricas por time_frame ────────────────────────────────────────────────

    tf_metrics = []
    for tf in sorted(preds_df["time_frame"].unique()):
        sub = preds_df[preds_df["time_frame"] == tf]
        m = metrics_summary(sub["pred_prob_up"].tolist(), sub["actual_outcome"].tolist(), tf)
        tf_metrics.append(m)
    report["by_time_frame"] = tf_metrics

    # ── Metricas por day_type ──────────────────────────────────────────────────

    dt_metrics = []
    for dt in sorted(preds_df["day_type"].unique()):
        sub = preds_df[preds_df["day_type"] == dt]
        m = metrics_summary(sub["pred_prob_up"].tolist(), sub["actual_outcome"].tolist(), dt)
        dt_metrics.append(m)
    report["by_day_type"] = dt_metrics

    with open(OUTPUT_REPORT, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Reporte guardado: {OUTPUT_REPORT}")

    # ── Resumen en consola ─────────────────────────────────────────────────────

    ov = report["overall"]
    print(f"\n{'='*55}")
    print(f"RESULTADO OOS — BTC 5m walk-forward")
    print(f"{'='*55}")
    print(f"  Predicciones evaluadas : {ov['n']:,}")
    print(f"  Cobertura              : {ov['coverage_pct']}%")
    print(f"  Brier score            : {ov['brier_score']}  (random=0.25, delta={ov['brier_vs_random']:+.5f})")
    print(f"  Log-loss               : {ov['log_loss']}  (random={ov['log_loss_random']})")
    print(f"  Accuracy (>50% thresh) : {ov['accuracy_50pct_threshold']:.1%}")
    print(f"  Mean |edge from 50%|   : {ov['mean_abs_edge_from_50']:.4f}")
    print()
    print(f"  Calibracion por decil:")
    print(f"  {'Pred':>8}  {'Actual':>8}  {'Error':>8}  {'N':>6}")
    for c in report["calibration"]:
        flag = " !" if abs(c["error"]) > 0.05 else ""
        print(f"  {c['mean_pred']:>8.4f}  {c['mean_actual']:>8.4f}  {c['error']:>+8.4f}  {c['n']:>6}{flag}")
    print()
    print(f"  Por time_frame:")
    for m in report["by_time_frame"]:
        if m["n"] == 0:
            continue
        print(f"    {m['label']:8s}  n={m['n']:5d}  brier={m['brier_score']:.4f}  acc={m['accuracy_50pct_threshold']:.1%}")
    print()
    print(f"  Slots con peor Brier (top 5):")
    worst = sorted(report["by_slot"], key=lambda x: x.get("brier_score", 0), reverse=True)[:5]
    for m in worst:
        if m["n"] == 0:
            continue
        print(f"    slot {m['label']:10s}  n={m['n']:4d}  brier={m['brier_score']:.4f}  acc={m['accuracy_50pct_threshold']:.1%}")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
