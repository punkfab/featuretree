"""ir.py — a neutral, named feature-tree IR (a small CAD DSL).

The operation-preserving representation that no neutral *file* format provides: a
declarative, ordered list of named features with named parameters. It is the single
source of truth; per-target emitters (FreeCAD here) translate it into that tool's
*native* feature vocabulary, so the tree shows up editable on the left.

Design choices that make round-trip tractable:
  * every feature has a stable, human-meaningful `name` (-> the target object's Label)
    so a human edit can be matched back by name, not by kernel edge id;
  * parameters are named values, not positions in a blob;
  * geometry is referenced symbolically (a feature name + plane / a query), never by
    unstable kernel edge/face ids — the wall that kills neutral feature files.

Scope: sketches (rectangles, circles, AND arbitrary polygons/profiles-with-holes) on
principal planes or face-attached, Pad, Pocket (through/depth), Fillet (edge query).
Plain JSON-able dicts, so the IR crosses cleanly into FreeCAD's own Python (3.11).
"""


def sketch(name, plane="XY", circles=(), rects=(), polys=(), on=None, ngons=()):
    """A 2D sketch.
        circles: [(cx, cy, r), ...]
        rects:   [(w, h, cx, cy), ...]
        polys:   [wire, ...] where wire = [(x, y), ...]  (closed automatically).
                 The FIRST poly is the outer profile; any following polys are holes
                 in it — so an extruded profile-with-holes is one sketch -> one pad.
        ngons:   [(cx, cy, across_flats, sides, rotation), ...] — regular polygons, kept as their
                 parameters so a hexagon stays a hexagon when its size is edited. sides defaults
                 to 6; rotation (degrees, default 0) is the direction of the first corner. An ngon
                 is shorthand for a poly: lower() appends it to `polys`, where it nests like one.
        plane: "XY" (default) or "XZ" — use "XZ" for a revolve profile (x = radius, z = axial).
        on: None -> the `plane`; or a face QUERY {"face_of": feature, "side": "top"|"bottom"}
            (coords stay global; the emitter maps them into the face's local frame).
    """
    d = {"kind": "sketch", "name": name, "plane": plane, "on": on,
         "circles": [list(c) for c in circles],
         "rects": [list(r) for r in rects],
         "polys": [[list(p) for p in poly] for poly in polys]}
    if ngons:                      # only written when used, so existing IR is unchanged
        d["ngons"] = [list(g) for g in ngons]
    return d


def ngon_poly(cx, cy, across_flats, sides=6, rotation=0.0):
    """The corners of a regular polygon: `across_flats` is twice the centre-to-side distance (for
    an even `sides`, the spanner size); the first corner points along `rotation` degrees."""
    import math
    n = int(sides)
    r = across_flats / 2.0 / math.cos(math.pi / n)
    return [[cx + r * math.cos(math.radians(rotation) + 2 * math.pi * k / n),
             cy + r * math.sin(math.radians(rotation) + 2 * math.pi * k / n)] for k in range(n)]


def pad(name, sketch, length, symmetric=False, taper=0.0):
    """Extrude a sketch. `taper` (degrees) drafts the walls: POSITIVE shrinks the profile along the
    extrusion, negative grows it — build123d's convention, which the FreeCAD emitter maps onto
    PartDesign's TaperAngle. Molded parts carry ~0.5-3 deg of draft so they release from the
    mould. The key is only written when non-zero, so untapered IR is unchanged."""
    d = {"kind": "pad", "name": name, "sketch": sketch, "length": length, "symmetric": symmetric}
    if taper:
        d["taper"] = float(taper)
    return d


def pocket(name, sketch, through=True, length=None, taper=0.0):
    """Cut a sketch into the solid. `taper` (degrees, blind pockets only): POSITIVE shrinks the
    profile as the cut goes deeper — the drafted cavity of a molded box."""
    d = {"kind": "pocket", "name": name, "sketch": sketch, "through": through, "length": length}
    if taper:
        if through:
            raise ValueError("a tapered pocket must be blind (through=False)")
        d["taper"] = float(taper)
    return d


def fillet(name, radius, select):
    """Round edges chosen by a QUERY (resolved against live geometry at build time, never stored
    kernel edge ids). Two forms:
        {"circles": "top_outer" | "top_all"}   circular edges on the top of the part
        {"edges_of": feature, "side": "top" | "bottom"}
            the edges where an earlier pad's or pocket's walls meet its end: a pad's top or bottom
            rim, a pocket's mouth ("top") or its floor / far opening ("bottom")."""
    return {"kind": "fillet", "name": name, "radius": radius, "select": select}


