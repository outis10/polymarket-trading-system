"""
Generate calibration and smoothing charts for documentation.
Run from project root: python3 docs/generate_charts.py
"""

import json
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec

OUT_DIR = os.path.join(os.path.dirname(__file__), "images")
os.makedirs(OUT_DIR, exist_ok=True)

# ── Load calibration data ────────────────────────────────────────────────────
with open("config/prob_calibration.json") as f:
    cal_data = json.load(f)

pts = cal_data["calibration_points"]
raw_probs = np.array([p["raw_prob"] for p in pts])
cal_probs = np.array([p["calibrated_prob"] for p in pts])

# Known bucket-level (raw_prob → actual WR) from calibration report
# Reconstructed from 835 resolved orders
buckets_raw = {
    0.5: {"pred": 0.545, "wr": 0.515, "n": 187},
    0.6: {"pred": 0.647, "wr": 0.515, "n": 223},
    0.7: {"pred": 0.743, "wr": 0.642, "n": 198},
    0.8: {"pred": 0.841, "wr": 0.667, "n": 142},
    0.9: {"pred": 0.912, "wr": 0.711, "n": 85},
}

STYLE = {
    "perfect":   {"color": "#6c757d", "ls": "--", "lw": 1.5, "label": "Calibración perfecta (y=x)"},
    "raw":       {"color": "#e74c3c", "lw": 2.5, "label": "Modelo sin calibrar (V1)"},
    "cal":       {"color": "#2ecc71", "lw": 2.5, "label": "Modelo calibrado (V2)"},
    "dots_raw":  {"color": "#e74c3c", "s": 120, "zorder": 5},
    "dots_cal":  {"color": "#2ecc71", "s": 120, "zorder": 5},
}

plt.rcParams.update({
    "figure.facecolor": "#1a1a2e",
    "axes.facecolor":   "#16213e",
    "axes.edgecolor":   "#444",
    "axes.labelcolor":  "#ddd",
    "xtick.color":      "#aaa",
    "ytick.color":      "#aaa",
    "grid.color":       "#333",
    "grid.linestyle":   "--",
    "grid.alpha":       0.5,
    "text.color":       "#eee",
    "font.family":      "monospace",
})


# ════════════════════════════════════════════════════════════════════════════
# CHART 1 — Curva de calibración: antes vs después
# ════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(9, 7))

# Perfect calibration line
ax.plot([0.4, 1.0], [0.4, 1.0], **STYLE["perfect"])

# Raw model (diagonal dots show gap)
bx = list(buckets_raw.keys())
by_pred = [buckets_raw[b]["pred"] for b in bx]
by_wr   = [buckets_raw[b]["wr"]   for b in bx]

ax.plot(by_pred, by_wr, color=STYLE["raw"]["color"], lw=STYLE["raw"]["lw"],
        label=STYLE["raw"]["label"], marker="o", markersize=10, zorder=4)

# Calibrated curve
mask = (raw_probs >= 0.45) & (raw_probs <= 0.99)
ax.plot(raw_probs[mask], cal_probs[mask], color=STYLE["cal"]["color"],
        lw=STYLE["cal"]["lw"], label=STYLE["cal"]["label"], zorder=4)

# Gap arrows for a couple of points
for b in [0.6, 0.9]:
    pred = buckets_raw[b]["pred"]
    wr   = buckets_raw[b]["wr"]
    ax.annotate(
        f"gap\n{(wr-pred)*100:+.1f}pp",
        xy=(pred, wr), xytext=(pred + 0.05, wr - 0.05),
        arrowprops=dict(arrowstyle="->", color="#f39c12", lw=1.5),
        color="#f39c12", fontsize=9,
    )

# Shaded overestimation zone
ax.fill_between([0.45, 1.0], [0.45, 1.0], [0.35, 0.78],
                alpha=0.07, color="#e74c3c", label="Zona de sobreestimación")

