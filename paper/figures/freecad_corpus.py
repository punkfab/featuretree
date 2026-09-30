#!/usr/bin/env python3
"""freecad_corpus.py — the FreeCAD backend on every recovered NIST feature tree.

For each IR in paper/figures/recovered/, emit a native PartDesign .FCStd with gen.emit (headless
freecadcmd), take the STEP fc_build writes beside it, and gate it against the build123d reference
build of the same IR (volume <= 0.5%, Boolean-free IoU >= 99.5%). Cached per part in
paper/figures/freecad/<part>.json; --fresh rebuilds.

    python3 paper/figures/freecad_corpus.py [--fresh] [part-substring ...]
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import cad_verify  # noqa: E402
import gen  # noqa: E402

OUT = Path(__file__).resolve().parent / "freecad"


def run(p):
    spec = json.loads(p.read_text())["spec"]
    name = p.name.split(".")[0]
    spec["name"] = name
    t0 = time.time()
    res = gen.emit(spec, str(OUT / f"{name}.FCStd"))
    t_build = time.time() - t0
    ver = cad_verify.verify(OUT / f"{name}.step", spec, samples=20000)
    return {"part": name, "features": len(spec["features"]), "tree_objects": len(res["tree"]),
            "build_s": round(t_build, 1), **ver}


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
            except BaseException as e:           # gen.emit raises SystemExit on a failed build
                r = {"part": p.name.split(".")[0], "error": f"{type(e).__name__}: {e}"[:400]}
            cache.write_text(json.dumps(r, indent=1))
        print(json.dumps({k: r.get(k) for k in ("part", "tree_objects", "build_s", "iou_pct",
                                                "dvol_pct", "verdict", "error")}), flush=True)


if __name__ == "__main__":
    main()