def chamfer(name, distance, select):
    """Break edges with an equal-distance (45 degree) chamfer of `distance`. Edges are chosen by
    the same QUERY as fillet()."""
    return {"kind": "chamfer", "name": name, "distance": distance, "select": select}


def revolve(name, sketch, angle=360.0):
    """Revolve a profile sketch about the Z axis by `angle` degrees. The sketch must lie in a
    plane CONTAINING the axis — the XZ plane (plane="XZ"), with all radii x >= 0 — and its `polys`
    give the cross-section. This is the primitive round parts need (wheels, bosses, nozzles) that
    sketch/pad can't: a body of revolution."""
    return {"kind": "revolve", "name": name, "sketch": sketch, "angle": angle}


def polar_pocket(name, radius, length, mount_r, z=0.0, count=4, phase=0.0):
    """Cut `count` cylindrical pockets evenly spaced about the Z axis, each of `radius` and
    `length`, its axis TANGENT to the circle of radius `mount_r` at axial height `z`, the ring
    rotated by `phase` degrees. Models a ring of roller pockets (omni wheel), a pin circle on a
    hub, etc. — a polar pattern of a tangent bore that plain pocket() (axial only) can't place."""
    return {"kind": "polar_pocket", "name": name, "radius": radius, "length": length,
            "mount_r": mount_r, "z": z, "count": count, "phase": phase}


def prism_cut(name, origin, normal, xdir, depth, polys=(), taper=0.0):
    """Subtract a 2D profile extruded along an arbitrary axis at an arbitrary location. The profile
    (polys — [outer, hole, hole, ...], each a wire of (u, v[, bulge]) in the plane's own 2D frame)
    lies in the plane through `origin` with local +X = `xdir` and outward normal `normal`; it is
    extruded `depth` along +normal and cut from the running solid.

    This is the general placed cut the STEP recognizer emits for RECOVERED features that plain
    face-attached pocket() can't place: multi-level / through pockets along the main axis (normal ∥
    the extrude axis) AND cross-axis holes (normal ⊥ it). One primitive, any axis, any location —
    a profile swept along some direction, subtracted. `taper` (degrees) drafts it: positive shrinks
    the profile along +normal, as for pad/pocket."""
    return {"kind": "prism_cut", "name": name,
            "origin": [round(float(c), 6) for c in origin],
            "normal": [round(float(c), 6) for c in normal],
            "xdir": [round(float(c), 6) for c in xdir], "depth": depth,
            "polys": [[list(p) for p in poly] for poly in polys]} | ({"taper": float(taper)} if taper else {})


def part(name, *features):
    return {"name": name, "features": list(features)}


def _geom():
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "targets"))
    import _geom as G
    return G


