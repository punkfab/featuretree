#!/usr/bin/env python3
"""Screenshot the recovered CTC-01 tree as a native FreeCAD PartDesign document.

Pipeline: STEP -> step_recognize -> IR -> gen.emit (freecadcmd builds the .FCStd)
-> the FreeCAD GUI opens it under Xvfb -> the real framebuffer is captured with
ImageMagick `import`. A Qt widget grab() is NOT used, because it does not capture
the OpenGL viewport.

The GUI runs with FREECAD_USER_HOME pointed at a throwaway directory. Without that
it reads the invoking user's real FreeCAD config, and any pending Document
Recovery from their own sessions pops a modal dialog over the screenshot -- and
must never be clicked by a script.

Requirements: the extracted FreeCAD AppImage (see runner.py), xvfb-run, ImageMagick.

Run from the REPO ROOT:
    python3 paper/figures/freecad_screenshot.py
Writes: paper/figures/freecad_tree.png  (and freecad_view.png, the viewport alone)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.getcwd())

STEP = os.path.expanduser(
    "~/Downloads/NIST-PMI-STEP-Files/AP203 geometry only/nist_ctc_01_asme1_rd.stp")
OUT = Path("paper/figures/freecad_tree.png")
GUI_SCRIPT = Path(__file__).with_name("_freecad_gui_shot.py").resolve()


def freecad_gui() -> str:
    import runner
    cmd = Path(runner.freecadcmd_path())
    gui = cmd.with_name("freecad")
    if not gui.exists():
        sys.exit(f"FreeCAD GUI binary not found next to {cmd}")
    return str(gui)


def main():
    import gen
    import step_recognize as sr

    work = Path(tempfile.mkdtemp(prefix="ft_shot_"))
    spec, rep = sr.recognize(STEP, name="CTC01")
    gen.emit(spec, str(work / "ctc01.FCStd"))
    print(f"recovered: verified={rep['verified']} dvol={rep['dvol_pct']}% "
          f"features={len(spec['features'])}")

    (work / "fchome").mkdir()
    env = {**os.environ,
           "FREECAD_USER_HOME": str(work / "fchome"),     # isolate from the user's config
           "FT_SHOT_DIR": str(work),
           "FT_SHOT_DOC": "ctc01.FCStd",
           "FT_SHOT_PNG": str(OUT.resolve())}
    subprocess.run(["xvfb-run", "-a", "-s", "-screen 0 1600x1000x24 +extension GLX +render",
                    freecad_gui(), str(GUI_SCRIPT)],
                   cwd=str(work), env=env, timeout=300,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log = (work / "shot2.log").read_text() if (work / "shot2.log").exists() else ""
    if "screen captured" not in log:
        sys.exit("capture failed:\n" + log)
    shutil.rmtree(work, ignore_errors=True)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
