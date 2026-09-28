"""Runs INSIDE the FreeCAD GUI (launched by freecad_screenshot.py). Do not run directly."""
import os, subprocess
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui

SC = os.environ["FT_SHOT_DIR"]
LOG = open(os.path.join(SC, "shot2.log"), "w")
def log(*a):
    LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

def step1():
    try:
        mw = Gui.getMainWindow()
        mw.setGeometry(0, 0, 1600, 1000)
        doc = App.openDocument(os.path.join(SC, os.environ["FT_SHOT_DOC"]))
        Gui.activateWorkbench("PartDesignWorkbench")
        doc.recompute()
        # hide everything that is not the tree or the 3D view
        for dw in mw.findChildren(QtGui.QDockWidget):
            t = dw.windowTitle()
            if t in ("Report view", "Python console", "Launcher", "Selection view", "Property view"):
                dw.hide()
        # show the Model tab of the combo view
        for tab in mw.findChildren(QtGui.QTabWidget):
            for i in range(tab.count()):
                if tab.tabText(i) == "Model":
                    tab.setCurrentIndex(i)
        # expand only the Body, one level: its children are the operation list
        for tw in mw.findChildren(QtGui.QTreeWidget):
            tw.collapseAll()
            root = tw.invisibleRootItem()
            def walk(item, depth):
                for k in range(item.childCount()):
                    c = item.child(k)
                    txt = c.text(0)
                    if depth == 0:            # document node
                        c.setExpanded(True); walk(c, 1)
                    elif depth == 1 and ("Body" in txt or txt == "CTC01"):
                        c.setExpanded(True)
            walk(root, 0)
        body = next(o for o in doc.Objects if o.TypeId == "PartDesign::Body")
        Gui.ActiveDocument.ActiveView.setActiveObject("pdbody", body)
        Gui.Selection.clearSelection()
        v = Gui.ActiveDocument.ActiveView
        v.viewIsometric(); v.fitAll()
        log("opened", len(doc.Objects), "objects;",
            "body children:", len([o for o in doc.Objects if o.TypeId.startswith("PartDesign::")]))
        QtCore.QTimer.singleShot(1500, step1b)
    except Exception as e:
        import traceback; log("step1 error", traceback.format_exc()); QtCore.QTimer.singleShot(100, quit_)

def step1b():
    mw = Gui.getMainWindow()
    # no popup notifications over the viewport
    App.ParamGet("User parameter:BaseApp/Preferences/NotificationArea").SetBool("NotificationAreaEnabled", False)
    for w in mw.findChildren(QtGui.QWidget):
        if w.metaObject().className() in ("Gui::NotificationBox",):
            w.hide()
    for tab in mw.findChildren(QtGui.QTabWidget):
        texts = [tab.tabText(i) for i in range(tab.count())]
        log("tabwidget", texts)
        for i, t in enumerate(texts):
            if t.replace("&", "").strip().lower() == "model":
                tab.setCurrentIndex(i); log("model tab set")
    for dw in mw.findChildren(QtGui.QDockWidget):
        log("dock", repr(dw.windowTitle()), dw.isVisible())
        if dw.windowTitle() in ("Report view", "Python console", "Selection view", "Property view"):
            dw.hide()
        if dw.windowTitle() == "Model":
            dw.raise_(); dw.show()
            mw.resizeDocks([dw], [440], QtCore.Qt.Horizontal)
            for tw in dw.findChildren(QtGui.QTreeWidget):
                tw.collapseAll()
                root = tw.invisibleRootItem()
                for a in range(root.childCount()):
                    d = root.child(a); d.setExpanded(True)          # document node
                    for b in range(d.childCount()):
                        c = d.child(b)
                        if "Body" in c.text(0):
                            c.setExpanded(True)                     # the operation list
                log("tree top:", [root.child(0).child(b).text(0) for b in range(min(5, root.child(0).childCount()))])
    # the tree gets the whole dock: hide the (empty) property editor under it
    for w in mw.findChildren(QtGui.QWidget):
        cn = w.metaObject().className()
        if cn in ("Gui::PropertyView", "Gui::DockWnd::PropertyView"):
            w.hide(); log("hid", cn)
    # popup notifications are separate top-level windows
    for w in QtGui.QApplication.topLevelWidgets():
        cn = w.metaObject().className()
        if w.isVisible() and w is not mw:
            log("toplevel", cn); w.hide()
    QtCore.QTimer.singleShot(2500, step2)

def step2():
    for w in QtGui.QApplication.topLevelWidgets():
        if w.isVisible() and w is not Gui.getMainWindow():
            w.hide()
    try:
        subprocess.run(["import", "-window", "root", os.environ["FT_SHOT_PNG"]],
                       check=True, env=os.environ)
        log("screen captured")
    except Exception as e:
        log("step2 error", repr(e))
    QtCore.QTimer.singleShot(300, quit_)

def quit_():
    LOG.close(); os._exit(0)

QtCore.QTimer.singleShot(3000, step1)