def lower(spec):
    """The spec as backends consume it — a copy in which
      * every sketch's `ngons` are appended to its `polys` (and the key dropped);
      * every fillet / chamfer selected by {"edges_of": ...} carries `picks`: one 3D point on each
        edge it means, worked out from the IR alone. A backend rounds or breaks the live edges
        through those points, so all backends choose the same edges without sharing kernel ids.
    Idempotent. The symbolic spec stays the source of truth: never store a lowered one."""
    import copy
    import math
    G = _geom()
    out = copy.deepcopy(spec)
    zlo = zhi = None                     # the part's extent so far
    sk, pads, made = {}, [], {}          # sketch -> (z0, side, loops); pads; feature name -> record

    def inside(loops, x, y):
        polys = [G.loop_points(lp) for lp in loops]
        simple = [p for lp, p in zip(loops, polys) if lp["segments"][0][0] == "circle" or lp.get("solo")]
        nested = [p for lp, p in zip(loops, polys) if not (lp["segments"][0][0] == "circle" or lp.get("solo"))]
        return any(G._pip(x, y, p) for p in simple) or sum(G._pip(x, y, p) for p in nested) % 2 == 1

    def mids(loops):
        pts = []
        for lp in loops:
            for sg in lp["segments"]:
                if sg[0] == "circle":      # 1 rad round: clear of the seam kernels put at 0 or 180 deg
                    pts.append((sg[1][0] + sg[2] * math.cos(1.0), sg[1][1] + sg[2] * math.sin(1.0)))
                elif sg[0] == "arc":
                    pts.append(tuple(sg[2]))
                else:
                    pts.append(((sg[1][0] + sg[2][0]) / 2, (sg[1][1] + sg[2][1]) / 2))
        return pts

    for f in out["features"]:
        k = f["kind"]
        if k == "sketch":
            if f.get("ngons"):
                f["polys"] = f.get("polys", []) + [ngon_poly(*g) for g in f["ngons"]]
            f.pop("ngons", None)
            on = f.get("on")
            side = (on or {}).get("side", "top") if on else None
            z0 = (zhi if side == "top" else zlo) if on and zhi is not None else 0.0
            loops = []
            if f.get("plane", "XY") == "XY" or on:
                loops = G.sketch_loops(f.get("circles", []), [], f.get("polys", []))
                loops += [{"segments": G.rect_segments(*r), "include": True, "solo": True}
                          for r in f.get("rects", [])]
            sk[f["name"]] = (z0, side, loops, f)
        elif k == "pad" and f["sketch"] in sk:
            z0, side, loops, _ = sk[f["sketch"]]
            L = f["length"]
            a, b = (z0 - L / 2, z0 + L / 2) if f.get("symmetric") else \
                   ((z0 - L, z0) if side == "bottom" else (z0, z0 + L))
            zlo, zhi = (a if zlo is None else min(zlo, a)), (b if zhi is None else max(zhi, b))
            pads.append((loops, a, b))
            made[f["name"]] = ("pad", loops, a, b)
        elif k == "pocket" and f["sketch"] in sk:
            z0, _, loops, _ = sk[f["sketch"]]
            made[f["name"]] = ("pocket", loops, f, zhi if zhi is not None else 0.0, z0)
        elif k == "revolve" and f["sketch"] in sk:
            vs = [p[1] for poly in sk[f["sketch"]][3].get("polys", []) for p in poly]
            if vs:
                zlo = min(vs) if zlo is None else min(zlo, min(vs))
                zhi = max(vs) if zhi is None else max(zhi, max(vs))
        elif k in ("fillet", "chamfer") and "edges_of" in f.get("select", {}):
            rec = made.get(f["select"]["edges_of"])
            side = f["select"].get("side", "top")
            picks = []
            if rec and rec[0] == "pad":
                picks = [[x, y, rec[3] if side == "top" else rec[2]] for x, y in mids(rec[1])]
            elif rec:
                _, loops, pf, top_then, z0 = rec
                for x, y in mids(loops):
                    cover = [(a, b) for lps, a, b in pads if inside(lps, x, y)]
                    if not cover:
                        continue
                    if side == "top":
                        z = max(b for _, b in cover)
                    elif pf["through"]:
                        z = min(a for a, _ in cover)
                    else:            # a blind pocket's floor: `length` in from the face it starts on
                        z = top_then - pf["length"] if z0 >= top_then - 1e-6 else z0 + pf["length"]
                    picks.append([x, y, z])
            f["picks"] = [[round(c, 6) for c in p] for p in picks]
    return out


def update_from_params(spec, params):
    """Flow human edits read back from any backend ({feature name: {key: value}} — FreeCAD's
    fc_read, the Fusion read script, SolidWorks --dump) into the IR, matched by feature name."""
    for f in spec["features"]:
        p = params.get(f["name"])
        if not p:
            continue
        if f["kind"] in ("pad", "pocket") and "length" in p and f.get("length") is not None:
            f["length"] = p["length"]
        if f["kind"] == "fillet" and "radius" in p:
            f["radius"] = p["radius"]
        if f["kind"] == "chamfer" and "distance" in p:
            f["distance"] = p["distance"]
        if f["kind"] == "revolve" and "angle" in p:
            f["angle"] = p["angle"]
        if f["kind"] == "prism_cut" and ("depth" in p or "length" in p):
            f["depth"] = p.get("depth", p.get("length"))   # FreeCAD holds a placed cut as a Pocket: 'length'
        if f["kind"] == "sketch" and "radii" in p:
            for i, r in enumerate(p["radii"]):
                if i < len(f["circles"]):
                    f["circles"][i][2] = r
    return spec


update_from_freecad = update_from_params     # the original name, kept for existing callers