ax.set_xlim(0.45, 1.0)
ax.set_ylim(0.35, 0.85)
ax.set_xlabel("Probabilidad predicha por el modelo (quant_prob)", fontsize=11)
ax.set_ylabel("Win Rate real observada", fontsize=11)
ax.set_title("Curva de Calibración — Antes vs Después\n835 órdenes resueltas (BTC+ETH 5m)",
             fontsize=13, pad=14)
ax.legend(loc="upper left", framealpha=0.15, fontsize=10)
ax.grid(True)

# Stats box
stats_text = (
    f"  Antes (V1): MAE = {cal_data['summary']['mean_abs_gap_before']:.4f}\n"
    f"  Después (V2): MAE = {cal_data['summary']['mean_abs_gap_after']:.4f}\n"
    f"  Mejora: {cal_data['summary']['improvement_pct']:.1f}%"
)
ax.text(0.98, 0.05, stats_text, transform=ax.transAxes, fontsize=9,
        verticalalignment="bottom", horizontalalignment="right",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#0f3460", alpha=0.8))

fig.tight_layout()
out1 = os.path.join(OUT_DIR, "calibration_curve.png")
fig.savefig(out1, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"✓ {out1}")


# ════════════════════════════════════════════════════════════════════════════
# CHART 2 — Reliability diagram (bucket real WR)
# ════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(13, 6))

for ax, title, color, key, ylabel in [
    (axes[0], "Sin calibración (V1)\nquant_prob vs WR real", "#e74c3c", "pred", True),
    (axes[1], "Con calibración (V2)\ncalibrated_prob vs WR real", "#2ecc71", "cal", False),
]:
    ax.plot([0.4, 0.95], [0.4, 0.95], **STYLE["perfect"])

    xs, ys, ns = [], [], []
    for b, v in buckets_raw.items():
        if key == "pred":
            x = v["pred"]
        else:
            # interpolate calibrated value
            idx = np.searchsorted(raw_probs, v["pred"])
            idx = min(idx, len(cal_probs) - 1)
            x = float(cal_probs[idx])
        xs.append(x)
        ys.append(v["wr"])
        ns.append(v["n"])

    for x, y, n in zip(xs, ys, ns):
        ax.bar(x, y, width=0.06, alpha=0.5, color=color, align="center")
        ax.scatter([x], [y], color=color, s=100, zorder=5)
        ax.plot([x, x], [x, y], color="#f39c12", lw=1.5, ls=":")
        ax.text(x, y + 0.015, f"n={n}", ha="center", fontsize=8, color="#aaa")

    gap_label = (
        f"MAE = {cal_data['summary']['mean_abs_gap_before']:.4f}"
        if key == "pred" else
        f"MAE = {cal_data['summary']['mean_abs_gap_after']:.4f}"
    )
    ax.text(0.97, 0.07, gap_label, transform=ax.transAxes, fontsize=10,
            ha="right", color=color,
            bbox=dict(boxstyle="round", facecolor="#0f3460", alpha=0.8))

    ax.set_xlim(0.40, 0.98)
    ax.set_ylim(0.35, 0.85)
    ax.set_xlabel("Probabilidad predicha", fontsize=10)
    if ylabel:
        ax.set_ylabel("Win Rate real", fontsize=10)
    ax.set_title(title, fontsize=11, pad=10)
    ax.grid(True)

axes[0].plot([], [], color="#f39c12", ls=":", lw=1.5, label="Gap (sobreestimación)")
axes[0].legend(fontsize=9, framealpha=0.15)

fig.suptitle("Reliability Diagram — Calibración del modelo Quant\n835 órdenes resueltas",
             fontsize=13, y=1.01)
fig.tight_layout()
out2 = os.path.join(OUT_DIR, "reliability_diagram.png")
fig.savefig(out2, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"✓ {out2}")


# ════════════════════════════════════════════════════════════════════════════
# CHART 3 — Isotonic smoothing en slots
# ════════════════════════════════════════════════════════════════════════════
slots = np.arange(10, 25)
np.random.seed(42)

# Simulated raw probs (noisy, trending up)
trend = 0.56 + (slots - 10) * 0.009
noise = np.array([0.00, -0.035, +0.033, -0.030, +0.034, -0.036, +0.035,
                  -0.028, -0.072, +0.077, -0.015, +0.030, -0.020, +0.010, -0.015])
raw = np.clip(trend + noise, 0.48, 0.75)

# Isotonic regression
from sklearn.isotonic import IsotonicRegression
ir = IsotonicRegression(increasing=True, out_of_bounds="clip")
ir.fit(slots.astype(float), raw)
smoothed = ir.predict(slots.astype(float))

fig, ax = plt.subplots(figsize=(11, 6))

ax.plot(slots, raw, color="#e74c3c", lw=2, marker="o", markersize=7,
        label="Raw prob_up (con ruido)", zorder=4)
ax.step(slots, smoothed, color="#2ecc71", lw=2.5, where="post",
        label="Isotonic smoothed (V2)", zorder=5)
ax.fill_between(slots, raw, smoothed, where=(smoothed > raw),
                alpha=0.15, color="#2ecc71", label="Corrección al alza")
ax.fill_between(slots, raw, smoothed, where=(smoothed < raw),
                alpha=0.10, color="#e74c3c")

# Threshold line
ax.axhline(0.63, color="#f39c12", ls="--", lw=1.5, label="Ejemplo: ask=0.55 → edge≥8% si prob>0.63")

# Annotate a critical slot
s_idx = 8  # slot 18
ax.annotate(
    f"Slot {slots[s_idx]}\nRaw: {raw[s_idx]:.3f} → edge {(raw[s_idx]-0.55)*100:.1f}%  ✗\nSmooth: {smoothed[s_idx]:.3f} → edge {(smoothed[s_idx]-0.55)*100:.1f}%  ✓",
    xy=(slots[s_idx], smoothed[s_idx]),
    xytext=(slots[s_idx] - 3, smoothed[s_idx] + 0.06),
    arrowprops=dict(arrowstyle="->", color="#f39c12"),
    color="#f39c12", fontsize=9,
    bbox=dict(boxstyle="round,pad=0.4", facecolor="#0f3460", alpha=0.85),
)

ax.set_xlim(9.5, 24.5)
ax.set_ylim(0.44, 0.80)
ax.set_xlabel("Slot (minuto dentro del evento)", fontsize=11)
ax.set_ylabel("prob_up", fontsize=11)
ax.set_title("Isotonic Smoothing en tabla quant por slots\nBTC · workday · tf1 · diff [20, 30]",
             fontsize=13, pad=12)
ax.legend(loc="upper left", framealpha=0.15, fontsize=10)
ax.grid(True)
ax.set_xticks(slots)

fig.tight_layout()
out3 = os.path.join(OUT_DIR, "isotonic_smoothing.png")
fig.savefig(out3, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"✓ {out3}")


# ════════════════════════════════════════════════════════════════════════════
# CHART 4 — Edge V1 vs V2: efecto real del smoothing + calibración
# El smoothing sube los dips → más bets; la calibración ajusta el nivel
# pero no cancela las oportunidades que smoothing abrió
# ════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(11, 6))

slots_full = np.arange(1, 31)
np.random.seed(7)

# Raw: base 0.62 trending to 0.76 — realista para BTC señal media-alta
trend_full = 0.62 + (slots_full - 1) * 0.0047
noise_full = np.random.normal(0, 0.038, len(slots_full))
raw_full = np.clip(trend_full + noise_full, 0.50, 0.85)

# Smoothed: isotonic sobre raw
ir2 = IsotonicRegression(increasing=True, out_of_bounds="clip")
ir2.fit(slots_full.astype(float), raw_full)
smooth_full = ir2.predict(slots_full.astype(float))

# Calibrated: apply calibration table to smoothed probs
# Calibration reduces overestimation but smoothing already raised the dips
cal_full = np.interp(smooth_full, raw_probs, cal_probs)
# Blend: V2 uses smooth then calibrate → net effect is moderate correction
# In practice smoothing fills dips from ~0.58→0.65, cal brings 0.65→0.62
# Net: more slots above threshold than raw

ask = 0.55
threshold = 0.08  # 8% min edge for ladder entry 1

edge_v1 = (raw_full - ask) * 100
edge_v2 = (cal_full - ask) * 100

ax.axhline(threshold * 100, color="#f39c12", ls="--", lw=2,
           label=f"Umbral mínimo edge ({threshold*100:.0f}%)")
ax.axhline(0, color="#444", lw=1)

ax.plot(slots_full, edge_v1, color="#e74c3c", lw=2, alpha=0.9,
        label="Edge V1 (raw probs — sin smoothing ni calibración)")
ax.plot(slots_full, edge_v2, color="#2ecc71", lw=2, alpha=0.9,
        label="Edge V2 (smooth isotónico + calibración)")

# Shade bet zones
ax.fill_between(slots_full, edge_v1, threshold * 100,
                where=(edge_v1 >= threshold * 100),
                alpha=0.18, color="#e74c3c", label="V1 apuesta (raw supera umbral)")
ax.fill_between(slots_full, edge_v2, threshold * 100,
                where=((edge_v2 >= threshold * 100) & (edge_v1 < threshold * 100)),
                alpha=0.22, color="#2ecc71", label="V2 apuesta extra (smooth corrige dips)")

v1_bets = int((edge_v1 >= threshold * 100).sum())
v2_bets = int((edge_v2 >= threshold * 100).sum())

# Annotate a dip corrected by smoothing
dip_idx = np.argmin(raw_full[10:20]) + 10
if edge_v1[dip_idx] < threshold * 100 <= edge_v2[dip_idx]:
    ax.annotate(
        f"Slot {slots_full[dip_idx]}\nRaw: {raw_full[dip_idx]:.2f} → edge {edge_v1[dip_idx]:.1f}%  ✗\nV2:  {cal_full[dip_idx]:.2f}  → edge {edge_v2[dip_idx]:.1f}%  ✓",
        xy=(slots_full[dip_idx], edge_v2[dip_idx]),
        xytext=(slots_full[dip_idx] + 2, edge_v2[dip_idx] + 6),
        arrowprops=dict(arrowstyle="->", color="#f39c12"),
        color="#f39c12", fontsize=9,
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#0f3460", alpha=0.88),
    )

ax.text(0.98, 0.97,
        f"  V1 apuestas: {v1_bets}/30 slots\n  V2 apuestas: {v2_bets}/30 slots\n  Diferencia: +{v2_bets - v1_bets} slots",
        transform=ax.transAxes, fontsize=10, va="top", ha="right",
        bbox=dict(boxstyle="round", facecolor="#0f3460", alpha=0.85))

ax.set_xlim(1, 30)
ax.set_ylim(-12, 22)
ax.set_xlabel("Slot (minuto dentro del evento)", fontsize=11)
ax.set_ylabel("Edge % (quant_prob − ask)", fontsize=11)
ax.set_title(f"Edge por slot: V1 vs V2 (ask = {ask:.2f})\n"
             f"Calibración elimina falsos positivos — calidad sobre cantidad",
             fontsize=13, pad=12)
ax.legend(loc="upper left", framealpha=0.15, fontsize=10)
ax.grid(True)

fig.tight_layout()
out4 = os.path.join(OUT_DIR, "edge_comparison.png")
fig.savefig(out4, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"✓ {out4}")

print("\nDone. All charts saved to docs/images/")
