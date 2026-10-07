"""mesh_compare.py — measure a scanned mesh, and score a feature tree against it.

A scan (STL) is real geometry at real scale, which a picture is not. It is still not a feature
tree, and its edges are soft, so this does three modest things by slicing the mesh across its Z axis:

  measure   the stepped outline (each level's diameter and height), the holes at each level
            (round, or a regular polygon with its across-flats size), and how far each rim is
            broken (chamfer / round), with the slice spacing as the resolution;
  tree      for round stepped parts with through holes, a feature tree built from those
            measurements: one size per recognised shape, so a hexagon comes out regular;
  compare   a volumetric overlap (IoU) between the mesh and an IR spec's solid, summed over
            slices, after centring both and searching the spin about Z.

It assumes the part's main axis is the mesh's Z axis and does not register anything else.

    python3 mesh_compare.py scan.stl                       # measure
    python3 mesh_compare.py scan.stl --spec tree.json      # ... and overlap with a tree
    python3 mesh_compare.py scan.stl --spec tree.json --scale   # scale the tree to the scan first
    python3 mesh_compare.py scan.stl --tree out.json       # a tree from the measurements, then its overlap
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def load(path):
    import trimesh
    return trimesh.load(str(path), force="mesh")


def slices(mesh, zs, min_area=1.0):
    """The mesh's cross-section at each z as one shapely geometry (None where it misses). Scan
    crumbs smaller than `min_area` are dropped."""
    from shapely.ops import unary_union
    out = []
    for sec in mesh.section_multiplane([0, 0, 0], [0, 0, 1], list(zs)):
        polys = [p.buffer(0) for p in sec.polygons_full if p.area >= min_area] if sec is not None else []
        out.append(unary_union(polys) if polys else None)
    return out


def _largest(g):
    return max(g.geoms, key=lambda p: p.area) if g.geom_type == "MultiPolygon" else g


def _ring_points(ring, n=720):
    """`n` points evenly spaced along a ring: a CAD mesh's hexagon has six vertices, a scan's has
    thousands, and the measurements below must not depend on which."""
    return np.array([ring.interpolate(t, normalized=True).coords[0] for t in np.linspace(0, 1, n, endpoint=False)])


def _flats(pts, centre, n, corner_deg, flat_tol=0.3, angle_tol=1.0):
    """Fit a line to the middle two thirds of each side of an n-gon. Returns each side's distance
    from the centre, the across-flats distances (opposite pairs, even n), how far the sides are from
    evenly turned, and `regular`: whether one size and one angle describe it within the tolerances
    (mm between the largest and smallest distance; degrees off 360 / n)."""
    cx, cy = centre
    ang = np.degrees(np.arctan2(pts[:, 1] - cy, pts[:, 0] - cx))
    dist, dirs = [], []
    for k in range(n):
        mid = corner_deg + (k + 0.5) * 360.0 / n
        p = pts[np.abs((ang - mid + 180) % 360 - 180) < 120.0 / n]
        q = p - p.mean(axis=0)
        nrm = np.linalg.svd(q, full_matrices=False)[2][1]
        if nrm @ (p.mean(axis=0) - (cx, cy)) < 0:
            nrm = -nrm
        dist.append(float(nrm @ (p.mean(axis=0) - (cx, cy))))
        dirs.append(math.degrees(math.atan2(nrm[1], nrm[0])))
    turn = [(dirs[(k + 1) % n] - dirs[k]) % 360 - 360.0 / n for k in range(n)]
    pairs = [dist[k] + dist[k + n // 2] for k in range(n // 2)] if n % 2 == 0 else [2 * d for d in dist]
    return {"across_flats": round(float(np.mean(pairs)), 3), "flat_pairs": [round(p, 3) for p in pairs],
            "flat_spread": round(max(pairs) - min(pairs), 3), "angle_error": round(max(abs(t) for t in turn), 2),
            "regular": bool(max(pairs) - min(pairs) <= flat_tol and max(abs(t) for t in turn) <= angle_tol)}


def _hole(ring):
    """A hole's centre, size and shape. A regular n-gon is recognised from its corners: n evenly
    spaced maxima of the radius, with min / max radius close to cos(pi / n)."""
    from shapely.geometry import Polygon
    p = Polygon(ring)
    cx, cy = p.centroid.coords[0]
    c = _ring_points(ring)
    r = np.hypot(c[:, 0] - cx, c[:, 1] - cy)
    out = {"centre": [round(cx, 2), round(cy, 2)], "diameter": round(2 * math.sqrt(p.area / math.pi), 2),
           "r_min": round(float(r.min()), 2), "r_max": round(float(r.max()), 2), "shape": "round"}
    if r.max() - r.min() > 0.06 * r.max():
        ang = np.arctan2(c[:, 1] - cy, c[:, 0] - cx)
        for n in (6, 4, 3, 8, 5):                       # a corner every 2 pi / n: fit its phase
            z = np.sum((r - r.mean()) * np.exp(1j * n * ang))
            fit = abs(z) / (np.sum(np.abs(r - r.mean())) + 1e-12)
            if fit > 0.6 and abs(r.min() / r.max() - math.cos(math.pi / n)) < 0.04:
                corner = math.degrees(np.angle(z)) / n % (360 / n)
                out.update(_flats(c, (cx, cy), n, corner), sides=n,
                           across_corners=round(2 * float(r.max()), 2), first_corner_deg=round(corner, 1))
                out["ideal_across_corners"] = round(out["across_flats"] / math.cos(math.pi / n), 2)
                out["shape"] = f"regular {n}-gon" if out["regular"] else f"{n}-gon, not regular"
                break
        else:
            out["shape"] = "irregular"
    return out


def _radius(sec):
    """Median distance of the outline from its centroid."""
    ext = _largest(sec).exterior
    c = _ring_points(ext, 360)
    cx, cy = ext.centroid.coords[0]
    return float(np.median(np.hypot(c[:, 0] - cx, c[:, 1] - cy)))


def _rim_break(mesh, z_end, inward, body, reach=2.0, step=0.05, tol=0.1):
    """How a level's outline falls away as it nears its end face at `z_end` (`inward` = +1 if the
    level lies above that face, -1 below): (height over which it is more than `tol` short of the
    body radius, radius lost at the last whole slice). (0, 0) is a sharp edge at this resolution."""
    zs = z_end + inward * np.arange(step, reach, step)
    short = [(abs(z - z_end), body - _radius(s)) for z, s in zip(zs, slices(mesh, zs))
             if s is not None and abs(_radius(s) - body) < 3.0]
    broken = [(h, d) for h, d in short if d > tol]
    return (round(max(h for h, _ in broken), 2), round(max(d for _, d in broken), 2)) if broken else (0.0, 0.0)


def _holes(mesh, z_lo, z_hi):
    """Holes of one level, seen at three heights and merged by position. A scanner sees a hole's
    mouth better than its bore, so each hole reports its roundest sighting."""
    seen = []
    for sec in slices(mesh, [z_lo + 0.1 * (z_hi - z_lo), (z_lo + z_hi) / 2, z_hi - 0.1 * (z_hi - z_lo)]):
        for ring in (_largest(sec).interiors if sec is not None else []):
            h = _hole(ring)
            if h["diameter"] < 1.0:
                continue
            for group in seen:
                if math.dist(group[0]["centre"], h["centre"]) < max(2.0, 0.3 * h["diameter"]):
                    group.append(h)
                    break
            else:
                seen.append([h])
    best = [max(g, key=lambda h: ("sides" in h, h["r_min"] / h["r_max"])) for g in seen]
    return sorted(best, key=lambda h: -h["diameter"])


def measure(mesh, dz=0.25, min_height=1.0):
    """Levels of the stepped outline, bottom to top, each with its holes and rim breaks. Slices
    are `dz` apart; rims are re-sliced every 0.05 mm."""
    z0, z1 = float(mesh.bounds[0][2]), float(mesh.bounds[1][2])
    zs = np.arange(z0 + dz / 2, z1, dz)
    rad = np.array([_radius(s) if s is not None else np.nan for s in slices(mesh, zs)])
    levels, i = [], 0
    while i < len(zs):
        j = i
        while j + 1 < len(zs) and abs(rad[j + 1] - rad[i]) < 3.0:      # same step of the outline
            j += 1
        lo, hi = float(zs[i] - dz / 2), float(zs[j] + dz / 2)
        if not np.isnan(rad[i]) and hi - lo >= min_height:             # thinner = a face being crossed
            body = float(np.median(rad[i:j + 1]))
            bh, bd = _rim_break(mesh, lo, +1, body)
            th, td = _rim_break(mesh, hi, -1, body)
            ext = _largest(slices(mesh, [(lo + hi) / 2])[0]).exterior
            ep = _ring_points(ext, 360)
            er = np.hypot(ep[:, 0] - ext.centroid.x, ep[:, 1] - ext.centroid.y)
            levels.append({"z": [round(lo, 2), round(hi, 2)], "height": round(hi - lo, 2),
                           "outer_diameter": round(2 * body, 2),
                           "centre": [round(ext.centroid.x, 2), round(ext.centroid.y, 2)],
                           "round": bool(er.max() - er.min() < 0.02 * er.max() + 0.2),
                           "bottom_break": {"height": bh, "radius_lost": bd},
                           "top_break": {"height": th, "radius_lost": td},
                           "holes": _holes(mesh, lo, hi)})
        i = j + 1
    return {"extents": [round(float(v), 2) for v in mesh.extents], "slice_spacing": dz, "levels": levels}


def _snap(v, grid=0.5, within=0.3):
    """A scanned size as a designer would have typed it: the nearest `grid` multiple when the scan
    is within `within` of it, else the measurement to 0.01."""
    g = round(v / grid) * grid
    return round(g, 6) if abs(g - v) <= within else round(v, 2)


def tree(measured, snap=True):
    """A feature tree from measure()'s output, for parts this module can describe: round steps
    stacked along Z, with through holes that are round or regular polygons. Returns (spec, notes).

    Each recognised shape becomes the feature a designer would use, with one size: a step is a
    circle and a pad; a regular hexagon is an ngon with one across-flats value (so it is regular
    by construction, whatever the scan's six sides measure); equally spaced holes at one radius
    become one bolt circle with one diameter. With `snap`, sizes within 0.3 mm of a 0.5 mm step
    take that value. Anything it cannot describe raises ValueError or is listed in the notes."""
    import ir as IR
    sn = _snap if snap else (lambda v, *a, **k: round(v, 3))
    levels, notes = measured["levels"], []
    if not levels or not all(lv["round"] for lv in levels):
        raise ValueError("only parts made of round steps along Z are handled")
    ax = np.mean([lv["centre"] for lv in levels], axis=0)                # the part's axis
    cuts = [levels[0]["z"][0]] + [(a["z"][1] + b["z"][0]) / 2 for a, b in zip(levels, levels[1:])] \
        + [levels[-1]["z"][1]]
    feats, prev = [], None
    for i, lv in enumerate(levels):
        d, h = sn(lv["outer_diameter"]), sn(cuts[i + 1] - cuts[i])
        feats.append(IR.sketch(f"step{i + 1}_outline", circles=[(0, 0, d / 2)],
                               on={"face_of": prev, "side": "top"} if prev else None))
        prev = f"step{i + 1}"
        feats.append(IR.pad(prev, f"step{i + 1}_outline", h))
        for end in ("bottom_break", "top_break"):
            if lv[end]["height"] >= 0.5 and lv[end]["radius_lost"] >= 0.5 and not (i == 0 and end == "bottom_break"):
                notes.append(f"{prev}: {end.replace('_', ' ')} of {lv[end]['height']} x {lv[end]['radius_lost']} mm "
                             f"seen but not modelled")

    holes = []                                   # merged across levels: [hole, set of level indices]
    for i, lv in enumerate(levels):
        for h in lv["holes"]:
            for rec in holes:
                if math.dist(rec[0]["centre"], h["centre"]) < 1.0:
                    rec[1].add(i)
                    if ("sides" in h, h["r_min"] / h["r_max"]) > ("sides" in rec[0], rec[0]["r_min"] / rec[0]["r_max"]):
                        rec[0] = h
                    break
            else:
                holes.append([h, {i}])
    usable = []
    for h, seen in holes:
        top = max(seen)
        off = math.dist(h["centre"], ax)
        clear = top + 1 == len(levels) or off - h["r_max"] >= levels[top + 1]["outer_diameter"] / 2 - 0.5
        if min(seen) != 0 or seen != set(range(top + 1)) or not clear:
            notes.append(f"hole at {h['centre']} is not a through hole; left out")
        else:
            usable.append((h, off))

    rounds = sorted((h for h, off in usable if "sides" not in h and off > 0.5),
                    key=lambda h: math.atan2(h["centre"][1] - ax[1], h["centre"][0] - ax[0]))
    n = len(rounds)
    if n >= 3:
        rad = [math.dist(h["centre"], ax) for h in rounds]
        ang = [math.degrees(math.atan2(h["centre"][1] - ax[1], h["centre"][0] - ax[0])) for h in rounds]
        phase = [(a - k * 360.0 / n + 180) % 360 - 180 for k, a in enumerate(ang)]
        if max(rad) - min(rad) < 1.0 and max(phase) - min(phase) < 3.0:
            good = [h["diameter"] for h in rounds if h["shape"] == "round"] or [h["diameter"] for h in rounds]
            d, R, p0 = sn(float(np.median(good))), sn(2 * float(np.mean(rad))) / 2, float(np.mean(phase))
            feats.append(IR.sketch("bolt_circle", circles=[
                (round(R * math.cos(math.radians(p0 + k * 360.0 / n)), 3),
                 round(R * math.sin(math.radians(p0 + k * 360.0 / n)), 3), d / 2) for k in range(n)]))
            feats.append(IR.pocket("bolt_holes", "bolt_circle", through=True))
            notes.append(f"{n} holes read as one pattern: dia {d} on a {2 * R} bolt circle, equally spaced")
            for h in rounds:
                if h["shape"] != "round" or abs(h["diameter"] - d) > 0.5:
                    notes.append(f"hole at {h['centre']} scanned as {h['shape']}, dia {h['diameter']}; "
                                 f"given the pattern's {d}")
            rounds = []
    for k, h in enumerate(rounds):
        c = (h["centre"][0] - ax[0], h["centre"][1] - ax[1])
        feats.append(IR.sketch(f"hole{k + 1}_profile", circles=[(round(c[0], 2), round(c[1], 2), sn(h["diameter"]) / 2)]))
        feats.append(IR.pocket(f"hole{k + 1}", f"hole{k + 1}_profile", through=True))
    for k, (h, off) in enumerate((h, off) for h, off in usable if "sides" in h or off <= 0.5):
        c = (0.0, 0.0) if off < 0.5 else (round(h["centre"][0] - ax[0], 2), round(h["centre"][1] - ax[1], 2))
        name = "bore" if off < 0.5 else f"socket{k + 1}"
        if "sides" in h and h["regular"]:
            feats.append(IR.sketch(f"{name}_profile", ngons=[(c[0], c[1], sn(h["across_flats"]), h["sides"],
                                                            round(h["first_corner_deg"] * 2) / 2)]))
            notes.append(f"{name}: scan's flats measure {h['flat_pairs']} (spread {h['flat_spread']} mm, angles "
                         f"within {h['angle_error']} deg); modelled as one regular {h['sides']}-gon, "
                         f"{sn(h['across_flats'])} across flats")
        elif "sides" in h:
            notes.append(f"{name}: a {h['sides']}-gon but not regular (flats {h['flat_pairs']}); left out")
            continue
        else:
            feats.append(IR.sketch(f"{name}_profile", circles=[(c[0], c[1], sn(h["diameter"]) / 2)]))
        feats.append(IR.pocket(name, f"{name}_profile", through=True))
    return IR.part("part", *feats), notes


def spec_mesh(spec):
    """An IR spec's solid as a trimesh (build123d reference build)."""
    import trimesh

    import b3d_emit
    part, _ = b3d_emit.emit(spec)
    vs, ts = part.tessellate(0.02, 0.05)
    return trimesh.Trimesh(np.array([[v.X, v.Y, v.Z] for v in vs]), np.array(ts), process=True)


def compare(spec, mesh, n=80, scale=False):
    """Volumetric overlap of the spec's solid with the mesh. Both are centred on their XY bounding
    boxes and stood on z = 0; the spin about Z is searched. With `scale` the spec is first scaled
    to the mesh's largest extent. Returns {"iou_pct", "spin_deg", "scale", "dvol_pct"}."""
    from shapely import affinity
    k = 1.0
    if scale:
        import image_recognize
        k = float(max(mesh.extents)) / float(max(spec_mesh(spec).extents))
        spec = image_recognize.scale_spec(spec, k)
    a, b = mesh, spec_mesh(spec)
    top = max(a.extents[2], b.extents[2])
    zs = (np.arange(n) + 0.5) * top / n

    def cut(m):
        c = (m.bounds[0] + m.bounds[1]) / 2
        return [affinity.translate(s, -c[0], -c[1]).simplify(0.02) if s is not None else None
                for s in slices(m, zs + m.bounds[0][2])]

    sa, sb = cut(a), cut(b)

    def iou(deg, idx):
        inter = union = 0.0
        for i in idx:
            p, q = sa[i], sb[i]
            if p is None or q is None:
                union += (p or q).area if (p or q) is not None else 0.0
                continue
            q = affinity.rotate(q, deg, origin=(0, 0))
            inter += p.intersection(q).area
            union += p.union(q).area
        return inter / union if union else 0.0

    few = range(0, n, max(1, n // 10))
    best = max(np.arange(0, 360, 2.0), key=lambda d: iou(d, few))
    best = max(np.arange(best - 2, best + 2.01, 0.25), key=lambda d: iou(d, few))
    va = sum(s.area for s in sa if s is not None) * top / n
    vb = sum(s.area for s in sb if s is not None) * top / n
    return {"iou_pct": round(100 * iou(best, range(n)), 2), "spin_deg": round(float(best) % 360, 2),
            "scale": round(k, 4), "dvol_pct": round(100 * (vb - va) / va, 2)}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Measure a scanned mesh; score a feature tree against it.")
    ap.add_argument("mesh")
    ap.add_argument("--spec", help="IR JSON (or an image_recognize result) to compare")
    ap.add_argument("--scale", action="store_true", help="scale the spec to the mesh's largest extent")
    ap.add_argument("--tree", metavar="OUT", help="build a feature tree from the measurements and write it here")
    ap.add_argument("--emit", help="write the measurements (and comparison) as JSON")
    a = ap.parse_args()
    mesh = load(a.mesh)
    out = {"mesh": os.path.basename(a.mesh), "measured": measure(mesh)}
    m = out["measured"]
    print(f"{out['mesh']}: extents {m['extents']} mm, sliced every {m['slice_spacing']} mm")
    for lv in m["levels"]:
        bb, tb = lv["bottom_break"], lv["top_break"]
        print(f"  z {lv['z'][0]:.1f}..{lv['z'][1]:.1f}  dia {lv['outer_diameter']}  height {lv['height']}"
              f"  rim break (height x radius lost): bottom {bb['height']} x {bb['radius_lost']}, "
              f"top {tb['height']} x {tb['radius_lost']}")
        for h in lv["holes"]:
            what = (f"{h['shape']}, flats {h['flat_pairs']}, {h['across_corners']} across corners "
                    f"(sharp would be {h['ideal_across_corners']}), first corner at {h['first_corner_deg']} deg" if "sides" in h
                    else f"{h['shape']}, dia {h['diameter']} (radius {h['r_min']}..{h['r_max']})")
            print(f"    hole at {h['centre']}: {what}")
    spec = None
    if a.tree:
        spec, out["notes"] = tree(m)
        spec["name"] = os.path.splitext(out["mesh"])[0].lower()
        with open(a.tree, "w") as fh:
            json.dump(spec, fh, indent=1)
        print(f"tree: {len(spec['features'])} features -> {a.tree}")
        for note in out["notes"]:
            print(f"  note: {note}")
    elif a.spec:
        with open(a.spec) as fh:
            spec = json.load(fh)
    if spec:
        out["compare"] = compare(spec.get("spec", spec), mesh, scale=a.scale)
        c = out["compare"]
        print(f"tree vs mesh: overlap {c['iou_pct']}%  volume {c['dvol_pct']:+}%  "
              f"(tree x{c['scale']}, spun {c['spin_deg']} deg)")
    if a.emit:
        with open(a.emit, "w") as fh:
            json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