def validate(spec):
    """Well-formedness of an IR spec, as a list of problems (empty = valid). Every backend is
    entitled to assume these hold; build123d happens to tolerate some violations (it unions
    loops one at a time) where FreeCAD and Onshape reject them, so a spec that breaks a rule can
    VERIFY in one backend and fail in another.

      names      feature names unique; every sketch reference names an EARLIER sketch
      loops      closed: >= 3 segments, or >= 2 if any is an arc; no zero-length segment; no
                 self-intersection
      profiles   within one sketch, loop boundaries never touch or cross (nesting is fine)
      ngons      at least 3 sides and a positive size
      pocket     a taper needs a blind pocket; a blind pocket needs a positive length
      edges      a fillet / chamfer has a positive size; {"edges_of": f} names an earlier pad or
                 pocket and resolves to at least one edge
      placement  prism_cut normal and xdir are non-zero and orthogonal

    Loop checks need shapely; without it they are skipped and reported as one problem."""
    import math
    G = _geom()
    problems, seen, sketches, solids = [], set(), set(), set()
    for f in spec["features"]:               # before lowering: a bad ngon cannot be expanded
        for g in (f.get("ngons") or []) if f["kind"] == "sketch" else []:
            if len(g) < 3 or not g[2] > 0 or (len(g) > 3 and int(g[3]) < 3):
                problems.append(f"{f['name']}: an ngon needs a positive size and at least 3 sides")
    if problems:
        return problems
    spec = lower(spec)

    def loops_ok(where, loops):
        try:
            from shapely.geometry import LineString, Polygon
        except ImportError:
            problems.append(f"{where}: loop checks skipped (pip install shapely)")
            return
        polys = []
        for i, lp in enumerate(loops):
            seg = lp["segments"]
            if seg[0][0] != "circle":
                arcs = any(sg[0] == "arc" for sg in seg)
                if len(seg) < (2 if arcs else 3):          # two arcs close a loop; lines need three
                    problems.append(f"{where}: loop {i} has {len(seg)} segment(s)")
                    continue
                if any(math.dist(sg[1], sg[-1]) < 1e-6 for sg in seg):
                    problems.append(f"{where}: loop {i} has a zero-length segment")
            poly = Polygon(G.loop_points(lp))
            if not poly.is_valid:
                problems.append(f"{where}: loop {i} self-intersects")
            polys.append((i, poly))
        for a in range(len(polys)):
            for b in range(a + 1, len(polys)):
                (i, p), (j, q) = polys[a], polys[b]
                if LineString(p.exterior.coords).intersects(LineString(q.exterior.coords)):
                    problems.append(f"{where}: loops {i} and {j} touch or cross")

    for f in spec["features"]:
        n, k = f["name"], f["kind"]
        if n in seen:
            problems.append(f"{n}: duplicate feature name")
        seen.add(n)
        if k == "sketch":
            sketches.add(n)
            loops_ok(n, G.sketch_loops(f.get("circles", []), f.get("rects", []), f.get("polys", [])))
        elif k in ("fillet", "chamfer"):
            size = f.get("radius" if k == "fillet" else "distance")
            if not (size or 0) > 0:
                problems.append(f"{n}: {k} needs a positive size")
            sel = f.get("select") or {}
            if "edges_of" in sel:
                if sel["edges_of"] not in solids:
                    problems.append(f"{n}: '{sel['edges_of']}' is not an earlier pad or pocket")
                elif sel.get("side", "top") not in ("top", "bottom"):
                    problems.append(f"{n}: side must be top or bottom")
                elif not f.get("picks"):
                    problems.append(f"{n}: the edge query selects nothing")
            elif sel.get("circles") not in ("top_outer", "top_all"):
                problems.append(f"{n}: select needs \"circles\" or \"edges_of\"")
        elif k in ("pad", "pocket", "revolve"):
            if k != "revolve":
                solids.add(n)
            if f["sketch"] not in sketches:
                problems.append(f"{n}: sketch '{f['sketch']}' is not an earlier sketch")
            if k == "pocket" and not f["through"] and not (f.get("length") or 0) > 0:
                problems.append(f"{n}: blind pocket needs a positive length")
            if k == "pocket" and f["through"] and f.get("taper"):
                problems.append(f"{n}: taper on a through pocket")
        elif k == "prism_cut":
            nn, xx = f["normal"], f["xdir"]
            if not any(nn) or not any(xx) or abs(sum(a * b for a, b in zip(nn, xx))) > 1e-6:
                problems.append(f"{n}: normal and xdir must be non-zero and orthogonal")
            loops_ok(n, G.sketch_loops(polys=f["polys"]))
    return problems


# --- built-in samples (also a smoke test: volume must match a build123d twin) ---

def sample_plate():
    """40x30x10 plate with an 8 mm through hole. FreeCAD volume == 11497.3 mm^3."""
    return part(
        "plate",
        sketch("outline", "XY", rects=[(40, 30, 0, 0)]),
        pad("body", "outline", length=10),
        sketch("hole_sketch", "XY", circles=[(0, 0, 4)]),
        pocket("hole", "hole_sketch", through=True),
    )


def sample_poly():
    """An L-shaped polygon profile + a hole, extruded — exercises the polygon primitive."""
    L = [(0, 0), (40, 0), (40, 14), (16, 14), (16, 30), (0, 30)]
    return part(
        "lbracket",
        sketch("profile", "XY", polys=[L]),
        pad("body", "profile", length=6),
        sketch("hole_sketch", "XY", circles=[(8, 8, 2.6)]),
        pocket("hole", "hole_sketch", through=True),
    )


SAMPLES = {"plate": sample_plate, "poly": sample_poly}
