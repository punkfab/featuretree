"""image_recognize.py — a rough feature tree from ONE picture of a part (prototype).

A STEP file carries exact geometry, so step_recognize can verify what it recovers. A picture
carries neither scale nor the hidden side, so this path is weaker by construction and says so:

  1. PROPOSE   a vision model (Claude) looks at the image and writes the part as IR features
               (or pass --spec with a tree written by anyone / anything else);
  2. BUILD     ir.validate + the build123d reference; errors go back to the model;
  3. POSE      search the orthographic camera whose silhouette of the built solid best overlaps
               the part's silhouette in the image;
  4. FIT       (--fit) adjust the dimensions the silhouette can see — pad lengths and the
               outlines of padded sketches — to raise that overlap;
  5. REFINE    (--refine N) show the model its render next to the image and ask again.

The result is never VERIFIED. Its status is ROUGH with a silhouette overlap: that number checks
outline and proportions from one viewpoint only. Holes and pockets inside the outline, anything
on the far side, and absolute size are the model's guess. --size pins the largest extent in mm.

    python3 image_recognize.py part.png --emit out.json --overlay check.png   # needs an API key
    python3 image_recognize.py part.png --spec guess.json --fit --size 60     # no model call
    python3 image_recognize.py part.png --fit --mesh scan.stl    # size and a 3D check from a scan
"""
import base64
import copy
import inspect
import json
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ir as IR

MODEL = "claude-opus-5-5"
N = 256                      # silhouettes are compared on an N x N grid
FILL = 0.86                  # the part's larger extent, as a fraction of the grid


