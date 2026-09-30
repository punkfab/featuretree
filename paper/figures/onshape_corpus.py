#!/usr/bin/env python3
"""onshape_corpus.py — the Onshape backend on every recovered NIST feature tree.

For each IR in paper/figures/recovered/, build it as a native Onshape Part Studio (onshape_emit),
export STEP, and gate it against the build123d reference build of the same IR (volume <= 0.5%,
Boolean-free IoU >= 99.5%). Records features built, wall time, the IoU, and the Part Studio URL.
Results are cached per part in paper/figures/onshape/<part>.json; --fresh rebuilds.

    python3 paper/figures/onshape_corpus.py [--fresh] [part-substring ...]
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import cad_verify  # noqa: E402
import onshape_emit  # noqa: E402
import onshape_translate  # noqa: E402

OUT = Path(__file__).resolve().parent / "onshape"


def run(p):
    spec = json.loads(p.read_text())["spec"]
    spec["name"] = p.name.split(".")[0]
    t0 = time.time()
    did, wid, eid, rows = onshape_emit.emit(spec)
    t_build = time.time() - t0
    step = onshape_translate.export_step(did, wid, eid, OUT / f"{spec['name']}.onshape.step")
    ver = cad_verify.verify(step, spec, samples=20000)
    fails = [r for r in rows if not r["ok"]]
    return {"part": spec["name"], "features": len(rows), "built": len(rows) - len(fails),
            "failures": fails[:10], "build_s": round(t_build, 1), **ver,
            "url": f"https://cad.onshape.com/documents/{did}/w/{wid}/e/{eid}"}


def main():
    OUT.mkdir(exist_ok=True)
    fresh = "--fresh" in sys.argv
    pick = [a for a in sys.argv[1:] if not a.startswith("--")]
    for p in sorted((ROOT / "paper/figures/recovered").glob("*.stp.json")):
        if pick and not any(k in p.name for k in pick):
            continue
        cache = OUT / (p.name.split(".")[0] + ".json")
        if cache.exists() and not fresh:
            r = json.loads(cache.read_text())
        else:
            try:
                r = run(p)
            except SystemExit as e:
                r = {"part": p.name.split(".")[0], "error": str(e)[:400]}
                if "quota" in str(e):                # not a result: print it, cache nothing, stop
                    print(json.dumps(r), flush=True)
                    break
            cache.write_text(json.dumps(r, indent=1))
        print(json.dumps({k: r.get(k) for k in ("part", "built", "features", "build_s", "iou_pct",
                                                "dvol_pct", "verdict", "error")}), flush=True)


if __name__ == "__main__":
    main()
