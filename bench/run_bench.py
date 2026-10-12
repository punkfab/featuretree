#!/usr/bin/env python3
"""Run featuretree's step_recognize over a folder of STEP files, one subprocess per part.

    python run_bench.py <dataset> [--jobs N] [--timeout S] [--limit N] [--shard i/n]

Reads  data/<dataset>/norm/*.step, writes results/<dataset>/<id>.json (resumable) and the
recovered IR to results/<dataset>/ir/<id>.ir.json.

Per part: verdict (VERIFIED / PARTIAL / ERROR / TIMEOUT), feature count, recognition time, and a
Boolean-free IoU of the re-emitted tree against ALL solids of the input (iou_check.registered_iou
family: best of 24 axis-aligned rotations, bbox-min alignment, so a lower bound).
"""
import argparse, json, os, signal, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))
FT = os.path.join(os.path.dirname(ROOT), "featuretree")
PY = os.path.join(ROOT, "ft_env", "bin", "python")

WORKER = r'''
import json, os, sys, time, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
path, ir_out = sys.argv[1], sys.argv[2]
res = {"part": os.path.basename(path)}
t0 = time.time()
try:
    import b3d_emit, step_recognize as sr, iou_check
    from build123d import import_step
    orig = iou_check.solid_part(import_step(path))
    res["input_faces"] = len(orig.faces())
    res["input_solids"] = len(orig.solids())
    t0 = time.time()
    spec, rep = sr.recognize(path)
    res["recognise_seconds"] = round(time.time() - t0, 2)
    feats = spec.get("features", [])
    res.update(status="VERIFIED" if rep.get("verified") else "PARTIAL",
               features=len(feats), operations=sum(1 for f in feats if f.get("kind") != "sketch"),
               method=rep.get("method"), dvol_pct=rep.get("dvol_pct"), gate_iou_pct=rep.get("iou_pct"),
               reason=rep.get("reason"))
    json.dump(spec, open(ir_out, "w"), default=str)
    try:
        out = b3d_emit.emit(spec)
        rec = iou_check.solid_part(out[0] if isinstance(out, tuple) else out)
        best_rot, best_p = None, -1.0
        for rot in iou_check.ROTATIONS:
            p, _ = iou_check.iou(orig, iou_check.register(rec, orig, rot), n=1500, seed=1)
            if p > best_p:
                best_rot, best_p = list(rot), p
            if p > 0.985:
                break
        p, ci = iou_check.iou(orig, iou_check.register(rec, orig, best_rot), n=20000, seed=2)
        res.update(iou=p, iou_ci=ci, rot=best_rot)
    except Exception as exc:
        res.update(iou=None, iou_error=f"{type(exc).__name__}: {exc}"[:200])
except Exception as exc:
    res.update(status="ERROR", error=f"{type(exc).__name__}: {exc}"[:300])
res["seconds"] = round(time.time() - t0, 2)
print("@@JSON@@" + json.dumps(res))
'''


def run_one(path, out_dir, timeout):
    pid = os.path.splitext(os.path.basename(path))[0]
    dst = os.path.join(out_dir, pid + ".json")
    if os.path.exists(dst):
        return json.load(open(dst))
    t0 = time.time()
    p = subprocess.Popen([PY, "-c", WORKER, path, os.path.join(out_dir, "ir", pid + ".ir.json")],
                         cwd=FT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                         start_new_session=True)
    try:
        out, _ = p.communicate(timeout=timeout)
        line = [l for l in out.splitlines() if l.startswith("@@JSON@@")]
        res = json.loads(line[-1][8:]) if line else {"part": pid, "status": "ERROR",
                                                     "error": f"crash rc={p.returncode}"}
    except subprocess.TimeoutExpired:
        res = {"part": pid, "status": "TIMEOUT"}
    finally:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    res["wall_seconds"] = round(time.time() - t0, 2)
    json.dump(res, open(dst, "w"))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--stride", type=int, default=1, help="take every k-th part (sorted ids)")
    a = ap.parse_args()
    src = os.path.join(ROOT, "data", a.dataset, "norm")
    out_dir = os.path.join(ROOT, "results", a.dataset)
    os.makedirs(os.path.join(out_dir, "ir"), exist_ok=True)
    paths = sorted(os.path.join(src, f) for f in os.listdir(src) if f.endswith((".step", ".stp")))
    import random
    random.Random(0).shuffle(paths)      # fixed random order: any prefix is a random sample
    if a.limit:
        paths = paths[:a.limit]
    t0, done = time.time(), 0
    with ThreadPoolExecutor(a.jobs) as ex:
        for r in ex.map(lambda p: run_one(p, out_dir, a.timeout), paths):
            done += 1
            if done % 25 == 0:
                print(f"{done}/{len(paths)} {time.time() - t0:.0f}s", flush=True)
    print("done", done, f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
