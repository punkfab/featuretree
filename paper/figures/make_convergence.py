#!/usr/bin/env python3
"""Generate fig. 'carve_convergence' — the paper's core argument as a picture.

Emits the recovered NIST CTC-01 IR incrementally, feature by feature, and plots
the reconstructed volume against the target. Shows the base envelope starting
155% over, each carving operation removing material, and the trajectory entering
the verification tolerance band -- which is the moment the recogniser is entitled
to say VERIFIED.

Run from the REPO ROOT:
    python3 paper/figures/make_convergence.py

Writes: paper/figures/carve_convergence.pdf (+ .png) and prints the data table.
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.getcwd())
import b3d_emit
import step_recognize as sr

STEP = "tests/step/nist_ctc_01_asme1_rd.stp"
TOL_PCT = 1.0                      # epsilon_V used for the shaded band
OUT = os.path.join("paper", "figures", "carve_convergence")

# Brand-neutral, print-safe, colourblind-distinguishable.
C_TRAJ   = "#2A6F97"   # carve trajectory
C_TARGET = "#1B1B1B"   # target volume
C_BAND   = "#8FC9E8"   # tolerance band
C_BASE   = "#C1666B"   # base envelope marker


def emit_volume(spec, n):
    sub = dict(spec)
    sub["features"] = spec["features"][:n]
    out = b3d_emit.emit(sub)
    solid = out[0] if isinstance(out, tuple) else out
    return solid.volume


def main():
    spec, rep = sr.recognize(STEP)
    feats = spec["features"]
    target = rep["vol_orig"]

    # Sample after every material-changing op (pad / pocket / prism_cut);
    # a bare 'sketch' adds no solid, so emitting there is wasted work.
    idxs = [i + 1 for i, f in enumerate(feats)
            if f["kind"] in ("pad", "pocket", "prism_cut")]

    xs, ys = [], []
    for n in idxs:
        try:
            v = emit_volume(spec, n)
        except Exception as exc:                      # a partial prefix can be invalid
            print(f"  skip n={n}: {exc}", file=sys.stderr)
            continue
        xs.append(n)
        ys.append(v)
        print(f"  n={n:3d}  kind={feats[n-1]['kind']:<10} vol={v:14.1f}  "
              f"{100.0*(v-target)/target:+8.2f}%")

    fig, ax = plt.subplots(figsize=(7.0, 3.9))

    lo, hi = target * (1 - TOL_PCT / 100.0), target * (1 + TOL_PCT / 100.0)
    ax.axhspan(lo, hi, color=C_BAND, alpha=0.45, zorder=1,
               label=f"verification tolerance ($\\pm${TOL_PCT:g}%)")
    ax.axhline(target, color=C_TARGET, lw=1.3, ls="--", zorder=3,
               label=f"target volume ({target/1e6:.3f}$\\times10^6$ mm$^3$)")
    ax.plot(xs, ys, "-o", color=C_TRAJ, ms=3.4, lw=1.5, zorder=4,
            label="reconstructed volume during carving")
    ax.plot([xs[0]], [ys[0]], "o", color=C_BASE, ms=8, zorder=5,
            label=f"base envelope ({100.0*(ys[0]-target)/target:+.0f}%)")

    ax.set_xlabel("features applied")
    ax.set_ylabel("volume (mm$^3$)")
    ax.set_title("Carving converges onto the target; the verifier accepts only inside the band")
    ax.legend(loc="upper right", fontsize=8, framealpha=0.95)
    ax.grid(alpha=0.25, lw=0.6)
    ax.margins(x=0.02)
    fig.tight_layout()

    for ext in ("pdf", "png"):
        fig.savefig(f"{OUT}.{ext}", dpi=200)
    final_pct = 100.0 * (ys[-1] - target) / target
    print(f"\nwrote {OUT}.pdf / .png")
    print(f"base {ys[0]:.1f} ({100.0*(ys[0]-target)/target:+.1f}%) -> "
          f"final {ys[-1]:.1f} ({final_pct:+.2f}%), target {target:.1f}")
    print(f"report: verified={rep['verified']} dvol_pct={rep['dvol_pct']}")


if __name__ == "__main__":
    main()
