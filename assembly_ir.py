"""assembly_ir.py — the ASSEMBLY half of the neutral IR: occurrences + parts + typed mates.

Additive to ir.py (which stays single-part). An assembly is a set of named OCCURRENCES, each placing
a PART (a single-part feature IR from ir.py / step_recognize) by a transform, plus typed MATES between
occurrences, gear COUPLINGS and named POSES. The mate vocabulary is deliberately the same closed set
cadgen (text-to-cad "CAD Skills") carries in its `.step.json` sidecar — revolute / slider /
cylindrical / fastened, an axis {origin, dir}, limits — so a cadgen assembly ingests losslessly and
can round-trip back out. Plain JSON-able dicts, like ir.py; nothing here is consumed by the existing
single-part emitters, so they cannot be affected by it.
"""

MATE_KINDS = ("revolute", "slider", "cylindrical", "fastened")


def occurrence(id, label, part=None, transform=None, color=None, component=None):
    """One placed instance of a part. `id` is the tree address ("o1", "o1.3", "o1.2.1" — depth-first,
    1-based, the same grammar cadgen uses so `#o1.3.f2` refs stay meaningful). `part` is the part's
    single-part IR spec (or None when only structure is known). `transform` is a 12-float row-major
    3x4 placement matrix, or None for identity."""
    return {"id": id, "label": label, "part": part,
            "transform": [round(float(v), 6) for v in transform] if transform else None,
            "color": list(color) if color else None, "component": component}


def mate(name, kind, parent, child, *, parent_id=None, child_id=None, axis=None, limits=None):
    """A typed joint from `parent` to `child` (occurrence LABELS; `*_id` are the resolved occurrence
    ids). `axis` = {"origin": [x,y,z], "dir": [x,y,z]} (None for fastened). `limits` = a mapping of DOF
    -> [lo, hi] (cadgen spells a 1-DOF mate's range as {"value": [lo, hi]})."""
    if kind not in MATE_KINDS:
        raise ValueError(f"mate {name!r}: kind must be one of {MATE_KINDS}, got {kind!r}")
    return {"name": name, "kind": kind, "parent": parent, "child": child,
            "parent_id": parent_id, "child_id": child_id,
            "axis": ({"origin": [float(v) for v in axis["origin"]], "dir": [float(v) for v in axis["dir"]]}
                     if axis and axis.get("origin") is not None and axis.get("dir") is not None else None),
            "limits": {str(k): [float(x) for x in v] for k, v in (limits or {}).items()}}


def coupling(name, gears, limits=None):
    """A gear ratio tying several mate DOFs to one driver (cadgen `couple`): gears = {dof: ratio}."""
    return {"name": name, "gears": {str(k): float(v) for k, v in dict(gears).items()},
            "limits": [float(x) for x in limits] if limits else None}


def assembly(name, occurrences, parts=None, mates=(), couplings=(), poses=None, provenance=None):
    """The assembly spec. `parts` maps a part key (usually the occurrence label) -> single-part IR."""
    return {"kind": "assembly", "name": name, "occurrences": list(occurrences),
            "parts": dict(parts or {}), "mates": list(mates), "couplings": list(couplings),
            "poses": {str(k): {str(d): float(v) for d, v in dict(vals).items()}
                      for k, vals in (poses or {}).items()},
            "provenance": dict(provenance or {})}


def mate_tree_problems(asm):
    """The structural rules a mate graph must satisfy (the same ones cadgen enforces, so what we
    ingest is what it would accept back): every child has at most ONE parent mate, no self-mates, no
    cycles (closed-loop linkages need a solver; this is a forward-kinematic tree). Returns a list of
    human-readable problems — empty means well-formed."""
    problems, parent_of = [], {}
    for m in asm["mates"]:
        c, p = m.get("child_id") or m["child"], m.get("parent_id") or m["parent"]
        if c == p:
            problems.append(f"mate {m['name']!r} mates {c!r} to itself")
        if c in parent_of:
            problems.append(f"occurrence {c!r} has more than one parent mate")
        parent_of[c] = p
    for start in parent_of:
        node, hops = start, 0
        while node in parent_of:
            node, hops = parent_of[node], hops + 1
            if node == start or hops > len(parent_of):
                problems.append(f"mate graph has a cycle through {start!r}")
                break
    return problems