# --- the image ---------------------------------------------------------------------------------
def foreground_mask(image_path, tol=24):
    """The part's silhouette: pixels unlike the border colour, largest connected blob, holes
    filled. Assumes a plain background (a render, a scan viewer, a product shot)."""
    import cv2
    img = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"cannot read image: {image_path}")
    h, w = img.shape[:2]
    b = max(2, min(h, w) // 50)
    border = np.concatenate([img[:b].reshape(-1, 3), img[-b:].reshape(-1, 3),
                             img[:, :b].reshape(-1, 3), img[:, -b:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    diff = np.abs(img.astype(np.int16) - bg).max(axis=2)
    raw = cv2.morphologyEx((diff > tol).astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(raw, connectivity=8)
    if n < 2:
        raise ValueError("no foreground found: the image needs a plain background")
    mask = (lab == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(mask, cs, -1, 1, thickness=cv2.FILLED)
    return mask.astype(bool)


def _bbox(mask):
    ys, xs = np.nonzero(mask)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def _normalise(mask):
    """Crop to the silhouette and rescale so its larger extent fills FILL of an N x N grid. Returns
    (grid mask, pixels per grid cell, bbox centre in image pixels) to map a fit back onto the image."""
    import cv2
    x0, y0, x1, y1 = _bbox(mask)
    s = FILL * N / max(x1 - x0, y1 - y0)
    m = np.float32([[s, 0, N / 2 - s * (x0 + x1) / 2], [0, s, N / 2 - s * (y0 + y1) / 2]])
    out = cv2.warpAffine(mask.astype(np.uint8) * 255, m, (N, N), flags=cv2.INTER_AREA)
    return out > 127, 1.0 / s, ((x0 + x1) / 2, (y0 + y1) / 2)


# --- the solid, as seen from a camera -------------------------------------------------------------
def _mesh(part):
    box = part.bounding_box()
    tol = max(box.size.X, box.size.Y, box.size.Z) / 400
    vs, ts = part.tessellate(tol, 0.2)
    return np.array([[v.X, v.Y, v.Z] for v in vs]), np.array(ts, dtype=np.int64)


def _rot(az, el, roll):
    """World -> camera for an orthographic camera at azimuth `az`, elevation `el` (degrees; el = 90
    looks straight down -Z), rolled `roll` about the view axis. Camera x is right, y up, z toward
    the viewer."""
    a, t, r = math.radians(az), math.radians(el - 90), math.radians(roll)
    rz = np.array([[math.cos(a), math.sin(a), 0], [-math.sin(a), math.cos(a), 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, math.cos(t), -math.sin(t)], [0, math.sin(t), math.cos(t)]])
    rr = np.array([[math.cos(r), -math.sin(r), 0], [math.sin(r), math.cos(r), 0], [0, 0, 1]])
    return rr @ rx @ rz


def _project(verts, cam):
    """Vertices -> grid pixels (and depth) for cam = (az, el, roll, zoom, dx, dy). zoom 1, dx = dy
    = 0 centres the projected bounding box and fills FILL of the grid, like _normalise."""
    az, el, roll, zoom, dx, dy = cam
    p = verts @ _rot(az, el, roll).T
    lo, hi = p[:, :2].min(axis=0), p[:, :2].max(axis=0)
    s = zoom * FILL * N / max(hi - lo)
    c = (lo + hi) / 2
    xy = np.empty((len(p), 2))
    xy[:, 0] = N / 2 + dx + s * (p[:, 0] - c[0])
    xy[:, 1] = N / 2 + dy - s * (p[:, 1] - c[1])
    return xy, p[:, 2]


def silhouette(mesh, cam):
    import cv2
    verts, tris = mesh
    xy, _ = _project(verts, cam)
    t = xy[tris]
    e1, e2 = t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]
    front = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0] < 0        # a closed solid: front faces cover it
    img = np.zeros((N, N), np.uint8)
    for tri in np.round(t[front] * 16).astype(np.int32):          # one by one: fillPoly XORs overlaps
        cv2.fillConvexPoly(img, tri, 1, shift=4)
    return img.astype(bool)


def _iou(a, b):
    u = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum()) / u if u else 0.0


def fit_camera(mesh, target, start=None):
    """The camera whose silhouette best overlaps `target` (a normalised grid mask). A coarse sweep of
    azimuth / elevation / quarter-turn rolls, then Nelder-Mead on all six parameters; with `start`
    the sweep is coarser and starts from that camera. Returns (cam, overlap)."""
    from scipy.optimize import minimize

    def cost(c):
        return 1.0 - _iou(silhouette(mesh, c), target)

    def top(cands, k):
        return [c for _, c in sorted((cost(c), c) for c in cands)[:k]]

    if start is None:
        starts = top([(az, el, roll, 1.0, 0.0, 0.0) for az in range(0, 360, 15)
                      for el in range(-75, 91, 15) for roll in (0, 90, 180, 270)], 4)
    else:      # a changed shape can move the best view a long way, so sweep again, more coarsely
        starts = top([tuple(start)] + [(az, el, start[2] + roll, 1.0, 0.0, 0.0)
                                       for az in range(0, 360, 30) for el in range(-75, 91, 15)
                                       for roll in (0, 90, 180, 270)], 2)
    best = None
    for s in starts:
        r = minimize(cost, s, method="Nelder-Mead",
                     options={"initial_simplex": _simplex(s, (6, 6, 6, 0.04, 4, 4)),
                              "xatol": 0.05, "fatol": 1e-4, "maxiter": 400})
        if best is None or r.fun < best[1]:
            best = (tuple(float(v) for v in r.x), float(r.fun))
    return best[0], 1.0 - best[1]


def _edges(gray):
    import cv2
    e = cv2.Canny(cv2.GaussianBlur(gray, (0, 0), 1.2), 30, 90)
    return cv2.GaussianBlur(e.astype(np.float32), (0, 0), 2.0)


def align_interior(mesh, cam, target, gray, slack=0.005):
    """A silhouette cannot fix the spin of a round part, nor always tell a view from above from one
    from below. Among cameras whose outline overlap stays within `slack` of `cam`'s, pick the one whose
    rendered interior edges (holes, steps) best correlate with the image's. Returns (cam, score):
    score is that correlation, in [-1, 1], measured inside the outline only."""
    import cv2
    inside = cv2.erode(target.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    want = _edges(gray)[inside]
    want = want - want.mean()
    base = _iou(silhouette(mesh, cam), target)

    def score(c):
        got = _edges(cv2.cvtColor(render(mesh, c), cv2.COLOR_BGR2GRAY))[inside]
        got = got - got.mean()
        d = float(np.linalg.norm(got) * np.linalg.norm(want))
        return float(got @ want) / d if d else 0.0

    best = (score(cam), cam)
    for el in (cam[1], -cam[1]):                    # seen from above, or the same outline from below
        for step in range(0, 360, 3):
            c = (cam[0] + step, el, *cam[2:])
            if _iou(silhouette(mesh, c), target) >= base - slack:
                best = max(best, (score(c), c))
    return best[1], best[0]


def _gray_grid(image_path, mask):
    """The image in grey, on the same N x N grid as _normalise(mask)."""
    import cv2
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    x0, y0, x1, y1 = _bbox(mask)
    s = FILL * N / max(x1 - x0, y1 - y0)
    m = np.float32([[s, 0, N / 2 - s * (x0 + x1) / 2], [0, s, N / 2 - s * (y0 + y1) / 2]])
    return cv2.warpAffine(img, m, (N, N), flags=cv2.INTER_AREA, borderValue=255)


def _simplex(x0, steps):
    x0 = np.asarray(x0, float)
    return np.vstack([x0] + [x0 + np.eye(len(x0))[i] * st for i, st in enumerate(steps)])


def render(mesh, cam, size=N):
    """A flat-shaded picture of the solid from `cam` (painter's algorithm, back faces culled): what
    the human, and the model on a refine round, compare against the image."""
    import cv2
    verts, tris = mesh
    xy, z = _project(verts, cam)
    xy = xy * (size / N)
    p = verts @ _rot(*cam[:3]).T
    t = p[tris]
    nrm = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    ln = np.linalg.norm(nrm, axis=1)
    keep = (nrm[:, 2] > 0) & (ln > 0)
    nrm = nrm[keep] / ln[keep, None]
    shade = 70 + 170 * np.clip(nrm @ np.array([-0.35, 0.45, 0.82]), 0, 1)
    order = np.argsort(z[tris[keep]].mean(axis=1))
    img = np.full((size, size, 3), 255, np.uint8)
    pts = np.round(xy[tris[keep]] * 16).astype(np.int32)
    for i in order:
        g = int(shade[i])
        cv2.fillConvexPoly(img, pts[i], (g, int(g * 0.72), int(g * 0.62)), shift=4, lineType=cv2.LINE_AA)
    return img


def overlay(image_path, mask, mesh, cam, out_path, size=512):
    """Three panels: the image (cropped to the part), the render from the fitted camera, and where
    the two silhouettes disagree (image only = red, model only = blue)."""
    import cv2
    img = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    x0, y0, x1, y1 = _bbox(mask)
    s = FILL * size / max(x1 - x0, y1 - y0)
    m = np.float32([[s, 0, size / 2 - s * (x0 + x1) / 2], [0, s, size / 2 - s * (y0 + y1) / 2]])
    left = cv2.warpAffine(img, m, (size, size), flags=cv2.INTER_AREA, borderValue=(255, 255, 255))
    mid = render(mesh, cam, size)
    a = cv2.resize(_normalise(mask)[0].astype(np.uint8), (size, size), interpolation=cv2.INTER_NEAREST) > 0
    b = cv2.resize(silhouette(mesh, cam).astype(np.uint8), (size, size), interpolation=cv2.INTER_NEAREST) > 0
    right = np.full((size, size, 3), 255, np.uint8)
    right[a & b] = (200, 200, 200)
    right[a & ~b] = (60, 60, 220)
    right[b & ~a] = (220, 120, 40)
    cv2.imwrite(str(out_path), np.hstack([left, mid, right]))
    return str(out_path)


# --- the IR: build, scale, and the dimensions a silhouette can see --------------------------------
def build(spec):
    """Validate and build a spec. Returns (mesh, extents, problems); mesh is None if it failed."""
    import b3d_emit
    try:
        problems = IR.validate(spec)
    except Exception as e:                                           # noqa: BLE001
        return None, None, [f"spec is malformed: {type(e).__name__}: {e}"]
    if problems:
        return None, None, problems
    try:
        part, res = b3d_emit.emit(copy.deepcopy(spec))
    except Exception as e:                                           # noqa: BLE001
        return None, None, [f"build failed: {type(e).__name__}: {e}"]
    if not res["volume"] > 0:
        return None, None, ["build produced no solid"]
    sz = part.bounding_box().size
    return _mesh(part), (sz.X, sz.Y, sz.Z), []


def scale_spec(spec, k):
    """Every length in the spec multiplied by k (angles, counts and arc bulges untouched)."""
    def pts(poly):
        return [[p[0] * k, p[1] * k, *p[2:]] for p in poly]
    out = copy.deepcopy(spec)
    for f in out["features"]:
        kind = f["kind"]
        if kind == "sketch":
            f["circles"] = [[c * k for c in cc] for cc in f.get("circles", [])]
            f["rects"] = [[c * k for c in rr] for rr in f.get("rects", [])]
            f["polys"] = [pts(p) for p in f.get("polys", [])]
            if f.get("ngons"):
                f["ngons"] = [[g[0] * k, g[1] * k, g[2] * k, *g[3:]] for g in f["ngons"]]
        elif kind == "chamfer":
            f["distance"] *= k
        elif kind in ("pad", "pocket"):
            if f.get("length") is not None:
                f["length"] *= k
        elif kind == "fillet":
            f["radius"] *= k
        elif kind == "polar_pocket":
            for key in ("radius", "length", "mount_r", "z"):
                f[key] *= k
        elif kind == "prism_cut":
            f["origin"] = [c * k for c in f["origin"]]
            f["depth"] *= k
            f["polys"] = [pts(p) for p in f["polys"]]
    return out


def _round(spec, nd=3):
    def r(v):
        if isinstance(v, float):
            return round(v, nd)
        if isinstance(v, list):
            return [r(x) for x in v]
        if isinstance(v, dict):
            return {a: r(b) for a, b in v.items()}
        return v
    return r(spec)


def _sketch_box(f):
    xs, ys = [], []
    for cx, cy, r in f.get("circles", []):
        xs += [cx - r, cx + r]; ys += [cy - r, cy + r]
    for w, h, cx, cy in f.get("rects", []):
        xs += [cx - w / 2, cx + w / 2]; ys += [cy - h / 2, cy + h / 2]
    for poly in f.get("polys", []) + [IR.ngon_poly(*g) for g in f.get("ngons", [])]:
        xs += [p[0] for p in poly]; ys += [p[1] for p in poly]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def _round_sketch(f):
    """True if the sketch has circles or arcs, which only a uniform scale keeps round."""
    return bool(f.get("circles")) or bool(f.get("ngons")) or any(len(p) > 2 and p[2] for poly in f.get("polys", []) for p in poly)


def _scale_sketch(f, centre, sx, sy):
    """Stretch a sketch about `centre`: positions by (sx, sy); circles and arc outlines keep their
    shape and grow by sqrt(sx * sy) about their own centre."""
    cx0, cy0 = centre
    g = math.sqrt(sx * sy)

    def mv(x, y):
        return cx0 + (x - cx0) * sx, cy0 + (y - cy0) * sy
    f["circles"] = [[*mv(cx, cy), r * g] for cx, cy, r in f.get("circles", [])]
    f["rects"] = [[w * sx, h * sy, *mv(cx, cy)] for w, h, cx, cy in f.get("rects", [])]
    if f.get("ngons"):
        f["ngons"] = [[*mv(n[0], n[1]), n[2] * g, *n[3:]] for n in f["ngons"]]
    polys = []
    for poly in f.get("polys", []):
        if any(len(p) > 2 and p[2] for p in poly):
            mx, my = sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)
            nx, ny = mv(mx, my)
            polys.append([[nx + (p[0] - mx) * g, ny + (p[1] - my) * g, *p[2:]] for p in poly])
        else:
            polys.append([[*mv(p[0], p[1]), *p[2:]] for p in poly])
    f["polys"] = polys


def _dims(spec):
    """The dimensions a silhouette can constrain, as (label, feature index, key): each pad's length,
    and for each sketch a pad consumes one scale (round outlines) or an x and a y stretch."""
    padded = {f["sketch"] for f in spec["features"] if f["kind"] == "pad"}
    out = []
    for i, f in enumerate(spec["features"]):
        if f["kind"] == "pad":
            out.append((f"{f['name']}.length", i, "length"))
        elif f["kind"] == "sketch" and f["name"] in padded and _sketch_box(f):
            if _round_sketch(f):
                out.append((f"{f['name']} scale", i, "s"))
            else:
                out.append((f"{f['name']} x", i, "x"))
                out.append((f"{f['name']} y", i, "y"))
    return out


def _apply(spec, dims, factors):
    """The spec with each dimension multiplied by its factor. A sketch no pad consumes (a hole
    pattern, a pocket outline) cannot be seen in a silhouette, so it follows the smallest padded
    outline that contains it: same stretch, about that outline's centre."""
    out = copy.deepcopy(spec)
    stretch = {}                                    # feature index -> [sx, sy]
    for (_, i, key), k in zip(dims, factors):
        if key == "length":
            out["features"][i]["length"] *= k
        else:
            sxy = stretch.setdefault(i, [1.0, 1.0])
            if key in ("s", "x"):
                sxy[0] *= k
            if key in ("s", "y"):
                sxy[1] *= k
    boxes = {i: _sketch_box(spec["features"][i]) for i in stretch}
    for i, f in enumerate(out["features"]):
        if f["kind"] != "sketch":
            continue
        if i in stretch:
            x0, y0, x1, y1 = boxes[i]
            _scale_sketch(f, ((x0 + x1) / 2, (y0 + y1) / 2), *stretch[i])
            continue
        box = _sketch_box(f)
        if box is None:
            continue
        around = [((b[2] - b[0]) * (b[3] - b[1]), j) for j, b in boxes.items()
                  if b[0] <= box[0] and b[1] <= box[1] and box[2] <= b[2] and box[3] <= b[3]]
        if around:
            j = min(around)[1]
            x0, y0, x1, y1 = boxes[j]
            _scale_sketch(f, ((x0 + x1) / 2, (y0 + y1) / 2), *stretch[j])
    return out


def fit_dimensions(spec, target, cam, lo=0.4, hi=2.5, maxiter=160):
    """Scale the silhouette-visible dimensions (each within [lo, hi] of the proposal) to raise the
    overlap, re-posing the camera locally at every step. Returns (spec, mesh, cam, overlap, changes)."""
    from scipy.optimize import minimize
    dims = _dims(spec)
    mesh0, _, _ = build(spec)
    best = {"score": _iou(silhouette(mesh0, cam), target), "spec": spec, "mesh": mesh0, "cam": cam,
            "x": np.zeros(len(dims))}
    if not dims:
        return spec, mesh0, cam, best["score"], {}

    def cost(x):
        if np.any(np.abs(x) > 1):
            return 1.0
        cand = _apply(spec, dims, [math.exp(v * math.log(hi if v > 0 else 1 / lo)) for v in x])
        mesh, _, problems = build(cand)
        if problems:
            return 1.0
        c, score = fit_camera(mesh, target, start=best["cam"])
        if score > best["score"]:
            best.update(score=score, spec=cand, mesh=mesh, cam=c, x=np.array(x))
        return 1.0 - score

    minimize(cost, np.zeros(len(dims)), method="Nelder-Mead",
             options={"initial_simplex": _simplex(np.zeros(len(dims)), [0.12] * len(dims)),
                      "xatol": 0.004, "fatol": 2e-4, "maxiter": maxiter})
    changes = {}
    for (label, *_), v in zip(dims, best["x"]):
        k = math.exp(v * math.log(hi if v > 0 else 1 / lo))
        if abs(k - 1) > 0.01:
            changes[label] = round(k, 3)
    return best["spec"], best["mesh"], best["cam"], best["score"], changes


# --- the model --------------------------------------------------------------------------------------
def system_prompt():
    """The IR, taken from ir.py's own docstrings so the prompt cannot drift from the code."""
    docs = "\n\n".join(f"{fn.__name__}{inspect.signature(fn)}\n{inspect.getdoc(fn)}"
                       for fn in (IR.sketch, IR.pad, IR.pocket, IR.fillet, IR.chamfer, IR.revolve,
                                  IR.polar_pocket, IR.prism_cut))
    return f"""You reconstruct a mechanical part from a single picture as a parametric feature tree, \
written in a small JSON IR. A CAD system will rebuild the tree and a person will edit it, so prefer \
the features a designer would have used (a base pad, a boss padded on its top face, a through hole, \
a ring of bolt holes) over a literal trace of the picture.

Each feature is a JSON object with a "kind" and the keys of the matching constructor below.

{docs}

Conventions:
- Millimetres. +Z is up; build the part standing the way it would sit on a table, on the XY plane, \
centred on the Z axis when it has one. A pad grows +Z from its sketch.
- To stack a boss on an earlier pad, attach its sketch with "on": {{"face_of": "<pad name>", \
"side": "top"}}. A through pocket ignores where its sketch sits; a blind pocket cuts down from the \
top face.
- A sketch's circles and rects are each a separate filled region. In "polys" the first wire is the \
outline and later wires are holes in it. A wire is a list of [x, y] points, closed automatically; \
[x, y, bulge] makes the edge to the next point a circular arc (bulge = tan(sweep / 4)).
- A regular polygon (a hex socket, a square drive) goes in "ngons", never as typed-out corners.
- Look for broken edges: a light band along a rim is a chamfer or a round. Add a chamfer (or a \
fillet, if it reads as rounded) for each one you can see, after the features whose edges it \
breaks, selecting with {{"edges_of": "<pad or pocket>", "side": "top" | "bottom"}}. Their size is a \
guess from the band's width; say so.
- Feature names are unique, short and meaningful (they become the labels in the CAD tree).
- A picture has no scale. Unless the image shows a dimension, choose a plausible overall size and \
keep the proportions you can see. Infer hidden features only where symmetry makes them likely (the \
fourth hole of a bolt circle), and list every such assumption.

Example (a 40 x 30 x 10 plate with an 8 mm through hole):
{json.dumps(IR.sample_plate())}

Reply with one JSON object and nothing else:
{{"name": "...", "features": [...], "assumptions": ["..."]}}"""


def _image_block(path):
    ext = os.path.splitext(str(path))[1].lower().lstrip(".")
    media = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
             "gif": "image/gif"}.get(ext)
    if media is None:
        raise ValueError(f"unsupported image type: .{ext}")
    with open(path, "rb") as fh:
        data = base64.standard_b64encode(fh.read()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}


def _parse(text):
    """The first JSON object in the reply -> (spec, assumptions)."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in the reply")
    d = json.loads(m.group(0))
    if not isinstance(d.get("features"), list):
        raise ValueError('the reply has no "features" list')
    return {"name": d.get("name", "part"), "features": d["features"]}, list(d.get("assumptions", []))


class Proposer:
    """One conversation with the model about one image. ask() returns its reply text; the history
    is append-only so its earlier reasoning stays valid."""

    def __init__(self, image_path, model=MODEL, effort="high"):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model, self.effort = model, effort
        self.messages = [{"role": "user", "content": [
            _image_block(image_path),
            {"type": "text", "text": "Write this part as a feature tree."}]}]

    def ask(self, content=None):
        if content is not None:
            self.messages.append({"role": "user", "content": content})
        with self.client.messages.stream(
                model=self.model, max_tokens=32000, system=system_prompt(),
                thinking={"type": "adaptive"}, output_config={"effort": self.effort},
                messages=self.messages) as stream:
            msg = stream.get_final_message()
        if msg.stop_reason == "refusal":
            raise RuntimeError("the model declined this image")
        if msg.stop_reason == "max_tokens":
            raise RuntimeError("the reply was cut off at max_tokens")
        self.messages.append({"role": "assistant", "content": msg.content})
        return "".join(b.text for b in msg.content if b.type == "text")


def propose(proposer, feedback=None, retries=3):
    """Ask until the reply parses, validates and builds (errors are sent back, up to `retries`).
    Returns (spec, assumptions, mesh, extents)."""
    for _ in range(retries + 1):
        text = proposer.ask(feedback)
        try:
            spec, assumptions = _parse(text)
        except ValueError as e:
            feedback = f"That reply could not be read ({e}). Reply with the one JSON object only."
            continue
        mesh, extents, problems = build(spec)
        if not problems:
            return spec, assumptions, mesh, extents
        feedback = ("That tree does not build:\n- " + "\n- ".join(problems[:8])
                    + "\nFix it and reply with the full corrected JSON object.")
    raise RuntimeError(f"no buildable tree after {retries + 1} attempts: {problems[:3]}")


# --- the whole path -----------------------------------------------------------------------------------
def recognize(image_path, spec=None, fit=False, refine=0, size=None, overlay_path=None, model=MODEL,
              mesh_path=None):
    """Image -> {"status": "ROUGH", "spec", "silhouette_iou", "camera", "assumptions", "warnings"}.
    With `spec` no model is called: the given tree is posed (and fitted) against the image. With
    `mesh_path` (a scan of the same part) the tree takes its size from the mesh, and the result
    gains "mesh": the volumetric overlap with it (mesh_compare.compare)."""
    import tempfile
    mask = foreground_mask(image_path)
    target = _normalise(mask)[0]
    gray = _gray_grid(image_path, mask)
    warnings, assumptions, rounds = [], [], []

    if spec is not None:
        mesh, extents, problems = build(spec)
        if problems:
            raise ValueError("the given spec does not build: " + "; ".join(problems[:5]))
        cam, score = fit_camera(mesh, target)
        proposer = None
    else:
        proposer = Proposer(image_path, model=model)
        spec, assumptions, mesh, extents = propose(proposer)
        cam, score = fit_camera(mesh, target)
        rounds.append(round(100 * score, 2))
        for _ in range(refine):
            with tempfile.TemporaryDirectory() as td:
                cam = align_interior(mesh, cam, target, gray)[0]
                shot = overlay(image_path, mask, mesh, cam, os.path.join(td, "check.png"))
                feedback = [_image_block(shot), {"type": "text", "text": (
                    f"Left: the picture. Middle: your tree, rebuilt and viewed from the best-matching "
                    f"camera. Right: where the outlines disagree (red = only in the picture, blue = "
                    f"only in your tree). Outline overlap is {100 * score:.1f}%. Compare the three, "
                    f"including features inside the outline that the overlap cannot see, and reply "
                    f"with the full corrected JSON object.")}]
            try:
                spec2, assumptions2, mesh2, _ = propose(proposer, feedback)
            except RuntimeError as e:
                warnings.append(f"refine round abandoned: {e}")
                break
            cam2, score2 = fit_camera(mesh2, target)
            rounds.append(round(100 * score2, 2))
            if score2 >= score:            # keep the better outline; the model saw both either way
                spec, assumptions, mesh, cam, score = spec2, assumptions2, mesh2, cam2, score2

    changes = {}
    if fit:
        spec, mesh, cam, score, changes = fit_dimensions(spec, target, cam)
    scan = None
    if mesh_path:
        import mesh_compare
        scan = mesh_compare.load(mesh_path)
        size = size or float(max(scan.extents))
    if size:
        _, extents, _ = build(spec)
        spec = scale_spec(spec, float(size) / max(extents))
    else:
        warnings.append("absolute size is a guess: a picture has no scale (pass --size)")
    spec = _round(spec)
    mesh, extents, problems = build(spec)
    if problems:
        raise RuntimeError("the final spec does not build: " + "; ".join(problems[:5]))
    cam, interior = align_interior(mesh, cam, target, gray)
    score = _iou(silhouette(mesh, cam), target)
    hidden = [f["name"] for f in spec["features"]
              if f["kind"] in ("pocket", "prism_cut", "polar_pocket", "fillet", "chamfer")]
    if hidden:
        warnings.append("not checked by the overlap (inside the outline, or too small to move it): "
                        + ", ".join(hidden))
    out = {"status": "ROUGH", "image": os.path.basename(str(image_path)), "spec": spec,
           "silhouette_iou": round(100 * float(score), 2), "interior_match": round(float(interior), 3),
           "camera": {"azimuth": round(cam[0] % 360, 1), "elevation": round(cam[1], 1),
                      "roll": round(cam[2] % 360, 1)},
           "extents_mm": [round(e, 2) for e in extents], "assumptions": assumptions,
           "warnings": warnings}
    if scan is not None:
        out["mesh"] = {"file": os.path.basename(str(mesh_path)), **mesh_compare.compare(spec, scan)}
    if changes:
        out["fitted"] = changes
    if rounds:
        out["rounds"] = rounds
    if overlay_path:
        out["overlay"] = overlay(image_path, mask, mesh, cam, overlay_path)
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(description="A rough feature tree from one picture of a part.")
    ap.add_argument("image")
    ap.add_argument("--spec", help="pose / fit this IR JSON against the image instead of asking a model")
    ap.add_argument("--fit", action="store_true", help="fit silhouette-visible dimensions")
    ap.add_argument("--refine", type=int, default=0, help="rounds of render-and-compare with the model")
    ap.add_argument("--size", type=float, help="largest extent of the part in mm")
    ap.add_argument("--mesh", help="a scan (STL) of the same part: gives the size and a 3D overlap check")
    ap.add_argument("--emit", help="write the result JSON here")
    ap.add_argument("--overlay", help="write the image | render | outline-difference picture here")
    ap.add_argument("--model", default=MODEL)
    a = ap.parse_args()
    spec = None
    if a.spec:
        with open(a.spec) as fh:
            spec = json.load(fh)
        spec = spec.get("spec", spec)
    r = recognize(a.image, spec=spec, fit=a.fit, refine=a.refine, size=a.size,
                  overlay_path=a.overlay, model=a.model, mesh_path=a.mesh)
    if a.emit:
        with open(a.emit, "w") as fh:
            json.dump(r, fh, indent=1)
    print(f"{r['status']}  silhouette overlap {r['silhouette_iou']}%  interior match {r['interior_match']}  "
          f"{len(r['spec']['features'])} features  extents {r['extents_mm']} mm")
    if "mesh" in r:
        print(f"against {r['mesh']['file']}: overlap {r['mesh']['iou_pct']}%  volume {r['mesh']['dvol_pct']:+}%")
    for f in r["spec"]["features"]:
        print(f"  {f['kind']:<12} {f['name']}")
    for k, v in r.get("fitted", {}).items():
        print(f"  fitted {k} x{v}")
    for w in r["assumptions"]:
        print(f"  assumed: {w}")
    for w in r["warnings"]:
        print(f"  note: {w}")


if __name__ == "__main__":
    main()
