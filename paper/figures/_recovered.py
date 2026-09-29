"""Load a recovered tree saved by run_corpus.py, or recognise it if there is none."""
import json
import os

DIR = os.path.join("paper", "figures", "recovered")


def load(step_path):
    """(spec, report) for a corpus part. Reads paper/figures/recovered/<part>.json when present so
    every measurement describes the SAME tree the corpus run produced; recognises otherwise."""
    fn = os.path.join(DIR, os.path.basename(step_path) + ".json")
    if os.path.exists(fn):
        d = json.load(open(fn))
        rep = d["report"]
        if rep.get("extrude_axis") is not None:
            rep["extrude_axis"] = tuple(rep["extrude_axis"])
        return d["spec"], rep
    import step_recognize as sr
    return sr.recognize(step_path)
