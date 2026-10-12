#!/usr/bin/env python3
"""Aggregate results/<dataset>/*.json.   python report.py deepcad fusion360"""
import glob, json, os, statistics as st, sys
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))


def load(ds):
    return [json.load(open(f)) for f in sorted(glob.glob(os.path.join(ROOT, "results", ds, "*.json")))]


def summary(rows):
    n = len(rows)
    stat = Counter(r.get("status") for r in rows)
    built = [r for r in rows if r.get("iou") is not None]           # a tree that re-executes to a solid
    ious = [r["iou"] for r in built]
    all_iou = [r["iou"] if r.get("iou") is not None else 0.0 for r in rows]
    ver = [r for r in rows if r.get("status") == "VERIFIED"]
    ver_iou = [r["iou"] for r in ver if r.get("iou") is not None]
    single = [r for r in rows if r.get("input_solids") == 1]
    out = {
        "n": n, "status": dict(stat),
        "invalid_ratio": round(1 - len(built) / n, 4) if n else None,
        "mean_iou_valid": round(st.mean(ious), 4) if ious else None,
        "median_iou_valid": round(st.median(ious), 4) if ious else None,
        "mean_iou_all_invalid_as_0": round(st.mean(all_iou), 4) if n else None,
        "verified_rate": round(len(ver) / n, 4) if n else None,
        "verified_mean_iou": round(st.mean(ver_iou), 4) if ver_iou else None,
        "verified_min_iou": round(min(ver_iou), 4) if ver_iou else None,
        "verified_below_0.995": sum(1 for v in ver_iou if v < 0.995),
        "verified_below_0.95": sum(1 for v in ver_iou if v < 0.95),
        "iou_ge_0.99": round(sum(1 for v in all_iou if v >= 0.99) / n, 4) if n else None,
        "iou_ge_0.9": round(sum(1 for v in all_iou if v >= 0.9) / n, 4) if n else None,
        "iou_lt_0.5": round(sum(1 for v in all_iou if v < 0.5) / n, 4) if n else None,
        "multi_solid_inputs": n - len(single),
        "single_solid_mean_iou_valid": round(st.mean([r["iou"] for r in single if r.get("iou") is not None]), 4)
        if any(r.get("iou") is not None for r in single) else None,
        "median_wall_s": round(st.median([r["wall_seconds"] for r in rows if "wall_seconds" in r]), 1) if n else None,
        "mean_wall_s": round(st.mean([r["wall_seconds"] for r in rows if "wall_seconds" in r]), 1) if n else None,
        "mean_ops": round(st.mean([r["operations"] for r in rows if r.get("operations") is not None]), 2)
        if any(r.get("operations") is not None for r in rows) else None,
        "errors": Counter((r.get("error") or "")[:60] for r in rows if r.get("status") == "ERROR").most_common(5),
    }
    return out


if __name__ == "__main__":
    res = {ds: summary(load(ds)) for ds in sys.argv[1:]}
    print(json.dumps(res, indent=1))
    json.dump(res, open(os.path.join(ROOT, "results", "summary.json"), "w"), indent=1)
