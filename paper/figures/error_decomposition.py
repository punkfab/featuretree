#!/usr/bin/env python3
"""Decompose the NIST CTC-01 verification residual into over-cut vs uncut material.

WHY THIS EXISTS. The recogniser reports a single scalar, |dV|/V = 0.1%, and the
repo's prose attributed it to the part's 8 uncut chamfers. That story implies the
recovered solid is LARGER than the original. It is in fact SMALLER (-0.101%), so
the scalar was hiding two errors of opposite sign that partially cancel.

METHOD / CAVEAT. Direct OCCT `-` and `&` between these two operands return
nonsense (zero intersection for solids whose bounding boxes coincide exactly),
while `+` behaves. So the decomposition is derived from the UNION via
inclusion-exclusion rather than trusted to a direct difference:

    |A n B| = |A| + |B| - |A u B|
    over-cut (in original, missing from recovery) = |A| - |A n B| = |A u B| - |B|
    uncut    (in recovery, absent from original)  = |B| - |A n B| = |A u B| - |A|

Self-consistency is asserted: (uncut - overcut) must equal the signed net.

Run from the REPO ROOT:
    python3 paper/figures/error_decomposition.py
"""
import os
import sys

from build123d import Pos, import_step

sys.path.insert(0, os.getcwd())
import b3d_emit
import step_recognize as sr

STEP = "tests/step/nist_ctc_01_asme1_rd.stp"


def one_solid(obj):
    solids = obj.solids() if hasattr(obj, "solids") else []
    return solids[0] if solids else obj


def main():
    orig = one_solid(import_step(STEP))
    spec, rep = sr.recognize(STEP)
    out = b3d_emit.emit(spec)
    rec = one_solid(out[0] if isinstance(out, tuple) else out)

    # Recognition works in the part's own frame; co-register by bbox min corner.
    bo, br = orig.bounding_box(), rec.bounding_box()
    delta = (bo.min.X - br.min.X, bo.min.Y - br.min.Y, bo.min.Z - br.min.Z)
    rec = Pos(*delta) * rec
    assert rec.bounding_box().min.Z == bo.min.Z, "co-registration failed"

    A, B = orig.volume, rec.volume
    union = orig + rec
    U = sum(s.volume for s in union.solids()) if union.solids() else union.volume

    inter = A + B - U
    overcut = U - B          # in original, missing from recovery
    uncut = U - A            # in recovery, absent from original
    net = B - A

    assert abs((uncut - overcut) - net) < 1.0, "inclusion-exclusion inconsistent"

    print(f"co-registration translation : {tuple(round(v, 3) for v in delta)}")
    print(f"vol original            A   = {A:14.1f}")
    print(f"vol recovered           B   = {B:14.1f}")
    print(f"vol union           |AuB|   = {U:14.1f}")
    print(f"vol intersection    |AnB|   = {inter:14.1f}   ({100*inter/A:.3f}% of A)")
    print()
    print(f"over-cut (missing from recovery) = {overcut:10.1f}  ({100*overcut/A:.4f}% of part)")
    print(f"uncut    (extra in recovery)     = {uncut:10.1f}  ({100*uncut/A:.4f}% of part)")
    print(f"net (signed)                     = {net:+10.1f}  ({100*net/A:+.4f}%)")
    print()
    total = overcut + uncut
    print(f"TOTAL geometric discrepancy      = {total:10.1f}  ({100*total/A:.4f}% of part)")
    print(f"scalar |dV| the verifier reports = {abs(net):10.1f}  ({100*abs(net)/A:.4f}% of part)")
    print(f"=> the volume check understates the true error by {total/abs(net):.2f}x")
    print()
    print(f"recogniser verdict: verified={rep['verified']} dvol_pct={rep['dvol_pct']}")


if __name__ == "__main__":
    main()
